from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from .. import models, schemas, services

router = APIRouter(
    prefix="/api/task-packages",
    tags=["任务包管理"],
    responses={404: {"description": "未找到"}}
)


@router.post("", response_model=schemas.TaskPackage, status_code=status.HTTP_201_CREATED)
def create_task_package(package: schemas.TaskPackageCreate, db: Session = Depends(get_db)):
    template = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.id == package.template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {package.template_id} 不存在"
        )

    existing = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package.package_no
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包编号 '{package.package_no}' 已存在"
        )

    db_package = models.TaskPackage(
        package_no=package.package_no,
        template_id=package.template_id,
        status="draft",
        operator=package.operator
    )
    db.add(db_package)
    db.commit()
    db.refresh(db_package)

    services.log_audit(
        db,
        action="create_task_package",
        entity_type="task_package",
        entity_id=db_package.id,
        details={
            "package_no": package.package_no,
            "template_id": package.template_id,
            "template_name": template.name
        },
        operator=package.operator
    )
    db.commit()

    return db_package


@router.get("", response_model=List[schemas.TaskPackage])
def list_task_packages(
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    query = db.query(models.TaskPackage)
    if status:
        query = query.filter(models.TaskPackage.status == status)
    packages = query.order_by(models.TaskPackage.created_at.desc()).offset(skip).limit(limit).all()
    return packages


@router.get("/{package_no}", response_model=schemas.TaskPackage)
def get_task_package(package_no: str, db: Session = Depends(get_db)):
    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务包编号 '{package_no}' 不存在"
        )
    return package


@router.post("/{package_no}/issue", response_model=schemas.StatusChangeResponse)
def issue_task_package(
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
        action="issue_task_package",
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
        message=f"任务包 '{package_no}' 已发放",
        package_no=package_no,
        old_status=old_status,
        new_status="issued"
    )


@router.post("/{package_no}/sync", response_model=schemas.StatusChangeResponse)
def sync_task_package(
    package_no: str,
    operator: Optional[str] = Query(None, description="操作人员"),
    db: Session = Depends(get_db)
):
    package, error = services.validate_package_status(db, package_no, ["issued"])
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error["detail"]
        )

    if services.has_open_conflicts(db, package.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包 '{package_no}' 存在未解决的冲突，无法标记为已同步"
        )

    readings_count = db.query(models.Reading).filter(
        models.Reading.task_package_id == package.id
    ).count()
    if readings_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包 '{package_no}' 没有任何读数记录，无法标记为已同步"
        )

    old_status = package.status
    package.status = "synced"
    package.synced_at = datetime.now()
    if operator:
        package.operator = operator

    db.commit()
    db.refresh(package)

    services.log_audit(
        db,
        action="sync_task_package",
        entity_type="task_package",
        entity_id=package.id,
        details={
            "package_no": package_no,
            "old_status": old_status,
            "new_status": "synced",
            "readings_count": readings_count
        },
        operator=operator or package.operator
    )
    db.commit()

    return schemas.StatusChangeResponse(
        success=True,
        message=f"任务包 '{package_no}' 已标记为已同步",
        package_no=package_no,
        old_status=old_status,
        new_status="synced"
    )


@router.post("/{package_no}/close", response_model=schemas.StatusChangeResponse)
def close_task_package(
    package_no: str,
    operator: Optional[str] = Query(None, description="操作人员"),
    db: Session = Depends(get_db)
):
    package, error = services.validate_package_status(db, package_no, ["synced"])
    if error:
        if error["code"] == 40401:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error["detail"]
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error["detail"]
        )

    if services.has_open_conflicts(db, package.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务包 '{package_no}' 存在未解决的冲突，无法关闭。请先解决所有冲突。"
        )

    old_status = package.status
    package.status = "closed"
    package.closed_at = datetime.now()
    if operator:
        package.operator = operator

    db.commit()
    db.refresh(package)

    services.log_audit(
        db,
        action="close_task_package",
        entity_type="task_package",
        entity_id=package.id,
        details={
            "package_no": package_no,
            "old_status": old_status,
            "new_status": "closed"
        },
        operator=operator or package.operator
    )
    db.commit()

    return schemas.StatusChangeResponse(
        success=True,
        message=f"任务包 '{package_no}' 已关闭",
        package_no=package_no,
        old_status=old_status,
        new_status="closed"
    )


@router.post("/{package_no}/rollback-draft", response_model=schemas.StatusChangeResponse)
def rollback_to_draft(
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
        action="rollback_task_package",
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


@router.get("/{package_no}/readings", response_model=List[schemas.Reading])
def get_package_readings(package_no: str, db: Session = Depends(get_db)):
    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务包编号 '{package_no}' 不存在"
        )

    readings = db.query(models.Reading).filter(
        models.Reading.task_package_id == package.id
    ).order_by(models.Reading.collected_at.desc()).all()
    return readings


@router.get("/{package_no}/conflicts", response_model=List[schemas.Conflict])
def get_package_conflicts(
    package_no: str,
    status: Optional[str] = Query(None, description="按冲突状态过滤: open/resolved"),
    db: Session = Depends(get_db)
):
    package = db.query(models.TaskPackage).filter(
        models.TaskPackage.package_no == package_no
    ).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务包编号 '{package_no}' 不存在"
        )

    query = db.query(models.Conflict).filter(
        models.Conflict.task_package_id == package.id
    )
    if status:
        query = query.filter(models.Conflict.status == status)

    conflicts = query.order_by(models.Conflict.created_at.desc()).all()
    return conflicts
