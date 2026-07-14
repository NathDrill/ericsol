from sqlalchemy.orm import Session
from ..models.settings import AppSetting
from pydantic import BaseModel
import json
from app.core.config import settings


class AISettings(BaseModel):
    openai_api_key: str | None = None
    enabled: bool = True
    model: str | None = "gpt-4.1"


def get_ai_settings(db: Session) -> AISettings:
    row = db.query(AppSetting).filter_by(key="ai").first()
    if not row:
        s = AISettings()
        row = AppSetting(key="ai", value=s.model_dump_json())
        db.add(row)
        db.commit()
        db.refresh(row)
    s = AISettings(**json.loads(row.value))
    # Fallback: if not configured in DB, use OPENAI_API_KEY from .env
    if not s.openai_api_key and settings.openai_api_key:
        s.openai_api_key = settings.openai_api_key
    return s


def set_ai_settings(db: Session, s: AISettings) -> AISettings:
    row = db.query(AppSetting).filter_by(key="ai").first()
    if not row:
        row = AppSetting(key="ai", value=s.model_dump_json())
        db.add(row)
    else:
        row.value = s.model_dump_json()
    db.commit()
    return s
