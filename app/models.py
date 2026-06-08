from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class InspectionTemplate(Base):
    __tablename__ = "inspection_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    check_items = relationship("CheckItem", back_populates="template", cascade="all, delete-orphan")
    task_packages = relationship("TaskPackage", back_populates="template")


class CheckItem(Base):
    __tablename__ = "check_items"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False)
    device_code = Column(String(100), nullable=False)
    item_name = Column(String(255), nullable=False)
    unit = Column(String(50), nullable=True)
    standard_value = Column(String(255), nullable=True)
    tolerance = Column(String(100), nullable=True)

    template = relationship("InspectionTemplate", back_populates="check_items")


class TaskPackage(Base):
    __tablename__ = "task_packages"

    id = Column(Integer, primary_key=True, index=True)
    package_no = Column(String(100), unique=True, nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    created_at = Column(DateTime, default=datetime.now)
    issued_at = Column(DateTime, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    operator = Column(String(100), nullable=True)

    template = relationship("InspectionTemplate", back_populates="task_packages")
    readings = relationship("Reading", back_populates="task_package", cascade="all, delete-orphan")
    conflicts = relationship("Conflict", back_populates="task_package", cascade="all, delete-orphan")


class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    task_package_id = Column(Integer, ForeignKey("task_packages.id"), nullable=False)
    device_code = Column(String(100), nullable=False)
    item_name = Column(String(255), nullable=False)
    reading_value = Column(String(255), nullable=False)
    collected_at = Column(DateTime, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.now)
    source_type = Column(String(50), default="offline")

    task_package = relationship("TaskPackage", back_populates="readings")


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True, index=True)
    task_package_id = Column(Integer, ForeignKey("task_packages.id"), nullable=False)
    device_code = Column(String(100), nullable=False)
    item_name = Column(String(255), nullable=False)
    existing_value = Column(String(255), nullable=False)
    new_value = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="open")
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)

    task_package = relationship("TaskPackage", back_populates="conflicts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    operator = Column(String(100), nullable=True)
