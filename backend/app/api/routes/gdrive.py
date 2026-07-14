from fastapi import APIRouter, Depends, Request, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.routes.auth import get_current_user
from app.services.gdrive_service import (
    get_settings, set_settings, build_flow, ensure_folder, list_new_pdfs, download_pdf, GDriveSettings
)
from app.services.source_storage_service import store_source_file
from datetime import datetime, timezone


router = APIRouter(prefix="/integrations/gdrive", tags=["integrations"])


@router.get("/config")
def get_config(db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_settings(db)
    return {
        "client_id": s.client_id,
        "has_client_secret": bool(s.client_secret),
        "folder_id": s.folder_id,
        "connected": s.connected,
        "last_sync": s.last_sync,
    }


@router.put("/config")
def put_config(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_settings(db)
    s.client_id = body.get("client_id")
    s.client_secret = body.get("client_secret")
    s.folder_id = body.get("folder_id")
    s.connected = False
    set_settings(db, s)
    return {"ok": True}


@router.get("/connect")
def connect(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    base_url = str(request.base_url).rstrip("/")
    s = get_settings(db)
    flow = build_flow(base_url, s)
    auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return {"auth_url": auth_url}


@router.get("/callback")
def callback(request: Request, code: str, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip("/")
    s = get_settings(db)
    flow = build_flow(base_url, s)
    flow.fetch_token(code=code)
    cred = flow.credentials
    s.token = {
        "token": cred.token,
        "refresh_token": cred.refresh_token,
        "token_uri": cred.token_uri,
        "client_id": cred.client_id,
        "client_secret": cred.client_secret,
        "scopes": cred.scopes,
    }
    # Build drive client and ensure folder
    drive = build("drive", "v3", credentials=cred)
    folder_id = ensure_folder(drive, s)
    s.folder_id = folder_id
    s.connected = True
    set_settings(db, s)
    return {"ok": True, "folder_id": folder_id}


@router.post("/sync")
def sync_now(db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = get_settings(db)
    if not (s.connected and s.token and s.folder_id):
        raise HTTPException(status_code=400, detail="GDrive not connected/configured")
    cred = Credentials(
        token=s.token.get("token"),
        refresh_token=s.token.get("refresh_token"),
        token_uri=s.token.get("token_uri"),
        client_id=s.token.get("client_id"),
        client_secret=s.token.get("client_secret"),
        scopes=s.token.get("scopes"),
    )
    drive = build("drive", "v3", credentials=cred)
    folder_id = s.folder_id
    files = list_new_pdfs(drive, folder_id, s.last_sync)
    created = []
    for f in files:
        try:
            data = download_pdf(drive, f["id"])
            stored = store_source_file(
                f["name"] or (f["id"] + ".pdf"),
                data,
                uploaded_by_email=getattr(user, "email", None),
                source_app="gdrive-sync",
            )
            created.append(
                {
                    "source_filename": stored["source_filename"],
                    "source_storage": stored["source_storage"],
                    "sharepoint_item_id": stored["sharepoint_item_id"],
                    "sharepoint_drive_id": stored["sharepoint_drive_id"],
                    "sharepoint_web_url": stored["sharepoint_web_url"],
                    "processing_status": "uploaded",
                }
            )
        except Exception:
            continue
    # Update last_sync
    s.last_sync = datetime.now(timezone.utc).isoformat()
    set_settings(db, s)
    return {"created": created, "count": len(created)}
