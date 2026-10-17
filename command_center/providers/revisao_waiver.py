"""Revisar e confirmar antes do clique final (#112; lacunas C-2, C-4 e A-5 do P-15).

A Fla. Stat. §668.50(10) deixa a pessoa desfazer o efeito de um erro quando o sistema não deu chance de evitá-lo
(assinou pelo piloto errado, digitou outro nome). Por isso a assinatura tem dois passos, e o servidor exige os dois:

1. **Revisão** (`POST .../review`): confere tudo menos o código do e-mail e devolve o resumo (documento, piloto, quem
   assina, parentesco, nome digitado e se bate com o da conta, validade e a frase de efeito legal). A revisão vai
   para `waiver_reviews` (hash do conteúdo, hora, IP) e para a trilha (`reviewed`, #111).
2. **Confirmação** (o POST de assinar): exige o `review_id` de uma revisão desta conta e piloto (ou deste convite),
   de até `VALIDADE_MIN` minutos, nunca usada e com **o mesmo conteúdo**. Se o nome digitado é outro, exige
   `name_mismatch_confirmed`. A revisão é marcada usada na mesma transação do INSERT da waiver; a trilha guarda as
   duas horas (`reviewed_at`, `confirmed_at`) e os dois nomes.

Nome "igual" é sem acento, sem diferença de maiúsculas e sem espaço repetido (A-5).
"""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from command_center.db import um

VALIDADE_MIN = 30                  # a revisão vale meia hora
POR_HORA = 20                      # revisões por conta e piloto (ou por convite) na última hora
# C-4: o que a tela mostra ao lado do botão final, e o que a trilha guarda como mostrado
BOTAO = "I agree — sign the waiver"
EFEITO_LEGAL = (f"By tapping “{BOTAO}” you confirm that you have read the whole document, that you agree to its terms "
                "and that you agree to sign it electronically. Your electronic signature has the same legal effect as a "
                "handwritten signature.")


class Demais(Exception):
    """Revisões demais na última hora (a rota devolve 429)."""


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normal(nome):
    """O nome para comparar: sem acento, sem maiúsculas e sem espaço repetido."""
    sem = "".join(c for c in unicodedata.normalize("NFKD", nome or "") if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem).strip().casefold()


def mesmo_nome(a, b):
    return bool(normal(a)) and normal(a) == normal(b)


def conteudo(dados, nome, png_sha, pilot_id, kind, template_sha):
    """O hash do que a pessoa revisou: o que muda entre a revisão e o clique final não assina."""
    c = {"typed_name": nome, "signature_png_sha256": png_sha, "pilot_id": pilot_id, "kind": kind, "template_sha256": template_sha,
         "relationship": (dados.get("relationship") or "").strip().lower() or None,
         "guardian_declaration": bool(dados.get("guardian_declaration")), "read_and_agree": bool(dados.get("read_and_agree")),
         "consent_esign": bool(dados.get("consent_esign")), "english_understood": bool(dados.get("english_understood")),
         "document_read_at": dados.get("document_read_at"), "document_read_mode": dados.get("document_read_mode") or "pdf_viewer"}
    return hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _escopo(fluxo, ids):
    return ("invite_id", ids.get("invite_id")) if fluxo == "invite" else ("account_id", ids.get("account_id"))


def criar(con, fluxo, ids, template_sha, conteudo_sha, nome, nome_cadastro, parentesco, ip=None, user_agent=None, detail=None):
    """Grava a revisão e o passo `reviewed` na trilha. `ids`: account_id, invite_id, pilot_id, client_id, kind,
    template_version_id (os mesmos da trilha)."""
    from command_center.db import inserir, transacao
    from command_center.providers import trilha_waiver as tw
    campo, valor = _escopo(fluxo, ids)
    agora_utc = datetime.now(timezone.utc)
    n = um(con, f"""SELECT COUNT(*) AS n FROM waiver_reviews WHERE {campo}=? AND pilot_id IS ? AND created_at >= ?""",
           (valor, ids.get("pilot_id"), _iso(agora_utc - timedelta(hours=1))))["n"]
    if n >= POR_HORA:
        raise Demais("Too many reviews in the last hour. Try again later.")
    bate = mesmo_nome(nome, nome_cadastro)
    linha = dict(created_at=_iso(agora_utc), expires_at=_iso(agora_utc + timedelta(minutes=VALIDADE_MIN)), flow=fluxo,
                 account_id=ids.get("account_id"), invite_id=ids.get("invite_id"), pilot_id=ids.get("pilot_id"),
                 client_id=ids.get("client_id"), kind=ids["kind"], template_version_id=ids.get("template_version_id"),
                 template_sha256=template_sha, content_sha256=conteudo_sha, typed_name=nome, name_on_file=nome_cadastro,
                 name_matches=1 if bate else 0, signer_relationship=parentesco, ip=ip, user_agent=(user_agent or "")[:300] or None)

    def gravar():
        rid = inserir(con, "waiver_reviews", **linha)
        tw.registrar(con, "reviewed", fluxo, ip=ip, user_agent=user_agent, detail={
            "review_id": rid, "typed_name": nome, "name_on_file": nome_cadastro, "name_matches": bate,
            "signer_relationship": parentesco, "content_sha256": conteudo_sha, **(detail or {})}, **ids)
        return rid

    if con.in_transaction:
        rid = gravar()
    else:
        with transacao(con, imediata=True):
            rid = gravar()
    return {**linha, "id": rid, "name_matches": bate}


def exigir(con, review_id, fluxo, ids, template_sha, conteudo_sha, nome_confirmado):
    """A revisão que este clique final confirma, conferida. Senão `ErroWaiver` (400), com o que fazer."""
    from command_center.providers.waiver_nativa import ErroWaiver
    try:
        rid = int(review_id)
    except (TypeError, ValueError):
        raise ErroWaiver("Review the summary before signing.")
    r = um(con, "SELECT * FROM waiver_reviews WHERE id=?", (rid,))
    campo, valor = _escopo(fluxo, ids)
    if not r or r["flow"] != fluxo or r[campo] != valor or r["pilot_id"] != ids.get("pilot_id") or r["kind"] != ids["kind"]:
        raise ErroWaiver("Review the summary before signing.")
    if r["used_at"]:
        raise ErroWaiver("This review was already used. Review the summary again before signing.")
    if r["expires_at"] < _iso(datetime.now(timezone.utc)):
        raise ErroWaiver("The review expired. Review the summary again before signing.")
    if r["template_sha256"] != template_sha or r["content_sha256"] != conteudo_sha:
        raise ErroWaiver("Something changed after the review. Review the summary again before signing.")
    if not r["name_matches"] and not nome_confirmado:
        raise ErroWaiver(f"The name you typed ({r['typed_name']}) is different from the name on file ({r['name_on_file']}). "
                         "Confirm that you want to sign with the name you typed.")
    return r


def marcar_usada(con, rid):
    """Dentro da transação da assinatura: a mesma revisão não confirma duas assinaturas."""
    from command_center.providers.waiver_nativa import ErroWaiver
    cur = con.execute("UPDATE waiver_reviews SET used_at=? WHERE id=? AND used_at IS NULL",
                      (_iso(datetime.now(timezone.utc)), rid))
    if cur.rowcount != 1:
        raise ErroWaiver("This review was already used. Review the summary again before signing.")


def na_trilha(r, confirmado_em, nome_confirmado):
    """O que a trilha da waiver (e o certificado) guarda da revisão: as duas horas e os dois nomes."""
    return {"review_id": r["id"], "reviewed_at": r["created_at"], "confirmed_at": confirmado_em,
            "typed_name": r["typed_name"], "name_on_file": r["name_on_file"], "name_matches": bool(r["name_matches"]),
            "name_mismatch_confirmed": bool(nome_confirmado) and not r["name_matches"],
            "legal_effect_statement": EFEITO_LEGAL, "final_button": BOTAO}
