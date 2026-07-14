from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, ForeignKey
from ..db.session import Base


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    aliases = relationship("VendorAlias", back_populates="vendor", cascade="all, delete-orphan")


class VendorAlias(Base):
    __tablename__ = "vendor_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(Integer, ForeignKey("vendors.id"))
    alias: Mapped[str] = mapped_column(String, index=True)
    vendor = relationship("Vendor", back_populates="aliases")

