#!/usr/bin/env python3
"""Bateria de conversas do robô SDR (14/10): o que ele decide para cada coisa que um lead escreve, e
o que a guarda faz com as respostas erradas que já saíram de verdade.

Sem rede e sem modelo: é a parte do robô que é código (rota antes da IA e guarda depois dela). O que
o modelo escreve entre uma e outra é conferido pelo card "Testar o robô" do painel. Cada caso aqui
vem do playbook de 13/10, dos prints do Instagram ou de um erro que já aconteceu.

Uso:
    python3 -m pytest -q salesagent/tests/test_sdr_bateria.py
"""
import sys
from pathlib import Path

import pytest

SALESAGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SALESAGENT))

import sdr  # noqa: E402
from sdr import estilo  # noqa: E402

# (o que o lead escreve, rota esperada, motivo esperado)
ROTAS = [
    # responde direto, sem passar para ninguém
    ("Oi", "responder", None),
    ("Quanto custa?", "responder", None),
    ("Oi, quanto custa para criança de 8 anos?", "responder", None),
    ("Where are you located?", "responder", None),
    ("Quais dias vocês têm?", "responder", None),
    ("How old does my kid have to be?", "responder", None),
    ("Quero começar, como faço?", "responder", None),
    # "agora não": respeita, não insiste (agora_nao), mas "não sei" é resposta, não adiamento
    ("Agora não, obrigado", "adiar", "AGORA_NAO"),
    ("Not now, maybe later", "adiar", "AGORA_NAO"),
    ("Depois eu falo com você", "adiar", "AGORA_NAO"),
    ("Agora não sei a idade dele?", "responder", None),
    # pedido de parar fecha de vez
    ("pare de mandar mensagem", "confirmar_opt_out", "OPT_OUT"),
    ("unsubscribe", "confirmar_opt_out", "OPT_OUT"),
    # objeção de preço e desconto: a ponte oferece a call com o time
    ("Tem desconto?", "escalar", "NEGOCIACAO"),
    ("Está muito caro", "escalar", "NEGOCIACAO"),
    ("Sim mas esta caro", "escalar", "NEGOCIACAO"),
    ("Consideraria se fosse mais barato", "escalar", "NEGOCIACAO"),
    ("That's too expensive for us", "escalar", "NEGOCIACAO"),
    # passa para a pessoa
    ("Quero falar com uma pessoa", "escalar", "PEDIDO_HUMANO"),
    ("I compete in Rotax series", "escalar", "PILOTO_COMPETIDOR"),
    ("Quero fechar", "escalar", "SINAL_CONVERSAO"),
]


@pytest.mark.parametrize("texto,acao,motivo", ROTAS, ids=[r[0][:40] for r in ROTAS])
def test_rota_antes_do_modelo(texto, acao, motivo):
    r = sdr.avaliar(texto)["roteamento"]
    assert r["acao"] == acao, r
    assert r.get("motivo") == motivo, r


# Respostas que o robô já deu (ou poderia dar) e a guarda precisa consertar.
PRINT_INSTAGRAM = ("It's a full day on track in a real race kart. You can see it all here: "
                   "https://urace.us/product/go-kart-driving-experience/ How old is the driver? "
                   "That's what sets the exact price.")


def test_guarda_primeira_resposta_sai_sem_link_e_sem_a_chamada():
    limpo, v = estilo.um_ativo(PRINT_INSTAGRAM, primeira_resposta=True)
    assert "http" not in limpo and "here:" not in limpo
    assert "How old is the driver?" in limpo and v == ["link_na_primeira_resposta"]


def test_guarda_depois_da_primeira_passa_um_link_so():
    texto = "Veja:\nhttps://urace.us/urace-academy/\nE o vídeo: https://youtu.be/TlLKzFPvI5g\nQual a idade?"
    limpo, v = estilo.um_ativo(texto, primeira_resposta=False)
    assert limpo.count("http") == 1 and "urace-academy" in limpo
    assert "mais_de_um_link" in v


def test_guarda_uma_pergunta_so():
    limpo, v = estilo.um_ativo("Quantos anos tem? Já andou de kart? E o que ele quer?", primeira_resposta=False)
    assert limpo.count("?") == 1 and limpo.startswith("Quantos anos tem?")
    assert "mais_de_uma_pergunta" in v


@pytest.mark.parametrize("frase", [
    "Good to hear from you.", "Best regards, Chase.", "I hope this message finds you well.",
    "Bom te ver de novo por aqui.", "Come by anytime.", "It's 20% off today.", "Great question!",
])
def test_guarda_corta_frase_proibida(frase):
    limpo, v = estilo.aplicar(f"A day on track is $719. {frase}")
    assert limpo == "A day on track is $719.", (limpo, v)
    assert any(x.startswith("nunca_dizer:") for x in v)


def test_guarda_sem_emoji_e_sem_travessao():
    limpo, _ = estilo.aplicar("Great 🏁 — see you there")
    assert "🏁" not in limpo and "—" not in limpo


# A persona não cita nomes do time ao lead (dono, 14/10). Os nomes só aparecem na própria proibição.
def test_persona_nao_cita_nome_do_time():
    texto = (SALESAGENT / "instructions" / "urace-sales-agent.md").read_text(encoding="utf-8")
    assert texto.count("Lucas") == 1 and texto.count("Italo") == 1, "só na linha que proíbe citar"
    assert "Never name anyone from the team" in texto


def test_persona_cabe_no_limite_do_openclaw():
    texto = (SALESAGENT / "instructions" / "urace-sales-agent.md").read_text(encoding="utf-8")
    assert len(texto) < 30000, "o limite no VPS é 40.000; passar de 30.000 pede enxugar"
    assert texto.rstrip().splitlines()[-1].strip(), "o arquivo termina em conteúdo, não cortado"


def test_guarda_nao_se_reapresenta_depois_da_primeira_resposta():
    texto = ("Oi! Aqui é o Chase, da URACE.\nUm dia inteiro na pista: $719.\n"
             "É pra você ou pra outra pessoa, e qual a idade do piloto?")
    limpo, v = estilo.sem_reapresentacao(texto, primeira_resposta=False)
    assert limpo == "Um dia inteiro na pista: $719.\nÉ pra você ou pra outra pessoa, e qual a idade do piloto?"
    assert v == ["reapresentacao"]
    # na primeira resposta a apresentação fica
    assert estilo.sem_reapresentacao(texto, primeira_resposta=True) == (texto, [])
    # inglês, e "Hi" junto da apresentação
    limpo, _ = estilo.sem_reapresentacao("Hi! Chase here from URACE. How old is the driver?", False)
    assert limpo == "How old is the driver?"
    # nada a cortar
    assert estilo.sem_reapresentacao("Legal, 8 anos já pode correr.", False) == ("Legal, 8 anos já pode correr.", [])
