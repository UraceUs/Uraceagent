#!/usr/bin/env python3
"""Servidor MCP do DocuSign para o Administrative AI.

Roda no HOST. Autentica por JWT (chave RSA em ~/.urace/, escopo
`signature impersonation`), assinando com o `openssl` da máquina -- sem
biblioteca Python nenhuma. O agente, no container, recebe só as
ferramentas; nem a chave nem o token chegam lá.

As regras do dono que viram código:

  - ENVIAR é a única escrita, e passa pelas 4 travas da skill DENTRO da
    ferramenta: waiver válida (< 1 ano) → recusa; envelope em aberto →
    recusa; idade não confirmada → recusa; nome/e-mail não conferidos →
    recusa. O modelo não tem como pular uma trava: elas rodam antes da
    chamada, no servidor.
  - Template só pelo ID, e só os dois reais. Nome nunca.
  - Base `demo.docusign.net` → envio SEMPRE recusado. Waiver de demo não
    tem validade jurídica. Leitura no demo é permitida (é a homologação).
  - `sendReminder` existe desde 22/09, e só nas condições que o dono deu
    ao decidir U-01: cliente com serviço MARCADO no futuro, 3 dias antes
    ou 1 dia antes, no máximo 2 por envelope. A política abriu a porta; a
    condição virou trava aqui dentro — ver `avaliar_lembrete`.
  - APLICAR=0 (padrão) transforma o envio em simulação.

Ver skills/urace-docusign/SKILL.md e brain/40_SISTEMAS/DocuSign.md.
"""
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

# fonte: brain/00_SYSTEM/PARAMETROS.md -- só estes dois existem para a automação
TEMPLATES = {
    "6dbf2094-39da-4c21-95dd-feda7ac28022": "Parental consent Waiver liability (menor → responsável)",
    "c51aede4-bba5-40df-9f14-24c340e2bd3e": "Adult Waiver (maior → piloto)",
}
ROLE_NAME = "Parental Consent Waiver Liability"   # mesmo nome nos dois templates
VALIDADE_WAIVER_DIAS = 365                          # PARAMETROS: 1 ano da assinatura
ABERTOS = ("sent", "delivered")                     # delivered NÃO é assinado


# ------------------------------------------------------------- ambiente
def _carregar_env():
    caminho = os.environ.get("URACE_ENV", os.path.expanduser("~/.urace/adminai.env"))
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    faltam = [k for k in ("DOCUSIGN_INTEGRATION_KEY", "DOCUSIGN_USER_ID",
                          "DOCUSIGN_ACCOUNT_ID", "DOCUSIGN_BASE_URI",
                          "DOCUSIGN_PRIVATE_KEY_PATH") if not os.environ.get(k)]
    if faltam:
        sys.exit(f"ERRO: faltam no env ({caminho}): {faltam}")
    chave = os.path.expanduser(os.environ["DOCUSIGN_PRIVATE_KEY_PATH"])
    if not os.path.isfile(chave):
        sys.exit(f"ERRO: chave privada não existe: {chave}")


def _base():
    return os.environ["DOCUSIGN_BASE_URI"].rstrip("/")


def _eh_demo():
    return "demo.docusign.net" in _base()


def _auth_host():
    return "account-d.docusign.com" if _eh_demo() else "account.docusign.com"


def _aplicar():
    return os.environ.get("APLICAR", "0") == "1"


# ------------------------------------------------------------------- JWT
def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _assinar_rs256(dados, caminho_chave):
    """RS256 pelo openssl da máquina: sem PyJWT, sem cryptography."""
    r = subprocess.run(["openssl", "dgst", "-sha256", "-sign", caminho_chave],
                       input=dados, capture_output=True)
    if r.returncode != 0:
        raise ErroFerramenta(f"openssl não assinou: {r.stderr.decode(errors='replace')[:200]}")
    return r.stdout


_token = {"valor": None, "expira": 0}


def _access_token():
    if _token["valor"] and time.time() < _token["expira"] - 60:
        return _token["valor"]
    agora = int(time.time())
    header = _b64url(json.dumps({"typ": "JWT", "alg": "RS256"}).encode())
    corpo = _b64url(json.dumps({
        "iss": os.environ["DOCUSIGN_INTEGRATION_KEY"],
        "sub": os.environ["DOCUSIGN_USER_ID"],
        "aud": _auth_host(),
        "iat": agora, "exp": agora + 3600,
        "scope": "signature impersonation",
    }).encode())
    assinatura = _b64url(_assinar_rs256(f"{header}.{corpo}".encode(),
                                        os.path.expanduser(os.environ["DOCUSIGN_PRIVATE_KEY_PATH"])))
    jwt = f"{header}.{corpo}.{assinatura}"
    dados = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt}).encode()
    req = urllib.request.Request(f"https://{_auth_host()}/oauth/token", data=dados, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        texto = e.read().decode(errors="replace")[:400]
        if "consent_required" in texto:
            raise ErroFerramenta(
                "consent_required: o JWT ainda não foi autorizado por um humano neste ambiente "
                f"({_auth_host()}). Ver docs/adminai/docusign-go-live.md, passo 4. ESCALAR.")
        raise ErroFerramenta(f"token JWT recusado (HTTP {e.code}): {texto}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com {_auth_host()}: {e.reason}")
    _token["valor"] = resp["access_token"]
    _token["expira"] = time.time() + int(resp.get("expires_in", 3600))
    return _token["valor"]


# ------------------------------------------------------------------ REST
def _req(caminho, metodo="GET", corpo=None, absoluto=False):
    url = caminho if absoluto else (
        f"{_base()}/restapi/v2.1/accounts/{os.environ['DOCUSIGN_ACCOUNT_ID']}{caminho}")
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {_access_token()}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
            return json.loads(bruto) if bruto else {}
    except urllib.error.HTTPError as e:
        raise ErroFerramenta(f"HTTP {e.code} em {metodo} {caminho}: "
                             f"{e.read()[:400].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o DocuSign: {e.reason}")


def _iso_dias_atras(dias):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resumo_envelope(e):
    sigs = []
    for s in (e.get("recipients") or {}).get("signers", []):
        sigs.append({"nome": s.get("name"), "email": s.get("email"),
                     "status": s.get("status"), "assinou_em": s.get("signedDateTime")})
    return {
        "envelopeId": e.get("envelopeId"), "assunto": e.get("emailSubject"),
        "status": e.get("status"), "enviado_em": e.get("sentDateTime"),
        "concluido_em": e.get("completedDateTime"), "expira_em": e.get("expireDateTime"),
        "template": e.get("templateId"), "signatarios": sigs or None,
        "aviso": "delivered = abriu e NÃO assinou; só completed conta" if e.get("status") == "delivered" else None,
    }


def _envelopes_de(email, desde_dias):
    """Todos os envelopes (qualquer status) que tenham esse e-mail como signatário."""
    email = email.strip().lower()
    q = urllib.parse.urlencode({"from_date": _iso_dias_atras(desde_dias),
                                "include": "recipients", "count": 100})
    achados = []
    for e in _req(f"/envelopes?{q}").get("envelopes", []):
        for s in (e.get("recipients") or {}).get("signers", []):
            if (s.get("email") or "").strip().lower() == email:
                achados.append(e)
                break
    return achados


# ----------------------------------------------------- PORTAS HUMANAS
# Funções chamadas só pelo Command Center num clique de pessoa. NÃO são
# ferramentas do MCP: o agente não as enxerga. Não passam por APLICAR
# (é ação humana) e são auditadas pelo Command Center.
def _req_bytes(caminho, accept="application/pdf"):
    url = f"{_base()}/restapi/v2.1/accounts/{os.environ['DOCUSIGN_ACCOUNT_ID']}{caminho}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {_access_token()}")
    req.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise ErroFerramenta(f"HTTP {e.code} em GET {caminho}: {e.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o DocuSign: {e.reason}")


def baixar_documento_humano(envelopeId):
    """PDF combinado (documento + certificado) de um envelope. Bytes."""
    return _req_bytes(f"/envelopes/{envelopeId}/documents/combined?certificate=true")


def formulario_humano(envelopeId):
    """Campos preenchidos (form data): é onde vive o nome do menor na parental."""
    r = _req(f"/envelopes/{envelopeId}/form_data")
    campos = {}
    for f in r.get("formData", []) or []:
        if f.get("name") and f.get("value") not in (None, ""):
            campos[f["name"]] = f["value"]
    for rec in r.get("recipientFormData", []) or []:
        for f in rec.get("formData", []) or []:
            if f.get("name") and f.get("value") not in (None, ""):
                campos.setdefault(f["name"], f["value"])
    return campos


# ---- modelos (dono, 16/09): ver, renomear e trocar o PDF, pela tela do painel
def modelo_humano(templateId):
    """Um modelo por inteiro: nome, documentos (id, nome, páginas), papéis e quantos campos
    (tabs) cada papel tem no documento. É o que a tela mostra antes de deixar mexer."""
    t = _req(f"/templates/{templateId}?include=recipients,tabs")
    docs = _req(f"/templates/{templateId}/documents").get("templateDocuments", []) or []
    papeis = []
    for s in (t.get("recipients") or {}).get("signers", []) or []:
        tabs = s.get("tabs") or {}
        papeis.append({"papel": s.get("roleName"), "recipientId": s.get("recipientId"),
                       "campos": sum(len(v) for v in tabs.values() if isinstance(v, list)),
                       "ancoras": sorted({x.get("anchorString") for v in tabs.values() if isinstance(v, list)
                                          for x in v if x.get("anchorString")})})
    return {"templateId": templateId, "nome": t.get("name"), "descricao": t.get("description"),
            "alterado_em": t.get("lastModified"), "compartilhado": t.get("shared"),
            "documentos": [{"documentId": d.get("documentId"), "nome": d.get("name"), "paginas": d.get("pages")} for d in docs],
            "papeis": papeis, "uso_pela_IA": TEMPLATES.get(templateId)}


def baixar_documento_do_modelo_humano(templateId, documentId):
    """O PDF de um documento do modelo, como está hoje. Bytes."""
    return _req_bytes(f"/templates/{templateId}/documents/{documentId}")


def renomear_modelo_humano(templateId, nome):
    """Só o nome. Nada mais do modelo é tocado."""
    nome = (nome or "").strip()
    if not (2 <= len(nome) <= 120):
        raise ErroFerramenta("nome do modelo: entre 2 e 120 caracteres")
    _req(f"/templates/{templateId}", "PUT", {"name": nome})
    return {"ok": True, "templateId": templateId, "nome": nome}


def substituir_documento_do_modelo_humano(templateId, documentId, nome_arquivo, pdf):
    """Troca o PDF de UM documento do modelo, mantendo o documentId — assim os campos de
    assinatura (tabs) continuam presos a ele. Se o novo PDF tiver outro leiaute, os campos
    por posição podem cair no lugar errado; os por âncora de texto seguem a âncora.
    Quem chama guarda o PDF antigo antes (Command Center). Bytes têm de ser PDF."""
    if not pdf or not pdf.startswith(b"%PDF"):
        raise ErroFerramenta("o arquivo não é um PDF")
    nome_arquivo = (nome_arquivo or "documento.pdf").strip()[:100]
    corpo = {"documents": [{"documentId": str(documentId), "name": nome_arquivo, "fileExtension": "pdf",
                            "documentBase64": base64.b64encode(pdf).decode()}]}
    r = _req(f"/templates/{templateId}/documents/{documentId}", "PUT", corpo)
    return {"ok": True, "templateId": templateId, "documentId": str(documentId), "nome": nome_arquivo, "resposta": r}


def anular_humano(envelopeId, motivo):
    """Anula (void) um envelope em aberto. Envelope completed NÃO pode ser
    anulado nem apagado por aqui: é documento assinado."""
    e = _req(f"/envelopes/{envelopeId}")
    if e.get("status") == "completed":
        raise ErroFerramenta("RECUSADO: envelope assinado é registro legal; fica no DocuSign. "
                             "No painel dá para ocultar.")
    if e.get("status") == "voided":
        return {"aplicado": False, "ja_estava": "voided"}
    _req(f"/envelopes/{envelopeId}", "PUT", {"status": "voided", "voidedReason": (motivo or "Anulado pelo Command Center")[:200]})
    return {"aplicado": True, "envelopeId": envelopeId, "status": "voided"}


def reenviar_humano(envelopeId, novo_email=None, novo_nome=None):
    """Reenvia a notificação ao signatário; se veio e-mail novo, corrige antes
    (caso do e-mail devolvido)."""
    e = _req(f"/envelopes/{envelopeId}?include=recipients")
    if e.get("status") not in ("sent", "delivered"):
        raise ErroFerramenta(f"RECUSADO: só envelope sent/delivered pode ser reenviado (está {e.get('status')}).")
    signers = (e.get("recipients") or {}).get("signers", [])
    if not signers:
        raise ErroFerramenta("envelope sem signatário")
    alvo = signers[0]
    if novo_email and novo_email.strip().lower() != (alvo.get("email") or "").lower():
        corpo = {"signers": [{"recipientId": alvo["recipientId"], "email": novo_email.strip(),
                              "name": (novo_nome or alvo.get("name") or "").strip()}]}
        r = _req(f"/envelopes/{envelopeId}/recipients?resend_envelope=true", "PUT", corpo)
        erros = [x for x in r.get("recipientUpdateResults", []) if (x.get("errorDetails") or {}).get("errorCode")]
        if erros:
            raise ErroFerramenta(f"DocuSign recusou a correção: {erros[0]['errorDetails']}")
        return {"aplicado": True, "reenviado": True, "email_corrigido": novo_email.strip()}
    _req(f"/envelopes/{envelopeId}/recipients?resend_envelope=true", "PUT",
         {"signers": [{"recipientId": alvo["recipientId"]}]})
    return {"aplicado": True, "reenviado": True, "email": alvo.get("email")}


# --------------------------------------- lembrete de waiver (trava do dono, 22/09)
DIAS_LEMBRETE = (3, 1)        # as duas únicas janelas: 3 dias antes e 1 dia antes
MAX_LEMBRETES = 2             # "2x" — o dono contou os lembretes, não as janelas
FUSO_CASA = "America/New_York"   # tudo no sistema roda no fuso de Orlando


def _painel():
    """O banco do Command Center, ou None se não der para abrir.

    O lembrete depende de um dado que só o painel tem: se aquele cliente tem
    serviço marcado. Sem banco não há como saber — e o que não se sabe não vira
    e-mail para cliente."""
    try:
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        from command_center.db import conectar
        return conectar()
    except Exception as e:                       # noqa: BLE001 - abrir banco é o extra, não o caminho
        log(f"lembrete: nao consegui abrir o banco do painel ({type(e).__name__}: {e})")
        return None


def _dia_local(iso):
    """A DATA de Orlando de um instante ISO, ou None se não der para ler.

    Contar em dias corridos (24h) daria "2 dias" para um serviço de amanhã de
    manhã visto hoje à noite. O dono falou em dias do calendário — é o que a
    pessoa vê na agenda."""
    from zoneinfo import ZoneInfo
    t = (iso or "").strip().replace("Z", "+00:00")
    if not t:
        return None
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        try:
            d = dt.datetime.fromisoformat(t[:19])
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(ZoneInfo(FUSO_CASA)).date()


def _clientes_do_email(con, email):
    linhas = con.execute(
        "SELECT id FROM clients WHERE email = ? "
        "UNION SELECT client_id FROM waivers WHERE signer_email = ? AND client_id IS NOT NULL",
        (email, email)).fetchall()
    return [r[0] for r in linhas if r[0] is not None]


def avaliar_lembrete(con, envelopeId, email, agora=None):
    """Decide se PODE lembrar aquele signatário. Devolve dict com `pode`, `motivo`
    e, quando pode, `dias` e `servico_em`.

    Dono (22/09), fechando U-01: pode lembrar, "2x". A condição inteira dele:
      - tem de haver serviço MARCADO no futuro para aquele e-mail;
      - só em duas janelas: 3 dias antes e 1 dia antes;
      - no máximo 2 lembretes por envelope, contados em `waiver_reminders`;
      - e a mesma janela não se repete (chamar duas vezes no mesmo dia não vale
        por dois).

    De propósito sem DocuSign nenhum aqui dentro: a regra é testável sozinha."""
    agora = agora or dt.datetime.now(dt.timezone.utc)
    email = (email or "").strip().lower()
    if not email:
        return {"pode": False, "motivo": "envelope sem e-mail de signatário"}

    feitos = con.execute("SELECT days_before FROM waiver_reminders WHERE envelope_id = ?",
                         (str(envelopeId),)).fetchall()
    if len(feitos) >= MAX_LEMBRETES:
        return {"pode": False,
                "motivo": f"já foram {len(feitos)} lembretes deste envelope; o dono autorizou {MAX_LEMBRETES}"}
    janelas_usadas = {r[0] for r in feitos}

    ids = _clientes_do_email(con, email)
    if not ids:
        return {"pode": False, "motivo": f"{email} não é cliente conhecido do painel"}
    marca = ",".join("?" * len(ids))
    eventos = con.execute(
        f"SELECT starts_at, COALESCE(title,'') FROM calendar_events "
        f"WHERE client_id IN ({marca}) AND starts_at IS NOT NULL ORDER BY starts_at", ids).fetchall()

    hoje = _dia_local(agora.isoformat())
    futuros = []
    for quando, titulo in eventos:
        dia = _dia_local(quando)
        if dia is None or dia < hoje:
            continue
        futuros.append(((dia - hoje).days, quando, titulo))
    if not futuros:
        return {"pode": False, "motivo": f"{email} não tem serviço marcado no futuro — sem serviço, sem lembrete"}

    futuros.sort()
    for dias, quando, titulo in futuros:
        if dias not in DIAS_LEMBRETE:
            continue
        if dias in janelas_usadas:
            continue
        return {"pode": True, "motivo": f"serviço em {dias} dia(s)", "dias": dias,
                "servico_em": quando, "servico": titulo}
    proximo = futuros[0][0]
    if proximo in janelas_usadas:
        return {"pode": False, "motivo": f"o lembrete de {proximo} dia(s) antes já foi mandado"}
    return {"pode": False,
            "motivo": f"o serviço mais próximo é daqui a {proximo} dia(s); só lembro a "
                      f"{DIAS_LEMBRETE[0]} e a {DIAS_LEMBRETE[1]} dia(s)"}


def registrar_lembrete(con, envelopeId, email, dias, servico_em):
    """Guarda o lembrete. É esta linha que impede o terceiro."""
    con.execute("INSERT INTO waiver_reminders (envelope_id, signer_email, days_before, service_at) "
                "VALUES (?,?,?,?)", (str(envelopeId), (email or "").strip().lower(), dias, servico_em))
    con.commit()


def enviar_waiver_humano(templateId, nome, email, servico=""):
    """Botão 'Enviar waiver' do Command Center. Não é ferramenta do agente. Não passa por APLICAR
    (a pessoa clicou), mas as travas de duplicidade (waiver válida / envelope aberto) continuam."""
    anterior = os.environ.get("APLICAR")
    os.environ["APLICAR"] = "1"
    try:
        return docusign_enviar_waiver(templateId, nome, email, idade_confirmada=True,
                                      nome_email_conferidos=True, servico=servico or "")
    finally:
        if anterior is None:
            os.environ.pop("APLICAR", None)
        else:
            os.environ["APLICAR"] = anterior


srv = Servidor("urace-docusign", "0.1")


# ----------------------------------------------------------- LEITURA
@srv.ferramenta(
    "docusign_ambiente",
    "Em qual ambiente o servidor está (demo ou produção), qual conta, e se o "
    "JWT autentica. CHAME PRIMEIRO. Se for demo, a conta está vazia de "
    "propósito (homologação) e nenhuma waiver real aparece aqui.")
def docusign_ambiente():
    info = _req(f"https://{_auth_host()}/oauth/userinfo", absoluto=True)
    contas = [{"accountId": a.get("account_id"), "nome": a.get("account_name"),
               "base_uri": a.get("base_uri"), "padrao": a.get("is_default")}
              for a in info.get("accounts", [])]
    return {
        "ambiente": "DEMO (homologação — sem validade jurídica)" if _eh_demo() else "PRODUÇÃO",
        "base_uri": _base(), "accountId": os.environ["DOCUSIGN_ACCOUNT_ID"],
        "usuario": info.get("email"), "contas_do_usuario": contas,
        "envio_permitido": (not _eh_demo()) and _aplicar(),
        "APLICAR": os.environ.get("APLICAR", "0"),
    }


@srv.ferramenta(
    "docusign_templates",
    "Templates da conta, com ID e papéis. Para waiver, usar SEMPRE pelo ID: "
    "só os dois de PARAMETROS existem para a automação; os outros são vazios.")
def docusign_templates():
    t = _req("/templates?include=recipients&count=100").get("envelopeTemplates", [])
    saida = []
    for x in t:
        tid = x.get("templateId")
        saida.append({"templateId": tid, "nome": x.get("name"),
                      "papeis": [s.get("roleName") for s in (x.get("recipients") or {}).get("signers", [])],
                      "uso_pela_IA": TEMPLATES.get(tid, "NÃO USAR — não é um dos dois reais")})
    return saida


@srv.ferramenta(
    "docusign_envelopes",
    "Lista envelopes por status, com signatários. Para a varredura diária use "
    "status 'sent,delivered' (os em aberto). Lembre: delivered NÃO é assinado.",
    {"status": {"type": "string", "description": "ex.: 'sent,delivered' ou 'completed'"},
     "desde_dias": {"type": "integer", "default": 120}},
    ["status"])
def docusign_envelopes(status, desde_dias=120):
    q = urllib.parse.urlencode({"from_date": _iso_dias_atras(desde_dias), "status": status,
                                "include": "recipients", "count": 100})
    envs = _req(f"/envelopes?{q}").get("envelopes", [])
    return {"ambiente": "DEMO" if _eh_demo() else "PRODUÇÃO", "total": len(envs),
            "envelopes": [_resumo_envelope(e) for e in envs]}


@srv.ferramenta(
    "docusign_envelope",
    "Um envelope completo, com signatários, datas e expiração.",
    {"envelopeId": {"type": "string"}}, ["envelopeId"])
def docusign_envelope(envelopeId):
    return _resumo_envelope(_req(f"/envelopes/{envelopeId}?include=recipients"))


@srv.ferramenta(
    "docusign_waivers_de",
    "Tudo que existe no DocuSign para um e-mail: waiver válida (completed há "
    "menos de 1 ano), envelopes em aberto (sent/delivered) e histórico. É a "
    "consulta das travas 1 e 2 — a ferramenta de envio refaz sozinha.",
    {"email": {"type": "string"}}, ["email"])
def docusign_waivers_de(email):
    envs = _envelopes_de(email, VALIDADE_WAIVER_DIAS + 30)
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=VALIDADE_WAIVER_DIAS)
    validas, abertos, outros = [], [], []
    for e in envs:
        r = _resumo_envelope(e)
        if e.get("status") == "completed" and e.get("completedDateTime"):
            quando = dt.datetime.fromisoformat(e["completedDateTime"].replace("Z", "+00:00"))
            (validas if quando >= limite else outros).append(r)
        elif e.get("status") in ABERTOS:
            abertos.append(r)
        else:
            outros.append(r)
    return {"email": email, "waiver_valida": validas or None, "em_aberto": abertos or None,
            "historico": outros or None,
            "conclusao": ("NÃO ENVIAR: já tem waiver válida" if validas else
                          "NÃO ENVIAR: já tem envelope em aberto" if abertos else
                          "sem waiver válida nem envelope em aberto")}


# ----------------------------------------------------------- ESCRITA
@srv.ferramenta(
    "docusign_enviar_waiver",
    "Cria E ENVIA a waiver a partir do template (não tem volta). As 4 travas "
    "rodam aqui dentro: waiver válida → recusa; envelope em aberto → recusa; "
    "idade_confirmada=false → recusa; nome_email_conferidos=false → recusa. "
    "Recusado em ambiente DEMO. Com APLICAR=0 é simulação. Só os 2 templates "
    "reais, pelo ID.",
    {"templateId": {"type": "string"},
     "nome": {"type": "string"}, "email": {"type": "string"},
     "idade_confirmada": {"type": "boolean",
                          "description": "true só se a idade do piloto foi confirmada em fonte (Asana/QuickBooks)"},
     "nome_email_conferidos": {"type": "boolean",
                               "description": "true só se nome e e-mail foram conferidos contra Asana/QuickBooks"},
     "servico": {"type": "string", "description": "referência do serviço, para o registro"}},
    ["templateId", "nome", "email", "idade_confirmada", "nome_email_conferidos"])
def docusign_enviar_waiver(templateId, nome, email, idade_confirmada, nome_email_conferidos, servico=""):
    if _eh_demo():
        raise ErroFerramenta("RECUSADO: ambiente DEMO. Waiver de demo não tem validade jurídica. "
                             "Só se envia de na4.docusign.net, depois do go-live.")
    if templateId not in TEMPLATES:
        raise ErroFerramenta(f"RECUSADO: template {templateId} não é um dos dois reais. "
                             f"Válidos: {list(TEMPLATES)}")
    if not idade_confirmada:
        raise ErroFerramenta("RECUSADO (trava 3): idade não confirmada. Parental para adulto é erro "
                             "visível. ESCALAR: 'fulano precisa de waiver X, e-mail Y, serviço Z — confirma?'")
    if not nome_email_conferidos:
        raise ErroFerramenta("RECUSADO (trava 4): nome e e-mail não conferidos contra Asana/QuickBooks. "
                             "Contato salvo errado propaga o erro para sempre.")
    email = email.strip()
    if "@" not in email or not nome.strip():
        raise ErroFerramenta("RECUSADO: nome ou e-mail inválido.")
    situacao = docusign_waivers_de(email)
    if situacao["waiver_valida"]:
        raise ErroFerramenta("RECUSADO (trava 1): já existe waiver válida (< 1 ano) para "
                             f"{email}: {situacao['waiver_valida'][0]['envelopeId']}. "
                             "Marcar a subtarefa e seguir.")
    if situacao["em_aberto"]:
        raise ErroFerramenta("RECUSADO (trava 2): já existe envelope em aberto para "
                             f"{email}: {situacao['em_aberto'][0]['envelopeId']}. Não mandar duas vezes.")
    descricao = (f"enviar '{TEMPLATES[templateId]}' para {nome.strip()} <{email}>"
                 + (f" · serviço: {servico}" if servico else ""))
    if not _aplicar():
        log("SIMULAÇÃO:", descricao)
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": descricao,
                "travas": "as 4 passaram", "aviso": "Nada foi enviado."}
    r = _req("/envelopes", "POST", {
        "templateId": templateId, "status": "sent",
        "templateRoles": [{"roleName": ROLE_NAME, "name": nome.strip(), "email": email}],
    })
    log("ENVIADO:", descricao, "->", r.get("envelopeId"))
    return {"aplicado": True, "envelopeId": r.get("envelopeId"), "status": r.get("status"),
            "template": TEMPLATES[templateId], "signatario": {"nome": nome.strip(), "email": email},
            "registrar": "comentário na tarefa do Asana com template, signatário, e-mail e envelopeId; linha no diário"}


if __name__ == "__main__":
    _carregar_env()
    log("ambiente:", "DEMO" if _eh_demo() else "PRODUÇÃO", "| base:", _base(),
        "| APLICAR =", os.environ.get("APLICAR", "0"))
    srv.rodar()


# ----------------------------------------------- ESCRITA liberada pelo dono em 17/09
# "Reenviar/corrigir e-mail, anular, lixeira, ver/renomear/trocar PDF de modelo: isso a IA
# pode fazer." Cada uma passa pelo gate do painel (aprovação ou confirmação) e por APLICAR.
def _pdf_local(caminho):
    """Lê um PDF do workspace do agente ou de ~/.urace — nunca de outro lugar."""
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    host = os.path.expanduser(f"~/.openclaw/workspace/{agente}")
    if caminho.startswith("/workspace/"):
        caminho = os.path.join(host, caminho[len("/workspace/"):])
    caminho = os.path.expanduser(caminho)
    real = os.path.realpath(caminho)
    if not any(real.startswith(os.path.realpath(r) + os.sep) for r in (host, os.path.expanduser("~/.urace"))):
        raise ErroFerramenta(f"RECUSADO: só leio PDF do workspace ou de ~/.urace, não {caminho}")
    with open(real, "rb") as f:
        dados = f.read()
    if not dados.startswith(b"%PDF"):
        raise ErroFerramenta("o arquivo não é um PDF")
    return os.path.basename(real), dados


@srv.ferramenta(
    "docusign_reenviar_waiver",
    "Reenvia a notificação de um envelope em aberto (sent/delivered) ao signatário; com `novo_email`, "
    "corrige o e-mail antes (caso do e-mail devolvido). Exige aprovação humana no painel. "
    "Com APLICAR=0 é simulação.",
    {"envelopeId": {"type": "string"}, "novo_email": {"type": "string"}, "novo_nome": {"type": "string"}}, ["envelopeId"])
def docusign_reenviar_waiver(envelopeId, novo_email=None, novo_nome=None):
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"reenviar {envelopeId}" + (f" para {novo_email}" if novo_email else "")}
    return reenviar_humano(envelopeId, novo_email, novo_nome)


@srv.ferramenta(
    "docusign_send_reminder",
    "Lembra o signatário de uma waiver EM ABERTO. Regras em código (dono, 22/09): só para "
    "quem tem serviço MARCADO no futuro, só 3 dias antes ou 1 dia antes, e no máximo 2 por "
    "envelope — a terceira chamada é recusada. Sem o banco do painel, recusa. "
    "Com APLICAR=0 é simulação.",
    {"envelopeId": {"type": "string"}}, ["envelopeId"])
def docusign_send_reminder(envelopeId):
    e = _req(f"/envelopes/{envelopeId}?include=recipients")
    if e.get("status") not in ABERTOS:
        raise ErroFerramenta(f"RECUSADO: só waiver em aberto recebe lembrete (está {e.get('status')}).")
    signers = (e.get("recipients") or {}).get("signers", [])
    if not signers:
        raise ErroFerramenta("envelope sem signatário")
    alvo = signers[0]
    con = _painel()
    if con is None:
        raise ErroFerramenta("RECUSADO: sem o banco do painel não dá para saber se existe serviço "
                             "marcado — e sem saber não se manda e-mail para cliente.")
    try:
        d = avaliar_lembrete(con, envelopeId, alvo.get("email"))
        if not d["pode"]:
            raise ErroFerramenta(f"RECUSADO: {d['motivo']}.")
        if not _aplicar():
            return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)",
                    "teria_feito": f"lembrar {alvo.get('email')} do envelope {envelopeId} "
                                   f"({d['dias']} dia(s) antes do serviço)"}
        # O DocuSign manda o lembrete pelo mesmo caminho do reenvio: a notificação
        # volta para o signatário, com o link original.
        _req(f"/envelopes/{envelopeId}/recipients?resend_envelope=true", "PUT",
             {"signers": [{"recipientId": alvo["recipientId"]}]})
        registrar_lembrete(con, envelopeId, alvo.get("email"), d["dias"], d["servico_em"])
        return {"aplicado": True, "envelopeId": envelopeId, "email": alvo.get("email"),
                "dias_antes": d["dias"], "servico_em": d["servico_em"],
                "lembretes_usados": con.execute(
                    "SELECT COUNT(*) FROM waiver_reminders WHERE envelope_id=?",
                    (str(envelopeId),)).fetchone()[0], "limite": MAX_LEMBRETES}
    finally:
        con.close()


@srv.ferramenta(
    "docusign_anular_envelope",
    "Anula (void) um envelope EM ABERTO, com motivo. Envelope assinado nunca é anulado (registro legal). "
    "Exige aprovação humana no painel. Com APLICAR=0 é simulação.",
    {"envelopeId": {"type": "string"}, "motivo": {"type": "string"}}, ["envelopeId", "motivo"])
def docusign_anular_envelope(envelopeId, motivo):
    if not (motivo or "").strip():
        raise ErroFerramenta("motivo é obrigatório")
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"anular {envelopeId}: {motivo}"}
    return anular_humano(envelopeId, motivo)


@srv.ferramenta(
    "docusign_renomear_modelo",
    "Renomeia um modelo (template) da conta. Só o nome. Pede confirmação no painel. Com APLICAR=0 é simulação.",
    {"templateId": {"type": "string"}, "nome": {"type": "string"}}, ["templateId", "nome"])
def docusign_renomear_modelo(templateId, nome):
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"renomear modelo {templateId} para '{nome}'"}
    return renomear_modelo_humano(templateId, nome)


@srv.ferramenta(
    "docusign_substituir_documento_modelo",
    "Troca o PDF de um documento de um modelo, mantendo o documentId (os campos de assinatura continuam nele). "
    "Guarda o PDF antigo em ~/.urace/docusign-templates antes. `caminho` é um PDF do workspace (/workspace/…) "
    "ou de ~/.urace. Exige aprovação humana no painel. Com APLICAR=0 é simulação.",
    {"templateId": {"type": "string"}, "documentId": {"type": "string"}, "caminho": {"type": "string"}}, ["templateId", "documentId", "caminho"])
def docusign_substituir_documento_modelo(templateId, documentId, caminho):
    nome, pdf = _pdf_local(caminho)
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"trocar o documento {documentId} do modelo {templateId} por {nome} ({len(pdf)} bytes)"}
    pasta = os.path.expanduser("~/.urace/docusign-templates")
    backup = None
    if any(str(d.get("documentId")) == str(documentId) for d in modelo_humano(templateId).get("documentos") or []):
        antigo = baixar_documento_do_modelo_humano(templateId, documentId)
        os.makedirs(pasta, mode=0o700, exist_ok=True)
        backup = os.path.join(pasta, f"{templateId}-{documentId}-{dt.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.pdf")
        with open(backup, "wb") as f:
            f.write(antigo)
        os.chmod(backup, 0o600)
    r = substituir_documento_do_modelo_humano(templateId, documentId, nome, pdf)
    return {**r, "backup": backup}
