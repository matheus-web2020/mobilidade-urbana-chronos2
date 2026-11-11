import React, { useEffect, useState } from "react";
import { enviar, km, obter } from "./api.js";

const NIVEIS = ["crítico", "alto", "moderado", "baixo"];
const ICONE = { crítico: "▲▲", alto: "▲", moderado: "●", baixo: "▽" };

export default function Criticidade() {
  const [regioes, setRegioes] = useState([]);
  const [f, setF] = useState({ inicio: "2023-11-01", fim: "2023-11-30", regiao: "", ordem: "indice" });
  const [res, setRes] = useState(null);
  const [filtroNivel, setFiltroNivel] = useState("");
  const [erro, setErro] = useState("");
  const [limites, setLimites] = useState(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    obter("regioes").then(setRegioes).catch(() => {});
    obter("parametros/criticidade").then((p) => setLimites(p.limites)).catch(() => {});
  }, []);

  async function consultar(ev) {
    ev?.preventDefault();
    setErro(""); setRes(null);
    try { setRes(await obter("criticidade", f)); } catch (e) { setErro(e.message); }
  }

  async function salvarLimites(ev) {
    ev.preventDefault();
    setMsg("");
    try {
      const p = await enviar("parametros/criticidade", { limites: limites.map(Number) });
      setLimites(p.limites); setMsg("Limites salvos."); if (res) consultar();
    } catch (e) { setMsg(e.message); }
  }

  const itens = res ? res.itens.filter((i) => !filtroNivel || i.nivel === filtroNivel) : [];

  return (
    <section>
      <form className="filtros" onSubmit={consultar}>
        <label>Início<input type="date" value={f.inicio} onChange={(e) => setF({ ...f, inicio: e.target.value })} required /></label>
        <label>Fim<input type="date" value={f.fim} onChange={(e) => setF({ ...f, fim: e.target.value })} required /></label>
        <label>Região
          <select value={f.regiao} onChange={(e) => setF({ ...f, regiao: e.target.value })}>
            <option value="">Todas</option>
            {regioes.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>Ordenar por
          <select value={f.ordem} onChange={(e) => setF({ ...f, ordem: e.target.value })}>
            <option value="indice">Índice (maior primeiro)</option><option value="nome">Nome do corredor</option>
          </select>
        </label>
        <button type="submit">Classificar</button>
      </form>

      {erro && <p className="aviso erro" role="alert">{erro}</p>}

      {res && (
        <>
          <p className="regra"><strong>Regra aplicada:</strong> {res.regra}</p>
          <div className="chips" role="group" aria-label="Filtrar por nível">
            <button className={!filtroNivel ? "ativo" : ""} onClick={() => setFiltroNivel("")}>Todos ({res.itens.length})</button>
            {NIVEIS.map((n) => (
              <button key={n} className={`nivel-${n === "crítico" ? "critico" : n} ${filtroNivel === n ? "ativo" : ""}`}
                      onClick={() => setFiltroNivel(n)}>
                {ICONE[n]} {n} ({res.contagem_por_nivel[n]})
              </button>
            ))}
          </div>
          <table className="ranking">
            <thead>
              <tr><th className="num">#</th><th>Corredor</th><th>Sentido</th><th>Região</th>
                <th className="num">Índice (km)</th><th className="num">Horas com lentidão</th><th>Nível</th></tr>
            </thead>
            <tbody>
              {itens.map((i) => (
                <tr key={i.id}>
                  <td className="num">{i.posicao}</td><td>{i.corredor}</td><td>{i.sentido}</td><td>{i.regiao}</td>
                  <td className="num">{km(i.indice, 3)}</td>
                  <td className="num">{Math.round(100 * i.frac_horas_com_lentidao)}%</td>
                  <td><span className={`selo nivel-${i.nivel === "crítico" ? "critico" : i.nivel}`}>{ICONE[i.nivel]} {i.nivel}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {limites && (
        <details className="admin">
          <summary>Parâmetros da regra (administrador)</summary>
          <form className="filtros" onSubmit={salvarLimites}>
            {["moderado a partir de", "alto a partir de", "crítico a partir de"].map((rot, k) => (
              <label key={k}>{rot} (km)
                <input type="number" step="0.0001" min="0" value={limites[k]}
                       onChange={(e) => setLimites(limites.map((v, j) => (j === k ? e.target.value : v)))} />
              </label>
            ))}
            <button type="submit">Salvar limites</button>
            {msg && <span className="msg">{msg}</span>}
          </form>
        </details>
      )}
    </section>
  );
}
