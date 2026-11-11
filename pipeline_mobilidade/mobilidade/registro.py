from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class RegistroExecucao:

    def __init__(self, data_dir: Path, etapa: str, fonte: str, parametros: dict | None = None):
        self.arquivo = Path(data_dir) / "logs" / "execucoes.jsonl"
        self.etapa, self.fonte, self.parametros = etapa, fonte, parametros or {}
        self.n_registros: int | None = None
        self.mensagem = ""

    def __enter__(self):
        self.inicio = datetime.now()
        return self

    def __exit__(self, exc_type, exc, tb):
        fim = datetime.now()
        linha = {
            "etapa": self.etapa, "fonte": self.fonte, "parametros": self.parametros,
            "inicio": self.inicio.isoformat(timespec="seconds"), "fim": fim.isoformat(timespec="seconds"),
            "status": "erro" if exc else "ok", "n_registros": self.n_registros,
            "mensagem": str(exc) if exc else self.mensagem,
        }
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")
        return False


def ultimas(data_dir: Path, n: int = 20) -> list[dict]:
    arq = Path(data_dir) / "logs" / "execucoes.jsonl"
    if not arq.exists():
        return []
    linhas = arq.read_text(encoding="utf-8").strip().splitlines()[-n:]
    return [json.loads(x) for x in linhas]
