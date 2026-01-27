from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class Notification(BaseModel):
    id: Optional[str] = None
    clinic_id: Optional[str] = None
    document_id: Optional[str] = None
    type: str
    title: str
    message: str
    variant: Optional[str] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    read: bool = False
    created_at: Optional[datetime] = None

class NotificationCreate(BaseModel):
    clinic_id: Optional[str] = None
    document_id: Optional[str] = None
    type: str
    title: str
    message: str
    variant: Optional[str] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class NotificationUpdate(BaseModel):
    read: Optional[bool] = None
