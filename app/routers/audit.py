from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from .. import models, schemas

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["审计日志"],
    responses={404: {"description": "未找到"}}
)


@router.get("", response_model=List[schemas.AuditLog])
def list_audit_logs(
    action: Optional[str] = Query(None, description="按操作类型过滤"),
    entity_type: Optional[str] = Query(None, description="按实体类型过滤"),
    entity_id: Optional[int] = Query(None, description="按实体ID过滤"),
    operator: Optional[str] = Query(None, description="按操作人员过滤"),
    batch_no: Optional[str] = Query(None, description="按导入批次过滤"),
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(models.AuditLog.entity_id == entity_id)
    if operator:
        query = query.filter(models.AuditLog.operator == operator)
    if batch_no:
        query = query.filter(models.AuditLog.batch_no == batch_no)

    logs = query.order_by(models.AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs
