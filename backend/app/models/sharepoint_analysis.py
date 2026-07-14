from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.session import Base


class SharePointAnalysis(Base):
    __tablename__ = "sharepoint_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sharepoint_item_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    sharepoint_drive_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sharepoint_web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String, default="received")
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contracts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
