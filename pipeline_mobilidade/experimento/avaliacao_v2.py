#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from experimento_previsao import naive, seasonal_naive

H = 24
QUANTIS = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
QCOLS = [f"q{q:g}" for q in QUANTIS]
PASSO_ORIGENS = pd.Timedelta(days=8)
INICIO_TESTE, FIM_TESTE = pd.Timestamp("2023-01-02"), pd.Timestamp("2023-12-29 23:00")
LIMIAR_PRINCIPAL, LIMIARES = 0.5, (0.25, 0.5, 0.75)
CHRONOS_MAX_CONTEXTO = 8192
MODELOS_PROB = ("Chronos-2", "Chronos-2 + covariáveis", "Chronos-2 + clima observado", "Chronos-2 (lacunas como NaN)",
                "AutoETS", "Mediana hora-semana")


def origens_teste(inicio=INICIO_TESTE, fim=FIM_TESTE, passo=PASSO_ORIGENS, horizonte=H) -> list[pd.Timestamp]:
    out, o = [], inicio
    while o + pd.Timedelta(hours=horizonte - 1) <= fim:
        out.append(o)
        o += passo
    return out


def mediana_hora_semana(hist: np.ndarray, horizonte: int = H, semanas: int = 8) -> tuple[np.ndarray, np.ndarray]:
    k = min(semanas, len(hist) // 168)
    if k == 0:
        v = np.full(horizonte, hist[-1])
        return v, np.tile(v[:, None], len(QUANTIS))
    amostra = np.stack([hist[len(hist) - 168 * j: len(hist) - 168 * j + horizonte] for j in range(1, k + 1)])
    return np.median(amostra, axis=0), np.quantile(amostra, QUANTIS, axis=0).T


def pinball(y: np.ndarray, qpred: np.ndarray, quantis=QUANTIS) -> np.ndarray:
    q = np.asarray(quantis)[None, :]
    e = y[:, None] - qpred
    return np.sum(np.maximum(q * e, (q - 1) * e), axis=1)


def wql(y: np.ndarray, qpred: np.ndarray, quantis=QUANTIS) -> float:
    den = np.sum(np.abs(y))
    return float(2 * pinball(y, qpred, quantis).sum() / (len(quantis) * den)) if den > 0 else float("nan")


def cobertura(y: np.ndarray, baixo: np.ndarray, alto: np.ndarray) -> float:
    return float(np.mean((y >= baixo) & (y <= alto)))


def dias_uteis_sem_registro(datas_serie: set, datas_cidade: set, inicio: pd.Timestamp, fim: pd.Timestamp,
                            feriados: set) -> list:
    dias = pd.date_range(inicio.normalize(), fim.normalize(), freq="D")
    return [d for d in dias if d.dayofweek < 5 and d not in feriados and d in datas_cidade and d not in datas_serie]


def dias_lacuna(datas_serie: set, datas_cidade: set, inicio: pd.Timestamp, fim: pd.Timestamp, feriados: set,
                janela: int = 20, freq_min: float = 0.9) -> list:
    uteis = [d for d in pd.date_range(inicio.normalize() - pd.Timedelta(days=3 * janela), fim.normalize(), freq="D")
             if d.dayofweek < 5 and d not in feriados and d in datas_cidade]
    out = []
    for i, d in enumerate(uteis):
        if d < inicio.normalize() or d in datas_serie or i < janela:
            continue
        anteriores = uteis[i - janela:i]
        if sum(x in datas_serie for x in anteriores) >= freq_min * janela:
            out.append(d)
    return out


def bootstrap_dois_niveis(d: np.ndarray, b: int = 2000, semente: int = 42) -> tuple[float, float, float]:
    rng = np.random.default_rng(semente)
    ns, nj = d.shape
    medias = np.empty(b)
    for i in range(b):
        si, ji = rng.integers(0, ns, ns), rng.integers(0, nj, nj)
        medias[i] = np.nanmean(d[np.ix_(si, ji)])
    return float(np.nanmean(d)), float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def diebold_mariano(d: np.ndarray, lag: int = 1) -> tuple[float, float]:
    from scipy import stats
    d = np.asarray(d, float)
    d = d[~np.isnan(d)]
    t = len(d)
    dc = d - d.mean()
    lrv = np.dot(dc, dc) / t
    for k in range(1, lag + 1):
        lrv += 2 * (1 - k / (lag + 1)) * np.dot(dc[k:], dc[:-k]) / t
    dm = d.mean() / np.sqrt(lrv / t)
    hln = np.sqrt((t + 1 - 2 * (lag + 1) + (lag + 1) * lag / t) / t)
    est = dm * hln
    return float(est), float(2 * stats.t.sf(abs(est), df=t - 1))


def holm(pvalores: dict[str, float]) -> dict[str, float]:
    itens = sorted(pvalores.items(), key=lambda kv: kv[1])
    m, ajust, acum = len(itens), {}, 0.0
    for i, (k, p) in enumerate(itens):
        acum = max(acum, min(1.0, (m - i) * p))
        ajust[k] = acum
    return ajust


def _ler_bruto() -> pd.DataFrame:
    from mobilidade.adapters.cet_csv import CetLentidaoCsv

    def arquivo(nome: str) -> Path:
        p = RAIZ / "dados" / "entrada" / nome
        copias = sorted((RAIZ / "dados" / "bruto" / "cet_lentidao_csv").glob(f"*_{nome}"))
        if p.exists() or not copias:
            return p
        return copias[-1]

    partes = [CetLentidaoCsv.ler(arquivo(f)) for f in ("lentidaotrechos2022.csv", "lentidao_trechos_2023.csv")]
    df = pd.concat(partes, ignore_index=True)
    df["ts"] = pd.to_datetime(df["data"], format="%d/%m/%Y %H:%M")
    df["series_id"] = df["corredor"].astype(str).str.strip() + " | " + df["sentido"].astype(str).str.strip()
    return df


def _feriados() -> set:
    cal = pd.read_parquet(RAIZ / "dados" / "tratado" / "calendario_diario.parquet")
    return set(pd.to_datetime(cal.loc[cal.feriado == 1, "data"]))


def preparar(saida: Path) -> None:
    from mobilidade.series import construir_series
    t0 = time.time()
    bruto = _ler_bruto()
    series, qual = construir_series(bruto, col_serie=["corredor", "sentido"], col_alvo="tamanho", col_ts="data",
                                    ausente_como_zero=True, freq_coleta="30min", fator=0.001)
    series.to_parquet(saida / "series_todas.parquet", index=False)

    feriados = _feriados()
    datas_cidade = set(bruto["ts"].dt.normalize())
    por_instante = bruto.groupby(["series_id", "ts"])["tamanho"].sum() / 1000
    uteis_2022 = [d for d in pd.date_range("2022-01-01", "2022-12-31") if d.dayofweek < 5]
    linhas = []
    for sid, g in bruto.groupby("series_id"):
        datas = set(g["ts"].dt.normalize())
        lac = dias_lacuna(datas, datas_cidade, INICIO_TESTE, FIM_TESTE, feriados)
        sem_registro = dias_uteis_sem_registro(datas, datas_cidade, INICIO_TESTE, FIM_TESTE, feriados)
        frac_e = (g["expressa"].astype(str).str.strip() == "E").mean()
        linhas.append({
            "series_id": sid, "corredor": g["corredor"].iloc[0].strip(), "sentido": g["sentido"].iloc[0].strip(),
            "regiao": g["nome_regiao"].mode().iloc[0], "tipo_via": "expressa" if frac_e >= 0.5 else "não expressa",
            "n_registros": len(g), "primeiro_registro": g["ts"].min(), "ultimo_registro": g["ts"].max(),
            "extensao_max_km": float(por_instante.loc[sid].max()),
            "frac_dias_uteis_2022": sum(d in datas for d in uteis_2022) / len(uteis_2022),
            "dias_uteis_sem_registro_2023": len(sem_registro),
            "dias_lacuna_2023": len(lac), "datas_lacuna_2023": ";".join(d.strftime("%Y-%m-%d") for d in lac),
        })
    meta = pd.DataFrame(linhas).sort_values("frac_dias_uteis_2022", ascending=False)
    for lim in LIMIARES:
        meta[f"sel_{lim:g}"] = meta["frac_dias_uteis_2022"] >= lim
    meta.to_csv(saida / "metadados_series.csv", index=False)
    resumo = {"n_combinacoes_corredor_sentido": int(len(meta)), "registros_brutos": int(len(bruto)),
              **{f"series_limiar_{lim:g}": int(meta[f"sel_{lim:g}"].sum()) for lim in LIMIARES},
              "qualidade": qual, "tempo_s": round(time.time() - t0, 1)}
    (saida / "preparo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "qualidade"}, indent=2, ensure_ascii=False))


def _carregar(saida: Path, limiar: float):
    meta = pd.read_csv(saida / "metadados_series.csv")
    ids = meta.loc[meta["frac_dias_uteis_2022"] >= limiar, "series_id"].tolist()
    s = pd.read_parquet(saida / "series_todas.parquet")
    s = s[s.series_id.isin(ids)]
    larga = s.pivot(index="timestamp", columns="series_id", values="target").sort_index()
    larga = larga.reindex(pd.date_range(larga.index.min(), larga.index.max(), freq="h"))
    return meta.set_index("series_id"), larga[ids]


def _covariaveis(indice: pd.DatetimeIndex) -> pd.DataFrame:
    cal = pd.read_parquet(RAIZ / "dados" / "tratado" / "calendario_diario.parquet")
    cal["data"] = pd.to_datetime(cal["data"])
    clima = pd.read_parquet(RAIZ / "dados" / "tratado" / "clima_horario.parquet")
    clima["timestamp"] = pd.to_datetime(clima["timestamp"])
    cov = pd.DataFrame({"timestamp": indice, "data": indice.normalize()})
    cov = cov.merge(cal[["data", "feriado", "fim_de_semana"]], on="data", how="left").drop(columns="data")
    cov = cov.merge(clima, on="timestamp", how="left")
    return cov.set_index("timestamp").astype(float).ffill().fillna(0.0)


def _linhas(sid, o, y, yhat, qpred=None):
    ts = pd.date_range(o, periods=H, freq="h")
    d = {"series_id": sid, "origem": o, "passo": np.arange(1, H + 1), "timestamp": ts, "y": y,
         "yhat": np.clip(yhat, 0, None)}
    if qpred is not None:
        qp = np.clip(np.sort(qpred, axis=1), 0, None)
        for j, c in enumerate(QCOLS):
            d[c] = qp[:, j]
    return pd.DataFrame(d)


def _historico(larga: pd.DataFrame, sid: str, o: pd.Timestamp) -> np.ndarray:
    h = larga[sid].loc[: o - pd.Timedelta(hours=1)].to_numpy()
    return h[~np.isnan(h)] if np.isnan(h[0]) else h


def rodar_baselines(larga, origens) -> pd.DataFrame:
    partes = []
    for o in origens:
        for sid in larga.columns:
            hist = _historico(larga, sid, o)
            y = larga[sid].loc[o: o + pd.Timedelta(hours=H - 1)].to_numpy()
            med, qmed = mediana_hora_semana(hist)
            for nome, prev, q in [("Ingênuo", naive(hist, H), None), ("Sazonal diário", seasonal_naive(hist, H, 24), None),
                                  ("Sazonal semanal", seasonal_naive(hist, H, 168), None),
                                  ("Zero", np.zeros(H), np.zeros((H, len(QUANTIS)))), ("Mediana hora-semana", med, qmed)]:
                partes.append(_linhas(sid, o, y, prev, q).assign(modelo=nome))
    return pd.concat(partes, ignore_index=True)


def rodar_ets(larga, origens, janela_h: int = 28 * 24) -> pd.DataFrame:
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS, SeasonalNaive
    niveis = [20, 40, 60, 80, 90]
    mapa = {0.05: "lo-90", 0.1: "lo-80", 0.2: "lo-60", 0.3: "lo-40", 0.4: "lo-20", 0.5: None,
            0.6: "hi-20", 0.7: "hi-40", 0.8: "hi-60", 0.9: "hi-80", 0.95: "hi-90"}
    partes = []
    for i, o in enumerate(origens):
        ctx = larga.loc[o - pd.Timedelta(hours=janela_h): o - pd.Timedelta(hours=1)]
        df = ctx.reset_index().melt(id_vars="index", var_name="unique_id", value_name="y").rename(columns={"index": "ds"})
        df = df.dropna()
        sf = StatsForecast(models=[AutoETS(season_length=24)], freq="h", n_jobs=-1,
                           fallback_model=SeasonalNaive(season_length=24))
        fc = sf.forecast(df=df, h=H, level=niveis)
        for sid, g in fc.groupby("unique_id"):
            g = g.sort_values("ds")
            qpred = np.column_stack([g["AutoETS"] if c is None else g[f"AutoETS-{c}"] for c in mapa.values()])
            y = larga[sid].loc[o: o + pd.Timedelta(hours=H - 1)].to_numpy()
            partes.append(_linhas(sid, o, y, g["AutoETS"].to_numpy(), qpred).assign(modelo="AutoETS"))
        print(f"[ets] origem {i + 1}/{len(origens)}", flush=True)
    return pd.concat(partes, ignore_index=True)


def _matriz_lgbm(larga: pd.DataFrame) -> pd.DataFrame:
    cov = _covariaveis(larga.index)
    longo = larga.rename_axis("timestamp").reset_index().melt(id_vars="timestamp", var_name="series_id", value_name="y")
    longo = longo.sort_values(["series_id", "timestamp"]).reset_index(drop=True)
    g = longo.groupby("series_id")["y"]
    for k in (24, 48, 72, 96, 120, 144, 168, 336):
        longo[f"lag{k}"] = g.shift(k)
    longo["media_mesma_hora_7d"] = longo[[f"lag{k}" for k in (24, 48, 72, 96, 120, 144, 168)]].mean(axis=1)
    longo["hora"] = longo["timestamp"].dt.hour
    longo["dia_semana"] = longo["timestamp"].dt.day_of_week
    longo = longo.merge(cov[["feriado"]], left_on="timestamp", right_index=True, how="left")
    longo["serie"] = longo["series_id"].astype("category")
    return longo


def rodar_lgbm(larga, origens) -> pd.DataFrame:
    import lightgbm as lgb
    m = _matriz_lgbm(larga)
    feats = [c for c in m.columns if c.startswith("lag")] + ["media_mesma_hora_7d", "hora", "dia_semana", "feriado", "serie"]
    partes = []
    for i, o in enumerate(origens):
        treino = m[(m.timestamp < o) & (m.timestamp >= o - pd.Timedelta(days=365))].dropna(subset=["y", "lag336"])
        modelo = lgb.LGBMRegressor(objective="l1", n_estimators=400, learning_rate=0.05, num_leaves=63,
                                   min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                                   random_state=42, verbose=-1, n_jobs=-1)
        modelo.fit(treino[feats], treino["y"])
        teste = m[(m.timestamp >= o) & (m.timestamp < o + pd.Timedelta(hours=H))]
        teste = teste.assign(yhat=modelo.predict(teste[feats]))
        for sid, g in teste.groupby("series_id", observed=True):
            g = g.sort_values("timestamp")
            partes.append(_linhas(sid, o, g["y"].to_numpy(), g["yhat"].to_numpy()).assign(modelo="LightGBM"))
        print(f"[lgbm] origem {i + 1}/{len(origens)} ({len(treino):,} linhas de treino)", flush=True)
    return pd.concat(partes, ignore_index=True)


def rodar_chronos(larga, origens, variante: str, meta: pd.DataFrame, device: str = "cpu",
                  parciais: Path | None = None) -> pd.DataFrame:
    from chronos import Chronos2Pipeline
    pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=device)
    if parciais is not None:
        parciais.mkdir(parents=True, exist_ok=True)
    nome = {"univariado": "Chronos-2", "covariaveis": "Chronos-2 + covariáveis",
            "oraculo": "Chronos-2 + clima observado", "nan": "Chronos-2 (lacunas como NaN)"}[variante]
    cov = _covariaveis(larga.index) if variante in ("covariaveis", "oraculo") else None
    larga_ctx = larga.copy()
    if variante == "nan":
        for sid in larga.columns:
            datas = meta.loc[sid, "datas_lacuna_2023"]
            for d in (datas.split(";") if isinstance(datas, str) and datas else []):
                larga_ctx.loc[pd.Timestamp(d): pd.Timestamp(d) + pd.Timedelta(hours=23), sid] = np.nan
    partes = []
    for i, o in enumerate(origens):
        t0 = time.time()
        arq = parciais / f"{variante}_{o:%Y%m%d}.parquet" if parciais is not None else None
        if arq is not None and arq.exists():
            partes.append(pd.read_parquet(arq))
            print(f"[chronos-{variante}] origem {i + 1}/{len(origens)} (retomada do parcial)", flush=True)
            continue
        ctx_frames, fut_frames = [], []
        for sid in larga.columns:
            serie = larga_ctx[sid].loc[: o - pd.Timedelta(hours=1)]
            serie = serie.loc[larga[sid].first_valid_index():].iloc[-CHRONOS_MAX_CONTEXTO:]
            f = pd.DataFrame({"id": sid, "timestamp": serie.index, "target": serie.to_numpy()})
            if cov is not None:
                f = f.join(cov, on="timestamp")
                fut_ts = pd.date_range(o, periods=H, freq="h")
                colunas = ["feriado", "fim_de_semana"] + (["temperatura_c", "precipitacao_mm"] if variante == "oraculo" else [])
                fut_frames.append(pd.DataFrame({"id": sid, "timestamp": fut_ts}).join(cov[colunas], on="timestamp"))
            ctx_frames.append(f)
        pred = pipe.predict_df(pd.concat(ctx_frames, ignore_index=True),
                               future_df=pd.concat(fut_frames, ignore_index=True) if fut_frames else None,
                               prediction_length=H, quantile_levels=QUANTIS, id_column="id",
                               timestamp_column="timestamp", target="target")
        da_origem = []
        for sid, g in pred.groupby("id", sort=False):
            g = g.sort_values("timestamp")
            y = larga[sid].loc[o: o + pd.Timedelta(hours=H - 1)].to_numpy()
            qpred = g[[f"{q:g}" if f"{q:g}" in g.columns else str(q) for q in QUANTIS]].to_numpy(float)
            da_origem.append(_linhas(sid, o, y, g["0.5"].to_numpy(float), qpred).assign(modelo=nome))
        da_origem = pd.concat(da_origem, ignore_index=True)
        if arq is not None:
            da_origem.to_parquet(arq, index=False)
        partes.append(da_origem)
        print(f"[chronos-{variante}] origem {i + 1}/{len(origens)} ({time.time() - t0:.1f} s)", flush=True)
    return pd.concat(partes, ignore_index=True)


def rodar(saida: Path, familias: list[str], limiar_chronos_extra: float, device: str) -> None:
    meta, larga = _carregar(saida, min(LIMIARES))
    _, larga_principal = _carregar(saida, limiar_chronos_extra)
    origens = origens_teste()
    print(f"{larga.shape[1]} séries (limiar {min(LIMIARES):g}); {larga_principal.shape[1]} no limiar "
          f"{limiar_chronos_extra:g}; {len(origens)} origens ({origens[0].date()} a {origens[-1].date()})")
    for fam in familias:
        t0 = time.time()
        if fam == "baselines":
            df = rodar_baselines(larga, origens)
        elif fam == "ets":
            df = rodar_ets(larga, origens)
        elif fam == "lgbm":
            df = rodar_lgbm(larga, origens)
        elif fam == "chronos":
            df = rodar_chronos(larga, origens, "univariado", meta, device, saida / "parciais")
        elif fam in ("chronos_cov", "chronos_oraculo", "chronos_nan"):
            df = rodar_chronos(larga_principal, origens, {"chronos_cov": "covariaveis", "chronos_oraculo": "oraculo",
                                                          "chronos_nan": "nan"}[fam], meta, device, saida / "parciais")
        else:
            raise SystemExit(f"família desconhecida: {fam}")
        df.to_parquet(saida / f"previsoes_{fam}.parquet", index=False)
        print(f"[{fam}] {len(df):,} linhas em {time.time() - t0:.0f} s")


def _escalas(larga: pd.DataFrame, origens) -> pd.DataFrame:
    linhas = []
    for sid in larga.columns:
        s = larga[sid].dropna()
        v, idx = s.to_numpy(), s.index
        cs = np.concatenate([[0], np.cumsum(v)])
        dif = np.abs(v[24:] - v[:-24])
        csd = np.concatenate([[0], np.cumsum(dif)])
        for o in origens:
            n = int(idx.searchsorted(o))
            linhas.append({"series_id": sid, "origem": o, "media_treino": cs[n] / n if n else np.nan,
                           "escala_mase": csd[n - 24] / (n - 24) if n > 24 else np.nan})
    return pd.DataFrame(linhas)


def _metricas_janela(prev: pd.DataFrame, lacunas: set) -> pd.DataFrame:
    prev = prev.copy()
    prev["erro"] = (prev["y"] - prev["yhat"]).abs()
    positivo = prev["y"] > 0
    chaves = pd.MultiIndex.from_arrays([prev["series_id"], prev["timestamp"].dt.normalize()])
    lacuna = chaves.isin(pd.MultiIndex.from_tuples(list(lacunas))) if lacunas else np.zeros(len(prev), bool)
    prev["n_pos"] = positivo.astype(int)
    prev["erro_pos"] = prev["erro"].where(positivo, 0.0)
    prev["n_sem_lacuna"] = (~lacuna).astype(int)
    prev["erro_sem_lacuna"] = prev["erro"].where(~lacuna, 0.0)
    prev["vies"] = prev["yhat"] - prev["y"]
    tem_q = all(c in prev.columns for c in QCOLS) and prev[QCOLS[0]].notna().any()
    agg = {"MAE": ("erro", "mean"), "soma_y": ("y", "sum"), "n": ("erro", "size"),
           "soma_erro_pos": ("erro_pos", "sum"), "n_pos": ("n_pos", "sum"),
           "soma_erro_sem_lacuna": ("erro_sem_lacuna", "sum"), "n_sem_lacuna": ("n_sem_lacuna", "sum"),
           "soma_vies": ("vies", "sum")}
    if tem_q:
        com_q = prev[QCOLS[0]].notna()
        prev["pinball"] = np.where(com_q, pinball(prev["y"].to_numpy(), prev[QCOLS].fillna(0).to_numpy()), np.nan)
        prev["cob80"] = ((prev["y"] >= prev["q0.1"]) & (prev["y"] <= prev["q0.9"])).astype(float).where(com_q)
        prev["cob90"] = ((prev["y"] >= prev["q0.05"]) & (prev["y"] <= prev["q0.95"])).astype(float).where(com_q)
        agg.update({"soma_pinball": ("pinball", lambda s: s.sum(min_count=1)),
                    "cob80": ("cob80", "mean"), "cob90": ("cob90", "mean")})
    return prev.groupby(["modelo", "series_id", "origem"]).agg(**agg).reset_index()


def avaliar(saida: Path, b: int) -> None:
    meta, larga = _carregar(saida, min(LIMIARES))
    origens = origens_teste()
    lacunas = {(sid, pd.Timestamp(d)) for sid, ds in meta["datas_lacuna_2023"].dropna().items() for d in ds.split(";") if d}
    arquivos = sorted(saida.glob("previsoes_*.parquet"))
    janelas = pd.concat([_metricas_janela(pd.read_parquet(a), lacunas) for a in arquivos], ignore_index=True)
    janelas = janelas.merge(_escalas(larga, origens), on=["series_id", "origem"], how="left")
    janelas["nMAE"] = janelas["MAE"] / janelas["media_treino"]
    janelas["MASE"] = janelas["MAE"] / janelas["escala_mase"]
    janelas.to_csv(saida / "metricas_por_janela.csv", index=False)

    resultado = {"executado_em": datetime.now().isoformat(timespec="seconds"), "n_origens": len(origens),
                 "origens": [str(o.date()) for o in origens], "arquivos": [a.name for a in arquivos], "conjuntos": {}}
    for lim in LIMIARES:
        ids = meta.index[meta["frac_dias_uteis_2022"] >= lim].tolist()
        resultado["conjuntos"][f"{lim:g}"] = _resumir(janelas[janelas.series_id.isin(ids)], meta.loc[ids], saida, lim, b,
                                                      principal=(lim == LIMIAR_PRINCIPAL))
    resultado["ambiente"] = {"python": platform.python_version(),
                             **{p: importlib.metadata.version(p) for p in ("pandas", "numpy", "chronos-forecasting",
                                                                           "torch", "statsforecast", "lightgbm", "scipy")}}
    (saida / "resultado_v2.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=float),
                                             encoding="utf-8")
    p = resultado["conjuntos"][f"{LIMIAR_PRINCIPAL:g}"]
    print(pd.DataFrame(p["modelos"]).T.round(3).to_string())
    print(json.dumps(p["testes"], indent=2, ensure_ascii=False))


def _resumir(jan: pd.DataFrame, meta: pd.DataFrame, saida: Path, lim: float, b: int, principal: bool) -> dict:
    completos = [m for m, g in jan.groupby("modelo") if g.series_id.nunique() == meta.shape[0]]
    jan = jan[jan.modelo.isin(completos)]
    por_serie = jan.groupby(["modelo", "series_id"]).agg(MAE=("MAE", "mean"), nMAE=("nMAE", "mean"),
                                                         MASE=("MASE", "mean")).reset_index()
    modelos = {}
    for m, g in jan.groupby("modelo"):
        ps = por_serie[por_serie.modelo == m]
        d = {"MAE_medio": ps.MAE.mean(), "MAE_mediano": ps.MAE.median(), "nMAE_medio": ps.nMAE.mean(),
             "MASE_medio": ps.MASE.mean(), "MASE_mediano": ps.MASE.median(),
             "MAE_horas_com_lentidao": g.soma_erro_pos.sum() / g.n_pos.sum(),
             "MAE_sem_lacunas": g.soma_erro_sem_lacuna.sum() / g.n_sem_lacuna.sum(),
             "MAE_global_horas": (g.MAE * g.n).sum() / g.n.sum(), "vies_medio": g.soma_vies.sum() / g.n.sum()}
        if "soma_pinball" in g and g.soma_pinball.notna().any():
            d.update({"WQL": 2 * g.soma_pinball.sum() / (len(QUANTIS) * g.soma_y.sum()),
                      "cobertura80": (g.cob80 * g.n).sum() / g.n.sum(), "cobertura90": (g.cob90 * g.n).sum() / g.n.sum()})
        modelos[m] = d
    mae = por_serie.pivot(index="series_id", columns="modelo", values="MAE")
    nmae = por_serie.pivot(index="series_id", columns="modelo", values="nMAE")
    for m in modelos:
        modelos[m]["series_menor_MAE"] = int((mae.idxmin(axis=1) == m).sum())
    empates = int((mae.nunique(axis=1) == 1).sum())

    out = {"limiar": lim, "n_series": int(meta.shape[0]), "modelos": modelos, "empates_todos_iguais": empates}
    alvo = "Chronos-2"
    if alvo not in mae.columns:
        return out
    nao_chronos = [m for m in mae.columns if not m.startswith("Chronos")]
    melhor_ref = min(nao_chronos, key=lambda m: modelos[m]["MAE_medio"])
    comparacoes = {"Sazonal semanal": "Sazonal semanal", "melhor_referencia": melhor_ref}
    for extra in ("Chronos-2 + covariáveis", "Chronos-2 + clima observado"):
        if extra in mae.columns:
            comparacoes[extra] = extra
    testes, p_w, p_dm = {}, {}, {}
    from scipy import stats
    matriz = jan.pivot_table(index=["series_id", "origem"], columns="modelo", values="MAE")
    matriz_n = jan.pivot_table(index=["series_id", "origem"], columns="modelo", values="nMAE")
    for rotulo, ref in comparacoes.items():
        a, r = (alvo, ref) if not ref.startswith("Chronos") else (ref, alvo)
        dif_serie = (mae[a] - mae[r]).dropna()
        w = stats.wilcoxon(dif_serie, zero_method="pratt")
        d_mat = (matriz[a] - matriz[r]).unstack("origem").to_numpy()
        dn_mat = (matriz_n[a] - matriz_n[r]).unstack("origem").to_numpy()
        dm, pdm = diebold_mariano(np.nanmean(d_mat, axis=0))
        media, lo, hi = bootstrap_dois_niveis(d_mat, b)
        mn, lon, hin = bootstrap_dois_niveis(dn_mat, b)
        testes[rotulo] = {"comparacao": f"{a} − {r}", "dif_MAE": media, "IC95_MAE": [lo, hi], "dif_nMAE": mn,
                          "IC95_nMAE": [lon, hin], "wilcoxon_W": float(w.statistic), "wilcoxon_p": float(w.pvalue),
                          "DM": dm, "DM_p": pdm, "series_a_melhor": int((dif_serie < 0).sum()),
                          "series_r_melhor": int((dif_serie > 0).sum()), "empates": int((dif_serie == 0).sum())}
        p_w[rotulo], p_dm[rotulo] = float(w.pvalue), pdm
    for k, v in holm(p_w).items():
        testes[k]["wilcoxon_p_holm"] = v
    for k, v in holm(p_dm).items():
        testes[k]["DM_p_holm"] = v
    out["testes"] = testes

    ganho = (mae["Sazonal semanal"] - mae[alvo]).sort_values(ascending=False)
    total = ganho.sum()
    out["concentracao_ganho"] = {"ganho_total_km": float(total),
                                 "fracao_top5": float(ganho.head(5).sum() / total) if total else None,
                                 "fracao_top10": float(ganho.head(10).sum() / total) if total else None,
                                 "spearman_ganho_vs_volume": float(stats.spearmanr(
                                     ganho, meta.loc[ganho.index, "extensao_max_km"]).statistic)}
    porte = pd.qcut(meta.loc[mae.index, "extensao_max_km"], 3, labels=["menor", "médio", "maior"])
    out["por_porte"] = {str(k): {"n": int((porte == k).sum()), "MAE_alvo": float(mae.loc[porte == k, alvo].mean()),
                                 "MAE_ref": float(mae.loc[porte == k, melhor_ref].mean()),
                                 "alvo_melhor": int((mae.loc[porte == k, alvo] < mae.loc[porte == k, melhor_ref]).sum())}
                        for k in porte.cat.categories}
    out["melhor_referencia"] = melhor_ref
    out["mase_sazonal_diario_no_teste"] = modelos["Sazonal diário"]["MASE_medio"]
    lac = meta["dias_lacuna_2023"]
    out["lacunas"] = {"corredores_com_lacuna": int((lac > 0).sum()), "dias_lacuna_total": int(lac.sum()),
                      "horas_lacuna_em_teste": int(jan[jan.modelo == alvo].eval("n - n_sem_lacuna").sum())}
    if principal:
        _tabelas_figuras(jan, por_serie, mae, nmae, meta, modelos, saida, alvo)
    return out


def _tabelas_figuras(jan, por_serie, mae, nmae, meta, modelos, saida: Path, alvo: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tab = meta[["corredor", "sentido", "regiao", "tipo_via", "extensao_max_km", "dias_lacuna_2023"]].copy()
    tab["MAE_Chronos2"] = mae[alvo]
    tab["MAE_semanal"] = mae["Sazonal semanal"]
    melhor = min([m for m in mae.columns if not m.startswith("Chronos")], key=lambda m: modelos[m]["MAE_medio"])
    tab["MAE_melhor_referencia"] = mae[melhor]
    tab["ganho_vs_semanal_pct"] = 100 * (1 - mae[alvo] / mae["Sazonal semanal"])
    tab["nMAE_Chronos2"] = nmae[alvo]
    tab.sort_values("extensao_max_km", ascending=False).to_csv(saida / "tabela_corredores.csv")
    reg = tab.groupby(["regiao", "tipo_via"]).agg(n=("corredor", "size"), MAE_C2=("MAE_Chronos2", "mean"),
                                                  MAE_sem=("MAE_semanal", "mean"),
                                                  ganho_mediano_pct=("ganho_vs_semanal_pct", "median"))
    reg.to_csv(saida / "quadro_regiao_tipo.csv")
    por_serie.to_csv(saida / "metricas_por_serie.csv", index=False)

    tinta, grade = "#52514e", "#e4e3df"
    refs = ["Sazonal semanal", melhor, "Mediana hora-semana"]
    refs = list(dict.fromkeys(r for r in refs if r in nmae.columns))
    fig, ax = plt.subplots(figsize=(7, 3.6))
    dados = [(1 - mae[alvo] / mae[r]).replace([np.inf, -np.inf], np.nan).dropna() * 100 for r in refs]
    ax.boxplot(dados, vert=False, tick_labels=[f"vs {r}" for r in refs], showmeans=True, widths=0.5,
               medianprops={"color": "#2a78d6", "lw": 2}, meanprops={"marker": "D", "markerfacecolor": "#eb6834",
                                                                     "markeredgecolor": "#eb6834", "ms": 5})
    for i, d in enumerate(dados, start=1):
        ax.scatter(d, np.random.default_rng(i).normal(i, 0.05, len(d)), s=9, color="#0b0b0b", alpha=0.45, zorder=3)
    ax.axvline(0, color=tinta, lw=0.8, ls="--")
    ax.set_xlabel("Redução do MAE do Chronos-2 por série (%)")
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="x", color=grade, lw=0.6)
    fig.tight_layout()
    fig.savefig(saida / "fig_ganho_por_serie.png", dpi=300)
    plt.close(fig)

    arquivos = sorted(saida.glob("previsoes_*.parquet"))
    p = pd.concat([pd.read_parquet(a, columns=["modelo", "series_id", "timestamp", "y", "yhat"]) for a in arquivos])
    p = p[p.series_id.isin(meta.index) & p.modelo.isin([alvo, "Sazonal semanal", melhor, "Chronos-2 + covariáveis"])]
    p["erro"] = (p.y - p.yhat).abs()
    hora = p.groupby(["modelo", p.timestamp.dt.hour]).erro.mean().unstack(0)
    estilos = {alvo: ("#2a78d6", "-"), "Sazonal semanal": ("#1baf7a", ":"), melhor: ("#eb6834", "--"),
               "Chronos-2 + covariáveis": ("#6250d6", "-.")}
    fig, ax = plt.subplots(figsize=(7, 3.2))
    for m in hora.columns:
        cor, ls = estilos.get(m, ("#52514e", "-"))
        ax.plot(hora.index, hora[m], color=cor, ls=ls, lw=1.8, marker="o", ms=3, label=m)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("Hora do dia")
    ax.set_ylabel("MAE (km)")
    ax.legend(frameon=False, fontsize=8)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", color=grade, lw=0.6)
    fig.tight_layout()
    fig.savefig(saida / "fig_mae_por_hora.png", dpi=300)
    plt.close(fig)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("etapa", choices=["preparar", "rodar", "avaliar"])
    p.add_argument("--saida", default=str(RAIZ / "resultados" / "v2"))
    p.add_argument("--modelos", nargs="+", default=["baselines", "ets", "lgbm", "chronos", "chronos_cov",
                                                    "chronos_oraculo", "chronos_nan"])
    p.add_argument("--device", default="cpu")
    p.add_argument("--bootstrap", type=int, default=2000)
    a = p.parse_args(argv)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    if a.etapa == "preparar":
        preparar(saida)
    elif a.etapa == "rodar":
        rodar(saida, a.modelos, LIMIAR_PRINCIPAL, a.device)
    else:
        avaliar(saida, a.bootstrap)


if __name__ == "__main__":
    main()
