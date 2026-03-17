from sqlalchemy import Column, Integer, String, DateTime, Text
from database import Base
from datetime import datetime


class InfinitCall(Base):
    __tablename__ = "infinit_calls"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50))
    status = Column(String(50), default="Pending")
    qualified = Column(String(10))
    meeting = Column(String(255))
    summary = Column(Text)
    attempt = Column(String(10))
    duration = Column(String(20))
    name = Column(String(255))
    company = Column(String(255))
    call_url = Column(Text)
    country = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
