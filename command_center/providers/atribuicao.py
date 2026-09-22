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
NOTA_CARD_NOVO = identidade.NOTA_CARD_NOVO
e_balde = identidade.e_balde


def _vivos(con):
    """Os cards que contam: 'separado' (corrida, tarefa) não é dono de serviço nenhum."""
    return todos(con, "SELECT * FROM clients WHERE kind<>?", (identidade.SEPARADO,))


def _descricao_lida(t):
    """Já se perguntou ao Asana por esta tarefa? Vale o carimbo `desc_read_at` — descrição
    sem contato nenhum também conta como lida, senão seria relida a cada varredura."""
    keys = t.keys()
    if "desc_read_at" in keys and t["desc_read_at"]:
        return True
    return any(t[k] for k in ("resp_name", "resp_email", "resp_phone") if k in keys)


def por_contato(con, tarefa, clientes=None):
    """O dono do serviço pelo que a DESCRIÇÃO diz — e-mail, telefone, responsável —
    antes de qualquer olhar para o título.

    Dono, 22/09: "o princípio para cruzar e confirmar é usar o nome do responsável e
    informações de contato. Aplique como base de agora para frente." O título diz
    "Alex"; a descrição diz Edward Donnell, ed@…: é o Alex do Edward, e ponto.
    Devolve (cliente, motivo) ou (None, None). Só decide quando bate UM card."""
    clientes = clientes if clientes is not None else _vivos(con)
    email = (tarefa["resp_email"] or "").strip().lower() if "resp_email" in tarefa.keys() else ""
    if email:
        achados = [c for c in clientes if (c["email"] or "").strip().lower() == email
                   or (c["email_alt"] or "").strip().lower() == email]
        if len(achados) == 1:
            return achados[0], f"e-mail da descrição ({email})"
    tel = identidade.so_digitos(tarefa["resp_phone"]) if "resp_phone" in tarefa.keys() else None
    if tel:
        achados = [c for c in clientes if c["phone"] and identidade.so_digitos(c["phone"]) == tel]
        if len(achados) == 1:
            return achados[0], f"telefone da descrição ({tarefa['resp_phone']})"
    resp = tarefa["resp_name"] if "resp_name" in tarefa.keys() else None
    if resp and len(_partes(resp)) >= 2:
        chave = identidade.chave_exata(resp)
        achados = [c for c in clientes if identidade.chave_exata(c["name"]) == chave]
        if not achados:
            achados = [c for c in clientes if identidade.mesmo_nome(resp, c["name"] or "")]
        if len(achados) == 1:
            return achados[0], f"responsável da descrição ({resp})"
    return None, None


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
    clientes = clientes if clientes is not None else _vivos(con)
    chave = identidade.chave_exata(alvo)
    partes = _partes(alvo)

    # UMA PALAVRA SÓ nunca passa pelo "nome igual": um card cujo piloto é só "Alex" bate
    # exato e a checagem de ambiguidade nunca roda — o serviço do Alex Xikis ia para o
    # Alex do Edward. Nome curto vai direto para a camada de partes, que junta TODOS os
    # candidatos e deixa a dúvida aparecer. Revisão adversarial de 22/09.
    if len(partes) >= 2:
        exatos = [(c, "nome igual") for c in clientes
                  if chave and (identidade.chave_exata(c["name"]) == chave
                                or identidade.chave_exata(c["pilot_name"]) == chave)]
        if exatos:
            return exatos

        quase = [(c, "nome quase igual") for c in clientes
                 if identidade.mesmo_nome(alvo, c["name"] or "")
                 or (c["pilot_name"] and identidade.mesmo_nome(alvo, c["pilot_name"]))]
        if quase:
            return quase

        # "Alex Savage" → Alexander Savage: sobrenome igual e primeiro nome ENCURTADO,
        # e só para apelido conhecido. Prefixo solto casava Gabriel×Gabriela e
        # Maria×Mariana — irmãos, o caso mais comum numa escola de kart.
        apelidos = []
        for c in clientes:
            for campo in ("pilot_name", "name"):
                p = _partes(c[campo])
                if len(p) >= 2 and p[-1] == partes[-1] and _e_apelido_de(partes[0], p[0]):
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

    if len(partes) == 1:
        p0 = partes[0]
        # O card com exatamente este nome (o balde) entra junto: se houver outro
        # candidato, a coisa é ambígua e o serviço fica no balde — que é onde já está.
        iguais = []
        for c in clientes:
            for campo in ("name", "pilot_name"):
                p = _partes(c[campo])
                if not p:
                    continue
                if p0 in (p[0], p[-1]):
                    iguais.append((c, f"{'primeiro' if p0 == p[0] else 'último'} nome de {c[campo]}"))
                    break
        # Sem Levenshtein aqui: "Daniel" pegava "Daniela", "Bruno" pegava "Bruna",
        # "Martin" pegava "Bruno Martins". Uma letra não separa duas pessoas.
        if iguais:
            return iguais
    return []


# Apelidos que o dono usa no quadro. Prefixo solto não vale: Gabriel≠Gabriela.
_APELIDOS = {
    "alex": {"alexander", "alexandre", "alexis"}, "mike": {"michael"}, "mikey": {"michael", "mike"},
    "dan": {"daniel"}, "danny": {"daniel"}, "chris": {"christopher", "christian"},
    "matt": {"matthew"}, "nick": {"nicholas", "nicolas"}, "tony": {"anthony"},
    "will": {"william"}, "bill": {"william"}, "rob": {"robert"}, "bob": {"robert"},
    "tom": {"thomas"}, "ben": {"benjamin"}, "sam": {"samuel"}, "joe": {"joseph"},
    "jim": {"james"}, "andy": {"andrew"}, "charlie": {"charles"}, "liam": {"william"},
    "zé": {"jose"}, "ze": {"jose"}, "bia": {"beatriz"}, "gui": {"guilherme"},
    "rafa": {"rafael", "rafaela"}, "cacá": {"carlos"}, "duda": {"eduarda", "eduardo"},
}


def _e_apelido_de(curto, longo):
    """'alex' é apelido de 'alexander'? Só pela tabela, nos dois sentidos."""
    if curto == longo:
        return True
    return longo in _APELIDOS.get(curto, ()) or curto in _APELIDOS.get(longo, ())


def sugestoes_para(con, nome, clientes=None):
    """Cards que PODEM ser esta pessoa — para a lista "para você unir", nunca para
    atribuir. Aqui pode ser frouxo (1 letra, prefixo, sobrenome) porque quem decide é o
    dono; `candidatos_para` é que ficou estrito depois da revisão de 22/09."""
    clientes = clientes if clientes is not None else _vivos(con)
    partes = _partes(nome)
    if not partes:
        return []
    achados, vistos = [], set()
    for c in clientes:
        if c["id"] in vistos or e_balde(c):
            continue
        for campo in ("pilot_name", "name"):
            p = _partes(c[campo])
            if not p:
                continue
            perto = (partes[0] in (p[0], p[-1]) or partes[-1] in (p[0], p[-1])
                     or (len(partes[-1]) >= 5 and min(identidade._lev(partes[-1], x) for x in (p[0], p[-1])) <= 1)
                     or (len(partes[0]) >= 5 and min(identidade._lev(partes[0], x) for x in (p[0], p[-1])) <= 1)
                     or (len(partes) >= 2 and len(p) >= 2 and p[-1] == partes[-1]
                         and _um_encurta_o_outro(partes[0], p[0])))
            if perto:
                achados.append((c, f"parecido com {c[campo]}")); vistos.add(c["id"])
                break
    return achados


def grau_de_igualdade(a, b):
    """'confirmado' (contato ou responsável iguais — regra do dono), 'parece' (só o
    nome) ou None. O relatório marca = para o primeiro e ~ para o segundo: o dono
    decide de olho no responsável e no contato, não no primeiro nome do piloto."""
    if identidade.mesmo_contato(a, b):
        return "confirmado"
    if parecem_a_mesma_pessoa(a, b):
        return "parece"
    return None


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


def _decidido_pelo_dono(con, nome, clientes):
    """O dono já uniu um card com este nome a outro? Então é ali que o serviço vai.

    `client_merges` guarda toda união feita à mão. Sem consultar isto, a varredura
    seguinte via "Mike" como ambíguo, abria um balde novo e tirava o serviço do card
    que ele tinha escolhido — desfazendo a decisão dele a cada rodada. Revisão
    adversarial de 22/09."""
    # SÓ união feita à mão. União automática ("sync") não é decisão de ninguém — e foi
    # justamente ela que comeu o balde "Alex" dentro do Edward Donnell às 13:46 de
    # 22/09. Cair de volta nela aqui cimentaria o erro em vez de desfazê-lo.
    linhas = todos(con, "SELECT keep_id, merged_by FROM client_merges WHERE LOWER(drop_name)=LOWER(?) "
                        "AND (merged_by LIKE 'user:%' OR merged_by LIKE 'owner:%') ORDER BY id DESC", (nome,))
    for l in linhas:
        alvo = next((c for c in clientes if c["id"] == l["keep_id"]), None)
        if alvo is not None:
            return alvo, f"você uniu '{nome}' a este card"
    return None


def _criar_card(con, nome):
    return inserir(con, "clients", source="asana", status="ACTIVE", name=nome,
                   email=None, notes=NOTA_CARD_NOVO, updated_at=agora())


def redistribuir(con, aplicar=False, criar_cards=True, projeto="U-RACE", ler_descricoes=False):
    """Varre TODOS os serviços e põe cada um no card de quem é.

    `aplicar=False` é a varredura: não escreve nada, só diz o que mudaria. Com
    `aplicar=True` move o que é certo e deixa o duvidoso para o humano.

    Processa os nomes do mais completo para o mais curto de propósito: assim
    "Charlie Marron" ganha (ou acha) o card antes de "Charlie M" ser procurado, e
    a forma curta cai no card certo em vez de abrir um segundo."""
    # Serviço cuja atribuição o DONO confirmou não é mexido por varredura nenhuma.
    # Ele confirmou em 22/09 que os 18 "Savage" e 2 "Savege" do #15 são do Alexander
    # (o card foi alcançado pelo sobrenome do Kenneth) e que o "Alex" do #238 é do
    # Alex Donnell. Sem carimbo, um homônimo novo no cadastro tiraria os dois de lá.
    tarefas = todos(con, "SELECT * FROM tasks WHERE (project=? OR ? IS NULL) "
                         "AND COALESCE(client_by,'') <> 'human'", (projeto, projeto))
    confirmadas = todos(con, "SELECT COUNT(*) AS n FROM tasks WHERE (project=? OR ? IS NULL) "
                             "AND client_by='human'", (projeto, projeto))[0]["n"]
    movidos, ja_certos, criados, unir, pelo_contato, lidas = [], 0, [], [], 0, 0
    falhas_leitura = []                                     # (task_id, título, erro): NUNCA em silêncio

    def _move(t, cliente, motivo):
        nonlocal ja_certos
        if t["client_id"] == cliente["id"]:
            ja_certos += 1
            return
        movidos.append({"task_id": t["id"], "title": t["title"], "pessoa": cliente["pilot_name"] or cliente["name"],
                        "de": t["client_id"], "para": cliente["id"],
                        "para_nome": cliente["pilot_name"] or cliente["name"], "motivo": motivo})
        if aplicar:
            con.execute("UPDATE tasks SET client_id=?, synced_at=? WHERE id=?", (cliente["id"], agora(), t["id"]))

    # 1ª passada — o CONTATO da descrição decide, antes do título (princípio do dono)
    vivos = _vivos(con)
    baldes = {c["id"] for c in vivos if e_balde(c)}
    restantes = []
    for t in tarefas:
        cliente, motivo = por_contato(con, t, vivos)
        # Serviço que está num BALDE ("Mike", "Sean"…) não é "já certo": está esperando.
        # Com --ler-descricoes, ele vai buscar responsável/contato no Asana — é assim que
        # o balde se esvazia sozinho (dono, 22/09: "aplique o princípio de agora em diante").
        if not cliente and ler_descricoes and t["client_id"] in baldes and not _descricao_lida(t):
            t, erro = _ler_descricao(con, t); lidas += 1
            if erro:
                falhas_leitura.append({"task_id": t["id"], "title": t["title"], "erro": erro})
            cliente, motivo = por_contato(con, t, vivos)
            if cliente:
                motivo = f"saiu do balde: {motivo}"
        if cliente:
            _move(t, cliente, motivo); pelo_contato += 1
        else:
            restantes.append(t)

    # 2ª passada — o título, agrupado por nome
    por_nome, sem_nome = {}, []
    truncados, por_chave = set(), {}
    for t in restantes:
        d = identidade.pessoa_do_titulo_detalhe(t["title"])
        pessoa = d["nome"]
        if not pessoa:
            sem_nome.append({"task_id": t["id"], "title": t["title"], "client_id": t["client_id"]})
            continue
        # Nome que sobrou de um CORTE e ficou com uma palavra só é pista fraca: o
        # sobrenome pode ter caído no vocabulário de serviço. Não serve para achar card
        # pelo primeiro nome — vai direto para card próprio.
        if d["truncado"] and len(pessoa.split()) == 1:
            truncados.add(pessoa)
        chave = identidade.chave_exata(pessoa)
        if chave in por_chave:
            por_chave[chave][1].append(t)
        else:
            por_chave[chave] = (pessoa, [t])

    # "JOSE MIGUEL Abed" e "Jose Miguel Abed" são a mesma pessoa: grafia não abre card.
    por_nome = {nome: tarefas_ for nome, tarefas_ in por_chave.values()}
    ordem = sorted(por_nome, key=lambda n: (-len(n.split()), -len(n), n.lower()))
    for nome in ordem:
        clientes = _vivos(con)                                  # relê: pode ter nascido card na volta anterior
        if nome in truncados:
            cliente, motivo = None, "nome cortado, de uma palavra só"
        else:
            cliente, motivo = resolver(con, nome, clientes)
            if cliente is None:
                # O dono já decidiu isto à mão? Se ele uniu um balde com este nome a um
                # card, a decisão dele manda — sem isto, a varredura seguinte recriava o
                # balde e tirava o serviço do card que ele escolheu.
                cliente, motivo = _decidido_pelo_dono(con, nome, clientes) or (None, motivo)
        if cliente is None and ler_descricoes:
            # Em dúvida pelo título, a descrição pode resolver — e a partir daqui fica
            # guardada na tarefa, então a próxima varredura não pergunta ao Asana de novo.
            ainda = []
            for t in por_nome[nome]:
                if not _descricao_lida(t):
                    t, erro = _ler_descricao(con, t); lidas += 1
                    if erro:
                        falhas_leitura.append({"task_id": t["id"], "title": t["title"], "erro": erro})
                c2, m2 = por_contato(con, t, clientes)
                if c2:
                    _move(t, c2, m2); pelo_contato += 1
                else:
                    ainda.append(t)
            por_nome[nome] = ainda
            if not ainda:
                continue
        if cliente is None:
            # ANTES de abrir balde: serviço que JÁ ESTÁ num card plausível fica onde
            # está. "AIDEN - KARTING SCHOOL" está no Aidan Mills, "Garret" no Garrett
            # Curtis, "Isabel" no card Isabel — tirar de lá para um balde novo é
            # estragar o que estava certo. A regra do dono é não pôr no card de OUTRO;
            # não é mexer em quem já está em casa.
            plausiveis = {c["id"] for c, _ in candidatos_para(con, nome, clientes)}
            plausiveis |= {c["id"] for c, _ in sugestoes_para(con, nome, clientes)}
            balde = next((c for c in clientes
                          if identidade.chave_exata(c["name"]) == identidade.chave_exata(nome) and e_balde(c)), None)

            def _fica_em_casa(t):
                cid = t["client_id"]
                if cid is None:
                    return False
                if balde is not None and cid == balde["id"]:
                    return True                      # já está no balde deste nome
                atual = next((c for c in clientes if c["id"] == cid), None)
                # Card com EXATAMENTE este nome: o serviço já está em casa. Sem isto,
                # "Isabel" saía do card "Isabel" para um card novo "Isabel".
                if atual is not None and identidade.chave_exata(atual["name"]) == identidade.chave_exata(nome):
                    return True
                # Card atual é FORTE parecido ("Henryk McKay" no "Henryl McKay": mesmo
                # sobrenome, 1 letra no primeiro nome)? Então não é escolha entre duas
                # pessoas — é a mesma, escrita errada. Fica, mesmo havendo outros nomes
                # parecidos por aí.
                if atual is not None and any(identidade.parecido(nome, n) for n in identidade._nomes(atual)):
                    return True
                # UM candidato plausível só: é ele mesmo, escrito de outro jeito
                # ("AIDEN" no Aidan Mills). Havendo mais de um, o card atual foi
                # escolhido pela máquina e não por evidência — aí sai.
                return cid in plausiveis and len(plausiveis) == 1

            ja_certos += sum(1 for t in por_nome[nome] if _fica_em_casa(t))
            por_nome[nome] = [t for t in por_nome[nome] if not _fica_em_casa(t)]
            if not por_nome[nome]:
                continue
            # Sem card, ou mais de um candidato. A regra do dono não abre exceção:
            # na dúvida o serviço NÃO encosta no card de ninguém — abre o seu.
            # O balde que já existe é reaproveitado: sem isso, cada varredura criava
            # mais um "Alex" e o serviço mudava de balde para sempre.
            parecidos = [c for c, _ in sugestoes_para(con, nome, clientes)]
            if balde is None:
                criados.append({"nome": nome, "servicos": len(por_nome[nome]), "porque": motivo,
                                "titulos": [t["title"] for t in por_nome[nome][:3]]})
            if parecidos:
                unir.append({"nome": nome, "servicos": len(por_nome[nome]), "parecidos": [
                    {"id": c["id"], "nome": c["pilot_name"] or c["name"], "responsavel": c["name"],
                     "email": c["email"], "phone": c["phone"],
                     "grau": grau_de_igualdade({"name": nome, "pilot_name": None, "email": None, "phone": None}, c),
                     "mesma_pessoa": parecem_a_mesma_pessoa({"name": nome, "pilot_name": None}, c)}
                    for c in parecidos[:5]]})
            if not criar_cards:
                continue
            if balde is not None:
                cliente, motivo = balde, "balde que já existe (na dúvida, nunca o de outro)"
            elif aplicar:
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
            _move(t, cliente, motivo)
    if aplicar:
        con.commit()
    return {"aplicado": bool(aplicar), "tarefas": len(tarefas), "confirmados": confirmadas,
            "ja_certos": ja_certos,
            "pelo_contato": pelo_contato, "descricoes_lidas": lidas, "falhas_leitura": falhas_leitura,
            "movidos": movidos, "criados": criados, "unir": unir, "sem_nome": sem_nome}


def _ler_descricao(con, tarefa):
    """Busca a descrição da tarefa no Asana e guarda responsável/e-mail/telefone nela.
    Devolve (tarefa relida, erro). Falha de rede não derruba a varredura — mas também
    não some: volta em `erro`, e o relatório mostra. Engolir erro aqui foi o que fez a
    varredura de 22/09 à noite parecer "nada a resolver" sem dizer por quê."""
    from command_center.providers import chamar, sync
    gid = um(con, "SELECT external_id FROM entity_links WHERE entity_type='task' AND entity_id=? AND system='asana'",
             (tarefa["id"],))
    if not gid:
        return tarefa, "tarefa sem gid do Asana em entity_links"
    try:
        full = chamar("asana", "asana_tarefa", gid=gid["external_id"])
    except Exception as e:                                    # noqa: BLE001 - ler é o extra
        return tarefa, f"{type(e).__name__}: {str(e)[:160]}"
    r = sync._resp_da_descricao(sync.parse_descricao(full.get("notas")))
    con.execute("UPDATE tasks SET resp_name=?, resp_email=?, resp_phone=?, desc_read_at=? WHERE id=?",
                (r["resp_name"], r["resp_email"], r["resp_phone"], r["desc_read_at"], tarefa["id"]))
    con.commit()
    return um(con, "SELECT * FROM tasks WHERE id=?", (tarefa["id"],)), None


def resumo(rel):
    """Uma linha por bucket, para log e para a tela."""
    return (f"RESUMO: {rel['tarefas']} serviços · {len(rel['movidos'])} movidos · {rel['ja_certos']} já certos · "
            f"{rel.get('confirmados', 0)} confirmados por você (intocáveis) · "
            f"{rel.get('pelo_contato', 0)} decididos por contato · "
            f"{rel.get('descricoes_lidas', 0)} descrições lidas ({len(rel.get('falhas_leitura', []))} falharam) · "
            f"{len(rel['criados'])} cards novos · {len(rel['unir'])} para você unir · "
            f"{len(rel['sem_nome'])} sem nome no título")
