#!/usr/bin/env python3
"""De quem é cada serviço — varredura e conserto do quadro inteiro.

Dono, 22/09: ao marcar uma sessão nova para o David Pera ele achou 113 serviços no
card, e 112 eram de outras pessoas. O título do Asana sempre diz de quem é; o
painel é que não estava lendo.

    python3 adminai/atribuir_servicos.py            # varredura: não escreve nada
    python3 adminai/atribuir_servicos.py --aplicar  # move cada serviço para o card certo

Move só o que é certo. Nome ambíguo e nome de uma palavra só sem card saem na
lista para decisão humana — unir no escuro é criar o mesmo problema do outro lado.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from command_center.db import aplicar_schema, conectar, um  # noqa: E402
from command_center.providers import atribuicao, identidade  # noqa: E402


def _nome(con, cid):
    if not cid:
        return "(sem card)"
    c = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (cid,))
    return f"#{cid} {(c['pilot_name'] or c['name']) if c else '?'}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="move de verdade (sem isto é só varredura)")
    ap.add_argument("--limite", type=int, default=40, help="quantas linhas mostrar por lista")
    ap.add_argument("--ler-descricoes", action="store_true",
                    help="para o que ficar em dúvida pelo título, busca a descrição no Asana (responsável + contato)")
    a = ap.parse_args()

    con = conectar()
    aplicar_schema(con)          # a migração não espera o deploy: a ferramenta se serve
    try:
        rel = atribuicao.redistribuir(con, aplicar=a.aplicar, ler_descricoes=a.ler_descricoes)
        print("\n" + ("APLICADO" if a.aplicar else "VARREDURA (nada foi escrito)"))
        print("=" * 72)
        print(atribuicao.resumo(rel))
        if rel.get("falhas_leitura"):
            f = rel["falhas_leitura"]
            print(f"\n!!! {len(f)} descrição(ões) NÃO puderam ser lidas no Asana. Primeiro erro:")
            print(f"    {f[0]['title'][:60]} -> {f[0]['erro']}")

        if rel["movidos"]:
            print(f"\n--- serviços que {'foram' if a.aplicar else 'seriam'} movidos "
                  f"({len(rel['movidos'])}) ---")
            for m in rel["movidos"][:a.limite]:
                print(f"  {m['title'][:56]:<56} {_nome(con, m['de'])} -> "
                      f"{m['para_nome']} ({m['motivo']})")
            if len(rel["movidos"]) > a.limite:
                print(f"  … e mais {len(rel['movidos']) - a.limite}")

        if rel["criados"]:
            print(f"\n--- cards {'criados' if a.aplicar else 'que nasceriam'} ({len(rel['criados'])}) ---")
            print("    (regra do dono: na dúvida o serviço NUNCA vai para o card de outra pessoa)")
            for c in rel["criados"][:a.limite]:
                print(f"  {c['nome']:<24} {c['servicos']:>3} serviço(s)  — {c['porque']}")
                for t in c.get("titulos", []):
                    print(f"       ex.: {t[:64]}")

        if rel["unir"]:
            print(f"\n--- PARA VOCÊ UNIR: card novo que pode ser alguém que já existe ({len(rel['unir'])}) ---")
            print("    (= confirmado por contato/responsável · ~ só o nome parece · ? nada)")
            for x in rel["unir"][:a.limite]:
                print(f"  {x['nome']:<24} {x['servicos']:>3} serviço(s)")
                for p in x["parecidos"]:
                    sinal = {"confirmado": "=", "parece": "~"}.get(p.get("grau"), "?")
                    print(f"       {sinal} #{p['id']} {p['nome']:<22} resp. {p['responsavel'] or '-':<22} "
                          f"{p['email'] or '-'}  {p['phone'] or '-'}")

        if rel["sem_nome"]:
            print(f"\n--- títulos sem gente reconhecível ({len(rel['sem_nome'])}) ---")
            for x in rel["sem_nome"][:a.limite]:
                print(f"  {x['title'][:60]:<60} hoje em {_nome(con, x['client_id'])}")
            if len(rel["sem_nome"]) > a.limite:
                print(f"  … e mais {len(rel['sem_nome']) - a.limite}")

        if a.aplicar:
            identidade.recalcular_status(con)
            con.commit()
            pares = identidade.candidatos_duplicados(con)
            if pares:
                print(f"\n--- pares que parecem a mesma pessoa ({len(pares)}) — decidir no painel ---")
                for p in pares[:a.limite]:
                    print(f"  #{p['a']['id']} {p['a']['pilot_name'] or p['a']['name']:<24} × "
                          f"#{p['b']['id']} {p['b']['pilot_name'] or p['b']['name']:<24} {p['why']}")
        else:
            print("\nNada foi escrito. Para aplicar: "
                  "python3 adminai/atribuir_servicos.py --aplicar")
    finally:
        con.close()


if __name__ == "__main__":
    main()
