from fastapi import APIRouter, Depends, Header, UploadFile, File, Form, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models.contract import Contract
from app.models.sharepoint_analysis import SharePointAnalysis
from app.schemas.contracts import ContractsResponse, ContractIn, ContractOut, ContractUpdate
from app.models.category import Category
from app.services.contract_service import refresh_contract_statuses, indicators, create_contract
from app.services.ai_service import build_ai_response as _build_ai_response, _normalize_recurrence as _normalize_recurrence_util
from app.services.ai_service import contract_qa as _contract_qa_local, _use_local_llm as _use_local_llm_qa
from app.utils.file_storage import save_contract_file
from app.services.source_storage_service import (
    create_sharepoint_list_item,
    delete_source_file,
    get_sharepoint_list_item,
    get_sharepoint_drive_item,
    load_source_file,
    materialize_source_file,
    store_source_file,
    update_contract_storage_metadata,
)
from .auth import get_current_user
from fastapi.responses import FileResponse, StreamingResponse
from app.core.config import settings
import os
import csv
import mimetypes
from io import BytesIO, StringIO
from pypdf import PdfReader
from datetime import date, timedelta
import json
from uuid import uuid4
from app.models.notification import NotificationLog
from app.services.ai_settings_service import get_ai_settings
from app.services.ai_service import _parse_date as _parse_date_util, _parse_days as _parse_days_util, _compute_next_deadline as _compute_next_deadline_util

def _anchor_from_checklist(checklist):
    """Date d'ancrage de secours (date object) tiree du checklist quand effective_date est absente."""
    try:
        dates = ((checklist or {}).get('duration_echeances') or {}).get('dates') or {}
        for key in ('effective_date', 'signature_date', 'anniversary_date', 'initial_term_end_date', 'termination_deadline'):
            v = dates.get(key)
            if isinstance(v, str) and len(v) >= 8:
                iso = _parse_date_util(v)
                if iso:
                    y, m, d = map(int, iso.split('-'))
                    return date(y, m, d)
    except Exception:
        pass
    return None


router = APIRouter(prefix="/contracts", tags=["contracts"])


def _normalize_recurrence(value: str | None) -> str:
    raw = (value or "monthly").strip().lower()
    aliases = {
        "monthly": "monthly",
        "mensuel": "monthly",
        "month": "monthly",
        "quarterly": "quarterly",
        "trimestriel": "quarterly",
        "quarter": "quarterly",
        "semiannual": "semiannual",
        "semi-annual": "semiannual",
        "semestriel": "semiannual",
        "annual": "annual",
        "annuel": "annual",
        "yearly": "annual",
        "year": "annual",
        "biannual": "biannual",
        "biennal": "biannual",
    }
    return aliases.get(raw, "monthly")


def _contract_checklist(c: Contract) -> dict:
    try:
        return json.loads(c.checklist_json) if c.checklist_json else {}
    except Exception:
        return {}


def _extract_legal_entity(c: Contract, checklist: dict | None = None) -> str | None:
    data = checklist if checklist is not None else _contract_checklist(c)
    identity = data.get("identity") or {}
    legal_entity = identity.get("legal_entity")
    return legal_entity if isinstance(legal_entity, str) and legal_entity.strip() else None


def _extract_contract_end_date(c: Contract, checklist: dict | None = None) -> str | None:
    data = checklist if checklist is not None else _contract_checklist(c)
    try:
        dates = ((data.get("duration_echeances") or {}).get("dates") or {})
        end_date = dates.get("initial_term_end_date")
        if isinstance(end_date, str) and end_date.strip():
            return end_date
    except Exception:
        pass
    try:
        block = data.get("1️⃣ DURÉE DU CONTRAT") or {}
        end_date = block.get("Date d’échéance exacte")
        if isinstance(end_date, str) and end_date.strip():
            return end_date
    except Exception:
        pass
    return None


def _parse_annex_documents(c: Contract) -> list[dict]:
    try:
        items = json.loads(c.annex_documents_json) if c.annex_documents_json else []
        if not isinstance(items, list):
            return []
        cleaned: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("id") or "").strip()
            stored_filename = str(item.get("stored_filename") or "").strip()
            original_filename = str(item.get("original_filename") or stored_filename).strip()
            if not doc_id or not stored_filename:
                continue
            cleaned.append(
                {
                    "id": doc_id,
                    "stored_filename": stored_filename,
                    "original_filename": original_filename,
                    "mime_type": str(item.get("mime_type") or "").strip() or None,
                    "size_bytes": item.get("size_bytes"),
                    "uploaded_at": str(item.get("uploaded_at") or "").strip() or None,
                }
            )
        return cleaned
    except Exception:
        return []


def _save_annex_documents(c: Contract, documents: list[dict]) -> None:
    c.annex_documents_json = json.dumps(documents, ensure_ascii=False)


def _build_file_response(path: str, download_name: str, inline: bool = False) -> FileResponse:
    mime_type, _ = mimetypes.guess_type(download_name)
    return FileResponse(
        path,
        media_type=mime_type or "application/octet-stream",
        filename=download_name,
        content_disposition_type="inline" if inline else "attachment",
    )


def _extract_pdf_text(data: bytes) -> str:
    text = ""
    try:
        reader = PdfReader(BytesIO(data))
        for page in reader.pages:
            text += page.extract_text() or "\n"
    except Exception:
        return ""
    return text


def _parse_optional_date(value: object) -> date | None:
    if value in (None, "", "null"):
        return None
    try:
        normalized = str(value).strip()
        if "T" in normalized:
            normalized = normalized.split("T", 1)[0]
        iso_value = _parse_date_util(normalized)  # type: ignore[arg-type]
        if not iso_value:
            return None
        y, m, d = map(int, str(iso_value).split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _coerce_optional_bool(value: object) -> bool | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"true", "1", "yes", "oui", "vrai"}:
        return True
    if raw in {"false", "0", "no", "non", "faux"}:
        return False
    return None


def _coerce_optional_int(value: object) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except Exception:
        return None


def _coerce_optional_float(value: object) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(str(value).strip().replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _build_analysis_from_sharepoint_fields(fields: dict | None) -> dict | None:
    if not isinstance(fields, dict):
        return None
    parsed: dict = {}
    raw_analysis_json = fields.get("AnalysisJson")
    if raw_analysis_json not in (None, "", "null"):
        try:
            candidate = json.loads(str(raw_analysis_json))
            if isinstance(candidate, dict):
                parsed = candidate
        except Exception:
            parsed = {}

    analysis = dict(parsed)

    def _set_if_missing(key: str, value: object) -> None:
        if analysis.get(key) not in (None, "", "null"):
            return
        if value in (None, "", "null"):
            return
        analysis[key] = value

    _set_if_missing("vendor_name", fields.get("VendorName"))
    _set_if_missing("contract_label", fields.get("ContractLabel") or fields.get("Title"))
    _set_if_missing("summary", fields.get("Summary"))

    effective_date = _parse_optional_date(fields.get("EffectiveDate"))
    if effective_date:
        _set_if_missing("effective_date", effective_date.isoformat())

    contract_end_date = _parse_optional_date(fields.get("ContractEndDate"))
    if contract_end_date:
        _set_if_missing("contract_end_date", contract_end_date.isoformat())

    termination_notice_deadline = _parse_optional_date(fields.get("TerminationNoticeDeadline"))
    if termination_notice_deadline:
        _set_if_missing("termination_notice_deadline", termination_notice_deadline.isoformat())

    notice_period_days = _coerce_optional_int(fields.get("NoticePeriodDays"))
    if notice_period_days is not None:
        _set_if_missing("notice_period_days", notice_period_days)

    renewal_months = _coerce_optional_int(fields.get("RenewalMonths"))
    if renewal_months is not None:
        _set_if_missing("renewal_months", renewal_months)

    auto_renewal = _coerce_optional_bool(fields.get("AutoRenewal"))
    if auto_renewal is not None:
        _set_if_missing("auto_renewal", auto_renewal)

    amount = _coerce_optional_float(analysis.get("amount"))
    if amount is not None:
        analysis["amount"] = amount

    confidence = _coerce_optional_float(analysis.get("confidence"))
    if confidence is not None:
        analysis["confidence"] = confidence

    checklist = analysis.get("checklist")
    if not isinstance(checklist, dict):
        checklist = {}
        analysis["checklist"] = checklist

    identity = checklist.get("identity")
    if not isinstance(identity, dict):
        identity = {}
        checklist["identity"] = identity

    legal_entity = analysis.get("legal_entity")
    if isinstance(legal_entity, str) and legal_entity.strip() and not identity.get("legal_entity"):
        identity["legal_entity"] = legal_entity.strip()

    if not analysis:
        return None
    return analysis


def _get_sharepoint_processing_status(fields: dict | None) -> str:
    if not isinstance(fields, dict):
        return "pending"
    raw = (
        fields.get("ProcessingStatus")
        or fields.get("ProcessingStatusValue")
        or fields.get("processingstatus")
        or "pending"
    )
    return str(raw).strip().lower() or "pending"


def _fetch_sharepoint_status(*, item_id: str, drive_id: str | None) -> dict | None:
    return None  # SharePoint desactive : plus aucun appel Microsoft (fixe aussi la lenteur de la liste)
    payload = get_sharepoint_drive_item(item_id=item_id, drive_id=drive_id)
    fields = (((payload.get("listItem") or {}).get("fields")) or {})
    analysis = _build_analysis_from_sharepoint_fields(fields)
    processing_status = _get_sharepoint_processing_status(fields)
    resolved_drive_id = (
        payload.get("parentReference", {}).get("driveId")
        or drive_id
        or settings.sharepoint_drive_id
    )
    return {
        "sharepoint_item_id": str(payload.get("id") or item_id),
        "sharepoint_drive_id": str(resolved_drive_id or ""),
        "sharepoint_web_url": payload.get("webUrl"),
        "processing_status": processing_status,
        "ready": processing_status in {"analyzed", "failed"},
        "analysis": analysis,
    }


def _refresh_contract_from_sharepoint(contract: Contract) -> dict | None:
    if contract.source_storage != "sharepoint" or not contract.sharepoint_item_id:
        return None
    status = _fetch_sharepoint_status(
        item_id=contract.sharepoint_item_id,
        drive_id=contract.sharepoint_drive_id,
    )
    if not status:
        return None
    contract.sharepoint_item_id = status.get("sharepoint_item_id") or contract.sharepoint_item_id
    contract.sharepoint_drive_id = status.get("sharepoint_drive_id") or contract.sharepoint_drive_id
    contract.sharepoint_web_url = status.get("sharepoint_web_url") or contract.sharepoint_web_url
    analysis = status.get("analysis")
    if isinstance(analysis, dict) and analysis:
        _apply_cached_sharepoint_analysis(contract, analysis if isinstance(analysis, dict) else None, overwrite=True)
    return status


def _apply_cached_sharepoint_analysis(contract: Contract, analysis: dict | None, *, overwrite: bool = False) -> None:
    if not isinstance(analysis, dict):
        return
    if analysis.get("contract_label") and (overwrite or not contract.title):
        contract.title = str(analysis["contract_label"])
    if analysis.get("notice_period_days") is not None and (overwrite or contract.notice_period_days is None):
        try:
            contract.notice_period_days = int(analysis["notice_period_days"])
        except Exception:
            pass
    if overwrite or contract.effective_date is None:
        parsed = _parse_optional_date(analysis.get("effective_date"))
        if parsed:
            contract.effective_date = parsed
    if analysis.get("renewal_months") is not None and (overwrite or contract.renewal_months is None):
        try:
            contract.renewal_months = int(analysis["renewal_months"])
        except Exception:
            pass
    if overwrite or contract.cancel_deadline is None:
        parsed = _parse_optional_date(analysis.get("termination_notice_deadline"))
        if parsed:
            contract.cancel_deadline = parsed
    if analysis.get("auto_renewal") is not None and (overwrite or contract.has_auto_renewal is False):
        contract.has_auto_renewal = bool(analysis.get("auto_renewal"))
    recurrence = analysis.get("recurrence")
    if recurrence and (overwrite or not contract.recurrence):
        contract.recurrence = _normalize_recurrence(str(recurrence))
    if analysis.get("amount") is not None and (overwrite or not (contract.amount_mrr or 0)):
        try:
            amount_mrr = round(float(analysis.get("amount") or 0.0) + 1e-9, 2)
            contract.amount_mrr = amount_mrr
            contract.amount_arr = round((amount_mrr * 12.0) + 1e-9, 2)
        except Exception:
            pass
    checklist = analysis.get("checklist")
    if checklist and (overwrite or not contract.checklist_json):
        try:
            contract.checklist_json = json.dumps(checklist, ensure_ascii=False)
        except Exception:
            pass


def _upsert_sharepoint_analysis(
    db: Session,
    *,
    sharepoint_item_id: str,
    sharepoint_drive_id: str | None,
    sharepoint_web_url: str | None,
    processing_status: str,
    analysis: dict | None,
    contract_id: int | None = None,
) -> SharePointAnalysis:
    row = db.query(SharePointAnalysis).filter_by(sharepoint_item_id=sharepoint_item_id).first()
    if not row:
        row = SharePointAnalysis(sharepoint_item_id=sharepoint_item_id)
        db.add(row)
    row.sharepoint_drive_id = sharepoint_drive_id or row.sharepoint_drive_id
    row.sharepoint_web_url = sharepoint_web_url or row.sharepoint_web_url
    row.processing_status = processing_status or row.processing_status
    row.contract_id = contract_id or row.contract_id
    if analysis is not None:
        row.analysis_json = json.dumps(analysis, ensure_ascii=False)
        row.summary = str(analysis.get("summary") or "").strip() or row.summary
    db.flush()
    return row


def _link_pending_sharepoint_analysis(db: Session, contract: Contract) -> None:
    if not contract.sharepoint_item_id:
        return
    row = db.query(SharePointAnalysis).filter_by(sharepoint_item_id=contract.sharepoint_item_id).first()
    if not row:
        return
    row.contract_id = contract.id
    analysis = None
    if row.analysis_json:
        try:
            analysis = json.loads(row.analysis_json)
        except Exception:
            analysis = None
    _apply_cached_sharepoint_analysis(contract, analysis, overwrite=False)
    db.commit()
    db.refresh(contract)


def _serialize_contract(c: Contract) -> dict:
    checklist = _contract_checklist(c)
    # Compute a smart deadline: prefer stored cancel_deadline; else compute from effective_date + renewal_months minus notice; else fallback to initial_term_end_date from checklist
    display_deadline: str | None = None
    deadline_label: str | None = None
    try:
        if c.cancel_deadline:
            display_deadline = c.cancel_deadline.isoformat()
        else:
            eff_iso = c.effective_date.isoformat() if c.effective_date else None
            due = _compute_next_deadline_util(eff_iso, c.renewal_months)
            if due:
                # notify-by = due - notice_days (default 30)
                nd = c.notice_period_days or 30
                y, m, d = map(int, due.split('-'))
                notify_by = date(y, m, d) - timedelta(days=nd)
                display_deadline = notify_by.isoformat()
            else:
                # fallback to initial term end date from checklist if exists and no auto-renewal
                if checklist and not c.has_auto_renewal:
                    try:
                        endd = (
                            ((checklist.get('duration_echeances') or {}).get('dates', {}) or {}).get('initial_term_end_date')
                            or ((checklist.get('1️⃣ DURÉE DU CONTRAT') or {})).get("Date d’échéance exacte")
                        )
                        if isinstance(endd, str):
                            display_deadline = endd
                    except Exception:
                        pass
        # Set a friendly label when it is monthly auto-renewal with 30-day notice
        if (c.has_auto_renewal and (c.renewal_months or 0) == 1 and (c.notice_period_days or 30) >= 30):
            deadline_label = "J-30 fin de mois"
    except Exception:
        display_deadline = None
    # Derive MRR/ARR if missing from checklist
    derived_mrr = c.amount_mrr or 0.0
    derived_arr = c.amount_arr or 0.0
    try:
        if derived_mrr == 0 and checklist:
            fin = (checklist.get('financial') or {}).get('amounts') or {}
            if isinstance(fin.get('monthly_subscription'), (int, float)):
                derived_mrr = float(fin.get('monthly_subscription'))
                derived_arr = round(derived_mrr * 12.0 + 1e-9, 2)
            elif isinstance(fin.get('annual_subscription'), (int, float)):
                derived_arr = float(fin.get('annual_subscription'))
                derived_mrr = round(derived_arr / 12.0 + 1e-9, 2)
    except Exception:
        pass

    contract_end_date = _extract_contract_end_date(c, checklist)
    d = {
        "id": c.id,
        "vendor_id": c.vendor_id,
        "title": c.title,
        "legal_entity": _extract_legal_entity(c, checklist),
        "amount_mrr": round(derived_mrr + 1e-9, 2),
        "amount_arr": round(derived_arr + 1e-9, 2) or round((derived_mrr * 12.0) + 1e-9, 2),
        "recurrence": _normalize_recurrence(c.recurrence),
        "cancel_deadline": display_deadline,
        "cancel_deadline_label": deadline_label,
        "notice_period_days": c.notice_period_days,
        "effective_date": c.effective_date.isoformat() if c.effective_date else None,
        "contract_end_date": contract_end_date,
        "renewal_months": c.renewal_months,
        "resiliation_effective_date": c.resiliation_effective_date.isoformat() if c.resiliation_effective_date else None,
        "has_auto_renewal": c.has_auto_renewal,
        "has_commitment": c.has_commitment,
        "source_storage": c.source_storage,
        "source_filename": c.source_filename,
        "sharepoint_item_id": c.sharepoint_item_id,
        "sharepoint_drive_id": c.sharepoint_drive_id,
        "sharepoint_web_url": c.sharepoint_web_url,
        "annex_documents": [
            {
                "id": doc["id"],
                "original_filename": doc["original_filename"],
                "mime_type": doc.get("mime_type"),
                "size_bytes": doc.get("size_bytes"),
                "uploaded_at": doc.get("uploaded_at"),
            }
            for doc in _parse_annex_documents(c)
        ],
        "tags": [t for t in (c.tags or '').split(',') if t],
        "status": c.status,
        "checklist": None,
    }
    try:
        d["checklist"] = checklist or None
    except Exception:
        d["checklist"] = None
    return d


@router.get("", response_model=ContractsResponse)
def list_contracts(search: str | None = None, status: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    refresh_contract_statuses(db)
    q = db.query(Contract)
    if search:
        q = q.filter(Contract.title.ilike(f"%{search}%"))
    if status:
        q = q.filter(Contract.status == status)
    items = q.all()
    dirty = False
    for item in items:
        try:
            if _refresh_contract_from_sharepoint(item):
                dirty = True
        except Exception:
            continue
    if dirty:
        db.commit()
        refresh_contract_statuses(db)
    ind = indicators(db)
    return {"total": len(items), "indicators": ind, "items": [_serialize_contract(c) for c in items]}


@router.get("/sharepoint-analysis-status")
def sharepoint_analysis_status(
    item_ids: str | None = None,
    web_urls: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    requested_ids = [value.strip() for value in (item_ids or "").split(",") if value.strip()]
    requested_urls = [value.strip() for value in (web_urls or "").split(",") if value.strip()]
    if not requested_ids and not requested_urls:
        return {"items": []}

    query = db.query(SharePointAnalysis)
    if requested_ids and requested_urls:
        query = query.filter(
            (SharePointAnalysis.sharepoint_item_id.in_(requested_ids))
            | (SharePointAnalysis.sharepoint_web_url.in_(requested_urls))
        )
    elif requested_ids:
        query = query.filter(SharePointAnalysis.sharepoint_item_id.in_(requested_ids))
    else:
        query = query.filter(SharePointAnalysis.sharepoint_web_url.in_(requested_urls))

    rows = query.all()
    rows_by_id = {row.sharepoint_item_id: row for row in rows}
    rows_by_url = {row.sharepoint_web_url: row for row in rows if row.sharepoint_web_url}
    contract_rows = db.query(Contract).filter(Contract.sharepoint_web_url.in_(requested_urls)).all() if requested_urls else []
    contracts_by_url = {row.sharepoint_web_url: row for row in contract_rows if row.sharepoint_web_url}
    live_by_item_id: dict[str, dict | None] = {}

    def _resolve_identifiers(lookup_kind: str, lookup_value: str) -> tuple[str | None, str | None]:
        if lookup_kind == "item_id":
            cached = rows_by_id.get(lookup_value)
            return lookup_value, (cached.sharepoint_drive_id if cached else None)
        cached = rows_by_url.get(lookup_value)
        if cached:
            return cached.sharepoint_item_id, cached.sharepoint_drive_id
        contract = contracts_by_url.get(lookup_value)
        if contract:
            return contract.sharepoint_item_id, contract.sharepoint_drive_id
        return None, None

    lookup_keys: list[tuple[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for sharepoint_item_id in requested_ids:
        key = ("item_id", sharepoint_item_id)
        if key not in seen_keys:
            seen_keys.add(key)
            lookup_keys.append(key)
    for sharepoint_web_url in requested_urls:
        key = ("web_url", sharepoint_web_url)
        if key not in seen_keys:
            seen_keys.add(key)
            lookup_keys.append(key)

    items = []
    for lookup_kind, lookup_value in lookup_keys:
        row = rows_by_id.get(lookup_value) if lookup_kind == "item_id" else rows_by_url.get(lookup_value)
        resolved_item_id, resolved_drive_id = _resolve_identifiers(lookup_kind, lookup_value)
        live_status = None
        if resolved_item_id:
            if resolved_item_id not in live_by_item_id:
                try:
                    live_by_item_id[resolved_item_id] = _fetch_sharepoint_status(
                        item_id=resolved_item_id,
                        drive_id=resolved_drive_id,
                    )
                except Exception:
                    live_by_item_id[resolved_item_id] = None
            live_status = live_by_item_id.get(resolved_item_id)

        analysis = None
        if live_status and isinstance(live_status.get("analysis"), dict):
            analysis = live_status.get("analysis")
        elif row and row.analysis_json:
            try:
                analysis = json.loads(row.analysis_json)
            except Exception:
                analysis = None
        status = (
            (str(live_status.get("processing_status")).strip().lower() if live_status else None)
            or (row.processing_status if row else None)
            or "pending"
        )
        ready = status in {"analyzed", "failed"} or isinstance(analysis, dict)
        items.append(
            {
                "lookup_kind": lookup_kind,
                "lookup_value": lookup_value,
                "sharepoint_item_id": (live_status.get("sharepoint_item_id") if live_status else None) or (row.sharepoint_item_id if row else None) or resolved_item_id,
                "sharepoint_drive_id": (live_status.get("sharepoint_drive_id") if live_status else None) or (row.sharepoint_drive_id if row else None) or resolved_drive_id,
                "sharepoint_web_url": ((live_status.get("sharepoint_web_url") if live_status else None) or (row.sharepoint_web_url if row else None) or (lookup_value if lookup_kind == "web_url" else None)),
                "processing_status": status,
                "ready": ready,
                "analysis": analysis if isinstance(analysis, dict) else None,
            }
        )
    return {"items": items}


@router.post("", response_model=ContractOut)
def create(c: ContractIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Resolve category
    category_id = c.category_id
    cat_name = (c.category_name or '').strip()
    recurrence = _normalize_recurrence(c.recurrence)
    if not category_id and cat_name:
        cat = db.query(Category).filter(Category.name.ilike(cat_name)).first()
        if not cat:
            cat = Category(name=cat_name)
            db.add(cat)
            db.flush()
        category_id = cat.id
    obj = None
    if c.sharepoint_item_id:
        obj = db.query(Contract).filter_by(sharepoint_item_id=c.sharepoint_item_id).first()
    if obj is None and c.title and c.source_filename:
        obj = (
            db.query(Contract)
            .filter(func.lower(Contract.title) == c.title.strip().lower())
            .filter(func.lower(func.coalesce(Contract.source_filename, "")) == c.source_filename.strip().lower())
            .first()
        )

    if obj is not None:
        months_map = {'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12, 'biannual': 24}
        months = months_map.get((recurrence or 'monthly').lower(), 1)
        amount_mrr = round((float(c.amount or 0.0) / months) + 1e-9, 2)
        amount_arr = round((amount_mrr * 12.0) + 1e-9, 2)
        obj.vendor_id = c.vendor_id
        obj.category_id = category_id
        obj.title = c.title
        obj.amount_mrr = amount_mrr
        obj.amount_arr = amount_arr
        obj.recurrence = recurrence
        obj.cancel_deadline = c.cancel_deadline
        obj.notice_period_days = c.notice_period_days
        obj.effective_date = c.effective_date
        obj.renewal_months = c.renewal_months
        obj.has_auto_renewal = c.has_auto_renewal
        obj.has_commitment = c.has_commitment
        obj.source_storage = c.source_storage
        obj.source_filename = c.source_filename
        obj.sharepoint_item_id = c.sharepoint_item_id
        obj.sharepoint_drive_id = c.sharepoint_drive_id
        obj.sharepoint_web_url = c.sharepoint_web_url
        obj.source_text = c.source_text
        obj.price_evolution_report = c.price_evolution_report
        obj.tags = ",".join(c.tags)
        if c.checklist is not None:
            obj.checklist_json = json.dumps(c.checklist, ensure_ascii=False)
        db.commit()
        db.refresh(obj)
        refresh_contract_statuses(db)
    else:
        obj = create_contract(
            db,
            title=c.title,
            amount=c.amount,
            recurrence=recurrence,
            vendor_id=c.vendor_id,
            cancel_deadline=c.cancel_deadline,
            notice_period_days=c.notice_period_days,
            has_auto_renewal=c.has_auto_renewal,
            has_commitment=c.has_commitment,
            source_storage=c.source_storage,
            tags=",".join(c.tags),
            source_text=c.source_text,
            price_evolution_report=c.price_evolution_report,
            source_filename=c.source_filename,
            sharepoint_item_id=c.sharepoint_item_id,
            sharepoint_drive_id=c.sharepoint_drive_id,
            sharepoint_web_url=c.sharepoint_web_url,
            checklist=c.checklist,
            category_id=category_id,
            effective_date=c.effective_date,
            renewal_months=c.renewal_months,
        )
    update_contract_storage_metadata(
        contract_id=obj.id,
        title=obj.title,
        source_storage=obj.source_storage,
        sharepoint_item_id=obj.sharepoint_item_id,
        sharepoint_drive_id=obj.sharepoint_drive_id,
        uploaded_by_email=getattr(user, "email", None),
    )
    _link_pending_sharepoint_analysis(db, obj)
    d = _serialize_contract(obj)
    try:
        if obj.category_id:
            cat = db.query(Category).get(obj.category_id)
            if cat:
                d["category"] = cat.name
    except Exception:
        pass
    return d


@router.post("/upload")
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = file.file.read()
    stored = store_source_file(file.filename or "contrat.pdf", data, uploaded_by_email=getattr(user, "email", None))
    return {
        "filename": stored["source_filename"],
        "source_storage": stored["source_storage"],
        "sharepoint_item_id": stored["sharepoint_item_id"],
        "sharepoint_drive_id": stored["sharepoint_drive_id"],
        "sharepoint_web_url": stored["sharepoint_web_url"],
    }


@router.post("/analyze")
def analyze(text: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    raise HTTPException(status_code=410, detail="Local AI analysis is disabled. Use the Microsoft SharePoint flow.")


@router.post("/analyze-pdf")
def analyze_pdf(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = file.file.read()
    filename = file.filename or "contrat.pdf"
    stored = store_source_file(filename, data, uploaded_by_email=getattr(user, "email", None))
    # Extraction du texte (pypdf) puis analyse par le LLM on-prem (Mistral). Aucune donnee ne sort.
    text = ""
    try:
        reader = PdfReader(BytesIO(data))
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
    except Exception:
        text = ""
    try:
        analysis = _build_ai_response(text, db, file_path=None) or {}
    except Exception:
        analysis = {}
    title = analysis.get("contract_label") or filename
    contract = create_contract(
        db,
        title=str(title)[:255],
        amount=0.0,
        recurrence=_normalize_recurrence_util(analysis.get("recurrence") or "monthly"),
        source_storage=stored["source_storage"],
        source_filename=stored["source_filename"],
        source_text=(text or "")[:20000],
    )
    # Mapping analyse -> champs du contrat (meme logique que le flux d'analyse existant)
    _apply_cached_sharepoint_analysis(contract, analysis, overwrite=True)
    db.commit()
    db.refresh(contract)
    return _serialize_contract(contract)


@router.post("/analyze-batch")
def analyze_batch(files: list[UploadFile] = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    results = []
    for file in files:
        try:
            data = file.file.read()
            filename = file.filename or "contrat.pdf"
            stored = store_source_file(filename, data, uploaded_by_email=getattr(user, "email", None))
            results.append(
                {
                    "source_filename": stored["source_filename"],
                    "source_storage": stored["source_storage"],
                    "sharepoint_item_id": stored["sharepoint_item_id"],
                    "sharepoint_drive_id": stored["sharepoint_drive_id"],
                    "sharepoint_web_url": stored["sharepoint_web_url"],
                    "processing_status": "uploaded",
                }
            )
        except Exception as e:
            results.append({"error": str(e), "filename": file.filename})
    return {"items": results}


@router.get("/spend/summary")
def spend_summary(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.query(Contract).all()
    quarterly = round(sum((c.amount_mrr or 0) * 3 for c in items) + 1e-9, 2)
    annual = round(sum((c.amount_arr or 0) for c in items) + 1e-9, 2)
    return {"quarterly": quarterly, "annual": annual}


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,31,30,31,30,31,31,30,31,30,31][m-1])
    return date(y, m, day)


@router.get("/cancellation-windows")
def cancellation_windows(filter_current: bool = True, horizon_months: int = 24, db: Session = Depends(get_db), user=Depends(get_current_user)):
    refresh_contract_statuses(db)
    today = date.today()
    max_date = _add_months(today, horizon_months)
    res = []
    for c in db.query(Contract).all():
        notice = c.notice_period_days or 30
        checklist = _contract_checklist(c)
        legal_entity = _extract_legal_entity(c, checklist)
        # Robustesse resiliations : deriver la recurrence + une date d'ancrage si absentes
        _REC = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12, "biannual": 24}
        rmonths = c.renewal_months or _REC.get((c.recurrence or "").lower()) or (12 if c.has_auto_renewal else None)
        base = c.effective_date or _anchor_from_checklist(checklist)
        # Point de départ et pas de reconduction (robuste)
        if rmonths and base:
            # Générer toutes les échéances sur l'horizon
            period = rmonths
            n = 1
            while True:
                due = _add_months(base, n*period)
                if due > max_date:
                    break
                # fenêtre calculée autour de due
                start = due - timedelta(days=notice)
                window_earliest = start - timedelta(days=30)
                row = {
                    "id": c.id,
                    "title": c.title,
                    "legal_entity": legal_entity,
                    "vendor_id": c.vendor_id,
                    "window_start": start.isoformat(),
                    "window_earliest": window_earliest.isoformat(),
                    "deadline": due.isoformat(),
                    "status": c.status,
                    "resiliation_effective_date": c.resiliation_effective_date.isoformat() if c.resiliation_effective_date else None,
                }
                if filter_current:
                    if window_earliest <= today <= due:
                        res.append(row)
                else:
                    if today <= due <= max_date:
                        res.append(row)
                n += 1
        elif c.cancel_deadline:
            start = c.cancel_deadline - timedelta(days=notice)
            window_earliest = start - timedelta(days=30)
            row = {
                "id": c.id,
                "title": c.title,
                "legal_entity": legal_entity,
                "vendor_id": c.vendor_id,
                "window_start": start.isoformat(),
                "window_earliest": window_earliest.isoformat(),
                "deadline": c.cancel_deadline.isoformat(),
                "status": c.status,
                "resiliation_effective_date": c.resiliation_effective_date.isoformat() if c.resiliation_effective_date else None,
            }
            if filter_current:
                if window_earliest <= today <= c.cancel_deadline:
                    res.append(row)
            else:
                if today <= c.cancel_deadline <= max_date:
                    res.append(row)
    return {"items": sorted(res, key=lambda r: r["deadline"]) }


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db), user=Depends(get_current_user)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "title", "vendor_id", "mrr", "arr", "status", "cancel_deadline"])
    for c in db.query(Contract).all():
        mrr = f"{(c.amount_mrr or 0):.2f}"
        arr = f"{(c.amount_arr or 0):.2f}"
        writer.writerow([c.id, c.title, c.vendor_id, mrr, arr, c.status, c.cancel_deadline])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contracts.csv"})


# Place summary endpoints before dynamic /{contract_id} to avoid 422 on matching
@router.get("/stats")
def contracts_stats(db: Session = Depends(get_db), user=Depends(get_current_user)):
    refresh_contract_statuses(db)
    ind = indicators(db)
    return ind


@router.get("/metrics")
def contracts_metrics(db: Session = Depends(get_db), user=Depends(get_current_user)):
    refresh_contract_statuses(db)
    return indicators(db)

@router.get("/summary")
def contracts_summary_alias(db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Backward-compatible alias for older frontends
    return contracts_metrics(db, user)  # type: ignore


@router.get("/{contract_id:int}", response_model=ContractOut)
def get_contract(contract_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    refresh_contract_statuses(db)
    try:
        if _refresh_contract_from_sharepoint(obj):
            db.commit()
    except Exception:
        db.rollback()
    db.refresh(obj)
    d = _serialize_contract(obj)
    try:
        if obj.category_id:
            cat = db.query(Category).get(obj.category_id)
            if cat:
                d["category"] = cat.name
    except Exception:
        pass
    return d


@router.put("/{contract_id:int}", response_model=ContractOut)
def update_contract(contract_id: int, body: ContractUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "tags" in data and isinstance(data["tags"], list):
        # store tags as comma-separated string
        data["tags"] = ",".join([t for t in data["tags"] if t]) or None
    if "recurrence" in data:
        data["recurrence"] = _normalize_recurrence(data.get("recurrence"))
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return _serialize_contract(obj)


@router.delete("/purge")
def purge_all_contracts(db: Session = Depends(get_db), user=Depends(get_current_user)):
    items = db.query(Contract).all()
    deleted = 0
    for c in items:
        try:
            delete_source_file(
                source_storage=c.source_storage,
                source_filename=c.source_filename,
                sharepoint_item_id=c.sharepoint_item_id,
                sharepoint_drive_id=c.sharepoint_drive_id,
            )
        except Exception:
            pass
        for doc in _parse_annex_documents(c):
            try:
                path = os.path.join(settings.storage_dir, doc["stored_filename"])
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        deleted += 1
    # Clean related logs
    db.query(NotificationLog).delete()
    # Delete contracts
    db.query(Contract).delete()
    db.commit()
    return {"deleted_contracts": deleted}


@router.post("/recompute-cancellations")
def recompute_cancellations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    raise HTTPException(status_code=410, detail="OpenAI cancellation recompute is disabled. Use Microsoft flows and SharePoint data.")


@router.post("/sharepoint-analysis-callback")
def sharepoint_analysis_callback(
    body: dict,
    db: Session = Depends(get_db),
    x_kskade_webhook_secret: str | None = Header(None),
):
    expected = settings.sharepoint_callback_secret
    if expected and x_kskade_webhook_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    sharepoint_item_id = str(body.get("sharepoint_item_id") or "").strip()
    if not sharepoint_item_id:
        raise HTTPException(status_code=400, detail="sharepoint_item_id is required")

    sharepoint_drive_id = str(body.get("sharepoint_drive_id") or "").strip() or None
    sharepoint_web_url = str(body.get("sharepoint_web_url") or "").strip() or None
    processing_status = str(body.get("processing_status") or "analyzed").strip() or "analyzed"
    contract_id = body.get("kskade_contract_id")

    analysis = body.get("analysis")
    if analysis is None and body.get("analysis_json"):
        try:
            analysis = json.loads(str(body.get("analysis_json")))
        except Exception:
            analysis = None
    if analysis is None:
        analysis = {}

    matched_contract = None
    if contract_id is not None:
        try:
            matched_contract = db.query(Contract).get(int(contract_id))
        except Exception:
            matched_contract = None
    if matched_contract is None:
        matched_contract = db.query(Contract).filter_by(sharepoint_item_id=sharepoint_item_id).first()

    row = _upsert_sharepoint_analysis(
        db,
        sharepoint_item_id=sharepoint_item_id,
        sharepoint_drive_id=sharepoint_drive_id,
        sharepoint_web_url=sharepoint_web_url,
        processing_status=processing_status,
        analysis=analysis if isinstance(analysis, dict) else None,
        contract_id=matched_contract.id if matched_contract else None,
    )

    if matched_contract:
        matched_contract.sharepoint_item_id = sharepoint_item_id
        matched_contract.sharepoint_drive_id = sharepoint_drive_id or matched_contract.sharepoint_drive_id
        matched_contract.sharepoint_web_url = sharepoint_web_url or matched_contract.sharepoint_web_url
        _apply_cached_sharepoint_analysis(matched_contract, analysis if isinstance(analysis, dict) else None, overwrite=True)
    db.commit()

    return {
        "ok": True,
        "matched_contract": bool(matched_contract),
        "contract_id": matched_contract.id if matched_contract else None,
        "analysis_cache_id": row.id,
    }


@router.delete("/{contract_id:int}")
def delete_contract(contract_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        delete_source_file(
            source_storage=obj.source_storage,
            source_filename=obj.source_filename,
            sharepoint_item_id=obj.sharepoint_item_id,
            sharepoint_drive_id=obj.sharepoint_drive_id,
        )
    except Exception:
        pass
    for doc in _parse_annex_documents(obj):
        try:
            path = os.path.join(settings.storage_dir, doc["stored_filename"])
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    # remove logs related
    db.query(NotificationLog).filter_by(contract_id=obj.id).delete()
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.post("/{contract_id:int}/qa")
def qa_contract(contract_id: int, question: str = Form(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    clean_question = (question or "").strip()
    if not clean_question:
        raise HTTPException(status_code=400, detail="question is required")

    if _use_local_llm_qa():
        answer = _contract_qa_local(clean_question, obj, db)
        return {"mode": "local", "status": "answered", "ready": True, "answer": answer}

    if not obj.sharepoint_item_id or not obj.sharepoint_drive_id:
        return {
            "mode": "unavailable",
            "answer": "Le chat Microsoft n'est pas disponible pour ce contrat tant qu'il n'est pas relié à un fichier SharePoint.",
        }

    try:
        created = create_sharepoint_list_item(
            list_name=settings.sharepoint_questions_list_name,
            fields={
                "Title": f"QA contrat #{obj.id}",
                "KskadeContractId": str(obj.id),
                "SharepointItemId": obj.sharepoint_item_id,
                "SharepointDriveId": obj.sharepoint_drive_id,
                "SharepointWebUrl": obj.sharepoint_web_url,
                "Question": clean_question,
                "QuestionStatus": "pending",
                "AskedByEmail": getattr(user, "email", None),
                "ProcessingProvider": "power-automate",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to create SharePoint QA request: {exc}")

    request_id = str(created.get("id") or "").strip()
    if not request_id:
        raise HTTPException(status_code=502, detail="SharePoint QA request id missing")
    return {
        "mode": "queued",
        "request_id": request_id,
        "status": "pending",
        "answer": "Question envoyée au flow Microsoft. Réponse en attente.",
    }


@router.get("/{contract_id:int}/qa-status")
def qa_contract_status(contract_id: int, request_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")

    clean_request_id = (request_id or "").strip()
    if not clean_request_id:
        raise HTTPException(status_code=400, detail="request_id is required")

    try:
        item = get_sharepoint_list_item(
            list_name=settings.sharepoint_questions_list_name,
            item_id=clean_request_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch SharePoint QA request: {exc}")

    fields = item.get("fields") or {}
    linked_contract_id = str(fields.get("KskadeContractId") or "").strip()
    if linked_contract_id and linked_contract_id != str(obj.id):
        raise HTTPException(status_code=403, detail="Request does not belong to this contract")

    raw_answer_json = fields.get("AnswerJson")
    parsed_answer_json = None
    if raw_answer_json:
        try:
            parsed_answer_json = json.loads(str(raw_answer_json))
        except Exception:
            parsed_answer_json = None

    status = str(fields.get("QuestionStatus") or "pending").strip() or "pending"
    answer = str(fields.get("Answer") or "").strip() or None
    error_message = str(fields.get("ErrorMessage") or "").strip() or None

    return {
        "request_id": clean_request_id,
        "status": status,
        "ready": status in {"answered", "failed"},
        "answer": answer,
        "answer_json": parsed_answer_json,
        "error_message": error_message,
    }


@router.put("/{contract_id:int}/marquer-resilie")
def mark_resilie(contract_id: int, effective_date: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    obj.status = "resilie"
    # Optionally set termination effective date
    if effective_date:
        try:
            y, m, d = map(int, effective_date.split('-'))
            obj.resiliation_effective_date = date(y, m, d)
        except Exception:
            pass
    db.commit()
    return {"ok": True}




@router.post("/{contract_id:int}/documents")
def upload_annex_documents(contract_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    documents = _parse_annex_documents(obj)
    created: list[dict] = []
    for file in files:
        content = file.file.read()
        if not content:
            continue
        original_name = os.path.basename(file.filename or "document")
        stored_name = f"{uuid4().hex}_{original_name}"
        save_contract_file(stored_name, content)
        entry = {
            "id": uuid4().hex,
            "stored_filename": stored_name,
            "original_filename": original_name,
            "mime_type": file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
            "size_bytes": len(content),
            "uploaded_at": date.today().isoformat(),
        }
        documents.append(entry)
        created.append(
            {
                "id": entry["id"],
                "original_filename": entry["original_filename"],
                "mime_type": entry["mime_type"],
                "size_bytes": entry["size_bytes"],
                "uploaded_at": entry["uploaded_at"],
            }
        )
    _save_annex_documents(obj, documents)
    db.commit()
    db.refresh(obj)
    return {"items": created}


@router.get("/{contract_id:int}/documents/{document_id}/download")
def download_annex_document(contract_id: int, document_id: str, inline: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    documents = _parse_annex_documents(obj)
    doc = next((item for item in documents if item["id"] == document_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = os.path.join(settings.storage_dir, doc["stored_filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File missing")
    return _build_file_response(path, doc["original_filename"], inline=inline)


@router.get("/{contract_id:int}/download")
def download_source(contract_id: int, inline: bool = False, db: Session = Depends(get_db), user=Depends(get_current_user)):
    obj = db.query(Contract).get(contract_id)
    if not obj or (not obj.source_filename and not obj.sharepoint_item_id):
        raise HTTPException(status_code=404, detail="No source")
    try:
        payload = load_source_file(
            source_storage=obj.source_storage,
            source_filename=obj.source_filename,
            sharepoint_item_id=obj.sharepoint_item_id,
            sharepoint_drive_id=obj.sharepoint_drive_id,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File missing")
    disposition = "inline" if inline else "attachment"
    headers = {"Content-Disposition": f'{disposition}; filename="{payload["filename"]}"'}
    return Response(content=payload["content"], media_type=payload["mime_type"], headers=headers)
