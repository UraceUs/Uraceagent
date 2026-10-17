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
from command_center.providers import NaoConectado, identidade  # noqa: E402

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


class QBORecusou(Exception):
    """O QuickBooks recusou a invoice (HTTP 400): nada foi criado, e o botão pode tentar de novo (#310, A1)."""
    nada_saiu = True


class QBOFalso:
    """O QuickBooks de mentira: anota cada invoice criada e, como o de verdade, devolve a resposta original
    quando a mesma `requestid` se repete (não cria a segunda, #310 A1)."""

    def __init__(self):
        self.invoices, self.reenvios, self.por_requestid = [], [], {}

    def _resposta(self, i):
        n = 1001 + i
        return {"id": str(n), "numero": str(n), "total": sum(l["unitario"] for l in self.invoices[i]["linhas"]), "enviado": True}

    def __call__(self, sistema, ferramenta, **kw):
        assert sistema == "quickbooks", sistema
        if ferramenta == "qbo_clientes_buscar":
            return [{"id": "77", "nome": "cliente"}]
        if ferramenta == "qbo_criar_e_enviar_invoice":
            if kw.get("requestid") in self.por_requestid:
                return self._resposta(self.por_requestid[kw["requestid"]])
            self.invoices.append(kw)
            if kw.get("requestid"):
                self.por_requestid[kw["requestid"]] = len(self.invoices) - 1
            return self._resposta(len(self.invoices) - 1)
        if ferramenta == "invoice_por_numero":
            i = int(kw["numero"]) - 1001 if str(kw["numero"]).isdigit() else -1
            if not 0 <= i < len(self.invoices):
                return None
            return {**self._resposta(i), "cliente_id": self.invoices[i]["cliente_id"], "cliente": "cliente"}
        if ferramenta == "qbo_enviar_invoice":
            self.reenvios.append(kw)
            return {"aplicado": True, "id": kw["id"], "enviado_para": kw.get("email")}
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
    monkeypatch.setattr(vendas, "chamar", _qbo_fora_do_ar(qbo))
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


# ------------------------------------------------------------------ #310, revisão: a trava vale para todas as saídas
def _closing(oid):
    con = conectar()
    try:
        return json.loads(um(con, "SELECT closing FROM opportunities WHERE id=?", (oid,))["closing"] or "null")
    finally:
        con.close()


def _uid(con, email):
    return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]


def _qbo_fora_do_ar(qbo):
    """O QuickBooks recusa a invoice (nada criado): o passo falha e o "tentar de novo" pode mandar."""
    def fora(sistema, ferramenta, **kw):
        if ferramenta == "qbo_criar_e_enviar_invoice":
            raise QBORecusou("HTTP 400 em POST /invoice (intuit_tid=x): o QuickBooks recusou")
        return qbo(sistema, ferramenta, **kw)
    return fora


def _no_meio(qbo, pedido):
    """O QuickBooks ainda responde o primeiro pedido quando o segundo chega (uma vez só)."""
    segundo = []

    def chamar(sistema, ferramenta, **kw):
        if ferramenta == "qbo_criar_e_enviar_invoice" and not segundo:
            segundo.append(None)
            segundo[0] = pedido()
        return qbo(sistema, ferramenta, **kw)
    return chamar, segundo


def _vence_a_marca(oid, minutos=11):
    f = _closing(oid)
    f["cobrando"]["em"] = (datetime.now(timezone.utc) - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con = conectar()
    try:
        con.execute("UPDATE opportunities SET closing=? WHERE id=?", (json.dumps(f, ensure_ascii=False), oid))
    finally:
        con.close()


def test_venda_paga_no_stripe_nao_mostra_liberar_nem_cobra_de_novo(cli, qbo):
    """R1: a venda paga no site (Buy now da loja e carrinho) nasce com `closing` {"por": "stripe"} e
    sem passos: aparecia como "esperando", com o Liberar, e o Liberar (e a IA) cobravam no QuickBooks
    quem já tinha pago."""
    from command_center.providers import carrinho, stripe_loja
    con = conectar()
    try:
        so = inserir(con, "store_orders", product_slug="camiseta", product_name="Camiseta Teste", quantity=1, unit_price=45,
                     amount=45, delivery="retirada", status="pago", amount_paid=45, email="loja.stripe@example.com",
                     name="Fulano Loja", phone="+1 407 555 0101", paid_at="2026-10-16T15:00:00.000Z")
        buy_now = stripe_loja.ligar_e_vender(con, so)
        so2 = inserir(con, "store_orders", kind="carrinho", product_slug="carrinho", product_name="Carrinho", quantity=1,
                      unit_price=60, amount=60, delivery="retirada", status="pago", amount_paid=60,
                      email="carrinho.stripe@example.com", name="Beltrano Carrinho", phone="+1 407 555 0102",
                      paid_at="2026-10-16T15:00:00.000Z")
        inserir(con, "store_order_items", order_id=so2, kind="produto", name="Luva Teste", quantity=1, unit_price=60, amount=60,
                product_slug="luva")
        do_carrinho = carrinho.pago(con, so2)
        for oid in (buy_now, do_carrinho):              # o pior caso: o serviço com item e preço no catálogo
            con.execute("UPDATE opportunities SET qbo_item_id='32' WHERE id=?", (oid,))
    finally:
        con.close()
    hg = entra(cli, "ger@urace.us")
    for oid, valor in ((buy_now, 45), (do_carrinho, 60)):
        assert _closing(oid)["por"] == "stripe"
        d = cli.get(f"{B}/sales/{oid}", headers=hg).json()
        assert d["invoice"] == "enviada", "pago no site: nem o aviso nem o Liberar aparecem"
        for r in (cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": valor, "item_id": "32"}),
                  cli.post(f"{B}/sales/{oid}/step/qbo", headers=hg),
                  cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO}),
                  cli.post(f"{B}/sales/{oid}/deposit", headers=hg)):
            assert r.status_code == 409 and "pago no site (Stripe)" in r.json()["detail"], r.text
        con = conectar()
        try:
            for acao in ("venda_enviar_invoice", "venda_fechar"):
                r = acoes_painel.executar(con, _uid(con, "ger@urace.us"), acao, {"opp_id": oid})
                assert not r["aplicado"] and "pago no site (Stripe)" in r["motivo"], r
        finally:
            con.close()
    assert not qbo.invoices, "quem pagou no site não recebe invoice"


def test_dois_step_qbo_ao_mesmo_tempo_mandam_uma_invoice_so(cli, qbo, monkeypatch):
    """R2: só o Liberar marcava antes de chamar o QuickBooks; dois "tentar de novo" ao mesmo tempo
    (duas abas, o botão e o MCP) mandavam duas invoices."""
    monkeypatch.setattr(vendas, "chamar", _qbo_fora_do_ar(qbo))
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Duas Abas", email="duasabas@example.com", amount=500)
    assert [p["ok"] for p in fecha(cli, h, oid)["passos"] if p["passo"] == "qbo"] == [False]
    chamar, segundo = _no_meio(qbo, lambda: cli.post(f"{B}/sales/{oid}/step/qbo", headers=h))
    monkeypatch.setattr(vendas, "chamar", chamar)
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 200, r.text
    assert segundo[0].status_code == 409 and "mandando a invoice" in segundo[0].json()["detail"], segundo[0].text
    assert len(qbo.invoices) == 1 and "cobrando" not in _closing(oid)
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 409 and len(qbo.invoices) == 1


def test_ia_e_liberar_ao_mesmo_tempo_mandam_uma_invoice_so(cli, qbo, monkeypatch):
    """R2: a IA conferia a marca do Liberar mas não punha a sua: o Liberar que chegava no meio dela
    (e a IA no meio do Liberar) mandava outra invoice."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="IA Primeiro", email="iaprimeiro@example.com", amount=300)
    oid2 = cria(cli, h, name="Gerente Primeiro", email="gerprimeiro@example.com", amount=300)
    fecha(cli, h, oid)
    fecha(cli, h, oid2)                                    # fora da tabela: as duas esperam o gerente
    hg = entra(cli, "ger@urace.us")
    chamar, segundo = _no_meio(qbo, lambda: cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300}))
    monkeypatch.setattr(vendas, "chamar", chamar)
    con = conectar()
    try:
        r = acoes_painel.executar(con, _uid(con, "ger@urace.us"), "venda_enviar_invoice", {"opp_id": oid})
    finally:
        con.close()
    assert r["aplicado"], r
    assert segundo[0].status_code == 409 and "pela IA" in segundo[0].json()["detail"], segundo[0].text
    assert len(qbo.invoices) == 1

    def ia():
        c = conectar()
        try:
            return acoes_painel.executar(c, _uid(c, "ger@urace.us"), "venda_enviar_invoice", {"opp_id": oid2})
        finally:
            c.close()
    chamar, segundo = _no_meio(qbo, ia)
    monkeypatch.setattr(vendas, "chamar", chamar)
    r = cli.post(f"{B}/sales/{oid2}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 200, r.text
    assert not segundo[0]["aplicado"] and "liberando a invoice" in segundo[0]["motivo"], segundo[0]
    assert len(qbo.invoices) == 2


def test_dois_close_ao_mesmo_tempo_mandam_uma_invoice_so(cli, qbo, monkeypatch):
    """R2: dois "Confirmar e fechar" ao mesmo tempo (duas abas, a tela e a IA) passavam os dois pela
    conferência de "já fechada" antes de algum gravar, e cada um mandava a sua invoice."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Dois Close", email="doisclose@example.com", amount=500)
    chamar, segundo = _no_meio(qbo, lambda: cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": SO_QBO}))
    monkeypatch.setattr(vendas, "chamar", chamar)
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": SO_QBO})
    assert r.status_code == 200, r.text
    assert segundo[0].status_code == 409 and "fechando a venda" in segundo[0].json()["detail"], segundo[0].text
    assert len(qbo.invoices) == 1 and "cobrando" not in _closing(oid)
    # a IA fechando enquanto a tela fecha também para
    oid2 = cria(cli, h, name="Tela E IA", email="telaeia@example.com", amount=500)

    def ia():
        c = conectar()
        try:
            return acoes_painel.executar(c, _uid(c, "closer@urace.us"), "venda_fechar", {"opp_id": oid2})
        finally:
            c.close()
    chamar, segundo = _no_meio(qbo, ia)
    monkeypatch.setattr(vendas, "chamar", chamar)
    assert cli.post(f"{B}/sales/{oid2}/close", headers=h, json={"passos": SO_QBO}).status_code == 200
    assert not segundo[0]["aplicado"] and "fechando a venda" in segundo[0]["motivo"], segundo[0]
    assert len(qbo.invoices) == 2


def test_reenvio_da_waiver_no_meio_do_liberar_nao_apaga_a_invoice_liberada(cli, qbo, monkeypatch):
    """R3: o passo regravava o `closing` inteiro que leu no começo. A waiver reenviada enquanto o
    gerente liberava apagava o "liberada": a invoice voltava a esperar, e o Liberar mandava outra."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Escrita Perdida", email="perdida@example.com", amount=300)
    fecha(cli, h, oid)                                     # fora da tabela: a invoice espera o gerente
    hg = entra(cli, "ger@urace.us")
    no_meio = []

    def waiver_lenta(con, o):                              # o DocuSign responde enquanto o gerente libera
        if not no_meio:
            no_meio.append(cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300}))
        return {"envelope": "E-1", "waiver_id": None, "modelo": "parental"}
    monkeypatch.setattr(vendas, "_waiver", waiver_lenta)
    assert cli.post(f"{B}/sales/{oid}/step/waiver", headers=hg).status_code == 200
    assert no_meio[0].status_code == 200, no_meio[0].text
    f = _closing(oid)
    passos = {p["passo"]: p["ok"] for p in f["passos"]}
    assert f["liberada"]["por"] == "Gina Gerente" and f["invoice_pendente"] is False and passos == {
        "qbo": True, "waiver": True, "asana": None, "kommo": None}, f
    assert cli.get(f"{B}/sales/{oid}", headers=hg).json()["invoice"] == "enviada"
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300}).status_code == 409
    assert len(qbo.invoices) == 1


def test_deposito_no_meio_do_liberar_sai_uma_vez_so(cli, qbo, monkeypatch):
    """R3: "Cobrar só o depósito" no meio do Liberar: o Liberar mandava o depósito na invoice dele, e o
    depósito sozinho saía também."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Deposito Duplo", email="depduplo@example.com", service="Arrive and Drive", amount=450)
    fecha(cli, h, oid, passos={**SO_QBO, "qbo": False})   # fora da tabela, invoice desligada: os dois botões aparecem
    hg = entra(cli, "ger@urace.us")
    chamar, segundo = _no_meio(qbo, lambda: cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450}))
    monkeypatch.setattr(vendas, "chamar", chamar)
    assert cli.post(f"{B}/sales/{oid}/deposit", headers=hg).status_code == 200
    assert segundo[0].status_code == 409 and "cobrando o depósito" in segundo[0].json()["detail"], segundo[0].text
    assert _closing(oid)["deposito_cobrado"] and "cobrando" not in _closing(oid)
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 450}).status_code == 200
    linhas = [(l["item_id"], l["unitario"]) for i in qbo.invoices for l in i["linhas"]]
    assert linhas == [("35", 400.0), ("31", 450.0)], "o depósito uma vez, e a invoice do serviço sem ele"


def test_liberar_que_caiu_depois_do_quickbooks_nao_manda_outra_sem_o_gerente_conferir(cli, qbo, monkeypatch):
    """R4: o QuickBooks mandou a invoice e a gravação final falhou. Não sobrava rastro, e o Liberar com
    a marca vencida (10 min) mandava outra. Agora o "enviando" fica na auditoria antes da chamada, e a
    tentativa sem desfecho só passa com o gerente confirmando que conferiu no QuickBooks."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Marca Vencida", email="marcavencida@example.com", amount=300)
    fecha(cli, h, oid)
    hg = entra(cli, "ger@urace.us")
    orig = vendas._ev

    def ev_cai(con, opp_id, kind, title, *a, **kw):
        if title.startswith("Invoice liberada"):
            raise RuntimeError("database is locked")      # o banco falha DEPOIS do QuickBooks responder
        return orig(con, opp_id, kind, title, *a, **kw)
    monkeypatch.setattr(vendas, "_ev", ev_cai)
    with pytest.raises(RuntimeError):
        cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    monkeypatch.setattr(vendas, "_ev", orig)
    assert len(qbo.invoices) == 1
    con = conectar()
    try:
        a = um(con, "SELECT detail FROM audit_logs WHERE event='sales.invoice.sending' AND entity_id=?", (str(oid),))
        assert a and json.loads(a["detail"])["por"] == "Gina Gerente", "o rastro de antes da chamada"
    finally:
        con.close()
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 409 and "liberando a invoice" in r.json()["detail"], r.text
    _vence_a_marca(oid)                                    # 11 minutos depois
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["motivo"] == "tentativa_sem_desfecho" and "Gina Gerente" in d["mensagem"] \
        and "não terminou: confira no QuickBooks se a invoice saiu" in d["mensagem"], d
    assert len(qbo.invoices) == 1
    # sem a marca (perdida), o "enviando" da auditoria sem desfecho para igual
    f = _closing(oid)
    marca = f.pop("cobrando")
    con = conectar()
    try:
        con.execute("UPDATE opportunities SET closing=? WHERE id=?", (json.dumps(f, ensure_ascii=False), oid))
    finally:
        con.close()
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho", r.text
    # o gerente confirma "não saiu: mandar": fica na auditoria, e a tentativa antiga ganha o desfecho (A2).
    # A1: a requestid da pendente vai junto; como ela tinha criado, o QuickBooks devolve a MESMA invoice
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300, "confirmar": True})
    assert r.status_code == 200, r.text
    assert len(qbo.invoices) == 1 and r.json()["resultado"]["invoice"] == "1001", "a requestid repetida não cria outra"
    con = conectar()
    try:
        a = um(con, "SELECT detail FROM audit_logs WHERE event='sales.invoice.release' AND entity_id=?", (str(oid),))
        assert json.loads(a["detail"])["confirmou"] == marca["tentativa"]
        c = um(con, "SELECT detail FROM audit_logs WHERE event='sales.invoice.confirmed' AND entity_id=?", (str(oid),))
        assert json.loads(c["detail"])["tentativa"] == marca["tentativa"]
    finally:
        con.close()


def test_reenvio_que_caiu_depois_do_quickbooks_nao_reenvia(cli, qbo, monkeypatch):
    """R4: o mesmo no "tentar de novo": a invoice saiu, a gravação caiu, e o próximo clique mandava a
    segunda. Quem vende não confirma por cima; o gerente confirma depois de conferir."""
    monkeypatch.setattr(vendas, "chamar", _qbo_fora_do_ar(qbo))
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Queda No Passo", email="quedanopasso@example.com", amount=500)
    fecha(cli, h, oid)
    monkeypatch.setattr(vendas, "chamar", qbo)
    orig = vendas._ev

    def ev_cai(con, opp_id, kind, title, *a, **kw):
        if "refeito à mão" in title:
            raise RuntimeError("database is locked")
        return orig(con, opp_id, kind, title, *a, **kw)
    monkeypatch.setattr(vendas, "_ev", ev_cai)
    with pytest.raises(RuntimeError):
        cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    monkeypatch.setattr(vendas, "_ev", orig)
    assert len(qbo.invoices) == 1
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 409 and len(qbo.invoices) == 1
    _vence_a_marca(oid)
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho", r.text
    r = cli.post(f"{B}/sales/{oid}/step/qbo?confirmar=true", headers=h)
    assert r.status_code == 403 and len(qbo.invoices) == 1, "quem vende não confirma por cima"
    hg = entra(cli, "ger@urace.us")
    assert cli.post(f"{B}/sales/{oid}/step/qbo?confirmar=true", headers=hg).status_code == 200
    assert len(qbo.invoices) == 1 and "cobrando" not in _closing(oid), "a requestid da pendente: a mesma invoice"


def test_servico_do_site_sem_item_sai_com_o_item_escolhido(cli, qbo):
    """R6: o serviço do site sem item no QuickBooks ficava sem saída: o "tentar de novo" dava 502 de
    novo (sem como escolher o item), e o Liberar dava 409 (na tabela, não espera ninguém)."""
    con = conectar()
    try:
        inserir(con, "booking_services", name="Sessao Sem Item", price=200, qbo_item_id=None, deposit=0, active=1)
        con.execute("INSERT INTO qbo_items (id, name, price, type, active) VALUES ('36','Sessao Avulsa',200,'Service',1)")
    finally:
        con.close()
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Sem Item", email="semitem@example.com", service="Sessao Sem Item", amount=200)
    q = [p for p in fecha(cli, h, oid)["passos"] if p["passo"] == "qbo"][0]
    assert q["ok"] is False and "não tem item" in q["detalhe"]
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=h).status_code == 502
    r = cli.post(f"{B}/sales/{oid}/step/qbo?item_id=36", headers=h)       # o item escolhido na tela
    assert r.status_code == 200, r.text
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[-1]["linhas"]] == [("36", 200.0)]
    # o item escolhido está fora da tabela: quem vende não manda, o gerente libera com ele
    oid2 = cria(cli, h, name="Sem Item 2", email="semitem2@example.com", service="Sessao Sem Item", amount=200)
    fecha(cli, h, oid2)
    r = cli.post(f"{B}/sales/{oid2}/step/qbo?item_id=32", headers=h)
    assert r.status_code == 409 and "Liberar invoice" in r.json()["detail"], r.text
    hg = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/sales/{oid2}/invoice/liberar", headers=hg, json={"valor": 200, "item_id": "32"})
    assert r.status_code == 200, r.text
    assert [(l["item_id"], l["unitario"]) for l in qbo.invoices[-1]["linhas"]] == [("32", 200.0)]
    assert len(qbo.invoices) == 2


def test_nenhum_passo_antes_de_fechar(cli, qbo):
    """R7: `step/<qualquer>` antes de fechar criava o `closing` e contornava o "Feche a venda antes":
    depois dele, o passo da invoice mandava, o fechamento dava 409 e a venda ficava presa."""
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Passo Antes", email="passoantes@example.com", amount=500)
    for passo in vendas.PASSOS:
        r = cli.post(f"{B}/sales/{oid}/step/{passo}", headers=h)
        assert r.status_code == 409 and "Feche a venda antes" in r.json()["detail"], (passo, r.text)
    assert _closing(oid) is None and not qbo.invoices
    assert fecha(cli, h, oid)["passos"][0]["ok"] is True and len(qbo.invoices) == 1


# ------------------------------------------------------------------ #310, 2ª revisão: sem resposta (A1) e "a invoice saiu" (A2)
def _criou_e_nao_respondeu(qbo, erro=None):
    """O QuickBooks cria a invoice e a resposta não chega (tempo esgotado depois de 60 s)."""
    def chamar(sistema, ferramenta, **kw):
        r = qbo(sistema, ferramenta, **kw)
        if ferramenta == "qbo_criar_e_enviar_invoice":
            raise erro or TimeoutError("The read operation timed out")
        return r
    return chamar


def _auditoria(oid, evento):
    con = conectar()
    try:
        return [json.loads(a["detail"] or "{}") for a in
                todos(con, "SELECT detail FROM audit_logs WHERE event=? AND entity_id=? ORDER BY id", (evento, str(oid)))]
    finally:
        con.close()


def _cai_ao_gravar(monkeypatch, comeco):
    """O banco falha DEPOIS do QuickBooks responder, no evento que começa com `comeco`."""
    orig = vendas._ev

    def ev_cai(con, opp_id, kind, title, *a, **kw):
        if title.startswith(comeco):
            raise RuntimeError("database is locked")
        return orig(con, opp_id, kind, title, *a, **kw)
    monkeypatch.setattr(vendas, "_ev", ev_cai)
    return orig


def test_criar_e_enviar_separa_recusa_de_sem_resposta(monkeypatch):
    """A1, no MCP do QuickBooks: só prova que nada foi criado o erro de antes do POST /invoice e a recusa
    (HTTP 4xx, menos 408 e 429). Tempo esgotado, conexão caída, 5xx, 408 e 429 não provam. Criada a
    invoice, o envio que falha volta a invoice com `enviado: False`, sem exceção; a `requestid` vai no POST."""
    from adminai.mcp import quickbooks_mcp as q
    original = q._req
    monkeypatch.setattr(q, "_aplicar", lambda: True)
    monkeypatch.setattr(q, "_proximo_doc_number", lambda: "9999")
    linhas = [{"item_id": "32", "quantidade": 1, "unitario": 500, "descricao": "Urace Daily"}]

    def falha(codigo=None, exc=None):
        def req(caminho, metodo="GET", corpo=None, params=None):
            if exc:
                raise exc
            e = q.ErroFerramenta(f"HTTP {codigo} em {metodo} {caminho} (intuit_tid=x): erro")
            e.http = codigo
            raise e
        return req
    for codigo in (400, 401, 404):
        monkeypatch.setattr(q, "_req", falha(codigo))
        with pytest.raises(q.InvoiceNaoCriada) as e:
            q.qbo_criar_e_enviar_invoice("77", linhas, email="recusa@example.com")
        assert vendas.nada_saiu(e.value), codigo
    for erro in [falha(c) for c in (408, 429, 500, 503)] + [falha(exc=TimeoutError("timed out")),
                                                           falha(exc=q.ErroFerramenta("sem conexão com o QuickBooks: reset"))]:
        monkeypatch.setattr(q, "_req", erro)
        with pytest.raises(Exception) as e:
            q.qbo_criar_e_enviar_invoice("77", linhas, email="semresposta@example.com")
        assert not vendas.nada_saiu(e.value), e.value
    # antes do POST: o número da invoice (consulta) ou o token caíram — nada foi criado
    monkeypatch.setattr(q, "_proximo_doc_number", lambda: (_ for _ in ()).throw(TimeoutError("query timed out")))
    with pytest.raises(q.InvoiceNaoCriada):
        q.qbo_criar_e_enviar_invoice("77", linhas)
    monkeypatch.setattr(q, "_proximo_doc_number", lambda: "9999")
    monkeypatch.setattr(q, "_req", original)
    monkeypatch.setattr(q, "_realm", lambda: "1")
    monkeypatch.setattr(q, "_access_token", lambda: (_ for _ in ()).throw(q.ErroFerramenta("sem refresh token do QuickBooks")))
    with pytest.raises(q.InvoiceNaoCriada):
        q.qbo_criar_e_enviar_invoice("77", linhas, numero="1")
    # criou e o envio falhou: a invoice criada volta, e a requestid foi no POST /invoice
    pedidos = []

    def req(caminho, metodo="GET", corpo=None, params=None):
        pedidos.append((metodo, caminho, params))
        if caminho == "/invoice":
            return {"Invoice": {"Id": "501", "DocNumber": corpo["DocNumber"], "TotalAmt": 500, "CustomerRef": {"value": "77"}}}
        e = q.ErroFerramenta(f"HTTP 500 em {metodo} {caminho} (intuit_tid=x): erro interno")
        e.http = 500
        raise e
    monkeypatch.setattr(q, "_req", req)
    r = q.qbo_criar_e_enviar_invoice("77", linhas, email="criada@example.com", requestid="urace-abc")
    assert r["enviado"] is False and r["id"] == "501" and r["numero"] == "9999" and "HTTP 500" in r["erro_envio"]
    assert pedidos[0] == ("POST", "/invoice", {"requestid": "urace-abc"})


def test_sem_resposta_do_quickbooks_nao_solta_a_marca(cli, qbo, monkeypatch):
    """A1: o QuickBooks criou a invoice e a resposta não chegou. A marca saía como se nada tivesse saído,
    e o próximo clique, de qualquer pessoa, criava e mandava outra. Agora a marca fica (`incerta`), o
    próximo pedido cai na tentativa sem desfecho, e o "Não saiu: mandar" do gerente leva a mesma
    `requestid`: se ela tinha criado, o QuickBooks devolve a mesma invoice."""
    monkeypatch.setattr(vendas, "chamar", _qbo_fora_do_ar(qbo))
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Timeout Depois", email="timeoutdepois@example.com", amount=500)
    fecha(cli, h, oid)                                     # na tabela, mas o QuickBooks recusou no fechamento
    assert "cobrando" not in _closing(oid), "a recusa prova que nada saiu: a marca sai"
    monkeypatch.setattr(vendas, "chamar", _criou_e_nao_respondeu(qbo))
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 502 and "pode ter saído" in r.json()["detail"], r.text
    assert len(qbo.invoices) == 1 and _closing(oid)["cobrando"]["incerta"], "sem resposta: a marca fica"
    assert _auditoria(oid, "sales.invoice.uncertain") and not [d for d in _auditoria(oid, "sales.invoice.failed")
                                                               if d["tentativa"] == _closing(oid)["cobrando"]["tentativa"]]
    monkeypatch.setattr(vendas, "chamar", qbo)
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)  # quem vende clica de novo
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho", r.text
    assert "não respondeu" in r.json()["detail"]["mensagem"]
    assert cli.post(f"{B}/sales/{oid}/step/qbo?confirmar=true", headers=h).status_code == 403
    assert len(qbo.invoices) == 1
    hg = entra(cli, "ger@urace.us")
    r = cli.post(f"{B}/sales/{oid}/step/qbo?confirmar=true", headers=hg)
    assert r.status_code == 200 and r.json()["resultado"]["invoice"] == "1001", r.text
    assert len(qbo.invoices) == 1, "a mesma requestid: o QuickBooks não cria a segunda"
    envios = _auditoria(oid, "sales.invoice.sending")
    assert envios[-1]["requestid"] == envios[-2]["requestid"] == qbo.invoices[0]["requestid"]
    assert _auditoria(oid, "sales.invoice.confirmed")[-1]["tentativa"] == envios[-2]["tentativa"]


def test_envio_que_falha_depois_de_criar_grava_a_invoice_e_reenvia_a_mesma(cli, qbo, monkeypatch):
    """A1, com a função de verdade: o POST /invoice dá certo e o POST /invoice/<id>/send dá HTTP 500.
    Cada clique criava mais uma invoice no QuickBooks. Agora a venda grava a invoice criada e não
    enviada; o passo e o fechamento não criam outra, e o Reenviar manda a MESMA."""
    from adminai.mcp import quickbooks_mcp as q
    criadas, enviadas, falhar = [], [], [True]

    def req(caminho, metodo="GET", corpo=None, params=None):
        if caminho == "/invoice" and metodo == "POST":
            criadas.append((corpo, params))
            return {"Invoice": {"Id": str(500 + len(criadas)), "DocNumber": corpo["DocNumber"], "TotalAmt": 500,
                                "CustomerRef": {"value": "77"}, "BillEmail": corpo.get("BillEmail")}}
        if caminho.endswith("/send"):
            if falhar[0]:
                e = q.ErroFerramenta(f"HTTP 500 em POST {caminho} (intuit_tid=x): erro interno")
                e.http = 500
                raise e
            enviadas.append((caminho, params))
            return {"Invoice": {"Id": "501", "DocNumber": "9999", "TotalAmt": 500, "EmailStatus": "EmailSent"}}
        if metodo == "GET" and caminho == "/invoice/501":
            return {"Invoice": {"Id": "501", "DocNumber": "9999", "TotalAmt": 500, "BillEmail": {"Address": "enviocaiu@example.com"}}}
        raise AssertionError((metodo, caminho))
    monkeypatch.setattr(q, "_req", req)
    monkeypatch.setattr(q, "_aplicar", lambda: True)
    monkeypatch.setattr(q, "_realm", lambda: "9341453113046421")
    monkeypatch.setattr(q, "_proximo_doc_number", lambda: "9999")

    def chamar(sistema, ferramenta, **kw):
        if ferramenta == "qbo_clientes_buscar":
            return [{"id": "77"}]
        return getattr(q, ferramenta)(**kw)
    h = entra(cli, "closer@urace.us")
    monkeypatch.setattr(vendas, "chamar", _qbo_fora_do_ar(qbo))
    oid = cria(cli, h, name="Envio Caiu", email="enviocaiu@example.com", amount=500)
    fecha(cli, h, oid)
    monkeypatch.setattr(vendas, "chamar", chamar)
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 200 and r.json()["resultado"]["enviado"] is False, r.text
    assert len(criadas) == 1 and criadas[0][1]["requestid"].startswith("urace-")
    q_ = [p for p in _closing(oid)["passos"] if p["passo"] == "qbo"][0]
    assert q_["ok"] is True and q_["enviado"] is False and (q_["invoice"], q_["numero"]) == ("501", "9999")
    assert "criada" in q_["detalhe"] and "reenviar" in q_["detalhe"]
    d = cli.get(f"{B}/sales/{oid}", headers=h).json()
    assert d["invoice"] == "enviada" and d["nao_enviadas"] == [{"invoice": "501", "numero": "9999", "o_que": "invoice"}]
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=h)
    assert r.status_code == 409 and "Reenviar" in r.json()["detail"], r.text
    assert cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": SO_QBO}).status_code == 409
    assert len(criadas) == 1, "nenhum clique cria a segunda"
    falhar[0] = False
    r = cli.post(f"{B}/sales/{oid}/invoice/reenviar", headers=h, json={"invoice": "501"})
    assert r.status_code == 200, r.text
    assert len(criadas) == 1 and enviadas == [("/invoice/501/send", {"sendTo": "enviocaiu@example.com"})], "a MESMA invoice"
    q_ = [p for p in _closing(oid)["passos"] if p["passo"] == "qbo"][0]
    assert q_["enviado"] is True and cli.get(f"{B}/sales/{oid}", headers=h).json()["nao_enviadas"] == []
    assert cli.post(f"{B}/sales/{oid}/invoice/reenviar", headers=h, json={}).status_code == 409
    assert _auditoria(oid, "sales.invoice.send")[0]["invoice"] == "501"


def test_confirmar_nao_saiu_encerra_a_tentativa_antiga(cli, qbo, monkeypatch):
    """A2 (a): o "confirmar" punha o `confirmou` só na marca nova; a tentativa antiga ficava sem desfecho, e
    a venda voltava a perguntar. Agora a confirmação grava o desfecho dela (`sales.invoice.confirmed`), e
    o `sales.close` grava o `confirmou`."""
    def nao_chegou(sistema, ferramenta, **kw):
        if ferramenta == "qbo_criar_e_enviar_invoice":    # a conexão caiu: o painel não sabe se o QuickBooks criou
            raise ConnectionResetError("Connection reset by peer")
        return qbo(sistema, ferramenta, **kw)
    monkeypatch.setattr(vendas, "chamar", nao_chegou)
    hg = entra(cli, "ger@urace.us")
    oid = cria(cli, hg, name="Conexao Caiu", email="conexaocaiu@example.com", amount=500)
    f = fecha(cli, hg, oid)
    q_ = [p for p in f["passos"] if p["passo"] == "qbo"][0]
    assert q_["ok"] is False and "não respondeu" in q_["detalhe"] and _closing(oid)["cobrando"]["incerta"]
    antiga = _closing(oid)["cobrando"]["tentativa"]
    monkeypatch.setattr(vendas, "chamar", qbo)
    r = cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho", r.text
    # o gerente conferiu no QuickBooks: não saiu. Fecha de novo, confirmando
    r = cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO, "confirmar": True})
    assert r.status_code == 200 and len(qbo.invoices) == 1, r.text
    assert _auditoria(oid, "sales.invoice.confirmed")[-1]["tentativa"] == antiga
    assert _auditoria(oid, "sales.close")[-1]["confirmou"] == antiga
    r = cli.post(f"{B}/sales/{oid}/step/qbo", headers=hg)
    assert r.status_code == 409 and "já saiu" in r.json()["detail"], "a tentativa antiga não pergunta mais"


def test_fechamento_que_mandou_e_caiu_registra_o_numero_e_nao_cobra_de_novo(cli, qbo, monkeypatch):
    """A2 (b): o fechamento do gerente mandou a invoice e caiu ao gravar. Conferido no QuickBooks que ela
    saiu, não havia como dizer isso ao painel: a venda pedia "confira" para sempre, e o único jeito de
    seguir mandava a segunda. Agora "A invoice saiu": o gerente informa o número, o painel confere no
    QuickBooks (só leitura) e grava."""
    hg = entra(cli, "ger@urace.us")
    oid = cria(cli, hg, name="Fechou E Caiu", email="fechoucaiu@example.com", amount=500)
    orig = _cai_ao_gravar(monkeypatch, "Venda fechada")
    with pytest.raises(RuntimeError):
        cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO})
    monkeypatch.setattr(vendas, "_ev", orig)
    assert len(qbo.invoices) == 1 and set(_closing(oid)) == {"cobrando"}
    tentativa = _closing(oid)["cobrando"]["tentativa"]
    _vence_a_marca(oid)
    r = cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho"
    rota = f"{B}/sales/{oid}/invoice/registrar"
    assert cli.post(rota, headers=entra(cli, "closer@urace.us"), json={"numero": "1001"}).status_code == 403, "quem vende não"
    hg = entra(cli, "ger@urace.us")
    assert cli.post(rota, json={"numero": "1001"}).status_code == 403, "sem o CSRF, nada"

    def desligado(sistema, ferramenta, **kw):
        raise NaoConectado("sem refresh token")
    monkeypatch.setattr(vendas, "chamar", desligado)
    r = cli.post(rota, headers=hg, json={"numero": "1001"})
    assert r.status_code == 503 and "Ligue o QuickBooks" in r.json()["detail"], r.text
    monkeypatch.setattr(vendas, "chamar", qbo)
    r = cli.post(rota, headers=hg, json={"numero": "4242"})
    assert r.status_code == 409 and "não existe" in r.json()["detail"], r.text

    def outro_cliente(sistema, ferramenta, **kw):
        return [{"id": "88"}] if ferramenta == "qbo_clientes_buscar" else qbo(sistema, ferramenta, **kw)
    monkeypatch.setattr(vendas, "chamar", outro_cliente)
    r = cli.post(rota, headers=hg, json={"numero": "1001"})
    assert r.status_code == 409 and "outro cliente" in r.json()["detail"], r.text
    monkeypatch.setattr(vendas, "chamar", qbo)
    assert set(_closing(oid)) == {"cobrando"}, "nada registrado sem conferir"
    r = cli.post(rota, headers=hg, json={"numero": "1001"})
    assert r.status_code == 200, r.text
    f = _closing(oid)
    q_ = [p for p in f["passos"] if p["passo"] == "qbo"][0]
    assert (q_["ok"], q_["numero"], q_["registrada"]) == (True, "1001", True) and "cobrando" not in f
    assert cli.get(f"{B}/sales/{oid}", headers=hg).json()["invoice"] == "enviada"
    assert cli.post(f"{B}/sales/{oid}/close", headers=hg, json={"passos": SO_QBO}).status_code == 409
    assert cli.post(f"{B}/sales/{oid}/step/qbo", headers=hg).status_code == 409
    assert cli.post(f"{B}/sales/{oid}/step/qbo?confirmar=true", headers=hg).status_code == 409
    assert len(qbo.invoices) == 1, "nada cobrado de novo"
    assert _auditoria(oid, "sales.invoice.registered")[0]["tentativa"] == tentativa
    assert cli.post(rota, headers=hg, json={"numero": "1001"}).status_code == 409, "não há mais o que registrar"


def test_liberar_que_mandou_e_caiu_registra_o_numero_e_sai_da_atencao(cli, qbo, monkeypatch):
    """A2 (b): o Liberar mandou e caiu ao gravar; dias depois a venda continuava "esperando", em Precisa de
    atenção, e a confirmação só servia para mandar a segunda. O número registrado é conferido: outro
    valor pede "registrar mesmo assim"."""
    h = entra(cli, "closer@urace.us")
    outra = cria(cli, h, name="Outra Venda", email="outravenda@example.com", amount=500)
    fecha(cli, h, outra)                                   # a invoice 1001, de outra venda do mesmo cliente no QuickBooks
    oid = cria(cli, h, name="Liberou E Caiu", email="liberoucaiu@example.com", amount=300)
    fecha(cli, h, oid)
    hg = entra(cli, "ger@urace.us")
    orig = _cai_ao_gravar(monkeypatch, "Invoice liberada")
    with pytest.raises(RuntimeError):
        cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    monkeypatch.setattr(vendas, "_ev", orig)
    _vence_a_marca(oid, minutos=60 * 24 * 3)               # três dias depois
    assert cli.get(f"{B}/sales/{oid}", headers=hg).json()["invoice"] == "esperando" and _na_atencao(oid)
    r = cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "tentativa_sem_desfecho"
    rota = f"{B}/sales/{oid}/invoice/registrar"
    r = cli.post(rota, headers=hg, json={"numero": "1001"})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "valor_diferente", r.text
    qbo.invoices[1]["linhas"][0]["unitario"] = 290.0      # a invoice foi editada no QuickBooks depois
    r = cli.post(rota, headers=hg, json={"numero": "#1002"})
    assert r.status_code == 409 and "$290" in r.json()["detail"]["mensagem"], r.text
    r = cli.post(rota, headers=hg, json={"numero": "1002", "aceitar_diferenca": True})
    assert r.status_code == 200 and "$290" in r.json()["aviso"], r.text
    f = _closing(oid)
    assert f["liberada"]["por"] == "Gina Gerente" and f["invoice_pendente"] is False and "cobrando" not in f
    assert cli.get(f"{B}/sales/{oid}", headers=hg).json()["invoice"] == "enviada" and not _na_atencao(oid)
    assert cli.post(f"{B}/sales/{oid}/invoice/liberar", headers=hg, json={"valor": 300, "confirmar": True}).status_code == 409
    assert len(qbo.invoices) == 2, "a de outra venda e a liberada: nenhuma a mais"
    assert _auditoria(oid, "sales.invoice.registered")[0]["diferente"] is True
