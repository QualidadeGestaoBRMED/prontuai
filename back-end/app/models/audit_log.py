from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class AuditLog(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_email": "gabriel.rodrigues@grupobrmed.com.br",
                "user_role": "ADMIN",
                "action": "documents.list",
                "resource": "documents",
                "method": "GET",
                "path": "/v1/documents",
                "status_code": 200,
                "ip": "127.0.0.1"
            }
        }


class AuditLogCreate(BaseModel):
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
