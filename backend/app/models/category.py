from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, DateTime
from datetime import datetime
from ..db.session import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

