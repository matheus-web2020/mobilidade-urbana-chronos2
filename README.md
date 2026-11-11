# Previsão de lentidão viária em São Paulo com Chronos-2

Este repositório reúne o código, os dados de entrada e os resultados de um trabalho de conclusão de curso em Engenharia
de Computação sobre **previsão da lentidão viária em São Paulo**. Ele acompanha o artigo *Previsão de lentidão viária em
São Paulo: avaliação retrospectiva com Chronos-2*.

O trabalho tem duas partes, que podem ser usadas de forma independente:

1. **Experimento de previsão** (`pipeline_mobilidade/`). Transforma a base pública de lentidão da CET em séries
   horárias por corredor e sentido e mede, ao longo de 2023 inteiro, se o **Chronos-2** — um modelo pré-treinado de
   séries temporais, usado sem ajuste fino nos dados deste estudo — prevê as 24 horas seguintes melhor que métodos
   simples, um modelo estatístico (AutoETS) e um modelo de aprendizado treinado nos próprios dados (LightGBM).
2. **MVP do sistema** (`app/`). Aplicação web (React + FastAPI + PostgreSQL) para **consultar** a lentidão de um
   corredor em um período e **classificar os pontos críticos** da cidade por uma regra explícita e ajustável.

Todos os números do artigo estão nos arquivos de `pipeline_mobilidade/resultados/v2/` e podem ser recalculados com os
comandos deste documento.

---

## Sumário

- [Principais resultados](#principais-resultados)
- [Conteúdo do repositório](#conteúdo-do-repositório)
- [Requisitos](#requisitos)
- [Passo 1 – Baixar o projeto e preparar o Python](#passo-1--baixar-o-projeto-e-preparar-o-python)
- [Passo 2 – Executar o MVP (sistema web)](#passo-2--executar-o-mvp-sistema-web)
- [Passo 3 – Reproduzir o experimento (opcional)](#passo-3--reproduzir-o-experimento-opcional)
- [Como o experimento foi feito](#como-o-experimento-foi-feito)
- [Como o MVP funciona](#como-o-mvp-funciona)
- [Dados e como conferi-los](#dados-e-como-conferi-los)
- [Problemas comuns](#problemas-comuns)
- [Limitações](#limitações)
- [Licenças](#licenças)

---

## Principais resultados

Avaliação em **43 séries** (corredor e sentido), **46 origens** distribuídas ao longo de 2023 e horizonte de **24 h**.
O indicador é a **extensão média horária de pista em lentidão, em quilômetros**. MAE = erro absoluto médio (menor é
melhor).

| Método | MAE médio (km) | MAE nas horas com lentidão (km) |
|---|---:|---:|
| Chronos-2 + clima observado (limite superior, usa o clima real do dia previsto) | 0,208 | 1,222 |
| Chronos-2 + covariáveis (calendário futuro e clima passado) | 0,209 | 1,225 |
| **Chronos-2 (univariado)** | **0,211** | **1,218** |
| **LightGBM global** | **0,211** | **1,362** |
| Mediana por hora da semana | 0,238 | 1,374 |
| AutoETS sazonal | 0,261 | 1,871 |
| Zero constante | 0,269 | 2,049 |
| Ingênuo sazonal semanal | 0,280 | 1,422 |

O que esses números mostram:

- **Contra o ingênuo sazonal semanal**, o Chronos-2 reduziu o MAE em 0,069 km (IC 95% de −0,122 a −0,029) e teve erro
  menor em 38 das 43 séries.
- **Contra o LightGBM**, o MAE médio ficou próximo (diferença de 0,0001 km, IC 95% de −0,026 a 0,024), mas o LightGBM
  teve erro menor em 32 das 43 séries (Wilcoxon com ajuste de Holm, p = 0,012). Não foi feito teste de equivalência,
  portanto o resultado não deve ser lido como empate. O Chronos-2 errou menos nas horas em que havia lentidão.
- As covariáveis (calendário e clima) melhoraram pouco o Chronos-2, e a diferença não foi estatisticamente
  significativa.
- O ganho se concentra nas séries de maior volume: as 10 séries com maior ganho respondem por cerca de 81% do ganho
  total.

Os valores completos, com intervalos, testes e os limiares de seleção de 25% e 75%, estão em
`pipeline_mobilidade/resultados/v2/resultado_v2.json`.

---

## Conteúdo do repositório

```
.
├── README.md                     este documento
├── LICENSE                       licença do código (MIT) e créditos dos dados de terceiros
├── pipeline_mobilidade/          experimento de previsão
│   ├── mobilidade/               coleta, validação e montagem das séries horárias
│   │   └── adapters/             leitores de cada fonte (CET, clima, feriados)
│   ├── experimento/
│   │   ├── avaliacao_v2.py       avaliação do artigo (preparar → rodar → avaliar)
│   │   └── experimento_previsao.py  linhas de base, métricas e adaptador do Chronos-2
│   ├── tests/                    34 testes automatizados (sem internet)
│   ├── dados/
│   │   ├── bruto/                arquivos originais da CET, do clima e dos feriados + manifesto com SHA-256
│   │   ├── tratado/              clima horário e calendário diário já processados
│   │   ├── entrada/              dicionário de dados da CET
│   │   └── logs/                 registro de cada comando executado no pipeline
│   ├── resultados/v2/            previsões, métricas, testes estatísticos e figuras do artigo
│   ├── requirements.txt          versões exatas das bibliotecas
│   └── README.md                 detalhes do pipeline e das fontes
└── app/                          MVP
    ├── api/                      API REST (FastAPI) e carga do banco
    ├── db/schema.sql             tabelas do PostgreSQL
    ├── web/                      interface (React + Vite)
    ├── tests/                    11 testes da regra e da API + script de capturas de tela
    ├── docs/capturas/            telas do sistema funcionando com os dados reais
    ├── requirements.txt
    └── README.md                 detalhes do MVP
```

---

## Requisitos

| Programa | Versão | Para quê | Onde obter |
|---|---|---|---|
| Git | qualquer recente | baixar o repositório | https://git-scm.com |
| Python | **3.12** | pipeline, experimento e API | https://www.python.org/downloads/ |
| Node.js | 20 ou mais recente | compilar a interface web | https://nodejs.org |
| PostgreSQL | 16 | banco de dados do MVP | https://www.postgresql.org/download/ |

- Para **só rodar os testes e conferir os resultados**, bastam Git e Python.
- Para **ver o sistema web funcionando**, são necessários os quatro.
- Na instalação do PostgreSQL, guarde a senha escolhida para o usuário administrador `postgres`. Ela será usada uma vez,
  no Passo 2.
- Os comandos abaixo são para o **PowerShell do Windows**. As diferenças para Linux e macOS estão indicadas.

---

## Passo 1 – Baixar o projeto e preparar o Python

```powershell
git clone <endereço deste repositório> mobilidade
cd mobilidade\pipeline_mobilidade

# ambiente virtual do Python (uma pasta .venv só para este projeto)
python -m venv .venv

# PyTorch para CPU (exigido pelo Chronos-2) e demais bibliotecas, nas versões usadas no artigo
.\.venv\Scripts\python.exe -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# bibliotecas da API (o MVP usa o mesmo ambiente)
.\.venv\Scripts\python.exe -m pip install -r ..\app\requirements.txt

# testes do pipeline e do experimento: devem terminar com "Ran 34 tests ... OK"
.\.venv\Scripts\python.exe -m unittest
```

**Linux e macOS:** use `python3 -m venv .venv` e troque `.\.venv\Scripts\python.exe` por `.venv/bin/python` em todos
os comandos. No macOS, instale o PyTorch com `pip install torch==2.14.1`, sem o `--index-url`.

---

## Passo 2 – Executar o MVP (sistema web)

Os comandos deste passo são executados a partir da pasta `app/`:

```powershell
cd ..\app
```

### 2.1 Criar o usuário e os bancos (uma única vez)

Escolha uma senha para o usuário do sistema e use-a no lugar de `<senha>`. O `psql` pede a senha do administrador
`postgres` definida na instalação.

```powershell
$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"
& $psql -U postgres -h localhost -c "CREATE ROLE mobilidade LOGIN PASSWORD '<senha>'"
& $psql -U postgres -h localhost -c "CREATE DATABASE mobilidade OWNER mobilidade"
& $psql -U postgres -h localhost -c "CREATE DATABASE mobilidade_teste OWNER mobilidade"
```

**Linux e macOS:** `sudo -u postgres psql -c "..."` com os mesmos três comandos SQL.

As tabelas não precisam ser criadas à mão: a carga do passo 2.3 aplica `db/schema.sql`.

### 2.2 Criar o arquivo `app/.env`

Crie o arquivo `app/.env` com o conteúdo abaixo, usando a mesma senha do passo 2.1:

```
DATABASE_URL=postgresql://mobilidade:<senha>@localhost:5432/mobilidade
DATABASE_URL_TESTE=postgresql://mobilidade:<senha>@localhost:5432/mobilidade_teste
```

O `.env` fica só no seu computador: o `.gitignore` impede que ele seja enviado ao repositório.

### 2.3 Carregar os dados no banco

```powershell
..\pipeline_mobilidade\.venv\Scripts\python.exe -m api.carregar
```

A carga lê as séries já incluídas em `pipeline_mobilidade/resultados/v2/` (272 combinações corredor-sentido, cerca de
4,1 milhões de horas), grava tudo no PostgreSQL e define os limites padrão de criticidade. Leva cerca de 2 minutos.

### 2.4 Testar a regra e a API

```powershell
# deve terminar com "Ran 11 tests ... OK" (usa o banco mobilidade_teste com dados sintéticos)
..\pipeline_mobilidade\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

### 2.5 Compilar a interface

```powershell
cd web
npm install
npm run build
cd ..
```

### 2.6 Iniciar o sistema

```powershell
..\pipeline_mobilidade\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

Com o terminal aberto, acesse no navegador:

- **http://localhost:8000** – o sistema, com duas abas:
  - **Consultar mobilidade**: escolha corredor, sentido, período e agregação (por hora ou por dia) e veja a tabela e o
    gráfico da lentidão;
  - **Pontos críticos**: ranking dos corredores por índice de criticidade, com nível (baixo, moderado, alto, crítico),
    filtro por região e ordenação.
- **http://localhost:8000/docs** – documentação interativa da API REST.

Para encerrar, pressione `Ctrl+C` no terminal. Nas próximas vezes, basta repetir o passo 2.6.

As telas esperadas estão em `app/docs/capturas/`. Para gerá-las de novo com o sistema no ar (opcional):

```powershell
..\pipeline_mobilidade\.venv\Scripts\python.exe -m playwright install chromium
..\pipeline_mobilidade\.venv\Scripts\python.exe tests\capturas_tela.py
```

---

## Passo 3 – Reproduzir o experimento (opcional)

Os resultados publicados estão em `pipeline_mobilidade/resultados/v2/`. Para refazê-los **sem sobrescrever** esses
arquivos, grave a nova rodada em outra pasta com `--saida`. Execute a partir de `pipeline_mobilidade/`:

```powershell
cd ..\pipeline_mobilidade
$py = ".\.venv\Scripts\python.exe"

# séries de todos os corredores, seleção com dados de 2022 e dias de lacuna (cerca de 10 s)
& $py experimento\avaliacao_v2.py preparar --saida resultados\reproducao

# linhas de base, AutoETS e LightGBM
& $py experimento\avaliacao_v2.py rodar --modelos baselines ets lgbm --saida resultados\reproducao

# as quatro variantes do Chronos-2 (cerca de 3 h em CPU; na primeira vez, baixa o modelo amazon/chronos-2)
& $py experimento\avaliacao_v2.py rodar --modelos chronos chronos_cov chronos_oraculo chronos_nan --saida resultados\reproducao

# métricas, intervalos de confiança, testes estatísticos e figuras
& $py experimento\avaliacao_v2.py avaliar --saida resultados\reproducao
```

Recomendações:

- Rode as famílias de modelos **uma de cada vez**, na ordem acima. O Chronos-2 e o AutoETS usam todos os núcleos do
  processador e, em paralelo, podem derrubar o processo.
- Se a rodada do Chronos-2 for interrompida, repita o mesmo comando: cada origem já calculada fica salva em
  `resultados/reproducao/parciais/` e não é refeita.
- Para conferir apenas a etapa estatística, sem gerar previsões, copie os arquivos `previsoes_*.parquet`,
  `metadados_series.csv`, `series_todas.parquet` e `preparo.json` de `resultados/v2/` para uma pasta nova e rode só o
  `avaliar` com `--saida` apontando para ela. O `resultado_v2.json` gerado deve coincidir com o publicado.

Para comparar a nova rodada com a publicada:

```powershell
& $py -c "import json; ler=lambda p: json.load(open(p, encoding='utf-8'))['conjuntos']['0.5']['modelos']; a=ler('resultados/v2/resultado_v2.json'); b=ler('resultados/reproducao/resultado_v2.json'); [print(m.ljust(30), 'publicado', round(a[m]['MAE_medio'], 4), '| reproduzido', round(b[m]['MAE_medio'], 4)) for m in a]"
```

---

## Como o experimento foi feito

**Dados.** Base *Lentidão por trechos* da CET (Portal de Dados Abertos da Prefeitura de São Paulo), anos de 2022 e
2023, com 313.797 registros coletados a cada 30 minutos. É uma base de **eventos**: um trecho só aparece quando há fila.
Por isso, a ausência de registro é tratada como lentidão zero.

**Séries.** Uma série por corredor e sentido (272 combinações), com a **extensão média horária de pista em lentidão, em
km** (soma dos trechos lentos em cada coleta, média por hora). As covariáveis são clima horário (temperatura e
precipitação, Open-Meteo) e feriados (BrasilAPI).

**Seleção sem olhar o período de teste.** Entram as séries com lentidão em pelo menos 50% dos dias úteis de **2022**,
o que resulta em 43 séries. O efeito dessa escolha é medido com limiares de 25% (74 séries) e 75% (20 séries).

**Teste.** 46 origens de previsão em 2023, uma a cada 8 dias (02/01 a 28/12), de modo que todas caiam em todos os dias
da semana. Em cada origem, cada método recebe apenas o histórico anterior e prevê as 24 horas seguintes.

**Métodos comparados.**

| Grupo | Métodos |
|---|---|
| Referências simples | ingênuo, sazonal diário, sazonal semanal, zero constante, mediana por hora da semana (8 semanas) |
| Estatístico | AutoETS com sazonalidade diária, ajustado às 4 semanas anteriores (statsforecast) |
| Aprendizado de máquina | LightGBM global, retreinado em cada origem com o ano anterior de todas as séries (hora, dia da semana, feriado, defasagens de 24 a 336 h e média da mesma hora nos 7 dias anteriores), em previsão direta |
| Modelo pré-treinado | Chronos-2 univariado; com covariáveis (feriado e fim de semana conhecidos no futuro, temperatura e precipitação só no passado); com clima futuro observado (limite superior); com dias de lacuna como valor faltante |

**Métricas.** MAE, nMAE (MAE dividido pela média da série no histórico anterior à origem), MASE, MAE só nas horas com lentidão e, para os métodos
probabilísticos, perda quantílica ponderada (WQL) e cobertura dos intervalos de 80% e 90%.

**Estatística.** Intervalo de confiança de 95% por bootstrap em dois níveis (séries e origens), teste de Wilcoxon
pareado por série e teste de Diebold–Mariano com correção de Harvey–Leybourne–Newbold, todos com ajuste de Holm para
comparações múltiplas.

**Lacunas suspeitas.** Um dia útil sem feriado em que a cidade teve registros, mas o corredor não, é marcado como
lacuna suspeita quando o corredor teve registro em pelo menos 18 dos 20 dias úteis anteriores. Foram 260 dias em 35
séries (648 horas dentro das janelas de teste). A avaliação é repetida sem essas horas e, no Chronos-2, com elas como
valor faltante.

---

## Como o MVP funciona

Arquitetura em camadas: **interface React (Vite) → API REST FastAPI (`/api/v1`) → PostgreSQL 16**.

| Funcionalidade | Endpoint | Tela |
|---|---|---|
| Lista de corredores e regiões | `GET /api/v1/localidades`, `GET /api/v1/regioes` | filtros das duas abas |
| Consulta da lentidão por corredor e período (HU02) | `GET /api/v1/consulta` | Consultar mobilidade |
| Classificação de pontos críticos (HU08) | `GET /api/v1/criticidade` | Pontos críticos |
| Limites da classificação | `GET` e `PUT /api/v1/parametros/criticidade` | – |

**Regra de criticidade.** O índice de um corredor e sentido no período é a média de km em lentidão das 7h às 20h de
segunda a sexta-feira, exceto feriados. O nível é definido por três limites: baixo, moderado, alto e crítico.
Os limites padrão são os quartis do índice de 2022 entre as 256 combinações com alguma lentidão (0,0029; 0,0128 e
0,068 km), o que torna a regra relativa ao ano de referência. A resposta da API sempre informa o valor do índice, o
nível, a posição no ranking e os limites aplicados.

**Mensagens de erro.** Critérios inválidos (por exemplo, data final antes da inicial) e períodos sem dados retornam
mensagens explicativas, exibidas na própria tela.

O MVP **não tem autenticação**: qualquer pessoa com acesso à API pode alterar os limites de criticidade. Para uso fora
de um ambiente local, seria necessário acrescentar controle de acesso.

---

## Dados e como conferi-los

| Fonte | Arquivos em `pipeline_mobilidade/dados/bruto/` | Licença |
|---|---|---|
| CET – Lentidão por trechos, 2022 e 2023 | `cet_lentidao_csv/` | CC BY |
| Open-Meteo – clima horário de São Paulo | `openmeteo/` | CC BY 4.0 |
| BrasilAPI – feriados nacionais | `calendario/` | – |

Cada arquivo vem acompanhado de um `.meta.json` com data da coleta, origem e hash SHA-256. Para confirmar que os CSV da
CET são os originais, baixe-os em
https://dados.prefeitura.sp.gov.br/dataset/base-de-dados-sobre-lentidao-por-trechos-cet e compare o hash:

```powershell
certutil -hashfile lentidao_trechos_2023.csv SHA256     # Linux/macOS: sha256sum lentidao_trechos_2023.csv
```

| Arquivo | SHA-256 |
|---|---|
| `lentidao_trechos_2023.csv` | `1c7bb63bfbda890fcfe5877723cc78c47cf6ba3a067686c7a4c20bdcd68dd27f` |
| `lentidaotrechos2022.csv` | `9c8a2cec72b8c1506dbbdabb90ad93911ba8e1fef6a67f59327961f5ec250f77` |

Arquivos de resultado (`pipeline_mobilidade/resultados/v2/`):

| Arquivo | Conteúdo |
|---|---|
| `resultado_v2.json` | resumo por modelo e por limiar de seleção, IC 95%, testes estatísticos, concentração do ganho, lacunas e versões das bibliotecas |
| `metricas_por_janela.csv` | todas as métricas por modelo, série e origem |
| `metricas_por_serie.csv` | métricas médias por modelo e série |
| `previsoes_*.parquet` | todas as previsões horárias (com quantis nos métodos probabilísticos) |
| `tabela_corredores.csv`, `quadro_regiao_tipo.csv` | caracterização e erro por corredor, região e tipo de via |
| `metadados_series.csv`, `preparo.json`, `series_todas.parquet` | as 272 combinações, critérios de seleção, lacunas e séries horárias |
| `fig_ganho_por_serie.png`, `fig_mae_por_hora.png` | figuras do artigo |

Detalhes das fontes e dos comandos de coleta estão em `pipeline_mobilidade/README.md`.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `defina DATABASE_URL (variável de ambiente ou app/.env)` | O arquivo `app/.env` não existe ou está em outra pasta. Refaça o passo 2.2. |
| `password authentication failed for user "mobilidade"` | A senha no `.env` é diferente da usada no `CREATE ROLE`. Corrija o `.env` ou altere a senha com `ALTER ROLE mobilidade PASSWORD '<senha>'`. |
| `connection refused` na porta 5432 | O serviço do PostgreSQL não está em execução. No Windows, inicie-o em *Serviços* (postgresql-x64-16). |
| `'psql' não é reconhecido` | Use o caminho completo, como no passo 2.1, ou ajuste a versão na pasta `C:\Program Files\PostgreSQL\`. |
| `Interface não encontrada: rode npm install e npm run build em app/web` | A interface não foi compilada. Refaça o passo 2.5. |
| `Ainda não existem parâmetros de criticidade` | O banco está vazio. Refaça o passo 2.3. |
| A porta 8000 já está em uso | Inicie com outra porta, por exemplo `--port 8001`, e acesse http://localhost:8001. |
| O processo do Chronos-2 é encerrado sem mensagem | Rodou junto com AutoETS ou LightGBM. Rode uma família de cada vez; a execução continua de onde parou. |
| Erro ao instalar `numpy`, `pandas` ou `torch` | Verifique se a versão do Python é a 3.12 (`python --version`). |

---

## Limitações

- A série de lentidão da CET usada aqui (Monitrans) termina em 2023. De 2024 em diante, a CET passou a usar dados do
  Waze, sem histórico público comparável. Os resultados valem para 2022–2023.
- A base registra um trecho apenas quando há fila. A ausência de registro foi tratada como zero, e a avaliação
  complementar trata as lacunas suspeitas como dado faltante.
- A avaliação cobre 43 séries de um sistema de monitoramento específico e não se generaliza para toda a malha viária.
- A CET não publica a extensão monitorada de cada corredor nem sua geometria. Por isso o MVP não tem mapa e a extensão
  máxima registrada em lentidão é usada apenas como aproximação do porte do corredor.

---

## Licenças

- **Código:** MIT (ver `LICENSE`).
- **Dados de terceiros** em `pipeline_mobilidade/dados/bruto/`: CET (CC BY), Open-Meteo (CC BY 4.0) e BrasilAPI, com
  os créditos em `LICENSE`.

Ambiente usado nos resultados publicados: Python 3.12.10, pandas 2.3.3, numpy 2.5.4, scipy 1.18.1, statsforecast
2.1.1, lightgbm 4.7.0, torch 2.14.1 (CPU) e chronos-forecasting 2.3.2 (versões fixadas em
`pipeline_mobilidade/requirements.txt`).
