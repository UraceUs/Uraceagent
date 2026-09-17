"""Ações do painel que a IA pode propor (dono, 17/09) — não são ferramentas de MCP:
rodam dentro do Command Center, com as travas do dono em código.

- `painel_unir_clientes`  — só quando os dois cards têm o MESMO e-mail, telefone ou
  responsável (chave exata). Fora disso é decisão humana: a ação falha e diz por quê.
- `painel_varrer_cliente` — Gmail (as duas caixas) e DocuSign do cliente; só leitura + espelho.
- `painel_waiver_lixeira` — tira a waiver do painel (restaurável); envelope em aberto é anulado
  no DocuSign; assinado só some do painel. Pede confirmação.

Cada uma devolve um dict com `aplicado` e o que fez; o executor do motor grava e audita.
"""
from command_center.db import agora, auditar, todos, um
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


ACOES = {
    "painel_unir_clientes": (painel_unir_clientes, ("keep_id", "drop_id", "motivo")),
    "painel_varrer_cliente": (painel_varrer_cliente, ("client_id",)),
    "painel_waiver_lixeira": (painel_waiver_lixeira, ("waiver_id", "motivo")),
}
DESCRICOES = {
    "painel_unir_clientes": "Une dois cards de cliente em um. Só quando têm o mesmo e-mail, telefone ou responsável; fora disso é decisão humana.",
    "painel_varrer_cliente": "Varre o Gmail (urace@ e support@) e o DocuSign de um cliente e liga o que achar ao card.",
    "painel_waiver_lixeira": "Tira uma waiver do painel (restaurável). Envelope em aberto é anulado no DocuSign; assinado só some do painel.",
}


def executar(con, user_id, acao, args):
    fn, params = ACOES[acao]
    kw = {k: args.get(k) for k in params if k in args}
    faltam = [k for k in params if k not in kw and k not in ("motivo",)]
    if faltam:
        return {"aplicado": False, "motivo": f"faltam argumentos: {faltam}"}
    return fn(con, user_id, **kw)


def descrever_todas():
    return [{"name": n, "description": DESCRICOES[n], "params": list(p)} for n, (_f, p) in ACOES.items()]
