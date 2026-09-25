"""Guarda de estilo — o que sai para o lead, aplicado DEPOIS do modelo.

As instruções pedem o mesmo, mas prompt deriva; a garantia fica aqui:
  - sem emoji;
  - sem travessão (vira vírgula);
  - frase com termo de NUNCA_DIZER é cortada inteira.
Se nada sobrar, devolve texto vazio e a ponte usa a mensagem de espera.
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

    frases = _FRASES.split(limpo)
    mantidas = []
    for frase in frases:
        termo = proibida(frase)
        if termo:
            violacoes.append(f"nunca_dizer:{termo}")
            continue
        mantidas.append(frase)
    limpo = " ".join(f.strip() for f in mantidas if f.strip())
    limpo = re.sub(r"[ \t]{2,}", " ", limpo).replace(" ,", ",").strip()
    return limpo, violacoes
