from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.settings import NotificationSettings
from app.services.email_service import send_mail
from app.services.notification_service import get_settings, set_settings

from .auth import get_current_user


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/notifications", response_model=NotificationSettings)
def get_notifications(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_settings(db)


@router.put("/notifications", response_model=NotificationSettings)
def put_notifications(body: NotificationSettings, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return set_settings(db, body)


@router.post("/notifications/test")
def notifications_test(db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_settings(db)
    if not s.recipients:
        return {"ok": False, "detail": "Aucun destinataire configuré"}
    try:
        ok = send_mail("[Kskade] Test notifications", "Ceci est un test d'alerte.", s.recipients)
        return {"ok": bool(ok)}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
