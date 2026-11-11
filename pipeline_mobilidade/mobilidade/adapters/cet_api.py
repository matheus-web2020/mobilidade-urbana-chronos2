from __future__ import annotations

import hashlib
import json

import pandas as pd

from .. import http
from ..armazenamento import salvar_bruto
from .base import FonteAdapter, ResultadoColeta


def extrair_registros(payload, profundidade: int = 4) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and profundidade > 0:
        for chave in ("records", "registros", "dados", "data", "results", "result", "items"):
            if chave in payload:
                achado = extrair_registros(payload[chave], profundidade - 1)
                if achado:
                    return achado
        for v in payload.values():
            achado = extrair_registros(v, profundidade - 1)
            if achado:
                return achado
    return []


class CetLentidaoApi(FonteAdapter):
    nome = "cet_lentidao_api"
    ANO_MIN, ANO_MAX = 2001, 2018

    def coletar(self, anos: list[int], limite: int = 1000, max_paginas: int = 100_000) -> ResultadoColeta:
        if not self.cfg.apilib_token:
            raise http.FonteIndisponivel(
                "APILIB_TOKEN não definido. Cadastre-se em apilib.prefeitura.sp.gov.br, assine a API "
                "LentidaoTransito e gere o token (veja .env.example).")
        res = ResultadoColeta(fonte=self.nome, n_registros=0)
        headers = {"Authorization": f"Bearer {self.cfg.apilib_token}"}
        for ano in anos:
            if not (self.ANO_MIN <= ano <= self.ANO_MAX):
                res.observacoes.append(f"{ano}: fora do período documentado da API ({self.ANO_MIN}–{self.ANO_MAX}); pulado.")
                continue
            registros, offset, ultima_pagina = [], 0, None
            for _ in range(max_paginas):
                r = http.get(f"{self.cfg.apilib_base_url}/{ano}", params={"limite": limite, "offset": offset},
                             headers=headers, timeout=self.cfg.timeout, tentativas=self.cfg.tentativas,
                             espera=self.cfg.espera)
                pagina = extrair_registros(r.json())
                if not pagina:
                    break
                assinatura = hashlib.md5(json.dumps(pagina[:3], sort_keys=True, default=str).encode()).hexdigest()
                if assinatura == ultima_pagina:
                    res.observacoes.append(f"{ano}: a API repetiu a mesma página em offset={offset}; coleta interrompida.")
                    break
                ultima_pagina = assinatura
                registros.extend(pagina)
                offset += len(pagina)
            destino = salvar_bruto(self.cfg.data_dir, self.nome, f"lentidao_{ano}.json",
                                   json.dumps(registros, ensure_ascii=False).encode("utf-8"),
                                   {"ano": ano, "limite": limite, "n_registros": len(registros),
                                    "url": f"{self.cfg.apilib_base_url}/{ano}"})
            res.arquivos.append(destino)
            res.n_registros += len(registros)
        return res

    @staticmethod
    def ler(caminho) -> pd.DataFrame:
        from pathlib import Path
        return pd.DataFrame(json.loads(Path(caminho).read_text(encoding="utf-8")))
