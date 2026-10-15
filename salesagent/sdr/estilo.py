"""Guarda de estilo — o que sai para o lead, aplicado DEPOIS do modelo.

As instruções pedem o mesmo, mas prompt deriva; a garantia fica aqui:
  - sem emoji;
  - sem travessão (vira vírgula);
  - frase com termo de NUNCA_DIZER é cortada inteira.
Se nada sobrar, devolve texto vazio e a ponte usa a mensagem de espera.

E a regra de um do playbook de 13/10 (D-2026-10-13), em `um_ativo`:
  - primeira resposta a um lead sai sem link (preview de link lê como anúncio);
  - depois, no máximo um link por mensagem;
  - no máximo uma pergunta por mensagem (fica a primeira: a ordem de
    qualificação põe a mais importante, a idade, na frente).
"""
import re

from . import regras
from .classificador import normalizar

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D]"
)
_TRAVESSAO = re.compile(r"\s*[–—]\s*")
_FRASES = re.compile(r"(?<=[.!?\n])\s+")


def proibida(texto):
    """Primeiro termo de NUNCA_DIZER presente no texto, ou None."""
    t = normalizar(texto)
    for termo, _motivo in regras.NUNCA_DIZER:
        if termo in t:
            return termo
    return None


def aplicar(texto):
    """Devolve (texto_limpo, violacoes). violacoes lista o que foi mexido."""
    violacoes = []
    if not texto:
        return "", violacoes
    limpo = texto
    if not regras.ESTILO["emoji"] and _EMOJI.search(limpo):
        limpo = _EMOJI.sub("", limpo)
        violacoes.append("emoji")
    if not regras.ESTILO["travessao"] and _TRAVESSAO.search(limpo):
        limpo = _TRAVESSAO.sub(", ", limpo)
        violacoes.append("travessao")

    # Linha a linha: cada linha do modelo é uma mensagem curta (14/10), então
    # a quebra de linha sobrevive à guarda.
    linhas = []
    for linha in limpo.split("\n"):
        mantidas = []
        for frase in _FRASES.split(linha):
            termo = proibida(frase)
            if termo:
                violacoes.append(f"nunca_dizer:{termo}")
                continue
            mantidas.append(frase)
        linha = " ".join(f.strip() for f in mantidas if f.strip())
        linha = re.sub(r"[ \t]{2,}", " ", linha).replace(" ,", ",").strip()
        if linha:
            linhas.append(linha)
    return "\n".join(linhas), violacoes


_URL = re.compile(r"https?://\S+")
# O link e a "chamada" que o apresenta ("You can see it all here: <link>"):
# sem o link a chamada fica pendurada, então sai junto.
_URL_COM_CHAMADA = re.compile(r"(?:[^.!?\n:]*:\s*)?https?://\S+")
_FRASE_FIM = re.compile(r"(?<=[.!?])\s+")


def _tirar_links(texto, manter):
    """Remove os links a partir do (manter+1)-ésimo, com a chamada de cada um."""
    vistos = 0

    def _troca(m):
        nonlocal vistos
        vistos += 1
        return m.group(0) if vistos <= manter else ""

    return _URL_COM_CHAMADA.sub(_troca, texto)


def um_ativo(texto, primeira_resposta):
    """Devolve (texto, violacoes): sem link na primeira resposta, no máximo
    um link depois, e no máximo uma pergunta."""
    violacoes = []
    if not texto:
        return "", violacoes
    limpo = texto
    links = _URL.findall(limpo)
    manter = 0 if primeira_resposta else 1
    if len(links) > manter:
        limpo = _tirar_links(limpo, manter)
        violacoes.append("link_na_primeira_resposta" if primeira_resposta else "mais_de_um_link")

    linhas = []
    ja_perguntou = False
    cortou = False
    for linha in limpo.split("\n"):
        frases = []
        for frase in _FRASE_FIM.split(linha):
            pergunta = frase.rstrip().endswith("?") and not _URL.fullmatch(frase.strip())
            if pergunta and ja_perguntou:
                cortou = True
                continue
            ja_perguntou = ja_perguntou or pergunta
            frases.append(frase)
        linhas.append(" ".join(f.strip() for f in frases if f.strip()))
    if cortou:
        violacoes.append("mais_de_uma_pergunta")
    limpo = "\n".join(linha for linha in linhas if linha)
    limpo = re.sub(r"[ \t]{2,}", " ", limpo).replace(" ,", ",").strip()
    return limpo, violacoes


# Reapresentação (14/10, teste no painel): "Oi! Aqui é o Chase, da URACE." na 2ª resposta. O nome sai
# uma vez, na primeira resposta; depois disso a frase de apresentação é cortada.
_APRESENTACAO = re.compile(r"\b(chase here|this is chase|i'm chase|i am chase|aqui [eé] o chase|"
                           r"sou o chase|soy chase|aqu[ií] es chase)\b", re.IGNORECASE)


def sem_reapresentacao(texto, primeira_resposta):
    """Devolve (texto, violacoes). Fora da primeira resposta, tira a frase em que o robô se apresenta
    outra vez. Se a apresentação vem junto de "Oi!" sozinho, o "Oi!" também sai."""
    if primeira_resposta or not texto or not _APRESENTACAO.search(texto):
        return texto, []
    saudacao = re.compile(r"(oi|ol[aá]|hi|hello|hola)[!,.\\s]*", re.IGNORECASE)
    linhas = []
    for linha in texto.split("\n"):
        mantidas = []
        for frase in (f.strip() for f in _FRASE_FIM.split(linha) if f.strip()):
            if _APRESENTACAO.search(frase):
                if mantidas and saudacao.fullmatch(mantidas[-1]):
                    mantidas.pop()      # o "Oi!" que vinha só para a apresentação
                continue
            mantidas.append(frase)
        if mantidas:
            linhas.append(" ".join(mantidas))
    return "\n".join(linhas), ["reapresentacao"]
