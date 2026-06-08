from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from .. import models, schemas, services

router = APIRouter(
    prefix="/api/conflicts",
    tags=["冲突管理"],
    responses={404: {"description": "未找到"}}
)


@router.get("", response_model=List[schemas.Conflict])
def list_conflicts(
    status: Optional[str] = Query(None, description="按冲突状态过滤: open/resolved"),
    package_no: Optional[str] = Query(None, description="按任务包编号过滤"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.Conflict)
    if status:
        query = query.filter(models.Conflict.status == status)
    if package_no:
        package = db.query(models.TaskPackage).filter(
            models.TaskPackage.package_no == package_no
        ).first()
        if package:
            query = query.filter(models.Conflict.task_package_id == package.id)

    conflicts = query.order_by(models.Conflict.created_at.desc()).offset(skip).limit(limit).all()
    return conflicts


@router.get("/{conflict_id}", response_model=schemas.Conflict)
def get_conflict(conflict_id: int, db: Session = Depends(get_db)):
    conflict = db.query(models.Conflict).filter(
        models.Conflict.id == conflict_id
    ).first()
    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"冲突 ID {conflict_id} 不存在"
        )
    return conflict


@router.post("/{conflict_id}/resolve", response_model=schemas.Conflict)
def resolve_conflict(
    conflict_id: int,
    resolve_data: schemas.ConflictResolve,
    db: Session = Depends(get_db)
):
    conflict = db.query(models.Conflict).filter(
        models.Conflict.id == conflict_id
    ).first()
    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"冲突 ID {conflict_id} 不存在"
        )

    if conflict.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"冲突 ID {conflict_id} 已解决，无需重复操作"
        )

    if resolve_data.keep_value not in ["existing", "new"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_value 必须是 'existing' 或 'new'"
        )

    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.id == conflict.task_package_id
    ).first()

    if package and package.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"所属任务包已关闭，无法解决冲突"
        )

    reading = db.query(models.Reading).filter(
        models.Reading.task_package_id == conflict.task_package_id,
        models.Reading.device_code == conflict.device_code,
        models.Reading.item_name == conflict.item_name
    ).first()

    if reading:
        if resolve_data.keep_value == "new":
            old_value = reading.reading_value
            reading.reading_value = conflict.new_value
            services.log_audit(
                db,
                action="reading_updated_by_conflict",
                entity_type="reading",
                entity_id=reading.id,
                details={
                    "conflict_id": conflict_id,
                    "device_code": conflict.device_code,
                    "item_name": conflict.item_name,
                    "old_value": old_value,
                    "new_value": conflict.new_value,
                    "resolution_note": resolve_data.resolution_note
                },
                operator=resolve_data.resolved_by
            )
        else:
            services.log_audit(
                db,
                action="conflict_keep_existing",
                entity_type="reading",
                entity_id=reading.id,
                details={
                    "conflict_id": conflict_id,
                    "device_code": conflict.device_code,
                    "item_name": conflict.item_name,
                    "kept_value": conflict.existing_value,
                    "discarded_value": conflict.new_value,
                    "resolution_note": resolve_data.resolution_note
                },
                operator=resolve_data.resolved_by
            )
    else:
        if resolve_data.keep_value == "new":
            new_reading = models.Reading(
                task_package_id=conflict.task_package_id,
                device_code=conflict.device_code,
                item_name=conflict.item_name,
                reading_value=conflict.new_value,
                collected_at=datetime.now(),
                source_type="conflict_resolution"
            )
            db.add(new_reading)
            db.flush()
            services.log_audit(
                db,
                action="reading_created_by_conflict",
                entity_type="reading",
                entity_id=new_reading.id,
                details={
                    "conflict_id": conflict_id,
                    "device_code": conflict.device_code,
                    "item_name": conflict.item_name,
                    "value": conflict.new_value,
                    "resolution_note": resolve_data.resolution_note
                },
                operator=resolve_data.resolved_by
            )

    conflict.status = "resolved"
    conflict.resolution_note = resolve_data.resolution_note
    conflict.resolved_at = datetime.now()
    conflict.resolved_by = resolve_data.resolved_by

    db.commit()
    db.refresh(conflict)

    services.log_audit(
        db,
        action="conflict_resolved",
        entity_type="conflict",
        entity_id=conflict_id,
        details={
            "package_no": package.package_no if package else None,
            "device_code": conflict.device_code,
            "item_name": conflict.item_name,
            "keep_value": resolve_data.keep_value,
            "resolution_note": resolve_data.resolution_note
        },
        operator=resolve_data.resolved_by
    )
    db.commit()

    return conflict
