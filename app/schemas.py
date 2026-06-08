from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class CheckItemBase(BaseModel):
    device_code: str = Field(..., max_length=100, description="设备编号")
    item_name: str = Field(..., max_length=255, description="检查项名称")
    unit: Optional[str] = Field(None, max_length=50, description="单位")
    standard_value: Optional[str] = Field(None, max_length=255, description="标准值")
    tolerance: Optional[str] = Field(None, max_length=100, description="公差")


class CheckItemCreate(CheckItemBase):
    pass


class CheckItem(CheckItemBase):
    id: int
    template_id: int

    class Config:
        from_attributes = True


class TemplateBase(BaseModel):
    name: str = Field(..., max_length=255, description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")


class TemplateCreate(TemplateBase):
    check_items: List[CheckItemCreate] = Field(..., description="检查项列表")


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")
    check_items: Optional[List[CheckItemCreate]] = Field(None, description="检查项列表")


class Template(TemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime
    check_items: List[CheckItem] = []

    class Config:
        from_attributes = True


class TaskPackageBase(BaseModel):
    package_no: str = Field(..., max_length=100, description="任务包编号")
    template_id: int = Field(..., description="模板ID")
    operator: Optional[str] = Field(None, max_length=100, description="操作人员")


class TaskPackageCreate(TaskPackageBase):
    pass


class TaskPackage(BaseModel):
    id: int
    package_no: str
    template_id: int
    status: str
    created_at: datetime
    issued_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    operator: Optional[str] = None
    template: Optional[Template] = None

    class Config:
        from_attributes = True


class ReadingBase(BaseModel):
    device_code: str = Field(..., max_length=100, description="设备编号")
    item_name: str = Field(..., max_length=255, description="检查项名称")
    reading_value: str = Field(..., max_length=255, description="读数")
    collected_at: datetime = Field(..., description="采集时间")
    source_type: Optional[str] = Field("offline", max_length=50, description="采集类型")


class ReadingUpload(BaseModel):
    package_no: str = Field(..., max_length=100, description="任务包编号")
    readings: List[ReadingBase] = Field(..., description="读数列表")


class Reading(ReadingBase):
    id: int
    task_package_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ConflictBase(BaseModel):
    pass


class ConflictResolve(BaseModel):
    resolution_note: str = Field(..., description="解决说明")
    keep_value: str = Field(..., description="保留的值: 'existing' 或 'new'")
    resolved_by: Optional[str] = Field(None, max_length=100, description="解决人")


class Conflict(BaseModel):
    id: int
    task_package_id: int
    device_code: str
    item_name: str
    existing_value: str
    new_value: str
    status: str
    resolution_note: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLog(BaseModel):
    id: int
    action: str
    entity_type: str
    entity_id: int
    details: Optional[str] = None
    created_at: datetime
    operator: Optional[str] = None

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    detail: str
    code: int
    timestamp: datetime = Field(default_factory=datetime.now)


class UploadResponse(BaseModel):
    success: bool
    message: str
    package_no: str
    readings_processed: int
    conflicts_found: int
    conflicts: List[Conflict] = []


class StatusChangeResponse(BaseModel):
    success: bool
    message: str
    package_no: str
    old_status: str
    new_status: str
