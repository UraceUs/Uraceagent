"""Execução real das diretivas `[[...]]` que o agente anexa às respostas.

Até aqui, a ponte só REMOVIA as diretivas (textproc.py) antes de mandar a
resposta ao cliente — quem de fato acionava CRM/escalação eram os endpoints
HTTP dedicados (`/tools/*`), pensados para chamada externa. Este módulo
interpreta e executa as diretivas que o próprio modelo anexa ao texto da
conversa, no mesmo fluxo — a peça que faltava do protocolo descrito em
`instructions/urace-sales-agent.md`, seção "System protocol".

`[[followup ...]]` agenda no scheduler da ponte (trilha `scheduled`) E cria
a tarefa no Kommo (B3, visibilidade humana) — desde 21/08 o agendador
dispara a mensagem sozinho (ver scheduler.py).
"""
import datetime
import re
import time

import config
import gates
import kommo_client as kommo
import state

_DIRECTIVE_RE = re.compile(r"\[\[(\w+)([^\]]*)\]\]", re.DOTALL)
_KV_RE = re.compile(r'(\w+)=("[^"]*"|\S+)')

_DUE_RE = re.compile(r"^\+(\d+)(min|h|d)$")
_DUE_UNIT_SECONDS = {"min": 60, "h": 3600, "d": 86400}


def parse(raw_directives: list[str]) -> list[tuple[str, dict]]:
    """Converte blocos "[[name k=v k2="v2"]]" em (name, {k: v, ...})."""
    parsed = []
    for block in raw_directives:
        m = _DIRECTIVE_RE.match(block.strip())
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        kwargs = {}
        for km in _KV_RE.finditer(rest):
            key, val = km.group(1), km.group(2)
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            kwargs[key] = val
        parsed.append((name, kwargs))
    return parsed


def parse_due(due: str) -> int:
    """'+2h' / '+24h' / '+3d' / '+7d' / '+10min' -> timestamp unix. Aceita
    também uma data ISO explícita. Sem valor reconhecível: +1d (nunca deixa
    uma tarefa sem due date -- B3)."""
    due = (due or "").strip()
    m = _DUE_RE.match(due)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return int(time.time()) + n * _DUE_UNIT_SECONDS[unit]
    try:
        return int(datetime.datetime.fromisoformat(due).timestamp())
    except ValueError:
        return int(time.time()) + 86400


# -------------------------------------------------------- ações por diretiva
def apply_qualify(lead_id: int, kwargs: dict) -> dict:
    """Mesma lógica usada pelo endpoint /tools/qualify -- reaproveitada aqui
    para que uma diretiva no meio da conversa tenha exatamente o mesmo
    efeito que uma chamada HTTP explícita. Devolve {'escalate': bool} --
    G2 (competidor -> Italo, sempre) não pode depender só do modelo lembrar
    de mandar [[escalate]] também."""
    fields = {}
    if kwargs.get("experience") in ("new", "first_time", "rental_only", "recreational",
                                     "raced_before", "competes"):
        fields["q_experience"] = kwargs["experience"]
    if kwargs.get("origin") in ("local", "traveler"):
        fields["q_origin"] = kwargs["origin"]
    if kwargs.get("age") is not None:
        try:
            fields["driver_age"] = int(kwargs["age"])
        except ValueError:
            pass
    if fields:
        state.update_conversation(lead_id, **fields)
    return {"escalate": fields.get("q_experience") == "competes"}


def apply_crm(lead_id: int, kwargs: dict) -> None:
    op = kwargs.get("op")
    if op == "note" and kwargs.get("text"):
        kommo.add_note(lead_id, kwargs["text"])
    elif op == "tags" and kwargs.get("tags"):
        tags = [t.strip() for t in kwargs["tags"].split(",") if t.strip()]
        if tags:
            kommo.add_tags(lead_id, tags)
    elif op == "task" and kwargs.get("text"):
        kommo.add_task(lead_id, kwargs["text"], parse_due(kwargs.get("due", "")))
    elif op == "stage" and kwargs.get("stage"):
        stage_key = kwargs["stage"]
        if stage_key in ("closed_won", "suppliers"):  # G9 + never_touch
            state.log("gate", lead_id, f"G9: estágio {stage_key} recusado (diretiva do modelo)")
            return
        stage_id = config.STAGES.get(stage_key)
        if stage_id:
            kommo.set_stage(lead_id, stage_id)
        else:
            state.log("error", lead_id, f"crm op=stage: chave desconhecida '{stage_key}'")
    else:
        state.log("error", lead_id, f"crm: diretiva mal formada ou op desconhecida: {kwargs}")


def apply_followup(lead_id: int, kwargs: dict) -> None:
    """Agenda o follow-up de verdade no scheduler (trilha `scheduled` -- data
    pedida pelo lead tem precedência sobre as trilhas automáticas, B2) e
    também registra a tarefa no Kommo para visibilidade humana (B3)."""
    import scheduler  # import tardio: scheduler não importa directives (sem ciclo)
    due_ts = parse_due(kwargs.get("due", ""))
    note = kwargs.get("note", "follow-up")
    track = kwargs.get("track", "?")
    scheduler.schedule_at(lead_id, due_ts, note)
    kommo.add_task(lead_id, f"[follow-up/{track}] {note}", due_ts)


def apply_price(lead_id: int, kwargs: dict) -> dict:
    """Resolve o link real via gates.get_price() (G1) -- nunca um número."""
    return gates.get_price(lead_id, kwargs.get("product", ""), kwargs.get("category", ""))


def execute(lead_id: int, raw_directives: list[str], escalate_fn) -> dict:
    """Executa todas as diretivas de uma resposta. `escalate_fn(lead_id,
    reason, context)` é injetada pelo chamador (app.py) para evitar import
    circular -- este módulo não decide QUANDO escalar por conta própria além
    do G2 (qualify->competes), só executa o que as diretivas pedem.

    Devolve {'price_results': [...], 'kb_results': [...]} -- resultados de
    `[[price ...]]` e `[[kb ...]]`, para o chamador decidir se precisa de
    uma segunda rodada com o modelo (a resposta original normalmente ainda
    não tem o dado real, só promete)."""
    price_results = []
    kb_results = []
    already_escalated_here = False
    for name, kwargs in parse(raw_directives):
        try:
            if name == "qualify":
                result = apply_qualify(lead_id, kwargs)
                if result["escalate"] and not already_escalated_here:
                    escalate_fn(lead_id, "driver já compete — conversa do dono (G2)", "")
                    already_escalated_here = True
            elif name == "crm":
                apply_crm(lead_id, kwargs)
            elif name == "escalate":
                if not already_escalated_here:
                    escalate_fn(lead_id, kwargs.get("reason", "solicitado pelo agente"),
                                kwargs.get("briefing", ""))
                    already_escalated_here = True
            elif name == "followup":
                apply_followup(lead_id, kwargs)
            elif name == "price":
                price_results.append(apply_price(lead_id, kwargs))
            elif name == "unknown":
                # Princípio fundamental: o agente declara que não sabe, e a
                # ESCALAÇÃO acontece em código -- não depende de ele lembrar
                # de mandar [[escalate]] junto. O briefing carrega o que o
                # §7 do brief exige: a pergunta, o que o Brain devolveu e o
                # que precisa ser confirmado.
                if not already_escalated_here:
                    pergunta = kwargs.get("question", "").strip()
                    achado = kwargs.get("found", "").strip() or "nada conclusivo"
                    escalate_fn(
                        lead_id,
                        f"agente sem informação confiável: {pergunta[:110] or 'pergunta do lead'}",
                        (f"Pergunta do lead: {pergunta or '(não informada pelo agente)'}\n"
                         f"O que o Brain devolveu: {achado}\n"
                         f"Precisa de: resposta confirmada por um operador "
                         f"autorizado. Responda aqui e ela vira conhecimento "
                         f"do Chase."))
                    already_escalated_here = True
            elif name == "kb":
                import brain_kb  # tardio: evita custo quando retrieval off
                hits = brain_kb.search(lead_id, kwargs.get("query", ""))
                kb_results.append({"query": kwargs.get("query", ""),
                                   "results": brain_kb.format_for_context(hits)
                                   or "nenhum documento encontrado"})
            else:
                state.log("error", lead_id, f"diretiva desconhecida: {name} {kwargs}")
        except Exception as exc:
            state.log("error", lead_id, f"falha executando diretiva {name}: {exc}")
    return {"price_results": price_results, "kb_results": kb_results}
