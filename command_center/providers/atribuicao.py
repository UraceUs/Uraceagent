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

# REGRA DO DONO (22/09), e ela manda em tudo aqui dentro:
#
#     "Nunca colocar serviço de outro cliente em card de outro cliente."
#
# Então na dúvida NÃO se escolhe: abre-se um card com o nome exatamente como está
# no título. "Mike_Prep for Orlando Cup" vira um card "Mike" ao lado do Mike
# Fattuta e do Mike Davies — ele pediu assim, e a lógica é dele: um card "Mike"
# com um serviço é ruído que ele une num clique; o serviço do Mike Davies dentro
# do card do Mike Fattuta é dado errado que ninguém vê.
#
# O mesmo vale para nome de uma palavra só sem card: "G.J" tem 19 serviços e não
# tem nome completo — "pode colocar como G.J" (dono).
NOTA_CARD_NOVO = ("Card aberto pela varredura de 22/09 com o nome como aparece no título "
                  "do Asana. Se for a mesma pessoa de outro card, una pelo painel.")


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
        iguais, quase = [], []
        for c in clientes:
            for campo in ("pilot_name", "name"):
                p = _partes(c[campo])
                if not p:
                    continue
                if p0 in (p[0], p[-1]):
                    iguais.append((c, f"{'primeiro' if p0 == p[0] else 'último'} nome de {c[campo]}"))
                    break
                perto = next((x for x in (p[0], p[-1])
                              if len(p0) >= 5 and identidade._lev(p0, x) <= 1), None)
                if perto:
                    quase.append((c, f"quase o {'primeiro' if perto == p[0] else 'último'} "
                                     f"nome de {c[campo]} (1 letra)"))
                    break
        # igual ganha de parecido: "Martin" é o Martin Jaramillo, não o Bruno Martins
        if iguais:
            return iguais
        if quase:
            return quase
    return []


def parecem_a_mesma_pessoa(a, b):
    """Dois CARDS que provavelmente são a mesma criança, escrita de dois jeitos.

    Mais largo que `identidade.parecido` de propósito, porque aqui não se une nada:
    serve só para dizer ao dono "una estes dois quando quiser". Pega o que ele achou
    no cadastro em 22/09: Charlie Marron × Charlie Marrom, Liam Burghol ×
    Liam Bourgnhol, Alexander Savage × Alex savage."""
    for na in identidade._nomes(a):
        for nb in identidade._nomes(b):
            if identidade.parecido(na, nb):
                return True
            pa, pb = _partes(na), _partes(nb)
            if len(pa) < 2 or len(pb) < 2:
                continue
            if pa[-1] == pb[-1] and _um_encurta_o_outro(pa[0], pb[0]):
                return True                      # Alexander Savage × Alex savage
            if pa[0] == pb[0] and identidade._lev(pa[-1], pb[-1]) <= 2:
                return True                      # Liam Burghol × Liam Bourgnhol
    return False


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
                   email=None, notes=NOTA_CARD_NOVO, updated_at=agora())


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

    movidos, ja_certos, criados, unir = [], 0, [], []
    ordem = sorted(por_nome, key=lambda n: (-len(n.split()), -len(n), n.lower()))
    for nome in ordem:
        clientes = todos(con, "SELECT * FROM clients")          # relê: pode ter nascido card na volta anterior
        cliente, motivo = resolver(con, nome, clientes)
        if cliente is None:
            # Sem card, ou mais de um candidato. A regra do dono não abre exceção:
            # na dúvida o serviço NÃO encosta no card de ninguém — abre o seu.
            parecidos = [c for c, _ in candidatos_para(con, nome, clientes)]
            criados.append({"nome": nome, "servicos": len(por_nome[nome]), "porque": motivo,
                            "titulos": [t["title"] for t in por_nome[nome][:3]]})
            if parecidos:
                unir.append({"nome": nome, "servicos": len(por_nome[nome]), "parecidos": [
                    {"id": c["id"], "nome": c["pilot_name"] or c["name"],
                     "mesma_pessoa": parecem_a_mesma_pessoa({"name": nome, "pilot_name": None}, c)}
                    for c in parecidos[:5]]})
            if not criar_cards:
                continue
            if aplicar:
                cid = _criar_card(con, nome)
                cliente = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
                motivo = "card próprio (na dúvida, nunca o de outro)"
            else:
                for t in por_nome[nome]:
                    movidos.append({"task_id": t["id"], "title": t["title"], "pessoa": nome,
                                    "de": t["client_id"], "para": None,
                                    "para_nome": f"{nome} (card novo)", "motivo": motivo})
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
            "movidos": movidos, "criados": criados, "unir": unir, "sem_nome": sem_nome}


def resumo(rel):
    """Uma linha por bucket, para log e para a tela."""
    return (f"{rel['tarefas']} serviços · {len(rel['movidos'])} movidos · {rel['ja_certos']} já certos · "
            f"{len(rel['criados'])} cards novos · {len(rel['unir'])} para você unir · "
            f"{len(rel['sem_nome'])} sem nome no título")
