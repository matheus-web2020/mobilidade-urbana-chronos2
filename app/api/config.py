from __future__ import annotations

import os
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
PIPELINE = APP.parent / "pipeline_mobilidade"


def _ler_env() -> dict:
    arq = APP / ".env"
    if not arq.exists():
        return {}
    pares = (linha.split("=", 1) for linha in arq.read_text(encoding="utf-8").splitlines() if "=" in linha)
    return {k.strip(): v.strip() for k, v in pares}


def database_url(teste: bool = False) -> str:
    chave = "DATABASE_URL_TESTE" if teste else "DATABASE_URL"
    url = os.environ.get(chave) or _ler_env().get(chave)
    if not url:
        raise RuntimeError(f"defina {chave} (variável de ambiente ou app/.env)")
    return url
