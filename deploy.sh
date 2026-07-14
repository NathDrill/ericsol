#!/usr/bin/env bash
# Déploiement ericsol (aidevoirs.com). À lancer sur la VM après un "git push" côté Mac.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
echo "==> Mise à jour du code (git pull)"
git pull --ff-only origin main
if [ -x backend/.venv/bin/pip ]; then
  echo "==> Dépendances backend"
  backend/.venv/bin/pip install -q -r backend/requirements.txt || true
fi
echo "==> Redémarrage du service"
systemctl restart ericsol
sleep 1
systemctl status ericsol --no-pager --lines=4 | head -8 || true
echo "==> Déployé ✓  →  https://aidevoirs.com"
