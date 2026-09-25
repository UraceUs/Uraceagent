"""Classificador — lê a mensagem e descreve os sinais. Não decide nada.

Quem decide é a triagem (zona do card) e o roteador (responde, cala ou
escala). Aqui só se responde "o que tem nesta mensagem".

Casamento por palavra inteira: "hi" não casa com "this", "ok" não casa com
"book". Termos com espaço casam como expressão.
"""
import re
import unicodedata

from . import regras

_REGEX_PIT_ID = re.compile(r"\bPIT-[A-Z0-9]{3,6}-[A-Z0-9]{4,8}\b", re.IGNORECASE)
_REGEX_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_REGEX_TELEFONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{2,3}\)?[\s.-]?\d{3,5}[\s.-]?\d{4}")
_REGEX_PILOTOS = re.compile(r"(\d{1,3})\s*(pilotos?|pessoas?|alunos?|criancas?|drivers?|kids?|people|participantes?)")
_REGEX_DATA = re.compile(r"\b\d{1,2}\s*[/-]\s*\d{1,2}(\s*[/-]\s*\d{2,4})?\b")
_REGEX_LETRA = re.compile(r"(?:^|\b)(?:opcao|letra|option)?\s*([abcd])(?:\)|\.|\b)")
_REMETENTE_AUTOMATICO = re.compile(regras.REMETENTES_AUTOMATICOS, re.IGNORECASE)

_PALAVRAS_DATA = [
    "hoje", "amanha", "semana que vem", "proxima semana", "fim de semana", "sabado", "domingo",
    "today", "tomorrow", "next week", "this weekend", "saturday", "sunday", "monday", "friday",
]

_PADROES = {}


def normalizar(texto):
    """Minúsculo, sem acento, espaços colapsados."""
    if not isinstance(texto, str):
        return ""
    sem_acento = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _padrao(termo):
    if termo not in _PADROES:
        _PADROES[termo] = re.compile(r"(?<![a-z0-9])" + re.escape(termo) + r"(?![a-z0-9])")
    return _PADROES[termo]


def contem(texto, termos):
    return any(_padrao(t).search(texto) for t in termos)


def _so_termos_de(texto, termos, max_palavras=5):
    """Mensagem curta feita só de termos da lista ("oi, bom dia", "ok valeu")."""
    limpo = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", texto)).strip()
    if not limpo or len(limpo.split(" ")) > max_palavras:
        return False
    resto = limpo
    for termo in sorted(termos, key=len, reverse=True):
        resto = _padrao(termo).sub(" ", resto)
    return not resto.strip() and resto != limpo


def detectar_classificacao(texto, intencoes):
    for letra, termos in regras.PROSA_CLASSIFICACAO:
        if contem(texto, termos):
            return letra
    if "compete" in intencoes:
        return "D"
    # Letra solta só vale em resposta curta ("b", "opção B", "letra c").
    palavras = re.sub(r"[^a-z0-9\s)]", " ", texto).split()
    if 0 < len(palavras) <= 3:
        achado = _REGEX_LETRA.search(texto)
        if achado:
            return achado.group(1).upper()
    return None


def remetente_automatico(email):
    return bool(email) and bool(_REMETENTE_AUTOMATICO.search(email))


def classificar(texto, remetente_email=None):
    """Sinais de uma mensagem. `remetente_email` ajuda a reconhecer máquina."""
    original = texto if isinstance(texto, str) else ""
    t = normalizar(original)

    intencoes = [nome for nome in (
        "preco", "agenda", "contratacao", "humano", "corporativo", "servico",
        "informacao", "conversao", "compete",
    ) if contem(t, regras.PALAVRAS[nome])]

    pilotos = None
    achado = _REGEX_PILOTOS.search(t)
    if achado and int(achado.group(1)) > 0:
        pilotos = int(achado.group(1))

    pit = _REGEX_PIT_ID.search(original)
    email = _REGEX_EMAIL.search(original)
    telefone = _REGEX_TELEFONE.search(original)
    classificacao = detectar_classificacao(t, intencoes)

    sinais = {
        "pit_id": pit.group(0).upper() if pit else None,
        "email": email.group(0) if email else None,
        "telefone": telefone.group(0) if telefone else None,
        "pilotos": pilotos,
        "data": bool(_REGEX_DATA.search(t)) or contem(t, _PALAVRAS_DATA),
        "classificacao": classificacao,
    }

    automatico = contem(t, regras.PALAVRAS["automatico"]) or remetente_automatico(remetente_email)
    saudacao = not intencoes and _so_termos_de(t, regras.PALAVRAS["saudacao"])
    encerramento = not intencoes and not saudacao and _so_termos_de(t, regras.PALAVRAS["encerramento"])

    return {
        "texto": original,
        "normalizado": t,
        "tem_texto": bool(t),
        "intencoes": intencoes,
        "sinais": sinais,
        "score": _score(intencoes, sinais),
        "automatico": automatico,
        "spam": contem(t, regras.PALAVRAS["spam"]),
        # "Unsubscribe" no rodapé de newsletter não é o lead pedindo para sair.
        "opt_out": not automatico and contem(t, regras.PALAVRAS["opt_out"]),
        "sensivel": contem(t, regras.PALAVRAS["sensivel"]),
        "desconto": contem(t, regras.PALAVRAS["desconto"]),
        "insatisfacao": contem(t, regras.PALAVRAS["insatisfacao"]),
        "grupo_grande": bool(pilotos and pilotos > regras.GRUPO_LIMITE_PILOTOS),
        "saudacao_isolada": saudacao,
        "encerramento": encerramento,
        "pede_humano": "humano" in intencoes,
        "conversao": "conversao" in intencoes,
        "compete": "compete" in intencoes or classificacao == "D",
    }


def _score(intencoes, sinais):
    total = sum(regras.PESOS.get(i, 0) for i in intencoes)
    if sinais["pit_id"]:
        total += regras.PESOS["pit_id"]
    if sinais["classificacao"]:
        total += regras.PESOS["classificacao"]
    if sinais["data"]:
        total += regras.PESOS["data"]
    if sinais["pilotos"]:
        total += regras.PESOS["pilotos"]
    if sinais["email"] or sinais["telefone"]:
        total += regras.PESOS["contato"]
    return total
