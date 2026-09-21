"""Conferência do chat: o que o Kommo tem × o que o painel guardou.

Pergunta do dono em 21/09, depois de descobrir que uma resposta dele se perdeu:
*"tem como identificar quais mensagens que não foram e quais não chegaram?"*. Tem —
não pela memória do painel, que é justamente o lado que pode estar faltando, mas
confrontando os dois lados:

* **não foi**: o painel diz que respondeu, e no Kommo aquela mensagem não existe.
* **não chegou**: o Kommo tem a mensagem do cliente, e o painel não guardou.

O casamento é por **direção e tempo** (±3 min), com o texto como desempate quando os
dois lados têm texto. Não é por id: a mesma mensagem tem id diferente em cada caminho
(nota do Kommo, id da mensagem no webhook, marca da sincronia) — foi isso que deixou a
conversa em dobro até 21/09.

**A regra que vale mais que tudo aqui: só acusa na direção em que enxerga.** Na primeira
versão (21/09, manhã) ela apontou quatro respostas como "não foi" — e a conversa daqueles
leads vinha VAZIA do Kommo. Acusar com base em lista vazia é o pior defeito que uma
conferência pode ter. Agora: se o Kommo não devolve nada de um lead, o veredito é *não deu
para conferir*; se devolve mensagens mas nenhuma nossa, as respostas daquele lead ficam em
*não dá para dizer* — nunca em "não foi".

**Duas fontes, porque nenhuma basta sozinha:** as notas do lead (`kommo_conversa`, traz
texto quando tem) e os eventos de conversa da conta (`kommo_chats`, sem texto, mas é o que
esta conta registra). A segunda entra só onde a primeira não cobre.

**Evento não é mensagem.** O evento do Kommo diz *"houve conversa nesta direção, a esta
hora"* — uma conversa respondida, não uma bolha. Quando o painel manda duas respostas
seguidas (11:24 "Hey Charles" e 11:24 "how are you?"), o Kommo registra UM evento para as
duas. Casar um-para-um com evento fez a conferência apontar a segunda como perdida, e o
print do Kommo mostrava as duas com ✓Delivered. Por isso, **um evento sem texto vale por
todas as mensagens da mesma direção dentro da janela**; só a nota com texto é
um-para-um.

**Dois limites:** a API do Kommo nem sempre traz o texto da mensagem de chat (aí o
casamento é só por tempo), e o que é anterior à integração não vem. Por isso a janela é
recente e o relatório conta quantas linhas ficaram sem texto.

Só leitura: não escreve no Kommo nem no banco.
"""
from command_center.db import todos

JANELA_S = 180                      # o mesmo minuto, com folga para o relógio dos dois lados
DIRECOES = ("entrada", "saida")


def _segundos(iso):
    """'2026-09-21T11:05:01.123Z' → epoch. Sem data utilizável → None."""
    from datetime import datetime, timezone
    if not iso:
        return None
    t = str(iso).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _limpo(t):
    return " ".join(str(t or "").split()).lower()


def _casa(kommo, painel):
    """Casa as duas listas (dicts com 'direcao'/'direction', 'texto'/'text', 'em'/'at').

    Guloso e em ordem de tempo: cada linha do Kommo leva a linha do painel mais próxima,
    da mesma direção, dentro da janela — texto igual tem preferência sobre só o tempo."""
    livres = list(range(len(painel)))
    pares, sobra_kommo = [], []
    for k in kommo:
        tk, txk = _segundos(k.get("em")), _limpo(k.get("texto"))
        melhor, melhor_nota = None, None
        for i in livres:
            p = painel[i]
            if p["direction"] != k["direcao"]:
                continue
            tp = _segundos(p["at"])
            if tk is None or tp is None or abs(tk - tp) > JANELA_S:
                continue
            txp = _limpo(p["text"])
            # nota menor ganha: texto igual primeiro, depois o mais perto no tempo
            nota = (0 if (txk and txp and txk == txp) else 1, abs(tk - tp))
            if txk and txp and txk != txp:
                continue                            # texto nos dois e diferente: não é a mesma
            if melhor_nota is None or nota < melhor_nota:
                melhor, melhor_nota = i, nota
        if melhor is None:
            sobra_kommo.append(k)
        else:
            livres.remove(melhor)
            pares.append((k, painel[melhor]))
    return pares, sobra_kommo, [painel[i] for i in livres]


def _ler_do_kommo(lead_externo, maximo=200):
    from command_center.providers import chamar
    return chamar("kommo", "kommo_conversa", lead_id=str(lead_externo), maximo=maximo)


def eventos_por_lead(dias=7, maximo=2000):
    """Eventos de conversa da conta, agrupados por lead. Sem texto — só direção e hora —,
    mas é o que esta conta registra quando a nota não existe. Falhou? `{}`: a conferência
    segue só com as notas e diz que enxergou menos."""
    from command_center.providers import chamar
    try:
        brutos = chamar("kommo", "kommo_chats", desde_dias=int(dias), maximo=int(maximo)) or []
    except Exception:                                             # noqa: BLE001
        return {}
    saida = {}
    for e in brutos:
        saida.setdefault(str(e.get("lead_id")), []).append(
            {"id": str(e.get("id")), "tipo": e.get("tipo") or "evento", "direcao": e.get("direcao"),
             "texto": "", "em": e.get("em"), "fonte": "evento"})
    return saida


def _lado_do_kommo(notas, eventos, corte):
    """Junta as duas fontes. O evento só entra onde não há nota da mesma direção por perto:
    as duas descrevem a mesma mensagem, e contar duas vezes inventaria conversa."""
    dentro = lambda x: corte is None or (_segundos(x.get("em")) or 0) >= corte          # noqa: E731
    itens = [dict(n, fonte=n.get("fonte") or "nota") for n in notas
             if n.get("direcao") in DIRECOES and dentro(n)]
    for ev in eventos or []:
        if ev.get("direcao") not in DIRECOES or not dentro(ev):
            continue
        te = _segundos(ev.get("em"))
        perto = any(i["direcao"] == ev["direcao"] and te is not None
                    and (_segundos(i.get("em")) or 0) and abs(_segundos(i["em"]) - te) <= JANELA_S
                    for i in itens)
        if not perto:
            itens.append(ev)
    itens.sort(key=lambda x: _segundos(x.get("em")) or 0)
    return itens


def _cobertos_por_evento(kommo, sobra):
    """Sobra do painel que um evento sem texto já explica. Devolve (cobertas, restantes).

    Sem isto, duas respostas no mesmo minuto viram uma entrega e uma acusação — e a
    acusação é falsa: o Kommo mostrava as duas entregues (provado no print de 21/09)."""
    marcos = [(k["direcao"], _segundos(k.get("em"))) for k in kommo
              if not _limpo(k.get("texto")) and _segundos(k.get("em")) is not None]
    cobertas, restantes = [], []
    for p in sobra:
        tp = _segundos(p["at"])
        if tp is not None and any(d == p["direction"] and abs(t - tp) <= JANELA_S for d, t in marcos):
            cobertas.append(p)
        else:
            restantes.append(p)
    return cobertas, restantes


def conferir_lead(con, lead, ler=None, desde=None, eventos=None):
    """Um lead: o que está só no Kommo, o que está só no painel, e o que não deu para dizer."""
    ler = ler or _ler_do_kommo
    try:
        bruto = ler(lead["external_id"]) or []
    except Exception as e:                                        # noqa: BLE001
        return {"lead": lead, "erro": str(e)[:200], "nao_chegou": [], "nao_foi": [], "confere": 0,
                "sem_texto_kommo": 0, "pendentes": [], "cego_saida": [], "sem_dados": True}
    corte = _segundos(desde)
    kommo = _lado_do_kommo(bruto, eventos, corte)
    painel = [dict(m) for m in todos(con, """SELECT id, direction, text, at, status, author, source
                                             FROM crm_messages WHERE lead_id=? AND direction IN ('entrada','saida')
                                             ORDER BY at""", (lead["id"],))
              if corte is None or (_segundos(m["at"]) or 0) >= corte]
    pares, so_kommo, so_painel = _casa(kommo, painel)
    # o que o painel sabe que não saiu já está marcado: não depende de conferência
    pendentes = [p for p in painel if p["direction"] == "saida" and p["status"] in ("queued", "sending", "failed")]
    ids_pendentes = {p["id"] for p in pendentes}
    sobrou_saida = [p for p in so_painel if p["direction"] == "saida"
                    and p["status"] == "sent" and p["id"] not in ids_pendentes]
    cobertas, sobrou_saida = _cobertos_por_evento(kommo, sobrou_saida)
    # A trava: só chama de "não foi" se este lado do Kommo provou que mostra resposta nossa.
    # Sem nenhuma saída visível, a ausência não diz nada — e silêncio não é prova.
    enxerga_saida = any(k["direcao"] == "saida" for k in kommo)
    return {
        "lead": lead,
        "erro": None,
        # cliente falou no Kommo e o painel não tem: não chegou (isto só dispara com dado na mão)
        "nao_chegou": [k for k in so_kommo if k["direcao"] == "entrada"],
        "nao_foi": sobrou_saida if enxerga_saida else [],
        "cego_saida": [] if enxerga_saida else sobrou_saida,
        "pendentes": pendentes,
        "confere": len(pares) + len(cobertas),
        "por_evento": len(cobertas),
        "sem_texto_kommo": sum(1 for k in kommo if not _limpo(k.get("texto"))),
        "sem_dados": not kommo,
    }


def conferir(con, dias=7, maximo_leads=40, ler=None, eventos=None):
    """Os leads com conversa nos últimos `dias`, um a um. Não escreve nada."""
    from datetime import datetime, timedelta, timezone
    desde = (datetime.now(timezone.utc) - timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%SZ")
    leads = todos(con, """SELECT id, external_id, name, source, link FROM crm_leads
                          WHERE COALESCE(last_message_at, synced_at) >= ?
                          ORDER BY COALESCE(last_message_at, synced_at) DESC LIMIT ?""", (desde, int(maximo_leads)))
    por_lead = eventos if eventos is not None else eventos_por_lead(dias=dias)
    saida = [conferir_lead(con, dict(l), ler=ler, desde=desde,
                           eventos=por_lead.get(str(l["external_id"]), [])) for l in leads]
    return {"desde": desde, "leads": saida, "eventos": sum(len(v) for v in por_lead.values()),
            "nao_chegou": sum(len(r["nao_chegou"]) for r in saida),
            "nao_foi": sum(len(r["nao_foi"]) for r in saida),
            "cego_saida": sum(len(r["cego_saida"]) for r in saida),
            "sem_dados": sum(1 for r in saida if r.get("sem_dados") and not r["erro"]),
            "pendentes": sum(len(r["pendentes"]) for r in saida),
            "erros": sum(1 for r in saida if r["erro"])}
