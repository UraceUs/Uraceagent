"""Ponte de e-mail dos Suits (#153): o fluxo do Ítalo no VPS, com Gmail falso.

Ítalo (08/10): "entrou uma venda de macacão ... manda um e-mail automaticamente para o cliente
agradecendo ... manda por favor as medidas, e entregar o PDF ... quando o cliente responde ...
sem dar a informação do cliente ... manda para o Matheus ... a IA faz aquele meio de campo".
Dono: "rode na nossa mente de testes, faça simulações".
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from command_center.api import auth
from command_center.api.main import app
from command_center.db import aplicar_schema, conectar, todos, um
from command_center.providers import suits_ponte as sp

VENDA = {"message_id": "m-venda", "de": "Urace <urace@urace.us>", "data": "Sun, 27 Sep 2026", "assunto": "[Urace]: You've got a new order: #4738",
         "corpo": "You've received a new order from Ryan Casner: Order #4738 Fully Custom Kart Suit ×1 $420.75 "
                  "casnerracingdevelopment@example.com (916) 952-6271", "anexos": [], "message_id_header": "<v@x>"}
VENDA_CAMISETA = dict(VENDA, message_id="m-camiseta", assunto="[Urace]: You've got a new order: #3700",
                      corpo="New order: Urace T-shirts - 3XS ×1 $19.95")


class Gmail:
    """O que a ponte usa do gmail_mcp, com as conversas do teste."""

    def __init__(self):
        self.threads, self.buscas, self.enviados = {}, {}, []

    def gmail_buscar(self, conta, consulta, so_inbox=True, maximo=20):
        for chave, ids in self.buscas.items():
            if chave in consulta:
                return {"threads": [{"thread_id": t} for t in ids]}
        return {"threads": []}

    def mensagens_da_thread(self, conta, thread_id, limite=8000):
        return {"thread_id": thread_id, "mensagens": [dict(m) for m in self.threads.get(thread_id, [])]}

    def anexo_bytes(self, conta, message_id, attachment_id):
        return b"%PDF-1.4 medidas" if attachment_id.endswith("pdf") else b"\x89PNG logo"

    def enviar_sistema(self, *a, **kw):
        self.enviados.append(a)
        return {"id": "s1", "thread_id": "t-novo"}


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "ponte.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path / "urace"))
    monkeypatch.setenv("CC_EMAIL_FAKE", str(tmp_path / "enviados.jsonl"))
    c = conectar(); aplicar_schema(c)
    c.execute("INSERT INTO users (email, name, role, pw_salt, pw_hash) VALUES ('a@urace.us','Admin','ADMIN','x','x')")
    yield c
    c.close()


def _executor(chamadas):
    def ex(con, cid, texto, sk, uid, prompt):
        chamadas.append({"cid": cid, "texto": texto, "prompt": prompt, "simular": sp.SIMULAR.get()})
    return ex


def _enviados(tmp_path):
    f = tmp_path / "enviados.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


# ------------------------------------------------------------------ eventos
def test_venda_de_macacao_no_site_abre_o_pedido_e_chama_a_ia_uma_vez(con):
    gm, chamadas = Gmail(), []
    gm.threads = {"t-venda": [VENDA], "t-camiseta": [VENDA_CAMISETA]}
    gm.buscas = {'subject:"new order"': ["t-venda", "t-camiseta"]}
    r = sp.rodar(con, gm, _executor(chamadas))
    assert r["eventos"] == 1 and r["simulacao"] is True
    p = um(con, "SELECT * FROM suit_orders WHERE site_order='4738'")
    assert p["source"] == "site" and p["status"] == "standby"
    assert len(chamadas) == 1 and "VENDA NOVA NO SITE" in chamadas[0]["prompt"] and f"Suits #{p['id']}" in chamadas[0]["prompt"]
    assert "manual_medidas" in chamadas[0]["prompt"] and "Hi {first name}, thank you for your order" in chamadas[0]["prompt"]
    assert um(con, "SELECT text FROM ai_commands WHERE id=?", (chamadas[0]["cid"],))["text"].startswith("EVENTO AUTOMÁTICO — Suits")
    assert um(con, "SELECT 1 AS x FROM suit_email_seen WHERE message_id='m-camiseta'")      # camiseta não é da ponte
    assert sp.rodar(con, gm, _executor(chamadas))["eventos"] == 0 and len(chamadas) == 1    # cada e-mail uma vez só
    assert len(todos(con, "SELECT id FROM suit_orders")) == 1


def test_resposta_do_cliente_baixa_os_anexos_e_ignora_o_que_nos_mandamos(con):
    pid = con.execute("INSERT INTO suit_orders (title, customer_email, gmail_thread_cliente) VALUES ('Ryan','ryan@example.com','t-cli')").lastrowid
    gm, chamadas = Gmail(), []
    gm.threads = {"t-cli": [
        {"message_id": "m1", "de": "URACE <urace@urace.us>", "assunto": "Order - Suit", "corpo": "Hi Ryan, thank you…", "anexos": []},
        {"message_id": "m2", "de": "Ryan <ryan@example.com>", "assunto": "Re: Order - Suit", "corpo": "Black and red, logo attached. Head 59 cm",
         "anexos": [{"nome": "logo.png", "mime": "image/png", "attachment_id": "a-png", "bytes": 10},
                    {"nome": "sizing.pdf", "mime": "application/pdf", "attachment_id": "a-pdf", "bytes": 10}]}]}
    r = sp.rodar(con, gm, _executor(chamadas))
    assert r["eventos"] == 1 and len(chamadas) == 1
    assert "O CLIENTE RESPONDEU" in chamadas[0]["prompt"] and "logo.png" in chamadas[0]["prompt"] and "Head 59 cm" in chamadas[0]["prompt"]
    assert sp.anexos_do_pedido(pid) == ["logo.png", "sizing.pdf"]
    assert um(con, "SELECT 1 AS x FROM suit_email_seen WHERE message_id='m1'")               # a nossa mensagem não é evento
    assert sp.rodar(con, gm, _executor(chamadas))["eventos"] == 0


def test_conversas_novas_reconhecem_fornecedor_designer_e_quem_nao_tem_pedido(con):
    sp.salvar_config(con, {"designer_email": "designer@example.com", "designer_nome": "Matheus"})
    con.execute("INSERT INTO suit_suppliers (name, email, is_current) VALUES ('Usman','speedinds@example.com',1)")
    bennie = con.execute("INSERT INTO suit_orders (title) VALUES ('Bennie Schneider')").lastrowid
    gm, chamadas = Gmail(), []
    gm.threads = {
        "t-usman": [{"message_id": "u1", "de": "speedinds@example.com", "assunto": "Re: SUIT - Bennie Schneider (Team 6)", "corpo": "measurements are wrong"}],
        "t-design": [{"message_id": "d1", "de": "Matheus <designer@example.com>", "assunto": f"Re: Suits #{bennie} design", "corpo": "Art attached",
                      "anexos": [{"nome": "mockup.png", "mime": "image/png", "attachment_id": "a-png", "bytes": 10}]}],
        "t-novo": [{"message_id": "n1", "de": "Paula Carter <paula@example.com>", "assunto": "Race suit for Matthew", "corpo": "I'd like a suit"}]}
    gm.buscas = {"label:Suits": ["t-usman", "t-novo"], "from:designer@example.com": ["t-design"]}
    sp.rodar(con, gm, _executor(chamadas))
    tipos = {c["texto"].split(": ")[-1] for c in chamadas}
    assert tipos == {"fornecedor", "designer", "marcador"}
    b = um(con, "SELECT gmail_thread_fornecedor, gmail_thread_designer FROM suit_orders WHERE id=?", (bennie,))
    assert (b["gmail_thread_fornecedor"], b["gmail_thread_designer"]) == ("t-usman", "t-design")
    assert sp.anexos_do_pedido(bennie) == ["mockup.png"]
    # #182: o marcador não abre pedido; a IA lê e só cria se for pedido de macacão
    assert um(con, "SELECT 1 AS x FROM suit_orders WHERE customer_email='paula@example.com'") is None
    pr = next(c["prompt"] for c in chamadas if c["texto"].endswith("marcador"))
    assert "NENHUM PEDIDO FOI CRIADO" in pr and 'gmail_thread_cliente="t-novo"' in pr and "Paula Carter <paula@example.com>" in pr


# ------------------------------------------------------------------ #182: só o que é pedido vira pedido
def test_email_com_marcador_que_nao_e_pedido_nao_deixa_pedido_nenhum(con):
    """Dono, 09/10: "está colocando todo e-mail que a gente coloca lá como um pedido de suit. E não é isso"."""
    gm, chamadas = Gmail(), []
    gm.threads = {
        "t-fia": [{"message_id": "f1", "de": "FIA Homologation <homologation@example.org>", "assunto": "Homologation 8856-2018",
                   "corpo": "Please find the certificate attached."}],
        "t-news": [{"message_id": "w1", "de": "Sparco <news@example.com>", "assunto": "New 2027 suits!", "corpo": "Shop now"}]}
    gm.buscas = {"label:Suits": ["t-fia", "t-news"]}
    r = sp.rodar(con, gm, _executor(chamadas))
    assert r["eventos"] == 2 and len(chamadas) == 2
    assert todos(con, "SELECT id FROM suit_orders") == [], "o painel não cria nada: quem decide é a IA, e ela não criou"
    assert all("Na dúvida, NÃO crie" in c["prompt"] for c in chamadas)
    assert sp.rodar(con, gm, _executor(chamadas))["eventos"] == 0, "cada e-mail é lido uma vez"


def test_mais_conversas_que_o_ciclo_voltam_como_marcador_e_nao_como_cliente(con, monkeypatch):
    monkeypatch.setattr(sp, "POR_CICLO", 2)
    gm, chamadas = Gmail(), []
    gm.threads = {f"t{i}": [{"message_id": f"m{i}", "de": f"Pessoa {i} <p{i}@example.com>", "assunto": f"assunto {i}", "corpo": "oi"}]
                  for i in range(5)}
    gm.buscas = {"label:Suits": [f"t{i}" for i in range(5)]}
    r1 = sp.rodar(con, gm, _executor(chamadas))
    assert (r1["eventos"], r1["ficaram_para_o_proximo"]) == (5, 3)
    r2 = sp.rodar(con, gm, _executor(chamadas))
    assert r2["eventos"] == 3
    assert {c["texto"].split(": ")[-1] for c in chamadas} == {"marcador"}, "nada vira 'o cliente respondeu' sem pedido"
    assert todos(con, "SELECT id FROM suit_orders") == []


def test_qualquer_email_da_equipe_e_nosso():
    assert sp._nosso("Italo <italo@urace.us>") and sp._nosso("support@urace.us")
    assert not sp._nosso("Paula <paula@example.com>") and not sp._nosso("x@urace.us.fake.com")


def test_ponte_desligada_ou_sem_o_motor_novo_nao_roda(con, monkeypatch):
    from command_center.api import ia
    monkeypatch.setattr(ia, "motor_da_ia", lambda: "openclaw")
    assert "motor novo" in sp.rodar(con, Gmail())["pulada"]
    sp.salvar_config(con, {"ponte_ligada": "0"})
    assert sp.rodar(con, Gmail(), _executor([]))["pulada"] == "ponte desligada"


# ------------------------------------------------------------------ o envio
def _pedido(con, **kw):
    campos = {"title": "Ryan Casner", "customer_name": "Ryan Casner", "customer_email": "ryan@example.com",
              "customer_phone": "(916) 952-6271", "ship_address": "1200 Oak Street\nSan Diego CA", **kw}
    cols = ", ".join(campos)
    return con.execute(f"INSERT INTO suit_orders ({cols}) VALUES ({', '.join('?' * len(campos))})", tuple(campos.values())).lastrowid


def test_em_simulacao_nada_sai_e_o_email_fica_na_linha_do_tempo(con, tmp_path):
    pid = _pedido(con)
    with open(sp.manual_pdf(), "wb") as f:
        f.write(b"%PDF-1.4")
    r = sp.enviar(con, pid, "cliente", "Your custom suit", "Hi Ryan, thank you!", ["manual_medidas"])
    assert r["simulado"] is True and _enviados(tmp_path) == []
    n = um(con, "SELECT kind, text FROM suit_notes WHERE id=?", (r["nota"],))
    assert n["kind"] == "email" and n["text"].startswith("SIMULAÇÃO") and "ryan@example.com" in n["text"] and "GUIDE TO FILLING" in n["text"]


def test_com_envio_automatico_sai_para_o_cliente_com_o_manual_e_guarda_a_conversa(con, tmp_path):
    sp.salvar_config(con, {"envio_automatico": "1"})
    pid = _pedido(con)
    with open(sp.manual_pdf(), "wb") as f:
        f.write(b"%PDF-1.4")
    r = sp.enviar(con, pid, "cliente", "Your custom suit", "Hi Ryan, thank you!", ["manual_medidas"])
    assert r["simulado"] is False
    e = _enviados(tmp_path)[0]
    assert e["to"] == "ryan@example.com" and e["anexos"] == ["GUIDE TO FILLING IN SIZING - URACE FORM.pdf"]
    th = um(con, "SELECT gmail_thread_cliente FROM suit_orders WHERE id=?", (pid,))["gmail_thread_cliente"]
    assert th and um(con, "SELECT 1 AS x FROM suit_email_seen WHERE message_id=?", (r["id"],))     # o nosso não volta como evento
    # a simulação forçada vale mesmo com o envio automático ligado
    marca = sp.SIMULAR.set(True)
    try:
        assert sp.enviar(con, pid, "cliente", "x", "y")["simulado"] is True
    finally:
        sp.SIMULAR.reset(marca)
    assert len(_enviados(tmp_path)) == 1


def test_designer_nao_recebe_dado_do_cliente_e_cliente_nao_ve_o_designer(con, tmp_path):
    sp.salvar_config(con, {"envio_automatico": "1", "designer_email": "designer@example.com", "designer_nome": "Matheus"})
    pid = _pedido(con)
    for corpo in ("Customer email ryan@example.com", "Call him at 916-952-6271", "Ship to 1200 Oak Street", "Client: Ryan Casner"):
        with pytest.raises(sp.Recusado):
            sp.enviar(con, pid, "designer", f"Suits #{pid}", corpo)
    with pytest.raises(sp.Recusado):
        sp.enviar(con, pid, "cliente", "Your mockup", "Matheus made this for you")
    with pytest.raises(sp.Recusado):
        sp.enviar(con, pid, "cliente", "Your mockup", "Questions? designer@example.com")
    r = sp.enviar(con, pid, "designer", f"Suits #{pid} — new design", "Black and red, number 27, logo attached. Driver: Ryan.")
    assert r["para"] == "designer@example.com" and _enviados(tmp_path)[-1]["to"] == "designer@example.com"


def test_sem_destinatario_ou_sem_anexo_nao_sai(con):
    pid = _pedido(con, customer_email=None)
    with pytest.raises(sp.Recusado, match="e-mail do cliente"):
        sp.enviar(con, pid, "cliente", "a", "b")
    sp.salvar_config(con, {"designer_email": ""})
    pid2 = _pedido(con)
    with pytest.raises(sp.Recusado, match="designer não está configurado"):
        sp.enviar(con, pid2, "designer", "a", "b")
    with pytest.raises(sp.Recusado, match="manual de medidas"):
        sp.enviar(con, pid2, "cliente", "a", "b", ["manual_medidas"])
    with pytest.raises(sp.Recusado, match="anexo não encontrado"):
        sp.enviar(con, pid2, "cliente", "a", "b", ["../../etc/passwd"])


def test_a_ferramenta_da_ia_devolve_a_recusa_para_ela_corrigir(con):
    from command_center.api import suits as api_suits
    f = {nome: fn for nome, _, _, _, fn in api_suits.ferramentas_ia()}
    pid = _pedido(con)
    sp.salvar_config(con, {"designer_email": "designer@example.com"})
    r = f["suits_email"](con, None, pid, "designer", "brief", "Client email: ryan@example.com")
    assert "recusado" in r and "designer não pode receber" in r["recusado"]
    assert f["suits_precisa_humano"](con, None, pid, "cliente pediu reembolso")["ok"]
    f["suits_precisa_humano"](con, None, pid, "de novo")
    assert len(todos(con, "SELECT id FROM ai_events WHERE kind='suit.humano'")) == 1             # um aviso por pedido
    from command_center.api import agente_sdk
    assert agente_sdk.classificar(con, "suits_email") == "fazer"          # sem o gargalo da aprovação (Ítalo, 08/10)


def test_simular_um_pedido_le_as_conversas_e_nada_sai(con, tmp_path):
    sp.salvar_config(con, {"envio_automatico": "1"})
    pid = _pedido(con, gmail_thread_cliente="t-cli")
    gm, chamadas = Gmail(), []
    gm.threads = {"t-cli": [{"message_id": "m2", "de": "Ryan <ryan@example.com>", "assunto": "Re: Order", "corpo": "design attached", "anexos": []}]}
    sp.simular_pedido(con, pid, gm, _executor(chamadas))
    assert chamadas[0]["simular"] is True and "SIMULAÇÃO NESTE PEDIDO" in chamadas[0]["prompt"] and "design attached" in chamadas[0]["prompt"]
    assert _enviados(tmp_path) == []


# ------------------------------------------------------------------ a API
SENHA = "senha-forte-123"


def test_api_da_ponte(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("URACE_DIR", str(tmp_path / "urace"))
    c = conectar(); aplicar_schema(c)
    auth.criar_usuario(c, "admin@urace.us", "Admin", "ADMIN", SENHA)
    auth.criar_usuario(c, "op@urace.us", "Op", "OPERATOR", SENHA)
    c.close()
    with TestClient(app, base_url="https://cc.test") as cli:
        def entra(email):
            cli.cookies.clear()
            assert cli.post("/ops/api/auth/login", json={"email": email, "password": SENHA}).status_code == 200
            return {"X-CSRF": cli.cookies.get("cc_csrf")}
        h = entra("op@urace.us")
        v = cli.get("/ops/api/suits/ponte").json()
        assert v["config"]["envio_automatico"] == "0" and v["manual"] is False      # começa em simulação
        assert cli.put("/ops/api/suits/ponte", headers=h, json={"envio_automatico": True}).status_code == 403
        h = entra("admin@urace.us")
        r = cli.put("/ops/api/suits/ponte", headers=h, json={"designer_nome": "Matheus", "designer_email": "designer@example.com"})
        assert r.status_code == 200 and r.json()["config"]["designer_email"] == "designer@example.com"
        assert cli.put("/ops/api/suits/ponte", headers=h, json={"designer_email": "sem-arroba"}).status_code == 400
        assert cli.post("/ops/api/suits/ponte/manual", headers=h, files={"arquivo": ("x.pdf", b"nao e pdf", "application/pdf")}).status_code == 400
        assert cli.post("/ops/api/suits/ponte/manual", headers=h, files={"arquivo": ("m.pdf", b"%PDF-1.4 ok", "application/pdf")}).status_code == 200
        assert cli.get("/ops/api/suits/ponte").json()["manual"] is True
        assert cli.get("/ops/api/suits/ponte/manual").content.startswith(b"%PDF")
        pid = cli.post("/ops/api/suits", headers=h, json={"customer_name": "Ryan",
                       "gmail_thread_cliente": "https://mail.google.com/mail/?authuser=urace@urace.us#all/thread-f:1877504265922336989"}).json()["id"]
        assert cli.get(f"/ops/api/suits/{pid}").json()["gmail_thread_cliente"] == "1a0e3c2eb294d8dd"   # o link vira o id da thread
        os.makedirs(sp.pasta(pid), exist_ok=True)
        with open(os.path.join(sp.pasta(pid), "logo.png"), "wb") as f:
            f.write(b"\x89PNG")
        assert cli.get(f"/ops/api/suits/{pid}/anexos").json() == [{"nome": "logo.png", "bytes": 4}]
        assert cli.get(f"/ops/api/suits/{pid}/anexos/logo.png").content == b"\x89PNG"
        assert cli.get(f"/ops/api/suits/{pid}/anexos/..%2F..%2Fsuits.sqlite").status_code == 404
        feitos = []
        monkeypatch.setattr(sp, "simular_pedido", lambda con, p, *a, **k: feitos.append(p))
        monkeypatch.setattr(sp, "rodar_em_segundo_plano", lambda: True)
        assert cli.post(f"/ops/api/suits/{pid}/ponte/simular", headers=h).status_code == 202
        assert cli.post("/ops/api/suits/ponte/rodar", headers=h).json()["iniciada"] is True
        import time
        for _ in range(50):
            if feitos:
                break
            time.sleep(0.05)
        assert feitos == [pid]


# ------------------------------------------------- regras do robô do Ítalo (Mio, 08/10, #156)
def test_padroes_do_mio_designer_assinatura_e_politica(con):
    cfg = sp.config(con)
    assert (cfg["designer_nome"], cfg["designer_email"]) == ("Mateus", "carvalhovisual1@gmail.com")
    assert cfg["assinatura"].splitlines()[:4] == ["Best regards,", "George", "", "Urace"] and "Eduardo" not in cfg["assinatura"]
    assert "three rounds of design revisions" in cfg["boas_vindas"] and "50% off" in cfg["boas_vindas"] and "33% off" in cfg["boas_vindas"]
    assert "Três rodadas" in cfg["politica"] and "33%" in cfg["politica"]


def test_o_prompt_leva_a_politica_e_nao_repete_as_boas_vindas(con):
    _pedido(con, gmail_thread_cliente="t-cli")
    gm, chamadas = Gmail(), []
    gm.threads = {"t-cli": [{"message_id": "r1", "de": "Ryan <ryan@example.com>", "assunto": "Re: Order - Suit", "corpo": "Ideas attached", "anexos": []}]}
    sp.rodar(con, gm, _executor(chamadas))
    pr = chamadas[0]["prompt"]
    assert "POLÍTICA DOS MACACÕES" in pr and "Três rodadas" in pr
    assert "não mande de novo" in pr and "não mande adendo de política" in pr and "não fabricante" in pr
    assert "George" in pr


def _jpeg_com_exif(texto):
    import io

    from PIL import Image
    im = Image.new("RGB", (64, 48), (200, 30, 30))
    exif = Image.Exif()
    exif[0x013B] = texto             # Artist
    b = io.BytesIO()
    im.save(b, "JPEG", exif=exif.tobytes())
    return b.getvalue()


def test_arte_do_designer_vai_ao_cliente_sem_nome_nem_metadados(con, tmp_path):
    sp.salvar_config(con, {"envio_automatico": "1"})
    pid = _pedido(con)
    sujo = _jpeg_com_exif("Mateus Carvalho carvalhovisual1@gmail.com")
    assert b"carvalhovisual1" in sujo
    sp.guardar_anexo(pid, "mateus_mockup_final.jpg", sujo)
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(100, 100); w.add_metadata({"/Author": "Mateus", "/Creator": "carvalhovisual1@gmail.com"})
    import io
    b = io.BytesIO(); w.write(b)
    sp.guardar_anexo(pid, "proof.pdf", b.getvalue())
    sp.enviar(con, pid, "cliente", "Your mockup", "Here is your mockup for approval.", ["mateus_mockup_final.jpg", "proof.pdf"])
    e = _enviados(tmp_path)[-1]
    assert e["anexos"] == ["URACE-design-1.jpg", "proof.pdf"]
    # o que saiu mesmo: os bytes limpos (o envio falso grava os nomes; aqui conferimos a limpeza direto)
    limpos = sp.limpar_para_cliente([("mateus_mockup_final.jpg", sujo, "image/jpeg"), ("proof.pdf", b.getvalue(), "application/pdf")],
                                    sp.config(con))
    for nome, dados, _ in limpos:
        assert b"carvalhovisual1" not in dados.lower() and b"mateus" not in dados.lower(), nome


def test_arquivo_que_nao_da_para_limpar_e_carrega_o_designer_nao_sai(con):
    sp.salvar_config(con, {"envio_automatico": "1"})
    pid = _pedido(con)
    sp.guardar_anexo(pid, "arte.ai", b"%!PS-Adobe Creator: carvalhovisual1@gmail.com")
    with pytest.raises(sp.Recusado, match="designer"):
        sp.enviar(con, pid, "cliente", "Your art", "Attached.", ["arte.ai"])
    # o manual de medidas é nosso: passa como está
    with open(sp.manual_pdf(), "wb") as f:
        f.write(b"%PDF-1.4 manual")
    assert sp.enviar(con, pid, "cliente", "Sizing", "Attached.", ["manual_medidas"])["simulado"] is False

