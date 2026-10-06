"""Código de 6 dígitos por e-mail (#108): confirmar o e-mail da conta e assinar a waiver.

*Ruiz v. Moss Bros.* (Cal. 2014) derrubou uma assinatura eletrônica porque a empresa não mostrou
por que só aquela pessoa podia ter assinado; a Flórida aceita como prova "the efficacy of any
security procedure" (Fla. Stat. §668.50(9)). Um código que chega na caixa da pessoa, na hora, é
esse procedimento.

- O código nunca é guardado: só o SHA-256 dele, com a conta e a finalidade.
- Vale 15 minutos, aceita 5 tentativas e só o mais recente vale.
- No máximo 1 envio por minuto e 5 por hora, por conta e finalidade.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from command_center.db import inserir, um

FINALIDADES = {"email_verify", "waiver_sign"}
VALIDADE_MIN = 15
TENTATIVAS = 5
POR_HORA = 5


class ErroCodigo(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


def _agora():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _hash(conta_id, finalidade, codigo):
    return hashlib.sha256(f"{conta_id}:{finalidade}:{codigo}".encode()).hexdigest()


def mascarar(email):
    nome, _, dom = (email or "").partition("@")
    return (nome[:1] + "•" * max(1, len(nome) - 1) + "@" + dom) if dom else email


def emitir(con, conta_id, finalidade, email, enviar):
    """Gera e manda um código. `enviar(para, assunto, texto)` devolve o id da mensagem."""
    if finalidade not in FINALIDADES:
        raise ValueError(finalidade)
    agora = _agora()
    ult = um(con, """SELECT created_at FROM portal_codes WHERE account_id=? AND purpose=?
                     ORDER BY id DESC LIMIT 1""", (conta_id, finalidade))
    if ult and ult["created_at"] > _iso(agora - timedelta(minutes=1)):
        raise ErroCodigo("We just sent you a code. Wait a minute before asking for another one.")
    n = um(con, "SELECT COUNT(*) AS n FROM portal_codes WHERE account_id=? AND purpose=? AND created_at > ?",
           (conta_id, finalidade, _iso(agora - timedelta(hours=1))))["n"]
    if n >= POR_HORA:
        raise ErroCodigo("Too many codes in the last hour. Try again later.")
    codigo = f"{secrets.randbelow(10**6):06d}"
    para_que = "confirm your email" if finalidade == "email_verify" else "sign the waiver"
    texto = (f"Your URACE code to {para_que} is: {codigo}\n\n"
             f"It expires in {VALIDADE_MIN} minutes. If you did not ask for it, ignore this email: "
             "nobody can use it without access to your account.\n\nURACE.US · Orlando, FL")
    mid = enviar(email, f"Your URACE code: {codigo}", texto)
    inserir(con, "portal_codes", account_id=conta_id, purpose=finalidade, code_hash=_hash(conta_id, finalidade, codigo),
            sent_to=email, message_id=mid, created_at=_iso(agora), expires_at=_iso(agora + timedelta(minutes=VALIDADE_MIN)))
    return {"sent_to": mascarar(email), "expires_in_minutes": VALIDADE_MIN}


def conferir(con, conta_id, finalidade, codigo):
    """Confere o código mais recente. Devolve a linha (com as horas de envio e de uso) ou levanta."""
    c = um(con, """SELECT * FROM portal_codes WHERE account_id=? AND purpose=? ORDER BY id DESC LIMIT 1""",
           (conta_id, finalidade))
    agora = _iso(_agora())
    if not c or c["used_at"] or c["expires_at"] < agora:
        raise ErroCodigo("This code has expired. Ask for a new one.")
    if c["attempts"] >= TENTATIVAS:
        raise ErroCodigo("Too many wrong tries. Ask for a new code.")
    limpo = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    if not secrets.compare_digest(_hash(conta_id, finalidade, limpo), c["code_hash"]):
        con.execute("UPDATE portal_codes SET attempts=attempts+1 WHERE id=?", (c["id"],))
        con.commit()                                          # a tentativa errada conta mesmo se o pedido falhar
        raise ErroCodigo("That code is not right. Check the email and try again.")
    con.execute("UPDATE portal_codes SET used_at=? WHERE id=?", (agora, c["id"]))
    return {**dict(c), "used_at": agora}
