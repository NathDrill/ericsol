from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.models.annotation import Annotation
from datetime import datetime

router = APIRouter()


@router.get("/annotations")
def list_annotations(path: str | None = Query(default=None), db: Session = Depends(get_db)):
    q = db.query(Annotation)
    if path:
        q = q.filter(Annotation.path == path)
    items = [
        {
            "id": a.id,
            "created_at": a.created_at.isoformat(),
            "path": a.path,
            "x_pct": float(a.x_pct),
            "y_pct": float(a.y_pct),
            "text": a.text,
            "done": bool(getattr(a, 'done', False)),
        }
        for a in q.order_by(Annotation.created_at.asc()).all()
    ]
    return {"ok": True, "items": items}


@router.get("/annotations/grouped")
def grouped_annotations(db: Session = Depends(get_db)):
    try:
        rows = db.execute(text(
            """
            SELECT path, COUNT(1) as n, MAX(created_at) as last_at
            FROM annotations
            GROUP BY path
            ORDER BY n DESC, last_at DESC
            """
        )).fetchall()
    except Exception:
        # If table doesn't exist yet or any transient error, return empty list
        return {"ok": True, "items": []}
    items = []
    for r in rows:
        last = r[2]
        if last is None:
            last_s = None
        else:
            last_s = last.isoformat() if hasattr(last, "isoformat") else str(last)
        items.append({"path": r[0], "count": r[1], "last_at": last_s})
    return {"ok": True, "items": items}


@router.post("/annotations")
def add_annotation(body: dict, db: Session = Depends(get_db)):
    path = (body.get("path") or "").strip()
    text = (body.get("text") or "").strip()
    try:
        x = float(body.get("x"))
        y = float(body.get("y"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_coordinates")
    if not path or not text:
        raise HTTPException(status_code=400, detail="missing_fields")
    a = Annotation(path=path, x_pct=max(0.0, min(100.0, x)), y_pct=max(0.0, min(100.0, y)), text=text[:2000], created_at=datetime.utcnow())
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"ok": True, "item": {
        "id": a.id,
        "created_at": a.created_at.isoformat(),
        "path": a.path,
        "x_pct": float(a.x_pct),
        "y_pct": float(a.y_pct),
        "text": a.text,
        "done": bool(getattr(a, 'done', False)),
    }}


from app.api.routes.auth import get_current_user


@router.delete("/annotations/{anno_id}")
def delete_annotation(anno_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    a = db.get(Annotation, anno_id)
    if not a:
        raise HTTPException(status_code=404, detail="not_found")
    db.delete(a)
    db.commit()
    return {"ok": True, "deleted": 1}


@router.patch("/annotations/{anno_id}")
def update_annotation_status(anno_id: int, body: dict, db: Session = Depends(get_db)):
    a = db.get(Annotation, anno_id)
    if not a:
        raise HTTPException(status_code=404, detail="not_found")
    if 'done' not in body:
        raise HTTPException(status_code=400, detail="missing_done")
    a.done = bool(body.get('done') is True)
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"ok": True, "item": {
        "id": a.id,
        "created_at": a.created_at.isoformat(),
        "path": a.path,
        "x_pct": float(a.x_pct),
        "y_pct": float(a.y_pct),
        "text": a.text,
        "done": bool(getattr(a, 'done', False)),
    }}
