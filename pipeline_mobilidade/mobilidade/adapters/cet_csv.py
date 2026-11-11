from __future__ import annotations

from pathlib import Path

import pandas as pd

from .. import http
from ..armazenamento import salvar_bruto
from .base import FonteAdapter, ResultadoColeta, ler_csv_robusto, parece_html


class CetLentidaoCsv(FonteAdapter):
    nome = "cet_lentidao_csv"

    def coletar(self, origem: str) -> ResultadoColeta:
        if origem.lower().startswith(("http://", "https://")):
            r = http.get(origem, timeout=self.cfg.timeout, tentativas=self.cfg.tentativas, espera=self.cfg.espera)
            conteudo = r.content
            if parece_html(conteudo):
                raise http.FonteIndisponivel(
                    "o portal devolveu uma página HTML (provável desafio CAPTCHA). Baixe o CSV pelo navegador "
                    "e rode novamente com o caminho do arquivo local.")
            nome = origem.rstrip("/").split("/")[-1] or "lentidao.csv"
        else:
            p = Path(origem)
            if not p.exists():
                raise FileNotFoundError(f"arquivo não encontrado: {p}")
            conteudo, nome = p.read_bytes(), p.name
            if parece_html(conteudo):
                raise ValueError("o arquivo parece HTML, não CSV (download interrompido por CAPTCHA?).")
        df = ler_csv_robusto(conteudo)
        destino = salvar_bruto(self.cfg.data_dir, self.nome, nome, conteudo,
                               {"origem": origem, "n_registros": len(df), "colunas": list(df.columns)})
        return ResultadoColeta(fonte=self.nome, arquivos=[destino], n_registros=len(df))

    @staticmethod
    def ler(caminho) -> pd.DataFrame:
        return ler_csv_robusto(Path(caminho))
