#!/usr/bin/env python3
"""Une cards que o dono disse serem a mesma pessoa.

    python3 adminai/unir_cards.py --unir "332,486,Liam Bourghol" --unir "162,296,Charlie Marron"
    python3 adminai/unir_cards.py --unir ... --aplicar

Cada --unir é "idA,idB[,nome final]". Sem --aplicar só mostra o plano. Quem fica é o
card com mais dados (e-mail, telefone, piloto, nascimento); empate, o mais antigo.
O nome final, se dado, corrige a grafia — os dois cards da Liam estavam errados
("Burghol" e "Bourgnhol"); o título do Asana escreve "Bourghol".

Usa `identidade.unir`, o mesmo do botão do painel: tudo do duplicado passa para o
principal, e o duplicado inteiro fica guardado em `client_merges`.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from command_center.db import agora, auditar, conectar, um  # noqa: E402
from command_center.providers import identidade  # noqa: E402

LIGADOS = ("tasks", "waivers", "emails", "invoices")


def _card(con, cid):
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    if not c:
        sys.exit(f"card #{cid} não existe")
    n = {t: um(con, f"SELECT COUNT(*) AS n FROM {t} WHERE client_id=?", (cid,))["n"] for t in LIGADOS}
    return c, n


def _dados(c):
    return sum(1 for k in ("email", "phone", "pilot_name", "pilot_dob") if c[k])


def _mostra(rotulo, c, n):
    print(f"  {rotulo} #{c['id']} {c['name']!r}  piloto={c['pilot_name']!r}  email={c['email'] or '-'}  "
          f"tel={c['phone'] or '-'}  | " + " ".join(f"{t}={n[t]}" for t in LIGADOS))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unir", action="append", required=True, metavar="A,B[,NOME]")
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()

    planos = []
    for esp in a.unir:
        p = [x.strip() for x in esp.split(",", 2)]
        if len(p) < 2 or not p[0].isdigit() or not p[1].isdigit():
            sys.exit(f"--unir precisa ser 'idA,idB[,nome]': {esp!r}")
        planos.append((int(p[0]), int(p[1]), p[2] if len(p) > 2 and p[2] else None))

    con = conectar()
    try:
        print("\n" + ("APLICANDO" if a.aplicar else "PLANO (nada foi escrito)"))
        print("=" * 72)
        for ida, idb, nome in planos:
            (ca, na), (cb, nb) = _card(con, ida), _card(con, idb)
            keep, drop = (ca, cb) if (_dados(ca), -ca["id"]) >= (_dados(cb), -cb["id"]) else (cb, ca)
            nk, nd = (na, nb) if keep["id"] == ca["id"] else (nb, na)
            print(f"\n{keep['name']} + {drop['name']}")
            _mostra("FICA ", keep, nk)
            _mostra("SAI  ", drop, nd)
            final = nome or keep["name"]
            print(f"  -> um card só, #{keep['id']} {final!r}, com "
                  + " ".join(f"{t}={nk[t] + nd[t]}" for t in LIGADOS))
            if not a.aplicar:
                continue
            identidade.unir(con, keep["id"], drop["id"], "owner:cli",
                            f"dono, 22/09: mesma pessoa, erro de digitação ({drop['name']!r})")
            if nome and nome != keep["name"]:
                con.execute("UPDATE clients SET name=?, updated_at=? WHERE id=?", (nome, agora(), keep["id"]))
            auditar(con, "client.merge", "owner:cli", entity_type="client", entity_id=keep["id"],
                    detail={"drop_id": drop["id"], "drop_name": drop["name"], "final_name": final,
                            "moved": nd, "reason": "dono, 22/09: mesma pessoa, erro de digitação"})
            con.commit()
            print("  feito.")
        if not a.aplicar:
            print("\nNada foi escrito. Para aplicar, repita com --aplicar.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
