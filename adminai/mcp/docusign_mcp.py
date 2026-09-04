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
  - Não existe void, não existe editar template, não existe
    `sendReminder` (U-01, não decidido). Se precisar, é humano.
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
