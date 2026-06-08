from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from .. import models, schemas, services

router = APIRouter(
    prefix="/api/readings",
    tags=["读数管理"],
    responses={404: {"description": "未找到"}}
)


@router.post("/upload", response_model=schemas.UploadResponse)
def upload_readings(
    upload_data: schemas.ReadingUpload,
    db: Session = Depends(get_db)
):
    package_no = upload_data.package_no

    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务包编号 '{package_no}' 不存在，无法上传读数"
        )

    if package.status not in ["issued", "synced"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包状态为 '{package.status}'，不允许上传读数。允许的状态: issued, synced"
        )

    if package.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包 '{package_no}' 已关闭，无法上传读数"
        )

    processed = 0
    conflicts_found = 0
    conflicts_list = []

    for reading_data in upload_data.readings:
        existing_reading = db.query(models.Reading).filter(
            models.Reading.task_package_id == package.id,
            models.Reading.device_code == reading_data.device_code,
            models.Reading.item_name == reading_data.item_name
        ).first()

        if existing_reading:
            if existing_reading.reading_value == reading_data.reading_value:
                processed += 1
                continue

            existing_open_conflict = db.query(models.Conflict).filter(
                models.Conflict.task_package_id == package.id,
                models.Conflict.device_code == reading_data.device_code,
                models.Conflict.item_name == reading_data.item_name,
                models.Conflict.status == "open"
            ).first()

            if existing_open_conflict:
                existing_open_conflict.new_value = reading_data.reading_value
                conflicts_list.append(existing_open_conflict)
                conflicts_found += 1
            else:
                conflict = models.Conflict(
                    task_package_id=package.id,
                    device_code=reading_data.device_code,
                    item_name=reading_data.item_name,
                    existing_value=existing_reading.reading_value,
                    new_value=reading_data.reading_value,
                    status="open"
                )
                db.add(conflict)
                db.flush()
                conflicts_list.append(conflict)
                conflicts_found += 1

            services.log_audit(
                db,
                action="reading_conflict_detected",
                entity_type="reading",
                entity_id=existing_reading.id,
                details={
                    "package_no": package_no,
                    "device_code": reading_data.device_code,
                    "item_name": reading_data.item_name,
                    "existing_value": existing_reading.reading_value,
                    "new_value": reading_data.reading_value
                }
            )
        else:
            new_reading = models.Reading(
                task_package_id=package.id,
                device_code=reading_data.device_code,
                item_name=reading_data.item_name,
                reading_value=reading_data.reading_value,
                collected_at=reading_data.collected_at,
                source_type=reading_data.source_type or "offline"
            )
            db.add(new_reading)
            processed += 1

            services.log_audit(
                db,
                action="reading_uploaded",
                entity_type="reading",
                entity_id=package.id,
                details={
                    "package_no": package_no,
                    "device_code": reading_data.device_code,
                    "item_name": reading_data.item_name,
                    "reading_value": reading_data.reading_value
                }
            )

    db.commit()

    conflict_schemas = [schemas.Conflict.model_validate(c) for c in conflicts_list]

    message = f"成功处理 {processed} 条读数"
    if conflicts_found > 0:
        message += f"，检测到 {conflicts_found} 个冲突需要解决"

    return schemas.UploadResponse(
        success=True,
        message=message,
        package_no=package_no,
        readings_processed=processed,
        conflicts_found=conflicts_found,
        conflicts=conflict_schemas
    )


@router.get("", response_model=List[schemas.Reading])
def list_readings(
    package_no: str = None,
    device_code: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.Reading)
    if package_no:
        package = db.query(models.TaskPackage).filter(
            models.TaskPackage.package_no == package_no
        ).first()
        if package:
            query = query.filter(models.Reading.task_package_id == package.id)
    if device_code:
        query = query.filter(models.Reading.device_code == device_code)

    readings = query.order_by(models.Reading.uploaded_at.desc()).offset(skip).limit(limit).all()
    return readings
