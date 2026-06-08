from sqlalchemy.orm import Session
from datetime import datetime
import json
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
    operator: str = None
):
    audit_log = models.AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
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
