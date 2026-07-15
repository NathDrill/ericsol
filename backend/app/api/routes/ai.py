from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.session import get_db
from app.services.ai_service import portfolio_qa, _use_local_llm
from app.services.source_storage_service import create_sharepoint_list_item, get_sharepoint_list_item

from .auth import get_current_user


router = APIRouter(prefix="/ai", tags=["ai"])


def _normalize_global_response(answer: str, bullets: list[str], citations: list[dict]) -> dict:
    clean_answer = (answer or "").strip() or "Analyse indisponible pour le moment."
    clean_bullets = [str(item).strip() for item in bullets if str(item).strip()]
    clean_citations = []
    seen = set()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        url = str(citation.get("url") or "").strip()
        label = str(citation.get("label") or "").strip()
        if not url or not label or url in seen:
            continue
        seen.add(url)
        clean_citations.append(
            {
                "label": label,
                "url": url,
                "note": str(citation.get("note") or "").strip(),
            }
        )
    return {
        "answer": clean_answer,
        "bullets": clean_bullets,
        "citations": clean_citations,
    }


def _normalize_portfolio_links(source_links: object) -> list[dict]:
    if not isinstance(source_links, list):
        return []
    citations: list[dict] = []
    seen: set[str] = set()
    for entry in source_links:
        url = ""
        label = ""
        note = ""
        if isinstance(entry, str):
            url = entry.strip()
            label = entry.strip() or "Source"
        elif isinstance(entry, dict):
            url = str(entry.get("url") or entry.get("href") or entry.get("path") or "").strip()
            label = str(entry.get("label") or entry.get("title") or url or "Source").strip()
            note = str(entry.get("note") or entry.get("description") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append({"label": label, "url": url, "note": note})
    return citations


def _portfolio_status_payload(*, request_id: str, status: str, answer: str | None, answer_json: object, error_message: str | None) -> dict:
    parsed = answer_json if isinstance(answer_json, dict) else None
    normalized_answer = answer
    if not normalized_answer and parsed:
        candidate = str(parsed.get("answer") or "").strip()
        normalized_answer = candidate or None
    bullets = []
    citations = []
    if parsed:
        raw_bullets = parsed.get("bullets")
        if isinstance(raw_bullets, list):
            bullets = [str(item).strip() for item in raw_bullets if str(item).strip()]
        citations = _normalize_portfolio_links(parsed.get("source_links") or parsed.get("citations"))
    return {
        "request_id": request_id,
        "status": status,
        "ready": status in {"answered", "failed"},
        "answer": normalized_answer,
        "bullets": bullets,
        "citations": citations,
        "answer_json": parsed,
        "error_message": error_message,
    }


@router.api_route("/qa", methods=["GET", "POST"])
async def qa_global(request: Request, question: str | None = None, q: str | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Q&A portefeuille. En mode LLM local (Mistral/Ollama) : réponse SYNCHRONE en croisant
    toute la base de contrats — plus aucun flow SharePoint. `history` (JSON) = suivi de conversation."""
    history = None
    if not question:
        question = q
    if request.method == "POST":
        try:
            data = await request.json()
            if isinstance(data, dict):
                question = data.get("question") or question
                if isinstance(data.get("history"), list):
                    history = data["history"]
        except Exception:
            try:
                form = await request.form()
                question = form.get("question") or question
            except Exception:
                pass
    clean_question = (question or "").strip()
    if not clean_question:
        return {"mode": "local", "status": "answered", "ready": True, "answer": "Veuillez saisir une question.", "bullets": [], "citations": []}

    if _use_local_llm():
        # portfolio_qa est bloquant (appel GPU distant) → threadpool pour ne pas figer l'event loop.
        answer = await run_in_threadpool(portfolio_qa, clean_question, db, history)
        return {"mode": "local", "status": "answered", "ready": True, "answer": answer, "bullets": [], "citations": []}

    # Chemin historique SharePoint/Power Automate (mode cloud uniquement).
    try:
        created = create_sharepoint_list_item(
            list_name=settings.sharepoint_portfolio_questions_list_name,
            fields={
                "Title": f"QA portefeuille {date.today().isoformat()}",
                "Question": clean_question,
                "QuestionStatus": "pending",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to create SharePoint portfolio QA request: {exc}")

    request_id = str(created.get("id") or "").strip()
    if not request_id:
        raise HTTPException(status_code=502, detail="SharePoint portfolio QA request id missing")

    return {
        "mode": "queued",
        "request_id": request_id,
        "status": "pending",
        "answer": "Question envoyée au flow Microsoft. Réponse en attente.",
    }


@router.get("/qa-status")
def qa_global_status(request_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    clean_request_id = (request_id or "").strip()
    if not clean_request_id:
        raise HTTPException(status_code=400, detail="request_id is required")

    try:
        item = get_sharepoint_list_item(
            list_name=settings.sharepoint_portfolio_questions_list_name,
            item_id=clean_request_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to fetch SharePoint portfolio QA request: {exc}")

    fields = item.get("fields") or {}
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

    return _portfolio_status_payload(
        request_id=clean_request_id,
        status=status,
        answer=answer,
        answer_json=parsed_answer_json,
        error_message=error_message,
    )
