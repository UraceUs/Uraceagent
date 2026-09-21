"""Rate Card do Drive → preço no QuickBooks.

Decisão do dono (18/09/2026): *"use o rate card sempre; ele será atualizado no Drive,
sempre consultar lá"* e *"não preciso aprovar se o valor estiver como está no rate card"*.
Daí este módulo: lê a planilha na origem, compara com o catálogo e aplica o que estiver
mapeado — uma vez por semana, ou no botão.

**Três travas, todas aprendidas apanhando:**

1. **A planilha mistura duas notações de número** — `$1,250` (milhar com vírgula) e
   `$2.756,90` (milhar com ponto, decimal com vírgula), às vezes na mesma coluna. O primeiro
   parser leu "2.756,90" como *dois e setenta e seis*. Regra que vale: o **último** separador
   é decimal quando sobram 1 ou 2 dígitos depois dele; senão é milhar.
2. **Nome parecido não é o mesmo item.** "Summer Camp 3 Days" e "5 Days" só se distinguem
   pelo qualificador, e um item do catálogo está escrito "Pratice" (com erro) — o que fura
   qualquer casamento por nome. Por isso o casamento **não é automático**: só vale o que
   está em `MAPA`, revisado por gente. O resto vira proposta no painel.
3. **Peça não muda de preço** (dono, 18/09). Só serviço e aluguel entram.

O que este módulo NÃO faz: escrever no QuickBooks. Ele devolve o plano; quem executa é a
ação `qbo_atualizar_preco`, com política e auditoria como qualquer outra.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

# A planilha, no Drive do dono. Trocar de arquivo é trocar este id.
PLANILHA = os.environ.get("RATECARD_SHEET", "160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo")
FAIXA = os.environ.get("RATECARD_FAIXA", "A1:Z400")
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"

PECA = re.compile(r"^(Parts|Engine parts|OTK Parts|BirelArt|Fuel and Oil|Electric)[: ]", re.I)
PREFIXO = re.compile(r"^(Service|Rental|Parts|Engine parts|OTK Parts|BirelArt|Electric|Fuel and Oil|Shipping):", re.I)
# linhas de totalização da planilha: nunca viram item (o dono marcou "não criar" em 18/09)
NAO_E_ITEM = {"total", "subtotal", "deposit due", "balance due", "shop"}


# --------------------------------------------------------------------- números
def preco(txt):
    """'$2.756,90' → 2756.9 · '$1,250/even' → 1250.0 · '$350/day' → 350.0 · sem $ → None."""
    m = re.search(r"\$\s?([\d][\d.,]*)", str(txt or ""))
    if not m:
        return None
    n = m.group(1).rstrip(".,")
    if not any(c in n for c in ".,"):
        return float(n)
    ponto = n[::-1].find(".")
    virgula = n[::-1].find(",")
    depois = min(ponto if ponto != -1 else 10**9, virgula if virgula != -1 else 10**9)
    if depois in (1, 2):                       # o último separador é decimal
        inteiro = n[: len(n) - depois - 1].replace(".", "").replace(",", "")
        return float(f"{inteiro}.{n[len(n) - depois:]}")
    return float(re.sub(r"[.,]", "", n))       # todos os separadores são de milhar


# --------------------------------------------------------------------- leitura
def _token_google():
    """O mesmo token do Gmail/Calendar: já tem `drive.readonly` e `spreadsheets.readonly`."""
    from adminai import google_auth
    return google_auth.access_token()


def ler_planilha(planilha=None, faixa=None, token=None):
    """Grade crua da Rate Card (lista de linhas, cada uma lista de células)."""
    url = f"{SHEETS}/{planilha or PLANILHA}/values/{urllib.parse.quote(faixa or FAIXA)}"
    req = urllib.request.Request(url + "?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE")
    req.add_header("Authorization", f"Bearer {token or _token_google()}")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read()).get("values", [])
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Rate Card: HTTP {e.code} ao ler a planilha — {e.read()[:200].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Rate Card: sem conexão com o Google — {e.reason}")


def extrair(grade):
    """Grade → [{'nome', 'contexto', 'valor', 'cru', 'linha'}]. Só linhas com UM preço:
    linha com vários preços é ambígua (a planilha põe a tabela de pacotes assim) e fica de
    fora, para não casar o valor errado com o nome certo."""
    saida = []
    for i, linha in enumerate(grade or []):
        cels = [str(c).strip() for c in linha if str(c).strip()]
        if not cels:
            continue
        precos = [c for c in cels if "$" in c and "vary" not in c.lower() and len(c) <= 40]
        nomes = [c for c in cels if "$" not in c]
        if not nomes or len(precos) != 1:
            continue
        v = preco(precos[0])
        if v is None or v < 1:
            continue
        if nomes[0].strip().lower() in NAO_E_ITEM:
            continue
        saida.append({"nome": nomes[0], "contexto": " · ".join(nomes[1:3]),
                      "valor": round(v, 2), "cru": precos[0], "linha": i + 1})
    return saida


# --------------------------------------------------------------------- o mapa revisado
def _mapa_arquivo():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "ratecard_mapa.json")


def mapa():
    """Pares Rate Card ↔ item do catálogo que uma pessoa já conferiu. Sem isto, nada é
    aplicado: nome parecido não basta (ver a trava 2 no topo)."""
    try:
        with open(_mapa_arquivo(), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {"pares": [], "revisado_em": None}


def _chave(nome, contexto=""):
    t = PREFIXO.sub("", f"{nome} {contexto}").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# --------------------------------------------------------------------- o plano
def planejar(entradas, itens):
    """O que fazer, sem fazer nada. `itens`: [{'id','nome','preco'}] do catálogo.

    Devolve `atualizar` (mapeado e com preço diferente), `iguais`, `criar` (marcado como
    novo no mapa) e `duvida` (a Rate Card mudou algo que ninguém ligou a um item)."""
    m = mapa()
    por_chave = {_chave(p["rc"]): p for p in m.get("pares", [])}
    familias = {k.strip().lower(): v for k, v in (m.get("familias") or {}).items()}
    por_id = {str(i.get("id")): i for i in itens}
    por_nome = {}
    for i in itens:              # o catálogo conhece o item pelos dois nomes
        for n in (i.get("nome"), i.get("nome_completo")):
            if n:
                por_nome[n.strip().lower()] = i

    plano = {"atualizar": [], "iguais": [], "criar": [], "duvida": [], "revisado_em": m.get("revisado_em")}
    for e in entradas:
        # a chave do mapa é o NOME da linha; o contexto entra só como desempate
        p = por_chave.get(_chave(e["nome"])) or por_chave.get(_chave(e["nome"], e["contexto"]))
        if not p:
            # sem par revisado, vale a decisão de FAMÍLIA que o dono deu em 18/09
            fam = familias.get(re.split(r"[—·]", e["nome"])[0].strip().lower())
            if fam == "ignorar":
                continue
            if fam == "criar":
                p = {"acao": "criar", "qbo": None}
            else:
                plano["duvida"].append({**e, "porque": "não está no mapa revisado"})
                continue
        if p.get("acao") == "ignorar":
            continue
        if p.get("acao") == "criar":
            nome = p.get("qbo") or e["nome"]
            if nome.strip().lower() in por_nome:      # alguém já criou desde a revisão
                item = por_nome[nome.strip().lower()]
            else:
                plano["criar"].append({"nome": nome, "valor": e["valor"], "rc": e["nome"], "linha": e["linha"]})
                continue
        else:
            item = por_id.get(str(p.get("qbo_id"))) or por_nome.get((p.get("qbo") or "").strip().lower())
        if not item:
            plano["duvida"].append({**e, "porque": f"o item '{p.get('qbo')}' não está mais no catálogo"})
            continue
        if PECA.match(item.get("nome_completo") or item.get("nome") or ""):   # peça mantém o preço (dono, 18/09)
            continue
        atual = item.get("preco")
        try:
            atual = float(atual) if atual not in (None, "") else None
        except (TypeError, ValueError):
            atual = None
        registro = {"id": item.get("id"), "qbo": item.get("nome_completo") or item.get("nome"), "atual": atual,
                    "novo": e["valor"], "rc": e["nome"], "cru": e["cru"], "linha": e["linha"]}
        if atual is not None and abs(atual - e["valor"]) <= 0.005:
            plano["iguais"].append(registro)
        else:
            plano["atualizar"].append(registro)
    _correcoes(m, por_nome, plano)
    return plano


def _correcoes(m, por_nome, plano):
    """Preço quebrado no catálogo (o separador de milhar comido na importação: um item de
    $2.400 cadastrado como $2,40). Não vem da Rate Card — veio do dono, item a item, em
    18/09. Só entra enquanto o preço ainda for o quebrado: depois de corrigido, some
    sozinho, então a rotina pode rodar toda semana sem repetir."""
    for c in m.get("correcoes", []):
        item = por_nome.get((c.get("qbo") or "").strip().lower())
        if not item:
            plano["duvida"].append({"nome": c.get("qbo"), "contexto": "", "valor": c.get("novo"),
                                    "cru": "", "linha": 0, "porque": "correção pendente, mas o item sumiu do catálogo"})
            continue
        try:
            atual = float(item.get("preco"))
        except (TypeError, ValueError):
            atual = None
        if atual is None or abs(atual - float(c["novo"])) <= 0.005:
            continue                                  # já corrigido
        if abs(atual - float(c.get("atual", -1))) > 0.005:
            plano["duvida"].append({"nome": c.get("qbo"), "contexto": "", "valor": c.get("novo"), "cru": "", "linha": 0,
                                    "porque": f"correção combinada para {c.get('atual')}, mas hoje está {atual} — alguém mexeu"})
            continue
        plano["atualizar"].append({"id": item.get("id"), "qbo": item.get("nome_completo") or item.get("nome"),
                                   "atual": atual, "novo": float(c["novo"]), "rc": "correção do dono",
                                   "cru": c.get("porque", ""), "linha": 0})


def resumo(plano):
    return (f'{len(plano["atualizar"])} para atualizar · {len(plano["iguais"])} já iguais · '
            f'{len(plano["criar"])} para criar · {len(plano["duvida"])} em dúvida')
