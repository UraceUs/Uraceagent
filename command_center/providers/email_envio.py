"""Envio de e-mail pela API do Gmail, da caixa da URACE (#108).

Usado pelo código de verificação da área do cliente: confirmar o e-mail da conta e o código de
uma vez na hora de assinar a waiver. A caixa é a de `CC_EMAIL_REMETENTE` (padrão `support`,
a recomendada; decisão do dono em aberto), com o token que o VPS já tem — o escopo
`gmail.modify` cobre o envio.

Teste e end-to-end nunca mandam e-mail de verdade: com `CC_EMAIL_FAKE=<arquivo>` a mensagem vai
para esse arquivo (uma linha JSON por e-mail) e nada sai da máquina.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from email.message import EmailMessage

CAIXAS = {"support": "support@urace.us", "urace": "urace@urace.us"}


def remetente():
    conta = (os.environ.get("CC_EMAIL_REMETENTE") or "support").strip().lower()
    return conta if conta in CAIXAS else "support"


class ErroEnvio(RuntimeError):
    """O e-mail não saiu (sem token, sem rede, Gmail recusou). A mensagem não carrega segredo."""


def enviar(para, assunto, texto):
    """Manda um e-mail de texto. Devolve o id da mensagem no Gmail (ou do arquivo, no teste)."""
    conta = remetente()
    msg = EmailMessage()
    msg["From"] = f"URACE.US <{CAIXAS[conta]}>"
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(texto)
    falso = os.environ.get("CC_EMAIL_FAKE")
    if falso:
        with open(falso, "a", encoding="utf-8") as f:
            f.write(json.dumps({"from": CAIXAS[conta], "to": para, "subject": assunto, "text": texto}) + "\n")
        return f"fake-{os.path.getsize(falso)}"
    try:
        from adminai import google_auth
        tok = google_auth.access_token(conta)
    except Exception as e:                                        # noqa: BLE001 — sem token no VPS
        raise ErroEnvio(f"sem token do Google para {CAIXAS[conta]}: {str(e)[:160]}")
    corpo = json.dumps({"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}).encode()
    req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", data=corpo, method="POST")
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}").get("id")
    except urllib.error.HTTPError as e:
        raise ErroEnvio(f"Gmail recusou o envio: HTTP {e.code}")
    except urllib.error.URLError as e:
        raise ErroEnvio(f"Gmail sem conexão: {e.reason}")
