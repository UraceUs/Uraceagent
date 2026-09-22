"""De quem é cada serviço.

Dono, 22/09: ao marcar uma sessão nova para o David Pera ele abriu o card e viu
**113 serviços** — e 112 eram de outras pessoas (Jude Cook, Harley Keeble,
Alexander Jacoby, Brody Robbin, Alex Xikis, Charlie Marron…). O título do Asana
sempre diz de quem é o serviço; o painel é que não estava lendo.

Duas metades no conserto:

  1. `identidade.pessoa_do_titulo` tira o NOME do título — reescrito no mesmo dia
     com a lista real do dono como gabarito (ele marcou entre parênteses onde
     estava o nome em cada formato). Antes acertava 27 de 70; agora, 70.
  2. Este módulo decide a qual CARD aquele nome pertence. Quando não dá para
     decidir sozinho, devolve para humano em vez de chutar — "Alexander" pode ser
     o Savage ou o Jacoby, e unir no escuro é criar o mesmo problema do outro
     lado. Regra da casa desde 04/09.
"""
import re

from command_center.db import agora, inserir, todos, um
from command_center.providers import identidade

# Nome de uma palavra só é sinal fraco: serve para achar o card, nunca para criar
# um. "Charlie" vira serviço do Charlie Marron se ele existir; se não existir,
# fica para o humano — criar um card "Charlie" ao lado de "Charlie Marron" é
# fabricar o duplicado que a gente passa a vida unindo.
MINIMO_PARA_CRIAR = 2          # palavras


def _partes(nome):
    return identidade.normaliza(nome)


def _um_encurta_o_outro(a, b):
    """'alex' × 'alexander': um é começo do outro, com pelo menos 3 letras em comum."""
    if not a or not b or a == b:
        return a == b
    curto, longo = (a, b) if len(a) <= len(b) else (b, a)
    return len(curto) >= 3 and longo.startswith(curto)


def _inicial_de(nome):
    """('Charlie M') → ('charlie', 'm') quando a última palavra é inicial abreviada."""
    p = (nome or "").split()
    if len(p) == 2 and identidade._RX_INICIAL.match(p[1]):
        return identidade.normaliza(p[0])[0] if identidade.normaliza(p[0]) else None, p[1][0].lower()
    return None, None


def candidatos_para(con, nome, clientes=None):
    """Os cards que aquele nome PODE ser, em camadas de confiança.

    Devolve a PRIMEIRA camada que tiver alguém — não mistura "nome igual" com
    "primeiro nome bate", senão um homônimo fraco empata com o certo."""
    alvo = (nome or "").strip()
    if not alvo:
        return []
    clientes = clientes if clientes is not None else todos(con, "SELECT * FROM clients")
    chave = identidade.chave_exata(alvo)
    partes = _partes(alvo)

    exatos = [(c, "nome igual") for c in clientes
              if chave and (identidade.chave_exata(c["name"]) == chave
                            or identidade.chave_exata(c["pilot_name"]) == chave)]
    if exatos:
        return exatos

    if len(partes) >= 2:
        quase = [(c, "nome quase igual") for c in clientes
                 if identidade.mesmo_nome(alvo, c["name"] or "")
                 or (c["pilot_name"] and identidade.mesmo_nome(alvo, c["pilot_name"]))]
        if quase:
            return quase

    # "Alex Savage" → Alexander Savage: sobrenome igual e primeiro nome encurtado.
    # `mesmo_nome` não serve aqui de propósito — ela decide UNIÃO de cards, e alargá-la
    # faria o painel unir gente no escuro. Aqui só se escolhe para onde vai o serviço.
    if len(partes) >= 2:
        apelidos = []
        for c in clientes:
            for campo in ("pilot_name", "name"):
                p = _partes(c[campo])
                if len(p) >= 2 and p[-1] == partes[-1] and _um_encurta_o_outro(partes[0], p[0]):
                    apelidos.append((c, f"apelido de {c[campo]}"))
                    break
        if apelidos:
            return apelidos

    # "Charlie M" → Charlie Marron: primeiro nome igual e sobrenome começando pela inicial
    primeiro, inicial = _inicial_de(alvo)
    if primeiro and inicial:
        por_inicial = []
        for c in clientes:
            for campo in ("pilot_name", "name"):
                p = _partes(c[campo])
                if len(p) >= 2 and p[0] == primeiro and p[-1].startswith(inicial):
                    por_inicial.append((c, f"inicial abreviada de {c[campo]}"))
                    break
        if por_inicial:
            return por_inicial

    # uma palavra só: bate com o primeiro OU o último nome de alguém ("Savage" →
    # Alexander Savage, "Branson" → Branson Silva, "Brason" → Branson por 1 letra)
    if len(partes) == 1:
        p0 = partes[0]
        por_parte = []
        for c in clientes:
            for campo in ("pilot_name", "name"):
                p = _partes(c[campo])
                if not p:
                    continue
                if p0 in (p[0], p[-1]):
                    por_parte.append((c, f"{'primeiro' if p0 == p[0] else 'último'} nome de {c[campo]}"))
                    break
                perto = next((x for x in (p[0], p[-1])
                               if len(p0) >= 5 and identidade._lev(p0, x) <= 1), None)
                if perto:
                    por_parte.append((c, f"quase o {'primeiro' if perto == p[0] else 'último'} "
                                         f"nome de {c[campo]} (1 letra)"))
                    break
        if por_parte:
            return por_parte
    return []


def resolver(con, nome, clientes=None):
    """(cliente, motivo). Cliente None quando não há card ou quando há mais de um."""
    cands = candidatos_para(con, nome, clientes)
    if len(cands) == 1:
        return cands[0][0], cands[0][1]
    if not cands:
        return None, "sem card"
    quem = ", ".join(f"#{c['id']} {c['pilot_name'] or c['name']}" for c, _ in cands[:4])
    return None, f"ambíguo entre {quem}"


def _criar_card(con, nome):
    return inserir(con, "clients", source="asana", status="ACTIVE", name=nome,
                   email=None, updated_at=agora())


def redistribuir(con, aplicar=False, criar_cards=True, projeto="U-RACE"):
    """Varre TODOS os serviços e põe cada um no card de quem é.

    `aplicar=False` é a varredura: não escreve nada, só diz o que mudaria. Com
    `aplicar=True` move o que é certo e deixa o duvidoso para o humano.

    Processa os nomes do mais completo para o mais curto de propósito: assim
    "Charlie Marron" ganha (ou acha) o card antes de "Charlie M" ser procurado, e
    a forma curta cai no card certo em vez de abrir um segundo."""
    tarefas = todos(con, "SELECT id, client_id, title FROM tasks WHERE project=? OR ? IS NULL",
                    (projeto, projeto))
    por_nome = {}
    sem_nome = []
    for t in tarefas:
        pessoa = identidade.pessoa_do_titulo(t["title"])
        if not pessoa:
            sem_nome.append({"task_id": t["id"], "title": t["title"], "client_id": t["client_id"]})
            continue
        por_nome.setdefault(pessoa, []).append(t)

    movidos, ja_certos, ambiguos, criados, sem_card = [], 0, [], [], []
    ordem = sorted(por_nome, key=lambda n: (-len(n.split()), -len(n), n.lower()))
    for nome in ordem:
        clientes = todos(con, "SELECT * FROM clients")          # relê: pode ter nascido card na volta anterior
        cliente, motivo = resolver(con, nome, clientes)
        if cliente is None and motivo == "sem card":
            if criar_cards and len(nome.split()) >= MINIMO_PARA_CRIAR:
                criados.append({"nome": nome, "servicos": len(por_nome[nome])})
                motivo = "card novo"
                if aplicar:
                    cid = _criar_card(con, nome)
                    cliente = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
                else:
                    # varredura: o card ainda não existe, mas o movimento existe e
                    # tem de aparecer no relatório — senão o dono vê menos do que vai acontecer
                    for t in por_nome[nome]:
                        movidos.append({"task_id": t["id"], "title": t["title"], "pessoa": nome,
                                        "de": t["client_id"], "para": None, "para_nome": nome,
                                        "motivo": motivo})
                    continue
            else:
                sem_card.append({"nome": nome, "servicos": len(por_nome[nome]),
                                 "porque": "nome de uma palavra só: não invento card",
                                 "titulos": [t["title"] for t in por_nome[nome][:3]]})
                continue
        if cliente is None:
            if motivo != "sem card":
                ambiguos.append({"nome": nome, "servicos": len(por_nome[nome]), "porque": motivo,
                                 "titulos": [t["title"] for t in por_nome[nome][:3]]})
            continue
        for t in por_nome[nome]:
            if t["client_id"] == cliente["id"]:
                ja_certos += 1
                continue
            movidos.append({"task_id": t["id"], "title": t["title"], "pessoa": nome,
                            "de": t["client_id"], "para": cliente["id"],
                            "para_nome": cliente["pilot_name"] or cliente["name"], "motivo": motivo})
            if aplicar:
                con.execute("UPDATE tasks SET client_id=?, synced_at=? WHERE id=?",
                            (cliente["id"], agora(), t["id"]))
    if aplicar:
        con.commit()
    return {"aplicado": bool(aplicar), "tarefas": len(tarefas), "ja_certos": ja_certos,
            "movidos": movidos, "criados": criados, "ambiguos": ambiguos,
            "sem_card": sem_card, "sem_nome": sem_nome}


def resumo(rel):
    """Uma linha por bucket, para log e para a tela."""
    return (f"{rel['tarefas']} serviços · {len(rel['movidos'])} movidos · {rel['ja_certos']} já certos · "
            f"{len(rel['criados'])} cards novos · {len(rel['ambiguos'])} ambíguos · "
            f"{len(rel['sem_card'])} sem card · {len(rel['sem_nome'])} sem nome no título")
