"""Rate Card do Drive → preço no QuickBooks.

Sem rede: a planilha é uma grade montada aqui e o QuickBooks é um dublê. O que se prova é
o que o dono decidiu em 18/09: a Rate Card manda, peça não muda, item fora do mapa revisado
não é tocado, e a rotina só roda segunda-feira.
"""
import datetime
import os
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import auth, precos  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, todos, um  # noqa: E402
from command_center.providers import ratecard  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"

GRADE = [
    ["URACE RATE CARD 2026"],
    ["Engine Rental — 100cc — National Event", "Engine Rental", "per event", "$1.250,00"],
    ["Shop — Labor (hourly)", "Shop Service", "per hour", "$95,00"],
    ["Shop — Tire Change (labor)", "Shop Service", "each", "$35,00"],
    ["Summer Camp — Baby Kart (4-7) — 3 Days", "Summer Camp", "package", "$2.069,93"],
    ["Fuel — Gasolina", "Fuel", "gal", "$12,00"],                    # família "ignorar"
    ["Total", "", "", "$9.999,00"],                                  # linha de totalização
    ["Chain — OTK", "Parts", "each", "$25,00"],                      # não está no mapa
    ["Arrive & Drive — Micro/Mini — Locals (3 days)", "", "", "$3.000", "$3.900"],   # dois preços: ambígua
]

CATALOGO = [
    {"id": "10", "nome": "100cc Engine Rental | National Event",
     "nome_completo": "Rental:100cc Engine Rental | National Event", "preco": 1200},
    {"id": "11", "nome": "Shop hour", "nome_completo": "Service:Shop hour", "preco": 95},
    {"id": "12", "nome": "Tire change labor", "nome_completo": "Service:Tire change labor", "preco": 42.6},
    {"id": "13", "nome": "Chain OTK", "nome_completo": "Parts:Chain OTK", "preco": 25},
]


class QBOFalso:
    """Dublê do módulo que escreve no QuickBooks."""
    def __init__(self):
        self.precos, self.criados, self.recusa = [], [], set()

    def preco_item_sistema(self, item_id, preco, quem="painel"):
        if str(item_id) in self.recusa:
            raise RuntimeError("RECUSADO: é peça, e peça mantém o preço")
        self.precos.append((str(item_id), round(float(preco), 2), quem))
        return {"aplicado": True, "id": item_id, "preco": preco}

    def criar_item_sistema(self, nome, preco=0, descricao=None):
        self.criados.append((nome, round(float(preco), 2)))
        return {"id": "novo-" + str(len(self.criados)), "nome": nome, "preco": preco}


@pytest.fixture()
def cli(monkeypatch):
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc.sqlite")
    con = conectar(); aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "op@urace.us", "Operador", "OPERATOR", SENHA)
    con.commit(); con.close()
    monkeypatch.setattr(ratecard, "ler_planilha", lambda *a, **k: GRADE)
    monkeypatch.setattr(precos, "_itens_do_catalogo", lambda: CATALOGO)
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email="admin@urace.us"):
    cli.cookies.clear()
    assert cli.post(f"{B}/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


# --------------------------------------------------------------------- número
@pytest.mark.parametrize("texto,esperado", [
    ("$2.756,90", 2756.90),     # milhar com ponto, decimal com vírgula
    ("$1,250/even", 1250.0),    # milhar com vírgula
    ("$2.400", 2400.0),         # milhar com ponto, sem decimal
    ("$689,23", 689.23),
    ("$350/day", 350.0),
    ("$95/h", 95.0),
    ("$5 each", 5.0),
    ("sem preço", None),
])
def test_le_as_duas_notacoes_da_planilha(texto, esperado):
    """A planilha mistura $1,250 e $2.756,90 — o primeiro parser leu 2.756,90 como 2,76."""
    v = ratecard.preco(texto)
    assert (v is None and esperado is None) or abs(v - esperado) < 0.005


def test_extrai_so_linha_com_um_preco_e_ignora_totalizacao():
    e = ratecard.extrair(GRADE)
    nomes = [x["nome"] for x in e]
    assert "Total" not in nomes                                   # linha de totalização
    assert not any("Arrive & Drive" in n for n in nomes)          # dois preços na mesma linha
    assert "Shop — Labor (hourly)" in nomes


# --------------------------------------------------------------------- plano
def test_plano_respeita_o_mapa_revisado_e_as_familias():
    p = ratecard.planejar(ratecard.extrair(GRADE), CATALOGO)
    muda = {x["qbo"]: (x["atual"], x["novo"]) for x in p["atualizar"]}
    assert muda["Rental:100cc Engine Rental | National Event"] == (1200.0, 1250.0)
    assert muda["Service:Tire change labor"] == (42.6, 35.0)
    assert [x["qbo"] for x in p["iguais"]] == ["Service:Shop hour"]
    assert [x["nome"] for x in p["criar"]] == ["Summer Camp — Baby Kart (4-7) — 3 Days"]   # família "criar"
    assert not any("Fuel" in x["nome"] for x in p["duvida"] + p["criar"])                  # família "ignorar"
    assert any("Chain" in x["nome"] for x in p["duvida"])                                  # fora do mapa: pergunta


def test_peca_nunca_muda_de_preco():
    grade = GRADE + [["Chain — OTK", "Parts", "each", "$99,00"]]
    mapa = ratecard.mapa()
    mapa["pares"].append({"rc": "Chain — OTK", "qbo": "Parts:Chain OTK", "qbo_id": "13", "acao": "atualizar"})
    import unittest.mock as mock
    with mock.patch.object(ratecard, "mapa", lambda: mapa):
        p = ratecard.planejar(ratecard.extrair(grade), CATALOGO)
    assert not any("Chain" in (x["qbo"] or "") for x in p["atualizar"])


# --------------------------------------------------------------------- aplicar
def test_aplicar_escreve_preco_e_cria_o_aprovado(cli, monkeypatch):
    falso = QBOFalso()
    monkeypatch.setitem(__import__("sys").modules, "adminai.mcp.quickbooks_mcp", falso)
    h = entra(cli)
    r = cli.post(f"{B}/precos/aplicar", json={"criar": True}, headers=h)
    assert r.status_code == 200, r.text
    saida = r.json()
    assert {p[0] for p in falso.precos} == {"10", "12"}            # os dois com preço diferente
    assert dict((p[0], p[1]) for p in falso.precos)["10"] == 1250.0
    assert falso.criados and falso.criados[0][1] == 2069.93
    assert not saida["falhas"]
    con = conectar()
    ev = todos(con, "SELECT * FROM audit_logs WHERE event='precos.item'")
    assert len(ev) == 2 and all(x["actor"].startswith("user:") for x in ev)
    con.close()


def test_falha_em_um_item_nao_derruba_os_outros(cli, monkeypatch):
    falso = QBOFalso(); falso.recusa.add("12")
    monkeypatch.setitem(__import__("sys").modules, "adminai.mcp.quickbooks_mcp", falso)
    h = entra(cli)
    saida = cli.post(f"{B}/precos/aplicar", json={"criar": False}, headers=h).json()
    assert [f["qbo"] for f in saida["falhas"]] == ["Service:Tire change labor"]
    assert [f["qbo"] for f in saida["feitos"]] == ["Rental:100cc Engine Rental | National Event"]
    assert not falso.criados                                       # criar=False


def test_operador_nao_mexe_em_preco(cli):
    h = entra(cli, "op@urace.us")
    assert cli.post(f"{B}/precos/aplicar", json={}, headers=h).status_code == 403
    assert cli.get(f"{B}/precos/plano").status_code == 403


def test_plano_nao_escreve_nada(cli, monkeypatch):
    falso = QBOFalso()
    monkeypatch.setitem(__import__("sys").modules, "adminai.mcp.quickbooks_mcp", falso)
    entra(cli)
    r = cli.get(f"{B}/precos/plano").json()
    assert r["resumo"].startswith("2 para atualizar")
    assert not falso.precos and not falso.criados


# --------------------------------------------------------------------- rotina
def test_rotina_so_roda_na_segunda(cli, monkeypatch):
    falso = QBOFalso()
    monkeypatch.setitem(__import__("sys").modules, "adminai.mcp.quickbooks_mcp", falso)
    con = conectar()
    terca = precos.rodar_semanal(con, hoje=datetime.date(2026, 9, 22))
    assert "pulou" in terca and not falso.precos
    segunda = precos.rodar_semanal(con, hoje=datetime.date(2026, 9, 21))
    assert len(segunda["feitos"]) >= 2
    # o que ficou sem par vira pergunta no painel, uma por vez
    ev = um(con, "SELECT * FROM ai_events WHERE kind='precos.duvida'")
    assert ev and "sem item ligado" in ev["summary"]
    precos.rodar_semanal(con, hoje=datetime.date(2026, 9, 21))
    assert um(con, "SELECT COUNT(*) AS n FROM ai_events WHERE kind='precos.duvida'")["n"] == 1
    con.close()


def test_a_rotina_semanal_esta_cadastrada():
    con = conectar()
    r = um(con, "SELECT * FROM automation_rules WHERE name='ratecard_semanal'")
    assert r and r["enabled"] == 1 and "07:30" in (r["schedule"] or "")
    p = um(con, "SELECT policy FROM action_policies WHERE action='qbo_atualizar_preco'")
    assert p and p["policy"] == "SAFE"
    con.close()


# --------------------------------------------------------------------- correções do dono
QUEBRADOS = [
    {"id": "20", "nome": "State Events (3 days / Extra day at $600)",
     "nome_completo": "Service:State Events (3 days / Extra day at $600)", "preco": 2.4},
    {"id": "21", "nome": "Travel Fee", "nome_completo": "Travel Fee", "preco": 250},
    {"id": "22", "nome": "FLKC Arrive and drive JR/SR",
     "nome_completo": "Service:FLKC Arrive and drive JR/SR", "preco": 999},
]


def test_corrige_preco_quebrado_uma_vez_so():
    """$2.400 cadastrado como $2,40. Corrige; depois de corrigido não repete."""
    p = ratecard.planejar([], QUEBRADOS)
    muda = {x["qbo"]: (x["atual"], x["novo"]) for x in p["atualizar"]}
    assert muda["Service:State Events (3 days / Extra day at $600)"] == (2.4, 2400.0)
    assert "Travel Fee" not in muda                       # já está nos 250 que o dono disse

    corrigido = [dict(QUEBRADOS[0], preco=2400)] + QUEBRADOS[1:]
    assert not [x for x in ratecard.planejar([], corrigido)["atualizar"] if "State Events" in x["qbo"]]


def test_correcao_nao_atropela_quem_mexeu_no_preco():
    """O item do FLKC estava 4,10 e hoje está 999: alguém mudou. Isso é pergunta, não escrita."""
    p = ratecard.planejar([], QUEBRADOS)
    assert not [x for x in p["atualizar"] if "FLKC" in x["qbo"]]
    assert any("FLKC" in d["nome"] and "alguém mexeu" in d["porque"] for d in p["duvida"])
