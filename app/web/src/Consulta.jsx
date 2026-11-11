import React, { useEffect, useMemo, useState } from "react";
import { km, obter } from "./api.js";
import Grafico from "./Grafico.jsx";

export default function Consulta() {
  const [locais, setLocais] = useState([]);
  const [regiao, setRegiao] = useState("");
  const [f, setF] = useState({ localidade_id: "", inicio: "2023-12-04", fim: "2023-12-08", agregacao: "hora" });
  const [res, setRes] = useState(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    obter("localidades").then((l) => {
      setLocais(l);
      const padrao = l.find((x) => x.corredor === "Marginal Tietê" && x.sentido.startsWith("Castelo")) || l[0];
      if (padrao) setF((v) => ({ ...v, localidade_id: String(padrao.id) }));
    }).catch((e) => setErro(e.message));
  }, []);

  const regioes = useMemo(() => [...new Set(locais.map((l) => l.regiao))].sort(), [locais]);
  const visiveis = locais.filter((l) => !regiao || l.regiao === regiao);

  async function consultar(ev) {
    ev?.preventDefault();
    setErro(""); setRes(null); setCarregando(true);
    try { setRes(await obter("consulta", f)); } catch (e) { setErro(e.message); } finally { setCarregando(false); }
  }

  return (
    <section>
      <form className="filtros" onSubmit={consultar}>
        <label>Região
          <select value={regiao} onChange={(e) => setRegiao(e.target.value)}>
            <option value="">Todas</option>
            {regioes.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label className="largo">Corredor e sentido
          <select value={f.localidade_id} onChange={(e) => setF({ ...f, localidade_id: e.target.value })} required>
            {visiveis.map((l) => <option key={l.id} value={l.id}>{l.corredor} — {l.sentido}</option>)}
          </select>
        </label>
        <label>Início<input type="date" value={f.inicio} onChange={(e) => setF({ ...f, inicio: e.target.value })} required /></label>
        <label>Fim<input type="date" value={f.fim} onChange={(e) => setF({ ...f, fim: e.target.value })} required /></label>
        <label>Agregação
          <select value={f.agregacao} onChange={(e) => setF({ ...f, agregacao: e.target.value })}>
            <option value="hora">Por hora</option><option value="dia">Por dia</option>
          </select>
        </label>
        <button type="submit" disabled={carregando || !f.localidade_id}>{carregando ? "Consultando…" : "Consultar"}</button>
      </form>

      {erro && <p className="aviso erro" role="alert">{erro}</p>}

      {res && (
        <>
          <h2>{res.localidade.corredor} — {res.localidade.sentido}
            <span className="etiqueta">{res.localidade.regiao} · via {res.localidade.tipo_via}</span></h2>
          <div className="cartoes">
            <div className="cartao"><span>Média no período</span><strong>{km(res.resumo.km_medio)} km</strong></div>
            <div className="cartao"><span>Máximo registrado</span><strong>{km(res.resumo.km_maximo)} km</strong></div>
            <div className="cartao"><span>{res.agregacao === "hora" ? "Horas" : "Dias"} com lentidão</span>
              <strong>{res.resumo.pontos_com_lentidao} de {res.resumo.pontos}</strong></div>
          </div>
          <Grafico serie={res.serie} agregacao={res.agregacao} />
          <details className="tabela-detalhe">
            <summary>Ver tabela ({res.serie.length} linhas)</summary>
            <table>
              <thead><tr><th>{res.agregacao === "hora" ? "Hora" : "Dia"}</th><th className="num">km médio</th><th className="num">km máximo</th></tr></thead>
              <tbody>
                {res.serie.map((p) => (
                  <tr key={p.instante}>
                    <td>{res.agregacao === "hora" ? p.instante.slice(0, 16).replace("T", " ") : p.instante.slice(0, 10)}</td>
                    <td className="num">{km(p.km_lentidao)}</td><td className="num">{km(p.km_max)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}
