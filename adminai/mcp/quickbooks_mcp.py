#!/usr/bin/env python3
"""Servidor MCP próprio do QuickBooks Online (URACE US INC).

Regras do dono, em código (brain/40_SISTEMAS/Conector do QuickBooks.md e
brain/10_PROCESSOS/Invoice e estimate no QuickBooks.md):
  - cliente do QBO é o RESPONSÁVEL, não o piloto
  - preço sai da Rate Card, não do catálogo
  - `amount` é UNITÁRIO; "x 2 dias" é quantity=2
  - item novo: sem dois-pontos no nome, taxable=false, tipo SERVICE
  - deep link SEMPRE por txnId (há doc_number duplicado na conta)
  - criar pode; ENVIAR só com aprovação humana (Command Center) e APLICAR=1
  - nunca apaga nada

Credenciais: QBO_CLIENT_ID / QBO_CLIENT_SECRET / QBO_REALM_ID no
~/.urace/adminai.env; o token (access + refresh) em ~/.urace/qbo-token.json,
gravado pelo consentimento feito no Command Center (/ops/api/qbo/connect).
⚠️ O refresh token ROTACIONA a cada uso e vale 100 dias: todo refresh é
gravado de volta no arquivo. Sem uso por 100 dias, refazer o consentimento.
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API = "https://quickbooks.api.intuit.com/v3/company"
MINOR = "70"
PROIBIDO_NO_NOME = ":"


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
    faltam = [k for k in ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID") if not os.environ.get(k)]
    if faltam:
        sys.exit(f"ERRO: faltam no env ({caminho}): {faltam}")
    if not os.path.isfile(_token_path()) and not os.environ.get("QBO_REFRESH_TOKEN"):
        sys.exit(f"ERRO: sem token do QuickBooks ({_token_path()}). Conecte pelo Command Center: Administração → QuickBooks → Conectar.")


def _token_path():
    return os.path.expanduser(os.environ.get("QBO_TOKEN_JSON", "~/.urace/qbo-token.json"))


def _aplicar():
    return os.environ.get("APLICAR", "0") == "1"


def _ler_token():
    p = _token_path()
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"refresh_token": os.environ.get("QBO_REFRESH_TOKEN"), "realm_id": os.environ.get("QBO_REALM_ID")}


def gravar_token(dados):
    """Grava access/refresh com permissão 600. Chamado aqui e pelo consentimento do Command Center."""
    p = _token_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _basic():
    return base64.b64encode(f"{os.environ['QBO_CLIENT_ID']}:{os.environ['QBO_CLIENT_SECRET']}".encode()).decode()


def trocar_codigo(code, redirect_uri):
    """Troca o code do consentimento por tokens (usado pelo Command Center)."""
    return _token_post({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})


def _token_post(campos):
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(campos).encode(), method="POST")
    req.add_header("Authorization", f"Basic {_basic()}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        texto = e.read().decode(errors="replace")[:300]
        if "invalid_grant" in texto:
            raise ErroFerramenta("refresh token do QuickBooks expirou ou foi revogado (vale 100 dias). "
                                 "Refazer o consentimento no Command Center. ESCALAR.")
        raise ErroFerramenta(f"token do QuickBooks recusado (HTTP {e.code}): {texto}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com a Intuit: {e.reason}")


_cache = {"access": None, "expira": 0}


def _access_token():
    import time
    if _cache["access"] and time.time() < _cache["expira"] - 60:
        return _cache["access"]
    t = _ler_token()
    if not t.get("refresh_token"):
        raise ErroFerramenta("sem refresh token do QuickBooks: conecte pelo Command Center.")
    resp = _token_post({"grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
    t.update(access_token=resp["access_token"], refresh_token=resp.get("refresh_token", t["refresh_token"]),
             expires_in=resp.get("expires_in"), obtido_em=dt.datetime.now(dt.timezone.utc).isoformat())
    gravar_token(t)                      # o refresh token rotacionou: persistir SEMPRE
    _cache.update(access=t["access_token"], expira=time.time() + int(resp.get("expires_in", 3600)))
    return t["access_token"]


def _realm():
    return _ler_token().get("realm_id") or os.environ["QBO_REALM_ID"]


def _req(caminho, metodo="GET", corpo=None, params=None):
    q = dict(params or {}); q["minorversion"] = MINOR
    url = f"{API}/{_realm()}{caminho}?{urllib.parse.urlencode(q)}"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {_access_token()}")
    req.add_header("Accept", "application/json")
    if dados is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
            return json.loads(bruto) if bruto else {}
    except urllib.error.HTTPError as e:
        # intuit_tid: o id que o suporte da Intuit pede para rastrear a chamada
        tid = e.headers.get("intuit_tid") if e.headers else None
        log("QBO erro", e.code, metodo, caminho, "intuit_tid=", tid)
        raise ErroFerramenta(f"HTTP {e.code} em {metodo} {caminho} (intuit_tid={tid}): {e.read()[:400].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o QuickBooks: {e.reason}")


def _query(sql):
    return _req("/query", params={"query": sql}).get("QueryResponse", {})


def _esc(s):
    return (s or "").replace("'", "\\'")


def deep_link(txn_id, tipo="invoice"):
    return f"https://qbo.intuit.com/app/login?pagereq={tipo}%3FtxnId%3D{txn_id}&deeplinkcompanyid={_realm()}"


# ------------------------------------------------------------- resumos
def _resumo_cliente(c):
    return {"id": c.get("Id"), "nome": c.get("DisplayName"), "empresa": c.get("CompanyName"),
            "email": ((c.get("PrimaryEmailAddr") or {}).get("Address") or "").lower() or None,
            "telefone": (c.get("PrimaryPhone") or {}).get("FreeFormNumber"),
            "saldo": c.get("Balance"), "ativo": c.get("Active")}


def _resumo_item(i):
    return {"id": i.get("Id"), "nome": i.get("Name"), "nome_completo": i.get("FullyQualifiedName"),
            "tipo": i.get("Type"), "preco": i.get("UnitPrice"), "ativo": i.get("Active"), "taxable": i.get("Taxable")}


def _status_invoice(inv, hoje):
    saldo = float(inv.get("Balance") or 0)
    total = float(inv.get("TotalAmt") or 0)
    if saldo <= 0 and total > 0:
        return "paid"
    if inv.get("DueDate") and inv["DueDate"] < hoje and saldo > 0:
        return "overdue"
    return "sent" if (inv.get("EmailStatus") == "EmailSent") else "open"


def _resumo_invoice(inv):
    hoje = dt.date.today().isoformat()
    cr = inv.get("CustomerRef") or {}
    linhas = [{"item": ((l.get("SalesItemLineDetail") or {}).get("ItemRef") or {}).get("name"),
               "qtd": (l.get("SalesItemLineDetail") or {}).get("Qty"), "unitario": (l.get("SalesItemLineDetail") or {}).get("UnitPrice"),
               "total": l.get("Amount"), "descricao": l.get("Description")}
              for l in inv.get("Line", []) if l.get("DetailType") == "SalesItemLineDetail"]
    return {"id": inv.get("Id"), "numero": inv.get("DocNumber"), "cliente_id": cr.get("value"), "cliente": cr.get("name"),
            "email": (inv.get("BillEmail") or {}).get("Address"), "emitida_em": inv.get("TxnDate"), "vence_em": inv.get("DueDate"),
            "total": inv.get("TotalAmt"), "saldo": inv.get("Balance"), "status": _status_invoice(inv, hoje),
            "email_status": inv.get("EmailStatus"), "memo": (inv.get("CustomerMemo") or {}).get("value"),
            "linhas": linhas, "link": deep_link(inv.get("Id")),
            "aviso": "saldo em aberto não é inadimplência: existe parcelamento (ver cérebro)" if float(inv.get("Balance") or 0) > 0 else None}


srv = Servidor("urace-quickbooks", "0.1")


# ------------------------------------------------------------- LEITURA
@srv.ferramenta("qbo_empresa", "Empresa conectada e estado do token. Sempre a primeira chamada.")
def qbo_empresa():
    r = _req(f"/companyinfo/{_realm()}").get("CompanyInfo", {})
    t = _ler_token()
    return {"empresa": r.get("CompanyName"), "realm_id": _realm(), "pais": r.get("Country"),
            "token_obtido_em": t.get("obtido_em"), "APLICAR": os.environ.get("APLICAR", "0"),
            "envio_permitido": _aplicar()}


@srv.ferramenta("qbo_clientes_buscar",
                "Clientes do QBO por nome ou e-mail (o cliente do QBO é o RESPONSÁVEL, não o piloto). "
                "Devolve id, nome, e-mail, saldo. Use antes de criar: nunca duplique.",
                {"texto": {"type": "string"}, "maximo": {"type": "integer", "default": 20}}, ["texto"])
def qbo_clientes_buscar(texto, maximo=20):
    t = _esc(texto.strip())
    if "@" in t:
        sql = f"select * from Customer where PrimaryEmailAddr = '{t}' maxresults {int(maximo)}"
    else:
        sql = f"select * from Customer where DisplayName like '%{t}%' maxresults {int(maximo)}"
    r = _query(sql)
    return [_resumo_cliente(c) for c in r.get("Customer", [])]


@srv.ferramenta("qbo_itens_buscar",
                "Itens do catálogo por nome (até 20 termos). O PREÇO válido é o da Rate Card, não o daqui. "
                "Devolve 'found' por termo; o que voltar found=false pode ser criado com qbo_criar_item.",
                {"termos": {"type": "array", "items": {"type": "string"}}}, ["termos"])
def qbo_itens_buscar(termos):
    saida = []
    for termo in list(termos)[:20]:
        r = _query(f"select * from Item where Name like '%{_esc(termo)}%' maxresults 10")
        itens = [_resumo_item(i) for i in r.get("Item", [])]
        saida.append({"termo": termo, "found": bool(itens), "itens": itens,
                      "requires_clarification": len(itens) > 1})
    return saida


@srv.ferramenta("qbo_invoices",
                "Invoices. status: open (saldo>0), overdue (vencida e saldo>0), paid, all. "
                "Opcional: cliente_id, desde_dias. Deep link por txnId.",
                {"status": {"type": "string", "default": "open"}, "cliente_id": {"type": "string"},
                 "desde_dias": {"type": "integer", "default": 365}, "maximo": {"type": "integer", "default": 100}})
def qbo_invoices(status="open", cliente_id=None, desde_dias=365, maximo=100):
    cond = [f"TxnDate >= '{(dt.date.today() - dt.timedelta(days=int(desde_dias))).isoformat()}'"]
    if cliente_id:
        cond.append(f"CustomerRef = '{_esc(cliente_id)}'")
    if status in ("open", "overdue"):
        cond.append("Balance > '0'")
    if status == "paid":
        cond.append("Balance = '0'")
    r = _query(f"select * from Invoice where {' and '.join(cond)} orderby TxnDate desc maxresults {int(maximo)}")
    out = [_resumo_invoice(i) for i in r.get("Invoice", [])]
    if status == "overdue":
        out = [i for i in out if i["status"] == "overdue"]
    return {"total": len(out), "invoices": out}


@srv.ferramenta("qbo_invoice", "Uma invoice completa pelo id (txnId).", {"id": {"type": "string"}}, ["id"])
def qbo_invoice(id):
    return _resumo_invoice(_req(f"/invoice/{id}").get("Invoice", {}))


@srv.ferramenta("qbo_estimates", "Estimates recentes (pré-corrida). Opcional cliente_id.",
                {"cliente_id": {"type": "string"}, "desde_dias": {"type": "integer", "default": 180}})
def qbo_estimates(cliente_id=None, desde_dias=180):
    cond = [f"TxnDate >= '{(dt.date.today() - dt.timedelta(days=int(desde_dias))).isoformat()}'"]
    if cliente_id:
        cond.append(f"CustomerRef = '{_esc(cliente_id)}'")
    r = _query(f"select * from Estimate where {' and '.join(cond)} orderby TxnDate desc maxresults 100")
    return [{"id": e.get("Id"), "numero": e.get("DocNumber"), "cliente": (e.get("CustomerRef") or {}).get("name"),
             "data": e.get("TxnDate"), "total": e.get("TotalAmt"), "status": e.get("TxnStatus"),
             "link": deep_link(e.get("Id"), "estimate")} for e in r.get("Estimate", [])]


@srv.ferramenta("qbo_contas_a_receber", "Relatório de contas a receber por faixa de atraso (AgedReceivables).")
def qbo_contas_a_receber():
    r = _req("/reports/AgedReceivables")
    linhas = []
    for row in (r.get("Rows") or {}).get("Row", []):
        cols = [c.get("value") for c in row.get("ColData", [])]
        if cols:
            linhas.append(cols)
    cab = [c.get("ColTitle") for c in (r.get("Columns") or {}).get("Column", [])]
    return {"colunas": cab, "linhas": linhas}


# ------------------------------------------------------------- ESCRITA
@srv.ferramenta("qbo_criar_cliente",
                "Cria cliente (o RESPONSÁVEL). Antes, busque: nunca duplique. Com APLICAR=0 é simulação.",
                {"nome": {"type": "string"}, "email": {"type": "string"}, "telefone": {"type": "string"}}, ["nome"])
def qbo_criar_cliente(nome, email=None, telefone=None):
    if qbo_clientes_buscar(nome, 5) or (email and qbo_clientes_buscar(email, 5)):
        raise ErroFerramenta("RECUSADO: já existe cliente com esse nome ou e-mail. Use o existente.")
    corpo = {"DisplayName": nome.strip()}
    if email:
        corpo["PrimaryEmailAddr"] = {"Address": email.strip()}
    if telefone:
        corpo["PrimaryPhone"] = {"FreeFormNumber": telefone.strip()}
    desc = f"criar cliente {nome} ({email or 'sem e-mail'})"
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": desc}
    return _resumo_cliente(_req("/customer", "POST", corpo).get("Customer", {}))


@srv.ferramenta("qbo_criar_item",
                "Cria item de catálogo. Sem dois-pontos no nome; taxable=false; tipo SERVICE (padrão da conta). "
                "Preço desconhecido entra 0 para o dono preencher. Com APLICAR=0 é simulação.",
                {"nome": {"type": "string"}, "preco": {"type": "number", "default": 0}, "descricao": {"type": "string"}}, ["nome"])
def qbo_criar_item(nome, preco=0, descricao=None):
    if PROIBIDO_NO_NOME in nome:
        raise ErroFerramenta("RECUSADO: o QBO não aceita ':' no nome do item. Crie com nome simples e avise que precisa ser movido para a categoria.")
    corpo = {"Name": nome.strip(), "Type": "Service", "Taxable": False, "UnitPrice": float(preco or 0),
             "IncomeAccountRef": _conta_receita()}
    if descricao:
        corpo["Description"] = descricao
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"criar item '{nome}' a {preco}"}
    return _resumo_item(_req("/item", "POST", corpo).get("Item", {}))


def _conta_receita():
    r = _query("select * from Account where AccountType = 'Income' and Active = true maxresults 5")
    contas = r.get("Account", [])
    if not contas:
        raise ErroFerramenta("nenhuma conta de receita ativa no plano de contas")
    pref = [c for c in contas if "service" in (c.get("Name") or "").lower() or "sales" in (c.get("Name") or "").lower()]
    c = (pref or contas)[0]
    return {"value": c["Id"], "name": c["Name"]}


def _linhas(linhas):
    out = []
    for l in linhas:
        if not l.get("item_id"):
            raise ErroFerramenta("cada linha precisa de item_id (busque com qbo_itens_buscar)")
        qtd = float(l.get("quantidade") or 1)
        unit = float(l["unitario"])                      # UNITÁRIO, nunca o total
        out.append({"DetailType": "SalesItemLineDetail", "Amount": round(qtd * unit, 2),
                    "Description": l.get("descricao"),
                    "SalesItemLineDetail": {"ItemRef": {"value": str(l["item_id"])}, "Qty": qtd, "UnitPrice": unit}})
    return out


LINHAS_SCHEMA = {"type": "array", "items": {"type": "object", "properties": {
    "item_id": {"type": "string"}, "quantidade": {"type": "number"}, "unitario": {"type": "number", "description": "valor UNITÁRIO pela Rate Card"},
    "descricao": {"type": "string"}}, "required": ["item_id", "unitario"]}}


@srv.ferramenta("qbo_criar_invoice",
                "Cria invoice para um cliente (id do QBO) com linhas [item_id, quantidade, unitario, descricao]. "
                "'unitario' é o valor unitário da Rate Card; 'x 2 dias' é quantidade 2. NÃO envia. Com APLICAR=0 é simulação.",
                {"cliente_id": {"type": "string"}, "linhas": LINHAS_SCHEMA, "vence_em": {"type": "string", "description": "AAAA-MM-DD"},
                 "memo": {"type": "string"}, "email": {"type": "string"}}, ["cliente_id", "linhas"])
def qbo_criar_invoice(cliente_id, linhas, vence_em=None, memo=None, email=None):
    corpo = {"CustomerRef": {"value": str(cliente_id)}, "Line": _linhas(linhas)}
    if vence_em:
        corpo["DueDate"] = vence_em
    if memo:
        corpo["CustomerMemo"] = {"value": memo[:1000]}
    if email:
        corpo["BillEmail"] = {"Address": email}
    total = sum(l["Amount"] for l in corpo["Line"])
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"criar invoice de {total:.2f} para cliente {cliente_id} ({len(linhas)} linha(s))"}
    return _resumo_invoice(_req("/invoice", "POST", corpo).get("Invoice", {}))


@srv.ferramenta("qbo_criar_estimate", "Cria estimate (pré-corrida) — mesmas linhas da invoice. Com APLICAR=0 é simulação.",
                {"cliente_id": {"type": "string"}, "linhas": LINHAS_SCHEMA, "memo": {"type": "string"}}, ["cliente_id", "linhas"])
def qbo_criar_estimate(cliente_id, linhas, memo=None):
    corpo = {"CustomerRef": {"value": str(cliente_id)}, "Line": _linhas(linhas)}
    if memo:
        corpo["CustomerMemo"] = {"value": memo[:1000]}
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"criar estimate para cliente {cliente_id}"}
    e = _req("/estimate", "POST", corpo).get("Estimate", {})
    return {"id": e.get("Id"), "numero": e.get("DocNumber"), "total": e.get("TotalAmt"), "link": deep_link(e.get("Id"), "estimate")}


@srv.ferramenta("qbo_enviar_invoice",
                "ENVIA a invoice por e-mail pelo QuickBooks. Exige aprovação humana no Command Center "
                "(D-2026-09-04) e APLICAR=1; fora disso é simulação.",
                {"id": {"type": "string"}, "email": {"type": "string", "description": "opcional; padrão é o BillEmail da invoice"}}, ["id"])
def qbo_enviar_invoice(id, email=None):
    inv = _req(f"/invoice/{id}").get("Invoice", {})
    if not inv:
        raise ErroFerramenta(f"invoice {id} não existe")
    destino = email or (inv.get("BillEmail") or {}).get("Address")
    if not destino:
        raise ErroFerramenta("invoice sem e-mail de cobrança: informe 'email'")
    desc = f"enviar invoice {inv.get('DocNumber')} ({inv.get('TotalAmt')}) para {destino}"
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": desc}
    r = _req(f"/invoice/{id}/send", "POST", params={"sendTo": destino}).get("Invoice", {})
    return {"aplicado": True, "id": id, "numero": r.get("DocNumber"), "enviado_para": destino, "email_status": r.get("EmailStatus"), "link": deep_link(id)}


@srv.ferramenta("qbo_criar_e_enviar_invoice",
                "Cria a invoice E envia por e-mail numa ação só. É a ação para propor quando o dono aprovar = enviar "
                "(mensalidade do dia 1, diária, lead and follow). Exige aprovação humana no painel; com APLICAR=0 é simulação.",
                {"cliente_id": {"type": "string"}, "linhas": LINHAS_SCHEMA, "vence_em": {"type": "string"},
                 "memo": {"type": "string"}, "email": {"type": "string"}}, ["cliente_id", "linhas"])
def qbo_criar_e_enviar_invoice(cliente_id, linhas, vence_em=None, memo=None, email=None):
    corpo = {"CustomerRef": {"value": str(cliente_id)}, "Line": _linhas(linhas)}
    if vence_em:
        corpo["DueDate"] = vence_em
    if memo:
        corpo["CustomerMemo"] = {"value": memo[:1000]}
    if email:
        corpo["BillEmail"] = {"Address": email}
    total = sum(l["Amount"] for l in corpo["Line"])
    if not _aplicar():
        return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": f"criar e enviar invoice de {total:.2f} para cliente {cliente_id}"}
    inv = _req("/invoice", "POST", corpo).get("Invoice", {})
    destino = email or (inv.get("BillEmail") or {}).get("Address")
    if not destino:
        c = _req(f"/customer/{cliente_id}").get("Customer", {})
        destino = (c.get("PrimaryEmailAddr") or {}).get("Address")
    if not destino:
        return {**_resumo_invoice(inv), "enviado": False, "aviso": "criada, mas sem e-mail de cobrança: envie pelo QuickBooks"}
    r = _req(f"/invoice/{inv['Id']}/send", "POST", params={"sendTo": destino}).get("Invoice", {})
    return {**_resumo_invoice(r or inv), "enviado": True, "enviado_para": destino}


if __name__ == "__main__":
    _carregar_env()
    log("realm:", os.environ.get("QBO_REALM_ID"), "| APLICAR =", os.environ.get("APLICAR", "0"))
    srv.rodar()
