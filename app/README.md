# MVP – Consulta de lentidão e classificação de criticidade

Implementa as histórias do MVP que dependem da interface (a HU13, carga e validação do CSV, está no pipeline em
`../pipeline_mobilidade`):

| História | Requisito | Caso de uso | Onde |
|---|---|---|---|
| HU02 – consultar a situação da mobilidade | RF07 | UC01 (E01 critérios inválidos, E02 sem dados, E03 indisponível) | `GET /api/v1/consulta`, aba **Consultar mobilidade** |
| HU08 – classificar localidades por regra explícita | RF18–RF20 | UC07 (ordenação, filtro, E01 sem resultados) | `GET /api/v1/criticidade`, aba **Pontos críticos** |
| Parâmetros da regra (administrador) | RF19 | – | `GET/PUT /api/v1/parametros/criticidade` |

Arquitetura em camadas, como na especificação: **React (Vite)** → **API REST FastAPI** → **PostgreSQL 16**.
Não há PostGIS no MVP: a base da CET não traz geometria dos corredores (o mapa segue como evolutivo).

## Regra de criticidade (HU08)

- **Índice** de um corredor/sentido num período = km médios em lentidão nas horas de 7h a 20h dos dias úteis
  (segunda a sexta, exceto feriados).
- **Níveis**: baixo < l1 ≤ moderado < l2 ≤ alto < l3 ≤ crítico. Os limites ficam na tabela `parametro_sistema` e podem
  ser alterados pelo administrador. O padrão são os quartis do índice de 2022 entre os corredores com alguma lentidão,
  ou seja, a regra é **relativa** ao ano de referência.
- A resposta sempre mostra o valor do índice, o nível, a posição no ranking e os limites aplicados.

## Como executar

Pré-requisitos: Python 3.12 (venv do pipeline), Node 20+ e PostgreSQL 16.

```powershell
# 1) banco (uma vez): criar usuário e bases com uma senha à sua escolha; as tabelas são criadas pela carga (passo 2)
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "CREATE ROLE mobilidade LOGIN PASSWORD '<senha>'"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE mobilidade OWNER mobilidade"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE mobilidade_teste OWNER mobilidade"
#    e criar o arquivo app/.env com a mesma senha:
#    DATABASE_URL=postgresql://mobilidade:<senha>@localhost:5432/mobilidade
#    DATABASE_URL_TESTE=postgresql://mobilidade:<senha>@localhost:5432/mobilidade_teste
..\pipeline_mobilidade\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) dados: gerar as séries no pipeline e carregar o banco (272 corredores, ~4,1 milhões de horas, ~2 min)
cd ..\pipeline_mobilidade; .\.venv\Scripts\python.exe experimento\avaliacao_v2.py preparar; cd ..\app
..\pipeline_mobilidade\.venv\Scripts\python.exe -m api.carregar

# 3) interface: compilar
cd web; npm install; npm run build; cd ..

# 4) subir (API + interface em http://localhost:8000; documentação da API em /docs)
..\pipeline_mobilidade\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

Desenvolvimento da interface com recarga automática: `npm run dev` em `web/` (encaminha `/api` para a porta 8000).

## Testes

```powershell
..\pipeline_mobilidade\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v   # regra + API (banco de teste)
..\pipeline_mobilidade\.venv\Scripts\python.exe tests\capturas_tela.py                  # telas reais (API no ar)
```

As capturas ficam em `docs/capturas/` (consulta por hora, critério inválido, ranking de criticidade e filtro por região).
