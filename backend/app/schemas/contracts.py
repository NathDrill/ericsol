from pydantic import BaseModel
from datetime import date


class ContractIn(BaseModel):
    vendor_id: int | None = None
    title: str
    recurrence: str = "monthly"
    amount: float = 0.0
    category_id: int | None = None
    category_name: str | None = None
    cancel_deadline: date | None = None
    notice_period_days: int | None = None
    effective_date: date | None = None
    renewal_months: int | None = None
    has_auto_renewal: bool = True
    has_commitment: bool = False
    source_storage: str | None = None
    tags: list[str] = []
    source_text: str | None = None
    price_evolution_report: str | None = None
    source_filename: str | None = None
    sharepoint_item_id: str | None = None
    sharepoint_drive_id: str | None = None
    sharepoint_web_url: str | None = None
    checklist: dict | None = None


class ContractOut(BaseModel):
    id: int
    vendor_id: int | None
    title: str
    category: str | None = None
    legal_entity: str | None = None
    amount_mrr: float
    amount_arr: float
    recurrence: str
    cancel_deadline: date | None
    notice_period_days: int | None
    effective_date: date | None
    contract_end_date: date | None = None
    renewal_months: int | None
    resiliation_effective_date: date | None = None
    has_auto_renewal: bool
    has_commitment: bool
    source_storage: str | None = None
    source_filename: str | None = None
    sharepoint_item_id: str | None = None
    sharepoint_drive_id: str | None = None
    sharepoint_web_url: str | None = None
    annex_documents: list[dict] | None = None
    tags: list[str] | None
    status: str
    checklist: dict | None = None

    class Config:
        from_attributes = True


class ContractsResponse(BaseModel):
    total: int
    indicators: dict
    items: list[ContractOut]


class ContractUpdate(BaseModel):
    vendor_id: int | None = None
    title: str | None = None
    category_id: int | None = None
    amount_mrr: float | None = None
    amount_arr: float | None = None
    recurrence: str | None = None
    cancel_deadline: date | None = None
    notice_period_days: int | None = None
    effective_date: date | None = None
    renewal_months: int | None = None
    resiliation_effective_date: date | None = None
    has_auto_renewal: bool | None = None
    has_commitment: bool | None = None
    source_storage: str | None = None
    source_filename: str | None = None
    sharepoint_item_id: str | None = None
    sharepoint_drive_id: str | None = None
    sharepoint_web_url: str | None = None
    tags: list[str] | None = None
