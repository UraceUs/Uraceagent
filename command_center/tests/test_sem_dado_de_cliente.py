"""Trava do repositório público: nenhum dado real de cliente nos arquivos rastreados (#244).

Dono, 14/10: *"deixe o repositório público, mas proteja dados de clientes"*. Teste e documento
usam dado fictício e marcado: e-mail `@example.com`, telefone na faixa 555-01xx, nome inventado.
(NO FAKE DATA continua valendo para o que o sistema mostra: o fictício mora só no teste.)

O que esta trava pega, em todo arquivo do `git ls-files`:
- e-mail de provedor pessoal (gmail, outlook, hotmail, yahoo, icloud…) — fora `@example.com` e
  `@urace.us`, só passa o da equipe e de fornecedor, que está guardado como hash;
- telefone dos EUA ou do Brasil escrito como telefone (com separador ou com `+`) fora da faixa
  555-01xx — a URACE e a equipe passam, também por hash;
- e-mail ou nome de cliente real de uma lista que só existe como sha256 em
  `sem_dado_de_cliente.json` (o nome em claro nunca entra no repositório) — no texto e no
  caminho do arquivo (as fichas de `brain/20_ENTIDADES/clientes/` têm o nome no arquivo).

Para incluir um nome na lista: `python command_center/tests/test_sem_dado_de_cliente.py "Nome"`
imprime o hash; ele vai para `nomes_de_cliente` do JSON.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LISTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sem_dado_de_cliente.json")

# brain/ e relatorios/ entram na trava: o dono decidiu (14/10) que o repositório fica público e
# não haverá repositório privado — as notas ficam aqui, com o dado de cliente trocado no lugar.

# Conteúdo do site público atual (depoimentos e campeões com nome, já publicados em urace.us).
# Só a checagem de NOME pula esta pasta; e-mail e telefone continuam valendo nela.
SITE_PUBLICO = ("command_center/vitrine/",)

# Código de terceiros e arquivos que não são texto.
TERCEIROS = (".obsidian/plugins/",)
NAO_TEXTO = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf",
             ".sqlite", ".zip", ".icns", ".mp4", ".mov")

PROVEDORES_PESSOAIS = re.compile(
    r"^(gmail\.com|googlemail\.com|hotmail\.[a-z.]+|outlook\.[a-z.]+|live\.[a-z.]+|msn\.com|"
    r"yahoo\.[a-z.]+|ymail\.com|rocketmail\.com|icloud\.com|me\.com|mac\.com|aol\.com|"
    r"proton\.me|protonmail\.com|gmx\.[a-z.]+|mail\.com|zoho\.com|"
    r"uol\.com\.br|bol\.com\.br|terra\.com\.br|ig\.com\.br|globo\.com|globomail\.com)$")
SISTEMA = re.compile(r"^(mailer-daemon|postmaster|no-?reply)@")     # remetente automático, não pessoa
EMAIL = re.compile(r"(?<![\w.+-])([\w.+-]+)@((?:[\w-]+\.)+[A-Za-z]{2,})")
# EUA: (407) 555-0101 · 407-555-0101 · 407.555.0101 · +1 407 555 0101 · +14075550101
TELEFONE_EUA = re.compile(r"(?<![\w.+])(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]\d{4}(?![\w])"
                          r"|(?<![\w+])\+1[2-9]\d{2}[2-9]\d{6}(?!\d)")
# Brasil: +55 11 99555-0134 · +55 (11) 9555-0134 · +5511995550134
TELEFONE_BR = re.compile(r"(?<![\w+])\+55[ .-]?\(?\d{2}\)?[ .-]?9?\d{4}[ .-]?\d{4}(?!\d)")
FICTICIO = re.compile(r"55501\d\d$")          # últimos 7 dígitos: 555-01xx


def normalizar(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _listas():
    with open(LISTAS, encoding="utf-8") as f:
        d = json.load(f)
    return {k: set(v) for k, v in d.items() if isinstance(v, list)}


def _arquivos():
    try:
        saida = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("sem git: a trava roda no CI e em qualquer clone")
    for nome in saida.decode().split("\0"):
        if not nome or nome.startswith(TERCEIROS):
            continue
        if nome.lower().endswith(NAO_TEXTO) or nome.endswith("package-lock.json"):
            continue
        caminho = os.path.join(RAIZ, nome)
        try:
            with open(caminho, encoding="utf-8") as f:
                yield nome, f.read()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue


def achados(nome, texto, listas):
    """[(linha, o que é)] — sem repetir o dado em claro."""
    saida = []
    olha_nome = not nome.startswith(SITE_PUBLICO)
    for n, linha in enumerate(texto.splitlines(), 1):
        for local, dominio in EMAIL.findall(linha):
            endereco = f"{local}@{dominio}".lower()
            endereco = re.sub(r"^(?:email|mailto)?%3a", "", endereco)
            dominio = dominio.lower()
            if sha(endereco) in listas["emails_de_cliente"]:
                saida.append((n, "e-mail de cliente real"))
            elif (PROVEDORES_PESSOAIS.match(dominio) and not SISTEMA.match(endereco)
                  and sha(endereco) not in listas["emails_da_equipe_e_fornecedores"]):
                saida.append((n, f"e-mail pessoal @{dominio} (use @example.com)"))
        for m in TELEFONE_EUA.finditer(linha):
            digitos = re.sub(r"\D", "", m.group(0))[-10:]
            if not FICTICIO.search(digitos) and sha("1" + digitos) not in listas["telefones_da_equipe"]:
                saida.append((n, "telefone dos EUA fora da faixa 555-01xx"))
        for m in TELEFONE_BR.finditer(linha):
            digitos = re.sub(r"\D", "", m.group(0))
            if not FICTICIO.search(digitos) and sha(digitos) not in listas["telefones_da_equipe"]:
                saida.append((n, "telefone do Brasil fora da faixa 555-01xx"))
        if olha_nome:
            palavras = re.findall(r"[a-z]+", normalizar(linha))
            for tam in (1, 2, 3):
                for i in range(len(palavras) - tam + 1):
                    if sha(" ".join(palavras[i:i + tam])) in listas["nomes_de_cliente"]:
                        saida.append((n, "nome de cliente real"))
    return saida


def test_nenhum_dado_real_de_cliente_no_repositorio():
    listas = _listas()
    problemas = []
    for nome, texto in _arquivos():
        problemas += [f"{nome}: caminho: {oque}" for _, oque in achados(nome, nome.replace("/", " "), listas)]
        problemas += [f"{nome}:{linha}: {oque}" for linha, oque in achados(nome, texto, listas)]
    assert not problemas, ("Dado real de cliente no repositório público (#244). Troque por fictício "
                           "marcado (@example.com, 555-01xx, nome inventado):\n" + "\n".join(problemas[:200]))


def test_a_trava_pega_o_que_deve_e_deixa_passar_o_ficticio():
    """A trava em si: o ficticio marcado passa, o resto não."""
    listas = _listas()
    passa = ("ana@example.com · suporte@urace.us · (407) 555-0101 · +1 407 555 0199 · +14075550142 · "
             "+55 11 99555-0147 · gid 1205141832260879 · 2026-10-14 09:00 · Ana Exemplo")
    assert achados("x.py", passa, listas) == []
    arroba = "@"                                # montado aqui para este arquivo não cair na própria trava
    for ruim in ("fulano" + arroba + "gmail.com", "x" + arroba + "Outlook.com", "407-482-" + "1234",
                 "(305) 222-" + "3344", "+1 321 222 " + "3344", "+1305222" + "3344", "+55 11 98888-" + "7777",
                 "+55119888" + "87777"):
        assert achados("x.py", ruim, listas), ruim
    assert achados("x.py", "mailer-daemon" + arroba + "googlemail.com", listas) == [], "endereço de sistema não é pessoa"
    real = "iaL knaH"[::-1]                     # um nome da lista, ao contrário para não cair na trava
    assert achados("x.py", "Cliente: " + real, listas) == [(1, "nome de cliente real")]
    assert achados("x.py", real.upper().replace(" ", "_") + "_Urace Daily", listas) == [(1, "nome de cliente real")]
    assert achados("command_center/vitrine/x.py", real, listas) == [], "site público: só e-mail e telefone"


if __name__ == "__main__":
    for nome in sys.argv[1:]:
        print(sha(" ".join(re.findall(r"[a-z]+", normalizar(nome)))))
