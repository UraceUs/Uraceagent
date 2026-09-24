"""Data cravada em teste que vive dentro de janela relativa é bomba-relógio.

Aconteceu três vezes neste repositório, sempre igual: o teste passa por semanas e um dia
quebra sozinho, sem ninguém ter mexido em nada — a data fixa envelheceu para fora da
janela que o código olha.

- `2026-09-04` quebrou em 18/09 (a atenção "cliente escreveu" olha 14 dias);
- consertaram **naquele lugar só**, com um comentário explicando;
- `2026-09-09` e `2026-09-14` quebraram em 23/09, pelo mesmo motivo.

O comentário não segurou, porque comentário não roda. Este teste roda.

A regra: campo que alimenta janela relativa (`last_at`, `expires_at`) não leva data
literal recente. Ou é relativa a `HOJE`, ou é claramente antiga de propósito — como
`2020-01-01`, que existe para provar que e-mail velho NÃO aparece, e cuja idade só
aumenta.

**O que esta varredura NÃO pega, e por que não tentei forçar.** Em 24/09 quebrou uma
ASSERÇÃO: eu trocara a fixture para data relativa e deixara `"ASSINADA em 2026-08-16"`
escrito à mão. Tentei estender a regra para asserções e ela acusou inocentes — testes
que conferem `vence_em == "2026-09-11"` a partir de um serviço em `"2026-09-13"`, que é
aritmética entre datas FIXAS e nunca envelhece. Guarda que acusa inocente é guarda que
alguém silencia, e aí ela não protege mais nada.

Se isso voltar a morder, o conserto certo não é uma regra estática mais esperta: é rodar
a suíte com o relógio adiantado alguns meses. Isso pega tudo — atribuição e asserção —
sem acusar ninguém à toa.
"""
import ast
import os
import re
from datetime import date

import pytest

TESTES = os.path.dirname(os.path.abspath(__file__))
# Campos que o código filtra por "últimos N dias" ou "vence em N dias".
CAMPOS = ("last_at", "expires_at")
LITERAL = re.compile(r"\b(" + "|".join(CAMPOS) + r")\s*=\s*[\"'](\d{4})-(\d{2})-(\d{2})")
# Perigosa é a data que CAMINHA PARA UMA BORDA: qualquer data futura (anda rumo ao
# vencimento) e qualquer passado recente (sai das janelas curtas de 14/30 dias). Data
# bem antiga é segura, porque só envelhece para o lado certo — `2020-01-01` existe para
# provar que e-mail velho não aparece, e ficar mais velho só reforça isso.
DIAS_PARA_SER_ANTIGA = 365


def _arquivos():
    for nome in sorted(os.listdir(TESTES)):
        if nome.startswith("test_") and nome.endswith(".py") and nome != os.path.basename(__file__):
            yield os.path.join(TESTES, nome)


def test_nenhum_teste_crava_data_recente_em_campo_de_janela():
    hoje = date.today()
    achados = []
    for caminho in _arquivos():
        with open(caminho, encoding="utf-8") as f:
            for n, linha in enumerate(f, 1):
                for campo, a, m, d in LITERAL.findall(linha):
                    try:
                        quando = date(int(a), int(m), int(d))
                    except ValueError:
                        continue
                    if (hoje - quando).days < DIAS_PARA_SER_ANTIGA:
                        achados.append(f"{os.path.basename(caminho)}:{n} {campo}={quando}")
    assert not achados, (
        "data recente cravada em campo de janela relativa — o teste vai quebrar sozinho "
        "quando ela envelhecer. Use algo relativo a HOJE:\n  " + "\n  ".join(achados))


def test_a_propria_regra_pega_o_caso_que_quebrou_em_23_09():
    """Prova que a varredura acima não é decorativa: ela acusa o padrão de verdade."""
    hoje = date.today()
    linha = f'last_at="{hoje.isoformat()}T10:00:00", handled=0'
    campo, a, m, d = LITERAL.findall(linha)[0]
    assert campo == "last_at"
    assert (hoje - date(int(a), int(m), int(d))).days < DIAS_PARA_SER_ANTIGA


def test_data_antiga_de_proposito_continua_permitida():
    """`2020-01-01` existe para provar que e-mail velho NÃO aparece. Isso nunca envelhece
    para o lado errado — e proibir seria trocar uma bomba por um estorvo."""
    hoje = date.today()
    campo, a, m, d = LITERAL.findall('last_at="2020-01-01T00:00:00", is_inbox=1')[0]
    assert (hoje - date(int(a), int(m), int(d))).days >= DIAS_PARA_SER_ANTIGA


def test_data_futura_e_sempre_perigosa():
    """Waiver com `expires_at="2027-09-15"` parece folgada — e é, por onze meses. Depois
    vira falha sozinha, no meio de uma sexta-feira, sem ninguém ter mexido em nada."""
    hoje = date.today()
    campo, a, m, d = LITERAL.findall('expires_at="2027-09-15"')[0]
    assert (hoje - date(int(a), int(m), int(d))).days < DIAS_PARA_SER_ANTIGA
