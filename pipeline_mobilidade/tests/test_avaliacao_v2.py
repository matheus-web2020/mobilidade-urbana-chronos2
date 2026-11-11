import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "avaliacao_v2", Path(__file__).resolve().parents[1] / "experimento" / "avaliacao_v2.py")
av = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = av
_spec.loader.exec_module(av)


class TestOrigens(unittest.TestCase):
    def test_passo_de_8_dias_percorre_a_semana_e_respeita_o_fim(self):
        o = av.origens_teste()
        self.assertEqual(o[0], pd.Timestamp("2023-01-02"))
        self.assertTrue(all((b - a) == pd.Timedelta(days=8) for a, b in zip(o, o[1:])))
        self.assertEqual({x.dayofweek for x in o}, set(range(7)))
        self.assertLessEqual(o[-1] + pd.Timedelta(hours=23), av.FIM_TESTE)


class TestBaselineHoraSemana(unittest.TestCase):
    def test_mediana_da_mesma_hora_nas_ultimas_semanas(self):
        semana = np.arange(168, dtype=float)
        hist = np.concatenate([semana + 10 * k for k in range(8)])
        med, q = av.mediana_hora_semana(hist, horizonte=24, semanas=8)
        np.testing.assert_allclose(med, np.arange(24) + 35.0)
        self.assertEqual(q.shape, (24, len(av.QUANTIS)))
        self.assertTrue(np.all(np.diff(q, axis=1) >= 0))


class TestMetricasProbabilisticas(unittest.TestCase):
    def test_pinball_zero_quando_todos_os_quantis_acertam(self):
        y = np.array([1.0, 2.0])
        self.assertEqual(av.pinball(y, np.tile(y[:, None], len(av.QUANTIS))).sum(), 0)

    def test_pinball_assimetrico(self):
        self.assertAlmostEqual(av.pinball(np.array([1.0]), np.array([[0.0]]), [0.9])[0], 0.9)
        self.assertAlmostEqual(av.pinball(np.array([1.0]), np.array([[0.0]]), [0.1])[0], 0.1)

    def test_wql_e_cobertura(self):
        y = np.array([2.0, 2.0])
        q = np.zeros((2, len(av.QUANTIS)))
        self.assertAlmostEqual(av.wql(y, q), 2 * sum(av.QUANTIS) * 2 * 2 / (len(av.QUANTIS) * 4))
        self.assertTrue(np.isnan(av.wql(np.zeros(2), q)))
        self.assertEqual(av.cobertura(np.array([1, 5]), np.array([0, 0]), np.array([2, 2])), 0.5)


class TestMetricasPorJanela(unittest.TestCase):
    def test_modelo_sem_quantis_fica_sem_wql_e_lacuna_sai_da_metrica(self):
        ts = pd.date_range("2023-01-03", periods=24, freq="h")
        base = {"series_id": "A", "origem": ts[0], "passo": range(1, 25), "timestamp": ts, "y": [0.0] * 12 + [2.0] * 12}
        com_q = pd.DataFrame({**base, "yhat": 1.0, "modelo": "Prob", **{c: 1.0 for c in av.QCOLS}})
        sem_q = pd.DataFrame({**base, "yhat": 1.0, "modelo": "Pontual", **{c: np.nan for c in av.QCOLS}})
        m = av._metricas_janela(pd.concat([com_q, sem_q]), lacunas={("A", pd.Timestamp("2023-01-03"))})
        m = m.set_index("modelo")
        self.assertTrue(np.isnan(m.loc["Pontual", "soma_pinball"]))
        self.assertTrue(np.isnan(m.loc["Pontual", "cob80"]))
        self.assertGreater(m.loc["Prob", "soma_pinball"], 0)
        self.assertEqual(m.loc["Prob", "n_pos"], 12)
        self.assertEqual(m.loc["Prob", "n_sem_lacuna"], 0)
        self.assertAlmostEqual(m.loc["Prob", "MAE"], 1.0)


class TestLacunas(unittest.TestCase):
    def test_dia_util_sem_registro_do_corredor_com_registro_na_cidade(self):
        cidade = {pd.Timestamp(d) for d in ["2023-01-02", "2023-01-03", "2023-01-04", "2023-01-07"]}
        serie = {pd.Timestamp("2023-01-02")}
        sem = av.dias_uteis_sem_registro(serie, cidade, pd.Timestamp("2023-01-02"), pd.Timestamp("2023-01-08"),
                                         feriados={pd.Timestamp("2023-01-04")})
        self.assertEqual(sem, [pd.Timestamp("2023-01-03")])

    def test_lacuna_suspeita_exige_habito_de_lentidao(self):
        uteis = [d for d in pd.date_range("2022-11-01", "2023-01-31") if d.dayofweek < 5]
        cidade = set(uteis)
        alvo = pd.Timestamp("2023-01-16")
        frequente = set(uteis) - {alvo}
        esparso = {d for i, d in enumerate(uteis) if i % 2 == 0} - {alvo}
        args = (cidade, pd.Timestamp("2023-01-02"), pd.Timestamp("2023-01-31"), set())
        self.assertEqual(av.dias_lacuna(frequente, *args), [alvo])
        self.assertEqual(av.dias_lacuna(esparso, *args), [])


class TestEstatistica(unittest.TestCase):
    def test_bootstrap_contem_a_media_e_e_deterministico(self):
        d = np.random.default_rng(0).normal(1.0, 0.5, (30, 40))
        m, lo, hi = av.bootstrap_dois_niveis(d, b=300)
        self.assertTrue(lo < m < hi)
        self.assertEqual(av.bootstrap_dois_niveis(d, b=300), (m, lo, hi))

    def test_diebold_mariano_detecta_diferenca_e_nao_inventa(self):
        rng = np.random.default_rng(1)
        _, p_dif = av.diebold_mariano(rng.normal(0.5, 1, 200))
        _, p_igual = av.diebold_mariano(rng.normal(0.0, 1, 200))
        self.assertLess(p_dif, 0.01)
        self.assertGreater(p_igual, 0.05)

    def test_holm_monotono_e_limitado(self):
        aj = av.holm({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(aj["a"], 0.03)
        self.assertAlmostEqual(aj["c"], 0.06)
        self.assertAlmostEqual(aj["b"], 0.06)


if __name__ == "__main__":
    unittest.main()
