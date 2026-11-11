from __future__ import annotations

from dataclasses import dataclass

NIVEIS = ("baixo", "moderado", "alto", "crítico")


@dataclass(frozen=True)
class ParametrosCriticidade:
    limites: tuple[float, float, float]
    hora_inicio: int = 7
    hora_fim: int = 20
    origem_limites: str = ""

    def __post_init__(self):
        l1, l2, l3 = self.limites
        if not (0 <= l1 < l2 < l3):
            raise ValueError("os limites devem ser crescentes e não negativos (l1 < l2 < l3)")
        if not (0 <= self.hora_inicio < self.hora_fim <= 24):
            raise ValueError("janela horária inválida")

    @classmethod
    def de_dict(cls, d: dict) -> "ParametrosCriticidade":
        return cls(tuple(float(x) for x in d["limites"]), int(d.get("hora_inicio", 7)), int(d.get("hora_fim", 20)),
                   d.get("origem_limites", ""))

    def como_dict(self) -> dict:
        return {"limites": list(self.limites), "hora_inicio": self.hora_inicio, "hora_fim": self.hora_fim,
                "origem_limites": self.origem_limites}


def nivel(indice: float, p: ParametrosCriticidade) -> str:
    l1, l2, l3 = p.limites
    if indice >= l3:
        return NIVEIS[3]
    if indice >= l2:
        return NIVEIS[2]
    if indice >= l1:
        return NIVEIS[1]
    return NIVEIS[0]


def limites_por_quartis(indices: list[float]) -> tuple[float, float, float]:
    v = sorted(x for x in indices if x > 0)
    if len(v) < 4:
        raise ValueError("índices positivos insuficientes para calcular quartis")

    def q(p):
        pos = p * (len(v) - 1)
        i = int(pos)
        return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (pos - i)

    a, b, c = q(0.25), q(0.5), q(0.75)
    return (round(a, 4), round(max(b, a + 1e-4), 4), round(max(c, b + 2e-4), 4))


def classificar(linhas: list[dict], p: ParametrosCriticidade, ordem: str = "indice") -> list[dict]:
    out = []
    for r in linhas:
        r = dict(r)
        r["nivel"] = nivel(r["indice"], p)
        r["frac_horas_com_lentidao"] = r["horas_com_lentidao"] / r["horas"] if r["horas"] else 0.0
        out.append(r)
    if ordem == "nome":
        out.sort(key=lambda r: (r["corredor"], r["sentido"]))
    else:
        out.sort(key=lambda r: (-r["indice"], r["corredor"]))
    por_indice = sorted(out, key=lambda r: -r["indice"])
    posicao = {id(r): i + 1 for i, r in enumerate(por_indice)}
    for r in out:
        r["posicao"] = posicao[id(r)]
    return out
