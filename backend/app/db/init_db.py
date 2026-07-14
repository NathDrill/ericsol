from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import Base, engine
from ..models.user import User
from ..models.vendor import Vendor, VendorAlias
from ..models.contract import Contract
from ..models.settings import AppSetting
from ..models.category import Category
from ..models.notification import NotificationLog
from ..models.annotation import Annotation  # ensure table is created
from ..models.sharepoint_analysis import SharePointAnalysis  # ensure table is created
from ..services.security import get_password_hash
from ..schemas.settings import NotificationSettings
import json


def init_db():
    Base.metadata.create_all(bind=engine)
    db = Session(bind=engine)
    try:
        # Ensure new columns exist (SQLite): detect and add if missing
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(contracts)"))}
            add = []
            if 'notice_period_days' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN notice_period_days INTEGER")
            if 'checklist_json' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN checklist_json TEXT")
            if 'effective_date' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN effective_date DATE")
            if 'renewal_months' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN renewal_months INTEGER")
            if 'resiliation_effective_date' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN resiliation_effective_date DATE")
            if 'category_id' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN category_id INTEGER REFERENCES categories(id)")
            if 'annex_documents_json' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN annex_documents_json TEXT")
            if 'source_storage' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN source_storage TEXT")
            if 'sharepoint_item_id' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN sharepoint_item_id TEXT")
            if 'sharepoint_drive_id' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN sharepoint_drive_id TEXT")
            if 'sharepoint_web_url' not in cols:
                add.append("ALTER TABLE contracts ADD COLUMN sharepoint_web_url TEXT")
            for sql in add:
                conn.execute(text(sql))
            # Ensure annotations table exists and has 'done' column
            conn.execute(text("CREATE TABLE IF NOT EXISTS annotations (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
            anno_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(annotations)"))}
            if 'done' not in anno_cols:
                try:
                    conn.execute(text("ALTER TABLE annotations ADD COLUMN done INTEGER DEFAULT 0 NOT NULL"))
                except Exception:
                    pass
        # users
        if not db.query(User).filter_by(email="eric.melki@example.com").first():
            db.add(User(email="eric.melki@example.com", full_name="Eric Melki", hashed_password=get_password_hash("Contrats2024!"), is_superuser=True))
        if not db.query(User).filter_by(email="eric.houri@example.com").first():
            db.add(User(email="eric.houri@example.com", full_name="Eric Houri", hashed_password=get_password_hash("Contrats2024!"), is_superuser=True))
        # vendors
        for name, aliases in [
            ("Orange Business", ["Orange", "OB"]),
            ("Microsoft", ["MS", "Office 365"]),
            ("OVHcloud", ["OVH"]),
        ]:
            v = db.query(Vendor).filter_by(name=name).first()
            if not v:
                v = Vendor(name=name)
                db.add(v)
                db.flush()
                for a in aliases:
                    db.add(VendorAlias(vendor_id=v.id, alias=a))
        # Seed default categories
        defaults = [
            "hébergement", "infogérance", "location/financement", "SAAS", "IAAS", "Datacenters", "Autres prestations",
        ]
        for name in defaults:
            if not db.query(Category).filter_by(name=name).first():
                db.add(Category(name=name, built_in=True))
        # default settings
        if not db.query(AppSetting).filter_by(key="notifications").first():
            s = NotificationSettings(recipients=["eric.melki@example.com", "eric.houri@example.com"]).model_dump_json()
            db.add(AppSetting(key="notifications", value=s))
        # default AI settings: no embedded secret in source code
        if not db.query(AppSetting).filter_by(key="ai").first():
            ai = {"openai_api_key": None, "enabled": True, "model": "gpt-4.1"}
            db.add(AppSetting(key="ai", value=json.dumps(ai)))
        db.commit()
    finally:
        db.close()
