import os
from ..core.config import settings


def ensure_storage():
    os.makedirs(settings.storage_dir, exist_ok=True)


def save_contract_file(filename: str, data: bytes) -> str:
    ensure_storage()
    safe_name = filename.replace("/", "_")
    # Normaliser l'extension en .pdf si PDF
    base, ext = os.path.splitext(safe_name)
    if ext.upper() == ".PDF":
        safe_name = base + ".pdf"
    path = os.path.join(settings.storage_dir, safe_name)
    with open(path, "wb") as f:
        f.write(data)
    return path
