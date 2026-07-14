from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.category import Category

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
def list_categories(db: Session = Depends(get_db)):
    items = db.query(Category).order_by(Category.name.asc()).all()
    return {"items": [{"id": c.id, "name": c.name} for c in items]}


@router.post("")
def add_category(name: str, db: Session = Depends(get_db)):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    cur = db.query(Category).filter(Category.name.ilike(name)).first()
    if cur:
        return {"id": cur.id, "name": cur.name, "created": False}
    obj = Category(name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "created": True}

