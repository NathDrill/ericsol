from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.schemas.vendors import VendorIn
from app.services.vendor_service import list_vendors, upsert_vendor, add_alias, match_vendor
from .auth import get_current_user
from app.models.vendor import Vendor
from app.models.contract import Contract


router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("")
def get_all(db: Session = Depends(get_db), user=Depends(get_current_user)):
    vs = list_vendors(db)
    return [{"id": v.id, "name": v.name, "aliases": [a.alias for a in v.aliases]} for v in vs]


@router.post("")
def upsert(body: VendorIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    v = upsert_vendor(db, body.name, body.aliases)
    return {"id": v.id, "name": v.name, "aliases": [a.alias for a in v.aliases]}


@router.post("/{vendor_id}/aliases")
def add_alias_route(vendor_id: int, alias: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    add_alias(db, vendor_id, alias)
    return {"ok": True}


@router.get("/match")
def match(q: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return match_vendor(db, q)


@router.get("/top")
def top_vendors(limit: int = 5, metric: str = "mrr", db: Session = Depends(get_db), user=Depends(get_current_user)):
    metric_col = Contract.amount_mrr if metric.lower() == "mrr" else Contract.amount_arr
    q = (
        db.query(Contract.vendor_id, func.sum(metric_col).label("sum"), func.count(Contract.id).label("count"))
        .filter(Contract.vendor_id.isnot(None))
        .group_by(Contract.vendor_id)
        .order_by(func.sum(metric_col).desc())
        .limit(limit)
    )
    rows = q.all()
    # Map vendor_id to names
    names = {v.id: v.name for v in db.query(Vendor).filter(Vendor.id.in_([r[0] for r in rows])).all()}
    return [
        {"vendor_id": vid, "name": names.get(vid, f"Vendor #{vid}"), metric.lower(): float(total or 0), "count": int(cnt)}
        for vid, total, cnt in rows
    ]
