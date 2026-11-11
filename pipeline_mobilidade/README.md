# Pipeline de dados e avaliação – Mobilidade Urbana SP (TCC)

Ingestão → bruto (cópia fiel + manifesto) → validação → séries horárias (+ clima e calendário) → avaliação da previsão.

```
fontes externas ──► mobilidade/adapters/ ──► dados/bruto/<fonte>/   (arquivo original + .meta.json: sha256, data, origem)
                                               │
                                               ├─► mobilidade/validacao.py   (relatório de qualidade)
                                               └─► mobilidade/series.py      (séries horárias por corredor e sentido)
                                                          │
                              experimento/avaliacao_v2.py ──► resultados/v2/   (previsões, métricas, testes, figuras)
```

## Fontes

| Fonte | Adaptador | Estado | Observações |
|---|---|---|---|
| CET – lentidão por trechos (CSV anual, Portal de Dados Abertos) | `cet_csv.py` | **em uso** (2022: 155.301 registros; 2023: 158.496) | coleta a cada 30 min; colunas `data`, `corredor`, `sentido`, `expressa`, `descricao`, `tamanho` (m em lentidão), `nome_regiao`. Base de **eventos**: só registra trecho com fila. Descontinuada em 31/12/2023 (de 2024 em diante, a CET usa dados do Waze, sem histórico público comparável) |
| Clima – Open-Meteo | `openmeteo.py` | **em uso** (17.520 horas, 2022–2023) | temperatura e precipitação, covariáveis do Chronos-2 |
| Calendário – BrasilAPI | `calendario.py` | **em uso** (32 feriados, 2022–2023) | feriados nacionais; 25/01, 09/07 e 20/11 acrescentados à mão |
| CET LentidaoTransito v1 (API Store) | `cet_api.py` | só simulação | anos 2001–2018; exige token; não usada |
| Infosiga-SP | `infosiga.py` | só simulação | não usada na previsão |

Downloads da CET (pelo navegador; o portal bloqueia acesso automatizado), em `dados/entrada/`:
[lentidao_trechos_2023.csv](https://dados.prefeitura.sp.gov.br/dataset/f03433f4-0d4b-44b4-a23b-17111bbb392a/resource/b183971e-0f64-42ec-ac3c-f4ec99f2711c/download/lentidao_trechos_2023.csv) ·
[lentidaotrechos2022.csv](https://dados.prefeitura.sp.gov.br/dataset/f03433f4-0d4b-44b4-a23b-17111bbb392a/resource/81edda3d-7313-4690-add8-2fb241b7c64a/download/lentidaotrechos2022.csv) ·
[dicionario-de-dados.csv](https://dados.prefeitura.sp.gov.br/dataset/f03433f4-0d4b-44b4-a23b-17111bbb392a/resource/176d789e-d23f-42d4-88a4-d7c40ba39669/download/dicionario-de-dados.csv).
As cópias fiéis com manifesto já estão em `dados/bruto/cet_lentidao_csv/`.

## Uso

```bash
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 1) Coleta (cópia fiel + manifesto) e covariáveis
python -m mobilidade.cli coletar cet-csv --origem dados/entrada/lentidaotrechos2022.csv
python -m mobilidade.cli coletar cet-csv --origem dados/entrada/lentidao_trechos_2023.csv
python -m mobilidade.cli coletar clima --inicio 2022-01-01 --fim 2023-12-31
python -m mobilidade.cli coletar calendario --anos 2022 2023

# 2) Avaliação do artigo: 46 origens em 2023, 10 métodos, testes estatísticos
python experimento/avaliacao_v2.py preparar                                  # séries de todos os corredores, seleção, lacunas
python experimento/avaliacao_v2.py rodar --modelos baselines ets lgbm        # rode as famílias uma de cada vez
python experimento/avaliacao_v2.py rodar --modelos chronos chronos_cov chronos_oraculo chronos_nan   # ~3 h em CPU
python experimento/avaliacao_v2.py avaliar                                   # resultados/v2/resultado_v2.json

python -m mobilidade.cli status      # histórico de execuções (RF25/RF28)
```

Não rode o Chronos-2 junto com o AutoETS ou o LightGBM: eles disputam os núcleos e o PyTorch pode cair. O Chronos-2
grava cada origem em `resultados/v2/parciais/` e retoma de onde parou se for interrompido.

O script `experimento/experimento_previsao.py` traz as linhas de base, as métricas e o adaptador do Chronos-2 usados
pela avaliação v2; sozinho, roda a avaliação simples de outubro (`--demo` para dados sintéticos).

## Resultados (`resultados/v2/`)

| Arquivo | Conteúdo |
|---|---|
| `resultado_v2.json` | resumo por modelo e por limiar de seleção, IC 95%, Wilcoxon, Diebold–Mariano, lacunas, ambiente |
| `metricas_por_janela.csv`, `metricas_por_serie.csv` | métricas por modelo × série × origem e por série |
| `previsoes_*.parquet` | todas as previsões horárias (com quantis nos métodos probabilísticos) |
| `tabela_corredores.csv`, `quadro_regiao_tipo.csv` | caracterização e erro por corredor, região e tipo de via |
| `metadados_series.csv`, `preparo.json`, `series_todas.parquet` | 272 combinações corredor-sentido, seleção, lacunas e séries |
| `fig_*.png` | figuras do artigo |

## Testes

```bash
python -m unittest -v     # 34 testes, sem internet (respostas simuladas e dados sintéticos)
```

Cobrem coleta e leitura (paginação, erros, CSV com vírgula decimal, CAPTCHA), séries e validação (base de eventos,
seleção por dias úteis), o experimento (linhas de base, MAE/MASE, janelas) e a avaliação v2 (origens, mediana por hora da
semana, perda quantílica, cobertura, lacunas, bootstrap, Diebold–Mariano, Holm).

Ambiente da avaliação v2 (novembro de 2026): Python 3.12.10, pandas 2.3.3, chronos-forecasting 2.3.2, torch 2.14.1
(CPU), statsforecast 2.1.1, lightgbm 4.7.0 – versões fixadas em `requirements.txt`.
