from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd
import psycopg

from .config import APP, PIPELINE, database_url
from .criticidade import ParametrosCriticidade, limites_por_quartis

V2 = PIPELINE / "resultados" / "v2"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def carregar(url: str, series: pd.DataFrame, meta: pd.DataFrame, feriados: pd.DataFrame, origem: str = "") -> dict:
    with psycopg.connect(url) as con:
        con.execute((APP / "db" / "schema.sql").read_text(encoding="utf-8"))
        con.execute("TRUNCATE serie_horaria, localidade, feriado RESTART IDENTITY CASCADE")
        with con.cursor() as cur:
            for r in meta.itertuples(index=False):
                cur.execute("INSERT INTO localidade (series_id, corredor, sentido, regiao, tipo_via, extensao_max_km) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (r.series_id, r.corredor, r.sentido, r.regiao, r.tipo_via, float(r.extensao_max_km)))
            ids = dict(cur.execute("SELECT series_id, id FROM localidade").fetchall())
            s = series[series.series_id.isin(ids)].dropna(subset=["target"])
            buf = io.StringIO()
            pd.DataFrame({"l": s.series_id.map(ids), "t": s.timestamp.dt.strftime("%Y-%m-%d %H:%M:%S"),
                          "k": s.target.round(4)}).to_csv(buf, index=False, header=False)
            buf.seek(0)
            with cur.copy("COPY serie_horaria (localidade_id, instante, km_lentidao) FROM STDIN WITH (FORMAT csv)") as cp:
                while bloco := buf.read(1 << 20):
                    cp.write(bloco)
            for r in feriados.itertuples(index=False):
                cur.execute("INSERT INTO feriado (data, nome) VALUES (%s,%s) ON CONFLICT DO NOTHING", (r.data, r.nome))
            indices = [x for (x,) in cur.execute(
                "SELECT AVG(s.km_lentidao) FROM serie_horaria s "
                "WHERE s.instante >= '2022-01-01' AND s.instante < '2023-01-01' "
                "AND EXTRACT(ISODOW FROM s.instante) < 6 AND EXTRACT(HOUR FROM s.instante) BETWEEN 7 AND 19 "
                "AND s.instante::date NOT IN (SELECT data FROM feriado) GROUP BY s.localidade_id").fetchall()]
            p = ParametrosCriticidade(limites_por_quartis([float(x) for x in indices]),
                                      origem_limites="quartis do índice de 2022 entre corredores com lentidão")
            cur.execute("INSERT INTO parametro_sistema (chave, valor, descricao) VALUES ('criticidade', %s, %s) "
                        "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()",
                        (json.dumps(p.como_dict()), "Regra inicial de criticidade (HU08): limites do índice em km"))
            cur.execute("INSERT INTO carga (arquivo, sha256, linhas) VALUES (%s,%s,%s)", (origem, "", len(s)))
    return {"localidades": len(ids), "linhas": int(len(s)), "limites": p.limites}


def main(argv=None) -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--teste", action="store_true", help="carrega no banco de teste")
    args = a.parse_args(argv)
    pq = V2 / "series_todas.parquet"
    series = pd.read_parquet(pq)
    meta = pd.read_csv(V2 / "metadados_series.csv")
    cal = pd.read_parquet(PIPELINE / "dados" / "tratado" / "calendario_diario.parquet")
    feriados = pd.DataFrame({"data": pd.to_datetime(cal.loc[cal.feriado == 1, "data"]).dt.date, "nome": "feriado"})
    r = carregar(database_url(args.teste), series, meta, feriados, origem=f"{pq.name} sha256={sha256(pq)[:16]}")
    print(r)


if __name__ == "__main__":
    main()
