"""Ações do painel que a IA pode propor (dono, 17/09) — não são ferramentas de MCP:
rodam dentro do Command Center, com as travas do dono em código.

- `painel_unir_clientes`  — só quando os dois cards têm o MESMO e-mail, telefone ou
  responsável (chave exata). Fora disso é decisão humana: a ação falha e diz por quê.
- `painel_varrer_cliente` — Gmail (as duas caixas) e DocuSign do cliente; só leitura + espelho.
- `painel_waiver_lixeira` — tira a waiver do painel (restaurável); envelope em aberto é anulado
  no DocuSign; assinado só some do painel. Pede confirmação.

Cada uma devolve um dict com `aplicado` e o que fez; o executor do motor grava e audita.
"""
import json

from command_center.db import agora, atualizar, auditar, todos, um
from command_center.providers import identidade


def _mesma_pessoa(a, b):
    """E-mail, telefone ou responsável exatamente iguais — o critério que o dono deu."""
    motivos = []
    ea, eb = (a.get("email") or "").strip().lower(), (b.get("email") or "").strip().lower()
    if ea and ea == eb:
        motivos.append(f"mesmo e-mail {ea}")
    ta, tb = identidade.so_digitos(a.get("phone")), identidade.so_digitos(b.get("phone"))
    if ta and ta == tb:
        motivos.append("mesmo telefone")
    if a.get("name") and identidade.chave_exata(a["name"]) == identidade.chave_exata(b.get("name") or ""):
        motivos.append(f"mesmo responsável {a['name']}")
    return motivos


def painel_unir_clientes(con, user_id, keep_id, drop_id, motivo=None):
    keep_id, drop_id = int(keep_id), int(drop_id)
    if keep_id == drop_id:
        return {"aplicado": False, "motivo": "os dois ids são o mesmo cliente"}
    a = um(con, "SELECT * FROM clients WHERE id=?", (keep_id,)); b = um(con, "SELECT * FROM clients WHERE id=?", (drop_id,))
    if not a or not b:
        return {"aplicado": False, "motivo": "cliente não encontrado"}
    iguais = _mesma_pessoa(a, b)
    if not iguais:
        return {"aplicado": False, "motivo": "RECUSADO: a IA só une cards com o mesmo e-mail, telefone ou responsável; "
                                              "sem isso é decisão humana (Clientes → Unir dois clientes)"}
    antes = {t: um(con, f"SELECT COUNT(*) AS n FROM {t} WHERE client_id=?", (drop_id,))["n"] for t in ("tasks", "waivers", "emails", "invoices")}
    identidade.unir(con, keep_id, drop_id, "ia", (motivo or "") + " · " + "; ".join(iguais))
    identidade.recalcular_status(con)
    auditar(con, "client.merge", "ia", user_id=user_id, entity_type="client", entity_id=keep_id,
            detail={"drop_id": drop_id, "criterio": iguais, "moved": antes, "motivo": motivo})
    return {"aplicado": True, "keep_id": keep_id, "drop_id": drop_id, "criterio": iguais, "movido": antes}


def painel_varrer_cliente(con, user_id, client_id):
    from command_center.api import rotas
    c = um(con, "SELECT * FROM clients WHERE id=?", (int(client_id),))
    if not c:
        return {"aplicado": False, "motivo": "cliente não encontrado"}
    saida = rotas._varrer_cliente(con, c)
    con.execute("UPDATE clients SET scanned_at=? WHERE id=?", (agora(), c["id"]))
    auditar(con, "client.scan", "ia", user_id=user_id, entity_type="client", entity_id=c["id"], detail=saida)
    return {"aplicado": True, **saida}


def painel_waiver_lixeira(con, user_id, waiver_id, motivo=None):
    from command_center.api import rotas
    from command_center.providers import NaoConectado, modulo
    w = um(con, "SELECT * FROM waivers WHERE id=?", (int(waiver_id),))
    if not w:
        return {"aplicado": False, "motivo": "waiver não encontrada"}
    env = rotas._envelope_id(con, w["id"])
    anulado = None
    if env and w["status"] in ("sent", "delivered", "autoresponded"):
        try:
            anulado = modulo("docusign").anular_humano(env, motivo or "Anulado pela IA (aprovado no Command Center)")
        except NaoConectado as e:
            return {"aplicado": False, "motivo": f"DocuSign não conectado: {e}"}
    con.execute("UPDATE waivers SET hidden=1, status=CASE WHEN ? THEN 'voided' ELSE status END, synced_at=? WHERE id=?",
                (1 if anulado and anulado.get("aplicado") else 0, agora(), w["id"]))
    auditar(con, "waiver.trash", "ia", user_id=user_id, entity_type="waiver", entity_id=w["id"],
            detail={"envelope": env, "reason": motivo, "voided": bool(anulado and anulado.get("aplicado")), "status_antes": w["status"]})
    return {"aplicado": True, "hidden": True, "voided": bool(anulado and anulado.get("aplicado")),
            "nota": "assinada fica no DocuSign; só saiu do painel" if w["status"] == "completed" else None}


# ---------------------------------------------------------------- vendas (closer, 17/09)
# Quem vende fala com a IA e ela age na oportunidade. Mesmas travas das rotas: Ganho só pelo
# fechamento, invoice fora da tabela continua sendo do dono.
def _opp_por(con, opp_id=None, nome=None, user_id=None):
    """Acha a oportunidade por id ou por nome. Vendas é área do operador: quem entra
    alcança qualquer oportunidade (correção do dono, 17/09)."""
    if opp_id:
        o = um(con, "SELECT * FROM opportunities WHERE id=?", (int(opp_id),))
        if not o:
            return None, f"não existe oportunidade #{opp_id}"
        return o, None
    if not nome:
        return None, "diga de quem é a oportunidade (nome ou id)"
    like = f"%{nome.strip().lower()}%"
    achadas = todos(con, """SELECT * FROM opportunities WHERE stage NOT IN ('GANHO','PERDIDO')
                            AND (lower(name) LIKE ? OR lower(COALESCE(pilot_name,'')) LIKE ?)
                            ORDER BY updated_at DESC LIMIT 5""", (like, like))
    if not achadas:
        return None, f"não achei oportunidade aberta de '{nome}'"
    if len(achadas) > 1:
        return None, "mais de uma oportunidade com esse nome: " + ", ".join(f"#{a['id']} {a['name']}" for a in achadas)
    return achadas[0], None


def venda_registrar_ligacao(con, user_id, opp_id=None, nome=None, resultado="pensar", texto=None, minutos=None,
                            proximo_em=None, proximo_que=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    if resultado not in vendas.RESULTADOS:
        return {"aplicado": False, "motivo": f"resultado deve ser um de: {', '.join(vendas.RESULTADOS)}"}
    titulo = vendas.RESULTADOS[resultado] + (f" · {minutos} min" if minutos else "")
    vendas._ev(con, o["id"], "call", titulo, (texto or "").strip() or None, "ia", 1 if resultado != "nao_atendeu" else 0)
    campos = {"updated_at": agora()}
    if proximo_em:
        campos.update(next_at=proximo_em, next_what=(proximo_que or "retorno"))
    etapa = "FECHAMENTO" if resultado == "fechou" else ("CONVERSA" if o["stage"] == "NOVO" and resultado != "sem_interesse" else None)
    if etapa and etapa != o["stage"]:
        campos["stage"] = etapa
        vendas._ev(con, o["id"], "stage", f"{vendas.ETAPA_PT[o['stage']]} → {vendas.ETAPA_PT[etapa]}", None, "ia")
    atualizar(con, "opportunities", o["id"], **campos)
    auditar(con, "sales.call", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"],
            detail={"resultado": resultado, "etapa": campos.get("stage")})
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], "etapa": campos.get("stage", o["stage"]),
            "retorno": campos.get("next_at")}


def venda_agendar_retorno(con, user_id, quando=None, opp_id=None, nome=None, o_que=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    if not quando:
        return {"aplicado": False, "motivo": "diga quando (AAAA-MM-DDTHH:MM)"}
    if len(quando) == 10:
        quando += "T12:00:00Z"
    atualizar(con, "opportunities", o["id"], next_at=quando, next_what=(o_que or "retorno"), updated_at=agora())
    vendas._ev(con, o["id"], "next", f"Retorno marcado: {vendas.quando_pt(quando)}", o_que, "ia")
    auditar(con, "sales.next", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"], detail={"quando": quando})
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], "quando": quando}


def venda_anotar(con, user_id, texto=None, opp_id=None, nome=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    t = (texto or "").strip()
    if not t:
        return {"aplicado": False, "motivo": "anotação vazia"}
    vendas._ev(con, o["id"], "note", "Anotação", t, "ia")
    atualizar(con, "opportunities", o["id"], notes=((o["notes"] + "\n") if o["notes"] else "") + t, updated_at=agora())
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"]}


def venda_mover_etapa(con, user_id, etapa=None, opp_id=None, nome=None, motivo=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    etapa = (etapa or "").upper()
    if etapa not in vendas.ETAPAS:
        return {"aplicado": False, "motivo": f"etapa deve ser uma de: {', '.join(vendas.ETAPAS)}"}
    if etapa == "GANHO":
        return {"aplicado": False, "motivo": "RECUSADO: Ganho é resultado do fechamento — use venda_fechar, que cria o cliente e dispara o resto"}
    if etapa == "PERDIDO" and not (motivo or "").strip():
        return {"aplicado": False, "motivo": "perdido exige motivo"}
    atualizar(con, "opportunities", o["id"], stage=etapa, lost_reason=(motivo or None) if etapa == "PERDIDO" else o["lost_reason"],
              next_at=None if etapa == "PERDIDO" else o["next_at"], updated_at=agora())
    vendas._ev(con, o["id"], "stage", f"{vendas.ETAPA_PT[o['stage']]} → {vendas.ETAPA_PT[etapa]}", motivo, "ia")
    auditar(con, "sales.stage", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"],
            detail={"de": o["stage"], "para": etapa, "motivo": motivo})
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], "etapa": etapa}


def venda_tarefa(con, user_id, titulo=None, opp_id=None, nome=None, onde="painel", quando=None, notas=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    if not (titulo or "").strip():
        return {"aplicado": False, "motivo": "diga o que é a tarefa"}
    extra = vendas.ExtraIn(titulo=titulo.strip(), onde=("asana" if onde == "asana" else "painel"), quando=quando, notas=notas)
    res = vendas._extra(con, o, extra, user_id)
    vendas._ev(con, o["id"], "task", f"Tarefa: {titulo.strip()}", res, "ia", 1)
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], **res}


def venda_enviar_waiver(con, user_id, opp_id=None, nome=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    try:
        res = vendas._waiver(con, dict(o, client_id=o["client_id"]))
    except Exception as e:                                        # noqa: BLE001
        return {"aplicado": False, "motivo": str(e)[:240]}
    vendas._ev(con, o["id"], "waiver", "Waiver enviada pela IA", res, "ia", 1)
    auditar(con, "sales.waiver", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"], detail=res)
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], **res}


def venda_enviar_invoice(con, user_id, opp_id=None, nome=None):
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    if not o["service"] or o["amount"] is None:
        return {"aplicado": False, "motivo": "esta oportunidade não tem serviço e valor: complete a ficha antes"}
    try:
        res = vendas._qbo(con, o, True)
    except Exception as e:                                        # noqa: BLE001
        return {"aplicado": False, "motivo": str(e)[:240]}
    vendas._ev(con, o["id"], "invoice", "Invoice criada e enviada pela IA", res, "ia", 1)
    auditar(con, "sales.invoice", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"], detail=res)
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], **res}


def venda_fechar(con, user_id, opp_id=None, nome=None):
    """Fecha a venda e dispara a lista inteira (cliente, QuickBooks, waiver, Asana, Kommo)."""
    from command_center.api import vendas
    o, erro = _opp_por(con, opp_id, nome, user_id)
    if erro:
        return {"aplicado": False, "motivo": erro}
    if not o["service"] or o["amount"] is None:
        return {"aplicado": False, "motivo": "para fechar preciso do serviço e do valor na ficha"}
    saida = []
    try:
        cid, det = vendas._cliente_do_fechamento(con, o, None)
        atualizar(con, "opportunities", o["id"], client_id=cid)
        o = dict(o, client_id=cid)
        vendas._passo(saida, "cliente", True, det, {"client_id": cid})
    except Exception as e:                                        # noqa: BLE001
        vendas._passo(saida, "cliente", False, str(e)[:200])
    for passo, fn in (("qbo", lambda: vendas._qbo(con, o, True)), ("waiver", lambda: vendas._waiver(con, o)),
                      ("asana", lambda: vendas._asana(con, o)), ("kommo", lambda: vendas._kommo_ganho(con, o))):
        try:
            vendas._passo(saida, passo, True, "feito", fn())
        except Exception as e:                                    # noqa: BLE001
            vendas._passo(saida, passo, False, str(e)[:200])
    fechado = {"em": agora(), "por": "ia", "passos": saida}
    etapa = "GANHO" if o["client_id"] else "FECHAMENTO"
    atualizar(con, "opportunities", o["id"], stage=etapa, closing=json.dumps(fechado, ensure_ascii=False),
              next_at=None, updated_at=agora())
    for p in saida:
        vendas._ev(con, o["id"], vendas.PASSO_KIND.get(p["passo"], "task"), f"{p['nome']}: {p['detalhe']}", None, "ia",
                   1 if p["ok"] else (0 if p["ok"] is False else None))
    auditar(con, "sales.close", "ia", user_id=user_id, entity_type="opportunity", entity_id=o["id"],
            detail={"passos": {p["passo"]: p["ok"] for p in saida}, "valor": o["amount"]})
    return {"aplicado": True, "oportunidade": o["id"], "quem": o["name"], "etapa": etapa,
            "feitos": [p["nome"] for p in saida if p["ok"]], "faltou": [f"{p['nome']}: {p['detalhe']}" for p in saida if p["ok"] is False]}


ACOES = {
    "painel_unir_clientes": (painel_unir_clientes, ("keep_id", "drop_id", "motivo")),
    "painel_varrer_cliente": (painel_varrer_cliente, ("client_id",)),
    "painel_waiver_lixeira": (painel_waiver_lixeira, ("waiver_id", "motivo")),
    "venda_registrar_ligacao": (venda_registrar_ligacao, ("opp_id", "nome", "resultado", "texto", "minutos", "proximo_em", "proximo_que")),
    "venda_agendar_retorno": (venda_agendar_retorno, ("opp_id", "nome", "quando", "o_que")),
    "venda_anotar": (venda_anotar, ("opp_id", "nome", "texto")),
    "venda_mover_etapa": (venda_mover_etapa, ("opp_id", "nome", "etapa", "motivo")),
    "venda_tarefa": (venda_tarefa, ("opp_id", "nome", "titulo", "onde", "quando", "notas")),
    "venda_enviar_waiver": (venda_enviar_waiver, ("opp_id", "nome")),
    "venda_enviar_invoice": (venda_enviar_invoice, ("opp_id", "nome")),
    "venda_fechar": (venda_fechar, ("opp_id", "nome")),
}
DESCRICOES = {
    "painel_unir_clientes": "Une dois cards de cliente em um. Só quando têm o mesmo e-mail, telefone ou responsável; fora disso é decisão humana.",
    "painel_varrer_cliente": "Varre o Gmail (urace@ e support@) e o DocuSign de um cliente e liga o que achar ao card.",
    "painel_waiver_lixeira": "Tira uma waiver do painel (restaurável). Envelope em aberto é anulado no DocuSign; assinado só some do painel.",
    "venda_registrar_ligacao": "Registra a ligação numa oportunidade de venda (resultado, o que foi dito, próximo passo) e move a etapa quando for o caso.",
    "venda_agendar_retorno": "Marca o retorno de uma oportunidade na agenda de vendas. Nada sai para o cliente.",
    "venda_anotar": "Guarda uma anotação interna na oportunidade.",
    "venda_mover_etapa": "Move a oportunidade no quadro de vendas (Ganho não: isso é o fechamento).",
    "venda_tarefa": "Cria uma tarefa do fechamento: no painel (lembrete) ou no Asana.",
    "venda_enviar_waiver": "Envia a waiver do serviço combinado para o responsável, pelo modelo certo do DocuSign.",
    "venda_enviar_invoice": "Cria o cliente no QuickBooks se faltar e envia a invoice do valor fechado.",
    "venda_fechar": "Fecha a venda: cria o card do cliente, o cliente e a invoice no QuickBooks, envia a waiver, cria a tarefa no Asana e move o Kommo para Closed won.",
}


def executar(con, user_id, acao, args):
    fn, params = ACOES[acao]
    kw = {k: args.get(k) for k in params if k in args}
    opcionais = ("motivo", "opp_id", "nome", "texto", "minutos", "proximo_em", "proximo_que", "o_que",
                 "onde", "quando", "notas", "titulo", "etapa", "resultado")
    faltam = [k for k in params if k not in kw and k not in opcionais]
    if faltam:
        return {"aplicado": False, "motivo": f"faltam argumentos: {faltam}"}
    return fn(con, user_id, **kw)


def descrever_todas():
    return [{"name": n, "description": DESCRICOES[n], "params": list(p)} for n, (_f, p) in ACOES.items()]
