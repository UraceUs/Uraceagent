"""Atendimento humano: o escalonamento da IA para uma pessoa (missão de 14/10).

    IA (ponte/Chase) ──escalate_to_human──▶ POST /ops/api/atendimento/casos
                                              │ 1. caso HUMAN_PENDING (um aberto por conversa)
                                              │ 2. trava a IA: ~/.urace/sdr_pausas.json
                                              │ 3. avisos: push · chat da equipe · WhatsApp oficial
    pessoa ──assumir──▶ HUMAN_ACTIVE ──responder pelo Kommo (o canal oficial do WhatsApp)
           ──encerrar──▶ RESOLVED          ┐ a ponte confirma a transição; só então a trava sai
           ──devolver à IA──▶ RETURNED_TO_AI┘ (sem confirmação a conversa continua com gente)

Três regras que não dependem de ninguém lembrar:

1. **A trava é do sistema, não do prompt.** O caso aberto escreve a conversa no arquivo de
   pausas que a ponte lê antes de toda resposta, follow-up e resgate. `reconciliar_pausas`
   reescreve o que faltar a cada meio minuto: queda no meio do caminho não destrava ninguém.
2. **Nada é dito como feito sem estar feito.** O agente recebe `humano_notificado=true` só
   quando um aviso saiu de verdade (push aceito por um aparelho, WhatsApp com id da Meta).
   Chat da equipe e simulação contam como registro, não como aviso.
3. **Idempotência em tudo que repete.** Chave por pedido, índice único por conversa aberta e
   chave por aviso: reprocessar o mesmo evento não abre caso nem manda aviso de novo.

Configuração (ambiente ou ~/.urace/atendimento.env, nunca no repositório):
  HANDOFF_PONTE_URL     onde a ponte ouve (ex.: http://127.0.0.1:8800). Vazio = sem ponte.
  HANDOFF_PONTE_TOKEN   segredo compartilhado com a ponte (cabeçalho X-Handoff-Token)
  HANDOFF_URL_PUBLICA   endereço do painel nos avisos (padrão https://ops.urace.us)
  WA_TEMPLATE_HANDOFF   template aprovado pela Meta para avisar fora da janela de 24 h
  HANDOFF_RETENCAO_DIAS texto de caso encerrado é apagado depois disto (padrão 365)
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from command_center.db import agora, auditar, inserir, todos, um

ENV = "~/.urace/atendimento.env"
FUSO = ZoneInfo("America/New_York")

ABERTOS = ("HUMAN_PENDING", "HUMAN_ACTIVE")
FECHADOS = ("RESOLVED", "RETURNED_TO_AI")
PRIORIDADES = ("baixa", "normal", "alta", "urgente")
# Quanto tempo um caso pode esperar alguém assumir antes de virar "atrasado".
PRAZO_MIN = {"urgente": 5, "alta": 15, "normal": 60, "baixa": 240}
REALERTA_MIN = 15          # entre um re-aviso e o próximo, enquanto ninguém assume
TETO_REALERTAS = 4         # depois disto o caso continua vermelho na tela, sem mais barulho
TENTATIVAS_MAX = 5         # aviso que falha 5 vezes desiste (e fica vermelho)

MOTIVOS = {
    "pedido_explicito": "o cliente pediu uma pessoa",
    "reclamacao": "reclamação",
    "pagamento": "pagamento, cobrança ou reembolso",
    "excecao_comercial": "exceção comercial fora da regra",
    "falhas_repetidas": "a IA não conseguiu resolver",
    "sem_autoridade": "precisa de decisão ou acesso que a IA não tem",
    "seguranca": "segurança, privacidade ou incidente",
    "baixa_confianca": "a IA não tem dado confiável para responder",
    "competidor": "piloto que compete (conversa do dono)",
    "operacional": "pedido operacional",
    "outro": "outro",
}
# A ponte e o agente falam em inglês e em português; tudo vira uma das chaves acima.
_SINONIMOS = {
    "explicit_request": "pedido_explicito", "human": "pedido_explicito", "pessoa": "pedido_explicito",
    "complaint": "reclamacao", "payment": "pagamento", "refund": "pagamento", "reembolso": "pagamento",
    "billing": "pagamento", "cobranca": "pagamento", "discount_request": "excecao_comercial",
    "desconto": "excecao_comercial", "commercial_exception": "excecao_comercial",
    "repeated_failure": "falhas_repetidas", "no_authority": "sem_autoridade", "security": "seguranca",
    "privacy": "seguranca", "incident": "seguranca", "low_confidence": "baixa_confianca",
    "kb_gap": "baixa_confianca", "unknown": "baixa_confianca", "competitor_profile": "competidor",
    "compete": "competidor", "operational_request": "operacional", "other": "outro",
}
# Quando só vem o texto do motivo, palavras dele escolhem a categoria (a primeira que bater).
_PALAVRAS = [
    ("pagamento", ("refund", "reembolso", "charge", "cobran", "pagamento", "payment", "invoice", "chargeback")),
    ("reclamacao", ("complaint", "reclama", "insatisf", "unhappy", "angry")),
    ("seguranca", ("lawyer", "advogad", "jurídic", "juridic", "privacy", "privacidade", "acidente",
                   "injury", "lesão", "incident")),
    ("excecao_comercial", ("discount", "desconto", "cheaper", "mais barato", "negoci")),
    ("pedido_explicito", ("human", "humano", "pessoa", "person", "someone", "manager", "gerente")),
    ("competidor", ("compete", "competi", "racer", "race team")),
    ("baixa_confianca", ("não sei", "nao sei", "unknown", "confian", "confidence")),
]


class ErroAtendimento(ValueError):
    """Pedido inválido: o que o chamador mandou não serve. Vira 400/403/409 na rota."""

    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.codigo = codigo


# --------------------------------------------------------------------- configuração
def _carrega_env():
    caminho = os.path.expanduser(os.environ.get("HANDOFF_ENV", ENV))
    try:
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def cfg(nome, padrao=""):
    if not os.environ.get(nome):
        _carrega_env()
    return os.environ.get(nome, padrao)


def _url_publica():
    return cfg("HANDOFF_URL_PUBLICA", "https://ops.urace.us").rstrip("/")


# --------------------------------------------------------------------- tempo
def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _dt(iso):
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _agora_dt():
    return datetime.now(timezone.utc)


def horario_humano(quando=None):
    """Seg–sex, 8h–18h de Orlando (D-2026-10-06). Re-aviso de prioridade normal/baixa só aqui."""
    t = (quando or _agora_dt()).astimezone(FUSO)
    return t.weekday() < 5 and 8 <= t.hour < 18


# --------------------------------------------------------------------- normalização
def lead_da_conversa(conversation_id):
    """Aceita 123, "123" ou "kommo:123". Devolve o id do lead no Kommo (int > 0)."""
    bruto = str(conversation_id if conversation_id is not None else "").strip()
    if bruto.lower().startswith("kommo:"):
        bruto = bruto[6:]
    if not bruto.isdigit() or int(bruto) <= 0 or len(bruto) > 15:
        raise ErroAtendimento("conversation_id inválido: use o id do lead no Kommo (ex.: kommo:31764961).")
    return int(bruto)


def prioridade_de(valor):
    v = str(valor or "normal").strip().lower()
    v = {"low": "baixa", "medium": "normal", "media": "normal", "média": "normal", "high": "alta",
         "urgent": "urgente", "critica": "urgente", "crítica": "urgente"}.get(v, v)
    if v not in PRIORIDADES:
        raise ErroAtendimento(f"prioridade inválida: use {', '.join(PRIORIDADES)}.")
    return v


def motivo_de(categoria, texto):
    """A categoria que veio (em pt ou en) ou, sem ela, a que as palavras do motivo indicam."""
    c = str(categoria or "").strip().lower()
    c = _SINONIMOS.get(c, c)
    if c in MOTIVOS:
        return c
    t = (texto or "").lower()
    for chave, palavras in _PALAVRAS:
        if any(p in t for p in palavras):
            return chave
    return "outro"


def _limpo(texto, limite):
    return " ".join(str(texto or "").split())[:limite] or None


# --------------------------------------------------------------------- eventos
def _evento(con, caso_id, tipo, ator, ator_nome=None, de=None, para=None, detalhe=None, correlacao=None):
    inserir(con, "handoff_eventos", caso_id=caso_id, tipo=tipo, ator=ator, ator_nome=(ator_nome or "")[:80] or None,
            de_estado=de, para_estado=para,
            detalhe=json.dumps(detalhe, ensure_ascii=False) if detalhe is not None else None,
            correlacao=(correlacao or None))


def _ator(u):
    if not u:
        return "sistema", "sistema"
    via = u.get("via")
    return (via if via else f"user:{u['id']}"), (u.get("name") or u.get("email") or "")


def caso(con, caso_id):
    c = um(con, "SELECT * FROM handoff_casos WHERE id=?", (caso_id,))
    if not c:
        raise ErroAtendimento("Caso não encontrado.", 404)
    return c


def caso_aberto(con, kommo_lead_id):
    return um(con, f"SELECT * FROM handoff_casos WHERE kommo_lead_id=? AND estado IN ({_ph(ABERTOS)}) "
                   "ORDER BY id DESC LIMIT 1", (kommo_lead_id, *ABERTOS))


def _ph(seq):
    return ",".join("?" * len(seq))


def estado_conversa(con, kommo_lead_id):
    """O estado lógico da conversa (o que a missão chama de AI_ACTIVE/HUMAN_*/RESOLVED)."""
    ultimo = um(con, "SELECT estado FROM handoff_casos WHERE kommo_lead_id=? ORDER BY id DESC LIMIT 1",
                (kommo_lead_id,))
    if not ultimo or ultimo["estado"] == "RETURNED_TO_AI":
        return "AI_ACTIVE"
    return ultimo["estado"]


# --------------------------------------------------------------------- a trava da IA
def _pausas():
    from command_center.api import sdr
    return sdr


def travar_ia(caso_row):
    """Escreve a conversa no arquivo que a ponte lê. Pausa manual que já existia é preservada:
    o caso só acrescenta a marca dele, e ao fechar só tira a marca dele."""
    sdr = _pausas()
    chave = str(caso_row["kommo_lead_id"])

    sdr.alterar_pausas(lambda d: _marcar_pausa(d, chave, caso_row))


def _marcar_pausa(d, chave, caso_row):
    """Pausa nova ganha autor e motivo do caso. Pausa manual que já existia fica como está (quem
    pausou, quando e por quê) e só recebe a marca do caso por cima."""
    atual = d.get(chave) if isinstance(d.get(chave), dict) else None
    if atual and (atual.get("manual") or not atual.get("handoff")):
        d[chave] = {**atual, "manual": True, "handoff": caso_row["id"]}
        return
    d[chave] = {"handoff": caso_row["id"], "por": f"atendimento humano #{caso_row['id']}",
                "em": datetime.now(FUSO).isoformat(timespec="seconds"),
                "motivo": MOTIVOS.get(caso_row["motivo"], caso_row["motivo"])}


def destravar_ia(caso_row):
    """Tira só a marca deste caso. Pausa manual de antes continua (a pessoa tira na página do robô)."""
    sdr = _pausas()
    chave = str(caso_row["kommo_lead_id"])

    def _mudar(d):
        atual = d.get(chave)
        if not isinstance(atual, dict) or atual.get("handoff") != caso_row["id"]:
            return
        if atual.get("manual"):
            atual.pop("handoff", None)
        else:
            d.pop(chave, None)

    sdr.alterar_pausas(_mudar)


def ia_travada(kommo_lead_id):
    entrada = _pausas().ler_pausas().get(str(kommo_lead_id))
    return entrada is not None


def reconciliar_pausas(con):
    """Arquivo e banco concordam. Caso aberto sem trava ganha trava (queda entre o INSERT e a
    escrita, arquivo apagado à mão); trava de caso que já fechou sai. Devolve o que mudou."""
    sdr = _pausas()
    abertos = {c["kommo_lead_id"]: c for c in todos(
        con, f"SELECT * FROM handoff_casos WHERE estado IN ({_ph(ABERTOS)})", ABERTOS)}
    # caso fechado mas a ponte ainda não confirmou: a trava fica até confirmar
    segurando = {c["kommo_lead_id"] for c in todos(
        con, "SELECT kommo_lead_id FROM handoff_casos WHERE ponte_pendente IS NOT NULL")}
    mudou = {"travadas": [], "soltas": []}

    def _mudar(d):
        for lead, c in abertos.items():
            atual = d.get(str(lead))
            if not isinstance(atual, dict) or atual.get("handoff") != c["id"]:
                _marcar_pausa(d, str(lead), c)
                mudou["travadas"].append(lead)
        for chave, v in list(d.items()):
            if not isinstance(v, dict) or not v.get("handoff") or not str(chave).isdigit():
                continue
            lead = int(chave)
            if lead in abertos or lead in segurando:
                continue
            if v.get("manual"):
                v.pop("handoff", None)
            else:
                d.pop(chave, None)
            mudou["soltas"].append(lead)

    sdr.alterar_pausas(_mudar)
    return mudou


# --------------------------------------------------------------------- abrir
def abrir_caso(con, *, conversation_id, reason, priority="normal", summary=None, customer_name=None,
               requested_action=None, category=None, canal=None, chave=None, origem="ia", u=None,
               correlacao=None, assumir=False, avisar_agora=True):
    """O `escalate_to_human` do agente. Devolve o que de fato aconteceu, para a IA não dizer ao
    cliente nada que não seja verdade:

        resultado        caso_criado | caso_existente
        humano_notificado  True só com aviso confirmado (push aceito / WhatsApp com id da Meta)
        notificacao      enviada | pendente | falhou | sem_destino
        ia_bloqueada     a trava da IA está escrita
    """
    lead = lead_da_conversa(conversation_id)
    motivo_texto = _limpo(reason, 500)
    if not motivo_texto:
        raise ErroAtendimento("reason é obrigatório: diga por que precisa de uma pessoa.")
    prio = prioridade_de(priority)
    motivo = motivo_de(category, motivo_texto)
    if origem not in ("ia", "regra", "humano"):
        raise ErroAtendimento("origem inválida.")
    ator, ator_nome = _ator(u)
    conversa = f"kommo:{lead}"
    chave = _limpo(chave, 200)

    crm = um(con, "SELECT id, name, contact_name, source FROM crm_leads WHERE external_id=?", (str(lead),))
    nome = _limpo(customer_name, 120) or (crm and (crm.get("contact_name") or crm.get("name"))) or None
    canal = canal or (crm and crm.get("source")) or None
    prazo = _iso(_agora_dt() + timedelta(minutes=PRAZO_MIN[prio]))

    con.execute("BEGIN IMMEDIATE")
    try:
        if chave:
            ja = um(con, "SELECT * FROM handoff_casos WHERE chave=?", (chave,))
            if ja:
                con.execute("COMMIT")
                return _resposta(con, ja, "caso_existente", "mesma chave de idempotência: pedido repetido")
        aberto = caso_aberto(con, lead)
        if aberto:
            _evento(con, aberto["id"], "escalonamento_repetido", ator, ator_nome,
                    detalhe={"motivo": motivo, "prioridade": prio}, correlacao=correlacao)
            # prioridade só sobe: um segundo pedido mais urgente não pode ficar com a primeira
            if PRIORIDADES.index(prio) > PRIORIDADES.index(aberto["prioridade"]):
                con.execute("UPDATE handoff_casos SET prioridade=?, prazo_em=MIN(COALESCE(prazo_em,?),?), "
                            "atualizado_em=? WHERE id=?", (prio, prazo, prazo, agora(), aberto["id"]))
                _evento(con, aberto["id"], "prioridade_subiu", ator, ator_nome,
                        detalhe={"de": aberto["prioridade"], "para": prio}, correlacao=correlacao)
            con.execute("COMMIT")
            return _resposta(con, caso(con, aberto["id"]), "caso_existente",
                             "a conversa já está com um atendimento humano aberto")
        cid = inserir(con, "handoff_casos", conversa=conversa, kommo_lead_id=lead,
                      crm_lead_id=crm["id"] if crm else None, conversa_conferida=1 if crm else 0,
                      canal=_limpo(canal, 30), cliente_nome=nome, prioridade=prio, motivo=motivo,
                      motivo_texto=motivo_texto, resumo=_limpo(summary, 1500),
                      acao_pedida=_limpo(requested_action, 500), origem=origem, chave=chave,
                      aberto_por=ator, prazo_em=prazo)
        _evento(con, cid, "criado", ator, ator_nome, para="HUMAN_PENDING",
                detalhe={"motivo": motivo, "prioridade": prio, "origem": origem,
                         "conversa_conferida": bool(crm)}, correlacao=correlacao)
        auditar(con, "handoff.criado", ator, user_id=(u or {}).get("id"), entity_type="handoff_caso",
                entity_id=cid, detail={"lead": lead, "motivo": motivo, "prioridade": prio, "origem": origem})
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    novo = caso(con, cid)
    try:
        travar_ia(novo)
        _evento(con, cid, "ia_travada", "sistema")
    except Exception as e:                                       # noqa: BLE001
        # o laço reconcilia a cada meio minuto; o agente fica sabendo que a trava não está escrita
        _evento(con, cid, "ia_trava_falhou", "sistema", detalhe={"erro": str(e)[:200]})
    if assumir and u:
        # a própria pessoa abriu e assumiu: ninguém precisa ser chamado, só fica no chat da equipe
        novo = assumir_caso(con, cid, u, correlacao=correlacao)
        enfileirar_avisos(con, novo, "abertura", so_registro=True)
    else:
        enfileirar_avisos(con, novo, "abertura")
    if avisar_agora:
        processar_fila(con, caso_id=cid)
    return _resposta(con, caso(con, cid), "caso_criado", None)


def resumo_avisos(con, caso_id):
    linhas = todos(con, "SELECT canal, status, erro FROM handoff_notificacoes WHERE caso_id=?", (caso_id,))
    confirmados = [n for n in linhas if n["canal"] in ("push", "whatsapp") and n["status"] in ("enviado", "entregue", "lido")]
    if confirmados:
        status = "enviada"
    elif any(n["status"] == "pendente" for n in linhas):
        status = "pendente"
    elif not [n for n in linhas if n["canal"] in ("push", "whatsapp")]:
        status = "sem_destino"
    else:
        status = "falhou"
    por_canal = {}
    for n in linhas:
        por_canal.setdefault(n["canal"], {}).setdefault(n["status"], 0)
        por_canal[n["canal"]][n["status"]] += 1
    return {"status": status, "humano_notificado": bool(confirmados), "por_canal": por_canal,
            "erros": sorted({n["erro"] for n in linhas if n["erro"]})[:5]}


def _resposta(con, c, resultado, observacao):
    avisos = resumo_avisos(con, c["id"])
    travada = ia_travada(c["kommo_lead_id"]) if c["estado"] in ABERTOS else False
    if avisos["humano_notificado"]:
        frase = "Uma pessoa da equipe foi avisada e vai assumir esta conversa."
    elif avisos["status"] == "pendente":
        frase = ("O caso está registrado e na fila da equipe, mas o aviso ainda não foi confirmado. "
                 "Não diga ao cliente que alguém já foi avisado; diga que a equipe vai responder aqui.")
    else:
        frase = ("O caso está registrado na fila da equipe, mas nenhum aviso foi confirmado. Não diga ao "
                 "cliente que alguém já foi avisado; diga que a equipe vai responder aqui.")
    return {"ok": True, "resultado": resultado, "caso_id": c["id"], "conversa": c["conversa"],
            "estado": c["estado"], "prioridade": c["prioridade"], "motivo": c["motivo"],
            "ia_bloqueada": travada, "notificacao": avisos["status"],
            "humano_notificado": avisos["humano_notificado"], "avisos": avisos["por_canal"],
            "erros_aviso": avisos["erros"], "observacao": observacao,
            "link": f"{_url_publica()}/ops/atendimento/{c['id']}", "instrucao_para_ia": frase}


# --------------------------------------------------------------------- transições humanas
def _pessoa(u):
    """Assumir, transferir, encerrar e devolver são atos de PESSOA. Chave de API é serviço:
    ela abre caso (é o caminho da IA), mas não decide atendimento."""
    if not u or str(u.get("via") or "").startswith("key:"):
        raise ErroAtendimento("Só uma pessoa logada assume, transfere, encerra ou devolve um atendimento.", 403)


def _gerente(u):
    from command_center.api import auth
    return bool(u.get("free")) or auth.pode(u.get("role"), "MANAGER")


def _mudar_estado(con, c, de, para, campos, tipo, u, detalhe=None, correlacao=None):
    """Transição com trava otimista: só muda se o caso ainda está no estado que a pessoa viu.
    Dois cliques em 'Assumir' ao mesmo tempo: o segundo recebe 409, não sobrescreve o primeiro."""
    sets = ", ".join(f"{k}=?" for k in campos)
    cur = con.execute(f"UPDATE handoff_casos SET {sets}, estado=?, atualizado_em=? WHERE id=? AND estado=?",
                      (*campos.values(), para, agora(), c["id"], de))
    if cur.rowcount != 1:
        atual = caso(con, c["id"])
        raise ErroAtendimento(f"O caso mudou enquanto você olhava (agora: {atual['estado']}). Recarregue.", 409)
    ator, nome = _ator(u)
    _evento(con, c["id"], tipo, ator, nome, de=de, para=para, detalhe=detalhe, correlacao=correlacao)
    auditar(con, f"handoff.{tipo}", ator, user_id=(u or {}).get("id"), entity_type="handoff_caso",
            entity_id=c["id"], detail={"de": de, "para": para, **(detalhe or {})})
    return caso(con, c["id"])


def assumir_caso(con, caso_id, u, correlacao=None):
    _pessoa(u)
    c = caso(con, caso_id)
    if c["estado"] != "HUMAN_PENDING":
        raise ErroAtendimento(f"Só caso pendente pode ser assumido (este está {c['estado']}).", 409)
    novo = _mudar_estado(con, c, "HUMAN_PENDING", "HUMAN_ACTIVE",
                         {"responsavel_id": u["id"], "assumido_em": agora()}, "assumido", u,
                         correlacao=correlacao)
    _avisar_ponte_em_fundo(con, novo, "HUMAN_ACTIVE", None, u)
    return novo


def transferir_caso(con, caso_id, u, para_user_id, correlacao=None):
    _pessoa(u)
    c = caso(con, caso_id)
    if c["estado"] != "HUMAN_ACTIVE":
        raise ErroAtendimento("Só caso em atendimento pode ser transferido.", 409)
    if c["responsavel_id"] != u["id"] and not _gerente(u):
        raise ErroAtendimento("Só quem está atendendo (ou um gerente) transfere o caso.", 403)
    destino = um(con, "SELECT id, name, role, active FROM users WHERE id=?", (para_user_id,))
    from command_center.api import auth
    if not destino or not destino["active"] or not auth.pode(destino["role"], "OPERATOR"):
        raise ErroAtendimento("Transfira para uma pessoa ativa que atende (operador ou acima).")
    if destino["id"] == c["responsavel_id"]:
        raise ErroAtendimento("O caso já está com essa pessoa.", 409)
    cur = con.execute("UPDATE handoff_casos SET responsavel_id=?, atualizado_em=? WHERE id=? AND estado='HUMAN_ACTIVE' "
                      "AND responsavel_id IS ?", (destino["id"], agora(), c["id"], c["responsavel_id"]))
    if cur.rowcount != 1:
        raise ErroAtendimento("O caso mudou enquanto você olhava. Recarregue.", 409)
    ator, nome = _ator(u)
    _evento(con, c["id"], "transferido", ator, nome, de="HUMAN_ACTIVE", para="HUMAN_ACTIVE",
            detalhe={"de_user": c["responsavel_id"], "para_user": destino["id"]}, correlacao=correlacao)
    auditar(con, "handoff.transferido", ator, user_id=u["id"], entity_type="handoff_caso", entity_id=c["id"],
            detail={"de_user": c["responsavel_id"], "para_user": destino["id"]})
    novo = caso(con, c["id"])
    enfileirar_avisos(con, novo, "transferencia", so_user=destino["id"])
    processar_fila(con, caso_id=c["id"])
    return novo


def _fechar(con, caso_id, u, para, texto, campo_texto, tipo, correlacao=None):
    _pessoa(u)
    c = caso(con, caso_id)
    if c["estado"] != "HUMAN_ACTIVE":
        raise ErroAtendimento("Assuma o caso antes de encerrar ou devolver (ele está "
                              f"{c['estado']}).", 409)
    if c["responsavel_id"] != u["id"] and not _gerente(u):
        raise ErroAtendimento("Só quem está atendendo (ou um gerente) encerra ou devolve o caso.", 403)
    if c["ponte_pendente"]:
        raise ErroAtendimento("Já existe uma mudança esperando a ponte confirmar. Aguarde.", 409)
    texto = _limpo(texto, 1500)
    if not texto:
        raise ErroAtendimento("Escreva o resultado do atendimento." if para == "RESOLVED"
                              else "Escreva o contexto que a IA precisa para continuar.")
    # A ponte confirma ANTES da trava sair. Sem confirmação o caso continua com a pessoa:
    # errar para o lado do humano custa espera; errar para o lado da IA custa uma resposta
    # automática no meio de um atendimento.
    ok, erro = sincronizar_ponte(c, para, texto, u)
    if ok:
        novo = _mudar_estado(con, c, "HUMAN_ACTIVE", para,
                             {campo_texto: texto, "fechado_em": agora(), "fechado_por": u["id"],
                              "ponte_pendente": None, "ponte_erro": None}, tipo, u, correlacao=correlacao)
        destravar_ia(novo)
        _evento(con, c["id"], "ia_destravada", "sistema")
        return novo, None
    con.execute("UPDATE handoff_casos SET ponte_pendente=?, ponte_erro=?, ponte_tentativas=ponte_tentativas+1, "
                f"{campo_texto}=?, fechado_por=?, atualizado_em=? WHERE id=? AND estado='HUMAN_ACTIVE'",
                (para, (erro or "")[:300], texto, u["id"], agora(), c["id"]))
    ator, nome = _ator(u)
    _evento(con, c["id"], "ponte_pendente", ator, nome, de="HUMAN_ACTIVE", para=para,
            detalhe={"erro": (erro or "")[:200]}, correlacao=correlacao)
    return caso(con, c["id"]), erro


def encerrar_caso(con, caso_id, u, resultado, correlacao=None):
    return _fechar(con, caso_id, u, "RESOLVED", resultado, "resultado", "resolvido", correlacao)


def devolver_caso(con, caso_id, u, nota, correlacao=None):
    return _fechar(con, caso_id, u, "RETURNED_TO_AI", nota, "nota_devolucao", "devolvido_ia", correlacao)


# --------------------------------------------------------------------- a ponte (sales-bridge)
def sincronizar_ponte(c, para, nota, u, timeout=8):
    """Diz à ponte o novo estado da conversa. Devolve (ok, erro).

    Sem HANDOFF_PONTE_URL não há ponte para avisar (a conversa não passa por ela): a trava do
    arquivo é tudo, e soltar a trava basta."""
    url = cfg("HANDOFF_PONTE_URL")
    if not url:
        return True, None
    token = cfg("HANDOFF_PONTE_TOKEN")
    if not token:
        return False, "HANDOFF_PONTE_TOKEN não configurado: a ponte recusaria"
    corpo = {"lead_id": c["kommo_lead_id"], "estado": para, "caso_id": c["id"], "nota": nota or "",
             "autor": ((u or {}).get("name") or "equipe")[:80]}
    req = urllib.request.Request(url.rstrip("/") + "/handoff/estado", data=json.dumps(corpo).encode(),
                                 method="POST", headers={"Content-Type": "application/json",
                                                         "X-Handoff-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return False, f"ponte respondeu {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"ponte fora do ar: {getattr(e, 'reason', e)}"[:200]
    if not dados.get("ok"):
        return False, str(dados.get("erro") or "a ponte recusou a transição")[:200]
    return True, None


def _avisar_ponte_em_fundo(con, c, para, nota, u):
    """Assumir não depende da ponte (a trava já está no arquivo); avisar é para o estado dela
    acompanhar. Prazo curto (ponte travada não prende o clique) e falha só registrada."""
    ok, erro = sincronizar_ponte(c, para, nota, u, timeout=3)
    if not ok:
        _evento(con, c["id"], "ponte_aviso_falhou", "sistema", detalhe={"para": para, "erro": (erro or "")[:200]})


def sincronizar_pendentes(con):
    """O laço repete as devoluções/encerramentos que a ponte ainda não confirmou."""
    feitos = []
    for c in todos(con, "SELECT * FROM handoff_casos WHERE ponte_pendente IS NOT NULL AND estado='HUMAN_ACTIVE'"):
        para = c["ponte_pendente"]
        texto = c["resultado"] if para == "RESOLVED" else c["nota_devolucao"]
        quem = um(con, "SELECT id, name, email, role FROM users WHERE id=?", (c["fechado_por"],)) or {"id": None}
        ok, erro = sincronizar_ponte(c, para, texto, quem)
        if not ok:
            con.execute("UPDATE handoff_casos SET ponte_erro=?, ponte_tentativas=ponte_tentativas+1 WHERE id=?",
                        ((erro or "")[:300], c["id"]))
            continue
        cur = con.execute("UPDATE handoff_casos SET estado=?, fechado_em=?, ponte_pendente=NULL, ponte_erro=NULL, "
                          "atualizado_em=? WHERE id=? AND estado='HUMAN_ACTIVE' AND ponte_pendente=?",
                          (para, agora(), agora(), c["id"], para))
        if cur.rowcount == 1:
            tipo = "resolvido" if para == "RESOLVED" else "devolvido_ia"
            _evento(con, c["id"], tipo, "sistema", "ponte confirmou depois", de="HUMAN_ACTIVE", para=para,
                    detalhe={"tentativas": c["ponte_tentativas"] + 1})
            destravar_ia(caso(con, c["id"]))
            _evento(con, c["id"], "ia_destravada", "sistema")
            feitos.append(c["id"])
    return feitos


# --------------------------------------------------------------------- avisos
def _destinatarios_push(con):
    """Quem atende cliente: operador, gerente e admin, ativos e sem cargo de box (mecânico e
    coach têm cargo e não atendem conversa)."""
    return [r["id"] for r in todos(con, "SELECT id FROM users WHERE active=1 AND role IN ('ADMIN','MANAGER','OPERATOR') "
                                        "AND (cargo IS NULL OR cargo='') ORDER BY id")]


def _canal_equipe(con):
    from command_center.api.equipe import garantir_canal
    cid = garantir_canal(con, "EQUIPE", entity_type="handoff_fila", entity_id=1, name="Atendimento humano")
    for uid in _destinatarios_push(con):
        con.execute("INSERT OR IGNORE INTO team_members (channel_id, user_id) VALUES (?,?)", (cid, uid))
    return cid


def texto_aviso(c, tipo="abertura"):
    cab = {"abertura": "[URACE IA · ATENDIMENTO HUMANO]", "realerta": "[URACE IA · ATENDIMENTO HUMANO · AINDA SEM RESPONSÁVEL]",
           "atrasado": "[URACE IA · ATENDIMENTO HUMANO · ATRASADO]",
           "transferencia": "[URACE IA · ATENDIMENTO HUMANO · TRANSFERIDO PARA VOCÊ]",
           "nova_mensagem": "[URACE IA · ATENDIMENTO HUMANO · O CLIENTE ESCREVEU]"}.get(tipo, "[URACE IA · ATENDIMENTO HUMANO]")
    linhas = [cab, "",
              f"Prioridade: {c['prioridade'].upper()}",
              f"Cliente: {c['cliente_nome'] or 'sem nome no Kommo'}",
              f"Conversa: {c['conversa']}" + (f" ({c['canal']})" if c.get("canal") else ""),
              f"Motivo: {MOTIVOS.get(c['motivo'], c['motivo'])}" + (f" — {c['motivo_texto']}" if c.get("motivo_texto") else "")]
    if c.get("resumo"):
        linhas.append(f"Resumo: {c['resumo']}")
    if c.get("acao_pedida"):
        linhas.append(f"Ação pedida: {c['acao_pedida']}")
    linhas += [f"Abrir: {_url_publica()}/ops/atendimento/{c['id']}",
               f"Kommo: https://urace.kommo.com/leads/detail/{c['kommo_lead_id']}",
               f"Status: {c['estado']}"]
    return "\n".join(linhas)


def enfileirar_avisos(con, c, tipo, numero=0, so_user=None, so_registro=False):
    """Uma linha por destino, com chave única. Repetir esta chamada não duplica nada."""
    sufixo = f"{tipo}:{numero}"
    agora_ = agora()
    usuarios = [] if so_registro else ([so_user] if so_user else _destinatarios_push(con))
    for uid in usuarios:
        con.execute("INSERT OR IGNORE INTO handoff_notificacoes (caso_id, tipo, canal, destino, chave, proxima_em) "
                    "VALUES (?,?,?,?,?,?)", (c["id"], tipo, "push", f"user:{uid}", f"{c['id']}:{sufixo}:push:{uid}", agora_))
    if so_user:
        return
    cid = _canal_equipe(con)
    con.execute("INSERT OR IGNORE INTO handoff_notificacoes (caso_id, tipo, canal, destino, chave, proxima_em) "
                "VALUES (?,?,?,?,?,?)", (c["id"], tipo, "equipe", f"canal:{cid}", f"{c['id']}:{sufixo}:equipe:{cid}", agora_))
    if so_registro:
        return
    for ct in todos(con, "SELECT id FROM team_contacts WHERE active=1 AND recebe_handoff=1 ORDER BY id"):
        con.execute("INSERT OR IGNORE INTO handoff_notificacoes (caso_id, tipo, canal, destino, chave, proxima_em) "
                    "VALUES (?,?,?,?,?,?)", (c["id"], tipo, "whatsapp", f"contato:{ct['id']}",
                                             f"{c['id']}:{sufixo}:whatsapp:{ct['id']}", agora_))


def _marcar(con, nid, status, erro=None, external_id=None, reagendar_min=None):
    proxima = _iso(_agora_dt() + timedelta(minutes=reagendar_min)) if reagendar_min else None
    con.execute("UPDATE handoff_notificacoes SET status=?, erro=?, external_id=COALESCE(?, external_id), "
                "proxima_em=?, enviado_em=CASE WHEN ? IN ('enviado','entregue','lido') THEN ? ELSE enviado_em END "
                "WHERE id=?", (status, (erro or None) and str(erro)[:300], external_id, proxima, status, agora(), nid))


def _enviar_push(con, n, c, texto):
    from command_center.api import push
    uid = int(n["destino"].split(":", 1)[1])
    titulo = {"abertura": "Atendimento humano", "transferencia": "Atendimento transferido para você",
              "nova_mensagem": "O cliente escreveu de novo"}.get(
        n["tipo"], "Atendimento humano esperando")
    corpo = f"{c['prioridade'].upper()} · {c['cliente_nome'] or 'cliente'} · {MOTIVOS.get(c['motivo'], c['motivo'])}"
    r = push.avisar(con, [uid], titulo, corpo, f"/ops/atendimento/{c['id']}")
    if r.get("enviados"):
        return "enviado", None, None
    if r.get("motivo") == "push não está pronto neste servidor":
        return "bloqueado", r["motivo"], None
    if not r.get("aparelhos"):
        return "bloqueado", "a pessoa não ativou o aviso no celular (Equipe → ativar notificações)", None
    return "falhou", "nenhum aparelho aceitou o aviso", None


def _enviar_equipe(con, n, c, texto):
    from command_center.api.equipe import guardar_mensagem
    cid = int(n["destino"].split(":", 1)[1])
    guardar_mensagem(con, cid, texto, "URACE IA", origem="atendimento", external_id=n["chave"])
    return "enviado", None, None


def _enviar_whatsapp(con, n, c, texto):
    """WhatsApp oficial (Cloud API, número da EQUIPE — nunca o número dos clientes, que vive no
    Kommo). Dentro da janela de 24 h vai texto; fora, só template aprovado pela Meta."""
    from command_center.api.whatsapp import _dentro_da_janela
    from command_center.providers import whatsapp as wa
    ct = um(con, "SELECT * FROM team_contacts WHERE id=? AND active=1", (int(n["destino"].split(":", 1)[1]),))
    if not ct or not ct.get("recebe_handoff"):
        return "desistiu", "contato inativo ou não recebe mais avisos de atendimento", None
    if not wa.aplicar():
        return "simulado", "WhatsApp oficial em simulação: falta configurar o número da equipe (WA_TOKEN, WA_PHONE_NUMBER_ID) ou WA_APLICAR=1", None
    if _dentro_da_janela(ct["last_inbound_at"]):
        r = wa.enviar_texto(ct["phone"], texto)
    elif cfg("WA_TEMPLATE_HANDOFF"):
        r = wa.enviar_template(ct["phone"], cfg("WA_TEMPLATE_HANDOFF"), cfg("WA_TEMPLATE_HANDOFF_IDIOMA", "pt_BR"),
                               [c["prioridade"].upper(), c["cliente_nome"] or "cliente",
                                MOTIVOS.get(c["motivo"], c["motivo"]), f"{_url_publica()}/ops/atendimento/{c['id']}"])
    else:
        return "bloqueado", (f"{ct['name']} não escreve para o número da equipe há mais de 24 h e não há template "
                             "aprovado (WA_TEMPLATE_HANDOFF): a Meta não deixa mandar texto livre."), None
    if r.get("simulado"):
        return "simulado", "WhatsApp oficial em simulação", None
    return "enviado", None, r.get("id")


_ENVIOS = {"push": _enviar_push, "equipe": _enviar_equipe, "whatsapp": _enviar_whatsapp}


def processar_fila(con, caso_id=None, limite=50):
    """Tenta o que está pendente e na hora. Falha passageira volta com espera crescente
    (1, 2, 4, 8 min); depois de TENTATIVAS_MAX, desiste e fica vermelho."""
    filtro, params = "", [agora()]
    if caso_id:
        filtro, params = " AND n.caso_id=?", [agora(), caso_id]
    pend = todos(con, f"""SELECT n.* FROM handoff_notificacoes n WHERE n.status='pendente'
                          AND (n.proxima_em IS NULL OR n.proxima_em<=?){filtro} ORDER BY n.id LIMIT {int(limite)}""",
                 tuple(params))
    resultado = {"enviados": 0, "falhas": 0, "outros": 0}
    for n in pend:
        # reivindica a linha: dois laços (ou o laço e a rota) não mandam o mesmo aviso
        cur = con.execute("UPDATE handoff_notificacoes SET tentativas=tentativas+1, proxima_em=? "
                          "WHERE id=? AND status='pendente' AND tentativas=?",
                          (_iso(_agora_dt() + timedelta(minutes=5)), n["id"], n["tentativas"]))
        if cur.rowcount != 1:
            continue
        c = caso(con, n["caso_id"])
        if c["estado"] not in ABERTOS:
            _marcar(con, n["id"], "desistiu", "o caso já foi fechado antes do aviso sair")
            continue
        try:
            status, erro, ext = _ENVIOS[n["canal"]](con, n, c, texto_aviso(c, n["tipo"]))
        except Exception as e:                                   # noqa: BLE001
            status, erro, ext = "falhou", str(e)[:300], None
        if status == "falhou":
            if n["tentativas"] + 1 >= TENTATIVAS_MAX:
                _marcar(con, n["id"], "desistiu", f"{erro} (desistiu depois de {TENTATIVAS_MAX} tentativas)")
            else:
                _marcar(con, n["id"], "pendente", erro, reagendar_min=2 ** n["tentativas"])
            resultado["falhas"] += 1
        else:
            _marcar(con, n["id"], status, erro, ext)
            resultado["enviados" if status == "enviado" else "outros"] += 1
    return resultado


def registrar_status_whatsapp(con, wamid, novo, erro=None):
    """O recibo da Meta (webhook) chega para os avisos também, não só para o chat da equipe."""
    if not wamid or novo not in ("enviado", "entregue", "lido", "falhou"):
        return 0
    ordem = "CASE status WHEN 'lido' THEN 3 WHEN 'entregue' THEN 2 WHEN 'enviado' THEN 1 ELSE 0 END"
    peso = {"enviado": 1, "entregue": 2, "lido": 3, "falhou": 9}[novo]
    cur = con.execute(f"UPDATE handoff_notificacoes SET status=?, erro=COALESCE(?, erro) WHERE canal='whatsapp' "
                      f"AND external_id=? AND ({ordem} < ? OR ?=9)", (novo, erro, wamid, peso, peso))
    return cur.rowcount or 0


COOLDOWN_CLIENTE_MIN = 10


def cliente_escreveu(con, kommo_lead_id):
    """Mensagem nova do cliente numa conversa com caso aberto (vista pelo hook/webhook do Kommo
    no painel — funciona mesmo com a ponte desligada). Quem está atendendo recebe um push; caso
    ainda sem ninguém só ganha o registro (o re-aviso de atraso cuida de chamar). Um aviso a cada
    COOLDOWN_CLIENTE_MIN por caso: cliente mandando cinco mensagens seguidas é um aviso só."""
    try:
        lead = int(kommo_lead_id)
    except (TypeError, ValueError):
        return None
    c = caso_aberto(con, lead)
    if not c:
        return None
    corte = _iso(_agora_dt() - timedelta(minutes=COOLDOWN_CLIENTE_MIN))
    if um(con, "SELECT 1 AS x FROM handoff_eventos WHERE caso_id=? AND tipo='cliente_escreveu' AND em>?", (c["id"], corte)):
        return c["id"]
    n = um(con, "SELECT COUNT(*) AS n FROM handoff_eventos WHERE caso_id=? AND tipo='cliente_escreveu'", (c["id"],))["n"] + 1
    _evento(con, c["id"], "cliente_escreveu", "kommo", detalhe={"n": n})
    if c["estado"] == "HUMAN_ACTIVE" and c["responsavel_id"]:
        enfileirar_avisos(con, c, "nova_mensagem", numero=n, so_user=c["responsavel_id"])
        processar_fila(con, caso_id=c["id"])
    return c["id"]


def varrer_atrasos(con, quando=None):
    """Caso pendente que passou do prazo: re-aviso a cada REALERTA_MIN, até o teto. Prioridade
    alta/urgente avisa a qualquer hora; normal/baixa espera o horário humano."""
    momento = quando or _agora_dt()
    limite = _iso(momento - timedelta(minutes=REALERTA_MIN))
    feitos = []
    for c in todos(con, "SELECT * FROM handoff_casos WHERE estado='HUMAN_PENDING' AND prazo_em<=? AND realertas<? "
                        "AND (ultimo_realerta IS NULL OR ultimo_realerta<=?)",
                   (_iso(momento), TETO_REALERTAS, limite)):
        if c["prioridade"] in ("normal", "baixa") and not horario_humano(momento):
            continue
        n = c["realertas"] + 1
        cur = con.execute("UPDATE handoff_casos SET realertas=?, ultimo_realerta=? WHERE id=? AND realertas=?",
                          (n, _iso(momento), c["id"], c["realertas"]))
        if cur.rowcount != 1:
            continue
        _evento(con, c["id"], "atrasado", "sistema", detalhe={"realerta": n})
        enfileirar_avisos(con, c, "atrasado", numero=n)
        feitos.append(c["id"])
    return feitos


def limpar_retencao(con, dias=None):
    """Caso encerrado há mais de N dias perde o texto (resumo, motivo, resultado, nome). Fica o
    esqueleto: datas, estados, quem atendeu — o suficiente para métrica, sem dado de cliente."""
    dias = int(dias or cfg("HANDOFF_RETENCAO_DIAS", "365") or 365)
    corte = _iso(_agora_dt() - timedelta(days=dias))
    cur = con.execute(f"""UPDATE handoff_casos SET resumo=NULL, motivo_texto=NULL, acao_pedida=NULL, resultado=NULL,
                          nota_devolucao=NULL, cliente_nome=NULL WHERE estado IN ({_ph(FECHADOS)}) AND fechado_em<?
                          AND (resumo IS NOT NULL OR cliente_nome IS NOT NULL OR resultado IS NOT NULL)""",
                      (*FECHADOS, corte))
    return cur.rowcount or 0


def ciclo(con):
    """Uma volta do laço (a cada meio minuto, junto do laço do chat)."""
    return {"pausas": reconciliar_pausas(con), "ponte": sincronizar_pendentes(con),
            "atrasos": varrer_atrasos(con), "fila": processar_fila(con)}


# --------------------------------------------------------------------- leitura
def _publico(con, c, agora_dt=None):
    agora_dt = agora_dt or _agora_dt()
    d = dict(c)
    prazo = _dt(c.get("prazo_em"))
    d["atrasado"] = c["estado"] == "HUMAN_PENDING" and bool(prazo and prazo <= agora_dt)
    d["sem_responsavel"] = c["estado"] in ABERTOS and not c.get("responsavel_id")
    d["motivo_rotulo"] = MOTIVOS.get(c["motivo"], c["motivo"])
    d["kommo_url"] = f"https://urace.kommo.com/leads/detail/{c['kommo_lead_id']}"
    d["espera_min"] = int(((_dt(c.get("assumido_em")) or agora_dt) - (_dt(c["criado_em"]) or agora_dt)).total_seconds() // 60)
    if c.get("responsavel_id"):
        r = um(con, "SELECT name FROM users WHERE id=?", (c["responsavel_id"],))
        d["responsavel_nome"] = r["name"] if r else None
    else:
        d["responsavel_nome"] = None
    return d


FILTROS = ("pendentes", "em_atendimento", "atrasados", "sem_responsavel", "resolvidos", "abertos", "todos")


def listar(con, filtro="abertos", limit=50, offset=0, kommo_lead_id=None):
    if filtro not in FILTROS:
        raise ErroAtendimento(f"filtro inválido: use {', '.join(FILTROS)}.")
    agora_iso = agora()
    where = {
        "pendentes": ("estado='HUMAN_PENDING'", ()),
        "em_atendimento": ("estado='HUMAN_ACTIVE'", ()),
        "atrasados": ("estado='HUMAN_PENDING' AND prazo_em<=?", (agora_iso,)),
        "sem_responsavel": (f"estado IN ({_ph(ABERTOS)}) AND responsavel_id IS NULL", ABERTOS),
        "resolvidos": (f"estado IN ({_ph(FECHADOS)})", FECHADOS),
        "abertos": (f"estado IN ({_ph(ABERTOS)})", ABERTOS),
        "todos": ("1=1", ()),
    }[filtro]
    cond, params = where
    if kommo_lead_id:
        cond += " AND kommo_lead_id=?"
        params = (*params, int(kommo_lead_id))
    ordem = "fechado_em DESC" if filtro == "resolvidos" else \
        "CASE prioridade WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, criado_em"
    total = um(con, f"SELECT COUNT(*) AS n FROM handoff_casos WHERE {cond}", params)["n"]
    linhas = todos(con, f"SELECT * FROM handoff_casos WHERE {cond} ORDER BY {ordem} LIMIT ? OFFSET ?",
                   (*params, max(1, min(int(limit), 200)), max(0, int(offset))))
    agora_dt = _agora_dt()
    return {"itens": [_publico(con, c, agora_dt) for c in linhas], "total": total, "contagem": contagem(con)}


def contagem(con):
    agora_iso = agora()
    r = um(con, f"""SELECT
        SUM(estado='HUMAN_PENDING') AS pendentes,
        SUM(estado='HUMAN_ACTIVE') AS em_atendimento,
        SUM(estado='HUMAN_PENDING' AND prazo_em<=?) AS atrasados,
        SUM(estado IN ({_ph(ABERTOS)}) AND responsavel_id IS NULL) AS sem_responsavel,
        SUM(estado IN ({_ph(FECHADOS)})) AS resolvidos
        FROM handoff_casos""", (agora_iso, *ABERTOS, *FECHADOS))
    return {k: int(v or 0) for k, v in (r or {}).items()}


def detalhe(con, caso_id):
    c = _publico(con, caso(con, caso_id))
    c["eventos"] = todos(con, "SELECT id, tipo, de_estado, para_estado, ator, ator_nome, detalhe, correlacao, em "
                              "FROM handoff_eventos WHERE caso_id=? ORDER BY id", (caso_id,))
    for e in c["eventos"]:
        try:
            e["detalhe"] = json.loads(e["detalhe"]) if e["detalhe"] else None
        except ValueError:
            pass
    c["avisos"] = todos(con, "SELECT id, tipo, canal, destino, status, tentativas, erro, criado_em, enviado_em "
                             "FROM handoff_notificacoes WHERE caso_id=? ORDER BY id", (caso_id,))
    c["ia_bloqueada"] = ia_travada(c["kommo_lead_id"])
    c["historico"] = todos(con, "SELECT id, estado, motivo, criado_em, fechado_em FROM handoff_casos "
                                "WHERE kommo_lead_id=? AND id<>? ORDER BY id DESC LIMIT 20", (c["kommo_lead_id"], caso_id))
    return c


def saude(con):
    """Para o /health e a tela: fila parada, aviso morto, ponte devendo confirmação."""
    pend = um(con, "SELECT COUNT(*) AS n, MIN(criado_em) AS mais_velho FROM handoff_notificacoes WHERE status='pendente'")
    return {"casos": contagem(con), "avisos_pendentes": pend["n"], "aviso_pendente_desde": pend["mais_velho"],
            "avisos_desistidos_24h": um(con, "SELECT COUNT(*) AS n FROM handoff_notificacoes WHERE status IN ('desistiu','falhou') "
                                             "AND criado_em>=strftime('%Y-%m-%dT%H:%M:%fZ','now','-1 day')")["n"],
            "ponte_pendente": um(con, "SELECT COUNT(*) AS n FROM handoff_casos WHERE ponte_pendente IS NOT NULL")["n"],
            "ponte_configurada": bool(cfg("HANDOFF_PONTE_URL")),
            "whatsapp_template": bool(cfg("WA_TEMPLATE_HANDOFF"))}
