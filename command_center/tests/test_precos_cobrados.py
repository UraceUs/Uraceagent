"""Preços já cobrados: o AI Command fecha invoice de peça sem perguntar o valor ao dono.

Dono, 28/09: montando as invoices do Bryan, do Frankie e do Brody, a IA travou pedindo o valor
de cada peça ("não consigo puxar o histórico de faturas nem o catálogo de peças"). Os valores
estavam nas invoices já enviadas. Estes testes trancam o caminho inteiro: o conector do
QuickBooks devolve o id do item em cada linha, a sincronia guarda as linhas no espelho, o
painel resume o histórico, o comando leva a tabela para a IA e a conferência aceita valor que
já foi cobrado do mesmo item — sem inventar nada quando não há histórico.
"""
import os
import sys
import tempfile

import pytest

os.environ["URACE_ENV"] = "/nao/existe"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adminai", "mcp"))

from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402


def _inv(num, data, cliente, email, cref, linhas, total=None):
    return {"id": f"tx-{num}", "numero": str(num), "cliente": cliente, "cliente_id": cref, "email": email,
            "emitida_em": data, "vence_em": data, "total": total or sum(l["total"] for l in linhas),
            "saldo": 0, "status": "paid", "linhas": linhas}


def _l(item, item_id, unit, qtd=1, desc=None):
    return {"item": item, "item_id": item_id, "qtd": qtd, "unitario": unit, "total": unit * qtd, "descricao": desc}


INVOICES = [
    _inv(2101, "2026-09-20", "Pablo Santiago", "pablo@x.com", "485",
         [_l("Rk Non Oring Chain", "71", 65, desc="Chain 108"), _l("Fuel mix", "72", 40), _l("Engine", "73", 250)]),
    _inv(2080, "2026-08-10", "Carlos Reis", "carlos@x.com", "501",
         [_l("Rk Non Oring Chain", "71", 60, desc="Chain 104"), _l("Tonykart Rear bumper fixing bolt", "74", 12, qtd=2)]),
    _inv(2050, "2026-07-01", "Ana Lima", "ana@x.com", "502",
         [_l("Rk Non Oring Chain", "71", 65), _l("MG SH2 Red Tires Jr/Sr", "75", 280, desc="Set of tires (dry)")]),
]


@pytest.fixture
def con(monkeypatch):
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-precos.sqlite")
    c = conectar(); aplicar_schema(c)
    from command_center.providers import sync
    monkeypatch.setattr(sync, "chamar", lambda s, a, **k: {"invoices": INVOICES} if a == "qbo_invoices" else [])
    yield c
    c.close()


def _sincroniza(con):
    from command_center.providers import sync
    r = sync.sync_qbo(con)
    con.commit()
    return r


# ------------------------------------------------------------------ espelho
def test_a_sincronia_guarda_as_linhas_de_cada_invoice(con):
    assert _sincroniza(con)["ok"] is True
    ls = todos(con, "SELECT item_id, item_name, description, qty, unit_price FROM invoice_lines ORDER BY invoice_id, line_no")
    assert len(ls) == 7
    assert {"item_id": "71", "item_name": "Rk Non Oring Chain", "description": "Chain 108", "qty": 1, "unit_price": 65} in [dict(x) for x in ls]


def test_invoice_editada_no_quickbooks_reescreve_as_linhas_sem_duplicar(con):
    _sincroniza(con)
    _sincroniza(con)                                      # de novo: nada duplica
    assert um(con, "SELECT COUNT(*) AS n FROM invoice_lines")["n"] == 7
    INVOICES[1]["linhas"] = INVOICES[1]["linhas"][:1]     # alguém tirou uma linha lá
    try:
        _sincroniza(con)
        iid = um(con, "SELECT id FROM invoices WHERE doc_number='2080'")["id"]
        assert [r["item_name"] for r in todos(con, "SELECT item_name FROM invoice_lines WHERE invoice_id=?", (iid,))] == ["Rk Non Oring Chain"]
    finally:
        INVOICES[1]["linhas"].append(_l("Tonykart Rear bumper fixing bolt", "74", 12, qtd=2))


def test_resposta_sem_o_campo_de_linhas_nao_apaga_o_que_existe(con):
    """Resposta antiga (sem `linhas`) não é 'invoice sem linhas': não mexe no espelho."""
    _sincroniza(con)
    from command_center.providers import sync
    sem = [{k: v for k, v in i.items() if k != "linhas"} for i in INVOICES]
    sync.chamar = lambda s, a, **k: {"invoices": sem} if a == "qbo_invoices" else []
    sync.sync_qbo(con); con.commit()
    assert um(con, "SELECT COUNT(*) AS n FROM invoice_lines")["n"] == 7


# ------------------------------------------------------------------ resumo
def test_tabela_de_precos_por_item(con):
    from command_center.providers import precos_cobrados as pc
    _sincroniza(con)
    chain = next(t for t in pc.tabela(con) if t["item_id"] == "71")
    assert chain["vezes"] == 3 and chain["ultimo"] == 65 and chain["ultimo_em"] == "2026-09-20"
    assert chain["mais_comum"] == 65 and chain["minimo"] == 60 and chain["maximo"] == 65
    assert pc.tabela(con)[0]["item_id"] == "71"           # o mais cobrado vem primeiro


def test_historico_pela_descricao_da_linha(con):
    """'Set of tires (dry)' está na descrição, não no nome do item: também acha."""
    from command_center.providers import precos_cobrados as pc
    _sincroniza(con)
    h = pc.historico(con, termo="set of tires")
    assert len(h) == 1 and h[0]["unit_price"] == 280 and h[0]["item_id"] == "75"
    assert [x["description"] for x in pc.historico(con, termo="chain 104")] == ["Chain 104"]


def test_ja_cobrado(con):
    from command_center.providers import precos_cobrados as pc
    _sincroniza(con)
    assert pc.ja_cobrado(con, "71", 60)["doc_number"] == "2080"
    assert pc.ja_cobrado(con, "71", 61) is None
    assert pc.ja_cobrado(con, None, 60) is None


# ------------------------------------------------------------------ o comando
PERGUNTA_DA_IA = """Ainda falta o que me trava de verdade: os preços das peças.
- Set of tires (dry)
- Chain — 108, 112, 104, 102
- Fuel mix (por abastecimento)
- Rear bumper bolt (un.)
- Rear bumper rubber"""


def test_o_comando_leva_os_precos_das_pecas_da_conversa(con):
    """A lista de peças estava na pergunta anterior da IA; o dono respondeu só com e-mails."""
    from command_center.api import auth, motor
    _sincroniza(con)
    uid = auth.criar_usuario(con, "dono@urace.us", "Dono", "ADMIN", "senha-forte-123")
    inserir(con, "ai_commands", user_id=uid, text="monte uma invoice por piloto com todos os dias", session_key="s",
            status="DONE", output=PERGUNTA_DA_IA)
    con.commit()
    ctx = motor.contexto_de_precos(con, "Frankie enzo.iadevaia@gmail.com; Jill hawaiicampers@gmail.com; Bryan pablo@x.com", uid)
    assert "PREÇOS JÁ COBRADOS NO QUICKBOOKS" in ctx
    assert "Rk Non Oring Chain (item_id 71): último $65.00 em 2026-09-20" in ctx
    assert "Fuel mix (item_id 72): último $40.00" in ctx
    assert "Tonykart Rear bumper fixing bolt (item_id 74): último $12.00" in ctx
    assert "MG SH2 Red Tires Jr/Sr (item_id 75)" in ctx
    assert "Cliente no QuickBooks de pablo@x.com: cliente_id=485" in ctx
    assert "enzo.iadevaia@gmail.com: sem invoice no espelho" in ctx


def test_conversa_sem_invoice_nem_preco_nao_leva_tabela(con):
    from command_center.api import motor
    _sincroniza(con)
    assert motor.contexto_de_precos(con, "quem corre domingo?") == ""


def test_sem_historico_diz_que_nao_ha_e_nao_inventa(con):
    from command_center.api import motor
    ctx = motor.contexto_de_precos(con, "monta a invoice do Bryan")
    assert "ainda não tem as linhas das invoices" in ctx and "$" not in ctx


def test_o_prompt_do_ai_command_leva_o_bloco(con, monkeypatch):
    """Ponta a ponta pela rota: o texto que vai ao agente contém a tabela."""
    from fastapi.testclient import TestClient
    from command_center.api import auth, ia
    from command_center.api.main import app
    _sincroniza(con)
    auth.criar_usuario(con, "op@urace.us", "Op", "OPERATOR", "senha-forte-123"); con.commit()
    monkeypatch.setattr(ia, "RUNNER", lambda texto, sk: (True, "ok\nACAO: nenhuma", None))
    with TestClient(app, base_url="https://cc.test") as c:
        assert c.post("/ops/api/auth/login", json={"email": "op@urace.us", "password": "senha-forte-123"}).status_code == 200
        r = c.post("/ops/api/ai/commands", json={"text": "invoice do Pablo: chain e fuel mix"},
                   headers={"X-CSRF": c.cookies.get("cc_csrf")})
        assert r.status_code == 202
    prompt = um(con, "SELECT prompt FROM ai_commands WHERE id=?", (r.json()["id"],))["prompt"]
    assert "Rk Non Oring Chain (item_id 71)" in prompt and "Fuel mix (item_id 72)" in prompt


def test_o_sufixo_manda_usar_a_tabela_antes_de_perguntar():
    from command_center.api import ia
    assert "PREÇOS JÁ COBRADOS NO QUICKBOOKS" in ia.SUFIXO and "qbo_historico_precos" in ia.SUFIXO


# ------------------------------------------------------------------ conferência
def _invoice(unit):
    return {"cliente_id": "485", "email": "pablo@x.com",
            "linhas": [{"item_id": "71", "quantidade": 1, "unitario": unit, "descricao": "Chain 108 - Bryan - 2026-10-03"}]}


def test_valor_ja_cobrado_do_item_nao_pede_conferencia(con):
    from command_center.api import acoes
    _sincroniza(con)
    args, prob = acoes.normalizar_invoice(_invoice(60), "", None, None, con)
    assert prob == [] and "_conferir" not in args


def test_valor_nunca_cobrado_continua_marcado_para_conferir(con):
    from command_center.api import acoes
    _sincroniza(con)
    args, _ = acoes.normalizar_invoice(_invoice(99), "", None, None, con)
    assert args.get("_conferir") and "invoice anterior" in args["_conferir"][0]


def test_preco_final_do_estoque_nao_pede_conferencia(con):
    """29/09: o preço final da peça, definido no estoque (custo + margem), é o valor da
    invoice. Vindo de lá, a linha não é marcada "de onde veio este valor?"."""
    from command_center.api import acoes
    from command_center.providers import estoque
    _sincroniza(con)
    estoque.criar_item(con, "peca", "Chain 108", category="hardware", cost=80, markup="$19")
    args, _ = acoes.normalizar_invoice(_invoice(99), "", None, None, con)
    assert "_conferir" not in args
    args, _ = acoes.normalizar_invoice(_invoice(98), "", None, None, con)
    assert args.get("_conferir"), "valor que não bate com nada continua marcado"


# ------------------------------------------------------------------ conector do QuickBooks
@pytest.fixture
def qb(monkeypatch, tmp_path):
    import quickbooks_mcp as q
    monkeypatch.setenv("QBO_CLIENT_ID", "cid"); monkeypatch.setenv("QBO_CLIENT_SECRET", "sec"); monkeypatch.setenv("QBO_REALM_ID", "1")
    monkeypatch.setenv("QBO_TOKEN_JSON", str(tmp_path / "t.json"))
    q.gravar_token({"refresh_token": "r", "realm_id": "1"})
    consultas = []

    def linha(nome, iid, unit, desc=None):
        return {"DetailType": "SalesItemLineDetail", "Amount": unit, "Description": desc,
                "SalesItemLineDetail": {"ItemRef": {"name": nome, "value": iid}, "Qty": 1, "UnitPrice": unit}}
    faturas = [{"Id": "9", "DocNumber": "2101", "TxnDate": "2026-09-20", "CustomerRef": {"value": "485", "name": "Pablo"},
                "TotalAmt": 105, "Balance": 0, "Line": [linha("Rk Non Oring Chain", "71", 65, "Chain 108"), linha("Fuel mix", "72", 40),
                                                         {"DetailType": "SubTotalLineDetail", "Amount": 105}]},
               {"Id": "8", "DocNumber": "2080", "TxnDate": "2026-08-10", "CustomerRef": {"value": "501", "name": "Carlos"},
                "TotalAmt": 60, "Balance": 0, "Line": [linha("Rk Non Oring Chain", "71", 60, "Chain 104")]}]

    def _query(sql):
        consultas.append(sql)
        return {"Invoice": faturas}
    monkeypatch.setattr(q, "_query", _query)
    return q, consultas


def test_linha_de_invoice_do_conector_traz_o_id_do_item(qb):
    q, _ = qb
    r = q._resumo_invoice({"Id": "9", "Line": [{"DetailType": "SalesItemLineDetail", "Amount": 65,
                                                "SalesItemLineDetail": {"ItemRef": {"name": "Chain", "value": "71"}, "Qty": 1, "UnitPrice": 65}}]})
    assert r["linhas"][0]["item_id"] == "71"


def test_conector_historico_de_precos(qb):
    q, consultas = qb
    r = q.qbo_historico_precos(["chain", "fuel mix", "nada disso"], cliente_id="485")
    chain, fuel, nada = r["resultado"]
    assert chain["resumo"] == {"vezes": 2, "ultimo": 65.0, "ultimo_em": "2026-09-20", "mais_comum": 65.0, "minimo": 60.0, "maximo": 65.0}
    assert chain["cobrancas"][0]["item_id"] == "71" and fuel["resumo"]["ultimo"] == 40.0
    assert nada["found"] is False and nada["resumo"] is None
    assert "CustomerRef = '485'" in consultas[0] and "startposition 1 maxresults 1000" in consultas[0]


def test_conector_historico_sem_termo_recusa(qb):
    q, _ = qb
    from mcp_stdio import ErroFerramenta
    with pytest.raises(ErroFerramenta):
        q.qbo_historico_precos([])


def test_historico_e_consulta_nao_acao():
    from command_center.api import acoes
    assert acoes.eh_consulta("qbo_historico_precos")
