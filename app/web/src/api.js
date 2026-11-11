export async function obter(caminho, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null));
  const r = await fetch(`/api/v1/${caminho}${qs.size ? `?${qs}` : ""}`);
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof corpo.detail === "string" ? corpo.detail : "Não foi possível concluir a consulta.");
  return corpo;
}

export async function enviar(caminho, dados) {
  const r = await fetch(`/api/v1/${caminho}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
  });
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof corpo.detail === "string" ? corpo.detail : "Não foi possível salvar.");
  return corpo;
}

export const km = (v, casas = 2) =>
  v == null ? "–" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
