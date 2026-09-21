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

**Dois limites, ditos na cara:** a API de notas do Kommo nem sempre traz o texto das
mensagens de chat (aí o casamento é só por tempo), e o que é anterior à integração não
vem pela API. Por isso a conferência olha uma janela recente e diz quantas linhas de
cada lado ficaram sem texto — o que não dá para afirmar, ela não afirma.

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


def conferir_lead(con, lead, ler=None, desde=None):
    """Um lead: o que está só no Kommo, o que está só no painel, e o que não deu para dizer."""
    ler = ler or _ler_do_kommo
    try:
        bruto = ler(lead["external_id"]) or []
    except Exception as e:                                        # noqa: BLE001
        return {"lead": lead, "erro": str(e)[:200], "nao_chegou": [], "nao_foi": [], "confere": 0,
                "sem_texto_kommo": 0, "pendentes": []}
    corte = _segundos(desde)
    kommo = [k for k in bruto if k.get("direcao") in DIRECOES
             and (corte is None or (_segundos(k.get("em")) or 0) >= corte)]
    painel = [dict(m) for m in todos(con, """SELECT id, direction, text, at, status, author, source
                                             FROM crm_messages WHERE lead_id=? AND direction IN ('entrada','saida')
                                             ORDER BY at""", (lead["id"],))
              if corte is None or (_segundos(m["at"]) or 0) >= corte]
    pares, so_kommo, so_painel = _casa(kommo, painel)
    # o que o painel sabe que não saiu já está marcado: não depende de conferência
    pendentes = [p for p in painel if p["direction"] == "saida" and p["status"] in ("queued", "sending", "failed")]
    ids_pendentes = {p["id"] for p in pendentes}
    return {
        "lead": lead,
        "erro": None,
        # cliente falou no Kommo e o painel não tem: não chegou
        "nao_chegou": [k for k in so_kommo if k["direcao"] == "entrada"],
        # o painel diz que respondeu (e deu por entregue) e o Kommo não tem: não foi
        "nao_foi": [p for p in so_painel if p["direction"] == "saida"
                    and p["status"] == "sent" and p["id"] not in ids_pendentes],
        "pendentes": pendentes,
        "confere": len(pares),
        "sem_texto_kommo": sum(1 for k in kommo if not _limpo(k.get("texto"))),
    }


def conferir(con, dias=7, maximo_leads=40, ler=None):
    """Os leads com conversa nos últimos `dias`, um a um. Não escreve nada."""
    from datetime import datetime, timedelta, timezone
    desde = (datetime.now(timezone.utc) - timedelta(days=int(dias))).strftime("%Y-%m-%dT%H:%M:%SZ")
    leads = todos(con, """SELECT id, external_id, name, source, link FROM crm_leads
                          WHERE COALESCE(last_message_at, synced_at) >= ?
                          ORDER BY COALESCE(last_message_at, synced_at) DESC LIMIT ?""", (desde, int(maximo_leads)))
    saida = [conferir_lead(con, dict(l), ler=ler, desde=desde) for l in leads]
    return {"desde": desde, "leads": saida,
            "nao_chegou": sum(len(r["nao_chegou"]) for r in saida),
            "nao_foi": sum(len(r["nao_foi"]) for r in saida),
            "pendentes": sum(len(r["pendentes"]) for r in saida),
            "erros": sum(1 for r in saida if r["erro"])}
