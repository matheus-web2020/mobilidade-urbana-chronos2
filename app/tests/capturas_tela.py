from pathlib import Path

from playwright.sync_api import sync_playwright

SAIDA = Path(__file__).resolve().parents[1] / "docs" / "capturas"
SAIDA.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    nav = p.chromium.launch()
    pg = nav.new_page(viewport={"width": 1280, "height": 900}, locale="pt-BR")
    erros = []
    pg.on("console", lambda m: erros.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://localhost:8000/")

    pg.get_by_role("button", name="Consultar", exact=True).click()
    pg.get_by_text("Média no período").wait_for()
    pg.mouse.move(700, 620)
    pg.screenshot(path=SAIDA / "01_consulta_por_hora.png", full_page=True)

    pg.locator("input[type=date]").nth(1).fill("2023-12-01")
    pg.locator("input[type=date]").nth(0).fill("2023-12-10")
    pg.get_by_role("button", name="Consultar", exact=True).click()
    pg.get_by_role("alert").wait_for()
    pg.screenshot(path=SAIDA / "02_consulta_criterio_invalido.png")

    pg.get_by_role("tab", name="Pontos críticos").click()
    pg.get_by_role("button", name="Classificar").click()
    pg.get_by_text("Regra aplicada").wait_for()
    pg.screenshot(path=SAIDA / "03_criticidade_ranking.png")

    pg.locator("select").first.select_option("SUL")
    pg.get_by_role("button", name="Classificar").click()
    pg.get_by_text("Regra aplicada").wait_for()
    pg.screenshot(path=SAIDA / "04_criticidade_regiao_sul.png")
    nav.close()

print("capturas em", SAIDA)
if erros:
    raise SystemExit(f"erros no console do navegador: {erros}")
