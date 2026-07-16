import os
import json as _json
import httpx as _httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from .core.config import settings
from .db.init_db import init_db
from .db.session import get_db
from .tasks.scheduler import start_scheduler
from .services.contract_service import indicators
from .api.routes import auth as auth_routes
from .api.routes import contracts as contracts_routes
from .api.routes import vendors as vendors_routes
from .api.routes import settings as settings_routes
from .api.routes import ai as ai_routes
from .api.routes import integrations as integrations_routes
from .api.routes import gdrive as gdrive_routes
from .api.routes import annotations as annotations_routes
from .api.routes import categories as categories_routes

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def front_no_stale_cache(request: Request, call_next):
    """Front en ES modules : le navigateur doit TOUJOURS revalider (no-cache => 304 si inchangé).
    Sans ça, le cache heuristique garde d'anciens JS apres un deploiement et casse l'app."""
    response = await call_next(request)
    if not request.url.path.startswith(settings.api_prefix):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.on_event("startup")
def on_startup():
    init_db()
    start_scheduler()


@app.get(f"{settings.api_prefix}/health")
def health():
    return {"status": "ok"}


app.include_router(auth_routes.router, prefix=settings.api_prefix)
app.include_router(contracts_routes.router, prefix=settings.api_prefix)
app.include_router(vendors_routes.router, prefix=settings.api_prefix)
app.include_router(settings_routes.router, prefix=settings.api_prefix)
app.include_router(ai_routes.router, prefix=settings.api_prefix)
app.include_router(integrations_routes.router, prefix=settings.api_prefix)
app.include_router(gdrive_routes.router, prefix=settings.api_prefix)
app.include_router(annotations_routes.router, prefix=settings.api_prefix)
app.include_router(categories_routes.router, prefix=settings.api_prefix)

# Fixed, high-priority metrics aliases to avoid any path conflicts
@app.get(f"{settings.api_prefix}/contracts/metrics")
def contracts_metrics_alias(db=Depends(get_db), user=Depends(auth_routes.get_current_user)):
    return indicators(db)

@app.get(f"{settings.api_prefix}/contracts/summary")
def contracts_summary_alias(db=Depends(get_db), user=Depends(auth_routes.get_current_user)):
    return indicators(db)

# Extra-stable alias to avoid any router conflicts entirely
@app.get(f"{settings.api_prefix}/contracts-metrics")
def contracts_metrics_extra_alias(db=Depends(get_db), user=Depends(auth_routes.get_current_user)):
    return indicators(db)

# Stable chat alias to avoid method/path issues
@app.api_route(f"{settings.api_prefix}/ai/chat", methods=["GET", "POST"])
async def ai_chat_alias(request: Request, db=Depends(get_db), user=Depends(auth_routes.get_current_user)):
    # Read question from query/form/json and return a safe fallback answer using indicators
    try:
        qp = request.query_params
        question = qp.get('question') or qp.get('q')
        if not question and request.method == 'POST':
            try:
                form = await request.form()
                question = form.get('question') or question
            except Exception:
                try:
                    data = await request.json()
                    if isinstance(data, dict):
                        question = data.get('question') or question
                except Exception:
                    pass
        stats = indicators(db)
        if not question:
            return {"answer": f"Contrats: {stats.get('count',0)} — MRR: {stats.get('mrr',0):.2f} EUR — ARR: {stats.get('arr',0):.2f} EUR"}
        # Fallback deterministic answer; IA détaillée gérée par route /api/ai/qa si disponible
        sc = stats.get('status_counts', {})
        ans = (
            f"Synthèse: {stats.get('count',0)} contrats. MRR {stats.get('mrr',0):.2f} EUR, ARR {stats.get('arr',0):.2f} EUR. "
            f"Actifs {sc.get('actif',0)}, Résiliés {sc.get('resilie',0)}, Expirés {sc.get('expire',0)}."
        )
        return {"answer": ans}
    except Exception:
        return {"answer": "Analyse indisponible pour le moment."}

"""
Serveur de frontend (build Vite) depuis FastAPI sur le même port.
Le build est attendu dans ../../frontend/dist relativement à ce fichier.
"""

FRONT_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))

if os.path.isdir(FRONT_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONT_DIST, "assets")), name="assets")


_CHAT_SYSTEM = (
    "Tu es un assistant IA francophone : clair, precis, utile et honnete. Reponds en francais. "
    "N'INVENTE JAMAIS de faits. Si une question porte sur une information recente, en temps reel ou "
    "que tu ne connais pas (resultat de match, meteo, actualite, prix, evenement recent) et qu'AUCUN "
    "resultat de recherche web ne t'est fourni dans le contexte, dis clairement et honnetement que tu "
    "ne disposes pas de cette information a jour, au lieu d'inventer une reponse."
)

_SEARCH_KW = ("actualit", "prix", "météo", "meteo", "cours", "bourse", "qui est", "qui sont", "quand",
    "combien", "cherche", "recherche", "dernier", "derniere", "récent", "recent", "aujourd", "news",
    "2024", "2025", "2026", "population", "capitale", "horaire", "résultat", "score", "sortie", "date de",
    "c'est quoi", "定", "quelle est", "quel est", "où se", "adresse de")


def _should_search(text: str) -> bool:
    t = (text or "").lower().strip()
    if not t:
        return False
    if "?" in t:
        return True
    return any(k in t for k in _SEARCH_KW)


def _fetch_page_text(url: str, limit: int = 1800) -> str:
    try:
        import re as _re
        r = _httpx.get(url, timeout=8.0, follow_redirects=True,
                       headers={"User-Agent": "Mozilla/5.0 (compatible; AssistantBot/1.0)"})
        if r.status_code != 200:
            return ""
        html = r.text
        html = _re.sub(r"(?is)<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", " ", html)
        text = _re.sub(r"(?s)<[^>]+>", " ", html)
        text = _re.sub(r"\s+", " ", text).strip()
        return text[:limit]
    except Exception:
        return ""


def _web_search(query: str, n: int = 5):
    results = []
    try:
        from ddgs import DDGS
        d = DDGS()
        try:
            for r in d.news(query, max_results=4, region="fr-fr"):
                results.append({"title": r.get("title") or "", "href": r.get("url") or r.get("href") or "", "body": r.get("body") or ""})
        except Exception:
            pass
        try:
            for r in d.text(query, max_results=n, region="fr-fr"):
                results.append({"title": r.get("title") or "", "href": r.get("href") or "", "body": r.get("body") or ""})
        except Exception:
            pass
    except Exception:
        return []
    seen, uniq = set(), []
    for r in results:
        if r["href"] and r["href"] not in seen:
            seen.add(r["href"]); uniq.append(r)
    uniq = uniq[:6]
    for r in uniq[:3]:
        page = _fetch_page_text(r["href"])
        if page and len(page) > len(r["body"]):
            r["body"] = page
    return uniq


async def _decide_search(base: str, model: str, key: str, last_user: str):
    """Le modèle décide lui-même s'il faut une recherche web + la requête. Renvoie (bool, query) ou None si erreur."""
    if not base or not (last_user or "").strip():
        return (False, "")
    prompt = [
        {"role": "system", "content":
            "Tu es un routeur. Determine si repondre correctement a la question de l'utilisateur necessite une "
            "recherche web : actualite, resultat sportif, meteo, prix/cours, evenement recent, horaires, ou tout "
            "fait susceptible d'avoir change depuis 2023 ou que tu ne connais pas avec certitude. "
            "Reponds UNIQUEMENT par un JSON compact, sans aucun texte autour : "
            "{\"search\": true|false, \"query\": \"requete web optimale, ou chaine vide\"}."},
        {"role": "user", "content": (last_user or "")[:1000]},
    ]
    try:
        async with _httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(base + "/chat/completions",
                json={"model": model, "messages": prompt, "stream": False, "temperature": 0, "max_tokens": 100},
                headers={"Authorization": "Bearer " + key})
        if r.status_code != 200:
            return None
        content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        import re as _re
        m = _re.search(r"\{.*\}", content, _re.S)
        if not m:
            return None
        j = _json.loads(m.group(0))
        q = str(j.get("query") or "").strip() or (last_user or "")
        return (bool(j.get("search")), q[:200])
    except Exception:
        return None


@app.post(f"{settings.api_prefix}/chat")
async def chat_stream(request: Request, user=Depends(auth_routes.get_current_user)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    incoming = body.get("messages") or []
    last_user = ""
    for m in reversed(incoming):
        if (m or {}).get("role") == "user":
            last_user = str((m or {}).get("content") or "")
            break

    base = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
    model = os.environ.get("LLM_MODEL", "mistral-small:24b")
    key = os.environ.get("LLM_API_KEY", "local")

    web_block = None
    decision = await _decide_search(base, model, key, last_user)
    if decision is None:                       # routeur en erreur -> filet heuristique
        do_search, query = (_should_search(last_user), last_user[:200])
    else:
        do_search, query = decision
    if do_search and query:
        results = await run_in_threadpool(_web_search, query, 5)
        if results:
            lines = [
                "RÉSULTATS DE RECHERCHE WEB effectués À L\u2019INSTANT pour toi — tu DISPOSES d\u2019un accès internet via ces extraits. "
                "Réponds DIRECTEMENT et factuellement en t\u2019appuyant dessus. "
                "Ne dis JAMAIS que tu ne peux pas naviguer sur internet ni accéder au temps réel. "
                "Si la réponse exacte (score, chiffre, date) figure dans les extraits, donne-la clairement. "
                "Cite les sources par [1], [2]… et termine par une section « Sources : ».",
                "",
            ]
            for i, r in enumerate(results, 1):
                lines.append("[%d] %s\n%s\n%s" % (i, r["title"], r["body"], r["href"]))
            web_block = "\n".join(lines)

    msgs = [{"role": "system", "content": _CHAT_SYSTEM}]
    if web_block:
        msgs.append({"role": "system", "content": web_block})
    for m in incoming[-20:]:
        role = str((m or {}).get("role") or "")
        content = str((m or {}).get("content") or "")[:8000]
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})

    async def gen():
        if not base:
            yield "Assistant non configuré (LLM_BASE_URL manquant)."
            return
        payload = {"model": model, "messages": msgs, "stream": True, "temperature": 0.4}
        try:
            async with _httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", base + "/chat/completions", json=payload,
                                         headers={"Authorization": "Bearer " + key}) as resp:
                    if resp.status_code != 200:
                        yield "Erreur du modèle (HTTP %d)." % resp.status_code
                        return
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            j = _json.loads(data)
                            delta = ((j.get("choices") or [{}])[0].get("delta") or {}).get("content")
                            if delta:
                                yield delta
                        except Exception:
                            continue
        except Exception as e:
            yield "\n[Assistant momentanément indisponible : %s]" % str(e)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


async def _stream_mistral(system: str, incoming: list, temperature: float = 0.4):
    base = (os.environ.get("LLM_BASE_URL") or "").rstrip("/")
    model = os.environ.get("LLM_MODEL", "mistral-small:24b")
    key = os.environ.get("LLM_API_KEY", "local")
    msgs = [{"role": "system", "content": system}]
    for m in (incoming or [])[-24:]:
        role = str((m or {}).get("role") or "")
        content = str((m or {}).get("content") or "")[:9000]
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    if not base:
        yield "Assistant non configuré."
        return
    payload = {"model": model, "messages": msgs, "stream": True, "temperature": temperature}
    try:
        async with _httpx.AsyncClient(timeout=240.0) as client:
            async with client.stream("POST", base + "/chat/completions", json=payload,
                                     headers={"Authorization": "Bearer " + key}) as resp:
                if resp.status_code != 200:
                    yield "Erreur du modèle (HTTP %d)." % resp.status_code
                    return
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        j = _json.loads(data)
                        delta = ((j.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
                    except Exception:
                        continue
    except Exception as e:
        yield "\n[Assistant momentanément indisponible : %s]" % str(e)


def _discovery_system(role: str) -> str:
    role = (role or "collaborateur").strip()[:80]
    return (
        "Tu es un consultant en solutions IA SOUVERAINES (modèle Mistral hébergé en France) pour la société Infoclip. "
        "Tu accompagnes un collaborateur du poste « %s » pour cadrer un projet d'application IA sur mesure. "
        "Mène un ENTRETIEN de cadrage : pose des questions ciblées, UNE ou DEUX à la fois, jamais un bloc. "
        "Cherche à comprendre : la tâche chronophage ou le problème concret, les applications/logiciels qu'il utilise "
        "aujourd'hui (Microsoft 365, CRM, compta, outils métier…), les données concernées, qui utiliserait l'outil, "
        "et le résultat attendu. Sois concret, bref, chaleureux et concret. Reformule ce que tu comprends. "
        "NE RÉDIGE PAS le cahier des charges maintenant : contente-toi de mener l'entretien jusqu'à avoir assez d'éléments. "
        "Quand tu estimes avoir l'essentiel, invite-le à cliquer sur « Générer le cahier des charges »."
    ) % role


def _spec_system(role: str) -> str:
    role = (role or "collaborateur").strip()[:80]
    return (
        "À partir de l'échange ci-dessus avec un collaborateur du poste « %s » chez Infoclip, rédige un CAHIER DES CHARGES "
        "structuré, professionnel et actionnable pour l'application IA souhaitée. Structure imposée, en markdown avec des titres ## :\n"
        "## 1. Contexte & poste concerné\n## 2. Problème / besoin identifié\n## 3. Objectif de l'application\n"
        "## 4. Utilisateurs cibles\n## 5. Applications & données à connecter\n## 6. Fonctionnalités clés (liste priorisée)\n"
        "## 7. Contraintes (souveraineté, sécurité, RGPD)\n## 8. Phases de réalisation proposées\n"
        "Appuie-toi UNIQUEMENT sur ce qui a été dit ; si une info manque, écris « à préciser ». "
        "Sois précis et concis, en français."
    ) % role


@app.post(f"{settings.api_prefix}/discovery")
async def discovery_chat(request: Request, user=Depends(auth_routes.get_current_user)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    role = str(body.get("role") or "")
    return StreamingResponse(_stream_mistral(_discovery_system(role), body.get("messages") or [], 0.5),
                             media_type="text/plain; charset=utf-8")


@app.post(f"{settings.api_prefix}/discovery/spec")
async def discovery_spec(request: Request, user=Depends(auth_routes.get_current_user)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    role = str(body.get("role") or "")
    convo = list(body.get("messages") or [])
    convo.append({"role": "user", "content": "Génère maintenant le cahier des charges complet selon la structure demandée."})
    return StreamingResponse(_stream_mistral(_spec_system(role), convo, 0.3),
                             media_type="text/plain; charset=utf-8")


@app.get("/{full_path:path}")
def spa_catch_all(full_path: str, request: Request):
    # Laisser passer les endpoints API
    if request.url.path.startswith(settings.api_prefix):
        raise HTTPException(status_code=404, detail="Not Found")
    host = (request.headers.get("host") or "").lower()
    if "aidevoirs" in host:
        chat_path = os.path.join(FRONT_DIST, "chat.html")
        if os.path.exists(chat_path):
            return FileResponse(chat_path, media_type="text/html")
    index_path = os.path.join(FRONT_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"message": "Frontend build missing. Please run frontend build."}
