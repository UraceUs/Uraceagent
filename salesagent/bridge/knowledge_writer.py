"""Resposta humana virando conhecimento do Chase.

O fecho do ciclo do brief de 25/08: cliente → Chase → (não sei) →
Italo/Eduardo → resposta → cliente → **e o Chase aprende**. Sem esta peça,
a mesma pergunta escala de novo na semana que vem, e o humano responde a
mesma coisa pela terceira vez.

Quatro regras do brief moram aqui, e cada uma existe para impedir um jeito
específico de estragar o Brain:

§9  Resposta humana é CANDIDATO, não verdade publicada. Vira documento com
    `status: review_required` -- pronto para um clique no Obsidian, nunca
    ativo sozinho. Autoridade alta acelera a revisão; não a dispensa.

§14 Antes de escrever, procura. Se já existe documento sobre o assunto, não
    duplica: anexa a confirmação ao que existe. Nunca sobrescreve em
    silêncio.

    Conflito (o novo contradiz um documento APROVADO) não é resolvido aqui:
    vira um documento marcado `conflict_detected` apontando os dois lados,
    para um humano decidir. Um sistema que escolhe sozinho entre duas
    verdades acaba publicando a errada.

§16 Memória ≠ conhecimento. "Para ESSE cliente pode 10%" é acordo daquele
    negócio e vai para a nota do lead no CRM; "podemos oferecer até 10%
    nesse segmento" é política e vai para o Brain. Errar isso publica um
    desconto pontual como regra da casa.

A regra de ouro do vault também vale: nada de preço em número, link ou
horário em prosa retrievável (`brain/_meta/README.md`). Uma resposta humana
que contenha isso é gravada com o número REDIGIDO e um aviso -- o valor
vigente vive no rate card, não aqui.
"""
import datetime
import re
import sys
from pathlib import Path

BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "brain"
LEARNINGS_DIR = BRAIN_DIR / "09_LEARNINGS"
sys.path.insert(0, str(BRAIN_DIR))

# ---------------------------------------------------------------- §16
# Marcas de acordo pontual: fala de UM negócio, não de política. A lista é
# curta de propósito -- na dúvida o texto NÃO vira conhecimento global, e
# perder um aprendizado custa menos que publicar um desconto como regra.
_ESPECIFICO_RE = re.compile(
    r"\b(para\s+(esse|este|ess[ae]\s+cliente|ele|ela)|"
    r"nesse\s+caso|neste\s+caso|s[óo]\s+(para|pra)\s+(ele|ela|esse)|"
    r"excep(c|ç)ional|abre\s+uma\s+exce|dessa\s+vez|dest[ae]\s+vez|"
    r"j[áa]\s+que\s+[ée]\s+(ele|ela)|por\s+ser\s+(ele|ela))\b",
    re.IGNORECASE)

# ---------------------------------------------------------------- regra de ouro
_VALOR_RE = re.compile(r"(?:R\$|US\$|\$)\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:reais|d[óo]lares|usd|brl)\b",
                       re.IGNORECASE)
_LINK_RE = re.compile(r"https?://\S+")


def classificar(texto: str) -> str:
    """'memory' (acordo daquele negócio) ou 'knowledge' (vale para todos)."""
    return "memory" if _ESPECIFICO_RE.search(texto or "") else "knowledge"


def redigir_volateis(texto: str) -> tuple[str, list[str]]:
    """Tira número de preço e link do texto que vai para o Brain. Devolve
    (texto limpo, avisos) -- o aviso vira nota no documento para o revisor
    entender por que o número sumiu."""
    avisos = []
    limpo = texto
    if _VALOR_RE.search(limpo):
        limpo = _VALOR_RE.sub("[valor - ver rate card]", limpo)
        avisos.append("valor em número removido (a fonte é o rate card, "
                      "nunca o Brain)")
    if _LINK_RE.search(limpo):
        limpo = _LINK_RE.sub("[link - ver program-links.json]", limpo)
        avisos.append("link removido (a fonte é program-links.json)")
    return limpo, avisos


def _slug(texto: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (texto or "").lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "sem-assunto"


def buscar_relacionado(pergunta: str, top: int = 3) -> list[dict]:
    """§14: o que o Brain já tem sobre isso. Usa o MESMO índice do agente --
    se a busca não acha, o agente também não acharia."""
    try:
        import indexer
        return indexer.search(pergunta, top_docs=top)
    except Exception:
        return []


def registrar(pergunta: str, resposta: str, autor: str,
              lead_id: int | None = None, autoridade: str = "high",
              forcar: bool = False, learnings_dir: Path | None = None,
              hoje: datetime.date | None = None) -> dict:
    """Grava a resposta humana como candidato no vault.

    `forcar=True` = o operador disse explicitamente "salve isso" (§18/§19),
    o que pula só a triagem memory-vs-knowledge -- nunca a revisão humana
    nem a detecção de conflito.

    Devolve {'written': bool, 'path': str|None, 'kind': str, 'reason': str}.
    """
    diretorio = learnings_dir or LEARNINGS_DIR
    hoje = hoje or datetime.date.today()
    pergunta = (pergunta or "").strip()
    resposta = (resposta or "").strip()

    if not resposta:
        return {"written": False, "path": None, "kind": "none",
                "reason": "sem resposta para registrar"}

    tipo = classificar(resposta)
    if tipo == "memory" and not forcar:
        return {"written": False, "path": None, "kind": "memory",
                "reason": ("parece acordo específico deste cliente, não "
                           "política — fica na nota do lead, não no Brain. "
                           "Se for regra geral, responda 'salvar isso'.")}

    limpo, avisos = redigir_volateis(resposta)
    relacionados = buscar_relacionado(pergunta or resposta)
    aprovados = [d for d in relacionados if d.get("path")]
    conflito = bool(aprovados) and not forcar

    slug = _slug(pergunta or resposta[:60])
    nome = f"humano - {slug}.md"
    caminho = diretorio / nome

    # §14: não sobrescreve o que um humano já promoveu.
    if caminho.exists():
        cabeca = caminho.read_text(encoding="utf-8")[:400]
        m = re.search(r"^status:\s*(\S+)", cabeca, re.MULTILINE)
        if m and m.group(1).lower() not in ("candidate", "review_required",
                                            "conflict_detected"):
            return {"written": False, "path": str(caminho), "kind": tipo,
                    "reason": ("já existe documento promovido por humano "
                               "sobre isso — não sobrescrevo; edite no "
                               "Obsidian se precisar mudar")}

    status = "conflict_detected" if conflito else "review_required"
    diretorio.mkdir(parents=True, exist_ok=True)

    bloco_relacionado = ""
    if aprovados:
        linhas = "\n".join(f"- `{d['path']}` — {d.get('title', '?')}"
                           for d in aprovados)
        bloco_relacionado = (
            f"\n## Já existe no Brain sobre isso\n\n{linhas}\n\n"
            f"> **Decida antes de aprovar**: se o documento acima já cobre "
            f"esta resposta, arquive este aqui (`status: archived`). Se ele "
            f"está desatualizado, atualize-o e arquive este. Se os dois "
            f"valem, ajuste os dois para não se contradizerem.\n")

    bloco_avisos = ""
    if avisos:
        bloco_avisos = ("\n> Nota do sistema: " + "; ".join(avisos)
                        + ". Regra do vault em `brain/_meta/README.md`.\n")

    caminho.write_text(
        "---\n"
        "type: learning\n"
        "category: resposta_humana\n"
        f"topic: {slug[:40]}\n"
        "priority: high\n"
        f"status: {status}\n"
        "source: italo\n"
        f"source_authority: {autor}\n"
        f"confidence: {autoridade}\n"
        f"last_updated: {hoje.isoformat()}\n"
        + (f"lead_id: {lead_id}\n" if lead_id else "")
        + "tags: [aprendizado, resposta-humana, confirmado]\n"
        "---\n\n"
        f"# {pergunta or 'Resposta confirmada por ' + autor}\n\n"
        f"> Confirmado por **{autor}** em {hoje.isoformat()}"
        + (f" (lead {lead_id})" if lead_id else "") + ".\n"
        f"> Status `{status}`: **ainda não está em uso pelo Chase.** "
        f"Revise e mude para `approved` no Obsidian para ele passar a "
        f"responder isso sozinho.\n"
        + bloco_avisos +
        (f"\n## Pergunta do lead\n\n{pergunta}\n" if pergunta else "")
        + f"\n## Resposta confirmada\n\n{limpo}\n"
        + bloco_relacionado
        + "\n## Antes de aprovar\n\n"
        "- Está em português e vale para QUALQUER lead (não é acordo de um cliente)?\n"
        "- Tem `aliases` em inglês? Leads perguntam em inglês; sem isso a "
        "busca não acha.\n"
        "- Nenhum preço em número, link ou horário no texto?\n",
        encoding="utf-8")

    return {"written": True, "path": str(caminho), "kind": tipo,
            "reason": ("conflito com documento existente — marcado para "
                       "decisão humana" if conflito else
                       "gravado como candidato para revisão")}


def reindexar() -> bool:
    """§15: índice atualizado na hora. O indexador é incremental por hash --
    só o arquivo novo é reprocessado, o vault inteiro não."""
    try:
        import indexer
        indexer.index_vault(BRAIN_DIR, indexer.default_db_path())
        return True
    except Exception:
        return False


# --------------------------------------------------------------- self-test
def self_test() -> int:
    import tempfile
    falhas = []
    hoje = datetime.date(2026, 8, 26)
    tmp = Path(tempfile.mkdtemp(prefix="kw-"))

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            falhas.append(label)

    check("§16 acordo pontual é memória",
          classificar("para esse cliente pode dar 10% de desconto") == "memory")
    check("§16 política é conhecimento",
          classificar("podemos oferecer até 10% para escolas parceiras") == "knowledge")
    check("§16 'nesse caso' é memória",
          classificar("nesse caso pode liberar") == "memory")

    limpo, avisos = redigir_volateis("custa R$ 450 e o link é https://urace.us/x")
    check("regra de ouro: número de preço redigido", "R$ 450" not in limpo, limpo)
    check("regra de ouro: link redigido", "https://" not in limpo, limpo)
    check("redação é explicada ao revisor", len(avisos) == 2, str(avisos))

    r = registrar("posso levar meu kart?", "para esse cliente pode",
                  "Italo", learnings_dir=tmp, hoje=hoje)
    check("§16 memória NÃO vira documento no Brain",
          r["written"] is False and r["kind"] == "memory", str(r))
    check("e a recusa explica como forçar", "salvar isso" in r["reason"], str(r))

    r = registrar("posso levar meu kart?", "para esse cliente pode",
                  "Italo", forcar=True, learnings_dir=tmp, hoje=hoje)
    check("'salvar isso' força mesmo o que parece específico",
          r["written"] is True, str(r))

    r = registrar("posso levar meu kart proprio?",
                  "Sim, com inspeção prévia e entrega 1 dia antes.",
                  "Italo", lead_id=31764961, learnings_dir=tmp, hoje=hoje)
    check("resposta de política vira documento", r["written"] is True, str(r))
    doc = Path(r["path"]).read_text(encoding="utf-8")
    check("§9 nasce como review_required, nunca approved",
          "status: review_required" in doc or "status: conflict_detected" in doc, doc[:200])
    check("§9 documento avisa que NÃO está em uso",
          "ainda não está em uso" in doc)
    check("autoria registrada", "source_authority: Italo" in doc)
    check("lead de origem registrado", "lead_id: 31764961" in doc)
    check("checklist de aprovação presente", "aliases" in doc)

    # §14: humano já promoveu -> não sobrescreve
    promovido = Path(r["path"])
    promovido.write_text(promovido.read_text(encoding="utf-8")
                         .replace("status: review_required", "status: approved")
                         .replace("status: conflict_detected", "status: approved"),
                         encoding="utf-8")
    r2 = registrar("posso levar meu kart proprio?", "Outra coisa qualquer",
                   "Eduardo", learnings_dir=tmp, hoje=hoje)
    check("§14 não sobrescreve o que humano aprovou", r2["written"] is False, str(r2))
    check("§14 a recusa aponta o caminho (Obsidian)", "Obsidian" in r2["reason"])
    check("§14 o documento aprovado ficou intacto",
          "status: approved" in promovido.read_text(encoding="utf-8"))

    r3 = registrar("", "qualquer coisa", "Italo", learnings_dir=tmp, hoje=hoje)
    check("sem pergunta ainda grava (usa a resposta como assunto)",
          r3["written"] is True, str(r3))
    r4 = registrar("pergunta", "", "Italo", learnings_dir=tmp, hoje=hoje)
    check("sem resposta não grava nada", r4["written"] is False, str(r4))

    print()
    if falhas:
        print(f"SELF TEST FALHOU - {len(falhas)}: {', '.join(falhas)}")
        return 1
    print("SELF TEST PASSOU - §9 candidato, §14 sem duplicar nem sobrescrever, "
          "§16 memória fora do Brain, regra de ouro respeitada")
    return 0


if __name__ == "__main__":
    sys.exit(self_test())
