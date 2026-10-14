"""Cada vendedor conecta o próprio Google Calendar, nos dois sentidos (#220).

Dono, 14/10: *"conectar ao Google Calendar e aí coloca um login com o Google, que aí ele consegue
logar com a conta dele do Google"*. Tudo aqui fala com o Google FALSO (`google_falso.py`), num
servidor local: nenhuma chamada sai da máquina.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import cofre, google_agenda
from command_center.tests.google_falso import GoogleFalso, credenciais_json

B = "/ops/api"
SENHA = "senha-forte-123"
ENV = ("CC_DB_PATH", "CC_COFRE_CHAVE", "CC_GOOGLE_BASE", "CC_GOOGLE_WEB_CREDENTIALS")


@pytest.fixture(scope="module")
def ambiente():
    antes = {k: os.environ.get(k) for k in ENV}
    pasta = tempfile.mkdtemp()
    fake = GoogleFalso()
    os.environ.update(CC_DB_PATH=os.path.join(pasta, "cc-google.sqlite"), CC_COFRE_CHAVE=cofre.nova_chave(),
                      CC_GOOGLE_BASE=fake.origem, CC_GOOGLE_WEB_CREDENTIALS=os.path.join(pasta, "google-web.json"))
    con = conectar()
    aplicar_schema(con)
    auth.criar_usuario(con, "carla@urace.us", "Carla Vendas", "OPERATOR", SENHA)
    auth.criar_usuario(con, "otto@urace.us", "Otto Vendas", "OPERATOR", SENHA)
    auth.criar_usuario(con, "mec@urace.us", "Mec", "OPERATOR", SENHA)
    con.execute("UPDATE users SET cargo='MECANICO' WHERE email='mec@urace.us'")
    admin = auth.criar_usuario(con, "admin@urace.us", "Admin", "ADMIN", SENHA)
    chave = auth.criar_chave(con, "teste", "ADMIN", admin, somente_leitura=False)["chave"]
    con.close()
    yield fake, os.environ["CC_GOOGLE_WEB_CREDENTIALS"], chave
    fake.parar()
    for k, v in antes.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture()
def cli(ambiente):
    with TestClient(app, base_url="https://cc.test") as c:
        yield c


@pytest.fixture()
def credencial(ambiente):
    _, caminho, _ = ambiente
    with open(caminho, "w") as f:
        f.write(credenciais_json())
    yield caminho
    os.remove(caminho)


def entra(cli, email):
    cli.cookies.clear()
    assert cli.post(B + "/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    return {"X-CSRF": cli.cookies.get("cc_csrf")}


def uid(email):
    con = conectar()
    try:
        return um(con, "SELECT id FROM users WHERE email=?", (email,))["id"]
    finally:
        con.close()


def conecta(cli, fake, h):
    """Botão → Google (Permitir) → volta ao painel. Devolve a resposta da volta."""
    r = cli.post(B + "/google/connect", headers=h)
    assert r.status_code == 200, r.text
    volta = fake.aprovar({k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()})
    u = urlsplit(volta)
    return cli.get(u.path + "?" + u.query, follow_redirects=False)


def cria_opp(cli, h, **campos):
    r = cli.post(B + "/sales", json={"name": "Marcos Teixeira", "phone": "+1 407 555 0144", **campos}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def quando(dias=1, hora=14):
    d = datetime.now(timezone.utc).replace(hour=hora, minute=0, second=0, microsecond=0) + timedelta(days=dias)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ sem o cliente OAuth na VPS
def test_sem_arquivo_de_credencial_o_botao_fica_desligado_e_diz_por_que(cli, ambiente):
    h = entra(cli, "carla@urace.us")
    s = cli.get(B + "/google/status").json()
    assert s["configurado"] is False and s["conectado"] is False
    assert "gerente" in s["motivo"] and "OAuth Web" in s["motivo"]
    assert cli.post(B + "/google/connect", headers=h).status_code == 503
    assert cli.get(B + "/sales/agenda").status_code == 200        # nada quebra na agenda


def test_arquivo_de_cliente_desktop_nao_serve(cli, ambiente):
    _, caminho, _ = ambiente
    with open(caminho, "w") as f:
        f.write(credenciais_json("installed"))
    try:
        entra(cli, "carla@urace.us")
        s = cli.get(B + "/google/status").json()
        assert s["configurado"] is False and "Desktop" in s["motivo"]
    finally:
        os.remove(caminho)


# ------------------------------------------------------------------ o fluxo OAuth
def test_conectar_pelo_google_guarda_o_token_cifrado_e_audita_sem_token(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    r = cli.post(B + "/google/connect", headers=h)
    q = parse_qs(urlsplit(r.json()["url"]).query)
    assert r.json()["url"].startswith(fake.origem + "/auth?")
    assert q["redirect_uri"] == ["https://ops.urace.us/ops/api/google/callback"]   # derivado do endereço do painel
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert "https://www.googleapis.com/auth/calendar.events" in q["scope"][0].split()
    volta = fake.aprovar({k: v[0] for k, v in q.items()})
    u = urlsplit(volta)
    r = cli.get(u.path + "?" + u.query, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ops/sales/agenda?google=ok"
    s = cli.get(B + "/google/status").json()
    assert s["conectado"] and s["email"] == "vendedor.teste@gmail.com"     # conta Google qualquer, não só @urace.us

    con = conectar()
    c = um(con, "SELECT * FROM google_conexoes WHERE user_id=?", (uid("carla@urace.us"),))
    at = cofre.decifrar(c["access_enc"], f"google:{c['user_id']}:access")
    rt = cofre.decifrar(c["refresh_enc"], f"google:{c['user_id']}:refresh")
    assert at in fake.access and rt in fake.refresh
    assert c["access_enc"].startswith("v1:") and at not in c["access_enc"] and rt not in c["refresh_enc"]
    with pytest.raises(cofre.ChaveErrada):                  # o token de um não abre como de outro
        cofre.decifrar(c["access_enc"], f"google:{uid('otto@urace.us')}:access")
    aud = todos(con, "SELECT event, detail FROM audit_logs WHERE event LIKE 'google.%'")
    con.close()
    assert any(a["event"] == "google.connect" and "vendedor.teste@gmail.com" in a["detail"] for a in aud)
    assert not any(at in (a["detail"] or "") or rt in (a["detail"] or "") for a in aud)


def test_state_adulterado_reusado_ou_de_outro_navegador_e_recusado(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "otto@urace.us")
    r = cli.post(B + "/google/connect", headers=h)
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    volta = urlsplit(fake.aprovar(q))
    caminho = volta.path + "?" + volta.query
    bom = q["state"]

    adulterado = caminho.replace(bom, bom[:-3] + ("AAA" if not bom.endswith("AAA") else "BBB"))
    assert cli.get(adulterado, follow_redirects=False).headers["location"].endswith("google=erro&motivo=estado")
    inventado = caminho.replace(bom, "x" * 20)
    assert cli.get(inventado, follow_redirects=False).headers["location"].endswith("google=erro&motivo=estado")

    nonce = cli.cookies.get("cc_gstate")
    cli.cookies.delete("cc_gstate")                          # o link foi aberto em outro navegador
    assert cli.get(caminho, follow_redirects=False).headers["location"].endswith("google=erro&motivo=estado")
    cli.cookies.set("cc_gstate", nonce, domain="cc.test", path="/ops/api/google/callback")
    # o state já foi queimado na tentativa anterior: nem o navegador certo usa de novo
    assert cli.get(caminho, follow_redirects=False).headers["location"].endswith("google=erro&motivo=estado")
    assert cli.get(B + "/google/status").json()["conectado"] is False


def test_state_vencido_e_recusado(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "otto@urace.us")
    r = cli.post(B + "/google/connect", headers=h)
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    con = conectar()
    con.execute("UPDATE google_oauth_states SET expires_at='2000-01-01T00:00:00.000Z' WHERE used_at IS NULL")
    con.close()
    v = urlsplit(fake.aprovar(q))
    assert cli.get(v.path + "?" + v.query, follow_redirects=False).headers["location"].endswith("motivo=estado")


def test_negar_no_google_ou_sem_permissao_de_agenda_nao_conecta(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "otto@urace.us")
    r = cli.post(B + "/google/connect", headers=h)
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.json()["url"]).query).items()}
    r = cli.get(f"{B}/google/callback?error=access_denied&state={q['state']}", follow_redirects=False)
    assert r.headers["location"].endswith("google=erro&motivo=negado")
    fake.conceder_escopo = False
    try:
        r = conecta(cli, fake, h)
    finally:
        fake.conceder_escopo = True
    assert r.headers["location"].endswith("google=erro&motivo=escopo")
    assert cli.get(B + "/google/status").json()["conectado"] is False


def test_so_a_pessoa_pelo_navegador_conecta(cli, ambiente, credencial):
    _, _, chave = ambiente
    cli.cookies.clear()
    assert cli.post(B + "/google/connect", headers={"Authorization": f"Bearer {chave}"}).status_code == 403
    assert cli.post(B + "/google/disconnect", headers={"Authorization": f"Bearer {chave}"}).status_code == 403
    h = entra(cli, "mec@urace.us")                            # mecânico: a trava do cargo fecha
    assert cli.post(B + "/google/connect", headers=h).status_code == 403


# ------------------------------------------------------------------ Painel → Google
def test_retorno_vira_evento_muda_junto_e_sai_ao_concluir_sem_tocar_no_que_nao_e_nosso(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    alheio = fake.evento_alheio("Dentista", "2030-01-01T10:00:00-05:00", "2030-01-01T11:00:00-05:00")
    fake.pedidos.clear()

    oid = cria_opp(cli, h, next_at=quando(1), next_what="ligar de volta", service="Arrive and Drive")
    con = conectar()
    m = um(con, "SELECT * FROM google_cal_events WHERE opp_id=?", (oid,))
    assert m and m["status"] == "ativo" and m["google_email"] == "vendedor.teste@gmail.com"
    ev = fake.eventos[m["event_id"]]
    assert ev["extendedProperties"]["private"]["urace_opp"] == str(oid)
    assert "Marcos Teixeira" in ev["summary"] and "ligar de volta" in ev["summary"]
    assert "407" not in ev["description"]                    # telefone do cliente não vai para o Google
    assert f"/ops/sales/{oid}" in ev["description"]
    ini = datetime.fromisoformat(ev["start"]["dateTime"])
    fim = datetime.fromisoformat(ev["end"]["dateTime"])
    assert (fim - ini) == timedelta(minutes=30) and ev["start"]["timeZone"] == "America/New_York"

    novo = quando(3, 16)
    assert cli.post(f"{B}/sales/{oid}/next", json={"quando": novo}, headers=h).status_code == 200
    m2 = um(con, "SELECT * FROM google_cal_events WHERE opp_id=?", (oid,))
    assert m2["event_id"] == m["event_id"]                   # o MESMO evento, atualizado
    assert datetime.fromisoformat(fake.eventos[m["event_id"]]["start"]["dateTime"]) == \
        datetime.fromisoformat(novo.replace("Z", "+00:00"))

    r = cli.post(f"{B}/sales/{oid}/stage", json={"etapa": "PERDIDO", "motivo": "foi para outra pista"}, headers=h)
    assert r.status_code == 200
    assert m["event_id"] not in fake.eventos                 # concluiu: o evento NOSSO saiu
    assert um(con, "SELECT status FROM google_cal_events WHERE opp_id=?", (oid,))["status"] == "removido"
    assert alheio in fake.eventos                            # o da pessoa ficou intacto
    assert not [p for p in fake.pedidos if alheio in p[1]]   # nem foi tocado
    con.close()


def test_registrar_ligacao_e_fechar_tambem_seguem_para_o_google(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    oid = cria_opp(cli, h)
    r = cli.post(f"{B}/sales/{oid}/call", json={"resultado": "pensar", "proximo_em": quando(2), "proximo_que": "mandar proposta"}, headers=h)
    assert r.status_code == 200
    con = conectar()
    m = um(con, "SELECT * FROM google_cal_events WHERE opp_id=?", (oid,))
    assert m and "mandar proposta" in fake.eventos[m["event_id"]]["summary"]
    r = cli.post(f"{B}/sales/{oid}/call", json={"resultado": "sem_interesse"}, headers=h)
    assert m["event_id"] not in fake.eventos
    con.close()


def test_retorno_de_outro_closer_nao_vai_para_o_meu_google(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    h2 = entra(cli, "otto@urace.us")                         # Otto não conectou
    oid = cria_opp(cli, h2, next_at=quando(1))
    con = conectar()
    assert um(con, "SELECT 1 AS x FROM google_cal_events WHERE opp_id=?", (oid,)) is None
    assert google_agenda.sincronizar_opp(con, oid) == "sem_conexao"
    con.close()


def test_ia_que_agenda_retorno_tambem_cria_o_evento(cli, ambiente, credencial):
    from command_center.api import acoes_painel
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    oid = cria_opp(cli, h)
    con = conectar()
    r = acoes_painel.executar(con, uid("carla@urace.us"), "venda_agendar_retorno", {"opp_id": oid, "quando": quando(4)})
    assert r["aplicado"]
    m = um(con, "SELECT * FROM google_cal_events WHERE opp_id=?", (oid,))
    assert m and m["event_id"] in fake.eventos
    con.close()


# ------------------------------------------------------------------ Google → Painel
def test_a_agenda_le_os_eventos_da_propria_pessoa_sem_repetir_os_nossos(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    amanha = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    fake.evento_alheio("Reunião com fornecedor", f"{amanha}T13:00:00-04:00", f"{amanha}T14:00:00-04:00")
    fake.evento_alheio("Lembrete livre", f"{amanha}T15:00:00-04:00", f"{amanha}T15:30:00-04:00", transparency="transparent")
    cria_opp(cli, h, next_at=quando(1))
    r = cli.get(B + "/google/events")
    assert r.status_code == 200 and "private" in r.headers["cache-control"]   # nunca em cache compartilhado
    d = r.json()
    titulos = {e["titulo"]: e for e in d["eventos"]}
    assert d["conectado"] and "Reunião com fornecedor" in titulos
    assert titulos["Reunião com fornecedor"]["ocupado"] is True and titulos["Lembrete livre"]["ocupado"] is False
    assert not [e for e in d["eventos"] if (e["titulo"] or "").startswith("URACE ·")]   # os nossos não voltam
    assert cli.get(B + "/google/events?de=2030-01-01&ate=2031-01-01").status_code == 400

    entra(cli, "otto@urace.us")                              # outra pessoa não vê nada da Carla
    assert cli.get(B + "/google/events").json() == {"conectado": False, "eventos": [], "de": d["de"], "ate": d["ate"]}


def test_token_vencido_renova_sozinho_e_renovacao_recusada_pede_para_reconectar(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    eu = uid("carla@urace.us")
    con = conectar()
    antes = um(con, "SELECT access_enc FROM google_conexoes WHERE user_id=?", (eu,))["access_enc"]
    con.execute("UPDATE google_conexoes SET expires_at='2000-01-01T00:00:00.000Z' WHERE user_id=?", (eu,))
    assert cli.get(B + "/google/events").json()["conectado"] is True
    depois = um(con, "SELECT access_enc, expires_at FROM google_conexoes WHERE user_id=?", (eu,))
    assert depois["access_enc"] != antes and depois["expires_at"] > "2001"

    con.execute("UPDATE google_conexoes SET expires_at='2000-01-01T00:00:00.000Z' WHERE user_id=?", (eu,))
    fake.recusar_refresh = True
    try:
        d = cli.get(B + "/google/events").json()
    finally:
        fake.recusar_refresh = False
    assert d["conectado"] is False and "conecte de novo" in d["erro"]
    s = cli.get(B + "/google/status").json()
    assert s["expirado"] and not s["conectado"]
    c = um(con, "SELECT access_enc, refresh_enc FROM google_conexoes WHERE user_id=?", (eu,))
    assert c["access_enc"] is None and c["refresh_enc"] is None
    con.close()
    assert conecta(cli, fake, h).headers["location"].endswith("google=ok")   # reconectar resolve
    assert cli.get(B + "/google/status").json()["conectado"]


def test_desconectar_revoga_e_apaga_so_o_token_da_pessoa(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    eu = uid("carla@urace.us")
    con = conectar()
    rt = cofre.decifrar(um(con, "SELECT refresh_enc FROM google_conexoes WHERE user_id=?", (eu,))["refresh_enc"], f"google:{eu}:refresh")
    nossos_antes = set(fake.nossos())
    r = cli.post(B + "/google/disconnect", headers=h)
    assert r.status_code == 200 and r.json()["revogado"] is True
    assert rt in fake.revogados
    assert um(con, "SELECT 1 AS x FROM google_conexoes WHERE user_id=?", (eu,)) is None
    assert set(fake.nossos()) == nossos_antes                # o calendário dela não é mexido ao sair
    aud = um(con, "SELECT detail FROM audit_logs WHERE event='google.disconnect' ORDER BY id DESC LIMIT 1")
    assert "vendedor.teste@gmail.com" in aud["detail"] and rt not in aud["detail"]
    con.close()
    assert cli.get(B + "/google/status").json()["conectado"] is False


def test_o_log_de_acesso_nao_guarda_o_codigo_nem_o_state():
    linha = '127.0.0.1 - "GET /ops/api/google/callback?state=abc.def&code=4/0Asegredo&scope=x HTTP/1.1" 303'
    m = google_agenda.mascarar(linha)
    assert "4/0Asegredo" not in m and "abc.def" not in m and "code=***" in m


def test_google_fora_do_ar_nao_derruba_a_venda_e_o_laco_acerta_depois(cli, ambiente, credencial):
    fake, _, _ = ambiente
    h = entra(cli, "carla@urace.us")
    if not cli.get(B + "/google/status").json()["conectado"]:
        conecta(cli, fake, h)
    os.environ["CC_GOOGLE_BASE"] = "http://127.0.0.1:9"      # porta fechada: o Google "caiu"
    try:
        oid = cria_opp(cli, h, next_at=quando(5))
    finally:
        os.environ["CC_GOOGLE_BASE"] = fake.origem
    s = cli.get(B + "/google/status").json()
    assert s["conectado"] and "sem conexão" in (s["erro"] or "")
    con = conectar()
    assert um(con, "SELECT 1 AS x FROM google_cal_events WHERE opp_id=? AND status='ativo'", (oid,)) is None
    feito = google_agenda.rodar(con)                         # o laço automático (a cada 15 min)
    m = um(con, "SELECT event_id FROM google_cal_events WHERE opp_id=? AND status='ativo'", (oid,))
    con.close()
    assert feito.get("criado", 0) >= 1 and m["event_id"] in fake.eventos
    assert cli.get(B + "/google/status").json()["erro"] is None
