"""Command Center em português e inglês (#177).

Dono, 09/10: "o command center inteiro com versão português e inglês". Todo texto de tela do painel
passa por tr('...'); este teste trava o caso de alguém pôr texto novo sem a tradução no dicionário
(src/i18n/en.json) ou com marcador {0} diferente."""
import ast
import json
import os
import re

WEB = os.path.join(os.path.dirname(__file__), "..", "web", "src")
DIC = os.path.join(WEB, "i18n", "en.json")
TR = re.compile(r"""\btr\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")


def _chaves():
    for raiz, pastas, arquivos in os.walk(WEB):
        pastas[:] = [p for p in pastas if p not in ("portal", "i18n")]
        for a in arquivos:
            if a.endswith((".ts", ".tsx")):
                txt = open(os.path.join(raiz, a), encoding="utf-8").read()
                for m in TR.finditer(txt):
                    yield ast.literal_eval(m.group(1)), os.path.relpath(os.path.join(raiz, a), WEB)


def test_todo_texto_do_painel_tem_traducao_em_ingles():
    dic = json.load(open(DIC, encoding="utf-8"))
    faltam = sorted({f"{arq}: {k!r}" for k, arq in _chaves() if k not in dic})
    assert not faltam, "texto sem tradução em src/i18n/en.json:\n" + "\n".join(faltam[:40])


def test_traducao_mantem_os_marcadores():
    dic = json.load(open(DIC, encoding="utf-8"))
    ph = lambda s: sorted(re.findall(r"\{\d+\}", s))
    ruins = [k for k, v in dic.items() if ph(k) != ph(v)]
    assert not ruins, ruins[:20]


def test_menu_e_telas_principais_em_ingles():
    dic = json.load(open(DIC, encoding="utf-8"))
    for pt, en in (("Hoje", "Today"), ("Clientes", "Clients"), ("Estoque", "Inventory"), ("Precisa de atenção", "Needs attention"),
                   ("Entrar", "Sign in"), ("Salvar", "Save")):
        assert dic.get(pt) == en, pt
