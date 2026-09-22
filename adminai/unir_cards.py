#!/usr/bin/env python3
"""Une cards que o dono disse serem a mesma pessoa.

    python3 adminai/unir_cards.py --unir "332+486+Liam Bourghol+Liam B=Liam Bourghol"
    python3 adminai/unir_cards.py --unir "162+296+Charlie M=Charlie Marron" --aplicar

Cada --unir é "membro+membro[+membro…]=nome final". Membro é o id do card ou o nome
EXATO dele (o nome tem de ser único no cadastro, senão recusa). Sem --aplicar só
mostra o plano. Quem fica é o card com mais dados (e-mail, telefone, piloto,
nascimento); empate, o mais antigo. O nome final corrige a grafia — os dois cards
da Liam estavam errados ("Burghol" e "Bourgnhol"); o título do Asana escreve
"Bourghol".

Usa `identidade.unir`, o mesmo do botão do painel: tudo do duplicado passa para o
principal, e o duplicado inteiro fica guardado em `client_merges`.
"""
import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from command_center.db import agora, aplicar_schema, auditar, conectar, todos, um  # noqa: E402
from command_center.providers import identidade  # noqa: E402

LIGADOS = ("tasks", "waivers", "emails", "invoices")


def _card(con, membro):
    """Card por id ou por nome exato. Nome repetido no cadastro é recusado: não se
    adivinha qual dos dois o dono quis."""
    m = str(membro).strip()
    if m.isdigit():
        c = um(con, "SELECT * FROM clients WHERE id=?", (int(m),))
        if not c:
            sys.exit(f"card #{m} não existe")
    else:
        achados = todos(con, "SELECT * FROM clients WHERE lower(name)=lower(?)", (m,))
        if not achados:
            sys.exit(f"nenhum card chamado exatamente {m!r}")
        if len(achados) > 1:
            sys.exit(f"{len(achados)} cards chamados {m!r}: {[x['id'] for x in achados]} — use o id")
        c = achados[0]
    n = {t: um(con, f"SELECT COUNT(*) AS n FROM {t} WHERE client_id=?", (c["id"],))["n"] for t in LIGADOS}
    return c, n


def _dados(c):
    return sum(1 for k in ("email", "phone", "pilot_name", "pilot_dob") if c[k])


def _mostra(rotulo, c, n):
    print(f"  {rotulo} #{c['id']} {c['name']!r}  piloto={c['pilot_name']!r}  email={c['email'] or '-'}  "
          f"tel={c['phone'] or '-'}  | " + " ".join(f"{t}={n[t]}" for t in LIGADOS))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unir", action="append", default=[], metavar="A+B[+C]=NOME")
    ap.add_argument("--piloto", action="append", default=[], metavar="ID=NOME",
                    help="corrige o nome do piloto de um card (dono: '#238 é Alex Donnell')")
    ap.add_argument("--responsavel", action="append", default=[], metavar="ID=NOME",
                    help="corrige o nome do responsável de um card (rótulo 'Email:' grudado, etc.)")
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()

    planos = []
    for esp in a.unir:
        if "=" not in esp:
            sys.exit(f"--unir precisa ser 'membro+membro=nome final': {esp!r}")
        membros, nome = esp.rsplit("=", 1)
        membros = [x.strip() for x in membros.split("+") if x.strip()]
        if len(membros) < 2 or not nome.strip():
            sys.exit(f"--unir precisa de 2+ membros e um nome final: {esp!r}")
        planos.append((membros, nome.strip()))

    con = conectar()
    aplicar_schema(con)          # a migração não espera o deploy: a ferramenta se serve
    try:
        print("\n" + ("APLICANDO" if a.aplicar else "PLANO (nada foi escrito)"))
        print("=" * 72)
        # resolve TODOS os grupos antes de escrever qualquer um: um nome errado no
        # segundo grupo não pode deixar o primeiro unido pela metade
        grupos = []
        for membros, nome in planos:
            cards = [_card(con, m) for m in membros]
            ids = [c["id"] for c, _ in cards]
            if len(set(ids)) != len(ids):
                sys.exit(f"membro repetido em {membros}")
            cards.sort(key=lambda cn: (-_dados(cn[0]), cn[0]["id"]))
            grupos.append((cards, nome))
        for cards, nome in grupos:
            (keep, nk), resto = cards[0], cards[1:]
            print(f"\n{' + '.join(c['name'] for c, _ in cards)}")
            _mostra("FICA ", keep, nk)
            for c, n in resto:
                _mostra("SAI  ", c, n)
            total = {t: nk[t] + sum(n[t] for _, n in resto) for t in LIGADOS}
            # O "nome final" é o nome da PESSOA (o piloto). O card guarda o responsável em
            # `name` e o piloto em `pilot_name`; quando são gente diferente (#15: Kenneth
            # Savage é o pai, Alexander Savage corre), o responsável fica como está —
            # é ele, com o contato, que confirma identidade (princípio do dono, 22/09).
            tem_responsavel = bool(keep["pilot_name"]) and \
                identidade.chave_exata(keep["pilot_name"]) != identidade.chave_exata(keep["name"])
            resp_final = keep["name"] if tem_responsavel else nome
            print(f"  -> um card só, #{keep['id']}: responsável {resp_final!r}, piloto {nome!r}, com "
                  + " ".join(f"{t}={total[t]}" for t in LIGADOS))
            if not a.aplicar:
                continue
            for drop, nd in resto:
                identidade.unir(con, keep["id"], drop["id"], "owner:cli",
                                f"dono, 22/09: mesma pessoa ({drop['name']!r})")
                auditar(con, "client.merge", "owner:cli", entity_type="client", entity_id=keep["id"],
                        detail={"drop_id": drop["id"], "drop_name": drop["name"], "final_name": nome,
                                "moved": nd, "reason": "dono, 22/09: mesma pessoa"})
            con.execute("UPDATE clients SET name=?, pilot_name=?, updated_at=? WHERE id=?",
                        (resp_final, nome, agora(), keep["id"]))
            con.commit()
            print("  feito.")
        for esp in a.piloto:
            if "=" not in esp:
                sys.exit(f"--piloto precisa ser 'id=nome': {esp!r}")
            cid, nome = esp.split("=", 1)
            c, n = _card(con, cid.strip())
            print(f"\n#{c['id']} {c['name']!r}: piloto {c['pilot_name']!r} -> {nome.strip()!r}")
            if a.aplicar:
                con.execute("UPDATE clients SET pilot_name=?, updated_at=? WHERE id=?", (nome.strip(), agora(), c["id"]))
                auditar(con, "client.update", "owner:cli", entity_type="client", entity_id=c["id"],
                        detail={"pilot_name": {"de": c["pilot_name"], "para": nome.strip()}, "reason": "dono, 22/09"})
                con.commit()
                print("  feito.")
        for esp in a.responsavel:
            if "=" not in esp:
                sys.exit(f"--responsavel precisa ser 'id=nome': {esp!r}")
            cid, nome = esp.split("=", 1)
            c, n = _card(con, cid.strip())
            print(f"\n#{c['id']}: responsável {c['name']!r} -> {nome.strip()!r}  (piloto {c['pilot_name']!r}, e-mail {c['email'] or '-'})")
            if a.aplicar:
                con.execute("UPDATE clients SET name=?, updated_at=? WHERE id=?", (nome.strip(), agora(), c["id"]))
                auditar(con, "client.update", "owner:cli", entity_type="client", entity_id=c["id"],
                        detail={"name": {"de": c["name"], "para": nome.strip()}, "reason": "dono, 22/09"})
                con.commit()
                print("  feito.")
        if not a.unir and not a.piloto and not a.responsavel:
            sys.exit("nada a fazer: passe --unir, --piloto e/ou --responsavel")
        if not a.aplicar:
            print("\nNada foi escrito. Para aplicar, repita com --aplicar.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
