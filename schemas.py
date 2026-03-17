from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WebhookPayload(BaseModel):
    phone: Optional[str] = ""
    status: Optional[str] = ""
    qualified: Optional[str] = ""
    meeting: Optional[str] = ""
    summary: Optional[str] = ""
    attempt: Optional[str] = ""
    duration: Optional[str] = ""
    name: Optional[str] = ""
    company: Optional[str] = ""
    call_url: Optional[str] = ""
    country: Optional[str] = ""


class CallResponse(BaseModel):
    id: int
    phone: Optional[str] = ""
    status: Optional[str] = ""
    qualified: Optional[str] = ""
    meeting: Optional[str] = ""
    summary: Optional[str] = ""
    attempt: Optional[str] = ""
    duration: Optional[str] = ""
    name: Optional[str] = ""
    company: Optional[str] = ""
    call_url: Optional[str] = ""
    country: Optional[str] = ""
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
