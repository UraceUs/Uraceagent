#!/usr/bin/env python3
"""Teste de balcão do SDR: o que ele decidiria para uma mensagem.

Sem Kommo, sem rede, sem modelo — só as regras de salesagent/sdr. Serve para
conferir uma regra antes de subir de nível, ou para explicar a alguém por que
um card foi para tal etapa.

Uso:
    python3 salesagent/tools/sdr_avaliar.py "Quanto custa o 1-Day?"
    python3 salesagent/tools/sdr_avaliar.py --zona Comercial "quero falar com alguém"
    python3 salesagent/tools/sdr_avaliar.py --email mfa@kommo.com "713157 is your code"
    python3 salesagent/tools/sdr_avaliar.py --tabela      # a bateria de exemplos
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sdr  # noqa: E402

EXEMPLOS = [
    "Oi", "Quanto custa o 1-Day?", "Tem vaga no sábado?", "713157 is your code to log in to Kommo",
    "Nossa empresa oferece tráfego pago", "Pare de mandar mensagem", "Lets do it, when can he start?",
    "He currently races in SKUSA", "Tem desconto?", "Obrigado!", "Onde fica a pista?",
    "Quero falar com alguém", "Evento da empresa para 12 pessoas",
]


def linha(texto, zona, email):
    card = {"existe": True, "zona": zona} if zona else {}
    r = sdr.avaliar(texto, card=card, remetente_email=email)
    t, ro = r["triagem"], r["roteamento"]
    etapa = t["destino"]["etapa"] if t["destino"]["mover"] else "(não mexe)"
    extra = f" [{ro['prioridade']}]" if ro.get("prioridade") else ""
    return f"{texto[:44]:44} | {t['acao']:16} | {etapa:32} | {ro['acao']}{extra}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("texto", nargs="*")
    ap.add_argument("--zona", choices=["Entrada", "Comercial"], default="Entrada",
                    help="onde o card está hoje (padrão: Entrada)")
    ap.add_argument("--email", default=None, help="e-mail do remetente, se houver")
    ap.add_argument("--tabela", action="store_true")
    a = ap.parse_args()
    textos = EXEMPLOS if a.tabela or not a.texto else [" ".join(a.texto)]
    print(f"{'mensagem':44} | {'ação':16} | {'etapa no Novo funil':32} | robô")
    for texto in textos:
        print(linha(texto, a.zona, a.email))
    return 0


if __name__ == "__main__":
    sys.exit(main())
