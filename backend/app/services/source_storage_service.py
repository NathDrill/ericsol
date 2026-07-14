from __future__ import annotations

import mimetypes
import os
import re
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator
from uuid import uuid4

import httpx

from app.core.config import settings
from app.utils.file_storage import save_contract_file


def sharepoint_storage_enabled() -> bool:
    return all(
        [
            settings.sharepoint_tenant_id,
            settings.sharepoint_client_id,
            settings.sharepoint_client_secret,
            settings.sharepoint_drive_id,
        ]
    )


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "document.pdf").strip() or "document.pdf"
    raw = raw.replace("\\", "_").replace("/", "_")
    raw = re.sub(r"[^A-Za-z0-9._ -]+", "_", raw)
    base, ext = os.path.splitext(raw)
    if ext.upper() == ".PDF":
        ext = ".pdf"
    cleaned = f"{base or 'document'}{ext or '.pdf'}"
    return cleaned


def _graph_token() -> str:
    if not sharepoint_storage_enabled():
        raise RuntimeError("SharePoint storage is not configured")
    url = f"https://login.microsoftonline.com/{settings.sharepoint_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.sharepoint_client_id,
        "client_secret": settings.sharepoint_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, data=data)
        resp.raise_for_status()
        payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Microsoft Graph token missing in response")
    return str(token)


def _graph_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@lru_cache(maxsize=16)
def _sharepoint_list_id(display_name: str) -> str:
    if not settings.sharepoint_site_id or not sharepoint_storage_enabled():
        raise RuntimeError("SharePoint site is not configured")
    token = _graph_token()
    url = f"https://graph.microsoft.com/v1.0/sites/{settings.sharepoint_site_id}/lists?$select=id,displayName"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_graph_headers(token))
        resp.raise_for_status()
        payload = resp.json()
    items = payload.get("value") or []
    wanted = (display_name or "").strip().lower()
    for item in items:
        if str(item.get("displayName") or "").strip().lower() == wanted:
            list_id = str(item.get("id") or "").strip()
            if list_id:
                return list_id
    raise RuntimeError(f"SharePoint list '{display_name}' not found")


def create_sharepoint_list_item(*, list_name: str, fields: dict[str, object | None]) -> dict:
    if not settings.sharepoint_site_id or not sharepoint_storage_enabled():
        raise RuntimeError("SharePoint list storage is not configured")
    payload_fields = {key: value for key, value in fields.items() if value is not None}
    token = _graph_token()
    list_id = _sharepoint_list_id(list_name)
    url = f"https://graph.microsoft.com/v1.0/sites/{settings.sharepoint_site_id}/lists/{list_id}/items"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=_graph_headers(token), json={"fields": payload_fields})
        resp.raise_for_status()
        return resp.json()


def get_sharepoint_list_item(*, list_name: str, item_id: str) -> dict:
    if not settings.sharepoint_site_id or not sharepoint_storage_enabled():
        raise RuntimeError("SharePoint list storage is not configured")
    token = _graph_token()
    list_id = _sharepoint_list_id(list_name)
    url = f"https://graph.microsoft.com/v1.0/sites/{settings.sharepoint_site_id}/lists/{list_id}/items/{item_id}?expand=fields"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_graph_headers(token))
        resp.raise_for_status()
        return resp.json()


def get_sharepoint_drive_item(*, item_id: str, drive_id: str | None = None) -> dict:
    if not item_id or not sharepoint_storage_enabled():
        raise RuntimeError("SharePoint file storage is not configured")
    token = _graph_token()
    target_drive = drive_id or settings.sharepoint_drive_id
    url = f"https://graph.microsoft.com/v1.0/drives/{target_drive}/items/{item_id}?expand=listItem($expand=fields)"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_graph_headers(token))
        resp.raise_for_status()
        return resp.json()


def _sharepoint_upload(filename: str, data: bytes) -> dict:
    token = _graph_token()
    original_name = _safe_filename(filename)
    stored_name = f"{uuid4().hex}_{original_name}"
    url = f"https://graph.microsoft.com/v1.0/drives/{settings.sharepoint_drive_id}/root:/{stored_name}:/content"
    mime_type, _ = mimetypes.guess_type(original_name)
    headers = _graph_headers(token)
    headers["Content-Type"] = mime_type or "application/octet-stream"
    with httpx.Client(timeout=60.0) as client:
        resp = client.put(url, headers=headers, content=data)
        resp.raise_for_status()
        payload = resp.json()
    return {
        "source_storage": "sharepoint",
        "source_filename": original_name,
        "sharepoint_item_id": payload.get("id"),
        "sharepoint_drive_id": payload.get("parentReference", {}).get("driveId") or settings.sharepoint_drive_id,
        "sharepoint_web_url": payload.get("webUrl"),
    }


def update_sharepoint_fields(
    *,
    item_id: str | None,
    fields: dict[str, object | None],
    drive_id: str | None = None,
) -> None:
    if not item_id or not sharepoint_storage_enabled():
        return
    payload = {key: value for key, value in fields.items() if value is not None}
    if not payload:
        return
    token = _graph_token()
    target_drive = drive_id or settings.sharepoint_drive_id
    url = f"https://graph.microsoft.com/v1.0/drives/{target_drive}/items/{item_id}/listItem/fields"
    with httpx.Client(timeout=30.0) as client:
        resp = client.patch(url, headers=_graph_headers(token), json=payload)
        resp.raise_for_status()


def store_source_file(filename: str, data: bytes, *, uploaded_by_email: str | None = None, source_app: str = "kskade-web") -> dict:
    safe_name = _safe_filename(filename)
    if sharepoint_storage_enabled():
        stored = _sharepoint_upload(safe_name, data)
        try:
            update_sharepoint_fields(
                item_id=stored.get("sharepoint_item_id"),
                drive_id=stored.get("sharepoint_drive_id"),
                fields={
                    "ProcessingStatus": "uploaded",
                    "UploadedByEmail": uploaded_by_email,
                    "SourceApp": source_app,
                },
            )
        except Exception:
            pass
        return stored
    path = save_contract_file(safe_name, data)
    return {
        "source_storage": "local",
        "source_filename": os.path.basename(path),
        "sharepoint_item_id": None,
        "sharepoint_drive_id": None,
        "sharepoint_web_url": None,
    }


def update_contract_storage_metadata(
    *,
    contract_id: int,
    title: str | None,
    source_storage: str | None,
    sharepoint_item_id: str | None,
    sharepoint_drive_id: str | None,
    uploaded_by_email: str | None = None,
) -> None:
    if source_storage != "sharepoint" or not sharepoint_item_id:
        return
    try:
        update_sharepoint_fields(
            item_id=sharepoint_item_id,
            drive_id=sharepoint_drive_id,
            fields={
                "KskadeContractId": str(contract_id),
                "ContractLabel": title,
                "UploadedByEmail": uploaded_by_email,
            },
        )
    except Exception:
        pass


def load_source_file(
    *,
    source_storage: str | None,
    source_filename: str | None,
    sharepoint_item_id: str | None = None,
    sharepoint_drive_id: str | None = None,
) -> dict:
    if source_storage == "sharepoint" and sharepoint_item_id:
        token = _graph_token()
        target_drive = sharepoint_drive_id or settings.sharepoint_drive_id
        meta_url = f"https://graph.microsoft.com/v1.0/drives/{target_drive}/items/{sharepoint_item_id}"
        content_url = f"{meta_url}/content"
        with httpx.Client(timeout=60.0) as client:
            meta_resp = client.get(meta_url, headers=_graph_headers(token))
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            content_resp = client.get(content_url, headers=_graph_headers(token), follow_redirects=True)
            content_resp.raise_for_status()
        name = meta.get("name") or source_filename or "document.pdf"
        mime_type = meta.get("file", {}).get("mimeType") or mimetypes.guess_type(str(name))[0] or "application/octet-stream"
        return {
            "filename": str(name),
            "content": content_resp.content,
            "mime_type": str(mime_type),
            "web_url": meta.get("webUrl"),
        }
    if not source_filename:
        raise FileNotFoundError("No source file configured")
    path = os.path.join(settings.storage_dir, source_filename)
    if not os.path.exists(path):
        raise FileNotFoundError("Local source file missing")
    mime_type, _ = mimetypes.guess_type(source_filename)
    with open(path, "rb") as fh:
        content = fh.read()
    return {
        "filename": source_filename,
        "content": content,
        "mime_type": mime_type or "application/octet-stream",
        "web_url": None,
    }


def delete_source_file(
    *,
    source_storage: str | None,
    source_filename: str | None,
    sharepoint_item_id: str | None = None,
    sharepoint_drive_id: str | None = None,
) -> None:
    if source_storage == "sharepoint" and sharepoint_item_id:
        token = _graph_token()
        target_drive = sharepoint_drive_id or settings.sharepoint_drive_id
        url = f"https://graph.microsoft.com/v1.0/drives/{target_drive}/items/{sharepoint_item_id}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.delete(url, headers=_graph_headers(token))
            resp.raise_for_status()
        return
    if source_filename:
        path = os.path.join(settings.storage_dir, source_filename)
        if os.path.exists(path):
            os.remove(path)


@contextmanager
def materialize_source_file(
    *,
    source_storage: str | None,
    source_filename: str | None,
    sharepoint_item_id: str | None = None,
    sharepoint_drive_id: str | None = None,
) -> Iterator[str]:
    if source_storage != "sharepoint":
        if not source_filename:
            raise FileNotFoundError("No source file configured")
        path = os.path.join(settings.storage_dir, source_filename)
        if not os.path.exists(path):
            raise FileNotFoundError("Local source file missing")
        yield path
        return

    payload = load_source_file(
        source_storage=source_storage,
        source_filename=source_filename,
        sharepoint_item_id=sharepoint_item_id,
        sharepoint_drive_id=sharepoint_drive_id,
    )
    suffix = os.path.splitext(payload["filename"])[1] or ".pdf"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(payload["content"])
            tmp_path = tmp.name
        yield tmp_path
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
