"""Vendas: os furos do #204, com a decisão do dono de 14/10.

1–3. Invoice fora da tabela NÃO sai sem aprovação ("precisa confirmar o valor da invoice"): o
     botão de passo (`step/qbo`) não passa por cima; quem libera é o gerente ou o dono, vendo o
     valor e o preço da tabela; o preço da tabela vem do catálogo (nunca do valor da venda); e a
     IA confere igual — operador confirmando a ação dela não basta.
4.   "O depósito de segurança é cobrado em venda manual ou automática": a venda manual leva a
     mesma linha "Security deposit" da automática, e o operador cobra só o depósito quando faltou.
5.   "Sim, é para criar um card de um irmão": mesmo responsável, e-mail e telefone; piloto
     próprio; os dois cards nunca se unem e o serviço de um não cai no do outro.
7.   Retorno de venda vencido aparece em Precisa de atenção.
8.   A confirmação do MCP cobre o chat do Kommo (/crm/*).
#310 (Liberar invoice): nenhuma invoice fica sem saída (a desligada pelo closer fora da tabela e a
     do fechamento de antes de 14/10 o gerente libera) e nenhuma sai duas vezes (passo, fechar de
     novo, IA, clique duplo no Liberar). O reenvio pelo passo fica na auditoria.

Nada fala com o QuickBooks de verdade: `chamar` é um falso que anota cada invoice.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

os.environ["URACE_ENV"] = "/nao/existe"

from fastapi.testclient import TestClient  # noqa: E402

from command_center.api import acoes_painel, atencao, auth, mcp_operar, vendas  # noqa: E402
from command_center.api.main import app  # noqa: E402
from command_center.db import aplicar_schema, conectar, inserir, todos, um  # noqa: E402
from command_center.providers import identidade  # noqa: E402

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-vendas-204.sqlite")
    con = conectar()
    aplicar_schema(con)
    auth.criar_usuario(con, "closer@urace.us", "Carla Vendas", "OPERATOR", SENHA)
    auth.criar_usuario(con, "ger@urace.us", "Gina Gerente", "MANAGER", SENHA)
    con.execute("""INSERT INTO qbo_items (id, name, price, type, active) VALUES
                   ('31','Arrive and Drive daily',500,'Service',1),
                   ('32','Urace Daily',500,'Service',1),
                   ('35','Security deposit',400,'Service',1)""")
    # o serviço do site que pede depósito (Arrive and Drive, contrato da Academy §2.3)
    inserir(con, "booking_services", name="Arrive and Drive", price=500, qbo_item_id="31", deposit=400, active=1)
    con.commit()
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


class QBOFalso:
    def __init__(self):
        self.invoices = []

    def __call__(self, sistema, ferramenta, **kw):
        assert sistema == "quickbooks", sistema
        if ferramenta == "qbo_clientes_buscar":
            return [{"id": "77", "nome": "cliente"}]
        if ferramenta == "qbo_criar_e_enviar_invoice":
            self.invoices.append(kw)
            n = 1000 + len(self.invoices)
            return {"id": str(n), "numero": str(n), "total": sum(l["unitario"] for l in kw["linhas"]), "enviado": True}
        raise AssertionError(ferramenta)


@pytest.fixture()
def qbo(monkeypatch):
    falso = QBOFalso()
    monkeypatch.setattr(vendas, "chamar", falso)
    monkeypatch.setattr(vendas, "_aplicando", lambda sistema, fn, *a, **kw: fn(*a, **kw))
    return falso


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def cria(cli, h, **campos):
    dados = {"name": "Marcos Teixeira", "phone": "+1 407 555 0144", "email": "marcos@example.com",
             "pilot_name": "Lucas Teixeira", "pilot_age": 9, "service": "Urace Daily", "amount": 500, "source": "Ligação"}
    dados.update(campos)
    r = cli.post(B + "/sales", json=dados, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


SO_QBO = {"cliente": False, "qbo": True, "waiver": False, "asana": False, "kommo": False}


def fecha(cli, h, oid, **extra):
    corpo = {"passos": SO_QBO}
    corpo.update(extra)
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json=corpo)
    assert r.status_code == 200, r.text
    return r.json()["fechamento"]


# ------------------------------------------------------------------ 1–3: a invoice fora da tabela
def test_preco_da_tabela_vem_do_catalogo_e_nao_do_que_a_tela_manda(cli, qbo):
    """A tela preenchia "Preço da tabela" com o valor da venda: a conferência nunca pegava nada."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Desconto Escondido", email="desconto@example.com", amount=380)
    f = fecha(cli, h, oid, preco_tabela=380)
    assert f["preco_tabela"] == 500 and f["na_tabela"] is False and f["aprovado"] is False
    assert f["invoice_pendente"] is True and not qbo.invoices, "fora da tabela: a invoice não sai"


def test_catalogo_da_tela_traz_o_preco_e_o_deposito_de_cada_item(cli):
    h = entra(cli, "closer@urace.us")
    c = cli.get(f"{B}/sales/catalogo", headers=h).json()
    itens = {i["name"]: i for i in c["itens"]}
    assert c["total"] == 2 and "Security deposit" not in itens, "o depósito entra sozinho, não se escolhe"
    assert itens["Arrive and Drive daily"]["price"] == 500 and itens["Arrive and Drive daily"]["deposito"] == 400
    assert itens["Urace Daily"]["deposito"] == 0
    assert [i["name"] for i in cli.get(f"{B}/sales/catalogo", headers=h, params={"q": "daily", "limit": 1}).json()["itens"]] == ["Arrive and Drive daily"]


def test_sem_preco_de_tabela_a_invoice_tambem_espera(cli, qbo):
    """Pela API, sem preço de tabela, a regra continua valendo: ninguém sabe se está na tabela."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Serviço Inventado", email="inventado@example.com", service="Pacote VIP Secreto", amount=90)
    f = fecha(cli, h, oid)
    assert f["na_tabela"] is None and f["aprovado"] is False and f["invoice_pendente"] is True
    assert not qbo.invoices


def test_valor_da_tabela_sai_direto_com_o_item_do_catalogo(cli, qbo):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Na Tabela", email="natabela@example.com", amount=500)
    f = fecha(cli, h, oid)
    assert f["na_tabela"] is True and f["invoice_pendente"] is False
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[0]["linhas"]] == [("32", 500.0)]


def test_botao_de_passo_nao_passa_por_cima_da_aprovacao(cli, qbo):
    """Antes, `step/qbo` (operador) mandava a invoice que esperava o dono, com aprovado=True."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Pulou a Fila", email="pulou@example.com", amount=300)
    assert fecha(cli, h, oid)["invoice_pendente"] is True
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 409 and "Liberar invoice" in r.json()["detail"]
    assert not qbo.invoices


def test_gerente_libera_a_invoice_conferindo_o_valor_e_fica_auditado(cli, qbo):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Liberar Depois", email="liberar@example.com", amount=450)
    fecha(cli, h, oid)
    # o operador não libera
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=h, json={"valor": 450}).status_code == 403
    hg = entra(cli, "ger@urace.us")
    d = cli.get(f"{B}/sales/{oid}", headers=hg).json()
    assert d["pode_liberar"] is True and d["tabela"]["preco"] == 500
    # valor diferente do da venda: não libera no escuro
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 500})
    assert r.status_code == 409 and not qbo.invoices
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450})
    assert r.status_code == 200, r.text
    f = r.json()["fechamento"]
    assert f["invoice_pendente"] is False and f["liberada"]["por"] == "Gina Gerente" and f["liberada"]["preco_tabela"] == 500
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[0]["linhas"]] == [("32", 450.0)]
    con = conectar()
    try:
        a = um(con, "SELECT detail FROM audit_logs WHERE event='sales.invoice.release' AND entity_id=?", (oid,))
        assert a and json.loads(a["detail"])["valor"] == 450 and json.loads(a["detail"])["preco_tabela"] == 500
    finally:
        con.close()
    # liberada uma vez, não há o que liberar de novo
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450}).status_code == 409


def test_ia_confere_a_tabela_e_operador_confirmando_nao_aprova(cli, qbo):
    """`venda_fechar` mandava a invoice com aprovado=True, e o operador podia confirmar a ação."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Fechou Pela IA", email="ia@example.com", amount=350)
    con = conectar()
    try:
        carla = um(con, "SELECT id FROM users WHERE email='closer@urace.us'")["id"]
        gina = um(con, "SELECT id FROM users WHERE email='ger@urace.us'")["id"]
        r = acoes_painel.executar(con, carla, "venda_fechar", {"opp_id": oid})
        assert r["aplicado"] and r["invoice_esperando_gerente"] is True and not qbo.invoices
        f = json.loads(um(con, "SELECT closing FROM opportunities WHERE id=?", (oid,))["closing"])
        assert f["na_tabela"] is False and f["preco_tabela"] == 500 and f["invoice_pendente"] is True
        # a invoice avulsa pela IA também não sai fora da tabela com operador
        r = acoes_painel.executar(con, carla, "venda_enviar_invoice", {"opp_id": oid})
        assert not r["aplicado"] and "gerente" in r["motivo"] and not qbo.invoices
        # com o gerente confirmando, sai
        oid2 = cria(cli, h, name="Fechou Pela IA 2", email="ia2@example.com", amount=350)
        r = acoes_painel.executar(con, gina, "venda_fechar", {"opp_id": oid2})
        assert r["invoice_esperando_gerente"] is False and len(qbo.invoices) == 1
        con.commit()
    finally:
        con.close()


# ------------------------------------------------------------------ 4: o depósito
def test_venda_manual_cobra_o_deposito_como_a_automatica(cli, qbo):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Arrive Manual", email="arrive@example.com", service="Arrive and Drive", amount=500)
    f = fecha(cli, h, oid)
    assert f["na_tabela"] is True and f["deposito"] == 400 and f["deposito_cobrado"]
    linhas = qbo.invoices[0]["linhas"]
    assert [(l["item_id"], l["unitario"]) for l in linhas] == [("31", 500.0), ("35", 400.0)]
    from command_center.providers import cobranca_agenda
    assert linhas[1]["descricao"] == cobranca_agenda.DESCRICAO_DEPOSITO
    # já cobrado: não cobra de novo
    assert cli.post(f"{B}/sales/{oid}/deposit", headers=h).status_code == 409


def test_operador_cobra_so_o_deposito_quando_faltou(cli, qbo):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Sem Depósito", email="semdep@example.com", service="Arrive and Drive", amount=500)
    # antes de fechar não há o que cobrar
    assert cli.post(f"{B}/sales/{oid}/deposit", headers=h).status_code == 409
    fecha(cli, h, oid, passos={**SO_QBO, "qbo": False})          # invoice desligada no fechamento
    assert not qbo.invoices
    r = cli.post(f"{B}/sales/{oid}/deposit", headers=h)
    assert r.status_code == 200, r.text
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[0]["linhas"]] == [("35", 400.0)]
    assert cli.post(f"{B}/sales/{oid}/deposit", headers=h).status_code == 409, "não cobra duas vezes"
    # e a invoice do serviço, mandada depois, não leva o depósito outra vez
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 200
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[1]["linhas"]] == [("31", 500.0)]
    # serviço que não pede depósito: o botão explica
    oid2 = cria(cli, h, name="Daily Sem Dep", email="daily@example.com", amount=500)
    fecha(cli, h, oid2, passos={**SO_QBO, "qbo": False})
    r = cli.post(f"{B}/sales/{oid2}/deposit", headers=h)
    assert r.status_code == 400 and "não pede depósito" in r.json()["detail"]


# ------------------------------------------------------------------ 5: o card do irmão
def test_card_do_irmao_pelo_novo_cliente(cli):
    con = conectar()
    try:
        enzo = inserir(con, "clients", name="Joseph Kartian", pilot_name="Enzo Kartian", email="joekur@example.com",
                       phone="407-555-0142", status="ACTIVE", source="asana")
        con.commit()
    finally:
        con.close()
    h = entra(cli, "closer@urace.us")
    # sem o vínculo, o mesmo e-mail devolve o card que existe (um card por pessoa)
    r = cli.post(f"{B}/clients", headers=h, json={"name": "Joseph Kartian", "email": "joekur@example.com", "pilot_name": "Lia Kartian"})
    assert r.json() == {"id": enzo, "created": False}
    r = cli.post(f"{B}/clients", headers=h, json={"name": "Joseph Kartian", "pilot_name": "Lia Kartian",
                                                  "pilot_dob": "2016-05-09", "irmao_de": enzo})
    assert r.status_code == 201 and r.json()["created"] is True
    lia = r.json()["id"]
    con = conectar()
    try:
        c = um(con, "SELECT * FROM clients WHERE id=?", (lia,))
        assert (c["name"], c["email"], c["phone"], c["pilot_name"], c["sibling_of"]) == \
            ("Joseph Kartian", "joekur@example.com", "407-555-0142", "Lia Kartian", enzo)
        identidade.deduplicar(con)                           # a sincronia une o mesmo e-mail…
        assert um(con, "SELECT id FROM clients WHERE id=?", (lia,)), "…mas irmão não é duplicado"
        assert identidade.nao_unir(con, enzo, lia)
        assert identidade.acha_pessoa(con, email="joekur@example.com", piloto="Lia Kartian")[0]["id"] == lia
        con.commit()
    finally:
        con.close()
    assert cli.post(f"{B}/client-merge", headers=entra(cli, "ger@urace.us"),
                    json={"keep_id": enzo, "drop_id": lia}).status_code == 409, "irmãos não se unem à mão"
    h = entra(cli, "closer@urace.us")
    assert [i["id"] for i in cli.get(f"{B}/clients/{lia}", headers=h).json()["irmaos"]] == [enzo]
    # pedir de novo devolve o mesmo card; o mesmo piloto do card de origem é recusado
    r = cli.post(f"{B}/clients", headers=h, json={"name": "x", "pilot_name": "Lia Kartian", "irmao_de": enzo})
    assert r.json() == {"id": lia, "created": False, "irmao_de": enzo}
    assert cli.post(f"{B}/clients", headers=h, json={"name": "x", "pilot_name": "Enzo Kartian", "irmao_de": enzo}).status_code == 400


def test_fechamento_cria_o_card_do_irmao_e_nunca_poe_no_card_do_outro(cli):
    con = conectar()
    try:
        bia = inserir(con, "clients", name="Paula Rocha", pilot_name="Bia Rocha", email="paula@example.com",
                      status="ACTIVE", source="asana")
        con.commit()
    finally:
        con.close()
    h = entra(cli, "closer@urace.us")
    so_cliente = {"cliente": True, "qbo": False, "waiver": False, "asana": False, "kommo": False}
    oid = cria(cli, h, name="Paula Rocha", email="paula@example.com", pilot_name="Theo Rocha")
    d = cli.get(f"{B}/sales/{oid}", headers=h).json()
    assert d["card"] == {"id": bia, "name": "Paula Rocha", "pilot_name": "Bia Rocha", "outro_piloto": True}
    # sem dizer que é irmão, o serviço do Theo não cai no card da Bia
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": so_cliente})
    passo = {p["passo"]: p for p in r.json()["fechamento"]["passos"]}
    assert passo["cliente"]["ok"] is False and "É irmão" in passo["cliente"]["detalhe"] and r.json()["client_id"] is None
    # com "É irmão", nasce o card do Theo ao lado do da Bia
    r = cli.post(f"{B}/sales/{oid}/step/cliente?irmao=true", headers=h)
    assert r.status_code == 200, r.text
    theo = r.json()["resultado"]["client_id"]
    assert theo != bia and "irmão" in r.json()["resultado"]["detalhe"]
    con = conectar()
    try:
        assert um(con, "SELECT pilot_name, sibling_of FROM clients WHERE id=?", (theo,)) == {"pilot_name": "Theo Rocha", "sibling_of": bia}
    finally:
        con.close()
    # a próxima venda do Theo cai no card dele, não no da irmã
    oid2 = cria(cli, h, name="Paula Rocha", email="paula@example.com", pilot_name="Theo Rocha")
    r = cli.post(f"{B}/sales/{oid2}/close", headers=h, json={"passos": so_cliente})
    assert r.json()["client_id"] == theo


# ------------------------------------------------------------------ 7: retorno vencido em Atenção
def test_retorno_de_venda_vencido_aparece_em_precisa_de_atencao(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Retorno Esquecido", email="esquecido@example.com")
    assert cli.post(f"{B}/sales/{oid}/next", headers=h, json={"quando": "2020-01-02T15:00:00Z", "o_que": "ligar de volta"}).status_code == 200
    con = conectar()
    try:
        itens = [i for i in atencao.coletar(con) if i["key"].startswith("venda-retorno")]
        assert itens and itens[0]["link"] == "/sales/agenda"
        assert any("Retorno Esquecido" in v for _k, v in itens[0]["facts"])
    finally:
        con.close()


def test_invoice_esperando_o_gerente_aparece_em_precisa_de_atencao(cli, qbo):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Espera Gerente", email="espera@example.com", amount=10)
    fecha(cli, h, oid)
    con = conectar()
    try:
        assert any(i["key"] == f"venda-invoice:opportunity:{oid}" and i["link"] == f"/sales/{oid}" for i in atencao.coletar(con))
    finally:
        con.close()


# ------------------------------------------------------------------ 8: MCP e o chat do Kommo
def test_mcp_pede_confirmacao_para_responder_mover_e_marcar_no_chat(cli):
    pede = {(o["metodo"], o["caminho"]): o["confirma"] for o in mcp_operar.catalogo()}
    for caminho in ("/ops/api/crm/leads/{lid}/reply", "/ops/api/crm/leads/{lid}/stage", "/ops/api/crm/leads/{lid}/tags",
                    "/ops/api/sales/{oid}/invoice/liberar", "/ops/api/sales/{oid}/deposit"):
        assert pede[("POST", caminho)] is True, caminho
    assert pede[("GET", "/ops/api/crm/inbox")] is False, "ler continua sem confirmação"


def test_irmaos_sem_vinculo_continuam_fora_do_card_um_do_outro(cli):
    """Os cards de antes do #204 (sem `sibling_of`) seguem as regras de sempre."""
    con = conectar()
    try:
        a = inserir(con, "clients", name="Ana Solo", email="solo@example.com", status="ACTIVE", source="asana")
        assert identidade.familia(con, a) == {a} and identidade.irmaos(con, a) == []
        assert todos(con, "SELECT id FROM clients WHERE sibling_of=?", (a,)) == []
    finally:
        con.close()


# ------------------------------------------------------------------ #310: Liberar invoice, sem saída e sem cobrar duas vezes
def _na_atencao(oid):
    con = conectar()
    try:
        return any(i["key"] == f"venda-invoice:opportunity:{oid}" for i in atencao.coletar(con))
    finally:
        con.close()


def test_invoice_desligada_no_fechamento_fora_da_tabela_o_gerente_libera(cli, qbo):
    """O closer fechou fora da tabela com a invoice desligada: o passo respondia "use Liberar
    invoice", o Liberar respondia "não tem invoice esperando" e a tela não mostrava botão — nem
    para o gerente."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Sem Saída", email="semsaida@example.com", amount=300)
    f = fecha(cli, h, oid, passos={**SO_QBO, "qbo": False})
    assert f["invoice_pendente"] is False and not qbo.invoices
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 409 and "Liberar invoice" in r.json()["detail"], "fora da tabela: o closer não manda"
    assert not _na_atencao(oid), "desligar a invoice foi escolha do closer: não vira alarme"
    hg = entra(cli, "ger@urace.us")
    d = cli.get(f"{B}/sales/{oid}", headers=hg).json()
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 200, r.text
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[0]["linhas"]] == [("32", 300.0)]
    assert d.get("invoice") == "esperando" and d["pode_liberar"], "a tela mostra o Liberar ao gerente"
    assert cli.get(f"{B}/sales/{oid}", headers=hg).json()["invoice"] == "enviada"


def test_fechamento_antigo_esperando_o_dono_tambem_libera_e_aparece_em_atencao(cli, qbo):
    """Os fechamentos de antes de 14/10 só tinham `pendente` no passo do QuickBooks (sem
    `invoice_pendente` nem `valor_aprovado`): não apareciam em Precisa de atenção, e nem o
    Liberar nem o passo os mandavam."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Fechamento Antigo", email="antigo@example.com", amount=300)
    em = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    antigo = {"em": em, "por": "Carla Vendas", "na_tabela": False, "aprovado": False,
              "motivo_preco": "valor $300 difere da tabela ($500)",
              "passos": [{"passo": "qbo", "nome": vendas.PASSO_PT["qbo"], "ok": None,
                          "detalhe": "invoice esperando aprovação do dono: valor $300 difere da tabela ($500)",
                          "cliente_qbo": None, "invoice": None, "pendente": True}]}
    con = conectar()
    try:
        con.execute("UPDATE opportunities SET closing=?, stage='GANHO' WHERE id=?", (json.dumps(antigo, ensure_ascii=False), oid))
        auth.criar_usuario(con, "dona.teste@urace.us", "Dora Dona", "ADMIN", SENHA)
    finally:
        con.close()
    assert _na_atencao(oid), "o gerente fica sabendo da invoice antiga que espera"
    assert cli.get(f"{B}/sales/{oid}", headers=h).json()["invoice"] == "esperando"
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 409
    assert cli.post(f"{B}/sales/{oid}/deposit", headers=h).status_code in (400, 409) and not qbo.invoices
    hd = entra(cli, "dona.teste@urace.us")
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hd, json={"valor": 300})
    assert r.status_code == 200, r.text
    assert r.json()["fechamento"]["liberada"]["por"] == "Dora Dona" and len(qbo.invoices) == 1
    assert not _na_atencao(oid), "liberada, sai de Precisa de atenção"


def test_step_qbo_nao_manda_segunda_invoice_quando_ja_saiu(cli, qbo):
    """`step/qbo` não conferia se a invoice já tinha saído: a venda na tabela, já faturada, ganhava
    a segunda invoice. Só a tela protegia (o botão aparece só em falha); a API e o MCP, não."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Duas Vezes Não", email="duasvezes@example.com", amount=500)
    fecha(cli, h, oid)
    assert len(qbo.invoices) == 1
    for quem in ("closer@urace.us", "ger@urace.us"):
        r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=entra(cli, quem))
        assert r.status_code == 409 and "já saiu" in r.json()["detail"] and "#1001" in r.json()["detail"], r.text
    assert len(qbo.invoices) == 1
    h = entra(cli, "closer@urace.us")
    assert cli.get(f"{B}/sales/{oid}", headers=h).json()["invoice"] == "enviada"
    # a venda que ainda não fechou também não manda a invoice pelo passo: o fechamento cobraria de novo
    oid2 = cria(cli, h, name="Ainda Aberta", email="aberta@example.com", amount=500)
    assert cli.post(f"{B}/sales/{oid2}/step/qbo", headers=h).status_code == 409 and len(qbo.invoices) == 1


def test_fechar_de_novo_nao_duplica_a_invoice(cli, qbo):
    """`POST /close` não conferia se a venda já tinha fechado: depois de liberada, fechar de novo
    voltava a invoice a esperar e o gerente liberava outra (e refazia card, waiver, Asana, Kommo)."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Fecha De Novo", email="denovo@example.com", amount=450)
    fecha(cli, h, oid)
    hg = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450}).status_code == 200
    h = entra(cli, "closer@urace.us")
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": SO_QBO})
    assert r.status_code == 409 and "já fechada" in r.json()["detail"], r.text
    hg = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450}).status_code == 409
    assert len(qbo.invoices) == 1
    # na tabela, a invoice sai no fechamento: fechar de novo também não manda a segunda
    h = entra(cli, "closer@urace.us")
    oid2 = cria(cli, h, name="Na Tabela De Novo", email="tabeladenovo@example.com", amount=500)
    fecha(cli, h, oid2)
    assert cli.post(f"{B}/sales/{oid2}/close", headers=h, json={"passos": SO_QBO}).status_code == 409
    assert len(qbo.invoices) == 2
    # o depósito cobrado sozinho também conta: fechar de novo cobraria outro
    oid3 = cria(cli, h, name="Depósito De Novo", email="depdenovo@example.com", service="Arrive and Drive", amount=500)
    fecha(cli, h, oid3, passos={**SO_QBO, "qbo": False})
    assert cli.post(f"{B}/sales/{oid3}/deposit", headers=h).status_code == 200
    assert cli.post(f"{B}/sales/{oid3}/close", headers=h, json={"passos": SO_QBO}).status_code == 409
    assert len(qbo.invoices) == 3


def test_reenvio_pelo_step_fica_na_auditoria(cli, qbo, monkeypatch):
    """Só o Liberar ia para a auditoria; a invoice mandada pelo botão do passo ficava só na linha
    do tempo da venda."""
    def fora_do_ar(sistema, ferramenta, **kw):
        if ferramenta == "qbo_criar_e_enviar_invoice":
            raise RuntimeError("QuickBooks fora do ar")
        return qbo(sistema, ferramenta, **kw)
    monkeypatch.setattr(vendas, "chamar", fora_do_ar)
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Reenvio Auditado", email="reenvio@example.com", amount=500)
    f = fecha(cli, h, oid)
    assert [p["ok"] for p in f["passos"] if p["passo"] == "qbo"] == [False] and not qbo.invoices
    monkeypatch.setattr(vendas, "chamar", qbo)
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 200, r.text
    con = conectar()
    try:
        carla = um(con, "SELECT id FROM users WHERE email='closer@urace.us'")["id"]
        a = um(con, "SELECT user_id, detail FROM audit_logs WHERE event='sales.invoice.resend' AND entity_id=?", (str(oid),))
        assert a and a["user_id"] == carla, "quem mandou fica registrado"
        assert json.loads(a["detail"])["invoice"] == r.json()["resultado"]["invoice"] and json.loads(a["detail"])["valor"] == 500
    finally:
        con.close()
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 409, "e não sai de novo"
    assert len(qbo.invoices) == 1


def test_ia_nao_manda_segunda_invoice(cli, qbo):
    """`venda_enviar_invoice` não conferia se a invoice já tinha saído, e a que ela mandava não
    ficava no fechamento: o passo e a própria IA mandavam outra."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="IA Duas Vezes", email="iaduas@example.com", amount=500)
    oid2 = cria(cli, h, name="IA Desligada", email="iadesligada@example.com", amount=500)
    oid3 = cria(cli, h, name="IA Antes de Fechar", email="iaantes@example.com", amount=500)
    con = conectar()
    try:
        carla = um(con, "SELECT id FROM users WHERE email='closer@urace.us'")["id"]
        gina = um(con, "SELECT id FROM users WHERE email='ger@urace.us'")["id"]
        assert acoes_painel.executar(con, carla, "venda_fechar", {"opp_id": oid})["aplicado"] and len(qbo.invoices) == 1
        for quem in (carla, gina):
            r = acoes_painel.executar(con, quem, "venda_enviar_invoice", {"opp_id": oid})
            assert not r["aplicado"] and "já saiu" in r["motivo"], r
            r = acoes_painel.executar(con, quem, "venda_fechar", {"opp_id": oid})
            assert not r["aplicado"] and "já fechada" in r["motivo"], r
        assert len(qbo.invoices) == 1
    finally:
        con.close()
    # a invoice que a IA manda fica no fechamento: depois dela, nem a IA nem o passo mandam outra
    fecha(cli, h, oid2, passos={**SO_QBO, "qbo": False})
    con = conectar()
    try:
        assert acoes_painel.executar(con, carla, "venda_enviar_invoice", {"opp_id": oid2})["aplicado"] and len(qbo.invoices) == 2
        assert not acoes_painel.executar(con, carla, "venda_enviar_invoice", {"opp_id": oid2})["aplicado"]
    finally:
        con.close()
    assert cli.post(f"{B}/sales/{oid2}/step/qbo", headers=h).status_code == 409
    assert len(qbo.invoices) == 2
    # antes de fechar, a invoice avulsa faria o fechamento cobrar de novo
    con = conectar()
    try:
        r = acoes_painel.executar(con, carla, "venda_enviar_invoice", {"opp_id": oid3})
        assert not r["aplicado"] and "não foi fechada" in r["motivo"] and len(qbo.invoices) == 2
    finally:
        con.close()


def test_dois_cliques_em_liberar_mandam_uma_invoice_so(cli, qbo, monkeypatch):
    """Dois "Liberar" ao mesmo tempo (duas abas, dois gerentes) chamavam o QuickBooks duas vezes: a
    tela só desabilita o botão na própria aba. O primeiro marca `liberando` antes de chamar."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Clique Duplo", email="cliqueduplo@example.com", amount=420)
    fecha(cli, h, oid)
    hg = entra(cli, "ger@urace.us")
    segundo = []

    def no_meio(sistema, ferramenta, **kw):
        if ferramenta == "qbo_criar_e_enviar_invoice" and not segundo:
            # o segundo clique chega enquanto o QuickBooks ainda responde o primeiro (uma vez só)
            segundo.append(None)
            segundo[0] = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 420})
        return qbo(sistema, ferramenta, **kw)
    monkeypatch.setattr(vendas, "chamar", no_meio)
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 420})
    assert r.status_code == 200, r.text
    assert segundo[0].status_code == 409 and "liberando" in segundo[0].json()["detail"], segundo[0].text
    assert len(qbo.invoices) == 1
    f = r.json()["fechamento"]
    assert "liberando" not in f and f["liberada"]["por"] == "Gina Gerente"
