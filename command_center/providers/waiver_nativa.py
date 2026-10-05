"""Waiver assinada no próprio sistema, sem DocuSign (#85) — fase 1, em paralelo.

Dono, 05/10: *"conseguimos replicar a plataforma do docusign nativa na vps?"* — por **custo**.

O que garante que a assinatura vale (ESIGN Act / UETA da Flórida) e se defende depois:

- **O texto legal é o mesmo**: o PDF de cada modelo vem do próprio DocuSign (importado pelo
  ADMIN), byte a byte, com o SHA-256 guardado. Ninguém redigita waiver.
- **Quem assina** é o responsável, logado na área do cliente (conta 18+ com senha). O modelo
  sai da idade do piloto: menor → parental; maior → adult.
- **Intenção e consentimento**: duas caixas obrigatórias ("li e concordo" e "concordo em
  assinar eletronicamente"), nome digitado e assinatura desenhada.
- **Prova**: data e hora (America/New_York e UTC), IP, aparelho, conta, os hashes do modelo
  e do PDF final, e uma página de assinatura e certificado anexada ao PDF original.
- **Validade de 1 ano**, como o e-mail do modelo no DocuSign promete ao cliente.
- Grava na MESMA tabela `waivers` (source='urace'): card do cliente, anexo no Asana e
  "waiver assinada" para a agenda tratam as duas iguais.

Nasce DESLIGADA (`booking_config.waiver_native = 0`): quem liga é o ADMIN, depois do sim do
advogado. Nada aqui toca o DocuSign além de LER os dois modelos na importação.
"""
import base64
import hashlib
import io
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import portal

# os mesmos dois modelos que a IA usa no DocuSign (adminai/mcp/docusign_mcp.py, TEMPLATES)
MODELOS = {
    "adult": "c51aede4-bba5-40df-9f14-24c340e2bd3e",      # Adult Waiver of Liability
    "parental": "6dbf2094-39da-4c21-95dd-feda7ac28022",   # Parental consent Waiver liability
}
NOME = {"adult": "Adult Release and Waiver of Liability",
        "parental": "Parental Consent, Release and Waiver of Liability (minor)"}
VALIDADE_DIAS = 365
MAX_ASSINATURA = 400_000            # bytes do PNG desenhado
MIN_TINTA = 0.004                   # fração mínima de pixels pintados: quadro em branco não é assinatura


class ErroWaiver(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


def pasta():
    p = os.environ.get("CC_WAIVERS_DIR") or os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "waivers")
    os.makedirs(os.path.join(p, "modelos"), mode=0o700, exist_ok=True)
    return p


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def ligada(con):
    c = um(con, "SELECT waiver_native FROM booking_config WHERE id=1")
    return bool(c and c["waiver_native"])


def ligar(con, ligado, por):
    if ligado and not all(modelo(con, k) for k in MODELOS):
        raise ValueError("importe os dois modelos do DocuSign antes de ligar")
    con.execute("INSERT OR IGNORE INTO booking_config (id) VALUES (1)")
    atualizar(con, "booking_config", 1, waiver_native=1 if ligado else 0, updated_by=por, updated_at=agora())
    return ligada(con)


# ------------------------------------------------------------------ modelos
def modelo(con, tipo):
    m = um(con, "SELECT * FROM waiver_templates WHERE kind=?", (tipo,))
    return m if m and m["pdf_path"] and os.path.isfile(m["pdf_path"]) else None


def modelos(con):
    return [{"kind": k, "templateId": MODELOS[k], "name": (m["name"] if m else None), "pages": (m["pages"] if m else None),
             "sha256": (m["sha256"] if m else None), "imported_at": (m["imported_at"] if m else None)}
            for k in MODELOS for m in [modelo(con, k)]]


def guardar_modelo(con, tipo, nome, pdf, por=None, origem="docusign"):
    """Guarda o PDF de um modelo como veio, com o hash e o texto (para ler na tela)."""
    from pypdf import PdfReader
    if tipo not in MODELOS:
        raise ValueError("modelo desconhecido")
    if not pdf.startswith(b"%PDF"):
        raise ValueError("o arquivo do modelo não é um PDF")
    leitor = PdfReader(io.BytesIO(pdf))
    texto = "\n\n".join((p.extract_text() or "").strip() for p in leitor.pages).strip()
    caminho = os.path.join(pasta(), "modelos", f"{tipo}-{_sha(pdf)[:12]}.pdf")
    with open(caminho, "wb") as f:
        f.write(pdf)
    os.chmod(caminho, 0o600)
    campos = dict(name=nome, pdf_path=caminho, sha256=_sha(pdf), pages=len(leitor.pages), text=texto,
                  source=origem, imported_at=agora(), imported_by=por)
    if um(con, "SELECT 1 AS x FROM waiver_templates WHERE kind=?", (tipo,)):
        con.execute(f"UPDATE waiver_templates SET {', '.join(k + '=?' for k in campos)} WHERE kind=?", (*campos.values(), tipo))
    else:
        con.execute(f"INSERT INTO waiver_templates (kind, {', '.join(campos)}) VALUES (?{', ?' * len(campos)})",
                    (tipo, *campos.values()))
    return dict(kind=tipo, **{k: v for k, v in campos.items() if k != "text"})


def importar_do_docusign(con, por=None):
    """LÊ os dois modelos no DocuSign (nome + PDF) e guarda aqui. Não altera nada lá."""
    from command_center.providers import modulo
    ds = modulo("docusign")
    saida = []
    for tipo, tid in MODELOS.items():
        info = ds.modelo_humano(tid)
        docs = info.get("documentos") or []
        if len(docs) != 1:
            raise ValueError(f"o modelo {info.get('nome') or tid} tem {len(docs)} documentos; esperava 1")
        pdf = ds.baixar_documento_do_modelo_humano(tid, docs[0]["documentId"])
        saida.append(guardar_modelo(con, tipo, info.get("nome") or NOME[tipo], pdf, por))
    return saida


# ------------------------------------------------------------------ situação por piloto
def tipo_para(piloto):
    if not piloto.get("birth_date"):
        raise ErroWaiver("Add the driver's date of birth first: it decides which waiver applies.")
    return "parental" if portal.idade(date.fromisoformat(piloto["birth_date"])) < portal.MAIORIDADE else "adult"


def vigente(con, pid):
    """A waiver nativa ainda válida deste piloto (ou None)."""
    return um(con, """SELECT * FROM waivers WHERE pilot_id=? AND source='urace' AND status='completed'
                      AND COALESCE(hidden,0)=0 AND expires_at >= ? ORDER BY completed_at DESC LIMIT 1""",
              (pid, portal.hoje().isoformat()))


def situacao(con, conta_id):
    """O que a área do cliente mostra: por piloto, qual waiver e se está assinada."""
    ativa = ligada(con)
    saida = []
    for p in portal.pilotos(con, conta_id):
        w = vigente(con, p["id"])
        try:
            tipo = tipo_para(p)
        except ErroWaiver:
            tipo = None
        saida.append({"driver_id": p["id"], "driver": p["name"], "kind": tipo,
                      "status": "signed" if w else "none", "waiver_id": w["id"] if w else None,
                      "signed_at": w["completed_at"] if w else None, "valid_until": w["expires_at"] if w else None})
    return {"enabled": ativa, "drivers": saida}


# ------------------------------------------------------------------ assinar
def _png(dataurl):
    m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$", dataurl or "")
    if not m:
        raise ErroWaiver("Draw your signature in the box.")
    png = base64.b64decode(m.group(1))
    if len(png) > MAX_ASSINATURA or not png.startswith(b"\x89PNG"):
        raise ErroWaiver("Draw your signature in the box.")
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("LA")
    lum, alfa = (bytes(b.tobytes()) for b in im.split())
    tinta = sum(1 for v, a in zip(lum, alfa) if a > 40 and v < 160) / max(1, im.width * im.height)
    if tinta < MIN_TINTA:
        raise ErroWaiver("Draw your signature in the box.")
    return png


def _nome(v):
    v = re.sub(r"\s+", " ", (v or "").strip())
    if len(v) < 3 or " " not in v:
        raise ErroWaiver("Type your full name, as your signature.")
    return v[:120]


def assinar(con, conta_id, pid, dados, ip=None, aparelho=None):
    """Assina a waiver do piloto `pid` pela conta `conta_id`. Devolve a linha de `waivers`."""
    if not ligada(con):
        raise ErroWaiver("Online waiver signing is not available yet. Our team will send you the waiver.")
    if not dados.get("read_and_agree") or not dados.get("consent_esign"):
        raise ErroWaiver("Check both boxes to sign: that you read and agree, and that you agree to sign electronically.")
    c = portal.conta(con, conta_id)
    p = next((x for x in portal.pilotos(con, conta_id) if x["id"] == pid), None)
    if not c or not p:
        raise LookupError("driver")
    tipo = tipo_para(p)
    m = modelo(con, tipo)
    if not m:
        raise ErroWaiver("Online waiver signing is not available yet. Our team will send you the waiver.")
    if vigente(con, pid):
        raise ErroWaiver("This driver already has a signed waiver that is still valid.")
    nome = _nome(dados.get("typed_name"))
    png = _png(dados.get("signature"))
    with open(m["pdf_path"], "rb") as f:
        base = f.read()
    if _sha(base) != m["sha256"]:                          # o modelo guardado mudou por fora: não assina
        raise ErroWaiver("The waiver document could not be verified. Please contact us.")
    agora_utc = datetime.now(timezone.utc)
    ny = agora_utc.astimezone(portal.FUSO)
    ate = (ny.date() + timedelta(days=VALIDADE_DIAS)).isoformat()
    sid = str(uuid.uuid4())
    trilha = {
        "signature_id": sid, "template": tipo, "template_name": m["name"], "template_sha256": m["sha256"],
        "template_pages": m["pages"], "account_id": conta_id, "account_email": c["email"], "signer_name": c["name"],
        "typed_name": nome, "driver_id": pid, "driver_name": p["name"], "driver_birth_date": p["birth_date"],
        "signed_at_utc": agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "signed_at_local": ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ip": ip, "user_agent": (aparelho or "")[:300], "read_and_agree": True, "consent_esign": True,
        "authentication": "URACE client account (email + password), signed in",
        "signature_png_sha256": _sha(png), "valid_until": ate,
    }
    final = _pdf_assinado(base, trilha, png)
    caminho = os.path.join(pasta(), f"urace-{sid}.pdf")
    with open(caminho, "wb") as f:
        f.write(final)
    os.chmod(caminho, 0o600)
    trilha["document_sha256"] = _sha(final)
    quando = agora()
    wid = inserir(con, "waivers", client_id=p.get("client_id"), signer_name=c["name"], signer_email=c["email"],
                  template=tipo, status="completed", sent_at=quando, completed_at=quando, expires_at=ate,
                  minor_name=p["name"] if tipo == "parental" else None, pdf_path=caminho,
                  subject=f"{m['name']} — {p['name']}"[:200], source="urace", pilot_id=pid,
                  doc_sha256=trilha["document_sha256"], audit=json.dumps(trilha, ensure_ascii=False),
                  link_reason="assinada na área do cliente" if p.get("client_id") else None,
                  link_by="sync" if p.get("client_id") else None, synced_at=quando)
    con.execute("INSERT INTO entity_links (entity_type, entity_id, system, external_id) VALUES ('waiver', ?, 'urace', ?)",
                (wid, sid))
    if p.get("client_id"):
        from command_center.api import motor
        motor.registrar_evento(con, "waiver.completed", "waiver", wid, p["client_id"],
                               f"waiver de {c['name']} assinada na área do cliente ({p['name']})")
    return um(con, "SELECT * FROM waivers WHERE id=?", (wid,))


def da_conta(con, conta_id, wid):
    """A waiver nativa `wid`, só se for de um piloto desta conta."""
    return um(con, """SELECT w.* FROM waivers w JOIN portal_pilots p ON p.id=w.pilot_id
                      WHERE w.id=? AND w.source='urace' AND p.account_id=?""", (wid, conta_id))


def listar(con, limit=50, offset=0):
    """As assinadas aqui, das mais novas para as mais velhas, paginadas."""
    total = um(con, "SELECT COUNT(*) AS n FROM waivers WHERE source='urace'")["n"]
    itens = todos(con, """SELECT id, client_id, pilot_id, signer_name, signer_email, minor_name, template, completed_at,
                                 expires_at, doc_sha256 FROM waivers WHERE source='urace'
                          ORDER BY completed_at DESC, id DESC LIMIT ? OFFSET ?""", (limit, offset))
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------------ o PDF
def _pdf_assinado(base, t, png):
    """O PDF do modelo, intacto, + uma página de assinatura e certificado no fim."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=letter)
    cv.setTitle(f"Signature and certificate — {t['template_name']}")
    larg, alt = letter
    x, y = 54, alt - 64

    def linha(txt, tam=10, fonte="Helvetica", passo=14):
        nonlocal y
        cv.setFont(fonte, tam)
        for pedaco in _quebra(txt, 95 if tam <= 10 else 70):
            cv.drawString(x, y, pedaco)
            y -= passo

    linha("Electronic signature and certificate of completion", 15, "Helvetica-Bold", 22)
    linha(f"Document: {t['template_name']} ({t['template_pages']} page(s) above this one)")
    linha(f"Signature ID: {t['signature_id']}")
    y -= 6
    rotulo = "Parent / legal guardian" if t["template"] == "parental" else "Participant"
    linha(f"{rotulo}: {t['signer_name']}   ·   Account: {t['account_email']}", 11, "Helvetica-Bold", 16)
    if t["template"] == "parental":
        linha(f"Minor participant: {t['driver_name']}   ·   Date of birth: {t['driver_birth_date']}")
    y -= 4
    linha("By signing below I confirm that I have read the document above, that I agree to its terms, and that I "
          "agree to sign it electronically. My electronic signature has the same effect as a handwritten signature.")
    y -= 8
    img = ImageReader(io.BytesIO(png))
    iw, ih = img.getSize()
    w = min(260.0, iw * 80.0 / max(ih, 1))
    cv.drawImage(img, x, y - 80, width=w, height=w * ih / max(iw, 1), mask="auto")
    y -= 90
    cv.line(x, y, x + 300, y)
    y -= 14
    linha(f"Signature of {t['signer_name']}   ·   Typed name: {t['typed_name']}")
    linha(f"Signed: {t['signed_at_local']}  ({t['signed_at_utc']} UTC)   ·   Valid until: {t['valid_until']}")
    y -= 10
    linha("Audit trail", 11, "Helvetica-Bold", 16)
    for k, v in (("Authentication", t["authentication"]), ("IP address", t["ip"] or "—"),
                 ("Device", t["user_agent"] or "—"), ("Agreed: read and agree", "yes"),
                 ("Agreed: sign electronically", "yes"), ("Document hash (SHA-256)", t["template_sha256"]),
                 ("Signature image hash (SHA-256)", t["signature_png_sha256"])):
        linha(f"{k}: {v}", 9, "Helvetica", 12)
    y -= 6
    linha("URACE.US INC · Orlando, FL · The SHA-256 of this complete file is kept in URACE's records to show it "
          "has not been altered.", 8, "Helvetica-Oblique", 11)
    cv.showPage()
    cv.save()

    out = PdfWriter()
    for pg in PdfReader(io.BytesIO(base)).pages:
        out.add_page(pg)
    for pg in PdfReader(io.BytesIO(buf.getvalue())).pages:
        out.add_page(pg)
    out.add_metadata({"/Title": f"{t['template_name']} — signed", "/Subject": f"Signature ID {t['signature_id']}"})
    final = io.BytesIO()
    out.write(final)
    return final.getvalue()


def _quebra(txt, n):
    palavras, linhas, atual = str(txt).split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > n and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return linhas + ([atual] if atual else [])
