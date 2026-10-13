"""#223: Administrativo › Como usar — os guias no painel e o MD para a IA.

Dono, 13/10: *"o guia de como usar a plataforma, cada função, tudo totalmente descrito … MD para
IA também, uma parte onde a pessoa consegue baixar o MD para colocar no chat da IA dela"*.
"""
import os
import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar

SENHA = "senha-forte-123"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cli():
    pasta = tempfile.mkdtemp()
    os.environ["CC_DB_PATH"] = os.path.join(pasta, "cc.sqlite")
    os.environ["URACE_DIR"] = pasta
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    mec = auth.criar_usuario(c, "mec@urace.us", "Mec", "OPERATOR", SENHA)
    c.execute("UPDATE users SET cargo='MECANICO' WHERE id=?", (mec,)); c.commit()
    c.close()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200


def test_lista_os_guias_e_le_cada_um_com_um_h1_so(cli):
    entra(cli, "op@urace.us")
    guias = cli.get("/ops/api/guia").json()["guias"]
    assert [g["slug"] for g in guias] == ["geral", "vendas", "mecanicos", "suits", "conectar-ia"]
    for g in guias:
        h = cli.get(f"/ops/api/guia/{g['slug']}").json()["html"]
        assert "<h1" not in h, "a tela já tem o h1; o guia começa no h2"
        assert "<table>" not in h.replace('<div class="guia-tbl"><table>', ""), "tabela larga rola na caixa, não na página"
    h = cli.get("/ops/api/guia/geral").json()["html"]
    assert 'href="/ops/como-usar/vendas"' in h and 'href="/ops/como-usar/suits"' in h, "link entre guias vira a tela"
    assert 'id="1-para-que-serve-o-command-center"' in h and 'href="#1-para-que-serve-o-command-center"' in h
    assert not re.search(r'href="[^"]*\.md[#"]', h), "nenhum link para .md quebrado dentro do painel"
    assert cli.get("/ops/api/guia/nao-existe").status_code == 404


def test_baixa_o_md_e_o_pdf(cli):
    entra(cli, "op@urace.us")
    r = cli.get("/ops/api/guia/vendas.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"] and r.text.startswith("# ")
    assert cli.get("/ops/api/guia/mecanicos.pdf").content[:4] == b"%PDF"
    assert cli.get("/ops/api/guia/vendas.pdf").status_code == 404


def test_md_para_a_ia_junta_tudo_e_nao_leva_segredo(cli):
    entra(cli, "op@urace.us")
    r = cli.get("/ops/api/guia/para-ia.md")
    assert r.status_code == 200 and "urace-command-center-para-ia.md" in r.headers["content-disposition"]
    t = r.text
    assert t.startswith("# URACE Command Center — instruções para a IA")
    for frase in ("urace_operacoes", "urace_api", "confirmar=true", "https://ops.urace.us/ops/mcp", "Liberar para operar"):
        assert frase in t, frase
    for arq in ("playbooks/playbook-geral.md", "playbooks/playbook-vendas.md", "suits-guia-do-lucas.md"):
        primeira = (REPO / "docs" / arq).read_text(encoding="utf-8").splitlines()[0]
        assert primeira in t, arq
    assert not re.search(r"(Bearer\s+[A-Za-z0-9_\-\.]{20,}|sk-[A-Za-z0-9]{10,}|ccak_[A-Za-z0-9]{10,})", t), "sem chave"


def test_o_box_nao_abre_o_como_usar(cli):
    entra(cli, "mec@urace.us")
    assert cli.get("/ops/api/guia").status_code == 403, "o guia de vendas tem preço; o box tem o PDF dele"


def test_toda_tela_do_menu_do_escritorio_esta_no_guia_geral():
    """'cada função, tudo totalmente descrito': tela nova no menu sem linha no guia falha aqui."""
    shell = (REPO / "command_center/web/src/components/Shell.tsx").read_text(encoding="utf-8")
    escritorio = shell[shell.index('</nav> : <nav className="nav" aria-label={tr("Principal")}>'):]
    escritorio = escritorio[len("</nav>"):escritorio.index("</nav>", len("</nav>"))]
    rotas = sorted(set(re.findall(r'<NL to="([^"]+)"', escritorio)))
    guia = (REPO / "docs/playbooks/playbook-geral.md").read_text(encoding="utf-8")
    faltam = [r for r in rotas if f"`/ops{r}`" not in guia]
    assert not faltam, f"telas do menu sem linha no playbook geral: {faltam}"
