#!/usr/bin/env python3
"""Mantém o campo "Status da ordem" e a SEÇÃO em sincronia no Shipping Orders.

O problema (achado em 28/08): o estado de um pedido está escrito em dois
lugares independentes -- o campo de status e o quadro (seção) onde a
tarefa está. Mexer em um e esquecer o outro faz os dois discordarem.

A regra, decidida pelo dono: sincronia NOS DOIS SENTIDOS. Quando o status
muda, a tarefa anda para o quadro certo; quando alguém arrasta a tarefa
para outro quadro, o status acompanha.

Como o empate é resolvido: A ÚLTIMA ALTERAÇÃO VENCE. Não é escolha
teórica -- foi validada num caso real. Na tarefa "4 Pieces Hour Meters"
o Eduardo concluiu às 19:32:29 e moveu para "Cancelled" às 19:32:53; o
campo nunca foi tocado depois. A seção era a informação mais nova, e era
a correta. O histórico do Asana (stories) diz exatamente isso, então é
dele que tiramos a resposta -- nunca de um chute.

Seções que NÃO são status ("Locations", "Alphaline Suits", "Cannotops",
"Seção sem título") são deixadas em paz: ali a seção significa categoria,
não estado. Mover uma tarefa de lá destruiria a organização deles.

Uso:
    export ASANA_TOKEN=...            # Personal Access Token (ver docs)
    python3 adminai/asana_status_sync.py            # simulação (padrão)
    python3 adminai/asana_status_sync.py --aplicar  # escreve no Asana
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://app.asana.com/api/1.0"
PROJETO_SHIPPING = "1215968721507536"
CAMPO_STATUS = "1215973949424917"

# status (opção do enum) -> seção do quadro. Os dois lados foram lidos da
# fonte em 28/08; "Payment pending" e "Refunded" foram criados nesse dia,
# porque existiam como status e não existiam como quadro -- sem eles a
# sincronia não teria para onde mover o pedido.
STATUS_PARA_SECAO = {
    "Order Created":   ("1215973949424918", "1215973949234108"),
    "Shipped":         ("1215973949424919", "1215973949234109"),
    "Arrived":         ("1215973949424920", "1215973949234110"),
    "Pending/Review":  ("1215973949424921", "1215973949234111"),
    "Payment pending": ("1215973949424959", "1217953854755118"),
    "Refunded":        ("1216770934507250", "1217953805649184"),
    "Cancelled":       ("1217677231456961", "1216267652449391"),
}
# a seção "Pending/Needs review" e o status "Pending/Review" são o mesmo
# estado com nomes diferentes -- daí o mapa por gid, não por nome.
SECAO_PARA_STATUS = {sec: (nome, opt) for nome, (opt, sec) in STATUS_PARA_SECAO.items()}

# Aqui a seção quer dizer categoria, não estado. Nunca mover daqui.
SECOES_FORA_DO_FLUXO = {
    "1215968721507537": "Seção sem título",
    "1215973949424928": "Alphaline Suits",
    "1215973949424927": "Cannotops",
    "1216012208422132": "Locations",
}


def _req(caminho, metodo="GET", corpo=None):
    token = os.environ.get("ASANA_TOKEN")
    if not token:
        sys.exit("ERRO: falta ASANA_TOKEN no ambiente. Veja docs/adminai/"
                 "automacao-status-secao.md para gerar o token.")
    dados = json.dumps({"data": corpo}).encode() if corpo is not None else None
    req = urllib.request.Request(f"{API}{caminho}", data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["data"]
    except urllib.error.HTTPError as e:
        # nunca engolir erro: quem chama precisa saber que NÃO foi aplicado
        sys.exit(f"ERRO HTTP {e.code} em {metodo} {caminho}: {e.read()[:400]!r}")


def tarefas_do_projeto():
    campos = ("gid,name,completed,memberships.section.gid,"
              "memberships.section.name,custom_fields.gid,"
              "custom_fields.enum_value.gid,custom_fields.enum_value.name")
    saida, offset = [], None
    while True:
        q = {"project": PROJETO_SHIPPING, "opt_fields": campos, "limit": 100}
        if offset:
            q["offset"] = offset
        r = _req(f"/tasks?{urllib.parse.urlencode(q)}")
        saida.extend(r)
        # a paginação vem no envelope; _req devolve só data, então uma
        # página cheia é o sinal de que pode haver mais
        if len(r) < 100:
            return saida
        offset = r[-1]["gid"]


def _secao_no_projeto(tarefa):
    for m in tarefa.get("memberships", []):
        sec = (m.get("section") or {}).get("gid")
        if sec in SECAO_PARA_STATUS or sec in SECOES_FORA_DO_FLUXO:
            return sec
    return None


def _status_da_tarefa(tarefa):
    for cf in tarefa.get("custom_fields", []):
        if cf.get("gid") == CAMPO_STATUS:
            ev = cf.get("enum_value") or {}
            return ev.get("name"), ev.get("gid")
    return None, None


def quem_mudou_por_ultimo(task_gid):
    """Lê o histórico e diz o que mudou mais recentemente: 'secao', 'campo'
    ou None. É isto que desempata -- não presumimos nada."""
    q = urllib.parse.urlencode({"opt_fields": "created_at,resource_subtype",
                                "limit": 100})
    stories = _req(f"/tasks/{task_gid}/stories?{q}")
    ult_secao = ult_campo = None
    for s in stories:  # a API devolve em ordem cronológica
        sub = s.get("resource_subtype") or ""
        if sub == "section_changed":
            ult_secao = s.get("created_at")
        elif "custom_field" in sub:
            ult_campo = s.get("created_at")
    if ult_secao and ult_campo:
        return "secao" if ult_secao > ult_campo else "campo"
    if ult_secao:
        return "secao"
    if ult_campo:
        return "campo"
    return None


def main():
    aplicar = "--aplicar" in sys.argv
    conflitos, ok, pulados, sem_status = [], 0, [], []

    for t in tarefas_do_projeto():
        sec = _secao_no_projeto(t)
        nome_status, gid_status = _status_da_tarefa(t)

        if sec in SECOES_FORA_DO_FLUXO:
            pulados.append((t["name"], SECOES_FORA_DO_FLUXO[sec]))
            continue
        if not nome_status:
            sem_status.append((t["gid"], t["name"]))
            continue

        esperada = STATUS_PARA_SECAO.get(nome_status, (None, None))[1]
        if sec == esperada:
            ok += 1
            continue
        conflitos.append({
            "gid": t["gid"], "nome": t["name"], "status": nome_status,
            "gid_status": gid_status, "secao_atual": sec,
            "secao_esperada": esperada,
        })

    print(f"== sincronia status x seção — Shipping Orders "
          f"({'APLICANDO' if aplicar else 'simulação'}) ==")
    print(f"-- {ok} tarefa(s) já consistentes")
    print(f"-- {len(pulados)} fora do fluxo de status (categoria, não estado)")
    for nome, secao in pulados:
        print(f"     · {nome[:60]} [{secao}]")
    if sem_status:
        print(f"-- {len(sem_status)} SEM status preenchido — precisa de humano:")
        for gid, nome in sem_status:
            print(f"     · {nome[:60]} ({gid})")

    if not conflitos:
        print("-- nenhuma divergência: campo e quadro contam a mesma história")
        return 0

    print(f"-- {len(conflitos)} divergência(s):")
    for c in conflitos:
        vencedor = quem_mudou_por_ultimo(c["gid"])
        atual = SECAO_PARA_STATUS.get(c["secao_atual"], ("?",))[0]
        if vencedor == "secao" and c["secao_atual"] in SECAO_PARA_STATUS:
            novo_nome, novo_opt = SECAO_PARA_STATUS[c["secao_atual"]]
            acao = f'campo "{c["status"]}" -> "{novo_nome}" (quadro venceu)'
            corpo = {"custom_fields": {CAMPO_STATUS: novo_opt}}
        else:
            acao = f'mover para o quadro de "{c["status"]}" (campo venceu)'
            corpo = None
        print(f"   · {c['nome'][:55]}: quadro={atual} campo={c['status']} => {acao}")
        if not aplicar:
            continue
        if corpo:
            _req(f"/tasks/{c['gid']}", "PUT", corpo)
        else:
            _req(f"/sections/{c['secao_esperada']}/addTask", "POST",
                 {"task": c["gid"]})
        _req(f"/tasks/{c['gid']}/stories", "POST", {"text":
             f"[IA ADM] Sincronia automática status x quadro: {acao}. "
             f"Critério: a última alteração vence (lido do histórico da tarefa)."})
        print("     aplicado + comentário registrado na tarefa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
