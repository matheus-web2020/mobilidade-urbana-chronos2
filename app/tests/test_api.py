import unittest

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from api.carregar import carregar
from api.config import database_url
from api.criticidade import ParametrosCriticidade, classificar, limites_por_quartis, nivel
from api.main import app


class TestRegraCriticidade(unittest.TestCase):
    p = ParametrosCriticidade((1.0, 2.0, 3.0))

    def test_faixas_nos_limites(self):
        self.assertEqual([nivel(x, self.p) for x in (0, 0.99, 1.0, 2.0, 2.99, 3.0, 10)],
                         ["baixo", "baixo", "moderado", "alto", "alto", "crítico", "crítico"])

    def test_limites_invalidos(self):
        for lim in [(2, 1, 3), (1, 1, 2), (-1, 1, 2)]:
            with self.assertRaises(ValueError):
                ParametrosCriticidade(lim)

    def test_quartis_ignoram_zeros(self):
        self.assertEqual(limites_por_quartis([0, 0, 1, 2, 3, 4, 5]), (2.0, 3.0, 4.0))

    def test_ranking_e_ordem_por_nome(self):
        linhas = [{"corredor": "B", "sentido": "x", "indice": 0.5, "horas": 10, "horas_com_lentidao": 5},
                  {"corredor": "A", "sentido": "y", "indice": 3.5, "horas": 10, "horas_com_lentidao": 10}]
        r = classificar(linhas, self.p)
        self.assertEqual([x["corredor"] for x in r], ["A", "B"])
        self.assertEqual([x["posicao"] for x in r], [1, 2])
        self.assertEqual(r[0]["nivel"], "crítico")
        r = classificar(linhas, self.p, ordem="nome")
        self.assertEqual([(x["corredor"], x["posicao"]) for x in r], [("A", 1), ("B", 2)])


def _dados_sinteticos():
    idx = pd.date_range("2022-01-03", "2023-01-08 23:00", freq="h")
    util = (idx.dayofweek < 5) & (idx.hour >= 7) & (idx.hour < 20)
    series = pd.concat([pd.DataFrame({"timestamp": idx, "series_id": f"C{k} | Ida", "target": np.where(util, k, 0.0)})
                        for k in range(1, 6)], ignore_index=True)
    meta = pd.DataFrame({"series_id": [f"C{k} | Ida" for k in range(1, 6)], "corredor": [f"C{k}" for k in range(1, 6)],
                         "sentido": "Ida", "regiao": ["CENTRO", "CENTRO", "SUL", "SUL", "OESTE"],
                         "tipo_via": "expressa", "extensao_max_km": [1.0, 2, 3, 4, 5]})
    feriados = pd.DataFrame({"data": [pd.Timestamp("2023-01-02").date()], "nome": ["teste"]})
    return series, meta, feriados


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = database_url(teste=True)
        cls.carga = carregar(cls.url, *_dados_sinteticos(), origem="sintético")
        app.state.database_url = cls.url
        cls.c = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        del app.state.database_url

    def test_carga_define_limites_por_quartis(self):
        self.assertEqual(self.carga["localidades"], 5)
        self.assertEqual(self.carga["limites"], (2.0, 3.0, 4.0))

    def test_consulta_por_dia(self):
        loc = {l["corredor"]: l["id"] for l in self.c.get("/api/v1/localidades").json()}
        r = self.c.get("/api/v1/consulta", params={"localidade_id": loc["C3"], "inicio": "2022-01-03",
                                                "fim": "2022-01-09", "agregacao": "dia"})
        self.assertEqual(r.status_code, 200, r.text)
        corpo = r.json()
        self.assertEqual(len(corpo["serie"]), 7)
        self.assertAlmostEqual(corpo["serie"][0]["km_lentidao"], 3 * 13 / 24)
        self.assertEqual(corpo["resumo"]["km_maximo"], 3.0)

    def test_consulta_criterios_invalidos_e_sem_dados(self):
        loc = self.c.get("/api/v1/localidades").json()[0]["id"]
        r = self.c.get("/api/v1/consulta", params={"localidade_id": loc, "inicio": "2022-02-10", "fim": "2022-02-01"})
        self.assertEqual(r.status_code, 422)
        r = self.c.get("/api/v1/consulta", params={"localidade_id": 9999, "inicio": "2022-02-01", "fim": "2022-02-02"})
        self.assertEqual(r.status_code, 422)
        r = self.c.get("/api/v1/consulta", params={"localidade_id": loc, "inicio": "2025-01-01", "fim": "2025-01-31"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("Dados disponíveis", r.json()["detail"])

    def test_criticidade_ranking_niveis_e_regiao(self):
        r = self.c.get("/api/v1/criticidade", params={"inicio": "2022-03-01", "fim": "2022-03-31"})
        self.assertEqual(r.status_code, 200, r.text)
        itens = r.json()["itens"]
        self.assertEqual([i["corredor"] for i in itens], ["C5", "C4", "C3", "C2", "C1"])
        self.assertEqual([i["nivel"] for i in itens], ["crítico", "crítico", "alto", "moderado", "baixo"])
        self.assertAlmostEqual(itens[0]["indice"], 5.0)
        self.assertIn("Índice =", r.json()["regra"])
        r = self.c.get("/api/v1/criticidade", params={"inicio": "2022-03-01", "fim": "2022-03-31", "regiao": "sul"})
        self.assertEqual({i["corredor"] for i in r.json()["itens"]}, {"C3", "C4"})

    def test_criticidade_so_feriado_e_fim_de_semana(self):
        r = self.c.get("/api/v1/criticidade", params={"inicio": "2023-01-01", "fim": "2023-01-02"})
        self.assertEqual(r.status_code, 404)

    def test_rota_de_api_inexistente_responde_404(self):
        r = self.c.get("/api/saude")
        self.assertEqual(r.status_code, 404)
        self.assertIn("não encontrada", r.json()["detail"])

    def test_alterar_parametros(self):
        r = self.c.put("/api/v1/parametros/criticidade", json={"limites": [3, 2, 1]})
        self.assertEqual(r.status_code, 422)
        r = self.c.put("/api/v1/parametros/criticidade", json={"limites": [0.5, 1.5, 4.5]})
        self.assertEqual(r.status_code, 200)
        itens = self.c.get("/api/v1/criticidade", params={"inicio": "2022-03-01", "fim": "2022-03-31"}).json()["itens"]
        self.assertEqual([i["nivel"] for i in itens], ["crítico", "alto", "alto", "alto", "moderado"])
        self.c.put("/api/v1/parametros/criticidade", json={"limites": [2, 3, 4]})


if __name__ == "__main__":
    unittest.main()
