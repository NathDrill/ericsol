from sqlalchemy.orm import Session
from ..models.vendor import Vendor, VendorAlias
from rapidfuzz import fuzz


def list_vendors(db: Session):
    return db.query(Vendor).all()


def upsert_vendor(db: Session, name: str, aliases: list[str]):
    v = db.query(Vendor).filter_by(name=name).first()
    if not v:
        v = Vendor(name=name)
        db.add(v)
        db.flush()
    # reset aliases simplistic
    db.query(VendorAlias).filter_by(vendor_id=v.id).delete()
    for a in aliases:
        db.add(VendorAlias(vendor_id=v.id, alias=a))
    db.commit()
    db.refresh(v)
    return v


def add_alias(db: Session, vendor_id: int, alias: str):
    db.add(VendorAlias(vendor_id=vendor_id, alias=alias))
    db.commit()


def match_vendor(db: Session, query: str) -> dict:
    all_names = []
    for v in db.query(Vendor).all():
        all_names.append((v.id, v.name))
        for a in v.aliases:
            all_names.append((v.id, a.alias))
    best = None
    best_score = -1
    for vid, name in all_names:
        score = fuzz.partial_ratio(query.lower(), name.lower())
        if score > best_score:
            best_score = score
            best = {"vendor_id": vid, "name": name, "score": score}
    return best or {"vendor_id": None, "name": None, "score": 0}

