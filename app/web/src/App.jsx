import React, { useEffect, useState } from "react";
import { obter } from "./api.js";
import Consulta from "./Consulta.jsx";
import Criticidade from "./Criticidade.jsx";

export default function App() {
  const [aba, setAba] = useState("consulta");
  const [saude, setSaude] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    obter("saude").then(setSaude).catch((e) => setErro(e.message));
  }, []);

  return (
    <div className="pagina">
      <header className="topo">
        <div>
          <h1>Lentidão viária em São Paulo</h1>
          <p className="sub">
            Consulta por corredor e classificação inicial de criticidade · dados da CET (Monitrans)
            {saude && ` · ${saude.localidades} corredores · ${saude.inicio.slice(0, 10)} a ${saude.fim.slice(0, 10)}`}
          </p>
        </div>
        <nav className="abas" role="tablist">
          <button role="tab" aria-selected={aba === "consulta"} onClick={() => setAba("consulta")}>Consultar mobilidade</button>
          <button role="tab" aria-selected={aba === "criticidade"} onClick={() => setAba("criticidade")}>Pontos críticos</button>
        </nav>
      </header>
      {erro && <p className="aviso erro">{erro}</p>}
      <main>{aba === "consulta" ? <Consulta /> : <Criticidade />}</main>
      <footer className="rodape">
        Indicador: km de pista em lentidão (média horária dos registros da CET a cada 30 min; hora sem registro = 0).
        Fonte: Base de dados sobre lentidão por trechos – CET, 2022–2023 (CC BY).
      </footer>
    </div>
  );
}
