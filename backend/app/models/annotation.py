from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime, Boolean
from datetime import datetime
from ..db.session import Base


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    x_pct: Mapped[float] = mapped_column(Float, nullable=False)
    y_pct: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(String(2048), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
