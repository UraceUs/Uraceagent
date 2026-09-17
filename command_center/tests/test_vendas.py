"""Vendas — o fluxo do closer (17/09).

O que estes testes seguram, porque é o que dói se quebrar:
  * oportunidade não é cliente: só vira card no fechamento;
  * closer vê e mexe apenas no que é dele — pela rota e pela IA;
  * closer não alcança o resto do painel (usuários, QuickBooks, políticas…);
  * fechar venda grava passo por passo: o que caiu não derruba o resto;
  * valor fora da tabela fecha a venda, mas a invoice fica esperando o dono;
  * tarefa personalizada do fechamento vira lembrete no painel;
  * conta de acesso livre não tem cargo e ninguém troca o papel dela.

Nada aqui fala com sistema real: o QuickBooks/DocuSign/Asana entram desligados
(`passos`) ou como "não conectado", que é exatamente o que acontece num VPS sem
credencial.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth, vendas
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um

B = "/ops/api"
SENHA = "senha-forte-123"


@pytest.fixture(scope="module")
def cli():
    os.environ["CC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cc-vendas.sqlite")
    con = conectar()
    aplicar_schema(con)
    auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(con, "closer@urace.us", "Carla Closer", "CLOSER", SENHA)
    auth.criar_usuario(con, "outro@urace.us", "Otto Closer", "CLOSER", SENHA)
    auth.criar_usuario(con, "leitura@urace.us", "Lê", "VIEWER", SENHA)
    con.commit()
    con.close()
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


def entra(cli, email):
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def cria(cli, h, **campos):
    dados = {"name": "Marcos Teixeira", "phone": "+1 407 555 0144", "email": "marcos.t@example.com",
             "pilot_name": "Lucas Teixeira", "pilot_age": 9, "service": "Arrive and Drive 4 Stroke",
             "amount": 350, "source": "Ligação"}
    dados.update(campos)
    r = cli.post(B + "/sales", json=dados, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --------------------------------------------------------------- o dia do closer
def test_ligacao_move_etapa_marca_retorno_e_aparece_na_agenda(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Ana Souza", email="ana@example.com", pilot_name=None, pilot_age=None)
    # começa em Novo, sem nada marcado
    d = cli.get(f"{B}/sales/{oid}", headers=h).json()
    assert d["oportunidade"]["stage"] == "NOVO" and d["oportunidade"]["client_id"] is None
    assert any(e["kind"] == "stage" for e in d["eventos"])

    r = cli.post(f"{B}/sales/{oid}/call", headers=h, json={
        "resultado": "pensar", "minutos": 7, "texto": "Vai falar com o marido e responde amanhã.",
        "proximo_em": "2030-01-10T14:00:00Z", "proximo_que": "confirmar sábado"})
    assert r.status_code == 200 and r.json()["etapa"] == "CONVERSA"

    d = cli.get(f"{B}/sales/{oid}", headers=h).json()["oportunidade"]
    assert d["next_what"] == "confirmar sábado" and d["next_at"].startswith("2030-01-10")
    ag = cli.get(f"{B}/sales/agenda", headers=h).json()
    assert any(o["id"] == oid and not o["atrasado"] for o in ag["retornos"])

    b = cli.get(f"{B}/sales/board", headers=h).json()
    conversa = [c for c in b["colunas"] if c["etapa"] == "CONVERSA"][0]
    assert b["so_minhas"] and any(o["id"] == oid for o in conversa["oportunidades"])
    assert [o for o in conversa["oportunidades"] if o["id"] == oid][0]["calls"] == 1

    # anotação entra na ficha e na linha do tempo
    assert cli.post(f"{B}/sales/{oid}/note", headers=h, json={"texto": "Mãe decide junto."}).status_code == 200
    d = cli.get(f"{B}/sales/{oid}", headers=h).json()
    assert "Mãe decide junto." in d["oportunidade"]["notes"]
    assert sum(1 for e in d["eventos"] if e["kind"] == "note") == 1


def test_perdido_exige_motivo_e_ganho_nao_sai_por_fora_do_fechamento(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Bruno Lima", email="bruno@example.com")
    assert cli.post(f"{B}/sales/{oid}/stage", headers=h, json={"etapa": "PERDIDO"}).status_code == 400
    assert cli.post(f"{B}/sales/{oid}/stage", headers=h, json={"etapa": "GANHO"}).status_code == 409
    r = cli.post(f"{B}/sales/{oid}/stage", headers=h, json={"etapa": "PERDIDO", "motivo": "achou caro"})
    assert r.status_code == 200
    o = cli.get(f"{B}/sales/{oid}", headers=h).json()["oportunidade"]
    assert o["stage"] == "PERDIDO" and o["lost_reason"] == "achou caro" and o["next_at"] is None


def test_closer_nao_alcanca_oportunidade_de_outro_closer(cli):
    h1 = entra(cli, "closer@urace.us")
    minha = cria(cli, h1, name="Cliente da Carla", email="carla-cliente@example.com")
    h2 = entra(cli, "outro@urace.us")
    assert cli.get(f"{B}/sales/{minha}", headers=h2).status_code == 403
    assert cli.post(f"{B}/sales/{minha}/note", headers=h2, json={"texto": "oi"}).status_code == 403
    b = cli.get(f"{B}/sales/board", headers=h2).json()
    assert all(o["id"] != minha for c in b["colunas"] for o in c["oportunidades"])
    # o administrador vê tudo
    ha = entra(cli, "admin@urace.us")
    assert cli.get(f"{B}/sales/{minha}", headers=ha).status_code == 200
    assert cli.get(f"{B}/sales/board", headers=ha).json()["so_minhas"] is False


def test_leitura_nao_cria_e_closer_nao_entra_no_resto_do_painel(cli):
    h = entra(cli, "leitura@urace.us")
    assert cli.post(B + "/sales", headers=h, json={"name": "X"}).status_code == 403
    h = entra(cli, "closer@urace.us")
    for caminho in ("/users", "/audit", "/policies", "/qbo/invoices", "/integrations", "/automation/rules"):
        assert cli.get(B + caminho, headers=h).status_code == 403, caminho
    # a área dele continua aberta
    assert cli.get(B + "/sales/board", headers=h).status_code == 200
    assert cli.get(B + "/dashboard", headers=h).status_code == 200


def test_lead_do_chat_vira_oportunidade_uma_vez_so(cli):
    con = conectar()
    try:
        lead = con.execute("""INSERT INTO crm_leads (external_id, name, contact_name, contact_phone,
                              contact_email, source, needs_reply) VALUES ('9001','Lead 9001','Pedro Alves',
                              '+1 407 555 0199','pedro@example.com','Instagram',1)""").lastrowid
        con.commit()
    finally:
        con.close()
    h = entra(cli, "closer@urace.us")
    r1 = cli.post(f"{B}/sales/from-lead/{lead}", headers=h)
    assert r1.status_code == 201 and r1.json()["reaproveitada"] is False
    r2 = cli.post(f"{B}/sales/from-lead/{lead}", headers=h)
    assert r2.json() == {"id": r1.json()["id"], "reaproveitada": True}
    o = cli.get(f"{B}/sales/{r1.json()['id']}", headers=h).json()["oportunidade"]
    assert o["name"] == "Pedro Alves" and o["source"] == "Instagram" and o["crm_lead_id"] == lead
    assert cli.post(f"{B}/sales/from-lead/999999", headers=h).status_code == 404


# --------------------------------------------------------------- fechamento
def test_fechar_cria_o_cliente_grava_passo_por_passo_e_a_tarefa_extra(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Marcos Teixeira", email="marcos.fecha@example.com")
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={
        "service": "Arrive and Drive 4 Stroke", "service_date": "2030-02-16", "service_time": "10:00",
        "amount": 350, "preco_tabela": 350, "pilot_name": "Lucas Teixeira", "pilot_age": 9,
        "email": "marcos.fecha@example.com", "phone": "+1 407 555 0144",
        "nota_cliente": "Primeira vez no kart; a mãe vai junto.",
        "passos": {"cliente": True, "qbo": False, "waiver": False, "asana": False, "kommo": False},
        "extras": [{"titulo": "Mandar o vídeo de boas-vindas", "onde": "painel", "quando": "2030-02-10"}]})
    assert r.status_code == 200, r.text
    f = r.json()["fechamento"]
    assert r.json()["etapa"] == "GANHO" and f["na_tabela"] is True and f["aprovado"] is True
    passo = {p["passo"]: p for p in f["passos"]}
    assert passo["cliente"]["ok"] is True and passo["cliente"]["client_id"]
    assert [p["ok"] for k, p in passo.items() if k in vendas.PASSOS and k != "cliente"] == [None, None, None, None]
    extra = [p for k, p in passo.items() if k.startswith("extra:")][0]
    assert extra["ok"] is True and extra["onde"] == "painel"

    con = conectar()
    try:
        c = um(con, "SELECT * FROM clients WHERE id=?", (passo["cliente"]["client_id"],))
        assert c["name"] == "Marcos Teixeira" and c["pilot_name"] == "Lucas Teixeira"
        assert "Primeira vez no kart" in (c["notes"] or "")
        assert um(con, "SELECT 1 AS x FROM audit_logs WHERE event='sales.close'")
        kinds = [e["kind"] for e in todos(con, "SELECT kind FROM opp_events WHERE opp_id=?", (oid,))]
        # cada passo entra na linha do tempo com o mesmo "kind" do resto do painel
        assert {"client", "stage", "task"} <= set(kinds)
    finally:
        con.close()
    # o lembrete da tarefa personalizada ficou no próximo passo da oportunidade
    o = cli.get(f"{B}/sales/{oid}", headers=h).json()["oportunidade"]
    assert o["next_what"] == "Mandar o vídeo de boas-vindas" and o["client_id"]


def test_fechar_liga_no_card_que_ja_existe_em_vez_de_duplicar(cli):
    con = conectar()
    try:
        cid = con.execute("INSERT INTO clients (name, email, status) VALUES ('Rita Antiga','rita@example.com','ACTIVE')").lastrowid
        con.commit()
    finally:
        con.close()
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Rita Nova", email="rita@example.com", pilot_name="Rita Nova", pilot_age=30)
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={
        "amount": 350, "preco_tabela": 350, "nota_cliente": "voltou depois de um ano",
        "passos": {"cliente": True, "qbo": False, "waiver": False, "asana": False, "kommo": False}})
    assert r.status_code == 200
    passo = {p["passo"]: p for p in r.json()["fechamento"]["passos"]}
    assert passo["cliente"]["client_id"] == cid and "já existia" in passo["cliente"]["detalhe"]
    con = conectar()
    try:
        assert um(con, "SELECT COUNT(*) AS n FROM clients WHERE email='rita@example.com'")["n"] == 1
        assert "voltou depois de um ano" in um(con, "SELECT notes FROM clients WHERE id=?", (cid,))["notes"]
    finally:
        con.close()


def test_valor_fora_da_tabela_fecha_a_venda_mas_a_invoice_espera_o_dono(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Fora da Tabela", email="fora@example.com")
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={
        "amount": 250, "preco_tabela": 350,
        "passos": {"cliente": True, "qbo": True, "waiver": False, "asana": False, "kommo": False}})
    assert r.status_code == 200
    f = r.json()["fechamento"]
    assert f["na_tabela"] is False and f["aprovado"] is False and "difere da tabela" in f["motivo_preco"]
    qbo = [p for p in f["passos"] if p["passo"] == "qbo"][0]
    # sem QuickBooks conectado o passo falha; o que importa é que o resto fechou
    assert qbo["ok"] is not True and r.json()["etapa"] == "GANHO"


def test_sem_servico_ou_valor_o_fechamento_e_recusado_com_texto_claro(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Sem Valor", email="semvalor@example.com", service=None, amount=None)
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={"passos": {}})
    assert r.status_code == 400 and "serviço e o valor" in r.json()["detail"]
    assert cli.post(f"{B}/sales/{oid}/step/inventado", headers=h).status_code == 400


def test_passo_sem_integracao_nao_derruba_o_fechamento(cli):
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Tudo Ligado", email="tudo@example.com")
    r = cli.post(f"{B}/sales/{oid}/close", headers=h, json={
        "amount": 350, "preco_tabela": 350,
        "passos": {"cliente": True, "qbo": True, "waiver": True, "asana": True, "kommo": True}})
    assert r.status_code == 200
    passo = {p["passo"]: p for p in r.json()["fechamento"]["passos"]}
    assert passo["cliente"]["ok"] is True
    assert all(passo[k]["ok"] is not True for k in ("qbo", "waiver", "asana"))
    assert all(passo[k]["detalhe"] for k in ("qbo", "waiver", "asana"))
    # kommo: esta oportunidade não veio do chat, então é um "nada a fazer" honesto
    assert passo["kommo"]["ok"] is True and "não veio do chat" in str(passo["kommo"])


# --------------------------------------------------------------- a IA da venda
def test_ia_age_na_oportunidade_e_recusa_o_que_nao_e_dela(cli):
    from command_center.api import acoes_painel
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Zeca IA", email="zeca@example.com")
    con = conectar()
    try:
        carla = um(con, "SELECT id FROM users WHERE email='closer@urace.us'")["id"]
        otto = um(con, "SELECT id FROM users WHERE email='outro@urace.us'")["id"]

        r = acoes_painel.executar(con, carla, "venda_anotar", {"nome": "Zeca", "texto": "quer sábado de manhã"})
        assert r["aplicado"] and r["oportunidade"] == oid

        r = acoes_painel.executar(con, carla, "venda_agendar_retorno", {"opp_id": oid, "quando": "2030-03-01"})
        assert r["aplicado"] and r["quando"].startswith("2030-03-01T")

        r = acoes_painel.executar(con, carla, "venda_registrar_ligacao",
                                  {"opp_id": oid, "resultado": "pensar", "texto": "ligou de volta"})
        assert r["aplicado"] and r["etapa"] == "CONVERSA"

        # Ganho não sai pela porta da etapa
        r = acoes_painel.executar(con, carla, "venda_mover_etapa", {"opp_id": oid, "etapa": "GANHO"})
        assert not r["aplicado"] and "venda_fechar" in r["motivo"]
        r = acoes_painel.executar(con, carla, "venda_mover_etapa", {"opp_id": oid, "etapa": "PERDIDO"})
        assert not r["aplicado"] and "motivo" in r["motivo"]

        # tarefa personalizada pela IA
        r = acoes_painel.executar(con, carla, "venda_tarefa", {"opp_id": oid, "titulo": "mandar o mapa da pista"})
        assert r["aplicado"] and r["onde"] == "painel"

        # oportunidade de outro closer: a IA não é atalho
        r = acoes_painel.executar(con, otto, "venda_anotar", {"opp_id": oid, "texto": "não devia entrar"})
        assert not r["aplicado"] and "outro closer" in r["motivo"]
        # nem por nome
        r = acoes_painel.executar(con, otto, "venda_anotar", {"nome": "Zeca", "texto": "nem assim"})
        assert not r["aplicado"] and "não achei" in r["motivo"]

        # resultado inventado é recusado com a lista do que vale
        r = acoes_painel.executar(con, carla, "venda_registrar_ligacao", {"opp_id": oid, "resultado": "talvez"})
        assert not r["aplicado"] and "fechou" in r["motivo"]
        con.commit()
    finally:
        con.close()


def test_acoes_de_venda_tem_politica_e_nome_no_catalogo(cli):
    con = conectar()
    try:
        pol = {p["action"]: p["policy"] for p in todos(con, "SELECT action, policy FROM action_policies")}
    finally:
        con.close()
    assert pol["venda_anotar"] == "SAFE" and pol["venda_agendar_retorno"] == "SAFE"
    assert pol["venda_enviar_waiver"] == "REQUIRES_CONFIRMATION"
    assert pol["venda_enviar_invoice"] == "REQUIRES_APPROVAL"
    assert pol["venda_fechar"] == "REQUIRES_CONFIRMATION"
    from command_center.api import acoes_painel
    nomes = {a["name"] for a in acoes_painel.descrever_todas()}
    assert {"venda_fechar", "venda_tarefa", "venda_enviar_invoice"} <= nomes


# --------------------------------------------------------------- acesso livre (sem cargo)
def test_conta_de_acesso_livre_nao_tem_cargo_e_ninguem_troca_o_papel(cli, monkeypatch):
    monkeypatch.setattr(auth, "ACESSO_LIVRE", ("dono@urace.us",))
    con = conectar()
    try:
        uid = auth.criar_usuario(con, "dono@urace.us", "Dono Livre", "VIEWER", SENHA)
        con.commit()
    finally:
        con.close()
    h = entra(cli, "dono@urace.us")
    eu = cli.get(B + "/auth/me", headers=h).json()
    assert eu["free"] is True
    # papel de leitura no banco, mas o acesso é irrestrito: alcança até o que é de ADMIN
    assert cli.get(B + "/users", headers=h).status_code == 200
    lista = cli.get(B + "/users", headers=h).json()
    assert [u for u in lista if u["id"] == uid][0]["free"] is True
    assert all(u["free"] is False for u in lista if u["email"] != "dono@urace.us")
    # e ninguém troca o cargo de quem não tem cargo
    ha = entra(cli, "admin@urace.us")
    r = cli.post(f"{B}/users/{uid}/role", headers=ha, json={"role": "OPERATOR"})
    assert r.status_code == 400 and "acesso livre" in r.json()["detail"]


# --------------------------------------------------------------- fuso da Florida
def test_dia_e_hoje_saem_no_fuso_da_florida():
    # 02:00Z de 18/03 ainda é 17/03 em Orlando — o painel precisa concordar com o dono
    assert vendas.dia_local("2030-03-18T02:00:00Z") == "2030-03-17"
    assert vendas.dia_local("2030-03-18T16:00:00Z") == "2030-03-18"
    assert vendas.dia_local(None) is None
    assert vendas.fim_do_dia_local() > vendas.hoje_local()
    assert len(vendas.hoje_local()) == 10


# ------------------------------------------- do texto da IA até a ação executada
def test_a_ia_declara_a_acao_o_painel_guarda_com_politica_e_executa(cli):
    from command_center.api import ia, motor
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Olga Fim", email="olga@example.com")
    con = conectar()
    try:
        carla = um(con, "SELECT id FROM users WHERE email='closer@urace.us'")["id"]
        cid = con.execute("INSERT INTO ai_commands (user_id, text, session_key, status) VALUES (?,?,?,'DONE')",
                          (carla, f"[oportunidade #{oid} — Olga Fim] anote que ela pediu sábado", "t")).lastrowid
        # o contexto que vai para a IA diz de que venda se trata e o nome exato de cada ação
        ctx = motor.contexto_da_venda(con, f"[oportunidade #{oid} — Olga Fim] anote isso")
        assert "CONTEXTO DA VENDA" in ctx and f'"opp_id": {oid}' in ctx.replace('"opp_id":', '"opp_id": ')
        assert "venda_fechar" in ctx and "Flórida" in ctx
        assert "SEM e-mail" not in ctx                      # esta ficha tem e-mail

        saida = ("Anotado.\n"
                 f'ACAO: venda_anotar | Olga Fim | guardar o pedido | {{"opp_id":{oid},"texto":"pediu sábado de manhã"}}')
        achadas = ia.extrair_acoes(con, cid, saida)
        assert [a["action"] for a in achadas] == ["venda_anotar"]
        con.commit()
        acao = um(con, "SELECT * FROM ai_actions WHERE command_id=?", (cid,))
        assert acao["policy"] == "SAFE" and acao["system"] in ("painel", "venda")
        con.execute("UPDATE ai_actions SET status='APPROVED' WHERE id=?", (acao["id"],))
        con.commit()
    finally:
        con.close()
    motor.executar_acao(acao["id"], carla)
    con = conectar()
    try:
        feita = um(con, "SELECT status, result FROM ai_actions WHERE id=?", (acao["id"],))
        assert feita["status"] == "DONE" and "aplicado" in feita["result"]
        assert "pediu sábado de manhã" in um(con, "SELECT notes FROM opportunities WHERE id=?", (oid,))["notes"]
    finally:
        con.close()


def test_contexto_avisa_quando_a_ficha_esta_sem_email(cli):
    from command_center.api import motor
    h = entra(cli, "closer@urace.us")
    oid = cria(cli, h, name="Sem Email", email=None, phone="+1 407 555 0111")
    con = conectar()
    try:
        ctx = motor.contexto_da_venda(con, f"[oportunidade #{oid} — Sem Email] manda a waiver")
        assert "SEM e-mail" in ctx
        assert motor.contexto_da_venda(con, "nada a ver com venda") == ""
        assert motor.contexto_da_venda(con, "[oportunidade #999999 — Fantasma] oi") == ""
    finally:
        con.close()
