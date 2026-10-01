"""Conta do site ↔ cliente do site interno (#42).

Dono, 30/09: *"conforme for sendo criado os clientes, tanto de maneira manual quanto a IA
identifique os nomes, tanto de clientes que nós já temos salvos na nossa base quanto os
ativos, a gente vincular o perfil do cliente no site público com o perfil do cliente no
site interno"*.

**O sistema sugere; a equipe confirma.** A sugestão usa o mesmo motor de identidade do
painel (o que junta o cliente do Asana, do DocuSign e do e-mail): e-mail, telefone, nome
do responsável e nome de cada piloto da conta, nessa ordem de confiança. Ela é calculada
na hora em que a tela abre, então cliente novo no painel (Asana, manual, IA) vira
sugestão sozinho.

Nada vira vínculo sem uma pessoa: o vínculo abre para o cliente o **histórico de
serviços** daquele card. Um telefone de família ou um nome parecido ligaria a conta ao
cliente errado e mostraria o serviço de outra pessoa — é a regra "nunca colocar serviço de
outro cliente em card de outro cliente".
"""
import json
import re

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import identidade

STATUS_SERVICO = {"completed": "done", "open": "scheduled"}


class ErroVinculo(ValueError):
    pass


def sugestao(con, conta):
    """Melhor candidato ainda livre (sem outra conta ligada), com o motivo — ou None."""
    ocupados = {r["client_id"] for r in todos(con, "SELECT client_id FROM portal_accounts WHERE client_id IS NOT NULL")}
    tentativas = [dict(email=conta["email"]), dict(telefone=conta["phone"]), dict(nome=conta["name"])]
    tentativas += [dict(piloto=p["name"]) for p in todos(con, "SELECT name FROM portal_pilots WHERE account_id=? AND active=1", (conta["id"],))]
    for t in tentativas:
        if not any(t.values()):
            continue
        c, motivo = identidade.acha_pessoa(con, **t)
        if c and c["id"] not in ocupados:
            campo = next(iter(t))
            return {"client_id": c["id"], "name": c["name"], "pilot_name": c["pilot_name"], "email": c["email"],
                    "phone": c["phone"], "motivo": {"email": "mesmo e-mail", "telefone": "mesmo telefone",
                                                    "nome": f"nome do responsável ({motivo})",
                                                    "piloto": f"nome do piloto ({motivo})"}[campo]}
    return None


def contas(con, filtro="sem_vinculo"):
    sql = """SELECT a.id, a.email, a.name, a.phone, a.city, a.state, a.created_at, a.client_id, a.linked_at,
                    c.name AS client_name, c.pilot_name AS client_pilot, u.name AS linked_by_name,
                    (SELECT COUNT(*) FROM portal_pilots p WHERE p.account_id=a.id AND p.active=1) AS drivers
               FROM portal_accounts a LEFT JOIN clients c ON c.id=a.client_id LEFT JOIN users u ON u.id=a.linked_by
              WHERE a.active=1"""
    if filtro == "sem_vinculo":
        sql += " AND a.client_id IS NULL"
    elif filtro == "vinculadas":
        sql += " AND a.client_id IS NOT NULL"
    saida = []
    for a in todos(con, sql + " ORDER BY a.client_id IS NOT NULL, a.id DESC LIMIT 500"):
        a = dict(a)
        a["pilotos"] = [p["name"] for p in todos(con, "SELECT name FROM portal_pilots WHERE account_id=? AND active=1 ORDER BY is_self DESC, id", (a["id"],))]
        a["sugestao"] = None if a["client_id"] else sugestao(con, a)
        saida.append(a)
    return saida


def vincular(con, conta_id, client_id, por):
    a = um(con, "SELECT id, client_id FROM portal_accounts WHERE id=? AND active=1", (conta_id,))
    if not a:
        raise ErroVinculo("conta do site não existe")
    c = um(con, "SELECT id, kind FROM clients WHERE id=?", (client_id,))
    if not c:
        raise ErroVinculo("cliente do site interno não existe")
    if c["kind"] == identidade.SEPARADO:
        raise ErroVinculo("esse card não é de cliente (foi separado como corrida/tarefa)")
    outra = um(con, "SELECT id, email FROM portal_accounts WHERE client_id=? AND id<>?", (client_id, conta_id))
    if outra:
        raise ErroVinculo(f"esse cliente já está ligado à conta {outra['email']}")
    atualizar(con, "portal_accounts", conta_id, client_id=client_id, linked_by=por, linked_at=agora(), updated_at=agora())
    return {"antes": a["client_id"], "depois": client_id}


def criar_cliente(con, conta_id, por):
    """Conta de alguém que não está na base (#52): cria o card com os dados da conta — o
    responsável, o e-mail, o telefone e o piloto (o primeiro que não é o próprio responsável,
    senão ele mesmo) — e vincula. Antes, confere: se o e-mail ou o telefone já são de um
    cliente, não cria outro (é para vincular àquele)."""
    a = um(con, "SELECT * FROM portal_accounts WHERE id=? AND active=1", (conta_id,))
    if not a:
        raise ErroVinculo("conta do site não existe")
    if a["client_id"]:
        raise ErroVinculo("essa conta já está vinculada")
    for campo, valor in (("email", a["email"]), ("telefone", a["phone"])):
        c, _ = identidade.acha_pessoa(con, **{campo: valor}) if valor else (None, None)
        if c:
            raise ErroVinculo(f"já existe um cliente com esse {'e-mail' if campo == 'email' else 'telefone'}: "
                              f"{c['pilot_name'] or c['name']} — vincule a ele")
    pil = todos(con, "SELECT name, birth_date, is_self FROM portal_pilots WHERE account_id=? AND active=1 ORDER BY is_self, id",
                (conta_id,))
    p = pil[0] if pil else None
    cid = inserir(con, "clients", name=a["name"], email=a["email"], phone=a["phone"],
                  pilot_name=p["name"] if p else a["name"], pilot_dob=p["birth_date"] if p else None,
                  status="NEW", source="site", notes=f"Criado pela conta do site #{conta_id}.")
    vincular(con, conta_id, cid, por)
    return cid


def desvincular(con, conta_id):
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta_id,))
    if not a:
        raise ErroVinculo("conta do site não existe")
    atualizar(con, "portal_accounts", conta_id, client_id=None, linked_by=None, linked_at=None, updated_at=agora())
    return {"antes": a["client_id"]}


def _servico(titulo):
    """'David Pera_Urace Daily_Using Own Kart [1/1]' → 'Urace Daily · Using Own Kart'. Só o
    serviço: o nome e as marcações internas não vão para o cliente."""
    base = re.sub(r"\s*\[[^\]]*\]\s*$", "", titulo or "")
    partes = [p.strip() for p in base.split("_") if p.strip()]
    return " · ".join(partes[1:]) if len(partes) > 1 else "Session"


def historico(con, conta_id):
    """O que o cliente vê: data, serviço e situação. Nada de nota, coluna ou responsável interno."""
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta_id,))
    if not a or not a["client_id"]:
        return {"linked": False, "services": []}
    linhas = todos(con, """SELECT due_on, title, status FROM tasks WHERE client_id=? AND due_on IS NOT NULL
                            ORDER BY due_on DESC LIMIT 200""", (a["client_id"],))
    return {"linked": True, "services": [{"date": t["due_on"][:10], "service": _servico(t["title"]),
                                          "status": STATUS_SERVICO.get(t["status"], "scheduled")} for t in linhas]}


def conta_do_cliente(con, client_id):
    """Para o card do cliente no site interno: a conta do site, os pilotos e as medidas."""
    a = um(con, """SELECT id, email, name, phone, birth_date, address_line1, address_line2, city, state, zip, created_at, linked_at,
                          last_login_at FROM portal_accounts WHERE client_id=? AND active=1""", (client_id,))
    if not a:
        return None
    pil = []
    for p in todos(con, "SELECT id, name, birth_date, is_self, measures, measures_updated_at FROM portal_pilots WHERE account_id=? AND active=1 ORDER BY is_self DESC, id", (a["id"],)):
        p = dict(p)
        p["measures"] = json.loads(p["measures"]) if p["measures"] else {}
        pil.append(p)
    return {**dict(a), "drivers": pil}
