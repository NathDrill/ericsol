from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from ..db.session import Base


class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)

