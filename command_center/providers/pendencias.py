"""Pendências da IA: o registro criado incompleto e a cobrança do que falta (#185).

Dono, 12/10: *"vão jogar lá o nome da pessoa, informações faltando, e a IA precisa assimilar
que tem informações faltando, e ao invés de bloquear e não fazer a tarefa, ela coloca a tarefa
com as informações que tem, e o restante ela identifica informações de contato para entrar em
contato, ou então ela consegue avisar o usuário que foi criado, mas que precisa colocar as
demais informações, e vai dando rodada de aviso até o usuário completar"*.

- A IA cria com o que tem (sem inventar nada) e chama `pendencia_registrar`: o que criou,
  onde está, o que falta e o contato que achou.
- Pendência de um cliente com `campos` (colunas do card) é conferida sozinha: preencheu o
  card, a pendência fecha.
- Cada comando novo da pessoa leva as pendências dela (`contexto`), e a IA cobra no fim da
  resposta; quando a pessoa manda o dado, a IA completa o registro e chama `pendencia_resolver`.
- A rotina `pendencias_aviso` (09:00 e 16:00) é a rodada: um push por pessoa com o que ela
  ainda deve. A pendência também fica em Atenção e no topo do AI Command, com "Completei".
"""
import json

from command_center.db import agora, atualizar, auditar, inserir, todos, um

# Colunas do card que o sistema sabe conferir sozinho.
CAMPOS_CLIENTE = {"email": "e-mail", "phone": "telefone", "pilot_name": "nome do piloto",
                  "pilot_dob": "data de nascimento do piloto"}
MAX_NO_CONTEXTO = 8


class ErroPendencia(ValueError):
    """Regra violada. A mensagem é para quem chamou (a IA ou a tela)."""


def _lista(v):
    if v is None:
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            v = [p for p in (x.strip() for x in v.replace(";", ",").split(",")) if p]
    return [str(x).strip()[:120] for x in v if str(x).strip()] if isinstance(v, list) else []


def publica(p):
    d = dict(p)
    d["campos"] = _lista(d.get("campos"))
    d["faltando"] = _lista(d.get("faltando")) + [CAMPOS_CLIENTE[k] for k in d["campos"] if k in CAMPOS_CLIENTE]
    return d


def registrar(con, titulo, faltando, user_id=None, command_id=None, onde=None, client_id=None, campos=None, contato=None):
    """Uma pendência aberta. A mesma (pessoa, título) ainda aberta é atualizada, não duplicada."""
    titulo = (titulo or "").strip()[:200]
    if not titulo:
        raise ErroPendencia("diga o que foi criado (titulo)")
    cid = int(client_id) if client_id not in (None, "", 0) else None
    if cid and not um(con, "SELECT id FROM clients WHERE id=?", (cid,)):
        raise ErroPendencia("cliente não encontrado no painel: registre sem client_id")
    cps = [c for c in _lista(campos) if c in CAMPOS_CLIENTE]
    falta = _lista(faltando)
    if not cid:                                   # sem card não há o que conferir: vira texto
        falta += [CAMPOS_CLIENTE[c] for c in cps if CAMPOS_CLIENTE[c] not in falta]
        cps = []
    else:                                         # o que o painel confere não se repete no texto
        falta = [f for f in falta if f not in {CAMPOS_CLIENTE[c] for c in cps}]
    if not falta and not cps:
        raise ErroPendencia("diga o que está faltando (faltando ou campos)")
    dados = dict(faltando=json.dumps(falta, ensure_ascii=False), campos=json.dumps(cps) if cps else None,
                 onde=(onde or "").strip()[:500] or None, contato=(contato or "").strip()[:500] or None,
                 client_id=cid)
    ja = um(con, "SELECT id FROM ai_pendencias WHERE status='aberta' AND user_id IS ? AND titulo=?", (user_id, titulo))
    if ja:
        atualizar(con, "ai_pendencias", ja["id"], **dados)
        pid = ja["id"]
    else:
        pid = inserir(con, "ai_pendencias", titulo=titulo, user_id=user_id, command_id=command_id, **dados)
    auditar(con, "ai.pendencia", "ai:agente_sdk", user_id=user_id, entity_type="ai_pendencia", entity_id=pid,
            detail={"titulo": titulo[:120], "faltando": falta[:10]})
    conferir(con, pid)
    return publica(um(con, "SELECT * FROM ai_pendencias WHERE id=?", (pid,)))


def resolver(con, pid, por, resolucao=None, user_id=None):
    """Fecha. Pela tela, só quem pediu ou um gerente (quem chama confere o papel)."""
    p = um(con, "SELECT * FROM ai_pendencias WHERE id=?", (int(pid),))
    if not p:
        raise LookupError("pendência não existe")
    if p["status"] != "aberta":
        return publica(p)
    atualizar(con, "ai_pendencias", p["id"], status="resolvida", resolved_at=agora(), resolved_by=por,
              resolucao=(resolucao or "").strip()[:500] or None)
    auditar(con, "ai.pendencia.resolvida", por, user_id=user_id, entity_type="ai_pendencia", entity_id=p["id"],
            detail={"resolucao": (resolucao or "")[:200]})
    return publica(um(con, "SELECT * FROM ai_pendencias WHERE id=?", (p["id"],)))


def conferir(con, pid):
    """Pendência de cliente: o que já está no card sai da lista; tudo preenchido, fecha. Devolve se fechou."""
    p = um(con, "SELECT * FROM ai_pendencias WHERE id=?", (pid,))
    if not p or p["status"] != "aberta" or not p["client_id"] or not p["campos"]:
        return False
    c = um(con, "SELECT * FROM clients WHERE id=?", (p["client_id"],))
    if not c:
        return False
    campos = _lista(p["campos"])
    resta = [k for k in campos if not str(c.get(k) or "").strip()]
    if resta == campos:
        return False
    if not resta and not _lista(p["faltando"]):
        resolver(con, pid, "sistema", "preenchido no card do cliente: "
                 + ", ".join(CAMPOS_CLIENTE[k] for k in campos if k in CAMPOS_CLIENTE))
        return True
    atualizar(con, "ai_pendencias", pid, campos=json.dumps(resta) if resta else None)
    return False


def abertas(con, user_id=None, limit=50, offset=0):
    where, par = "p.status='aberta'", []
    if user_id is not None:
        where += " AND p.user_id=?"
        par.append(user_id)
    total = um(con, f"SELECT COUNT(*) AS n FROM ai_pendencias p WHERE {where}", par)["n"]
    itens = [publica(p) for p in todos(con, f"""SELECT p.*, u.name AS quem FROM ai_pendencias p
                                                 LEFT JOIN users u ON u.id=p.user_id WHERE {where}
                                                 ORDER BY p.id LIMIT ? OFFSET ?""", (*par, limit, offset))]
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


def contexto(con, user_id):
    """Para o prompt de cada comando: o que esta pessoa ainda deve completar."""
    if not user_id:
        return ""
    for p in todos(con, "SELECT id FROM ai_pendencias WHERE status='aberta' AND user_id=?", (user_id,)):
        conferir(con, p["id"])
    ps = abertas(con, user_id, limit=MAX_NO_CONTEXTO)["itens"]
    if not ps:
        return ""
    linhas = [f"- #{p['id']} {p['titulo']}: falta {', '.join(p['faltando'])}"
              + (f" · contato: {p['contato']}" if p.get("contato") else "") for p in ps]
    return ("\n\nPENDÊNCIAS ABERTAS DE QUEM ESTÁ PEDINDO (registros que você criou incompletos). Se esta mensagem "
            "traz o que falta, complete o registro e chame pendencia_resolver. Se não traz, lembre no fim da resposta, "
            "numa linha curta, o que ainda falta:\n" + "\n".join(linhas))


def rodada(con, avisar=None):
    """A rodada de aviso: confere os cards, e manda um push por pessoa com o que ela ainda deve."""
    if avisar is None:
        from command_center.api.push import avisar
    for p in todos(con, "SELECT id FROM ai_pendencias WHERE status='aberta'"):
        conferir(con, p["id"])
    por_pessoa = {}
    for p in todos(con, "SELECT * FROM ai_pendencias WHERE status='aberta' AND user_id IS NOT NULL ORDER BY id"):
        por_pessoa.setdefault(p["user_id"], []).append(publica(p))
    avisos = 0
    for uid, ps in por_pessoa.items():
        primeiro = ps[0]
        corpo = (f"{primeiro['titulo']}: falta {', '.join(primeiro['faltando'])}"
                 + (f" · e mais {len(ps) - 1}" if len(ps) > 1 else ""))
        titulo = "Falta completar 1 registro" if len(ps) == 1 else f"Faltam completar {len(ps)} registros"
        avisar(con, [uid], titulo, corpo[:180], "/ops/ai")
        con.execute(f"UPDATE ai_pendencias SET rodadas=rodadas+1, ultimo_aviso=? WHERE id IN ({','.join('?' * len(ps))})",
                    (agora(), *[p["id"] for p in ps]))
        avisos += 1
    con.commit()
    return {"ok": True, "pessoas": avisos, "abertas": sum(len(v) for v in por_pessoa.values())}


# ------------------------------------------------------------------ para o agente
def ferramentas_ia():
    """(nome, descrição, propriedades, obrigatórios, função(con, user_id, command_id, **args))."""
    def registrar_(con, uid, cmd, titulo, faltando, onde=None, client_id=None, campos=None, contato=None, **_):
        return registrar(con, titulo, faltando, user_id=uid, command_id=cmd, onde=onde, client_id=client_id,
                         campos=campos, contato=contato)

    def resolver_(con, uid, cmd, id, resolucao=None, **_):
        p = um(con, "SELECT user_id FROM ai_pendencias WHERE id=?", (int(id),))
        if not p:
            return {"erro": "pendência não existe"}
        return resolver(con, int(id), "ia", resolucao, user_id=uid)

    def abertas_(con, uid, cmd, **_):
        return abertas(con, uid)["itens"]

    return [
        ("pendencia_registrar",
         "Registre o que ficou faltando num registro que você CRIOU com dados incompletos (tarefa, cliente, pedido, "
         "invoice, estimate). Quem pediu recebe avisos até completar. Use depois de criar, nunca no lugar de criar.",
         {"titulo": {"type": "string", "description": "o que foi criado, ex.: 'Tarefa: aula de kart do João Silva em 14/10'"},
          "faltando": {"type": "array", "items": {"type": "string"},
                       "description": "o que falta e NÃO é campo do card, em português simples: 'horário', 'tamanho do macacão'"},
          "onde": {"type": "string", "description": "link ou lugar do registro criado"},
          "client_id": {"type": "integer", "description": "id do cliente no painel, quando houver"},
          "campos": {"type": "array", "items": {"type": "string", "enum": list(CAMPOS_CLIENTE)},
                     "description": "campos do card do cliente que faltam: email, phone, pilot_name, pilot_dob (o painel confere sozinho e fecha quando forem preenchidos)"},
          "contato": {"type": "string", "description": "contato encontrado para pedir o que falta (onde achou)"}},
         ["titulo"], registrar_),
        ("pendencia_resolver", "Feche uma pendência quando o que faltava foi completado.",
         {"id": {"type": "integer"}, "resolucao": {"type": "string", "description": "o que foi completado"}},
         ["id"], resolver_),
        ("pendencias_abertas", "As pendências abertas de quem está pedindo.", {}, [], abertas_),
    ]
