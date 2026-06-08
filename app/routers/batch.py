from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ..database import get_db
from .. import models, schemas, services

router = APIRouter(
    prefix="/api/batch",
    tags=["批量管理"],
    responses={404: {"description": "未找到"}}
)


@router.post("/import/json", response_model=schemas.BatchImportResponse)
def batch_import_json(
    import_data: schemas.BatchImportJson,
    db: Session = Depends(get_db)
):
    templates_data = [t.model_dump() for t in import_data.templates]
    packages_data = [p.model_dump() for p in import_data.task_packages]

    result = services.process_batch_import(
        db=db,
        templates_data=templates_data,
        packages_data=packages_data,
        source_type="json",
        operator=import_data.operator
    )

    return result


@router.post("/import/csv", response_model=schemas.BatchImportResponse)
async def batch_import_csv(
    file: UploadFile = File(...),
    operator: Optional[str] = Query(None, description="操作人员"),
    db: Session = Depends(get_db)
):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持 CSV 格式文件"
        )

    try:
        content = await file.read()
        content_str = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件编码错误，请使用 UTF-8 编码"
        )

    templates_data, packages_data, parse_errors = services.parse_csv_data(content_str)

    if parse_errors:
        batch_no = services.generate_batch_no()
        return schemas.BatchImportResponse(
            success=False,
            message="CSV 解析失败",
            batch_no=batch_no,
            total_records=0,
            success_count=0,
            failed_count=len(parse_errors),
            results=[
                schemas.ImportRecordResult(
                    row_index=i+1,
                    success=False,
                    record_type="parse_error",
                    identifier="csv_parse",
                    message="解析错误",
                    errors=[err]
                )
                for i, err in enumerate(parse_errors)
            ]
        )

    result = services.process_batch_import(
        db=db,
        templates_data=templates_data,
        packages_data=packages_data,
        source_type="csv",
        source_filename=file.filename,
        operator=operator
    )

    return result


@router.get("/export", response_model=schemas.BatchExportResponse)
def batch_export(
    batch_no: Optional[str] = Query(None, description="按导入批次过滤"),
    entity_type: Optional[str] = Query(None, description="按实体类型过滤: template/task_package"),
    operator: Optional[str] = Query(None, description="按操作人员过滤"),
    db: Session = Depends(get_db)
):
    if entity_type and entity_type not in ["template", "task_package"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_type 只能是 'template' 或 'task_package'"
        )

    result = services.get_batch_export(db, batch_no, entity_type, operator)

    services.log_audit(
        db,
        action="batch_export",
        entity_type="batch",
        entity_id=0,
        details={
            "batch_no": batch_no,
            "entity_type": entity_type,
            "operator_filter": operator,
            "export_count": result.export_count
        },
        operator=operator,
        batch_no=batch_no
    )
    db.commit()

    return result


@router.get("/validate-publish/{package_no}", response_model=schemas.PublishValidationResult)
def validate_publish(
    package_no: str,
    db: Session = Depends(get_db)
):
    result = services.validate_before_publish(db, package_no)
    return result


@router.post("/publish/{package_no}", response_model=schemas.StatusChangeResponse)
def publish_task_package(
    package_no: str,
    operator: Optional[str] = Query(None, description="操作人员"),
    db: Session = Depends(get_db)
):
    validation = services.validate_before_publish(db, package_no)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="发布前校验失败: " + "; ".join(validation.errors)
        )

    package, error = services.validate_package_status(db, package_no, ["draft"])
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error["detail"]
        )

    old_status = package.status
    package.status = "issued"
    package.issued_at = datetime.now()
    if operator:
        package.operator = operator

    db.commit()
    db.refresh(package)

    services.log_audit(
        db,
        action="publish_task_package",
        entity_type="task_package",
        entity_id=package.id,
        details={
            "package_no": package_no,
            "old_status": old_status,
            "new_status": "issued",
            "validation_passed": True
        },
        operator=operator or package.operator
    )
    db.commit()

    return schemas.StatusChangeResponse(
        success=True,
        message=f"任务包 '{package_no}' 已发布",
        package_no=package_no,
        old_status=old_status,
        new_status="issued"
    )


@router.get("/validate-revoke/{package_no}", response_model=schemas.RevokeValidationResult)
def validate_revoke(
    package_no: str,
    db: Session = Depends(get_db)
):
    result = services.validate_before_revoke(db, package_no)
    return result


@router.post("/revoke/{package_no}", response_model=schemas.StatusChangeResponse)
def revoke_task_package(
    package_no: str,
    operator: Optional[str] = Query(None, description="操作人员"),
    db: Session = Depends(get_db)
):
    validation = services.validate_before_revoke(db, package_no)
    if not validation.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.message
        )

    package, error = services.validate_package_status(db, package_no, ["issued"])
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error["detail"]
        )

    old_status = package.status
    package.status = "draft"
    package.issued_at = None

    db.commit()
    db.refresh(package)

    services.log_audit(
        db,
        action="revoke_task_package",
        entity_type="task_package",
        entity_id=package.id,
        details={
            "package_no": package_no,
            "old_status": old_status,
            "new_status": "draft",
            "readings_count": validation.readings_count
        },
        operator=operator or package.operator
    )
    db.commit()

    return schemas.StatusChangeResponse(
        success=True,
        message=f"任务包 '{package_no}' 已撤回为草稿状态",
        package_no=package_no,
        old_status=old_status,
        new_status="draft"
    )


@router.get("/batches", response_model=list[schemas.ImportBatchBase])
def list_batches(
    skip: int = 0,
    limit: int = 100,
    operator: Optional[str] = Query(None, description="按操作人员过滤"),
    db: Session = Depends(get_db)
):
    query = db.query(models.ImportBatch)
    if operator:
        query = query.filter(models.ImportBatch.operator == operator)
    batches = query.order_by(models.ImportBatch.created_at.desc()).offset(skip).limit(limit).all()
    return batches


@router.get("/batches/{batch_no}", response_model=schemas.ImportBatchBase)
def get_batch(
    batch_no: str,
    db: Session = Depends(get_db)
):
    batch = db.query(models.ImportBatch).filter(
        models.ImportBatch.batch_no == batch_no
    ).first()
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次编号 '{batch_no}' 不存在"
        )
    return batch
