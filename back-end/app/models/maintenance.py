from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MaintenanceWindowStatus(str, Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class MaintenancePublicStatus(str, Enum):
    NONE = "none"
    SCHEDULED = "scheduled"
    ACTIVE = "active"


class MaintenanceWindowCreate(BaseModel):
    title: str = Field(default="Manutenção programada", min_length=3, max_length=120)
    message: str = Field(..., min_length=3, max_length=500)
    starts_at: datetime
    ends_at: Optional[datetime] = None
    eta: Optional[str] = Field(default=None, max_length=120)


class MaintenanceWindowUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=120)
    message: Optional[str] = Field(default=None, min_length=3, max_length=500)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    eta: Optional[str] = Field(default=None, max_length=120)


class MaintenanceWindow(BaseModel):
    id: str
    status: MaintenanceWindowStatus
    title: str
    message: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    eta: Optional[str] = None
    created_by: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    activated_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class MaintenanceStatusResponse(BaseModel):
    status: MaintenancePublicStatus
    message: str = ""
    eta: str = ""
    title: str = ""
    id: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    version: Optional[str] = None
