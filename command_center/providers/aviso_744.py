"""Conferência do aviso do §744.301(3) da Flórida no modelo parental da waiver nativa (#116, lacuna F-2).

Pelo menor, a renúncia do pai ou da mãe só vale se o documento traz o aviso que a lei pede, em maiúsculas e
em letra maior que o resto. **O texto do aviso não está no código** (NO FAKE DATA): é o que o advogado
aprovar, num arquivo fora do repositório, `CC_WAIVER_AVISO_744` ou, sem a variável, `aviso-744.txt` na pasta
das waivers (`~/.urace/waivers`). O arquivo tem só o texto do aviso, como o advogado aprovou.

- **Sem o arquivo**: a conferência só informa ("esperando o texto aprovado") e nada é barrado.
- **Com o arquivo**: o modelo parental que não passa não é importado, a assinatura não liga e a parental não
  se assina online. Arquivo configurado que não abre ou está vazio também barra: alguém quis configurar.

O que se confere no PDF é o que o pypdf consegue ler (melhor esforço: depende de como o PDF foi gerado):
- o texto aprovado aparece inteiro e na ordem (só letras e números contam: espaço, pontuação e quebra de
  linha, não);
- todas as letras dele estão em maiúsculas no documento;
- a menor letra do aviso tem pelo menos `PONTOS_A_MAIS` pontos a mais que a letra do corpo (o tamanho mais
  usado no resto do documento). A regra dos pontos também é para o advogado confirmar com o texto.
"""
import hashlib
import io
import os
import re
from collections import Counter

PONTOS_A_MAIS = 5.0                  # [conferir com o advogado, junto com o texto do aviso]
_FOLGA = 0.05                        # arredondamento do tamanho calculado pela matriz do PDF
_CACHE = {}                          # (sha256 do PDF, sha256 do texto aprovado) → resultado


def caminho():
    """Onde fica o texto aprovado: `CC_WAIVER_AVISO_744`, ou `aviso-744.txt` na pasta das waivers."""
    from command_center.providers import waiver_nativa
    return os.environ.get("CC_WAIVER_AVISO_744") or os.path.join(waiver_nativa.pasta(), "aviso-744.txt")


def aprovado():
    """O texto aprovado pelo advogado: None (não configurado) ou {path, text, sha256, error}."""
    p = caminho()
    if not os.environ.get("CC_WAIVER_AVISO_744") and not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            texto = f.read().strip()
    except (OSError, UnicodeDecodeError) as e:
        return {"path": p, "text": None, "sha256": None,
                "error": f"O arquivo do texto aprovado ({p}) não abre: {e.__class__.__name__}. Até corrigir, nada é liberado."}
    if not _letras_do_texto(texto):
        return {"path": p, "text": None, "sha256": None,
                "error": f"O arquivo do texto aprovado ({p}) está vazio. Até corrigir, nada é liberado."}
    return {"path": p, "text": texto, "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(), "error": None}


def _minuscula(c):
    """`c` em minúscula, sem mudar o tamanho da cadeia (o índice do documento casa com o do aviso)."""
    m = c.lower()
    return m if len(m) == 1 else c


def _letras_do_texto(texto):
    return "".join(_minuscula(c) for c in texto if c.isalnum())


def _vezes(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def letras(pdf):
    """[(letra ou número, tamanho em pontos)] do PDF inteiro, na ordem de leitura do pypdf."""
    from pypdf import PdfReader
    saida = []

    def ver(texto, cm, tm, _fonte, tamanho):
        if not texto or not tamanho:
            return
        m = _vezes(tm, cm)
        pt = round(float(tamanho) * (m[2] ** 2 + m[3] ** 2) ** 0.5, 2)
        saida.extend((c, pt) for c in texto if c.isalnum())

    for pagina in PdfReader(io.BytesIO(pdf)).pages:
        pagina.extract_text(visitor_text=ver)
    return saida


def _ate_onde(palavras, doc):
    """Quantas palavras do começo do aviso aparecem seguidas no documento (busca binária: é monotônico)."""
    lo, hi = 0, len(palavras)
    while lo < hi:
        meio = (lo + hi + 1) // 2
        if _letras_do_texto("".join(palavras[:meio])) in doc:
            lo = meio
        else:
            hi = meio - 1
    return lo


def _corpo(tamanhos):
    """O tamanho da letra do corpo: o mais usado (em letras), fora o aviso."""
    return Counter(round(t, 1) for t in tamanhos).most_common(1)[0][0] if tamanhos else None


def conferir(pdf, cfg=...):
    """O resultado da conferência do aviso no PDF do modelo parental (dict para a tela, a trilha e o banco)."""
    cfg = aprovado() if cfg is ... else cfg
    regra = f"approved notice text, whole, in uppercase, at least {PONTOS_A_MAIS:g} pt larger than the body text"
    if not cfg:
        return {"configured": False, "ok": None, "rule": regra,
                "reason": "Esperando o texto do aviso aprovado pelo advogado: a conferência só informa e nada é barrado."}
    if cfg.get("error"):
        return {"configured": True, "ok": False, "rule": regra, "approved_sha256": None, "reason": cfg["error"]}
    chave = (hashlib.sha256(pdf).hexdigest(), cfg["sha256"])
    if chave in _CACHE:
        return dict(_CACHE[chave])
    r = {"configured": True, "rule": regra, "approved_sha256": cfg["sha256"], **_medir(pdf, cfg["text"])}
    _CACHE[chave] = r
    return dict(r)


def _medir(pdf, texto):
    try:
        ls = letras(pdf)
    except Exception as e:                       # PDF que o pypdf não lê: não dá para provar o aviso
        return {"ok": False, "found": False, "reason": f"O PDF não pôde ser lido para conferir o aviso ({e.__class__.__name__})."}
    if not ls:
        return {"ok": False, "found": False,
                "reason": "O PDF não tem texto que se possa ler (imagem escaneada?): o aviso não pode ser conferido."}
    doc = "".join(_minuscula(c) for c, _ in ls)
    alvo = _letras_do_texto(texto)
    achados = []
    i = doc.find(alvo)
    while i >= 0:
        achados.append(i)
        i = doc.find(alvo, i + 1)
    if not achados:
        palavras = [p for p in re.split(r"[\W_]+", texto) if p]
        k = _ate_onde(palavras, doc)
        tem = " ".join(palavras[max(0, k - 6):k])
        falta = " ".join(palavras[k:k + 6])
        onde = (f"o documento tem até “…{tem}” e falta a partir de “{falta}…”" if k
                else f"nem o começo (“{falta}…”) aparece")
        return {"ok": False, "found": False, "reason": f"O aviso aprovado não está inteiro no modelo: {onde}."}
    melhor = None
    for i in achados:
        trecho = ls[i:i + len(alvo)]
        resto = [t for _, t in ls[:i]] + [t for _, t in ls[i + len(alvo):]]
        minusculas = sum(1 for c, _ in trecho if c.islower())
        aviso_pt = min(t for _, t in trecho)
        corpo_pt = _corpo(resto)
        dif = round(aviso_pt - corpo_pt, 2) if corpo_pt is not None else None
        tamanho_ok = dif is not None and dif >= PONTOS_A_MAIS - _FOLGA
        r = {"ok": minusculas == 0 and tamanho_ok, "found": True, "uppercase": minusculas == 0, "lowercase_letters": minusculas,
             "notice_pt": aviso_pt, "body_pt": corpo_pt, "difference_pt": dif, "required_pt": PONTOS_A_MAIS}
        nota = (r["ok"], r["uppercase"], -99 if dif is None else dif)
        if melhor is None or nota > melhor[0]:
            melhor = (nota, r)
    m = melhor[1]
    if m["body_pt"] is None:
        m["ok"] = False
        m["reason"] = "O documento só tem o aviso: não há texto do corpo para comparar o tamanho da letra."
    elif m["ok"]:
        m["reason"] = (f"O aviso aprovado está no modelo, em maiúsculas, com letra de {m['notice_pt']:g} pt contra "
                       f"{m['body_pt']:g} pt do corpo (+{m['difference_pt']:g} pt).")
    else:
        faltas = []
        if not m["uppercase"]:
            faltas.append(f"{m['lowercase_letters']} letra(s) do aviso em minúscula")
        if m["difference_pt"] < PONTOS_A_MAIS - _FOLGA:
            faltas.append(f"a letra do aviso ({m['notice_pt']:g} pt) não tem {PONTOS_A_MAIS:g} pt a mais que a do corpo "
                          f"({m['body_pt']:g} pt)")
        m["reason"] = "O aviso aprovado está no modelo, mas " + " e ".join(faltas) + "."
    return m
