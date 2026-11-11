import React, { useMemo, useRef, useState } from "react";
import { km } from "./api.js";

export default function Grafico({ serie, agregacao }) {
  const L = 720, A = 240, m = { e: 48, d: 12, t: 12, b: 28 };
  const ref = useRef(null);
  const [foco, setFoco] = useState(null);

  const { x, y, max, caminho, area, ticksY, ticksX } = useMemo(() => {
    const n = serie.length;
    const max = Math.max(0.5, ...serie.map((p) => p.km_lentidao));
    const x = (i) => m.e + (n <= 1 ? 0 : (i / (n - 1)) * (L - m.e - m.d));
    const y = (v) => m.t + (1 - v / max) * (A - m.t - m.b);
    const pts = serie.map((p, i) => `${x(i)},${y(p.km_lentidao)}`);
    const passo = Math.max(1, Math.round(n / 6));
    return {
      x, y, max,
      caminho: `M${pts.join("L")}`,
      area: `M${x(0)},${y(0)}L${pts.join("L")}L${x(n - 1)},${y(0)}Z`,
      ticksY: [0, max / 2, max],
      ticksX: serie.map((p, i) => i).filter((i) => i % passo === 0),
    };
  }, [serie]);

  const rotulo = (s) => (agregacao === "dia" ? s.slice(0, 10) : s.slice(0, 16).replace("T", " "));

  function mover(ev) {
    const r = ref.current.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * L;
    const i = Math.round(((px - m.e) / (L - m.e - m.d)) * (serie.length - 1));
    setFoco(Math.min(serie.length - 1, Math.max(0, i)));
  }

  return (
    <figure className="grafico">
      <svg ref={ref} viewBox={`0 0 ${L} ${A}`} onMouseMove={mover} onMouseLeave={() => setFoco(null)}
           role="img" aria-label="Série de km em lentidão no período consultado">
        {ticksY.map((t) => (
          <g key={t}>
            <line x1={m.e} x2={L - m.d} y1={y(t)} y2={y(t)} className="grade" />
            <text x={m.e - 6} y={y(t) + 4} textAnchor="end" className="eixo">{km(t, 1)}</text>
          </g>
        ))}
        {ticksX.map((i) => (
          <text key={i} x={x(i)} y={A - 8} textAnchor="middle" className="eixo">{rotulo(serie[i].instante).slice(5)}</text>
        ))}
        <path d={area} className="area" />
        <path d={caminho} className="linha" />
        {foco != null && (
          <g>
            <line x1={x(foco)} x2={x(foco)} y1={m.t} y2={A - m.b} className="cursor" />
            <circle cx={x(foco)} cy={y(serie[foco].km_lentidao)} r="4" className="ponto" />
          </g>
        )}
      </svg>
      <figcaption>
        {foco != null
          ? `${rotulo(serie[foco].instante)} — ${km(serie[foco].km_lentidao)} km em lentidão`
          : `km em lentidão (máx. no gráfico: ${km(max, 1)} km) — passe o mouse para ver os valores`}
      </figcaption>
    </figure>
  );
}
