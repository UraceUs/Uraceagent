#!/usr/bin/env python3
"""Extrator de aprendizados — o começo do learning loop (D4 da auditoria).

Lê o log de auditoria da ponte (SQLite) e transforma padrões operacionais
em documentos-candidato no vault (`brain/09_LEARNINGS/`, status: candidate).
**Nunca promove**: candidato só vira conhecimento quando Italo/Eduardo
mudarem o status no Obsidian — e só então entra no índice de retrieval.

v1 é deterministico (sem LLM): extrai o que já é sinal objetivo no log —
1. Motivos de escalação recorrentes (o que os leads pedem que o agente
   não resolve) — agrupados por motivo, com contagem.
2. Buscas do Brain sem nenhum resultado (kind=brain, "sem hits") — buracos
   reais de conhecimento apontados pelos próprios leads.
3. Links de programa não configurados acionados em conversa (portão G1).

Dedupe por slug: se o arquivo do padrão já existe, só atualiza a contagem/
última ocorrência — e se um humano já mudou o status (não é mais
candidate), o extrator NÃO toca mais no arquivo.

Uso:
    python3 brain/extract_learnings.py --self-test
    python3 brain/extract_learnings.py --days 7 --dry-run
    python3 brain/extract_learnings.py            # roda de verdade
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

BRAIN_DIR = Path(__file__).resolve().parent
LEARNINGS_DIR = BRAIN_DIR / "09_LEARNINGS"


def audit_db_path() -> Path:
    urace = Path(os.environ.get("URACE_DIR", Path.home() / ".urace"))
    return urace / "salesbridge.db"


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len] or "sem-titulo"


# ---------------------------------------------------------------- extração
def collect_findings(db_path: Path, days: int) -> list[dict]:
    if not db_path.exists():
        return []
    since = int(time.time()) - days * 86400
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        findings: list[dict] = []

        rows = conn.execute(
            "SELECT detail, COUNT(*) AS n, MAX(ts) AS last_ts FROM audit "
            "WHERE kind='escalation' AND ts >= ? GROUP BY detail "
            "ORDER BY n DESC LIMIT 12", (since,)).fetchall()
        for r in rows:
            findings.append({
                "kind": "escalacao-recorrente",
                "key": r["detail"][:80],
                "count": r["n"], "last_ts": r["last_ts"],
                "title": f"Escalação recorrente: {r['detail'][:60]}",
                "body": (
                    f"O motivo de escalação **\"{r['detail'][:200]}\"** ocorreu "
                    f"{r['n']}x nos últimos {days} dias.\n\n"
                    "Perguntas para revisão humana: o agente deveria saber "
                    "responder isso sozinho (novo documento no Brain)? Ou a "
                    "escalação está correta e o padrão só merece registro?"),
            })

        rows = conn.execute(
            "SELECT detail, COUNT(*) AS n, MAX(ts) AS last_ts FROM audit "
            "WHERE kind='brain' AND detail LIKE '%sem hits%' AND ts >= ? "
            "GROUP BY detail ORDER BY n DESC LIMIT 12", (since,)).fetchall()
        for r in rows:
            q = r["detail"]
            m = re.search(r"q='([^']*)'", q) or re.search(r'q="([^"]*)"', q)
            query = m.group(1) if m else q[:80]
            findings.append({
                "kind": "busca-sem-resposta",
                "key": query[:80],
                "count": r["n"], "last_ts": r["last_ts"],
                "title": f"Busca sem resposta no Brain: {query[:50]}",
                "body": (
                    f"A busca **{query!r}** não encontrou nenhum documento "
                    f"({r['n']}x nos últimos {days} dias).\n\n"
                    "É um buraco de conhecimento apontado por conversa real: "
                    "criar o documento que responde isso, ou adicionar "
                    "aliases a um documento existente."),
            })

        rows = conn.execute(
            "SELECT detail, COUNT(*) AS n, MAX(ts) AS last_ts FROM audit "
            "WHERE kind='gate' AND detail LIKE '%link não configurado%' "
            "AND ts >= ? GROUP BY detail ORDER BY n DESC LIMIT 6",
            (since,)).fetchall()
        for r in rows:
            findings.append({
                "kind": "link-faltando",
                "key": r["detail"][:80],
                "count": r["n"], "last_ts": r["last_ts"],
                "title": f"Link de programa faltando: {r['detail'][:50]}",
                "body": (
                    f"O portão G1 bloqueou {r['n']}x por link não configurado "
                    f"({r['detail'][:150]}). Cada ocorrência é um lead que "
                    "ouviu \"vou confirmar\" em vez de receber a página — "
                    "configurar o link em `salesagent/config/program-links.json`."),
            })
        return findings
    finally:
        conn.close()


# ------------------------------------------------------------------ escrita
def write_candidates(findings: list[dict], learnings_dir: Path,
                     dry_run: bool = False) -> dict:
    stats = {"created": 0, "updated": 0, "skipped_human": 0}
    learnings_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()

    for f in findings:
        slug = slugify(f"{f['kind']}-{f['key']}")
        path = learnings_dir / f"auto - {slug}.md"
        if path.exists():
            head = path.read_text(encoding="utf-8")[:400]
            m = re.search(r"^status:\s*(\S+)", head, re.MULTILINE)
            if m and m.group(1).lower() != "candidate":
                stats["skipped_human"] += 1  # humano assumiu; não tocar
                continue
            stats["updated"] += 1
        else:
            stats["created"] += 1
        if dry_run:
            continue
        last_seen = datetime.date.fromtimestamp(f["last_ts"]).isoformat()
        path.write_text(
            "---\n"
            "type: learning\n"
            f"category: {f['kind']}\n"
            f"topic: {slug[:40]}\n"
            "priority: medium\n"
            "status: candidate\n"
            "source: conversa_real\n"
            f"last_updated: {today}\n"
            f"tags: [aprendizado, automatico, {f['kind']}]\n"
            "---\n\n"
            f"# [CANDIDATO] {f['title']}\n\n"
            f"> Gerado automaticamente pelo extrator (ocorrências: "
            f"{f['count']}, última: {last_seen}). Revise: edite o conteúdo "
            f"como quiser e mude `status` para `approved` para o agente "
            f"passar a usar — ou para `archived` para descartar.\n\n"
            f"{f['body']}\n",
            encoding="utf-8")
    return stats


# --------------------------------------------------------------- self-test
def self_test() -> int:
    import tempfile
    failures = []

    def check(label, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {label}" + ("" if cond else f"  {detail}"))
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "audit.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE audit (id INTEGER PRIMARY KEY, ts INTEGER,"
                     " lead_id INTEGER, kind TEXT, detail TEXT)")
        now = int(time.time())
        for _ in range(3):
            conn.execute("INSERT INTO audit (ts, kind, detail) VALUES (?,?,?)",
                         (now, "escalation", "pedido de desconto"))
        conn.execute("INSERT INTO audit (ts, kind, detail) VALUES (?,?,?)",
                     (now, "brain", "3ms q='gift card' -> sem hits"))
        conn.execute("INSERT INTO audit (ts, kind, detail) VALUES (?,?,?)",
                     (now - 90 * 86400, "escalation", "motivo antigo"))
        conn.commit()
        conn.close()

        findings = collect_findings(db, days=7)
        check("agrupa escalações com contagem",
              any(f["kind"] == "escalacao-recorrente" and f["count"] == 3
                  for f in findings), str(findings))
        check("captura busca sem hits",
              any(f["kind"] == "busca-sem-resposta" and "gift card" in f["key"]
                  for f in findings))
        check("janela de dias respeitada (antigo fora)",
              not any("motivo antigo" in f["key"] for f in findings))

        ldir = Path(td) / "learnings"
        stats = write_candidates(findings, ldir)
        check("candidatos criados", stats["created"] == len(findings), str(stats))
        files = list(ldir.glob("auto - *.md"))
        check("arquivos no formato do vault",
              all("status: candidate" in p.read_text(encoding='utf-8') for p in files))

        stats2 = write_candidates(findings, ldir)
        check("re-execução atualiza, não duplica",
              stats2["created"] == 0 and stats2["updated"] == len(findings), str(stats2))

        promoted = files[0]
        promoted.write_text(promoted.read_text(encoding="utf-8")
                            .replace("status: candidate", "status: approved"),
                            encoding="utf-8")
        stats3 = write_candidates(findings, ldir)
        check("arquivo promovido por humano nunca é tocado",
              stats3["skipped_human"] == 1, str(stats3))
        check("conteúdo promovido intacto",
              "status: approved" in promoted.read_text(encoding="utf-8"))

        check("banco inexistente devolve vazio",
              collect_findings(Path(td) / "nao-existe.db", 7) == [])

    print()
    if failures:
        print(f"SELF TEST FALHOU — {len(failures)}")
        return 1
    print("SELF TEST PASSOU — extração, janela, dedupe e respeito à "
          "promoção humana verificados")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Extrai aprendizados candidatos do log da ponte.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    findings = collect_findings(audit_db_path(), args.days)
    stats = write_candidates(findings, LEARNINGS_DIR, dry_run=args.dry_run)
    print(f"{len(findings)} padrão(ões) encontrados — "
          f"{stats['created']} candidatos novos, {stats['updated']} "
          f"atualizados, {stats['skipped_human']} sob controle humano (intactos)")
    if stats["created"] and not args.dry_run:
        print("Revisão: abra brain/09_LEARNINGS/ no Obsidian e promova ou "
              "arquive os candidatos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
