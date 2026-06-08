from sqlalchemy.orm import Session
from datetime import datetime
import json
import csv
import io
from typing import List, Tuple, Dict, Any
from . import models, schemas


VALID_STATUSES = ["draft", "issued", "synced", "closed"]
STATUS_TRANSITIONS = {
    "draft": ["issued"],
    "issued": ["synced", "draft"],
    "synced": ["closed", "issued"],
    "closed": []
}


def log_audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: int,
    details: dict = None,
    operator: str = None,
    batch_no: str = None
):
    audit_log = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        batch_no=batch_no,
        details=json.dumps(details, ensure_ascii=False) if details else None,
        operator=operator
    )
    db.add(audit_log)
    db.flush()


def can_transition_status(old_status: str, new_status: str) -> bool:
    if old_status not in STATUS_TRANSITIONS:
        return False
    return new_status in STATUS_TRANSITIONS[old_status]


def check_conflict(
    db: Session,
    task_package_id: int,
    device_code: str,
    item_name: str,
    new_value: str
) -> models.Conflict | None:
    existing = db.query(models.Reading).filter(
        models.Reading.task_package_id == task_package_id,
        models.Reading.device_code == device_code,
        models.Reading.item_name == item_name
    ).first()

    if existing and existing.reading_value != new_value:
        conflict = models.Conflict(
            task_package_id=task_package_id,
            device_code=device_code,
            item_name=item_name,
            existing_value=existing.reading_value,
            new_value=new_value,
            status="open"
        )
        return conflict
    return None


def has_open_conflicts(db: Session, task_package_id: int) -> bool:
    count = db.query(models.Conflict).filter(
        models.Conflict.task_package_id == task_package_id,
        models.Conflict.status == "open"
    ).count()
    return count > 0


def validate_package_status(
    db: Session,
    package_no: str,
    allowed_statuses: list[str]
) -> tuple[models.TaskPackage | None, dict | None]:
    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()

    if not package:
        return None, {
            "detail": f"任务包编号 '{package_no}' 不存在",
            "code": 40401
        }

    if package.status not in allowed_statuses:
        return None, {
            "detail": f"任务包状态为 '{package.status}'，不允许此操作。允许的状态: {allowed_statuses}",
            "code": 40901
        }

    return package, None


def generate_batch_no() -> str:
    return f"BATCH-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def validate_template_fields(template_data: Dict[str, Any], row_index: int) -> Tuple[bool, List[str]]:
    errors = []
    if not template_data.get("name"):
        errors.append(f"第 {row_index} 行: 模板名称不能为空")
    elif len(template_data["name"]) > 255:
        errors.append(f"第 {row_index} 行: 模板名称长度不能超过255字符")

    check_items = template_data.get("check_items", [])
    if not check_items:
        errors.append(f"第 {row_index} 行: 检查项列表不能为空")
    else:
        for i, item in enumerate(check_items):
            if not item.get("device_code"):
                errors.append(f"第 {row_index} 行 检查项{i+1}: 设备编号不能为空")
            if not item.get("item_name"):
                errors.append(f"第 {row_index} 行 检查项{i+1}: 检查项名称不能为空")

    return len(errors) == 0, errors


def validate_task_package_fields(pkg_data: Dict[str, Any], row_index: int) -> Tuple[bool, List[str]]:
    errors = []
    if not pkg_data.get("package_no"):
        errors.append(f"第 {row_index} 行: 任务包编号不能为空")
    elif len(pkg_data["package_no"]) > 100:
        errors.append(f"第 {row_index} 行: 任务包编号长度不能超过100字符")

    if not pkg_data.get("template_id"):
        errors.append(f"第 {row_index} 行: 模板ID不能为空")
    elif not isinstance(pkg_data["template_id"], int):
        errors.append(f"第 {row_index} 行: 模板ID必须是整数")

    return len(errors) == 0, errors


def check_template_name_duplicate(db: Session, name: str, exclude_id: int = None) -> bool:
    query = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.name == name
    )
    if exclude_id:
        query = query.filter(models.InspectionTemplate.id != exclude_id)
    return query.first() is not None


def check_package_no_duplicate(db: Session, package_no: str, exclude_id: int = None) -> bool:
    query = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    )
    if exclude_id:
        query = query.filter(models.TaskPackage.id != exclude_id)
    return query.first() is not None


def create_import_batch(
    db: Session,
    source_type: str,
    source_filename: str = None,
    total_records: int = 0,
    operator: str = None
) -> models.ImportBatch:
    batch = models.ImportBatch(
        batch_no=generate_batch_no(),
        source_type=source_type,
        source_filename=source_filename,
        total_records=total_records,
        operator=operator,
        status="processing"
    )
    db.add(batch)
    db.flush()
    return batch


def parse_csv_data(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
    templates = []
    task_packages = []
    errors = []

    try:
        reader = csv.DictReader(io.StringIO(content))
        for i, row in enumerate(reader, start=2):
            record_type = row.get("record_type", "").strip().lower()

            if record_type == "template":
                template = {
                    "name": row.get("template_name", "").strip(),
                    "description": row.get("description", "").strip(),
                    "check_items": []
                }

                check_item_str = row.get("check_items", "").strip()
                if check_item_str:
                    try:
                        template["check_items"] = json.loads(check_item_str)
                    except json.JSONDecodeError:
                        errors.append(f"第 {i} 行: check_items JSON 格式错误")
                        continue

                templates.append(template)

            elif record_type == "task_package":
                try:
                    template_id = int(row.get("template_id", "0"))
                except ValueError:
                    errors.append(f"第 {i} 行: template_id 必须是整数")
                    continue

                pkg = {
                    "package_no": row.get("package_no", "").strip(),
                    "template_id": template_id,
                    "operator": row.get("operator", "").strip() or None
                }
                task_packages.append(pkg)
            else:
                errors.append(f"第 {i} 行: 未知的 record_type '{record_type}'，应为 'template' 或 'task_package'")

    except Exception as e:
        errors.append(f"CSV 解析错误: {str(e)}")

    return templates, task_packages, errors


def process_batch_import(
    db: Session,
    templates_data: List[Dict],
    packages_data: List[Dict],
    source_type: str,
    source_filename: str = None,
    operator: str = None
) -> schemas.BatchImportResponse:
    total_records = len(templates_data) + len(packages_data)
    batch = create_import_batch(db, source_type, source_filename, total_records, operator)
    batch_no = batch.batch_no

    results: List[schemas.ImportRecordResult] = []
    success_count = 0
    failed_count = 0
    row_index = 1

    template_name_map: Dict[str, int] = {}
    for t in db.query(models.InspectionTemplate).all():
        template_name_map[t.name] = t.id

    package_no_set = set()
    for p in db.query(models.TaskPackage).all():
        package_no_set.add(p.package_no)

    batch_template_names = set()
    batch_package_nos = set()

    for template_data in templates_data:
        row_index += 1
        is_valid, field_errors = validate_template_fields(template_data, row_index)

        if not is_valid:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="template",
                identifier=template_data.get("name", "unknown"),
                message="字段校验失败",
                errors=field_errors
            ))
            continue

        name = template_data["name"]
        if name in template_name_map or name in batch_template_names:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="template",
                identifier=name,
                message="模板名称重复",
                errors=[f"模板名称 '{name}' 已存在或在本次导入中重复"]
            ))
            continue

        try:
            db_template = models.InspectionTemplate(
                name=name,
                description=template_data.get("description"),
                import_batch_id=batch.id
            )
            db.add(db_template)
            db.flush()

            for item in template_data["check_items"]:
                db_item = models.CheckItem(
                    template_id=db_template.id,
                    device_code=item.get("device_code", ""),
                    item_name=item.get("item_name", ""),
                    unit=item.get("unit"),
                    standard_value=item.get("standard_value"),
                    tolerance=item.get("tolerance")
                )
                db.add(db_item)

            template_name_map[name] = db_template.id
            batch_template_names.add(name)
            success_count += 1

            log_audit(
                db,
                action="import_template",
                entity_type="template",
                entity_id=db_template.id,
                details={"name": name, "check_items_count": len(template_data["check_items"])},
                operator=operator,
                batch_no=batch_no
            )

            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=True,
                record_type="template",
                identifier=name,
                message=f"导入成功，模板ID: {db_template.id}",
                errors=[]
            ))

        except Exception as e:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="template",
                identifier=name,
                message="数据库错误",
                errors=[str(e)]
            ))

    for pkg_data in packages_data:
        row_index += 1
        is_valid, field_errors = validate_task_package_fields(pkg_data, row_index)

        if not is_valid:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="task_package",
                identifier=pkg_data.get("package_no", "unknown"),
                message="字段校验失败",
                errors=field_errors
            ))
            continue

        package_no = pkg_data["package_no"]
        template_id = pkg_data["template_id"]

        if package_no in package_no_set or package_no in batch_package_nos:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="task_package",
                identifier=package_no,
                message="任务包编号重复",
                errors=[f"任务包编号 '{package_no}' 已存在或在本次导入中重复"]
            ))
            continue

        if template_id not in template_name_map.values():
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="task_package",
                identifier=package_no,
                message="模板不存在",
                errors=[f"模板ID {template_id} 不存在，请先导入模板"]
            ))
            continue

        try:
            db_package = models.TaskPackage(
                package_no=package_no,
                template_id=template_id,
                import_batch_id=batch.id,
                status="draft",
                operator=pkg_data.get("operator") or operator
            )
            db.add(db_package)
            db.flush()

            package_no_set.add(package_no)
            batch_package_nos.add(package_no)
            success_count += 1

            log_audit(
                db,
                action="import_task_package",
                entity_type="task_package",
                entity_id=db_package.id,
                details={"package_no": package_no, "template_id": template_id},
                operator=pkg_data.get("operator") or operator,
                batch_no=batch_no
            )

            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=True,
                record_type="task_package",
                identifier=package_no,
                message=f"导入成功，任务包ID: {db_package.id}",
                errors=[]
            ))

        except Exception as e:
            failed_count += 1
            results.append(schemas.ImportRecordResult(
                row_index=row_index,
                success=False,
                record_type="task_package",
                identifier=package_no,
                message="数据库错误",
                errors=[str(e)]
            ))

    batch.success_count = success_count
    batch.failed_count = failed_count
    batch.status = "completed"
    batch.details = json.dumps({
        "templates_imported": len([r for r in results if r.record_type == "template" and r.success]),
        "packages_imported": len([r for r in results if r.record_type == "task_package" and r.success])
    }, ensure_ascii=False)
    db.flush()

    log_audit(
        db,
        action="batch_import",
        entity_type="batch",
        entity_id=batch.id,
        details={
            "batch_no": batch_no,
            "total_records": total_records,
            "success_count": success_count,
            "failed_count": failed_count,
            "source_type": source_type
        },
        operator=operator,
        batch_no=batch_no
    )

    db.commit()

    return schemas.BatchImportResponse(
        success=failed_count == 0,
        message=f"批量导入完成: 成功 {success_count} 条，失败 {failed_count} 条" if total_records > 0 else "没有可导入的数据",
        batch_no=batch_no,
        total_records=total_records,
        success_count=success_count,
        failed_count=failed_count,
        results=results
    )


def validate_before_publish(
    db: Session,
    package_no: str
) -> schemas.PublishValidationResult:
    errors = []
    warnings = []

    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()

    if not package:
        return schemas.PublishValidationResult(
            valid=False,
            package_no=package_no,
            errors=[f"任务包编号 '{package_no}' 不存在"],
            warnings=[]
        )

    if package.status != "draft":
        errors.append(f"任务包状态为 '{package.status}'，只有 draft 状态才能发布")

    template = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.id == package.template_id
    ).first()

    if not template:
        errors.append(f"任务包关联的模板ID {package.template_id} 不存在")
    else:
        check_items_count = db.query(models.CheckItem).filter(
            models.CheckItem.template_id == template.id
        ).count()
        if check_items_count == 0:
            errors.append(f"模板 '{template.name}' 没有定义任何检查项")
        else:
            warnings.append(f"模板 '{template.name}' 包含 {check_items_count} 个检查项")

    existing = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no,
        models.TaskPackage.id != package.id
    ).first()
    if existing:
        errors.append(f"任务包编号 '{package_no}' 已被其他任务包占用")

    if package.status == "draft" and not errors:
        warnings.append("任务包发布后将从 draft 变为 issued 状态，可上传读数")

    return schemas.PublishValidationResult(
        valid=len(errors) == 0,
        package_no=package_no,
        errors=errors,
        warnings=warnings
    )


def validate_before_revoke(
    db: Session,
    package_no: str
) -> schemas.RevokeValidationResult:
    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()

    if not package:
        return schemas.RevokeValidationResult(
            allowed=False,
            package_no=package_no,
            current_status="unknown",
            readings_count=0,
            message=f"任务包编号 '{package_no}' 不存在"
        )

    readings_count = db.query(models.Reading).filter(
        models.Reading.task_package_id == package.id
    ).count()

    if package.status == "closed":
        return schemas.RevokeValidationResult(
            allowed=False,
            package_no=package_no,
            current_status=package.status,
            readings_count=readings_count,
            message="已关闭的任务包不能撤回"
        )

    if package.status == "synced":
        return schemas.RevokeValidationResult(
            allowed=False,
            package_no=package_no,
            current_status=package.status,
            readings_count=readings_count,
            message="已同步的任务包不能撤回，读数已同步完成"
        )

    if package.status == "draft":
        return schemas.RevokeValidationResult(
            allowed=False,
            package_no=package_no,
            current_status=package.status,
            readings_count=readings_count,
            message="任务包已经是草稿状态，无需撤回"
        )

    if package.status == "issued":
        if readings_count > 0:
            return schemas.RevokeValidationResult(
                allowed=False,
                package_no=package_no,
                current_status=package.status,
                readings_count=readings_count,
                message=f"已发放的任务包已有 {readings_count} 条读数记录，不能撤回"
            )
        else:
            return schemas.RevokeValidationResult(
                allowed=True,
                package_no=package_no,
                current_status=package.status,
                readings_count=readings_count,
                message="可以撤回，任务包尚未同步任何读数"
            )

    return schemas.RevokeValidationResult(
        allowed=False,
        package_no=package_no,
        current_status=package.status,
        readings_count=readings_count,
        message=f"未知状态 '{package.status}'"
    )


def get_reading_summary(db: Session, task_package_id: int) -> schemas.ReadingSummary:
    readings_count = db.query(models.Reading).filter(
        models.Reading.task_package_id == task_package_id
    ).count()

    conflicts = db.query(models.Conflict).filter(
        models.Conflict.task_package_id == task_package_id
    ).all()

    total_conflicts = len(conflicts)
    open_conflicts = len([c for c in conflicts if c.status == "open"])
    resolved_conflicts = len([c for c in conflicts if c.status == "resolved"])

    return schemas.ReadingSummary(
        total_readings=readings_count,
        total_conflicts=total_conflicts,
        open_conflicts=open_conflicts,
        resolved_conflicts=resolved_conflicts
    )


def get_batch_export(
    db: Session,
    batch_no: str = None,
    entity_type: str = None,
    operator: str = None
) -> schemas.BatchExportResponse:
    items: List[schemas.BatchExportItem] = []

    if entity_type is None or entity_type == "task_package":
        query = db.query(models.TaskPackage)
        if batch_no:
            query = query.join(models.ImportBatch).filter(
                models.ImportBatch.batch_no == batch_no
            )
        if operator:
            query = query.filter(models.TaskPackage.operator == operator)

        packages = query.all()
        for pkg in packages:
            batch_info = None
            batch_no_val = None
            if pkg.import_batch:
                batch_info = schemas.ImportBatchBase.model_validate(pkg.import_batch)
                batch_no_val = pkg.import_batch.batch_no

            summary = get_reading_summary(db, pkg.id)

            data = {
                "id": pkg.id,
                "package_no": pkg.package_no,
                "template_id": pkg.template_id,
                "template_name": pkg.template.name if pkg.template else None,
                "status": pkg.status,
                "operator": pkg.operator,
                "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
                "issued_at": pkg.issued_at.isoformat() if pkg.issued_at else None,
                "synced_at": pkg.synced_at.isoformat() if pkg.synced_at else None,
                "closed_at": pkg.closed_at.isoformat() if pkg.closed_at else None
            }

            items.append(schemas.BatchExportItem(
                batch_no=batch_no_val,
                import_batch=batch_info,
                current_status=pkg.status,
                reading_summary=summary,
                data=data
            ))

    if entity_type is None or entity_type == "template":
        query = db.query(models.InspectionTemplate)
        if batch_no:
            query = query.join(models.ImportBatch).filter(
                models.ImportBatch.batch_no == batch_no
            )

        templates = query.all()
        for tpl in templates:
            batch_info = None
            batch_no_val = None
            if tpl.import_batch:
                batch_info = schemas.ImportBatchBase.model_validate(tpl.import_batch)
                batch_no_val = tpl.import_batch.batch_no

            data = {
                "id": tpl.id,
                "name": tpl.name,
                "description": tpl.description,
                "check_items_count": len(tpl.check_items),
                "check_items": [
                    {
                        "device_code": ci.device_code,
                        "item_name": ci.item_name,
                        "unit": ci.unit,
                        "standard_value": ci.standard_value,
                        "tolerance": ci.tolerance
                    }
                    for ci in tpl.check_items
                ],
                "task_packages_count": len(tpl.task_packages),
                "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
                "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None
            }

            items.append(schemas.BatchExportItem(
                batch_no=batch_no_val,
                import_batch=batch_info,
                current_status="active",
                reading_summary=None,
                data=data
            ))

    return schemas.BatchExportResponse(
        success=True,
        message=f"导出成功，共 {len(items)} 条记录",
        export_count=len(items),
        items=items
    )
