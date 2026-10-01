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

**Cada driver tem o seu card** (#65, dono, 01/10: *"um client id para cada driver"*). A conta é
do responsável; cada piloto dela liga ao SEU card (o número do card é o Client ID do driver).
O vínculo da conta (`portal_accounts.client_id`) continua sendo o card principal — o do
primeiro driver ligado —, e a sessão marcada no site conta no card do driver dela.
"""
import json
import re

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import identidade

STATUS_SERVICO = {"completed": "done", "open": "scheduled"}


class ErroVinculo(ValueError):
    pass


def _ocupados(con, conta_id):
    """Cards já ligados a OUTRA conta do site ou a um driver de outra conta."""
    return {r["client_id"] for r in todos(con, """SELECT client_id FROM portal_accounts WHERE client_id IS NOT NULL AND id<>?
                                                   UNION SELECT client_id FROM portal_pilots WHERE client_id IS NOT NULL AND account_id<>?""",
                                          (conta_id, conta_id))}


def sugestao(con, conta):
    """Melhor candidato ainda livre (sem outra conta ligada), com o motivo — ou None."""
    ocupados = _ocupados(con, conta["id"])
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
        a["drivers_list"] = drivers_da_conta(con, a["id"])
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
    if um(con, "SELECT id FROM portal_pilots WHERE client_id=? AND account_id<>?", (client_id, conta_id)):
        raise ErroVinculo("esse card já é de um driver de outra conta")
    atualizar(con, "portal_accounts", conta_id, client_id=client_id, linked_by=por, linked_at=agora(), updated_at=agora())
    herdar_card(con, conta_id, por)
    return {"antes": a["client_id"], "depois": client_id}


# ------------------------------------------------------------------ um card por driver (#65)
def herdar_card(con, conta_id, por=None):
    """O card principal da conta é de UM piloto (`clients.pilot_name`): esse piloto herda o card —
    o de mesmo nome, ou o único piloto da conta. Só preenche o que está vazio. Devolve o id do
    piloto que herdou, ou None."""
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta_id,))
    if not a or not a["client_id"] or um(con, "SELECT id FROM portal_pilots WHERE client_id=?", (a["client_id"],)):
        return None
    c = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (a["client_id"],))
    pil = todos(con, "SELECT id, name FROM portal_pilots WHERE account_id=? AND active=1 AND client_id IS NULL ORDER BY is_self DESC, id",
                (conta_id,))
    if not c or not pil:
        return None
    alvo = identidade.chave_exata(c["pilot_name"] or c["name"])
    iguais = [p for p in pil if identidade.chave_exata(p["name"]) == alvo] or \
             [p for p in pil if identidade.mesmo_nome(p["name"], c["pilot_name"] or c["name"])]
    total = um(con, "SELECT COUNT(*) AS n FROM portal_pilots WHERE account_id=? AND active=1", (conta_id,))["n"]
    p = iguais[0] if len(iguais) == 1 else (pil[0] if total == 1 else None)
    if p:
        atualizar(con, "portal_pilots", p["id"], client_id=a["client_id"], linked_by=por, linked_at=agora(), updated_at=agora())
        return p["id"]
    return None


def drivers_da_conta(con, conta_id):
    """Os drivers da conta com o card de cada um (Client ID) e, para quem não tem, a sugestão."""
    saida = []
    for p in todos(con, """SELECT p.id, p.name, p.birth_date, p.client_id, p.linked_at, c.name AS client_name, c.pilot_name AS client_pilot
                             FROM portal_pilots p LEFT JOIN clients c ON c.id=p.client_id
                            WHERE p.account_id=? AND p.active=1 ORDER BY p.is_self DESC, p.id""", (conta_id,)):
        p = dict(p)
        p["sugestao"] = None if p["client_id"] else sugestao_driver(con, p["id"])
        saida.append(p)
    return saida


def _piloto(con, pilot_id):
    p = um(con, "SELECT * FROM portal_pilots WHERE id=? AND active=1", (pilot_id,))
    if not p:
        raise ErroVinculo("driver não existe")
    return p


def sugestao_driver(con, pilot_id):
    """Card livre com o nome deste driver (o motor de identidade, pelo piloto). Ligado a outro
    driver ou a outra conta, não serve."""
    p = _piloto(con, pilot_id)
    if len(identidade.normaliza(p["name"])) < 2:
        return None              # primeiro nome sozinho não identifica ninguém
    c, motivo = identidade.acha_pessoa(con, piloto=p["name"])
    if not c or c["id"] in _ocupados(con, p["account_id"]) or \
            um(con, "SELECT id FROM portal_pilots WHERE client_id=? AND id<>?", (c["id"], pilot_id)):
        return None
    return {"client_id": c["id"], "name": c["name"], "pilot_name": c["pilot_name"], "motivo": f"nome do piloto ({motivo})"}


def vincular_driver(con, pilot_id, client_id, por):
    p = _piloto(con, pilot_id)
    c = um(con, "SELECT id, kind FROM clients WHERE id=?", (client_id,))
    if not c:
        raise ErroVinculo("cliente do site interno não existe")
    if c["kind"] == identidade.SEPARADO:
        raise ErroVinculo("esse card não é de cliente (foi separado como corrida/tarefa)")
    outro = um(con, "SELECT name FROM portal_pilots WHERE client_id=? AND id<>?", (client_id, pilot_id))
    if outro:
        raise ErroVinculo(f"esse card já é do driver {outro['name']}: cada driver tem o seu")
    if client_id in _ocupados(con, p["account_id"]):
        raise ErroVinculo("esse card é de outra conta do site")
    atualizar(con, "portal_pilots", pilot_id, client_id=client_id, linked_by=por, linked_at=agora(), updated_at=agora())
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (p["account_id"],))
    if not a["client_id"]:      # o primeiro driver ligado vira o card principal da conta
        atualizar(con, "portal_accounts", p["account_id"], client_id=client_id, linked_by=por, linked_at=agora(), updated_at=agora())
    return {"driver": pilot_id, "antes": p["client_id"], "depois": client_id}


def criar_cliente_driver(con, pilot_id, por):
    """Card novo para o driver: responsável e contato da conta, piloto = o driver. Se já existe
    card com o nome dele, recusa (é para vincular àquele). O e-mail do responsável é o mesmo
    dos irmãos — por isso aqui ele não bloqueia, a não ser que seja de um card de outra conta."""
    p = _piloto(con, pilot_id)
    if p["client_id"]:
        raise ErroVinculo("esse driver já tem card")
    a = um(con, "SELECT * FROM portal_accounts WHERE id=?", (p["account_id"],))
    da_conta = {a["client_id"]} | {r["client_id"] for r in todos(con, "SELECT client_id FROM portal_pilots WHERE account_id=? AND client_id IS NOT NULL", (a["id"],))}
    s = sugestao_driver(con, pilot_id)
    if s:
        raise ErroVinculo(f"já existe o card de {s['pilot_name'] or s['name']} (Client ID {s['client_id']}): vincule a ele")
    for campo, valor in (("email", a["email"]), ("telefone", a["phone"])):
        c, _ = identidade.acha_pessoa(con, **{campo: valor}) if valor else (None, None)
        if c and c["id"] not in da_conta and c["id"] in _ocupados(con, a["id"]):
            raise ErroVinculo(f"esse {'e-mail' if campo == 'email' else 'telefone'} é de um card de outra conta do site")
    cid = inserir(con, "clients", name=a["name"], email=a["email"], phone=a["phone"], pilot_name=p["name"], pilot_dob=p["birth_date"],
                  status="NEW", source="site", notes=f"Criado pela conta do site #{a['id']}, driver {p['name']}.")
    vincular_driver(con, pilot_id, cid, por)
    return cid


def desvincular_driver(con, pilot_id):
    p = _piloto(con, pilot_id)
    atualizar(con, "portal_pilots", pilot_id, client_id=None, linked_by=None, linked_at=None, updated_at=agora())
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (p["account_id"],))
    if p["client_id"] and a["client_id"] == p["client_id"]:   # era o card principal: passa ao próximo driver com card
        prox = um(con, "SELECT client_id FROM portal_pilots WHERE account_id=? AND client_id IS NOT NULL ORDER BY id LIMIT 1", (p["account_id"],))
        atualizar(con, "portal_accounts", p["account_id"], client_id=prox["client_id"] if prox else None, updated_at=agora(),
                  **({} if prox else {"linked_by": None, "linked_at": None}))
    return {"driver": pilot_id, "antes": p["client_id"]}


def cards_da_conta(con, conta_id):
    """{client_id: nome do driver (ou None)} — todos os cards que a conta vê."""
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta_id,))
    saida = {r["client_id"]: r["name"] for r in todos(con, "SELECT client_id, name FROM portal_pilots WHERE account_id=? AND active=1 AND client_id IS NOT NULL", (conta_id,))}
    if a and a["client_id"] and a["client_id"] not in saida:
        saida[a["client_id"]] = None
    return saida


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
    vincular(con, conta_id, cid, por)          # o driver do card herda o card (#65)
    return cid


def desvincular(con, conta_id):
    a = um(con, "SELECT client_id FROM portal_accounts WHERE id=?", (conta_id,))
    if not a:
        raise ErroVinculo("conta do site não existe")
    atualizar(con, "portal_accounts", conta_id, client_id=None, linked_by=None, linked_at=None, updated_at=agora())
    # o driver que tinha o card principal também solta; os outros drivers continuam com os seus
    con.execute("UPDATE portal_pilots SET client_id=NULL, linked_by=NULL, linked_at=NULL, updated_at=? WHERE account_id=? AND client_id=?",
                (agora(), conta_id, a["client_id"]))
    return {"antes": a["client_id"]}


def _servico(titulo):
    """'David Pera_Urace Daily_Using Own Kart [1/1]' → 'Urace Daily · Using Own Kart'. Só o
    serviço: o nome e as marcações internas não vão para o cliente."""
    base = re.sub(r"\s*\[[^\]]*\]\s*$", "", titulo or "")
    partes = [p.strip() for p in base.split("_") if p.strip()]
    return " · ".join(partes[1:]) if len(partes) > 1 else "Session"


def historico(con, conta_id):
    """O que o cliente vê: data, serviço, situação e o driver (cada driver tem o seu card, #65).
    Nada de nota, coluna ou responsável interno."""
    cards = cards_da_conta(con, conta_id)
    if not cards:
        return {"linked": False, "services": []}
    marca = ",".join("?" * len(cards))
    linhas = todos(con, f"""SELECT t.due_on, t.title, t.status, t.client_id, c.pilot_name FROM tasks t LEFT JOIN clients c ON c.id=t.client_id
                             WHERE t.client_id IN ({marca}) AND t.due_on IS NOT NULL ORDER BY t.due_on DESC LIMIT 200""", tuple(cards))
    return {"linked": True, "services": [{"date": t["due_on"][:10], "service": _servico(t["title"]),
                                          "status": STATUS_SERVICO.get(t["status"], "scheduled"),
                                          "driver": cards[t["client_id"]] or t["pilot_name"]} for t in linhas]}


def conta_do_cliente(con, client_id):
    """Para o card do cliente no site interno: a conta do site, os pilotos e as medidas. O card
    pode ser o principal da conta ou o de um driver dela (#65): `driver_id` diz de qual."""
    driver = um(con, "SELECT id, account_id FROM portal_pilots WHERE client_id=? AND active=1", (client_id,))
    a = um(con, """SELECT id, email, name, phone, birth_date, address_line1, address_line2, city, state, zip, created_at, linked_at,
                          last_login_at FROM portal_accounts WHERE active=1 AND (client_id=? OR id=?)
                    ORDER BY client_id=? DESC LIMIT 1""", (client_id, driver["account_id"] if driver else -1, client_id))
    if not a:
        return None
    pil = []
    for p in todos(con, """SELECT id, name, birth_date, is_self, measures, measures_updated_at, client_id
                             FROM portal_pilots WHERE account_id=? AND active=1 ORDER BY is_self DESC, id""", (a["id"],)):
        p = dict(p)
        p["measures"] = json.loads(p["measures"]) if p["measures"] else {}
        pil.append(p)
    return {**dict(a), "drivers": pil, "driver_id": driver["id"] if driver else None}
