from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .db.init_db import init_db
from .tasks.scheduler import start_scheduler
from .api.routes import auth as auth_routes
from .api.routes import contracts as contracts_routes
from .api.routes import vendors as vendors_routes
from .api.routes import settings as settings_routes
from .api.routes import ai as ai_routes
from .api.routes import integrations as integrations_routes
from .api.routes import gdrive as gdrive_routes
from .api.routes import annotations as annotations_routes
from .api.routes import categories as categories_routes
from .services.contract_service import indicators
from .db.session import get_db
from fastapi import Depends
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/{full_path:path}")
def spa_catch_all(full_path: str, request: Request):
    # Laisser passer les endpoints API
    if request.url.path.startswith(settings.api_prefix):
        raise HTTPException(status_code=404, detail="Not Found")
    index_path = os.path.join(FRONT_DIST, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"message": "Frontend build missing. Please run frontend build."}
