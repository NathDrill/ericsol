from sqlalchemy.orm import Session
from datetime import date
from ..models.contract import Contract
from ..models.notification import NotificationLog
from ..models.settings import AppSetting
from ..schemas.settings import NotificationSettings
from .email_service import send_mail
import json


def get_settings(db: Session) -> NotificationSettings:
    row = db.query(AppSetting).filter_by(key="notifications").first()
    if not row:
        s = NotificationSettings()
        row = AppSetting(key="notifications", value=s.model_dump_json())
        db.add(row)
        db.commit()
        db.refresh(row)
    return NotificationSettings(**json.loads(row.value))


def set_settings(db: Session, s: NotificationSettings) -> NotificationSettings:
    row = db.query(AppSetting).filter_by(key="notifications").first()
    if not row:
        row = AppSetting(key="notifications", value=s.model_dump_json())
        db.add(row)
    else:
        row.value = s.model_dump_json()
    db.commit()
    return s


def send_pending_notifications(db: Session):
    s = get_settings(db)
    if not s.reminders_active or not s.recipients:
        return 0
    today = date.today()
    sent = 0
    for c in db.query(Contract).all():
        if c.cancel_deadline:
            delta = (c.cancel_deadline - today).days
            if delta in s.remind_days or (s.alert_no_auto_renewal and not c.has_auto_renewal):
                # Deduplicate simple: skip if already logged today
                exists = db.query(NotificationLog).filter_by(contract_id=c.id, kind=str(delta)).first()
                if exists:
                    continue
                subject = f"Alerte contrat {c.title}: J-{delta}"
                body = f"Contrat {c.title} — deadline résiliation: {c.cancel_deadline} — statut: {c.status}"
                if send_mail(subject, body, s.recipients):
                    db.add(NotificationLog(contract_id=c.id, kind=str(delta), recipients=",".join(s.recipients)))
                    db.commit()
                    sent += 1
    return sent

