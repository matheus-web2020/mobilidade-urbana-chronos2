from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel

from .config import APP, database_url
from .criticidade import ParametrosCriticidade, classificar

app = FastAPI(title="Mobilidade SP – MVP", version="1.0",
              description="Consulta de lentidão por corredor e período e classificação inicial de criticidade.")
MAX_DIAS_CONSULTA = 366


def conexao():
    try:
        con = psycopg.connect(app.state.database_url if hasattr(app.state, "database_url") else database_url(),
                              row_factory=dict_row)
    except psycopg.OperationalError as e:
        raise HTTPException(503, "Consulta temporariamente indisponível (banco de dados inacessível).") from e
    try:
        yield con
    finally:
        con.close()


def _periodo(con, inicio: date, fim: date) -> None:
    if inicio > fim:
        raise HTTPException(422, "Período inválido: a data inicial é posterior à final.")
    if (fim - inicio).days + 1 > MAX_DIAS_CONSULTA:
        raise HTTPException(422, f"Período inválido: o máximo é {MAX_DIAS_CONSULTA} dias.")
    lim = con.execute("SELECT MIN(instante)::date AS ini, MAX(instante)::date AS fim FROM serie_horaria").fetchone()
    if lim["ini"] is None or fim < lim["ini"] or inicio > lim["fim"]:
        raise HTTPException(404, f"Não há dados para o período. Dados disponíveis de {lim['ini']} a {lim['fim']}.")


def _parametros(con) -> ParametrosCriticidade:
    r = con.execute("SELECT valor FROM parametro_sistema WHERE chave = 'criticidade'").fetchone()
    if not r:
        raise HTTPException(404, "Ainda não existem parâmetros de criticidade (rode a carga do banco).")
    return ParametrosCriticidade.de_dict(r["valor"])


@app.get("/api/v1/saude")
def saude(con=Depends(conexao)):
    r = con.execute("SELECT COUNT(*) AS localidades, (SELECT MIN(instante) FROM serie_horaria) AS inicio, "
                    "(SELECT MAX(instante) FROM serie_horaria) AS fim FROM localidade").fetchone()
    return {"status": "ok", **r}


@app.get("/api/v1/localidades")
def localidades(regiao: str | None = None, con=Depends(conexao)):
    sql = "SELECT id, corredor, sentido, regiao, tipo_via, extensao_max_km FROM localidade"
    args = []
    if regiao:
        sql += " WHERE regiao = %s"
        args.append(regiao.upper())
    return con.execute(sql + " ORDER BY corredor, sentido", args).fetchall()


@app.get("/api/v1/regioes")
def regioes(con=Depends(conexao)):
    return [r["regiao"] for r in con.execute("SELECT DISTINCT regiao FROM localidade ORDER BY 1").fetchall()]


@app.get("/api/v1/consulta")
def consulta(localidade_id: int, inicio: date, fim: date,
             agregacao: Literal["hora", "dia"] = "hora", con=Depends(conexao)):
    _periodo(con, inicio, fim)
    loc = con.execute("SELECT id, corredor, sentido, regiao, tipo_via FROM localidade WHERE id = %s",
                      (localidade_id,)).fetchone()
    if not loc:
        raise HTTPException(422, "Localidade inválida.")
    passo = "hour" if agregacao == "hora" else "day"
    pontos = con.execute(
        f"SELECT date_trunc('{passo}', instante) AS instante, AVG(km_lentidao)::float AS km_lentidao, "
        "MAX(km_lentidao)::float AS km_max FROM serie_horaria WHERE localidade_id = %s AND instante >= %s "
        "AND instante < %s GROUP BY 1 ORDER BY 1", (localidade_id, inicio, fim + timedelta(days=1))).fetchall()
    if not pontos:
        raise HTTPException(404, "Não existem dados disponíveis para a localidade e o período selecionados.")
    valores = [p["km_lentidao"] for p in pontos]
    resumo = {"km_medio": sum(valores) / len(valores), "km_maximo": max(p["km_max"] for p in pontos),
              "pontos": len(pontos), "pontos_com_lentidao": sum(v > 0 for v in valores)}
    return {"localidade": loc, "inicio": inicio, "fim": fim, "agregacao": agregacao, "resumo": resumo,
            "serie": pontos}


@app.get("/api/v1/criticidade")
def criticidade(inicio: date, fim: date, regiao: str | None = None,
                ordem: Literal["indice", "nome"] = "indice", con=Depends(conexao)):
    _periodo(con, inicio, fim)
    p = _parametros(con)
    sql = ("SELECT l.id, l.corredor, l.sentido, l.regiao, l.tipo_via, AVG(s.km_lentidao)::float AS indice, "
           "COUNT(*) AS horas, COUNT(*) FILTER (WHERE s.km_lentidao > 0) AS horas_com_lentidao "
           "FROM serie_horaria s JOIN localidade l ON l.id = s.localidade_id "
           "WHERE s.instante >= %s AND s.instante < %s AND EXTRACT(ISODOW FROM s.instante) < 6 "
           "AND EXTRACT(HOUR FROM s.instante) >= %s AND EXTRACT(HOUR FROM s.instante) < %s "
           "AND s.instante::date NOT IN (SELECT data FROM feriado)")
    args: list = [inicio, fim + timedelta(days=1), p.hora_inicio, p.hora_fim]
    if regiao:
        sql += " AND l.regiao = %s"
        args.append(regiao.upper())
    linhas = con.execute(sql + " GROUP BY l.id", args).fetchall()
    if not linhas:
        raise HTTPException(404, "Não existem resultados de criticidade para os critérios selecionados "
                                 "(o período tem apenas fins de semana ou feriados?).")
    itens = classificar(linhas, p, ordem)
    contagem = {n: sum(1 for r in itens if r["nivel"] == n) for n in ("baixo", "moderado", "alto", "crítico")}
    l1, l2, l3 = (f"{x:g}".replace(".", ",") for x in p.limites)
    return {"inicio": inicio, "fim": fim, "regiao": regiao, "parametros": p.como_dict(),
            "regra": (f"Índice = km médios em lentidão de {p.hora_inicio}h a {p.hora_fim}h nos dias úteis do período. "
                      f"Níveis: baixo < {l1} ≤ moderado < {l2} ≤ alto < {l3} ≤ crítico (km)."),
            "contagem_por_nivel": contagem, "itens": itens}


class NovosParametros(BaseModel):
    limites: list[float]
    hora_inicio: int = 7
    hora_fim: int = 20


@app.get("/api/v1/parametros/criticidade")
def ler_parametros(con=Depends(conexao)):
    return _parametros(con).como_dict()


@app.put("/api/v1/parametros/criticidade")
def alterar_parametros(novos: NovosParametros, con=Depends(conexao)):
    if len(novos.limites) != 3:
        raise HTTPException(422, "Informe exatamente três limites.")
    try:
        p = ParametrosCriticidade(tuple(novos.limites), novos.hora_inicio, novos.hora_fim, "definido pelo administrador")
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    con.execute("UPDATE parametro_sistema SET valor = %s, atualizado_em = now() WHERE chave = 'criticidade'",
                (json.dumps(p.como_dict()),))
    con.commit()
    return p.como_dict()


_DIST = APP / "web" / "dist"
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")


@app.get("/{caminho:path}", include_in_schema=False)
def spa(caminho: str):
    if caminho.startswith("api/"):
        raise HTTPException(404, "Rota da API não encontrada.")
    if not (_DIST / "index.html").exists():
        raise HTTPException(404, "Interface não encontrada: rode npm install e npm run build em app/web.")
    return FileResponse(_DIST / "index.html")
