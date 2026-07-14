from fastapi import APIRouter, Depends
from .auth import get_current_user


router = APIRouter(prefix="/integrations/sage-acs", tags=["integrations"])


@router.get("")
def status(user=Depends(get_current_user)):
    return {"status": "KO", "detail": "Stub non connecté"}


@router.post("/sync")
def sync(user=Depends(get_current_user)):
    return {"ok": True, "detail": "Sync déclenchée (stub)"}
