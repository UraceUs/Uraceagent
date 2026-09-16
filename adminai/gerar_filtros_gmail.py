#!/usr/bin/env python3
"""Gera filtros NATIVOS do Gmail a partir dos e-mails reais de cada caixa.

Pedido do dono (14/09): *"leia as tags dos dois e-mails, identifique as keywords
de cada um e coloque nativamente neles os marcadores"*. Ou seja: parar de depender
da IA para classificar o que é determinístico — quem manda o e-mail já diz onde ele
vai.

COMO FUNCIONA
  1. Para cada marcador CONFIRMADO no manual (taxonomia_gmail.py), pega uma amostra
     das mensagens que já estão nele e lê o remetente.
  2. Monta a distribuição remetente → marcadores. Um remetente só vira regra do
     marcador X se a MAIORIA das mensagens dele estiver em X (--share) e houver
     evidência suficiente (--min). Isso evita o caso Amazon, que aparece em
     "Shipping Status" e em "Finances/Shopping" ao mesmo tempo.
  3. Escreve um `mailFilters.xml` que o Gmail importa
     (Configurações → Filtros → Importar filtros) e um relatório em Markdown para
     o dono conferir ANTES de importar.

O QUE ELE NÃO FAZ, DE PROPÓSITO
  * Não escreve nada no Gmail. O escopo `gmail.modify` não cria filtro, e mesmo
    que criasse, filtro é configuração do dono: ele revisa e importa.
  * Não inventa marcador. Só usa os que ele confirmou no manual.
  * Não arquiva nada além de `wNews` — regra dele desde 28/08.
  * Não usa palavra no assunto. Remetente é evidência; palavra solta no assunto
    gera falso positivo em massa. O que não tem remetente estável vai para o
    relatório como decisão dele, não como regra chutada.

    python3 adminai/gerar_filtros_gmail.py --conta urace
    python3 adminai/gerar_filtros_gmail.py --conta support --amostra 40
"""
import argparse
import collections
import os
import re
import sys
import time
import urllib.parse
from xml.sax.saxutils import quoteattr

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))

import gmail_mcp  # noqa: E402
from command_center.providers.classificar import SISTEMA  # noqa: E402
from command_center.providers.taxonomia_gmail import FORA, MANUAL, MANUAL_SUPPORT, OK  # noqa: E402

ARQUIVAVEL = "wNews"                 # o único marcador que sai da inbox sozinho
# Pastas de histórico: mandar e-mail NOVO para lá é enterrá-lo. Arquivo por ano
# ("a triagem NÃO usa", manual do dono) e pasta de quem já saiu da empresa — o
# gerador tinha posto a Delta e um fornecedor na pasta da Manu, que saiu.
FAMILIAS_SEM_FILTRO = {"Years 2019-2023", "Ex-Funcionários"}
PASTAS_SEM_FILTRO = ("Team/Ex-Employees",)

# Regras que o dono revisou e RECUSOU (14/09). Ficam aqui para não voltarem na
# próxima geração — o gerador não tem como saber que a Hilton não é corrida.
REGRAS_RECUSADAS = {
    ("flag@dol.gov", "Banks/Idea Financial"),                     # DOL não é banco; o certo é o EB3
    ("noreply@h6.hilton.com", "RACES/F4/JFC"),                    # hotel, não corrida
    ("noreply@booking.com", "ITALO/Casamento"),                   # reserva nova não é do casamento
    ("greenlane@dwolla.com", "RACES"),                            # pagamento, não corrida
    ("info@tkart.it", "Team/Samira"),                             # o destino é o marcador do TKART
    ("info@mortgagehouz.com", "Team/Anabelly"),                   # o certo é Finances/Accounting
    ("team@user.hostinger.com", "Marketing & Sales/Comercial/Landipage Old"),   # hospedagem, não lead
    ("alejandra.anez@mylaps.com", "ITALO"),                       # MyLaps já tem filtro do dono
    ("zach.holcombe@mylaps.com", "ITALO"),
    ("alejandra.anez@mylaps.com", "CORP/Betim"),
    ("zach.holcombe@mylaps.com", "CORP/Betim"),
    ("@mylaps.com", "ITALO"),
    ("@mylaps.com", "CORP/Betim"),
    # segunda rodada de revisão do dono, 15/09
    ("@orlandokartcenter.com", "Finances/Pending Invoices ❗"),   # viraria conta a pagar fantasma
    ("mailer-daemon@googlemail.com", "Marketing & Sales/Colina | Site e ADS"),  # é e-mail devolvido
    ("@flybreeze.com", "RACES/F4/JFC"),                          # companhia aérea, não corrida
    ("payments-noreply@google.com", "Marketing & Sales/Comercial/Canais | Social Media"),  # é cobrança
    # terceira rodada — revisão da extensão, 16/09
    ("trackingupdates@fedex.com", "CORP/CORP Canotops"),         # rastreio é Shipping Status
    ("noreply.odd@dhl.com", "Suppliers/Stickers - Jake"),         # transportadora não é o fornecedor
    ("@dhl.com", "Suppliers/Stickers - Jake"),
    ("@bluegemsmgmt.com", "ITALO"),                               # é parceria, não pessoal
    ("ken@naturecoasthealthcare.com", "Team/LARA"),               # pasta de quem já saiu; fica só RACES/F4
}
RX_EMAIL = re.compile(r"<([^>]+)>")

# Regras DITADAS pelo dono (16/09), não inferidas da amostra. A única exceção à regra
# "nada de assunto": remetente fixo (DocuSign) + frase fixa (o nome do modelo da waiver).
# (busca do Gmail para `hasTheWord`, marcador, arquivar?) — só entram se o marcador
# existir na caixa.
REGRAS_DO_DONO = [
    ("from:(docusign.net OR docusign.com)", "Softwares|Apps/Docusign", False),
    ('from:(docusign.net) subject:("Waiver of Liability") {subject:"Please Complete" subject:"Completed:"}',
     "Waivers", False),
]
# Remetentes genéricos demais para virar regra: pegariam a caixa inteira.
DOMINIOS_PROIBIDOS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"}
# Domínios de PLATAFORMA DE ENVIO, usados por milhares de empresas: nunca viram regra de
# domínio. `@g.shopifyemail.com` não é a loja do Orlando Kart Center — é toda loja Shopify;
# `@shared1.ccsend.com` é o Constant Contact inteiro. O endereço individual
# (`store+57444597856@t.shopifyemail.com`) continua valendo: ele é preciso, o domínio não.
# (Revisão da extensão em 16/09.)
# Transportadora NÃO entra aqui: `@ups.com` → Shipping Status é regra boa (na caixa do dono,
# UPS é sempre envio). O erro "DHL → fornecedor Jake" é caso a caso, e vai para as recusadas.
DOMINIOS_COMPARTILHADOS = ("shopifyemail.com", "ccsend.com", "hs-send.com", "hubspotemail.net",
                           "mailchimpapp.net", "mcsv.net", "sendgrid.net", "mailgun.org", "rsgsv.net")


def _endereco(de):
    """'Fulano <a@b.com>' -> 'a@b.com', em minúsculas."""
    m = RX_EMAIL.search(de or "")
    bruto = (m.group(1) if m else (de or "")).strip().strip("<>").lower()
    return bruto if "@" in bruto else ""


def marcadores_da_caixa(conta):
    """Abre a caixa e devolve os marcadores dela.

    São DOIS carregamentos, e esquecer o segundo custou uma rodada: `_carregar_env`
    lê o ~/.urace/adminai.env, mas quem preenche `_contas` com os tokens é
    `_carregar_contas`. Sem ele o Gmail responde "conta não configurada.
    Disponíveis: []" — que parece falta de credencial e não é."""
    gmail_mcp._carregar_env()
    gmail_mcp._carregar_contas()
    if conta not in gmail_mcp._contas:
        sys.exit(f"ERRO: a caixa {conta}@ não tem token neste servidor "
                 f"({gmail_mcp._sem_token.get(conta, '?')}).\n"
                 f"Rode: python3 adminai/google_auth.py --conta {conta}")
    return gmail_mcp._mapa_labels(conta)


def _req(conta, url, tentativas=4):
    """Como o _req do MCP, mas espera e tenta de novo quando o Gmail limita."""
    for n in range(tentativas):
        try:
            return gmail_mcp._req(conta, url)
        except Exception as e:
            texto = str(e)
            if n == tentativas - 1 or not any(c in texto for c in ("429", "403", "500", "503")):
                raise
            time.sleep(2 ** n)
    return {}


def amostrar(conta, nomes, amostra, mapa=None, verboso=True):
    """(remetente -> Counter(marcador), remetente -> nº de MENSAGENS).

    Os dois são necessários. A primeira versão usava a soma dos marcadores como
    denominador e isso reprovava justamente os remetentes que importam: uma
    mensagem da UPS que está em `Shipping Status` E em `Finances/Shopping` contava
    2, a fatia de cada marcador virava 50%, e nenhum dos dois passava. Era por isso
    que `Shipping Status`, `wNews`, `Finances/Shopping` e `Banks/PayPal` — os
    maiores da caixa — saíam sem regra nenhuma."""
    por_remetente = collections.defaultdict(collections.Counter)
    mensagens = collections.Counter()
    mapa = mapa or gmail_mcp._mapa_labels(conta)
    id_para_nome = {v: k for k, v in mapa.items()}
    vistos = set()
    for i, nome in enumerate(nomes, 1):
        # POR ID, não por nome: `q=label:"Softwares|Apps/Docusign"` devolve ZERO porque o
        # Gmail interpreta o `|` na consulta. Foi assim que todos os `Softwares|Apps/*`,
        # `LOC | Practice/*` e `Kart Racing School | Client talks` apareceram vazios —
        # e `LOC | Practice/Practice Orlando` tem 370 conversas.
        q = urllib.parse.urlencode({"labelIds": mapa[nome], "maxResults": amostra})
        try:
            r = _req(conta, f"{gmail_mcp.GMAIL}/messages?{q}")
        except Exception as e:
            print(f"  ! {nome}: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
            continue
        msgs = r.get("messages", [])
        if verboso:
            print(f"[{i}/{len(nomes)}] {nome}: {len(msgs)} mensagens", file=sys.stderr)
        for m in msgs:
            if m["id"] in vistos:
                continue
            vistos.add(m["id"])
            try:
                d = _req(conta, f"{gmail_mcp.GMAIL}/messages/{m['id']}?format=metadata&metadataHeaders=From")
            except Exception:
                continue
            end = _endereco(gmail_mcp._cabecalho(d, "From"))
            if not end or end.split("@")[-1] in DOMINIOS_PROIBIDOS:
                continue
            mensagens[end] += 1
            # a mensagem conta para TODOS os marcadores que ela tem: é assim que
            # a ambiguidade (Amazon em dois marcadores) aparece nos números
            for lid in d.get("labelIds", []):
                alvo = id_para_nome.get(lid)
                if alvo and alvo in nomes:
                    por_remetente[end][alvo] += 1
    return por_remetente, mensagens


def _recusado(remetente, alvo):
    """Regra que não deve nascer: pasta de histórico, ou par que o dono já recusou.

    Recusar o domínio recusa os endereços dele: sem isso, tirar
    `@orlandokartcenter.com → Pending Invoices` deixava `arielle@orlandokartcenter.com`
    entrar sozinho no mesmo marcador, pela porta do endereço individual."""
    if alvo.split("/")[0] in FAMILIAS_SEM_FILTRO or alvo.startswith(PASTAS_SEM_FILTRO):
        return True
    if (remetente, alvo) in REGRAS_RECUSADAS:
        return True
    return not remetente.startswith("@") and ("@" + _dominio(remetente), alvo) in REGRAS_RECUSADAS


def _dominio(endereco):
    return endereco.split("@")[-1]


def por_dominio(por_remetente, mensagens):
    """Junta os remetentes por domínio: (dominio -> Counter(marcador), dominio -> mensagens,
    dominio -> quantos endereços distintos).

    É daqui que sai a cobertura que o dono pediu ("nativo o máximo que der"). Regra por
    endereço só pega o endereço que já apareceu na amostra: `mcinfo@ups.com` vira filtro,
    mas `tracking@ups.com` que chegar amanhã não. Regra por domínio pega os dois — e os
    que ainda nem existem."""
    contagens = collections.defaultdict(collections.Counter)
    msgs = collections.Counter()
    enderecos = collections.defaultdict(set)
    for end, c in por_remetente.items():
        d = _dominio(end)
        contagens[d].update(c)
        msgs[d] += mensagens.get(end, 0)
        enderecos[d].add(end)
    return contagens, msgs, enderecos


def regras(por_remetente, mensagens, share, minimo, max_marcadores=2):
    """marcador -> [(remetente, acertos, mensagens)], só onde a evidência sustenta.

    `minimo` conta as mensagens NAQUELE marcador, não o total do remetente: 2 de 3
    passava na versão anterior e foi assim que um apelido do eBay virou regra do
    `Finances/Anderson_EB3` e uma newsletter da F1 virou `Platforms & Subscriptions`.
    Um remetente pode legitimamente virar regra de dois marcadores (a UPS está em
    `Shipping Status` e em `Finances/Shopping`): o Gmail aceita os dois filtros."""
    saida = collections.defaultdict(list)
    for end, contagem in por_remetente.items():
        total = mensagens.get(end, 0)
        if not total:
            continue
        for alvo, n in contagem.most_common(max_marcadores):
            if _recusado(end, alvo):
                continue
            if n >= minimo and n / total >= share:
                saida[alvo].append((end, n, total))
    # promove a domínio o que se sustenta no domínio inteiro, e some com os endereços
    # daquele domínio que viraram redundantes
    dcont, dmsgs, dends = por_dominio(por_remetente, mensagens)
    for dom, contagem in dcont.items():
        if len(dends[dom]) < 2:           # um endereço só: a regra por endereço já basta
            continue
        if any(dom == c or dom.endswith("." + c) for c in DOMINIOS_COMPARTILHADOS):
            continue                      # plataforma de envio / transportadora: só endereço
        total = dmsgs.get(dom, 0)
        if not total:
            continue
        for alvo, n in contagem.most_common(max_marcadores):
            if _recusado("@" + dom, alvo):
                continue
            if n >= minimo and n / total >= share:
                saida[alvo] = [t for t in saida[alvo] if _dominio(t[0]) != dom]
                saida[alvo].append(("@" + dom, n, total))
    for alvo in list(saida):
        if not saida[alvo]:
            del saida[alvo]
        else:
            saida[alvo].sort(key=lambda x: -x[1])
    return saida


def regras_do_dono(na_caixa):
    """As ditadas, filtradas pelo que existe nesta caixa."""
    return [(q, alvo, arq) for q, alvo, arq in REGRAS_DO_DONO if alvo in na_caixa]


def xml(por_marcador, conta, ditadas=()):
    L = ["<?xml version='1.0' encoding='UTF-8'?>",
         "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>",
         f"  <title>Filtros URACE — {conta}@urace.us</title>"]
    for busca, alvo, arquivar in ditadas:
        L += ["  <entry>",
              "    <category term='filter'></category>",
              "    <title>Mail Filter</title>",
              "    <content></content>",
              f"    <apps:property name='hasTheWord' value={quoteattr(busca)}/>",
              f"    <apps:property name='label' value={quoteattr(alvo)}/>"]
        if arquivar:
            L.append("    <apps:property name='shouldArchive' value='true'/>")
        L.append("  </entry>")
    for alvo in sorted(por_marcador):
        remetentes = " OR ".join(e for e, _n, _t in por_marcador[alvo])
        L += ["  <entry>",
              "    <category term='filter'></category>",
              "    <title>Mail Filter</title>",
              "    <content></content>",
              f"    <apps:property name='from' value={quoteattr(remetentes)}/>",
              f"    <apps:property name='label' value={quoteattr(alvo)}/>"]
        # regra do dono: só propaganda sai da inbox — e propaganda é a família wNews inteira
        if alvo == ARQUIVAVEL or alvo.startswith(ARQUIVAVEL + "/"):
            L.append("    <apps:property name='shouldArchive' value='true'/>")
        L.append("  </entry>")
    L.append("</feed>")
    return "\n".join(L) + "\n"


def desconhecidos(na_caixa):
    """Marcadores da caixa que não são do dono nem do Gmail.

    Tem de descontar os do sistema (INBOX, SENT, CATEGORY_*…) e o manual INTEIRO,
    não só o confirmado. Sem isso o relatório enchia de ruído e escondia o que
    importa: um marcador novo que apareceu sozinho, como os `Email Review/…` de
    agosto."""
    # os DOIS manuais: a support@ tem taxonomia própria, e sem ela os 64 marcadores
    # dela apareceriam como "intrusos" no relatório daquela caixa
    # e o que o dono deixou de FORA ("Action Required", "Email Review/…") NÃO é conhecido:
    # se voltar a aparecer na caixa, tem de ser listado como intruso, não escondido
    do_manual = {n for n, _f, _q, _t, e in MANUAL if e != FORA} | {n for n, _f, _q, _t, e in MANUAL_SUPPORT if e != FORA}
    return sorted(n for n in na_caixa
                  if n not in do_manual and n.upper() not in SISTEMA
                  and not n.startswith("CATEGORY_") and not n.upper().endswith("_STAR"))


def relatorio(por_marcador, nomes, na_caixa, conta, share, minimo, ditadas=()):
    cobertos = set(por_marcador) | {alvo for _q, alvo, _a in ditadas}
    sem = [n for n in nomes if n not in cobertos]
    fora_do_manual = desconhecidos(na_caixa)
    L = [f"# Filtros do Gmail — {conta}@urace.us", "",
         f"Gerado de mensagens reais da caixa. Um remetente vira regra quando **{int(share*100)}%** ou mais",
         f"das mensagens DELE estão naquele marcador e há pelo menos **{minimo}** mensagens dele ali.",
         "A evidência é lida `mensagens no marcador / mensagens do remetente`. Um mesmo remetente",
         "pode virar regra de dois marcadores — a UPS está em `Shipping Status` e em",
         "`Finances/Shopping`, e o Gmail aceita os dois filtros.",
         "",
         "Regra que começa com `@` vale para o **domínio inteiro** — pega inclusive endereços",
         "que ainda não existem. Ela só é criada quando o domínio tem 2 ou mais endereços",
         "diferentes e o conjunto todo aponta para o mesmo marcador.",
         "",
         f"- marcadores com filtro: **{len(cobertos)}**",
         f"- marcadores sem remetente estável: **{len(sem)}**",
         f"- remetentes usados: **{sum(len(v) for v in por_marcador.values())}**", ""]
    if fora_do_manual:
        L += ["## ⚠️ Marcadores na caixa que NÃO estão no manual", "",
              "Não são do sistema do Gmail e não estão no manual que o dono confirmou em 11/09.",
              "A IA os ignora. Confira um por um: os seus entram no manual; os que você não",
              "reconhecer foram postos por outra coisa, como os `Email Review/…` de agosto.", ""]
        L += [f"- `{n}`" for n in fora_do_manual] + [""]
    if ditadas:
        L += ["## Regras ditadas pelo dono", "", "Não vêm da amostra: são a regra dele, palavra por palavra.", "",
              "| Marcador | Busca do Gmail |", "|---|---|"]
        L += [f"| `{alvo.replace('|', chr(92) + '|')}` | `{q}` |" for q, alvo, _a in ditadas] + [""]
    L += ["## As regras", "", "| Marcador | Remetentes | Evidência |", "|---|---|---|"]
    for alvo in sorted(por_marcador):
        itens = por_marcador[alvo]
        ev = ", ".join(f"{n}/{t}" for _e, n, t in itens[:4])
        rem = "<br>".join(e for e, _n, _t in itens[:8])
        if len(itens) > 8:
            rem += f"<br>… mais {len(itens) - 8}"
        L.append(f"| `{alvo.replace('|', chr(92) + '|')}` | {rem} | {ev} |")
    if sem:
        L += ["", "## Sem remetente estável — decisão sua", "",
              "Estes não têm um remetente que os identifique (são conversa com pessoa, ou o",
              "remetente varia demais). Filtro por palavra no assunto erraria em massa, então",
              "eu **não** inventei regra. Continuam com a triagem da IA, que usa o manual.", ""]
        L += [f"- `{n}`" for n in sem]
    L += ["", "## Como importar", "",
          "Gmail → Ver todas as configurações → **Filtros e endereços bloqueados** →",
          "**Importar filtros** → escolher o arquivo → *Abrir arquivo* → revisar → *Criar filtros*.",
          "Marque **\"Aplicar novos filtros a conversas existentes\"** só se quiser reclassificar o",
          "histórico; sem isso vale para o que chegar daqui para frente.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conta", default="urace", choices=["urace", "support"])
    ap.add_argument("--amostra", type=int, default=30, help="mensagens por marcador")
    ap.add_argument("--share", type=float, default=0.6, help="fatia mínima do remetente no marcador")
    ap.add_argument("--min", dest="minimo", type=int, default=3, help="mensagens mínimas do remetente")
    ap.add_argument("--saida", default=os.path.expanduser("~/.urace"))
    a = ap.parse_args()

    mapa = marcadores_da_caixa(a.conta)
    na_caixa = list(mapa)
    nomes = [n for n, _f, _q, _t, e in MANUAL if e == OK and n in na_caixa]
    if not nomes:
        sys.exit(f"nenhum marcador do manual existe na caixa {a.conta}@ — nada a fazer.")
    print(f"caixa {a.conta}@: {len(na_caixa)} marcadores, {len(nomes)} do manual confirmado", file=sys.stderr)

    por_remetente, mensagens = amostrar(a.conta, nomes, a.amostra, mapa=mapa)
    por_marcador = regras(por_remetente, mensagens, a.share, a.minimo)

    os.makedirs(a.saida, exist_ok=True)
    fx = os.path.join(a.saida, f"mailFilters-{a.conta}.xml")
    fr = os.path.join(a.saida, f"filtros-{a.conta}.md")
    ditadas = regras_do_dono(na_caixa)
    with open(fx, "w", encoding="utf-8") as f:
        f.write(xml(por_marcador, a.conta, ditadas))
    with open(fr, "w", encoding="utf-8") as f:
        f.write(relatorio(por_marcador, nomes, na_caixa, a.conta, a.share, a.minimo, ditadas))
    print(f"\nescrito: {fx}\nescrito: {fr}", file=sys.stderr)
    print(f"{len(por_marcador)} filtros, {sum(len(v) for v in por_marcador.values())} remetentes")


if __name__ == "__main__":
    main()
