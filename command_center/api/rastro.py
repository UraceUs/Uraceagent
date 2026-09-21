"""O rastro do agente no Asana.

Dono, 21/09, depois de achar tarefa de agente no Asana dele sem saber de quem era:
*"moveu uma tarefa, coloca um comentário dizendo que foi movido tal dia, tal hora, pelo
agente de IA... enviou a invoice, coloca no comentário, invoice enviada tal dia pelo
agente de IA. Enviou a waiver, enviada tal dia... coloca o horário também"*.

A assinatura (em `mcp_stdio`) marca o que o agente **escreve**. Isto marca o que ele
**faz em outro sistema** — porque enviar invoice no QuickBooks ou waiver no DocuSign não
deixa nenhum vestígio no Asana, que é onde a equipe olha. Sem isto, a pessoa abre a tarefa
do cliente e não tem como saber que a cobrança já saiu.

**Só interno.** O comentário fica na tarefa do Asana, que é da equipe. O cliente não vê
nada disso — decisão dele no mesmo dia: *"o que foi interno nosso; para o cliente não
aparece que foi feito isso"*.

Nada aqui levanta exceção: quando o rastro é escrito, a ação JÁ aconteceu. Falhar em
comentar não pode transformar uma invoice enviada em erro na tela.
"""
from command_center.db import auditar, um


def no_asana(con, gid, o_que, detalhe=None):
    """Comenta na tarefa do Asana o que o painel acabou de fazer, com dia e hora."""
    if not gid:
        return False
    try:
        from command_center.providers import modulo
        modulo("asana").comentar_rastro(str(gid), o_que)
        auditar(con, "asana.rastro", "system", entity_type="task", entity_id=None,
                detail={"gid": str(gid), "o_que": o_que, **(detalhe or {})})
        return True
    except Exception as e:                                    # noqa: BLE001
        try:
            auditar(con, "asana.rastro.failed", "system", entity_type="task", entity_id=None,
                    detail={"gid": str(gid), "o_que": o_que, "erro": f"{type(e).__name__}: {str(e)[:160]}"})
        except Exception:                                     # noqa: BLE001
            pass
        return False


def tarefa_do_cliente(con, client_id, quando=None):
    """A tarefa do Asana em que este rastro faz sentido: a do dia do serviço, se houver;
    senão a mais recente do cliente. Sem cliente ligado, não há onde comentar — e aí o
    rastro simplesmente não sai, em vez de ir parar na tarefa de outra pessoa."""
    if not client_id:
        return None
    base = """SELECT l.external_id FROM tasks t
              JOIN entity_links l ON l.entity_type='task' AND l.entity_id=t.id AND l.system='asana'
              WHERE t.client_id=?"""
    if quando:
        r = um(con, base + " AND t.due_on=? ORDER BY t.id DESC LIMIT 1", (client_id, quando))
        if r:
            return r["external_id"]
    r = um(con, base + " ORDER BY t.due_on DESC, t.id DESC LIMIT 1", (client_id,))
    return r["external_id"] if r else None


def invoice_enviada(con, inv, para=None, lembrete=False):
    """Invoice saiu do QuickBooks → a tarefa do cliente fica sabendo."""
    if not inv:
        return False
    numero = inv["doc_number"] if isinstance(inv, dict) or hasattr(inv, "keys") else None
    gid = tarefa_do_cliente(con, (inv["client_id"] if "client_id" in inv.keys() else None), inv["due_on"] if "due_on" in inv.keys() else None)
    o_que = ("Lembrete da invoice" if lembrete else "Invoice") + (f" {numero}" if numero else "") + " enviada"
    if para:
        o_que += f" para {para}"
    return no_asana(con, gid, o_que, {"invoice": numero})


def waiver_enviada(con, client_id, nome, email, modelo=None, gid=None):
    """Waiver saiu do DocuSign → a mesma tarefa registra."""
    gid = gid or tarefa_do_cliente(con, client_id)
    o_que = f"Waiver enviada para {nome or email}" + (f" (modelo {modelo})" if modelo else "")
    return no_asana(con, gid, o_que, {"email": email})
