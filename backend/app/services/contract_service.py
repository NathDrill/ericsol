from sqlalchemy.orm import Session
from datetime import date
from ..models.contract import Contract
import json


def refresh_contract_statuses(db: Session):
    today = date.today()
    for c in db.query(Contract).all():
        status = "actif"
        # Preserve a manually marked terminated contract until its effective date passes.
        if c.resiliation_effective_date and c.resiliation_effective_date < today:
            status = "expire"
        elif c.status == "resilie":
            status = "resilie"
        elif c.cancel_deadline and c.cancel_deadline < today:
            status = "deadline_depassee"
        elif c.cancel_deadline and (c.cancel_deadline - today).days <= 15:
            status = "a_resilier"
        c.status = status
    db.commit()


def indicators(db: Session) -> dict:
    items = db.query(Contract).all()
    today = date.today()
    mrr = sum(c.amount_mrr for c in items)
    # Exclude contracts with a resiliation effective date within the current year from ARR
    arr = 0.0
    for c in items:
        if c.resiliation_effective_date and c.resiliation_effective_date.year == today.year:
            continue
        arr += (c.amount_arr or 0.0)
    # Status counts
    counts = { "actif": 0, "a_resilier": 0, "deadline_depassee": 0, "resilie": 0, "expire": 0 }
    for c in items:
        if c.status in counts:
            counts[c.status] += 1
    return {"mrr": mrr, "arr": arr, "count": len(items), "status_counts": counts}


def create_contract(db: Session, *, title: str, amount: float, recurrence: str = "monthly", **kwargs) -> Contract:
    # amount is entered according to selected recurrence period
    months_map = { 'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12, 'biannual': 24 }
    months = months_map.get((recurrence or 'monthly').lower(), 1)
    mrr = round((amount / months) + 1e-9, 2)
    arr = round((mrr * 12.0) + 1e-9, 2)
    checklist = kwargs.pop('checklist', None)
    if checklist is not None:
        kwargs['checklist_json'] = json.dumps(checklist, ensure_ascii=False)
    obj = Contract(title=title, amount_mrr=mrr, amount_arr=arr, recurrence=recurrence, **kwargs)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    refresh_contract_statuses(db)
    return obj
