#!/usr/bin/env python3
"""Roda as sincronias pela linha de comando — sem painel, sem login.

    python3 adminai/sincronizar.py docusign
    python3 adminai/sincronizar.py asana gmail
    python3 adminai/sincronizar.py --listar
    python3 adminai/sincronizar.py tudo

Nasceu de 22/09: a extensão da VPS precisou rodar a sincronia do DocuSign (o conserto
da paginação, que destrava a waiver da Nadine) e não achou comando nenhum — só o botão
do painel, que exige login. Ela não improvisou, e fez certo: reportou a falta.

LEITURA E ESPELHO, só. Estas funções puxam dos sistemas para o banco do painel; não
enviam e-mail, não criam nada fora, não apagam. O que escreve para fora tem porta
própria, com política e confirmação.
"""
import argparse
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()          # o python3 do sistema não tem as dependências (22/09)

from command_center.db import aplicar_schema, conectar  # noqa: E402
from command_center.providers import sync  # noqa: E402

# nome na linha de comando -> (função, o que faz)
SINCRONIAS = {
    "asana":      (sync.sync_asana,            "quadro U-RACE: colunas do dia, serviços e clientes"),
    "asana-full": (sync.sync_asana_completo,   "histórico COMPLETO do quadro (demorado)"),
    "docusign":   (sync.sync_docusign,         "envelopes e waivers (pagina até o fim desde 22/09)"),
    "gmail":      (sync.sync_gmail,            "caixas urace@ e support@"),
    "qbo":        (sync.sync_qbo,              "QuickBooks: invoices e pagamentos"),
    "kommo":      (sync.sync_kommo,            "CRM: leads e conversas"),
    "corridas":   (sync.sincronizar_corridas,  "coluna RACES vira o calendário de corridas"),
    "cerebro":    (sync.sync_cerebro,          "brain/ para o painel"),
    "tudo":       (sync.sync_tudo,             "todas as de cima, na ordem"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("quais", nargs="*", help="uma ou mais: " + ", ".join(SINCRONIAS))
    ap.add_argument("--listar", action="store_true", help="mostra o que existe e sai")
    a = ap.parse_args()

    if a.listar or not a.quais:
        print("\nsincronias disponíveis:\n")
        for nome, (_f, oq) in SINCRONIAS.items():
            print(f"  {nome:<12} {oq}")
        print("\nex.: python3 adminai/sincronizar.py docusign")
        return 0 if a.listar else 2

    desconhecidas = [q for q in a.quais if q not in SINCRONIAS]
    if desconhecidas:
        print(f"não conheço: {', '.join(desconhecidas)}. Use --listar.", file=sys.stderr)
        return 2

    con = conectar()
    aplicar_schema(con)
    ruim = 0
    try:
        for nome in a.quais:
            fn, _oq = SINCRONIAS[nome]
            print(f"\n=== {nome} ===", flush=True)
            t0 = time.monotonic()
            try:
                r = fn(con)
                con.commit()
                print(f"  {r}")
                # as funções devolvem {"ok": bool, ...}; nem todas, então só reprova o que disser não
                if isinstance(r, dict) and r.get("ok") is False:
                    ruim += 1
                    print("  !! esta sincronia falhou (veja o motivo acima)", file=sys.stderr)
            except Exception as e:                       # noqa: BLE001 - uma que falha não derruba as outras
                ruim += 1
                print(f"  !! {type(e).__name__}: {e}", file=sys.stderr)
            print(f"  ({time.monotonic() - t0:.1f}s)")
    finally:
        con.close()
    if ruim:
        print(f"\n{ruim} sincronia(s) falharam.", file=sys.stderr)
    return 1 if ruim else 0


if __name__ == "__main__":
    sys.exit(main())
