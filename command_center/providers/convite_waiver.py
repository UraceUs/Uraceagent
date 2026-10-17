"""Convite da waiver por e-mail (#135).

Dono, 14/10: *"vai ser por e-mail para o adulto ou para o responsável assinar aquela waiver. Tanto
para adulto quanto para responsável, o e-mail que tiver no card vai receber isso."*

- **Para quem**: o e-mail do card. Piloto com 18 anos ou mais (pela data de nascimento do piloto)
  assina a própria waiver (`adult`, #104); menor, o responsável assina por ele (`parental`, #105:
  pai ou mãe, com a declaração). A tela do painel mostra nome e e-mail antes e pede confirmação.
- **O link** é pessoal, de uso único e vence em `VALIDADE_HORAS`. É `segredo.selo`: só o SHA-256
  do segredo fica no banco, e o selo é um HMAC (chave própria, fora do repositório) sobre o card,
  o modelo, o e-mail, o nascimento do piloto e a validade. Abre a assinatura nativa (#85) sem
  conta e sem login, já presa àquele card e piloto: nenhum campo da tela escolhe o card. Se o card
  mudar (outro e-mail, outra data de nascimento, união com outro card, piloto fez 18), o link para
  de valer e a equipe reenvia.
- **Quem assina tem a caixa** (#108): além do link, um código de 6 dígitos chega no mesmo e-mail na
  hora de assinar; os dois vão para a trilha e para o certificado.
- **Reenviar** manda um link novo e aposenta os anteriores ainda em aberto. Cada passo (enviado,
  aberto, documento entregue, código, assinado, recusado) fica na auditoria do card.
- **Política**: pela pessoa no painel, o clique dela (com a confirmação). Pela IA,
  `painel_waiver_convite` é REQUIRES_APPROVAL: sai para o cliente, espera o aprovar.

Nenhum e-mail sai em teste: `email_envio` com `CC_EMAIL_FAKE` grava num arquivo.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from command_center.db import agora, atualizar, auditar, inserir, todos, um, waiver_anulada
from command_center.providers import codigos, portal, trilha_waiver as tw, waiver_nativa as wn

VALIDADE_HORAS = 72          # a issue (#135, dono 06/10): "um link de uso único, que vale 72 h"
INTERVALO_ENVIO_S = 60       # dois cliques seguidos não mandam dois e-mails
CODIGO_MIN = codigos.VALIDADE_MIN
CODIGO_TENTATIVAS = codigos.TENTATIVAS
CODIGO_POR_HORA = codigos.POR_HORA
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


class ErroConvite(ValueError):
    """Para a equipe, em português: por que o convite não sai deste card."""


class Cedo(ErroConvite):
    """Um convite acabou de sair para este card."""


class EnvioFalhou(ErroConvite):
    """O e-mail não saiu (Gmail)."""


class LinkInvalido(wn.ErroWaiver):
    """Para o cliente, em inglês: o link não vale (inválido, usado, trocado, vencido, card mudou)."""

    def __init__(self, msg, estado, convite=None):
        super().__init__(msg)
        self.estado = estado
        self.convite = convite


def _agora():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


# ------------------------------------------------------------------ o selo do link
def _chave():
    """A chave do HMAC: 32 bytes aleatórios, criados na primeira vez, só legíveis pelo serviço.
    Fica na pasta das waivers (~/.urace/waivers), nunca no repositório. Perdida, os links em
    aberto deixam de valer (a equipe reenvia); nada assinado depende dela."""
    caminho = os.path.join(wn.pasta(), "convite.key")
    try:
        with open(caminho, "rb") as f:
            k = f.read()
    except FileNotFoundError:
        k = secrets.token_bytes(32)
        try:
            fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:                       # outro processo criou agora: vale a dele
            with open(caminho, "rb") as f:
                k = f.read()
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(k)
    if len(k) < 32:
        raise RuntimeError("chave do convite da waiver corrompida")
    return k


def _selo(segredo, inv):
    msg = "|".join(str(x) for x in (segredo, inv["client_id"], inv["kind"], (inv["email"] or "").lower(),
                                     inv["driver_birth_date"], inv["expires_at"]))
    d = hmac.new(_chave(), msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(d).decode().rstrip("=")[:32]


# ------------------------------------------------------------------ para quem vai
def _mesma_pessoa(a, b):
    return re.sub(r"\s+", " ", (a or "").strip()).casefold() == re.sub(r"\s+", " ", (b or "").strip()).casefold()


def _do_card(con, client_id):
    """Piloto, nascimento, e-mail e modelo, como o card diz agora. Nada é escolhido pela tela."""
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    if not c:
        return None
    pil = um(con, "SELECT id, name, birth_date FROM portal_pilots WHERE client_id=? AND active=1", (client_id,))
    piloto = (c.get("pilot_name") or "").strip() or (pil["name"] if pil else None) or c["name"]
    nasc = (c.get("pilot_dob") or "").strip()[:10] or (pil["birth_date"] if pil and pil["birth_date"] else None)
    try:
        nasc_d = date.fromisoformat(nasc) if nasc else None
    except ValueError:
        nasc_d = None
    idade = portal.idade(nasc_d) if nasc_d else None
    tipo = None if idade is None else ("parental" if idade < portal.MAIORIDADE else "adult")
    return {"card": c, "pilot_id": pil["id"] if pil else None, "driver_name": piloto,
            "driver_birth_date": nasc_d.isoformat() if nasc_d else None, "age": idade, "kind": tipo,
            "email": (c.get("email") or "").strip().lower() or None, "responsible": c["name"],
            "signer_name": piloto if tipo == "adult" else c["name"]}


def _vigente_do_card(con, client_id, tipo):
    return um(con, f"""SELECT id, expires_at FROM waivers WHERE client_id=? AND source='urace' AND status='completed'
                       AND template=? AND COALESCE(hidden,0)=0 AND NOT {waiver_anulada()} AND expires_at >= ?
                       ORDER BY completed_at DESC LIMIT 1""",
              (client_id, tipo, portal.hoje().isoformat()))


def destino(con, client_id):
    """O que o painel mostra antes do clique: para quem vai, qual waiver e, se não pode, por quê."""
    d = _do_card(con, client_id)
    if d is None:
        raise LookupError("cliente")
    c = d.pop("card")
    motivo = None
    if not wn.ligada(con):
        motivo = ("A assinatura da waiver no próprio sistema está desligada (Site › Waiver). "
                  "O convite abre essa assinatura: ligue-a antes.")
    elif not d["email"]:
        motivo = "O card não tem e-mail. Ponha no card o e-mail do piloto adulto ou do responsável para mandar o convite."
    elif not _EMAIL.match(d["email"]):
        motivo = f"O e-mail do card ({d['email']}) não parece válido. Corrija no card."
    elif d["email"].endswith("@urace.us"):
        motivo = "O e-mail do card é da URACE. Ponha o e-mail do cliente no card."
    elif not d["driver_birth_date"]:
        motivo = ("O card não tem a data de nascimento do piloto. Ela decide quem assina: o próprio piloto "
                  "(18 anos ou mais) ou o responsável (menor).")
    elif d["kind"] == "parental" and (not (c.get("pilot_name") or "").strip() or _mesma_pessoa(c["pilot_name"], c["name"])):
        motivo = ("O piloto é menor e o card não tem o nome do responsável (pai ou mãe), que é quem assina. "
                  "Ponha o piloto no campo Piloto e o responsável no nome do card.")
    v = _vigente_do_card(con, client_id, d["kind"]) if d["kind"] else None
    return {**d, "client_id": client_id, "enabled": wn.ligada(con), "can_send": motivo is None, "reason": motivo,
            "valid_hours": VALIDADE_HORAS, "valid_waiver_until": v["expires_at"] if v else None}


# ------------------------------------------------------------------ o e-mail
def _quando(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(portal.FUSO)
    return t.strftime("%b %-d, %Y at %-I:%M %p") + " (Orlando time)"


def assunto(inv):
    return ("Sign your URACE waiver" if inv["kind"] == "adult"
            else f"Sign the URACE waiver for {inv['driver_name']}")


def texto(inv, link):
    primeiro = (inv["signer_name"] or "").split()[0] if inv["signer_name"] else "there"
    if inv["kind"] == "adult":
        porque = ("Before you drive at URACE, please sign your Release and Waiver of Liability. Only you can sign it, "
                  "because it is about your own rights.")
    else:
        porque = (f"Before {inv['driver_name']} drives at URACE, a parent needs to sign the Parental Consent, Release "
                  f"and Waiver of Liability for them. As {inv['driver_name']}'s parent, you can sign it online.")
    return (f"Hi {primeiro},\n\n{porque}\n\nOpen your personal link to read and sign it (no account needed):\n\n{link}\n\n"
            f"The link is only for you: it works once and expires in {VALIDADE_HORAS} hours, on {_quando(inv['expires_at'])}. "
            "When you sign, we also send a 6-digit code to this email to confirm it is you.\n\n"
            "If you were not expecting this email, you can ignore it.\n\nURACE.US · Orlando, FL")


def _link(token, base=None):
    from command_center import enderecos
    return f"{(base or enderecos.cliente()).rstrip('/')}/ops/portal/invite/{token}"


def enviar(con, client_id, por, user_id=None, email_confirmado=None, enviar_email=None, base=None, ip=None):
    """Manda o convite para o e-mail do card. `email_confirmado` é o que a pessoa viu na
    confirmação: se o card mudou no meio, não manda. Reenviar aposenta os convites em aberto."""
    from command_center.providers import email_envio
    d = destino(con, client_id)
    if not d["can_send"]:
        raise ErroConvite(d["reason"])
    if email_confirmado is not None and (email_confirmado or "").strip().lower() != d["email"]:
        raise ErroConvite("O e-mail do card mudou depois que a tela abriu. Confira o destino e mande de novo.")
    agora_utc = _agora()
    ult = um(con, "SELECT created_at FROM waiver_invites WHERE client_id=? ORDER BY id DESC LIMIT 1", (client_id,))
    if ult and ult["created_at"] > _iso(agora_utc - timedelta(seconds=INTERVALO_ENVIO_S)):
        raise Cedo("Um convite acabou de sair para este card. Espere um minuto antes de reenviar.")
    anteriores = [r["id"] for r in todos(con, """SELECT id FROM waiver_invites WHERE client_id=? AND used_at IS NULL
                                                 AND revoked_at IS NULL""", (client_id,))]
    segredo = secrets.token_urlsafe(32)
    inv = {"client_id": client_id, "kind": d["kind"], "signer_name": d["signer_name"], "email": d["email"],
           "driver_name": d["driver_name"], "driver_birth_date": d["driver_birth_date"], "token_hash": _sha(segredo),
           "created_at": _iso(agora_utc), "created_by": por, "user_id": user_id,
           "expires_at": _iso(agora_utc + timedelta(hours=VALIDADE_HORAS))}
    iid = inserir(con, "waiver_invites", **inv)
    inv["id"] = iid
    token = f"{segredo}.{_selo(segredo, inv)}"
    try:
        mid = (enviar_email or email_envio.enviar)(inv["email"], assunto(inv), texto(inv, _link(token, base)))
    except email_envio.ErroEnvio as e:
        atualizar(con, "waiver_invites", iid, revoked_at=agora(), revoked_reason="e-mail não saiu")
        auditar(con, "waiver.invite.send_failed", por, user_id=user_id, entity_type="client", entity_id=client_id,
                detail={"invite": iid, "erro": str(e)[:160]}, ip=ip)
        raise EnvioFalhou("O e-mail não saiu agora (Gmail). Nada foi enviado; tente de novo em alguns minutos.")
    atualizar(con, "waiver_invites", iid, sent_at=agora(), message_id=mid)
    if anteriores:
        con.execute(f"""UPDATE waiver_invites SET revoked_at=?, revoked_reason='reenviado'
                        WHERE id IN ({','.join('?' * len(anteriores))}) AND used_at IS NULL AND revoked_at IS NULL""",
                    (agora(), *anteriores))
    auditar(con, "waiver.invite.sent", por, user_id=user_id, entity_type="client", entity_id=client_id,
            detail={"invite": iid, "kind": inv["kind"], "to": inv["email"], "signer": inv["signer_name"],
                    "driver": inv["driver_name"], "expires_at": inv["expires_at"], "resend": bool(anteriores),
                    "replaced": anteriores}, ip=ip)
    m = wn.modelo(con, inv["kind"])
    tw.registrar(con, "invite_sent", "invite", ip=ip, detail={"to": codigos.mascarar(inv["email"]), "by": por,
                                                              "expires_at": inv["expires_at"], "resend": bool(anteriores)},
                 **_ids(inv, d.get("pilot_id"), m))
    return linha(con, iid)


def _ids(inv, pilot_id=None, m=None):
    """Os campos de escopo da trilha (#111) para um evento deste convite."""
    return dict(invite_id=inv["id"], client_id=inv["client_id"], pilot_id=pilot_id, kind=inv["kind"],
                template_version_id=m.get("version_id") if m else None)


# ------------------------------------------------------------------ situação
ROTULO = {"sent": "enviado", "opened": "aberto", "signed": "assinado", "expired": "expirado",
          "replaced": "substituído", "failed": "não saiu"}


def estado(inv, agora_iso=None):
    agora_iso = agora_iso or _iso(_agora())
    if inv["used_at"]:
        return "signed"
    if inv["revoked_at"]:
        return "replaced" if inv["revoked_reason"] == "reenviado" else "failed"
    if inv["expires_at"] < agora_iso:
        return "expired"
    return "opened" if inv["opened_at"] else "sent"


_CAMPOS = """i.id, i.client_id, i.kind, i.signer_name, i.email, i.driver_name, i.driver_birth_date, i.created_at, i.created_by,
             i.expires_at, i.sent_at, i.opened_at, i.used_at, i.waiver_id, i.revoked_at, i.revoked_reason,
             u.name AS created_by_name"""


def linha(con, iid):
    inv = um(con, f"SELECT {_CAMPOS} FROM waiver_invites i LEFT JOIN users u ON u.id=i.user_id WHERE i.id=?", (iid,))
    return {**inv, "status": estado(inv)} if inv else None


def listar(con, client_id, limite=20):
    agora_iso = _iso(_agora())
    return [{**r, "status": estado(r, agora_iso)} for r in todos(
        con, f"""SELECT {_CAMPOS} FROM waiver_invites i LEFT JOIN users u ON u.id=i.user_id
                 WHERE i.client_id=? ORDER BY i.id DESC LIMIT ?""", (client_id, limite))]


# ------------------------------------------------------------------ o link, do lado do cliente
_INVALIDO = "This link is not valid. Ask URACE to send you a new one."


def achar(con, token):
    """O convite deste token, com o selo conferido (ou None). Não olha validade nem uso."""
    token = (token or "").strip()
    segredo, _, selo = token.partition(".")
    if not segredo or not selo or len(token) > 200:
        return None
    inv = um(con, "SELECT * FROM waiver_invites WHERE token_hash=?", (_sha(segredo),))
    if not inv or not hmac.compare_digest(selo, _selo(segredo, inv)):
        return None
    return inv


def conferir(con, token):
    """O convite, se o link ainda vale para assinar. Senão `LinkInvalido` (com o estado)."""
    inv = achar(con, token)
    if not inv:
        raise LinkInvalido(_INVALIDO, "invalid")
    if inv["used_at"]:
        raise LinkInvalido("This link was already used: the waiver is signed.", "used", inv)
    if inv["revoked_at"]:
        raise LinkInvalido("This link was replaced by a newer one. Use the latest email from URACE.", "replaced", inv)
    if inv["expires_at"] < _iso(_agora()):
        raise LinkInvalido("This link has expired. Ask URACE to send you a new one.", "expired", inv)
    d = _do_card(con, inv["client_id"])
    if (not d or d["email"] != (inv["email"] or "").lower() or d["driver_birth_date"] != inv["driver_birth_date"]
            or d["kind"] != inv["kind"]):
        raise LinkInvalido("This link is no longer valid because the details on file changed. Ask URACE to send "
                           "you a new one.", "changed", inv)
    if not wn.ligada(con):
        raise LinkInvalido("Online waiver signing is not available right now. Please contact URACE.", "off", inv)
    return inv


def ver(con, token, ip=None, aparelho=None):
    """O que a tela do convite mostra. A primeira abertura fica registrada; cada abertura vai para a trilha (#111)."""
    inv = conferir(con, token)
    m = wn.modelo(con, inv["kind"])
    if not m:
        raise LinkInvalido("Online waiver signing is not available right now. Please contact URACE.", "off", inv)
    if not inv["opened_at"]:
        con.execute("UPDATE waiver_invites SET opened_at=? WHERE id=? AND opened_at IS NULL", (agora(), inv["id"]))
        auditar(con, "waiver.invite.opened", f"invite:{inv['id']}", entity_type="client", entity_id=inv["client_id"],
                detail={"invite": inv["id"]}, ip=ip)
    tw.abriu_pelo_link(con, ip=ip, user_agent=aparelho, detail={"first": not inv["opened_at"]}, **_ids(inv, _piloto(con, inv), m))
    return {"kind": inv["kind"], "driver": inv["driver_name"], "signer_name": inv["signer_name"],
            "email": codigos.mascarar(inv["email"]), "expires_at": inv["expires_at"],
            "model": {"name": m["name"], "pages": m["pages"], "text": m["text"] or "",
                      "declaration": wn.DECLARACAO if inv["kind"] == "parental" else None}}


def pdf_do_modelo(con, token, ip=None, aparelho=None):
    """O PDF do modelo, e o registro da entrega (#107) — o assinar exige este registro."""
    inv = conferir(con, token)
    m = wn.modelo(con, inv["kind"])
    if not m:
        raise LinkInvalido("Online waiver signing is not available right now. Please contact URACE.", "off", inv)
    with open(m["pdf_path"], "rb") as f:
        pdf = f.read()
    auditar(con, "waiver.invite.document_view", f"invite:{inv['id']}", entity_type="waiver_invite", entity_id=inv["id"],
            detail={"kind": inv["kind"], "sha256": m["sha256"]}, ip=ip)
    tw.entregou_o_pdf(con, "invite", ip=ip, user_agent=aparelho, detail={"sha256": m["sha256"]},
                      **_ids(inv, _piloto(con, inv), m))
    return pdf


def _piloto(con, inv):
    d = _do_card(con, inv["client_id"])
    return d["pilot_id"] if d else None


def evento_da_tela(con, token, evento, modo=None, paginas=None, ip=None, aparelho=None):
    """#111: o que só a tela do convite sabe (abriu, leu todas as páginas), com lista fechada e limite."""
    inv = conferir(con, token)
    detalhe = None
    if evento == "all_pages_viewed":
        if modo not in wn.MODOS_LEITURA:
            raise ValueError("modo de leitura inválido")
        detalhe = {"mode": modo, "pages": paginas}
    return tw.da_tela(con, evento, "invite", ip=ip, user_agent=aparelho, detail=detalhe,
                      **_ids(inv, _piloto(con, inv), wn.modelo(con, inv["kind"])))


def emitir_codigo(con, token, enviar_email=None, ip=None, aparelho=None):
    """O código de 6 dígitos (#108) no e-mail do convite. 1 por minuto, 5 por hora."""
    from command_center.providers import email_envio
    inv = conferir(con, token)
    agora_utc = _agora()
    ult = um(con, "SELECT created_at FROM waiver_invite_codes WHERE invite_id=? ORDER BY id DESC LIMIT 1", (inv["id"],))
    if ult and ult["created_at"] > _iso(agora_utc - timedelta(minutes=1)):
        raise codigos.ErroCodigo("We just sent you a code. Wait a minute before asking for another one.")
    n = um(con, "SELECT COUNT(*) AS n FROM waiver_invite_codes WHERE invite_id=? AND created_at > ?",
           (inv["id"], _iso(agora_utc - timedelta(hours=1))))["n"]
    if n >= CODIGO_POR_HORA:
        raise codigos.ErroCodigo("Too many codes in the last hour. Try again later.")
    codigo = f"{secrets.randbelow(10**6):06d}"
    corpo = (f"Your URACE code to sign the waiver is: {codigo}\n\nIt expires in {CODIGO_MIN} minutes. If you did not ask "
             "for it, ignore this email: nobody can use it without the link we sent you.\n\nURACE.US · Orlando, FL")
    mid = (enviar_email or email_envio.enviar)(inv["email"], f"Your URACE code: {codigo}", corpo)
    inserir(con, "waiver_invite_codes", invite_id=inv["id"], code_hash=_sha(f"{inv['id']}:{codigo}"), sent_to=inv["email"],
            message_id=mid, created_at=_iso(agora_utc), expires_at=_iso(agora_utc + timedelta(minutes=CODIGO_MIN)))
    auditar(con, "waiver.invite.code_sent", f"invite:{inv['id']}", entity_type="client", entity_id=inv["client_id"],
            detail={"invite": inv["id"]}, ip=ip)
    tw.registrar(con, "code_sent", "invite", ip=ip, user_agent=aparelho, detail={"sent_to": codigos.mascarar(inv["email"])},
                 **_ids(inv, _piloto(con, inv), wn.modelo(con, inv["kind"])))
    return {"sent_to": codigos.mascarar(inv["email"]), "expires_in_minutes": CODIGO_MIN}


def _conferir_codigo(con, inv, codigo):
    c = um(con, "SELECT * FROM waiver_invite_codes WHERE invite_id=? ORDER BY id DESC LIMIT 1", (inv["id"],))
    agora_iso = _iso(_agora())
    if not c or c["used_at"] or c["expires_at"] < agora_iso:
        raise wn.ErroWaiver("Ask for the signing code: we send it to your email.")
    if c["attempts"] >= CODIGO_TENTATIVAS:
        raise wn.ErroWaiver("Too many wrong tries. Ask for a new code.")
    limpo = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    if not secrets.compare_digest(_sha(f"{inv['id']}:{limpo}"), c["code_hash"]):
        con.execute("UPDATE waiver_invite_codes SET attempts=attempts+1 WHERE id=?", (c["id"],))
        raise wn.ErroWaiver("That code is not right. Check the email and try again.")
    con.execute("UPDATE waiver_invite_codes SET used_at=? WHERE id=?", (agora_iso, c["id"]))
    return {**c, "used_at": agora_iso}


def _preparar(con, token, dados):
    """O que a revisão e o clique final conferem igual (#112: tudo, menos o código do e-mail)."""
    from command_center.providers import revisao_waiver as rv
    inv = conferir(con, token)
    if not dados.get("read_and_agree") or not dados.get("consent_esign"):
        raise wn.ErroWaiver("Check both boxes to sign: that you read and agree, and that you agree to sign electronically.")
    if not dados.get("english_understood"):
        raise wn.ErroWaiver("Confirm that you read and understand English, or that you had the document translated.")
    tipo = inv["kind"]
    parentesco, declaracao = wn._parentesco(dados, inv["driver_name"]) if tipo == "parental" else (None, None)
    m = wn.modelo(con, tipo)
    if not m:
        raise wn.ErroWaiver("Online waiver signing is not available right now. Please contact URACE.")
    if _vigente_do_card(con, inv["client_id"], tipo):
        raise wn.ErroWaiver("This driver already has a signed waiver that is still valid.")
    nome = wn._nome(dados.get("typed_name"))
    png = wn._png(dados.get("signature"))
    with open(m["pdf_path"], "rb") as f:
        base = f.read()
    if wn._sha(base) != m["sha256"]:
        raise wn.ErroWaiver("The waiver document could not be verified. Please contact us.")
    wn._exigir_aviso(tipo, base)                           # #116: antes de gastar o código do e-mail
    entregue, lido, modo = wn._leitura(con, inv["id"], tipo, dados, _agora(), entidade="waiver_invite",
                                       evento="waiver.invite.document_view")
    d = _do_card(con, inv["client_id"])
    pid = d["pilot_id"] if d else None
    return {"inv": inv, "tipo": tipo, "parentesco": parentesco, "declaracao": declaracao, "m": m, "nome": nome, "png": png,
            "base": base, "entregue": entregue, "lido": lido, "modo": modo, "pilot_id": pid, "ids": _ids(inv, pid, m),
            "conteudo": rv.conteudo(dados, nome, wn._sha(png), pid, tipo, m["sha256"])}


def revisar(con, token, dados, ip=None, aparelho=None):
    """#112, passo 1 pelo convite: confere tudo menos o código e devolve o resumo; a revisão vai para a trilha."""
    from command_center.providers import revisao_waiver as rv
    x = _preparar(con, token, dados)
    inv = x["inv"]
    r = rv.criar(con, "invite", x["ids"], x["m"]["sha256"], x["conteudo"], x["nome"], inv["signer_name"], x["parentesco"],
                 ip=ip, user_agent=aparelho, detail={"read_and_agree": True, "consent_esign": True, "language_ack": True,
                                                     "guardian_declaration": bool(x["declaracao"]),
                                                     "signature_png_sha256": wn._sha(x["png"])})
    return wn.resumo(r, x["m"], x["tipo"], inv["driver_name"], inv["driver_birth_date"], inv["signer_name"], x["parentesco"],
                     x["declaracao"], x["png"])


def assinar(con, token, dados, ip=None, aparelho=None):
    """Assina pelo convite. O card, o piloto, o modelo e o e-mail vêm do convite, nunca da tela.
    #112: só com a revisão (`review_id`) deste convite, válida, nunca usada e com o mesmo conteúdo.
    Devolve (waiver, convite)."""
    from command_center.providers import revisao_waiver as rv
    x = _preparar(con, token, dados)
    inv, tipo, m, nome, png, ids = x["inv"], x["tipo"], x["m"], x["nome"], x["png"], x["ids"]
    rev = rv.exigir(con, dados.get("review_id"), "invite", ids, m["sha256"], x["conteudo"], dados.get("name_mismatch_confirmed"))
    cod = _conferir_codigo(con, inv, dados.get("sign_code"))
    tw.registrar(con, "code_verified", "invite", ip=ip, user_agent=aparelho,
                 detail={"sent_to": codigos.mascarar(cod["sent_to"]), "sent_at": cod["created_at"]}, **ids)
    agora_utc = _agora()                                  # a hora da assinatura vem depois do último passo da trilha
    ny = agora_utc.astimezone(portal.FUSO)
    nasc = date.fromisoformat(inv["driver_birth_date"])
    ate_d = wn.validade(tipo, nasc, ny.date())
    ate_motivo = ("the day before the minor turns 18" if tipo == "parental" and ate_d < ny.date() + timedelta(days=wn.VALIDADE_DIAS)
                  else "one year")
    revisao = rv.na_trilha(rev, agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), dados.get("name_mismatch_confirmed"))
    trilha = {
        "signature_id": str(uuid.uuid4()), "template": tipo, "template_name": m["name"], "template_sha256": m["sha256"],
        "template_pages": m["pages"], "account_id": None, "account_email": inv["email"], "email_label": "Email",
        "signer_name": inv["signer_name"], "typed_name": nome, "client_id": inv["client_id"],
        "driver_id": x["pilot_id"], "driver_name": inv["driver_name"],
        "driver_birth_date": inv["driver_birth_date"], "signer_relationship": x["parentesco"],
        "guardian_declaration": x["declaracao"],
        "signed_at_utc": agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "signed_at_local": ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ip": ip, "user_agent": (aparelho or "")[:300], "read_and_agree": True, "consent_esign": True,
        "language_ack": wn.IDIOMA, "governing_law": "Florida law; courts in Orange County, Florida",
        "document_delivered_at": x["entregue"], "document_all_pages_viewed_at": x["lido"],
        "reading_mode": x["modo"], "reading_requirement": wn.MODOS_LEITURA[x["modo"]],
        "authentication": (f"Personal one-time invitation link emailed by URACE to {inv['email']} at {inv['sent_at']} "
                           f"(valid until {inv['expires_at']}); one-time code sent to {cod['sent_to']} at {cod['created_at']}, "
                           f"confirmed {cod['used_at']}"),
        "invitation_id": inv["id"], "invitation_sent_to": inv["email"], "invitation_sent_at": inv["sent_at"],
        "invitation_opened_at": inv["opened_at"], "invitation_sent_by": inv["created_by"],
        "otp_sent_to": cod["sent_to"], "otp_sent_at": cod["created_at"], "otp_verified_at": cod["used_at"],
        "otp_message_id": cod["message_id"],
        "signature_png_sha256": wn._sha(png), "valid_until": ate_d.isoformat(), "valid_until_reason": ate_motivo,
        "review": revisao, "reviewed_at_utc": revisao["reviewed_at"], "confirmed_at_utc": revisao["confirmed_at"],
    }

    def marcar_usado(c2):
        cur = c2.execute("UPDATE waiver_invites SET used_at=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL",
                         (agora(), inv["id"]))
        if cur.rowcount != 1:
            raise LinkInvalido("This link was already used: the waiver is signed.", "used", inv)
        rv.marcar_usada(c2, rev["id"])

    w = wn.gravar(con, x["base"], m, trilha, png, client_id=inv["client_id"], pilot_id=x["pilot_id"],
                  signer_name=inv["signer_name"], signer_email=inv["email"],
                  link_reason=f"assinada pelo convite #{inv['id']}, enviado ao e-mail do card", link_by="human",
                  resumo=f"waiver de {inv['signer_name']} assinada pelo convite por e-mail ({inv['driver_name']})",
                  antes=marcar_usado, eventos={"fluxo": "invite", "cobrir": dict(invite_id=inv["id"]), "ids": ids,
                                               "ip": ip, "user_agent": aparelho, "detalhe": wn._no_signed(revisao)})
    con.execute("UPDATE waiver_invites SET waiver_id=? WHERE id=?", (w["id"], inv["id"]))
    auditar(con, "waiver.invite.signed", f"invite:{inv['id']}", entity_type="client", entity_id=inv["client_id"],
            detail={"invite": inv["id"], "waiver": w["id"], "kind": tipo, "sha256": w["doc_sha256"]}, ip=ip)
    return w, um(con, "SELECT * FROM waiver_invites WHERE id=?", (inv["id"],))


def pdf_assinado(con, token, ip=None, aparelho=None):
    """O PDF assinado, pelo mesmo link, até a validade do convite (a cópia de quem assinou)."""
    inv = achar(con, token)
    if not inv or not inv["used_at"] or not inv["waiver_id"] or inv["expires_at"] < _iso(_agora()):
        return None
    w = um(con, "SELECT id, pdf_path FROM waivers WHERE id=? AND client_id=?", (inv["waiver_id"], inv["client_id"]))
    if not (w and w["pdf_path"] and os.path.isfile(w["pdf_path"])):
        return None
    tw.registrar(con, "downloaded", "invite", ip=ip, user_agent=aparelho, detail={"by": "signer"},
                 waiver_id=w["id"], **_ids(inv))
    return w
