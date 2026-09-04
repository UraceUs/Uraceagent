#!/usr/bin/env python3
"""Servidor MCP do Google (Gmail, Calendar, Sheets) para o Administrative AI.

Roda no HOST. Autentica com refresh token gravado por adminai/google_auth.py
(um arquivo por caixa: urace@ e support@). O agente, no container, recebe
só as ferramentas -- nem token, nem client secret chegam lá.

As regras do dono que viram código:

  - NÃO EXISTE ferramenta de enviar. Só rascunho. As exceções autorizadas
    (depósito, waiver) saem pelo QuickBooks e pelo DocuSign, não por aqui.
  - Arquivar (tirar da INBOX) só é permitido junto com o marcador `wNews`.
    "Propaganda sai sozinha; todo o resto fica na inbox."
  - Não existe apagar, nem spam, nem criar marcador. A taxonomia é do
    dono; a IA usa a que existe (brain/40_SISTEMAS/Taxonomia do Gmail.md).
  - APLICAR=0 (padrão) transforma toda escrita em simulação.

Anexo baixado vai para o workspace do agente, em anexos/, e a ferramenta
devolve o caminho como o container enxerga (/workspace/anexos/...) -- é o
caminho que asana_anexar_arquivo aceita. Fecha o ciclo da waiver assinada.
"""
import base64
import datetime as dt
import email
import email.message
import email.utils
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL = "https://www.googleapis.com/calendar/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
MARCADOR_ARQUIVAVEL = "wNews"            # o único que sai da inbox sozinho
PROIBIDOS = {"TRASH", "SPAM"}            # nunca, por nenhuma ferramenta


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


def _aplicar():
    return os.environ.get("APLICAR", "0") == "1"


def _workspace_host():
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    return os.path.expanduser(f"~/.openclaw/workspace/{agente}")


# ---------------------------------------------------------------- contas
_contas = {}          # nome -> dict(token file content)
_tokens = {}          # nome -> {"valor", "expira"}
_labels = {}          # nome -> {label_name: id}


def _carregar_contas():
    cands = {
        "urace": os.environ.get("GOOGLE_TOKEN_JSON", os.path.expanduser("~/.urace/google-token.json")),
        "support": os.environ.get("GOOGLE_TOKEN_JSON_SUPPORT",
                                  os.path.expanduser("~/.urace/google-token-support.json")),
    }
    for nome, p in cands.items():
        p = os.path.expanduser(p)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                _contas[nome] = json.load(f)
    if not _contas:
        sys.exit("ERRO: nenhum token do Google. Rode adminai/google_auth.py primeiro.")


def _conta(nome):
    if nome not in _contas:
        raise ErroFerramenta(f"conta '{nome}' não configurada. Disponíveis: {list(_contas)}. "
                             "Para support@, rode google_auth.py --conta support no VPS.")
    return _contas[nome]


def _access_token(nome):
    t = _tokens.get(nome)
    if t and time.time() < t["expira"] - 60:
        return t["valor"]
    c = _conta(nome)
    dados = urllib.parse.urlencode({
        "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=dados, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        texto = e.read().decode(errors="replace")[:300]
        if "invalid_grant" in texto:
            raise ErroFerramenta(f"refresh token da conta {nome} foi revogado ou expirou. "
                                 "Refazer o consentimento: adminai/google_auth.py. ESCALAR.")
        raise ErroFerramenta(f"token do Google recusado ({nome}, HTTP {e.code}): {texto}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o Google: {e.reason}")
    _tokens[nome] = {"valor": resp["access_token"], "expira": time.time() + int(resp.get("expires_in", 3600))}
    return _tokens[nome]["valor"]


def _req(nome, url, metodo="GET", corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {_access_token(nome)}")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
            return json.loads(bruto) if bruto else {}
    except urllib.error.HTTPError as e:
        raise ErroFerramenta(f"HTTP {e.code} em {metodo} {url.split('?')[0]}: "
                             f"{e.read()[:300].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o Google: {e.reason}")


# --------------------------------------------------------------- helpers
def _mapa_labels(nome):
    if nome not in _labels:
        r = _req(nome, f"{GMAIL}/labels")
        _labels[nome] = {l["name"]: l["id"] for l in r.get("labels", [])}
    return _labels[nome]


def _label_id(nome, label):
    m = _mapa_labels(nome)
    if label in m:
        return m[label]
    # tolerância a maiúsculas/minúsculas, nunca a nome novo
    for n, i in m.items():
        if n.lower() == label.lower():
            return i
    raise ErroFerramenta(f"marcador '{label}' não existe na conta {nome}. A IA não cria marcador — "
                         "use um da taxonomia (brain/40_SISTEMAS/Taxonomia do Gmail.md).")


def _cabecalho(msg, nome):
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == nome.lower():
            return h.get("value")
    return None


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _corpo(payload):
    """Prefere text/plain; cai para HTML sem tags. Lista anexos."""
    textos, htmls, anexos = [], [], []

    def walk(p):
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        if p.get("filename"):
            anexos.append({"nome": p["filename"], "mime": mime, "attachment_id": body.get("attachmentId"),
                           "bytes": body.get("size")})
        if body.get("data"):
            t = _b64d(body["data"]).decode("utf-8", errors="replace")
            (textos if mime == "text/plain" else htmls if mime == "text/html" else []).append(t)
        for sub in p.get("parts", []) or []:
            walk(sub)
    walk(payload)
    texto = "\n".join(textos) if textos else re.sub(r"<[^>]+>", " ", "\n".join(htmls))
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto).strip()
    return texto, anexos


def _resumo_msg(m, com_corpo=False, limite=4000):
    r = {"message_id": m["id"], "de": _cabecalho(m, "From"), "para": _cabecalho(m, "To"),
         "data": _cabecalho(m, "Date"), "assunto": _cabecalho(m, "Subject"),
         "marcadores": m.get("labelIds"), "snippet": m.get("snippet")}
    if com_corpo:
        texto, anexos = _corpo(m.get("payload", {}))
        r["corpo"] = texto[:limite] + ("…[cortado]" if len(texto) > limite else "")
        r["anexos"] = anexos or None
    return r


def _simulado(descricao):
    log("SIMULAÇÃO:", descricao)
    return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": descricao,
            "aviso": "Nada foi alterado. Registre no relatório como pendente de liberação."}


srv = Servidor("urace-google", "0.1")
CONTA = {"type": "string", "enum": ["urace", "support"], "description": "qual caixa: urace ou support"}


# ----------------------------------------------------------- LEITURA
@srv.ferramenta(
    "gmail_contas",
    "Quais caixas estão configuradas e se o token autentica. CHAME PRIMEIRO. "
    "Devolve o e-mail real de cada conta, como o Google o vê.")
def gmail_contas():
    saida = {}
    for nome in _contas:
        try:
            p = _req(nome, f"{GMAIL}/profile")
            saida[nome] = {"email": p.get("emailAddress"), "threads": p.get("threadsTotal"), "ok": True}
        except ErroFerramenta as e:
            saida[nome] = {"ok": False, "erro": str(e)}
    return {"contas": saida, "APLICAR": os.environ.get("APLICAR", "0"), "envio": "não existe ferramenta de envio"}


@srv.ferramenta(
    "gmail_marcadores",
    "Lista os marcadores (labels) da caixa, com contagem de não lidos. É a taxonomia do dono.",
    {"conta": CONTA}, ["conta"])
def gmail_marcadores(conta):
    r = _req(conta, f"{GMAIL}/labels")
    return sorted([{"nome": l["name"], "id": l["id"], "tipo": l.get("type")} for l in r.get("labels", [])],
                  key=lambda x: x["nome"].lower())


@srv.ferramenta(
    "gmail_buscar",
    "Busca threads. `consulta` usa a sintaxe do Gmail (ex.: 'newer_than:1d', "
    "'from:docusign.net', 'subject:invoice'). Por padrão só INBOX. Devolve "
    "remetente, assunto, data, marcadores e snippet da última mensagem.",
    {"conta": CONTA, "consulta": {"type": "string"},
     "so_inbox": {"type": "boolean", "default": True},
     "maximo": {"type": "integer", "default": 20}},
    ["conta", "consulta"])
def gmail_buscar(conta, consulta, so_inbox=True, maximo=20):
    params = {"q": consulta, "maxResults": max(1, min(int(maximo), 100))}
    if so_inbox:
        params["labelIds"] = "INBOX"
    r = _req(conta, f"{GMAIL}/threads?{urllib.parse.urlencode(params)}")
    ids = {}
    saida = []
    for t in r.get("threads", []):
        th = _req(conta, f"{GMAIL}/threads/{t['id']}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        msgs = th.get("messages", [])
        if not msgs:
            continue
        ult = msgs[-1]
        nomes = {}
        for m in msgs:
            for lid in m.get("labelIds", []):
                nomes[lid] = True
        inv = {v: k for k, v in _mapa_labels(conta).items()}
        saida.append({"thread_id": t["id"], "mensagens": len(msgs),
                      "de": _cabecalho(ult, "From"), "assunto": _cabecalho(ult, "Subject"),
                      "data": _cabecalho(ult, "Date"),
                      "marcadores": sorted(inv.get(l, l) for l in nomes),
                      "snippet": ult.get("snippet")})
    return {"conta": conta, "total": len(saida), "threads": saida,
            "proxima_pagina": r.get("nextPageToken")}


@srv.ferramenta(
    "gmail_thread",
    "Lê uma thread inteira: cada mensagem com remetente, data, corpo (texto) e "
    "anexos (nome + attachment_id, para gmail_baixar_anexo).",
    {"conta": CONTA, "thread_id": {"type": "string"}}, ["conta", "thread_id"])
def gmail_thread(conta, thread_id):
    th = _req(conta, f"{GMAIL}/threads/{thread_id}?format=full")
    inv = {v: k for k, v in _mapa_labels(conta).items()}
    msgs = []
    for m in th.get("messages", []):
        r = _resumo_msg(m, com_corpo=True)
        r["marcadores"] = [inv.get(l, l) for l in (m.get("labelIds") or [])]
        msgs.append(r)
    return {"conta": conta, "thread_id": thread_id, "mensagens": msgs}


@srv.ferramenta(
    "gmail_baixar_anexo",
    "Baixa um anexo para o workspace do agente (anexos/). Devolve o caminho "
    "como o container enxerga (/workspace/anexos/...), pronto para "
    "asana_anexar_arquivo. Uso principal: a waiver assinada que chega em support@.",
    {"conta": CONTA, "message_id": {"type": "string"}, "attachment_id": {"type": "string"},
     "nome": {"type": "string", "description": "nome do arquivo a gravar, ex.: waiver-fulano.pdf"}},
    ["conta", "message_id", "attachment_id", "nome"])
def gmail_baixar_anexo(conta, message_id, attachment_id, nome):
    nome = os.path.basename(nome).replace("..", "_")
    if not nome:
        raise ErroFerramenta("nome inválido")
    r = _req(conta, f"{GMAIL}/messages/{message_id}/attachments/{attachment_id}")
    dados = _b64d(r["data"])
    pasta = os.path.join(_workspace_host(), "anexos")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, nome)
    with open(destino, "wb") as f:
        f.write(dados)
    return {"gravado_em_host": destino, "caminho_no_container": f"/workspace/anexos/{nome}",
            "bytes": len(dados)}


@srv.ferramenta(
    "calendar_eventos",
    "Eventos do calendário principal da conta nos próximos N dias (leitura).",
    {"conta": CONTA, "dias": {"type": "integer", "default": 14}}, ["conta"])
def calendar_eventos(conta, dias=14):
    agora = dt.datetime.now(dt.timezone.utc)
    params = {"timeMin": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "timeMax": (agora + dt.timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "singleEvents": "true", "orderBy": "startTime", "maxResults": 100}
    r = _req(conta, f"{CAL}/calendars/primary/events?{urllib.parse.urlencode(params)}")
    return [{"id": e.get("id"), "titulo": e.get("summary"),
             "inicio": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
             "fim": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"),
             "local": e.get("location"), "link": e.get("htmlLink")} for e in r.get("items", [])]


@srv.ferramenta(
    "sheets_ler",
    "Lê um intervalo de uma planilha do Google (ex.: a Rate Card — ID em "
    "brain/40_SISTEMAS/Rate Card.md). Devolve as linhas como listas.",
    {"conta": CONTA, "planilha_id": {"type": "string"},
     "intervalo": {"type": "string", "description": "ex.: 'Sheet1!A1:F60'"}},
    ["conta", "planilha_id", "intervalo"])
def sheets_ler(conta, planilha_id, intervalo):
    r = _req(conta, f"{SHEETS}/{planilha_id}/values/{urllib.parse.quote(intervalo, safe='!:')}")
    return {"intervalo": r.get("range"), "linhas": r.get("values", [])}


# ----------------------------------------------------------- ESCRITA
@srv.ferramenta(
    "gmail_rotular",
    "Aplica e/ou remove marcadores numa thread. Regras em código: nunca TRASH/SPAM; "
    "remover INBOX (arquivar) só se a thread receber ou já tiver 'wNews' — "
    "propaganda é o único tipo que sai da inbox sozinho. Com APLICAR=0 é simulação.",
    {"conta": CONTA, "thread_id": {"type": "string"},
     "adicionar": {"type": "array", "items": {"type": "string"}, "default": []},
     "remover": {"type": "array", "items": {"type": "string"}, "default": []}},
    ["conta", "thread_id"])
def gmail_rotular(conta, thread_id, adicionar=None, remover=None):
    adicionar, remover = list(adicionar or []), list(remover or [])
    if not adicionar and not remover:
        raise ErroFerramenta("nada a fazer: adicionar e remover vazios")
    for l in adicionar + remover:
        if l.upper() in PROIBIDOS:
            raise ErroFerramenta(f"RECUSADO: '{l}' nunca. A IA não apaga nem marca spam.")
    if any(l.upper() == "INBOX" for l in remover):
        th = _req(conta, f"{GMAIL}/threads/{thread_id}?format=minimal")
        atuais = set()
        for m in th.get("messages", []):
            atuais.update(m.get("labelIds") or [])
        vai_ter_wnews = (_label_id(conta, MARCADOR_ARQUIVAVEL) in atuais) or \
                        any(l.lower() == MARCADOR_ARQUIVAVEL.lower() for l in adicionar)
        if not vai_ter_wnews:
            raise ErroFerramenta(f"RECUSADO: arquivar (remover INBOX) só com '{MARCADOR_ARQUIVAVEL}'. "
                                 "Todo o resto fica na inbox — regra do dono.")
    add_ids = [_label_id(conta, l) if l.upper() not in ("INBOX", "UNREAD", "STARRED") else l.upper() for l in adicionar]
    rem_ids = [_label_id(conta, l) if l.upper() not in ("INBOX", "UNREAD", "STARRED") else l.upper() for l in remover]
    desc = f"thread {thread_id} ({conta}): +{adicionar} -{remover}"
    if not _aplicar():
        return _simulado(desc)
    _req(conta, f"{GMAIL}/threads/{thread_id}/modify", "POST",
         {"addLabelIds": add_ids, "removeLabelIds": rem_ids})
    return {"aplicado": True, "thread_id": thread_id, "adicionado": adicionar, "removido": remover}


@srv.ferramenta(
    "gmail_rascunho",
    "Cria um RASCUNHO (nunca envia). Para responder numa thread, passe thread_id e "
    "responder_message_id — o rascunho entra na conversa com In-Reply-To. Com "
    "APLICAR=0 é simulação. Quem envia é humano, no Gmail.",
    {"conta": CONTA, "para": {"type": "string"}, "assunto": {"type": "string"},
     "corpo": {"type": "string"},
     "thread_id": {"type": "string"}, "responder_message_id": {"type": "string"}},
    ["conta", "para", "assunto", "corpo"])
def gmail_rascunho(conta, para, assunto, corpo, thread_id=None, responder_message_id=None):
    if "@" not in para:
        raise ErroFerramenta("destinatário inválido")
    msg = email.message.EmailMessage()
    msg["To"] = para
    msg["Subject"] = assunto
    msg["From"] = _conta(conta).get("email", "")
    if responder_message_id:
        orig = _req(conta, f"{GMAIL}/messages/{responder_message_id}?format=metadata&metadataHeaders=Message-ID&metadataHeaders=References")
        mid = _cabecalho(orig, "Message-ID")
        if mid:
            msg["In-Reply-To"] = mid
            refs = _cabecalho(orig, "References")
            msg["References"] = f"{refs} {mid}".strip() if refs else mid
    msg.set_content(corpo)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    desc = f"rascunho ({conta}) para {para}: '{assunto}'" + (f" na thread {thread_id}" if thread_id else "")
    if not _aplicar():
        return _simulado(desc)
    corpo_api = {"message": {"raw": raw}}
    if thread_id:
        corpo_api["message"]["threadId"] = thread_id
    r = _req(conta, f"{GMAIL}/drafts", "POST", corpo_api)
    return {"aplicado": True, "draft_id": r.get("id"), "para": para, "assunto": assunto,
            "aviso": "É rascunho. Ninguém recebeu nada. Quem envia é humano."}


if __name__ == "__main__":
    _carregar_env()
    _carregar_contas()
    log("contas:", list(_contas), "| APLICAR =", os.environ.get("APLICAR", "0"))
    srv.rodar()
