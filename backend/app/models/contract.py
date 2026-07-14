from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Date, Float, Boolean, Text, ForeignKey
from ..db.session import Base


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("vendors.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, default="")
    amount_mrr: Mapped[float] = mapped_column(Float, default=0.0)
    amount_arr: Mapped[float] = mapped_column(Float, default=0.0)
    recurrence: Mapped[str] = mapped_column(String, default="monthly")
    cancel_deadline: Mapped[Date | None] = mapped_column(Date, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    renewal_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resiliation_effective_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    has_auto_renewal: Mapped[bool] = mapped_column(Boolean, default=True)
    has_commitment: Mapped[bool] = mapped_column(Boolean, default=False)
    source_storage: Mapped[str | None] = mapped_column(String, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    sharepoint_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sharepoint_drive_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sharepoint_web_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    annex_documents_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="actif")
    price_evolution_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_json: Mapped[str | None] = mapped_column(Text, nullable=True)
