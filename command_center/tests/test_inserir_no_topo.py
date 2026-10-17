"""#312: a inserção fica no topo, e o "Adicionar serviço" escolhe a página do site.

Dono, 16/10: *"Na aba de serviços do site … onde a gente adiciona um novo serviço. Eu preciso que essa parte fique lá
em cima ou tenha um botão de adicionar novo serviço e a gente escolhe em qual página que esse serviço vai estar, e aí
abra essa seção … Se tiver muito serviço, vai acabar que ele vai ficar lá embaixo e a gente não vai ter acesso. Então
eu preciso que essas coisas de inserção fiquem sempre por cima, assim que abrir."*

O que estes testes trancam:
- o seletor de página só oferece as páginas que o site tem de verdade, com o endereço que o site atende;
- o lugar de cada serviço no site (`no_site`) sai da **mesma regra** que monta a página: o que o painel diz que está
  no Arrive and Drive é o que a página mostra, e o kart (ou o add-on) com dois serviços ativos fica fora dos dois;
- `GET /site/servicos` traz as páginas e o lugar de cada serviço;
- o componente `InserirNoTopo` (botão com `aria-expanded`, foco no primeiro campo, painel na tela, Esc fecha, motion
  dos tokens) está em cada lugar da varredura, **antes** da lista daquela tela.
O caminho no navegador, em 360 e 390 px, está em `e2e/test_navegador.py` (os testes com "no topo" no nome).
"""
import os
import re

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar  # noqa: E402
from command_center.providers import servicos_site as sv  # noqa: E402
from command_center.vitrine import paginas, paginas_site as ps  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WEB = os.path.join(RAIZ, "command_center", "web", "src")
SENHA = "senha-forte-123"
HOST = "novo.urace.us"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _onde(con):
    ss = sv.lista(con)
    return {s["name"]: d for s, d in ((s, sv.onde_no_site(ss)[s["id"]]) for s in ss)}


def _pagina_do_kart(con):
    return paginas.arrive_and_drive(HOST, servicos=sv.para_cliente(con, cartao=True), lead_follow=sv.addon_do_site(con))


# --------------------------------------------------------------- as páginas do seletor
def test_as_paginas_do_seletor_sao_as_que_o_site_tem():
    """Sem inventar página: o Arrive and Drive e as três páginas dos cartões, cada uma no endereço que o site atende."""
    from command_center.api.vitrine import PAGINAS
    from command_center.providers.cartoes_site import PAGINAS as DOS_CARTOES
    pgs = sv.paginas_do_site()
    assert [p["id"] for p in pgs] == ["arrive-and-drive", "academy", "pro-team", "for-beginners"]
    assert all(p["caminho"] in PAGINAS for p in pgs), "toda página do seletor é uma página do site"
    assert {p["id"] for p in pgs if p["cartoes"]} == set(DOS_CARTOES), "os cartões entram só nas páginas que têm cartão"
    assert {p["id"]: p["caminho"] for p in pgs if p["cartoes"]} == DOS_CARTOES


# --------------------------------------------------------------- onde cada serviço está hoje
def test_o_kart_que_o_painel_diz_no_arrive_and_drive_e_o_que_a_pagina_mostra(con):
    """Os karts da migração: cada um único e ativo, então cada um está no Arrive and Drive — e a página mostra cada um."""
    onde = sv.onde_no_site(sv.lista(con))
    karts = [s for s in sv.lista(con) if (s["kind"] or "session") == "session" and s["site_kart"]]
    assert karts, "a migração semeia os karts do site"
    html = _pagina_do_kart(con)
    for s in karts:
        assert onde[s["id"]] == {"onde": "kart", "pagina": "arrive-and-drive", "chave": s["site_kart"], "com": []}
        assert f'value="{s["site_kart"]}"' in html, s["site_kart"]


def test_dois_servicos_com_o_mesmo_kart_ficam_fora_do_site_e_o_painel_diz_com_quem(con):
    sid = sv.criar(con, None, {"name": "2-stroke de teste", "price": 100, "site_kart": "2-stroke"})
    onde = _onde(con)
    assert onde["2-stroke de teste"]["onde"] == "repetido"
    assert onde["2-stroke de teste"]["com"] == ["Arrive and Drive 2-stroke"]
    assert onde["Arrive and Drive 2-stroke"]["com"] == ["2-stroke de teste"]
    assert onde["Arrive and Drive 2-stroke"]["pagina"] is None
    assert 'value="2-stroke"' not in _pagina_do_kart(con), "a página tira o kart ambíguo, como o painel avisa"
    sv.mudar(con, None, sid, {"active": False})
    onde = _onde(con)
    assert onde["Arrive and Drive 2-stroke"]["onde"] == "kart" and onde["2-stroke de teste"]["onde"] == "desativado"
    assert 'value="2-stroke"' in _pagina_do_kart(con)


def test_o_add_on_o_plano_e_a_sessao_sem_kart(con):
    onde = _onde(con)
    lf = next(n for n, d in onde.items() if d["chave"] == "Lead and Follow")
    assert onde[lf]["onde"] == "addon" and onde[lf]["pagina"] == "arrive-and-drive"
    assert 'class="agenda-lf addon"><input' in _pagina_do_kart(con), "a caixa do add-on está na reserva"
    # um segundo add-on com a mesma chave: o site tira a caixa, e o painel diz por quê
    sv.criar(con, None, {"name": "Lead and Follow 2", "price": 10, "kind": "addon", "site_kart": "Lead and Follow"})
    assert _onde(con)["Lead and Follow 2"]["onde"] == "repetido" and sv.addon_do_site(con) is None
    # o add-on sem a chave do Lead and Follow o site não mostra
    sv.criar(con, None, {"name": "Fotos do dia", "price": 50, "kind": "addon"})
    assert _onde(con)["Fotos do dia"] == {"onde": "nenhum", "pagina": None, "chave": None, "com": []}
    # o plano vai para a Academy, e a página mostra
    sv.criar(con, None, {"name": "Academy 3 months teste", "price": 2688.43, "kind": "plan", "months": 3, "sessions_month": 4})
    assert _onde(con)["Academy 3 months teste"]["pagina"] == "academy"
    assert "Academy 3 months teste" in ps.academy(HOST, planos=sv.planos_para_cliente(con))
    # a sessão sem kart fica só na área do cliente
    sv.criar(con, None, {"name": "Coaching avulso", "price": 369})
    assert _onde(con)["Coaching avulso"]["onde"] == "area"
    assert "Coaching avulso" in [s["name"] for s in sv.para_cliente(con)]


@pytest.fixture()
def cli(con):
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.commit()
    with TestClient(app, base_url="https://cc.test") as t:
        yield t


def test_a_lista_do_painel_traz_as_paginas_e_onde_cada_servico_esta(cli):
    assert cli.post("/ops/api/auth/login", json={"email": "op@urace.us", "password": SENHA}).status_code == 200
    d = cli.get("/ops/api/site/servicos").json()
    assert d["paginas"] == sv.paginas_do_site()
    assert d["chave_addon"] == "Lead and Follow"
    assert d["servicos"] and all(set(s["no_site"]) == {"onde", "pagina", "chave", "com"} for s in d["servicos"])


# --------------------------------------------------------------- o componente, em cada lugar da varredura
def _src(rel):
    return open(os.path.join(WEB, rel), encoding="utf-8").read()


def test_o_componente_inserir_no_topo():
    c = _src("components/Inserir.tsx")
    assert "export function InserirNoTopo" in c
    for parte in ("aria-expanded={aberto}", "aria-controls={id}", "scrollIntoView", ".focus(", "'Escape'",
                  "prefers-reduced-motion", 'className={`cd ins-painel'):
        assert parte in c, parte
    css = _src("styles/glass.css")
    assert re.search(r"\.ins-painel\{[^}]*animation:ins-entra var\(--dur-media\) var\(--ease-saida\)", css), "motion dos tokens"
    assert re.search(r"@keyframes ins-entra\{from\{opacity:0;transform:[^}]*\}to\{opacity:1;transform:none\}\}", css)
    assert "@media(prefers-reduced-motion:reduce){.ins-painel{animation:none}}" in css


# (arquivo, botão/rótulo do InserirNoTopo, o que desenha a lista daquela tela — o inserir vem antes)
LUGARES = [
    ("pages/SitePublico.tsx", "Adicionar serviço", "l.data.servicos.map(sv =>"),
    ("pages/SitePublico.tsx", "Adicionar cartão", "const lista = cartoes.filter(c => c.page === pg)"),
    ("pages/SitePublico.tsx", "Bloquear datas", '<Section title={tr("Calendário do mês")}>'),
    ("pages/LojaProdutos.tsx", "Novo produto", "l.data.produtos.map(p =>"),
    ("pages/EditorSite.tsx", "Adicionar página", "l.data.paginas.map(p =>"),
    ("pages/System.tsx", "Novo usuário", "(data || []).map(u =>"),
    ("pages/System.tsx", "Nova chave", "(data || []).map(k =>"),
    ("pages/Sdr.tsx", "Pausar a IA numa conversa", "d.data.itens.map(x => <li key={x.lead_id}>"),
    ("pages/Sdr.tsx", "Nova instrução", "d.data.itens.map(i =>"),
    ("pages/Sdr.tsx", "Novo relato", "itens.map(r =>"),
    ("pages/Vendas.tsx", "Anotação (interna)", "evs.map(e =>"),
    ("pages/Client360.tsx", "Adicionar contrato", "m.contracts.map(k =>"),
    ("pages/Garage.tsx", "Novo chassi", "data.chassis.map(c =>"),
    ("pages/Garage.tsx", "Novo motor", "data.engines.map(e => <Linha<Engine>"),
    ("pages/Garage.tsx", "Nova peça", "parts.map(p =>"),
    ("pages/Checklists.tsx", "Adicionar item", "m.itens.map(i =>"),
    ("pages/Races.tsx", "Convidar piloto", "{r.invited.map(i => <div className=\"att\""),
]


@pytest.mark.parametrize("arquivo,rotulo,lista", LUGARES, ids=[r for _, r, _ in LUGARES])
def test_a_insercao_vem_antes_da_lista(arquivo, rotulo, lista):
    s = _src(arquivo)
    assert "import { InserirNoTopo } from '../components/Inserir'" in s
    botao = f'<InserirNoTopo rotulo={{tr("{rotulo}")}}'
    assert s.count(botao) == 1, f"{arquivo}: falta o InserirNoTopo de {rotulo!r}"
    assert s.count(lista) == 1, f"{arquivo}: a marca da lista mudou ({lista!r})"
    assert s.index(botao) < s.index(lista), f"{arquivo}: {rotulo!r} tem de vir antes da lista"


@pytest.mark.parametrize("arquivo,antigo", [
    ("pages/SitePublico.tsx", '<Section title={tr("Novo serviço")}>'),
    ("pages/SitePublico.tsx", '<Section title={tr("Novo cartão")}>'),
    ("pages/LojaProdutos.tsx", '<Section title={tr("Novo produto")}>'),
    ("pages/EditorSite.tsx", '<Section title={tr("Nova página")}>'),
    ("pages/System.tsx", '<Section title={tr("Novo usuário")}>'),
])
def test_o_formulario_do_fim_saiu(arquivo, antigo):
    assert antigo not in _src(arquivo), f"{arquivo}: o formulário antigo do fim da tela continua lá"
