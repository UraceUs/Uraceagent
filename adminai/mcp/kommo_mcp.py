#!/usr/bin/env python3
"""Servidor MCP próprio do Kommo (CRM comercial da URACE, urace.kommo.com).

Roda no HOST, sem dependência nenhuma (urllib). O token longo da
integração privada fica em ~/.urace/kommo.env (KOMMO_DOMAIN, KOMMO_TOKEN,
KOMMO_BOT_ID, KOMMO_HOOK_KEY, KOMMO_BOT_SECRET) — nunca no repositório,
nunca no container do agente.

Regras do dono, em código:
  - NADA é apagado: não existe apagar lead, contato, nota ou tag aqui.
  - LER é livre (funis, leads, contato, origem, tags, conversa).
  - ESCREVER (mover de etapa, marcar tag, anotar, responder) é PORTA
    HUMANA: não é ferramenta do agente, e só acontece com APLICAR=1,
    que o Command Center libera na ação do dono. O agente pode PROPOR
    pelo painel; quem confirma é gente.
  - O chat (Instagram/Facebook/WhatsApp) entra e sai pelo circuito do
    Salesbot provado em 24/08: o bot manda cada mensagem recebida ao hook
    do painel e fica esperando; a resposta humana volta pelo return_url
    e o bot a mostra no chat, com o texto NOSSO. Sem KOMMO_BOT_ID não dá
    para reabrir o chat horas depois — o painel recusa em vez de fingir.

Ver brain/40_SISTEMAS/Kommo - o que da para fazer pelo Command Center.md.
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

TIMEOUT = 40
LIMITE_PAGINA = 250                      # teto da API v4
# tipos de nota que são conversa de verdade (o resto é ruído de sistema)
NOTAS_DE_CONVERSA = {"amomail_message", "chat_message", "sms_in", "sms_out", "call_in", "call_out"}
NOTA_COMUM = "common"


# ------------------------------------------------------------- ambiente
def _carregar_env():
    """Lê ~/.urace/kommo.env (e o adminai.env como reserva). Sem token, NaoConectado."""
    for caminho in (os.environ.get("KOMMO_ENV", os.path.expanduser("~/.urace/kommo.env")),
                    os.environ.get("URACE_ENV", os.path.expanduser("~/.urace/adminai.env"))):
        if caminho and os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha or linha.startswith("#") or "=" not in linha:
                        continue
                    k, v = linha.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    faltam = [k for k in ("KOMMO_DOMAIN", "KOMMO_TOKEN") if not os.environ.get(k)]
    if faltam:
        sys.exit(f"ERRO: faltam no env (~/.urace/kommo.env): {faltam}")


def _base():
    d = os.environ["KOMMO_DOMAIN"].strip().replace("https://", "").replace("http://", "").strip("/")
    return f"https://{d}/api/v4"


_ctx = threading.local()      # o Command Center liga APLICAR só na thread da ação humana


def _aplicar():
    forcado = getattr(_ctx, "aplicar", None)
    if forcado is not None:
        return bool(forcado)
    return os.environ.get("APLICAR", "0") == "1"


def _simulado(desc):
    return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)", "teria_feito": desc}


def _req(caminho, metodo="GET", corpo=None, params=None):
    url = _base() + caminho
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={
        "Authorization": f"Bearer {os.environ['KOMMO_TOKEN']}",
        "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            bruto = r.read()
            if r.status == 204 or not bruto:
                return {}
            return json.loads(bruto)
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:400]
        if e.code in (401, 403):
            raise ErroFerramenta(f"Kommo recusou a credencial ({e.code}). O token longo pode ter expirado: "
                                 f"gere outro na integração privada e grave em ~/.urace/kommo.env. {detalhe}")
        if e.code == 404 and metodo == "GET":
            return {}
        raise ErroFerramenta(f"Kommo {metodo} {caminho} → {e.code}: {detalhe}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"Kommo fora de alcance: {e}")
    except (TimeoutError, OSError) as e:
        raise ErroFerramenta(f"Kommo não respondeu a tempo: {e}")


def _lista(caminho, chave, params=None, maximo=200):
    """Pagina /api/v4 até `maximo`. Devolve a lista de `_embedded[chave]`."""
    saida, pagina = [], 1
    limite = min(LIMITE_PAGINA, maximo)         # FIXO: page=2&limit=50 devolve 51-100, não 251-300
    while len(saida) < maximo:
        p = dict(params or {}, page=pagina, limit=limite)
        r = _req(caminho, params=p)
        itens = ((r or {}).get("_embedded") or {}).get(chave) or []
        saida.extend(itens)
        if len(itens) < limite or not r.get("_links", {}).get("next"):
            break
        pagina += 1
    return saida[:maximo]


def _quando(ts):
    """Carimbo do Kommo (epoch) → ISO UTC. None fica None."""
    if not ts:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- leitura
srv = Servidor("urace-kommo", "0.1")

_cache_funis = {"em": 0, "dados": None}


def _funis(forcar=False):
    if not forcar and _cache_funis["dados"] and time.time() - _cache_funis["em"] < 300:
        return _cache_funis["dados"]
    saida = []
    for p in _lista("/leads/pipelines", "pipelines", maximo=50):
        etapas = [{"id": str(s["id"]), "nome": s.get("name"), "ordem": s.get("sort"),
                   "cor": s.get("color"), "tipo": s.get("type")}
                  for s in ((p.get("_embedded") or {}).get("statuses") or [])]
        etapas.sort(key=lambda e: e["ordem"] or 0)
        saida.append({"id": str(p["id"]), "nome": p.get("name"), "principal": bool(p.get("is_main")),
                      "ordem": p.get("sort"), "etapas": etapas})
    _cache_funis.update(em=time.time(), dados=saida)
    return saida


def _nome_etapa(funil_id, etapa_id):
    for f in _funis():
        if f["id"] == str(funil_id):
            for e in f["etapas"]:
                if e["id"] == str(etapa_id):
                    return f["nome"], e["nome"], e["ordem"]
            return f["nome"], None, None
    return None, None, None


_contatos = {}


def _carregar_contatos(ids):
    """Contatos em lote (até 50 por chamada) — 250 leads viravam 250 chamadas e estouravam o tempo (10/09)."""
    faltam = [str(i) for i in ids if str(i) not in _contatos]
    for i in range(0, len(faltam), 50):
        lote = faltam[i:i + 50]
        params = {f"filter[id][{j}]": v for j, v in enumerate(lote)}
        params["limit"] = 50
        r = _req("/contacts", params=params) or {}
        for c in ((r.get("_embedded") or {}).get("contacts") or []):
            _contatos[str(c.get("id"))] = c
        for v in lote:
            _contatos.setdefault(v, None)


def _contato_do_lead(lead):
    """Primeiro contato embutido → nome, e-mail, telefone."""
    cs = ((lead.get("_embedded") or {}).get("contacts") or [])
    if not cs:
        return {}
    c = cs[0]
    if "custom_fields_values" not in c and c.get("id"):        # veio só o id: usa o lote (ou busca um)
        cid = str(c["id"])
        if cid not in _contatos:
            _carregar_contatos([cid])
        c = _contatos.get(cid) or c
    return _resumo_contato(c)


def _campos(entidade):
    """custom_fields_values → {nome do campo: valor}."""
    saida = {}
    for cf in (entidade.get("custom_fields_values") or []):
        vals = [v.get("value") for v in (cf.get("values") or []) if v.get("value") not in (None, "")]
        if vals:
            saida[cf.get("field_name") or cf.get("field_code") or str(cf.get("field_id"))] = vals[0] if len(vals) == 1 else vals
    return saida


def _primeiro(v):
    """Campo com vários valores vem como lista: fica o primeiro (texto)."""
    if isinstance(v, (list, tuple)):
        v = next((x for x in v if x not in (None, "")), None)
    return str(v).strip() if v not in (None, "") else None


def _resumo_contato(c):
    campos = _campos(c)
    email = _primeiro(next((v for k, v in campos.items() if "email" in (k or "").lower()), None))
    tel = _primeiro(next((v for k, v in campos.items() if any(x in (k or "").lower() for x in ("phone", "telefone", "whats"))), None))
    return {"id": str(c.get("id")) if c.get("id") else None, "nome": c.get("name"),
            "email": email, "telefone": tel, "campos": campos}


def _resumo_lead(lead, com_contato=True):
    funil, etapa, ordem = _nome_etapa(lead.get("pipeline_id"), lead.get("status_id"))
    campos = _campos(lead)
    origem = (campos.get("Origem") or campos.get("Source") or campos.get("origem")
              or (lead.get("_embedded") or {}).get("source", {}).get("name"))
    return {
        "id": str(lead.get("id")), "nome": lead.get("name"), "valor": lead.get("price"),
        "funil_id": str(lead.get("pipeline_id")) if lead.get("pipeline_id") else None, "funil": funil,
        "etapa_id": str(lead.get("status_id")) if lead.get("status_id") else None, "etapa": etapa, "ordem": ordem,
        "tags": [t.get("name") for t in ((lead.get("_embedded") or {}).get("tags") or []) if t.get("name")],
        "responsavel_id": str(lead.get("responsible_user_id")) if lead.get("responsible_user_id") else None,
        "origem": origem, "campos": campos,
        "criado_em": _quando(lead.get("created_at")), "atualizado_em": _quando(lead.get("updated_at")),
        "contato": _contato_do_lead(lead) if com_contato else {},
        "link": f"https://{os.environ['KOMMO_DOMAIN'].replace('https://', '').strip('/')}/leads/detail/{lead.get('id')}",
    }


@srv.ferramenta("kommo_conta", "Conta do Kommo ligada (nome, subdomínio, usuários). Só leitura.", {}, [])
def kommo_conta():
    r = _req("/account", params={"with": "users_groups"})
    return {"id": str(r.get("id")) if r.get("id") else None, "nome": r.get("name"),
            "subdominio": r.get("subdomain"), "moeda": r.get("currency"),
            "funis": len(_funis()), "responder_habilitado": bool(os.environ.get("KOMMO_BOT_ID"))}


@srv.ferramenta("kommo_funis", "Funis de venda com as etapas em ordem (id, nome, ordem). Só leitura.", {}, [])
def kommo_funis():
    return _funis(forcar=True)


@srv.ferramenta("kommo_leads",
                "Leads do CRM: filtra por funil, etapa ou texto (nome, e-mail, telefone). "
                "Devolve etapa, tags, origem e contato. Só leitura.",
                {"funil_id": {"type": "string"}, "etapa_id": {"type": "string"},
                 "texto": {"type": "string"}, "maximo": {"type": "integer", "default": 50}}, [])
def kommo_leads(funil_id=None, etapa_id=None, texto=None, maximo=50):
    params = {"with": "contacts", "order[updated_at]": "desc"}
    if funil_id:
        params["filter[pipeline_id]"] = int(funil_id)
    if etapa_id:
        params["filter[statuses][0][status_id]"] = int(etapa_id)
        if funil_id:
            params["filter[statuses][0][pipeline_id]"] = int(funil_id)
    if texto:
        params["query"] = texto
    _contatos.clear()                                 # cache vale por chamada
    leads = _lista("/leads", "leads", params, maximo=int(maximo or 50))
    ids = [str(c["id"]) for l in leads for c in (((l.get("_embedded") or {}).get("contacts") or [])[:1]) if c.get("id")]
    if ids:
        try:
            _carregar_contatos(ids)
        except ErroFerramenta:
            pass                                          # cai no um-a-um só para os que faltarem
    return [_resumo_lead(l) for l in leads]


@srv.ferramenta("kommo_lead", "Um lead pelo id, com contato, tags, origem e campos. Só leitura.",
                {"lead_id": {"type": "string"}}, ["lead_id"])
def kommo_lead(lead_id):
    r = _req(f"/leads/{int(lead_id)}", params={"with": "contacts,source_id"})
    if not r:
        raise ErroFerramenta(f"lead {lead_id} não existe nesta conta do Kommo")
    return _resumo_lead(r)


@srv.ferramenta("kommo_conversa",
                "Conversa e anotações de um lead, em ordem de tempo (quem falou, quando, o quê). "
                "O que é anterior à integração não vem pela API do Kommo. Só leitura.",
                {"lead_id": {"type": "string"}, "maximo": {"type": "integer", "default": 100}}, ["lead_id"])
def kommo_conversa(lead_id, maximo=100):
    notas = _lista(f"/leads/{int(lead_id)}/notes", "notes", {"order[created_at]": "asc"}, maximo=int(maximo or 100))
    saida = []
    for n in notas:
        tipo = n.get("note_type")
        p = n.get("params") or {}
        texto = p.get("text") or p.get("message") or p.get("link") or ""
        if not texto and tipo not in NOTAS_DE_CONVERSA:
            continue
        entrada = tipo in ("amomail_message", "chat_message") and (p.get("income") is True)
        saida.append({"id": str(n.get("id")), "tipo": tipo,
                      "direcao": "entrada" if entrada else ("saida" if tipo in NOTAS_DE_CONVERSA else "nota"),
                      "quem": p.get("author") or p.get("from") or ("cliente" if entrada else None),
                      "texto": texto, "em": _quando(n.get("created_at"))})
    return saida


CANAIS = (("amocrmwa", "WhatsApp"), ("waba", "WhatsApp"), ("whatsapp", "WhatsApp"), ("instagram", "Instagram"),
          ("facebook", "Facebook"), ("fb", "Facebook"), ("messenger", "Facebook"), ("telegram", "Telegram"),
          ("viber", "Viber"), ("sms", "SMS"), ("amojo", "Chat do site"), ("site", "Chat do site"))


def canal_da_origem(origem):
    """'com.amocrm.amocrmwa' → 'WhatsApp'; 'instagram' → 'Instagram'… None se não souber."""
    o = (origem or "").lower()
    for chave, nome in CANAIS:
        if chave in o:
            return nome
    return None


TIPOS_CHAT = ("incoming_chat_message", "outgoing_chat_message")


_talks = {}
TIPOS_TALK = ("conversation_answered",)          # o único tipo de talk que a conta emitiu (10/09); nome inventado = 400


def talk(talk_id):
    """Conversa (talk) do Kommo: lead, contato, canal (origin), horas. Com cache."""
    tid = str(talk_id)
    if tid not in _talks:
        r = _req(f"/talks/{int(tid)}") or {}
        _talks[tid] = {"id": tid, "lead_id": str(r.get("entity_id")) if r.get("entity_type") in ("lead", "leads") and r.get("entity_id") else None,
                       "contato_id": str(r.get("contact_id")) if r.get("contact_id") else None,
                       "origem": r.get("origin"), "canal": canal_da_origem(r.get("origin")),
                       "lida": r.get("is_read"), "em_trabalho": r.get("is_in_work"),
                       "criada_em": _quando(r.get("created_at")), "atualizada_em": _quando(r.get("updated_at"))}
    return _talks[tid]


def _lead_do_contato(contato_id):
    """Lead mais recente ligado a um contato (para conversa que só aponta o contato)."""
    r = _req(f"/contacts/{int(contato_id)}", params={"with": "leads"}) or {}
    leads = ((r.get("_embedded") or {}).get("leads") or [])
    return str(leads[-1]["id"]) if leads else None


def _evento_chat(ev):
    """Evento cru → registro de chat, ou None se não for mensagem de chat.
    Nesta conta (10/09) a conversa aparece como entidade 'talk' (conversation_answered):
    o talk diz o lead e o canal."""
    tipo = str(ev.get("type") or "")
    if ev.get("entity_type") == "talk" or tipo in TIPOS_TALK:
        try:
            t = talk(ev.get("entity_id"))
        except Exception:
            return None
        lead = t["lead_id"]
        if not lead and t["contato_id"]:
            try:
                lead = _lead_do_contato(t["contato_id"])
            except Exception:
                lead = None
        if not lead:
            return None
        # "answered" = nós respondemos; "created/opened" = o cliente falou
        entrada = tipo in ("talk_created", "talk_opened")
        return {"id": str(ev.get("id")), "lead_id": lead, "direcao": "entrada" if entrada else "saida",
                "canal": t["canal"], "origem": t["origem"], "tipo": tipo, "talk_id": t["id"], "mensagem_id": None,
                "em": _quando(ev.get("created_at"))}
    if "chat_message" not in tipo and "message" not in tipo:
        return None
    if ev.get("entity_type") not in (None, "lead", "leads"):
        return None
    va = ev.get("value_after") or []
    msg = {}
    if isinstance(va, list) and va and isinstance(va[0], dict):
        msg = va[0].get("message") or va[0]
    elif isinstance(va, dict):
        msg = va.get("message") or va
    origem = msg.get("origin") or msg.get("source") or ""
    return {"id": str(ev.get("id")), "lead_id": str(ev.get("entity_id")),
            "direcao": "entrada" if tipo.startswith("incoming") else "saida",
            "canal": canal_da_origem(origem), "origem": origem or None, "tipo": tipo,
            "talk_id": str(msg.get("talk_id")) if msg.get("talk_id") else None,
            "mensagem_id": str(msg.get("id")) if msg.get("id") else None,
            "em": _quando(ev.get("created_at"))}


def _filtros_de_chat(desde):
    """Os formatos de filtro que a API v4 aceita variam entre contas/versões; tenta na ordem."""
    return [
        ("tipo[]", {"filter[type][]": TIPOS_CHAT + TIPOS_TALK, "filter[created_at][from]": desde}),
        ("tipo[0]", {"filter[type][0]": TIPOS_CHAT[0], "filter[type][1]": TIPOS_CHAT[1], "filter[created_at][from]": desde}),
        ("tipo,csv", {"filter[type]": ",".join(TIPOS_CHAT + TIPOS_TALK), "filter[created_at][from]": desde}),
        ("sem tipo", {"filter[created_at][from]": desde}),
    ]


def _lista_eventos(params, maximo):
    """Como _lista, mas com listas nos params (urlencode doseq)."""
    saida, pagina = [], 1
    limite = min(LIMITE_PAGINA, maximo)
    while len(saida) < maximo:
        p = dict(params, page=pagina, limit=limite)
        url = _base() + "/events?" + urllib.parse.urlencode(p, doseq=True)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['KOMMO_TOKEN']}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                bruto = r.read()
                dados = json.loads(bruto) if bruto and r.status != 204 else {}
        except urllib.error.HTTPError as e:
            if e.code == 204:
                break
            raise ErroFerramenta(f"Kommo GET /events → {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        itens = ((dados or {}).get("_embedded") or {}).get("events") or []
        saida.extend(itens)
        if len(itens) < limite or not dados.get("_links", {}).get("next"):
            break
        pagina += 1
    return saida[:maximo]


@srv.ferramenta("kommo_chats",
                "Movimento do chat (Instagram, Facebook, WhatsApp…) pelos eventos da conta: para cada "
                "mensagem recebida/enviada, o lead, o canal, a direção e a hora. O TEXTO das mensagens "
                "dos canais nativos não vem pela API do Kommo. Só leitura.",
                {"desde_dias": {"type": "integer", "default": 30}, "maximo": {"type": "integer", "default": 2000}}, [])
def kommo_chats(desde_dias=30, maximo=2000):
    _talks.clear()
    desde = int(time.time()) - int(desde_dias or 30) * 86400
    saida, modo, erros = [], None, []
    for nome, params in _filtros_de_chat(desde):
        try:
            # sem filtro de tipo vem TUDO (etapa, tarefa, nota…): lê mais páginas e separa aqui
            brutos = _lista_eventos(params, maximo if nome != "sem tipo" else max(maximo, 1000))
        except ErroFerramenta as e:                     # formato que esta conta não aceita: tenta o próximo
            erros.append(f"{nome}: {str(e)[:120]}")
            continue
        saida = [x for x in (_evento_chat(ev) for ev in brutos) if x]
        modo = nome
        if saida:
            break
    if modo is None and erros:
        raise ErroFerramenta("nenhum formato de filtro aceito: " + " | ".join(erros))
    saida.sort(key=lambda x: x["em"] or "")
    _ultimo_modo["modo"] = modo
    return saida


_ultimo_modo = {"modo": None}


def eventos_brutos_humano(maximo=20, desde_dias=30):
    """Diagnóstico (porta do painel, só ADMIN): os últimos eventos crus da conta, sem
    filtro de tipo, com os nomes de tipo e a forma do value_after — o suficiente para
    acertar o filtro de chat sem adivinhar. Nunca traz texto de mensagem."""
    desde = int(time.time()) - int(desde_dias or 30) * 86400
    brutos = _lista_eventos({"filter[created_at][from]": desde}, int(maximo or 20))
    tipos = {}
    for ev in brutos:
        tipos[ev.get("type")] = tipos.get(ev.get("type"), 0) + 1
    amostra = [{"type": ev.get("type"), "entity_type": ev.get("entity_type"), "entity_id": ev.get("entity_id"),
                "created_at": _quando(ev.get("created_at")),
                "value_after": json.loads(json.dumps(ev.get("value_after"))[:400]) if isinstance(ev.get("value_after"), (dict, list)) and len(json.dumps(ev.get("value_after"))) <= 400 else str(ev.get("value_after"))[:400]}
               for ev in brutos[:int(maximo or 20)]]
    return {"tipos": tipos, "amostra": amostra, "modo_do_ultimo_chats": _ultimo_modo["modo"]}


# --------------------------------------------------- portas humanas
# Não são ferramentas do agente: quem chama é o Command Center, depois do
# clique de uma pessoa. Todas exigem APLICAR=1 (o painel libera na hora).
def mover_etapa_humano(lead_id, etapa_id, funil_id=None):
    """Move o lead de etapa no funil. Não fecha, não apaga: só muda a coluna."""
    funil, etapa, _ = _nome_etapa(funil_id, etapa_id) if funil_id else (None, None, None)
    if not _aplicar():
        return _simulado(f"mover lead {lead_id} para a etapa {etapa or etapa_id}")
    corpo = {"status_id": int(etapa_id)}
    if funil_id:
        corpo["pipeline_id"] = int(funil_id)
    _req(f"/leads/{int(lead_id)}", "PATCH", corpo)
    return {"aplicado": True, "lead_id": str(lead_id), "etapa_id": str(etapa_id), "etapa": etapa, "funil": funil}


def marcar_tag_humano(lead_id, tags):
    """ACRESCENTA tags ao lead (as que já existem continuam)."""
    novas = [t.strip() for t in (tags if isinstance(tags, (list, tuple)) else [tags]) if str(t).strip()]
    if not novas:
        raise ErroFerramenta("nenhuma tag para marcar")
    atual = kommo_lead(lead_id)["tags"]
    juntas = atual + [t for t in novas if t not in atual]
    if not _aplicar():
        return _simulado(f"marcar {novas} no lead {lead_id} (ficaria com {juntas})")
    _req(f"/leads/{int(lead_id)}", "PATCH", {"_embedded": {"tags": [{"name": t} for t in juntas]}})
    return {"aplicado": True, "lead_id": str(lead_id), "tags": juntas, "novas": novas}


def nota_humana(lead_id, texto):
    """Anotação interna no lead (não vai para o cliente)."""
    texto = (texto or "").strip()
    if not texto:
        raise ErroFerramenta("nota vazia")
    if not _aplicar():
        return _simulado(f"anotar no lead {lead_id}: {texto[:80]}")
    r = _req(f"/leads/{int(lead_id)}/notes", "POST",
             [{"note_type": NOTA_COMUM, "params": {"text": texto[:20000]}}])
    nid = (((r or {}).get("_embedded") or {}).get("notes") or [{}])[0].get("id")
    return {"aplicado": True, "lead_id": str(lead_id), "nota_id": str(nid) if nid else None}


# --------------------------------------------- o chat: circuito do Salesbot
# Caminho provado com lead real do Instagram em 24/08 (era Chase): o Salesbot
# tem um bloco de widget que faz `widget_request` para o nosso hook a cada
# mensagem recebida (form-encoded, chaves PHP-style) e fica esperando a
# continuação; quem responde POSTa no `return_url` com {"data": {"reply": …}}
# e o bot mostra {{json.reply}} no chat do lead — o texto NOSSO, inteiro, no
# canal em que ele falou. Para responder horas depois, `bots/run` reabre o
# canal: o bot chama o hook sem mensagem e recebe o que estava na fila.
import base64
import hashlib
import hmac


def parse_corpo_hook(bruto):
    """Corpo do widget_request em qualquer formato: JSON ou form-urlencoded com
    chaves PHP-style ('data[lead_id]'), que é o que o Salesbot manda de verdade."""
    if not bruto:
        return {}
    if isinstance(bruto, bytes):
        bruto = bruto.decode("utf-8", "replace")
    try:
        j = json.loads(bruto)
        return j if isinstance(j, dict) else {"_corpo": j}
    except ValueError:
        pass
    plano = {k: (v[0] if len(v) == 1 else v) for k, v in urllib.parse.parse_qs(bruto, keep_blank_values=True).items()}
    raiz = {}
    for chave, valor in plano.items():
        partes = chave.replace("]", "").split("[")
        no = raiz
        for i, parte in enumerate(partes):
            if i == len(partes) - 1:
                no[parte] = valor
            else:
                prox = no.get(parte)
                if not isinstance(prox, dict):
                    prox = {}
                    no[parte] = prox
                no = prox
    return raiz


def _cava(payload, *caminhos):
    for caminho in caminhos:
        no = payload
        for parte in caminho.split("."):
            if isinstance(no, list) and parte.isdigit():
                no = no[int(parte)] if int(parte) < len(no) else None
            elif isinstance(no, dict):
                no = no.get(parte)
            else:
                no = None
            if no is None:
                break
        if isinstance(no, (str, int, float)) and no != "":
            return no
    return None


def extrair_entrada(payload):
    """(lead_id, texto, return_url, token, nome, telefone) do payload do widget."""
    lead = _cava(payload, "lead_id", "data.lead_id", "data.lead.id", "data.lead.0.id", "lead.id", "leads.0.id")
    texto = _cava(payload, "message", "data.message", "data.message.text", "data.message.message.text",
                  "message.text", "data.talk.message.text", "text", "data.text")
    # o placeholder que o Kommo não resolveu vem literal: não é mensagem
    if isinstance(texto, str) and texto.strip().startswith("{{"):
        texto = None
    return {"lead_id": str(lead) if lead is not None else None, "texto": (str(texto).strip() if texto is not None else ""),
            "return_url": _cava(payload, "return_url", "data.return_url"),
            "token": _cava(payload, "token", "data.token"),
            "nome": _cava(payload, "contact_name", "data.contact_name", "data.contact.name", "contact.name"),
            "telefone": _cava(payload, "contact_phone", "data.contact_phone", "data.contact.phone")}


def verificar_token_bot(token):
    """JWT descartável do widget_request: HS512 com o client secret da integração
    (KOMMO_BOT_SECRET). Sem segredo configurado, não há o que verificar (True)."""
    segredo = os.environ.get("KOMMO_BOT_SECRET", "")
    if not segredo:
        return True
    if not token or token.count(".") != 2:
        return False
    try:
        h, p, sig = token.split(".")
        esperado = hmac.new(segredo.encode(), f"{h}.{p}".encode(), hashlib.sha512).digest()
        dado = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        if not hmac.compare_digest(esperado, dado):
            return False
        claims = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        return claims.get("exp") is None or int(claims["exp"]) >= int(time.time())
    except Exception:
        return False


_SHOW_LIMITE = 80          # validado na conta em 24/08: show > 80 chars = 400 TooLong
_MAX_HANDLERS = 10
_RX_FRASE = re.compile(r"(?<=[.!?…])\s+")


def _baloes(texto, limite=_SHOW_LIMITE):
    """Quebra a resposta em balões de até `limite` chars: por linha, depois por frase,
    por palavra só em último caso (nunca no meio de palavra/URL). Porte do provado 24/08."""
    saida = []

    def _palavras(seg):
        while len(seg) > limite:
            corte = seg.rfind(" ", 1, limite + 1)
            if corte <= 0:
                corte = limite
            saida.append(seg[:corte].strip())
            seg = seg[corte:].strip()
        if seg:
            saida.append(seg)

    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        if len(linha) <= limite:
            saida.append(linha)
            continue
        junto = ""
        for frase in _RX_FRASE.split(linha):
            cand = f"{junto} {frase}".strip() if junto else frase
            if len(cand) <= limite:
                junto = cand
            else:
                if junto:
                    saida.append(junto)
                junto = ""
                if len(frase) <= limite:
                    junto = frase
                else:
                    _palavras(frase)
        if junto:
            saida.append(junto)
    return saida


def _return_url_confiavel(url):
    """A continuação leva o KOMMO_TOKEN no header: só vai para o domínio da conta."""
    try:
        p = urllib.parse.urlparse(str(url or ""))
    except Exception:
        return False
    if p.scheme != "https" or not p.hostname:
        return False
    dominio = os.environ.get("KOMMO_DOMAIN", "").replace("https://", "").strip("/").lower()
    host = p.hostname.lower()
    return host == dominio or host.endswith(".kommo.com") or host.endswith(".amocrm.com")


def continuar_bot_humano(return_url, texto):
    """Entrega `texto` no chat do lead pela continuação do Salesbot.

    KOMMO_MODO_ENTREGA = "balloons" (padrão; provado com lead real em 24/08: até 10
    handlers `show` de <= 80 chars) ou "json_reply" (widget v2: uma mensagem inteira via
    {{json.reply}}; só se o widget v2 estiver instalado e o bot re-salvo).
    Devolve (ok, detalhe). 404 = o bot já não estava esperando."""
    texto = (texto or "").strip()
    if not texto or not return_url:
        return False, "sem texto ou sem return_url"
    if not _return_url_confiavel(return_url):
        return False, "return_url fora do domínio do Kommo"
    modo = (os.environ.get("KOMMO_MODO_ENTREGA") or "balloons").strip().lower()
    if modo == "json_reply":
        corpo = {"data": {"status": "success", "reply": texto[:4000]}}
    else:
        pedacos = _baloes(texto)
        if not pedacos:
            return False, "sem texto"
        if len(pedacos) > _MAX_HANDLERS:
            return False, f"resposta longa demais para o chat ({len(pedacos)} balões, máximo {_MAX_HANDLERS}): encurte"
        corpo = {"data": {"status": "success"},
                 "execute_handlers": [{"handler": "show", "params": {"type": "text", "value": p}} for p in pedacos]}
    if not _aplicar():
        return False, f"SIMULAÇÃO (APLICAR=0): entregaria no chat ({modo}): {texto[:80]}"
    req = urllib.request.Request(return_url, data=json.dumps(corpo).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['KOMMO_TOKEN']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 300, f"{r.status} ({modo})"
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:200]
        if e.code == 404:
            return False, "o bot já não estava esperando (404)"
        return False, f"{e.code}: {detalhe}"
    except Exception as e:                       # URLError, timeout, conexão caída: nunca derruba quem chamou
        return False, f"falha na entrega: {type(e).__name__}: {str(e)[:120]}"


def abrir_canal_humano(lead_id, bot_id=None):
    """Dispara o Salesbot no lead (`bots/run`, provado em 25/08): o bot chama o hook
    sem mensagem e recebe o que estiver na fila. Sem KOMMO_BOT_ID, recusa."""
    bot = str(bot_id or os.environ.get("KOMMO_BOT_ID") or "").strip()
    if not bot:
        raise ErroFerramenta("RECUSADO: sem KOMMO_BOT_ID no ~/.urace/kommo.env não dá para reabrir o chat do "
                             "lead. Ligue o bot do Command Center no Kommo e grave o id dele.")
    if not _aplicar():
        return _simulado(f"disparar o bot {bot} no lead {lead_id}")
    _req(f"/bots/{int(bot)}/run", "POST", {"entity_id": int(lead_id), "entity_type": "leads"})
    return {"aplicado": True, "lead_id": str(lead_id), "bot_id": bot}


def responder_humano(lead_id, texto, bot_id=None):
    """Mantida por compatibilidade: hoje a resposta é fila + circuito do Salesbot
    (command_center/api/crm.py). Aqui só reabre o canal."""
    return abrir_canal_humano(lead_id, bot_id)


def atribuir_humano(lead_id, usuario_id):
    """Troca o responsável do lead."""
    if not _aplicar():
        return _simulado(f"passar o lead {lead_id} para o usuário {usuario_id}")
    _req(f"/leads/{int(lead_id)}", "PATCH", {"responsible_user_id": int(usuario_id)})
    return {"aplicado": True, "lead_id": str(lead_id), "responsavel_id": str(usuario_id)}


def usuarios_humano():
    """Usuários da conta (para escolher responsável)."""
    return [{"id": str(u.get("id")), "nome": u.get("name"), "email": u.get("email")}
            for u in _lista("/users", "users", maximo=100)]


if __name__ == "__main__":
    _carregar_env()
    log("APLICAR =", os.environ.get("APLICAR", "0"), "| conta:", os.environ.get("KOMMO_DOMAIN"))
    srv.rodar()
