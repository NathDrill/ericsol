from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, DateTime
from datetime import datetime
from ..db.session import Base


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recipients: Mapped[str] = mapped_column(String)

