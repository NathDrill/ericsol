from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from sqlalchemy.orm import Session
from app.models.settings import AppSetting
import json
import io
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

GDRIVE_SCOPE = ["https://www.googleapis.com/auth/drive.readonly"]
REDIRECT_PATH = "/api/integrations/gdrive/callback"
FOLDER_NAME = "kskade-contrats"


@dataclass
class GDriveSettings:
    client_id: str | None = None
    client_secret: str | None = None
    folder_id: str | None = None
    token: dict[str, Any] | None = None  # stores refresh_token/access_token json
    last_sync: str | None = None  # ISO8601
    connected: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "folder_id": self.folder_id,
            "token": self.token,
            "last_sync": self.last_sync,
            "connected": self.connected,
        })

    @staticmethod
    def from_json(s: str | None) -> GDriveSettings:
        if not s:
            return GDriveSettings()
        d = json.loads(s)
        return GDriveSettings(
            client_id=d.get("client_id"),
            client_secret=d.get("client_secret"),
            folder_id=d.get("folder_id"),
            token=d.get("token"),
            last_sync=d.get("last_sync"),
            connected=bool(d.get("connected")),
        )


def get_settings_row(db: Session) -> AppSetting:
    row = db.query(AppSetting).filter_by(key="gdrive").first()
    if not row:
        row = AppSetting(key="gdrive", value=GDriveSettings().to_json())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_settings(db: Session) -> GDriveSettings:
    return GDriveSettings.from_json(get_settings_row(db).value)


def set_settings(db: Session, s: GDriveSettings) -> GDriveSettings:
    row = get_settings_row(db)
    row.value = s.to_json()
    db.commit()
    return s


def build_flow(base_url: str, s: GDriveSettings) -> Flow:
    if not (s.client_id and s.client_secret):
        raise ValueError("Missing Google client_id/client_secret")
    redirect_uri = base_url.rstrip("/") + REDIRECT_PATH
    client_config = {
        "web": {
            "client_id": s.client_id,
            "client_secret": s.client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GDRIVE_SCOPE)
    flow.redirect_uri = redirect_uri
    return flow


def ensure_folder(drive, s: GDriveSettings) -> str:
    # Find by name if folder_id absent
    if s.folder_id:
        return s.folder_id
    q = "name = '%s' and mimeType = 'application/vnd.google-apps.folder' and trashed=false" % FOLDER_NAME
    res = drive.files().list(q=q, fields="files(id,name)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    # Create folder
    meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    fol = drive.files().create(body=meta, fields="id").execute()
    return fol["id"]


def list_new_pdfs(drive, folder_id: str, last_sync: str | None) -> list[dict]:
    q = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    if last_sync:
        q += f" and modifiedTime > '{last_sync}'"
    res = drive.files().list(q=q, fields="files(id,name,modifiedTime)", orderBy="modifiedTime asc").execute()
    return res.get("files", [])


def download_pdf(drive, file_id: str) -> bytes:
    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue()

