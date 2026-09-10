#!/usr/bin/env python3
"""Servidor MCP próprio do Kommo (CRM comercial da URACE, urace.kommo.com).

Roda no HOST, sem dependência nenhuma (urllib). O token longo da
integração privada fica em ~/.urace/kommo.env (KOMMO_DOMAIN, KOMMO_TOKEN,
KOMMO_BOT_ID, KOMMO_CAMPO_RESPOSTA, KOMMO_WEBHOOK_SECRET) — nunca no
repositório, nunca no container do agente.

Regras do dono, em código:
  - NADA é apagado: não existe apagar lead, contato, nota ou tag aqui.
  - LER é livre (funis, leads, contato, origem, tags, conversa).
  - ESCREVER (mover de etapa, marcar tag, anotar, responder) é PORTA
    HUMANA: não é ferramenta do agente, e só acontece com APLICAR=1,
    que o Command Center libera na ação do dono. O agente pode PROPOR
    pelo painel; quem confirma é gente.
  - Responder pelo canal nativo (Instagram/Facebook/WhatsApp) sai pelo
    Salesbot da conta (caminho provado em 24-25/08 na era Chase): a
    mensagem aparece como do bot, e o texto do painel só chega ao cliente
    se o bot mandar o campo indicado em KOMMO_CAMPO_RESPOSTA. Sem
    KOMMO_BOT_ID a resposta é recusada; sem o campo, o painel avisa que
    quem escolhe o texto é o roteiro do bot — nunca finge que enviou.

Ver brain/40_SISTEMAS/Kommo - o que da para fazer pelo Command Center.md.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

TIMEOUT = 20
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


def _aplicar():
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
        if e.code == 404:
            return {}
        raise ErroFerramenta(f"Kommo {metodo} {caminho} → {e.code}: {detalhe}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"Kommo fora de alcance: {e}")


def _lista(caminho, chave, params=None, maximo=200):
    """Pagina /api/v4 até `maximo`. Devolve a lista de `_embedded[chave]`."""
    saida, pagina = [], 1
    while len(saida) < maximo:
        p = dict(params or {}, page=pagina, limit=min(LIMITE_PAGINA, maximo - len(saida)))
        r = _req(caminho, params=p)
        itens = ((r or {}).get("_embedded") or {}).get(chave) or []
        saida.extend(itens)
        if len(itens) < p["limit"] or not r.get("_links", {}).get("next"):
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


def _contato_do_lead(lead):
    """Primeiro contato embutido → nome, e-mail, telefone."""
    cs = ((lead.get("_embedded") or {}).get("contacts") or [])
    if not cs:
        return {}
    c = cs[0]
    if "custom_fields_values" not in c and c.get("id"):        # veio só o id: busca o contato
        c = _req(f"/contacts/{c['id']}") or c
    return _resumo_contato(c)


def _campos(entidade):
    """custom_fields_values → {nome do campo: valor}."""
    saida = {}
    for cf in (entidade.get("custom_fields_values") or []):
        vals = [v.get("value") for v in (cf.get("values") or []) if v.get("value") not in (None, "")]
        if vals:
            saida[cf.get("field_name") or cf.get("field_code") or str(cf.get("field_id"))] = vals[0] if len(vals) == 1 else vals
    return saida


def _resumo_contato(c):
    campos = _campos(c)
    email = next((v for k, v in campos.items() if "email" in (k or "").lower()), None)
    tel = next((v for k, v in campos.items() if any(x in (k or "").lower() for x in ("phone", "telefone", "whats"))), None)
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
    return [_resumo_lead(l) for l in _lista("/leads", "leads", params, maximo=int(maximo or 50))]


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


def responder_humano(lead_id, texto, bot_id=None):
    """Responde ao lead pelo canal em que ele falou (Instagram, Facebook, WhatsApp).

    Como a mensagem sai: quem entrega no chat é o Salesbot da conta, disparado
    por API (caminho provado em 24-25/08 na era Chase). Duas coisas vêm daí, e
    as duas são ditas em voz alta em vez de escondidas:

      1. a mensagem aparece como do BOT, não de uma pessoa, e o gatilho tem
         cooldown de 5 min por lead;
      2. o bot manda o que ELE está configurado para mandar. Para o texto
         escrito no painel chegar ao cliente, o Salesbot precisa enviar um
         CAMPO do lead — o id desse campo vai em KOMMO_CAMPO_RESPOSTA, e o
         painel grava o texto lá antes de disparar. Sem esse campo, o painel
         grava a nota, dispara o bot e AVISA que quem escolhe o texto é o
         roteiro do bot: ninguém fica achando que o cliente leu o que se
         escreveu aqui.

    Sem KOMMO_BOT_ID a resposta é RECUSADA: melhor não responder do que fingir."""
    texto = (texto or "").strip()
    if not texto:
        raise ErroFerramenta("resposta vazia")
    bot = str(bot_id or os.environ.get("KOMMO_BOT_ID") or "").strip()
    if not bot:
        raise ErroFerramenta("RECUSADO: sem KOMMO_BOT_ID no ~/.urace/kommo.env não dá para entregar a mensagem no "
                             "chat do Kommo. Configure o Salesbot de resposta (ou responda pelo próprio Kommo) — "
                             "a nota interna continua disponível.")
    campo = str(os.environ.get("KOMMO_CAMPO_RESPOSTA") or "").strip()
    if not _aplicar():
        return _simulado(f"responder ao lead {lead_id} pelo bot {bot}"
                         f"{f' (texto no campo {campo})' if campo else ' (sem campo de resposta configurado)'}: {texto[:80]}")
    if campo:                                    # o Salesbot lê este campo e manda o que está nele
        _req(f"/leads/{int(lead_id)}", "PATCH",
             {"custom_fields_values": [{"field_id": int(campo), "values": [{"value": texto[:4000]}]}]})
    # o texto vai como nota do painel ANTES do disparo: fica o registro do que foi dito
    _req(f"/leads/{int(lead_id)}/notes", "POST",
         [{"note_type": NOTA_COMUM, "params": {"text": f"[Command Center] resposta enviada: {texto[:2000]}"}}])
    _req(f"/bots/{int(bot)}/run", "POST", {"entity_id": int(lead_id), "entity_type": "leads"})
    return {"aplicado": True, "lead_id": str(lead_id), "bot_id": bot, "campo": campo or None,
            "como": "mensagem do bot no canal do lead",
            "aviso": ("sai como mensagem do bot; cooldown de 5 min por lead" if campo else
                      "sai como mensagem do bot e QUEM ESCOLHE O TEXTO É O ROTEIRO DO BOT: sem "
                      "KOMMO_CAMPO_RESPOSTA configurado, o que você escreveu ficou registrado na nota do lead, "
                      "mas pode não ser o que o cliente vai ler. Cooldown de 5 min por lead.")}


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
