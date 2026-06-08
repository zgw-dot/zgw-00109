from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from ..database import get_db
from .. import models, schemas, services

router = APIRouter(
    prefix="/api/templates",
    tags=["巡检模板"],
    responses={404: {"description": "未找到"}}
)


@router.post("", response_model=schemas.Template, status_code=status.HTTP_201_CREATED)
def create_template(template: schemas.TemplateCreate, db: Session = Depends(get_db)):
    db_template = models.InspectionTemplate(
        name=template.name,
        description=template.description
    )
    db.add(db_template)
    db.flush()

    for item in template.check_items:
        db_item = models.CheckItem(
            template_id=db_template.id,
            device_code=item.device_code,
            item_name=item.item_name,
            unit=item.unit,
            standard_value=item.standard_value,
            tolerance=item.tolerance
        )
        db.add(db_item)

    db.commit()
    db.refresh(db_template)

    services.log_audit(
        db,
        action="create_template",
        entity_type="template",
        entity_id=db_template.id,
        details={"name": template.name, "check_items_count": len(template.check_items)},
        operator=template.model_dump().get("operator")
    )
    db.commit()

    return db_template


@router.get("", response_model=List[schemas.Template])
def list_templates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    templates = db.query(models.InspectionTemplate).offset(skip).limit(limit).all()
    return templates


@router.get("/{template_id}", response_model=schemas.Template)
def get_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在"
        )
    return template


@router.put("/{template_id}", response_model=schemas.Template)
def update_template(
    template_id: int,
    template_update: schemas.TemplateUpdate,
    db: Session = Depends(get_db)
):
    db_template = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.id == template_id
    ).first()
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在"
        )

    update_data = template_update.model_dump(exclude_unset=True)

    if "name" in update_data:
        db_template.name = update_data["name"]
    if "description" in update_data:
        db_template.description = update_data["description"]
    db_template.updated_at = datetime.now()

    if "check_items" in update_data and update_data["check_items"] is not None:
        db.query(models.CheckItem).filter(
            models.CheckItem.template_id == template_id
        ).delete()

        for item in update_data["check_items"]:
            db_item = models.CheckItem(
                template_id=db_template.id,
                device_code=item["device_code"],
                item_name=item["item_name"],
                unit=item.get("unit"),
                standard_value=item.get("standard_value"),
                tolerance=item.get("tolerance")
            )
            db.add(db_item)

    db.commit()
    db.refresh(db_template)

    services.log_audit(
        db,
        action="update_template",
        entity_type="template",
        entity_id=template_id,
        details={"updated_fields": list(update_data.keys())},
        operator=update_data.get("operator")
    )
    db.commit()

    return db_template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    db_template = db.query(models.InspectionTemplate).filter(
        models.InspectionTemplate.id == template_id
    ).first()
    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在"
        )

    task_packages_count = db.query(models.TaskPackage).filter(
        models.TaskPackage.template_id == template_id
    ).count()
    if task_packages_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该模板已关联 {task_packages_count} 个任务包，无法删除"
        )

    db.delete(db_template)
    db.commit()

    services.log_audit(
        db,
        action="delete_template",
        entity_type="template",
        entity_id=template_id,
        details={"name": db_template.name}
    )
    db.commit()

    return None
