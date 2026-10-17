"""Waiver assinada no próprio sistema, sem DocuSign (#85) — fase 1, em paralelo.

Dono, 05/10: *"conseguimos replicar a plataforma do docusign nativa na vps?"* — por **custo**.

O que garante que a assinatura vale (ESIGN Act / UETA da Flórida) e se defende depois:

- **O texto legal é o mesmo**: o PDF de cada modelo vem do próprio DocuSign (importado pelo
  ADMIN), byte a byte, com o SHA-256 guardado. Ninguém redigita waiver.
- **Quem assina** é o responsável, logado na área do cliente (conta 18+ com senha). O modelo
  sai da idade do piloto: menor → parental; maior → adult. A **adult só o próprio piloto**
  assina (#104): um adulto só renuncia aos próprios direitos (*Sanislo*, Fla. 2015), e a
  waiver que o titular assinasse por outro adulto não protegeria nada. Pelo **menor**, só
  **pai ou mãe** (#105): o §744.301(3) da Flórida só deixa o *natural guardian* renunciar
  pelo filho, e sem isso *Kirton v. Fields* (2008) anula a waiver. Quem assina diz o
  parentesco e declara a autoridade; os dois vão para a trilha e para o certificado. Tutor
  nomeado por juiz assina no balcão, com a ordem judicial.
- **Intenção e consentimento**: duas caixas obrigatórias ("li e concordo" e "concordo em
  assinar eletronicamente"), nome digitado e assinatura desenhada.
- **Revisar antes do clique final** (#112, Fla. Stat. §668.50(10)): o passo 1 confere tudo e mostra o
  resumo (documento, piloto, quem assina, parentesco, nome digitado, assinatura, validade); o passo 2,
  "I agree — sign the waiver", com a frase de efeito legal ao lado, só assina com essa revisão, sem nada
  mudado. Nome digitado diferente do da conta pede confirmação; a trilha guarda as duas horas e os dois nomes.
- **Quem assina é quem tem a caixa de e-mail** (#108): a conta precisa do e-mail confirmado por
  código, e na hora de assinar chega um código novo nessa caixa. Diante de um "não fui eu", é o
  que mostra que só aquela pessoa podia ter assinado (*Ruiz v. Moss Bros.*; Fla. Stat. §668.50(9)).
- **Leitura** (#107): a tela mostra o PDF de verdade (o aviso do §744.301(3) com a formatação
  do documento) e só libera as caixas depois de todas as páginas passarem pela tela. O servidor
  exige que o PDF tenha sido entregue a esta conta nas últimas 24 h (registro na auditoria) e
  guarda as duas horas: a da entrega (servidor) e a da leitura completa (relatada pela tela).
- **Prova**: data e hora (America/New_York e UTC), IP, aparelho, conta, os hashes do modelo
  e do PDF final, e uma página de assinatura e certificado anexada ao PDF original.
- **Validade de 1 ano**, como o e-mail do modelo no DocuSign promete ao cliente. A **parental
  vence na véspera dos 18 anos** se isso vier antes (#106): adulto, o piloto assina a própria.
- Grava na MESMA tabela `waivers` (source='urace'): card do cliente, anexo no Asana e
  "waiver assinada" para a agenda tratam as duas iguais.
- **Imutável e fora da lixeira** (#109): a linha assinada não muda nem sai do banco (trigger
  `waivers_nativa_imutavel`), o PDF fica só leitura (0400) e a trilha inteira vai também para o
  `audit_logs`. Para tirar de vigor, um gerente **anula com motivo** (`waiver_voids`): ela continua
  no card, na lista e no backup, marcada como anulada.
- **Versões do modelo** (#116): cada texto importado fica em `waiver_template_versions` (append-only,
  com o PDF só leitura); reimportar acrescenta a versão nova e a anterior continua consultável. A
  assinatura guarda o hash e o id da versão que valia. O modelo parental passa pela conferência do aviso
  do §744.301(3) (`aviso_744`), que só barra quando o texto aprovado pelo advogado está configurado.

Nasce DESLIGADA (`booking_config.waiver_native = 0`): quem liga é o ADMIN, depois do sim do
advogado. Nada aqui toca o DocuSign além de LER os dois modelos na importação.
"""
import base64
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone

from command_center.db import agora, atualizar, inserir, todos, um, waiver_anulada
from command_center.providers import portal

# os mesmos dois modelos que a IA usa no DocuSign (adminai/mcp/docusign_mcp.py, TEMPLATES)
MODELOS = {
    "adult": "c51aede4-bba5-40df-9f14-24c340e2bd3e",      # Adult Waiver of Liability
    "parental": "6dbf2094-39da-4c21-95dd-feda7ac28022",   # Parental consent Waiver liability
}
NOME = {"adult": "Adult Release and Waiver of Liability",
        "parental": "Parental Consent, Release and Waiver of Liability (minor)"}
VALIDADE_DIAS = 365
AVISO_18_DIAS = 7                   # dono, 06/10: avisar 7 dias antes dos 18 (era 30)
# #119 (dono, 06/10: sem tradução por enquanto): quem assina confirma o idioma; vai para a trilha
IDIOMA = "I read and understand English, or I had this document translated before signing."
MAX_ASSINATURA = 400_000            # bytes do PNG desenhado
MIN_TINTA = 0.004                   # fração mínima de pixels pintados: quadro em branco não é assinatura


class ErroWaiver(ValueError):
    """Mensagem em inglês: é o que o cliente lê."""


def _so_ele_assina(nome):
    return (f"{nome} is an adult and must sign their own waiver: only the driver can give up their own rights. "
            f"{nome} can create their own account and sign it there, or sign in person at the track.")


# Pelo menor, online, só pai ou mãe (#105). Tutor nomeado por juiz: no balcão, com a ordem judicial.
PARENTESCOS = {"mother": "Mother", "father": "Father"}
DECLARACAO = "I am the parent (natural guardian) of {minor} and I have the authority to sign this waiver for them."


LEITURA_HORAS = 24
MODOS_LEITURA = {
    "pdf_viewer": "every page of the PDF shown on screen before the boxes unlock",
    "pdf_opened_and_text": "the browser could not show the PDF: the signer opened the PDF and scrolled the text to the end",
}


def _leitura(con, conta_id, tipo, dados, agora_utc, entidade="portal_account", evento="portal.waiver.document_view"):
    """#107: (quando o PDF foi entregue a esta conta, quando a tela viu todas as páginas).
    #135: pelo convite, a entrega é registrada no convite (`waiver_invite`), não numa conta."""
    entregue = um(con, """SELECT MAX(at) AS at FROM audit_logs WHERE event=?
                           AND entity_type=? AND entity_id=? AND json_extract(detail, '$.kind')=?
                           AND at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)""",
                 (evento, entidade, str(conta_id), tipo, f"-{LEITURA_HORAS} hours"))["at"]
    if not entregue:
        raise ErroWaiver("Open and read the whole document before signing.")
    try:
        lido = datetime.fromisoformat(str(dados.get("document_read_at") or "").replace("Z", "+00:00"))
        if lido.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ErroWaiver("Read the whole document before signing: scroll through every page.")
    if not (agora_utc - timedelta(hours=LEITURA_HORAS) <= lido <= agora_utc + timedelta(minutes=2)):
        raise ErroWaiver("Read the whole document before signing: scroll through every page.")
    modo = dados.get("document_read_mode") or "pdf_viewer"
    if modo not in MODOS_LEITURA:
        raise ErroWaiver("Read the whole document before signing: scroll through every page.")
    return entregue, lido.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), modo


def _parentesco(dados, menor):
    """O parentesco de quem assina a parental, validado; devolve (rótulo, declaração aceita)."""
    rel = (dados.get("relationship") or "").strip().lower()
    if rel == "legal_guardian":
        raise ErroWaiver("A court-appointed legal guardian signs in person at the track, with a copy of the court order.")
    if rel == "other":
        raise ErroWaiver(f"Only a parent (mother or father) can sign the waiver for a minor. Ask {menor}'s mother or "
                         "father to sign it, or come to the track together.")
    if rel not in PARENTESCOS:
        raise ErroWaiver(f"Tell us your relationship to {menor}: only a parent can sign the waiver for a minor.")
    if not dados.get("guardian_declaration"):
        raise ErroWaiver(f"Confirm that you are {menor}'s parent and have the authority to sign for them.")
    return PARENTESCOS[rel], DECLARACAO.format(minor=menor)


def precisa_assinar_sozinho(piloto, tipo):
    """Piloto adulto que não é o titular da conta: o titular não assina por ele (#104)."""
    return tipo == "adult" and not piloto.get("is_self")


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
    if ligado:                                     # #116: só barra com o texto aprovado pelo advogado configurado
        a = aviso_do_atual(con)
        if a["configured"] and not a["ok"]:
            raise ValueError(f"o modelo parental atual não passa na conferência do aviso §744.301(3): {a['reason']}")
    con.execute("INSERT OR IGNORE INTO booking_config (id) VALUES (1)")
    atualizar(con, "booking_config", 1, waiver_native=1 if ligado else 0, updated_by=por, updated_at=agora())
    return ligada(con)


# ------------------------------------------------------------------ modelos
def modelo(con, tipo):
    m = um(con, "SELECT * FROM waiver_templates WHERE kind=?", (tipo,))
    return m if m and m["pdf_path"] and os.path.isfile(m["pdf_path"]) else None


def _numero(con, vid):
    """A versão N do modelo (1 = a primeira importada daquele tipo)."""
    r = um(con, """SELECT COUNT(*) AS n FROM waiver_template_versions x
                   WHERE x.kind = (SELECT kind FROM waiver_template_versions WHERE id=?) AND x.id <= ?""", (vid, vid))
    return r["n"] if r and r["n"] else None


def modelos(con):
    return [{"kind": k, "templateId": MODELOS[k], "name": (m["name"] if m else None), "pages": (m["pages"] if m else None),
             "sha256": (m["sha256"] if m else None), "imported_at": (m["imported_at"] if m else None),
             "version_id": (m.get("version_id") if m else None),
             "version": (_numero(con, m["version_id"]) if m and m.get("version_id") else None)}
            for k in MODELOS for m in [modelo(con, k)]]


def _pdf_da_versao(tipo, sha, pdf, caminho=None):
    """O PDF da versão, gravado uma vez e só leitura (0400, como o assinado, #109). Já está lá com o mesmo
    hash: não mexe. Sumiu ou mudou por fora: volta o original, que é o que o hash da versão diz."""
    caminho = caminho or os.path.join(pasta(), "modelos", f"{tipo}-{sha}.pdf")
    try:
        with open(caminho, "rb") as f:
            if _sha(f.read()) == sha:
                return caminho, False
        os.chmod(caminho, 0o600)
    except FileNotFoundError:
        pass
    with open(caminho, "wb") as f:
        f.write(pdf)
    os.chmod(caminho, 0o400)
    return caminho, True


def guardar_modelo(con, tipo, nome, pdf, por=None, origem="docusign"):
    """Guarda o PDF de um modelo como veio, com o hash e o texto (para ler na tela).

    #116: cada texto é uma versão em `waiver_template_versions` (append-only); o mesmo PDF de novo é a mesma
    versão. `waiver_templates` passa a apontar para ela, e a versão anterior continua consultável, com o PDF.
    O parental passa pela conferência do aviso §744.301(3): com o texto aprovado configurado, o que não passa
    não entra (o atual continua valendo); sem ele, o resultado fica na versão e só informa."""
    from pypdf import PdfReader
    from command_center.db import transacao
    from command_center.providers import aviso_744
    if tipo not in MODELOS:
        raise ValueError("modelo desconhecido")
    if not pdf.startswith(b"%PDF"):
        raise ValueError("o arquivo do modelo não é um PDF")
    sha = _sha(pdf)
    leitor = PdfReader(io.BytesIO(pdf))
    texto = "\n\n".join((p.extract_text() or "").strip() for p in leitor.pages).strip()
    aviso = aviso_744.conferir(pdf) if tipo == "parental" else None
    if aviso and aviso["configured"] and not aviso["ok"]:
        raise ValueError(f"o modelo parental não passa na conferência do aviso §744.301(3): {aviso['reason']} "
                         "Nada foi importado: o modelo atual continua valendo.")
    antes = um(con, "SELECT * FROM waiver_template_versions WHERE kind=? AND sha256=?", (tipo, sha))
    caminho, gravou = _pdf_da_versao(tipo, sha, pdf, antes["pdf_path"] if antes else None)
    quando = agora()

    def gravar_versao():
        con.execute("""INSERT OR IGNORE INTO waiver_template_versions (kind, sha256, name, pdf_path, pages, text, source,
                       imported_at, imported_by, notice_744) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (tipo, sha, nome, caminho, len(leitor.pages), texto, origem, quando, por,
                     json.dumps(aviso, ensure_ascii=False) if aviso else None))
        v = um(con, "SELECT id, pdf_path FROM waiver_template_versions WHERE kind=? AND sha256=?", (tipo, sha))
        campos = dict(name=nome, pdf_path=v["pdf_path"], sha256=sha, pages=len(leitor.pages), text=texto,
                      source=origem, imported_at=quando, imported_by=por, version_id=v["id"])
        if um(con, "SELECT 1 AS x FROM waiver_templates WHERE kind=?", (tipo,)):
            con.execute(f"UPDATE waiver_templates SET {', '.join(k + '=?' for k in campos)} WHERE kind=?", (*campos.values(), tipo))
        else:
            con.execute(f"INSERT INTO waiver_templates (kind, {', '.join(campos)}) VALUES (?{', ?' * len(campos)})",
                        (tipo, *campos.values()))
        return campos

    if con.in_transaction:
        campos = gravar_versao()
    else:
        with transacao(con):
            campos = gravar_versao()
    return dict(kind=tipo, **{k: v for k, v in campos.items() if k != "text"}, version=_numero(con, campos["version_id"]),
                new_version=antes is None, file_restored=bool(antes) and gravou,
                notice_744_ok=aviso["ok"] if aviso else None)


def importar_do_docusign(con, por=None):
    """LÊ os dois modelos no DocuSign (nome + PDF) e guarda aqui. Não altera nada lá.
    Baixa os dois antes de guardar: o parental que não passa no aviso (#116) não deixa entrar só o adult."""
    from command_center.providers import aviso_744, modulo
    ds = modulo("docusign")
    baixados = []
    for tipo, tid in MODELOS.items():
        info = ds.modelo_humano(tid)
        docs = info.get("documentos") or []
        if len(docs) != 1:
            raise ValueError(f"o modelo {info.get('nome') or tid} tem {len(docs)} documentos; esperava 1")
        baixados.append((tipo, info.get("nome") or NOME[tipo], ds.baixar_documento_do_modelo_humano(tid, docs[0]["documentId"])))
    for tipo, _nome, pdf in baixados:
        a = aviso_744.conferir(pdf) if tipo == "parental" else None
        if a and a["configured"] and not a["ok"]:
            raise ValueError(f"o modelo parental do DocuSign não passa na conferência do aviso §744.301(3): {a['reason']} "
                             "Nada foi importado: os modelos atuais continuam valendo.")
    return [guardar_modelo(con, tipo, nome, pdf, por) for tipo, nome, pdf in baixados]


# ------------------------------------------------------------------ versões do modelo (#116)
def _versao_saida(v):
    v = dict(v)
    v["notice_744"] = json.loads(v["notice_744"]) if v.get("notice_744") else None
    if "current" in v:
        v["current"] = bool(v["current"])
    return v


_VERSAO = """v.id, v.kind, v.sha256, v.name, v.pages, v.source, v.imported_at, v.imported_by, u.name AS imported_by_name,
             v.notice_744, (t.version_id IS NOT NULL) AS current,
             (SELECT COUNT(*) FROM waiver_template_versions x WHERE x.kind = v.kind AND x.id <= v.id) AS number,
             (SELECT COUNT(*) FROM waivers w WHERE w.source='urace' AND w.template = v.kind
                AND json_extract(w.audit, '$.template_sha256') = v.sha256) AS signatures"""
_DE_VERSAO = """FROM waiver_template_versions v LEFT JOIN users u ON u.id = v.imported_by
                LEFT JOIN waiver_templates t ON t.version_id = v.id"""


def versoes(con, kind=None, limit=50, offset=0):
    """Todas as versões dos modelos, das mais novas para as mais velhas, paginadas (sem o texto)."""
    onde, args = ("WHERE v.kind=?", (kind,)) if kind else ("", ())
    total = um(con, f"SELECT COUNT(*) AS n FROM waiver_template_versions v {onde}", args)["n"]
    itens = todos(con, f"SELECT {_VERSAO} {_DE_VERSAO} {onde} ORDER BY v.id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"itens": [_versao_saida(v) for v in itens], "total": total, "limit": limit, "offset": offset}


def versao(con, vid):
    """Uma versão, com o texto e o caminho do PDF (ou None)."""
    v = um(con, f"SELECT {_VERSAO}, v.text, v.pdf_path {_DE_VERSAO} WHERE v.id=?", (vid,))
    return _versao_saida(v) if v else None


def versao_por_hash(con, kind, sha):
    """A versão que uma assinatura usou, pelo `template_sha256` da trilha (vale para as de antes das versões)."""
    v = um(con, "SELECT id FROM waiver_template_versions WHERE kind=? AND sha256=?", (kind, sha))
    return versao(con, v["id"]) if v else None


def aviso_do_atual(con):
    """A conferência do aviso §744.301(3) no modelo parental atual, contra o texto aprovado de agora."""
    from command_center.providers import aviso_744
    cfg = aviso_744.aprovado()
    if cfg and cfg.get("error"):                   # o arquivo que não abre ou está vazio vem antes de tudo (revisão #328)
        return {"configured": True, "ok": False, "reason": cfg["error"]}
    m = modelo(con, "parental")
    if not m:
        return {"configured": bool(cfg), "ok": None if not cfg else False,
                "reason": "O modelo parental ainda não foi importado."}
    with open(m["pdf_path"], "rb") as f:
        return aviso_744.conferir(f.read(), cfg)


def aviso(con):
    """O que Site › Waiver mostra do aviso: se há texto aprovado, onde ele fica e como o parental atual se sai."""
    from command_center.providers import aviso_744
    cfg = aviso_744.aprovado()
    return {**aviso_do_atual(con), "path": aviso_744.caminho(), "approved_text": cfg.get("text") if cfg else None,
            "approved_sha256": cfg.get("sha256") if cfg else None}


def _exigir_aviso(tipo, pdf):
    """#116: com o texto aprovado configurado, a parental sem o aviso do §744.301(3) não se assina online."""
    if tipo != "parental":
        return None
    from command_center.providers import aviso_744
    a = aviso_744.conferir(pdf)
    if a["configured"] and not a["ok"]:
        raise ErroWaiver("Online signing of this waiver is not available right now. Our team will send you the waiver.")
    return a


# ------------------------------------------------------------------ situação por piloto
def tipo_para(piloto):
    if not piloto.get("birth_date"):
        raise ErroWaiver("Add the driver's date of birth first: it decides which waiver applies.")
    return "parental" if portal.idade(date.fromisoformat(piloto["birth_date"])) < portal.MAIORIDADE else "adult"


def dia_dos_18(nascimento):
    """O dia em que o piloto faz 18 — pela mesma conta de `portal.idade` (29/02 vira 01/03)."""
    try:
        return nascimento.replace(year=nascimento.year + portal.MAIORIDADE)
    except ValueError:
        return date(nascimento.year + portal.MAIORIDADE, 3, 1)


def validade(tipo, nascimento, dia):
    """Até quando vale a waiver assinada em `dia`: 1 ano; a parental, no máximo até a véspera
    dos 18 (#106) — adulto, a renúncia do pai já não cobre a participação dele."""
    ate = dia + timedelta(days=VALIDADE_DIAS)
    if tipo == "parental" and nascimento:
        ate = min(ate, dia_dos_18(nascimento) - timedelta(days=1))
    return ate


def vigente(con, pid):
    """A waiver nativa ainda válida deste piloto (ou None). A parental deixa de valer quando o
    piloto faz 18, mesmo que a data gravada seja mais longa (assinada antes desta regra)."""
    w = um(con, f"""SELECT * FROM waivers WHERE pilot_id=? AND source='urace' AND status='completed'
                    AND COALESCE(hidden,0)=0 AND NOT {waiver_anulada()} AND expires_at >= ?
                    ORDER BY completed_at DESC LIMIT 1""",
           (pid, portal.hoje().isoformat()))
    if w and w["template"] == "parental":
        p = um(con, "SELECT birth_date FROM portal_pilots WHERE id=?", (pid,))
        if p and p["birth_date"] and portal.idade(date.fromisoformat(p["birth_date"])) >= portal.MAIORIDADE:
            return None
    return w


def faz_18_em(piloto):
    """A data dos 18 anos, se for nos próximos AVISO_18_DIAS dias (para avisar o responsável)."""
    if not piloto.get("birth_date"):
        return None
    d = dia_dos_18(date.fromisoformat(piloto["birth_date"]))
    hoje = portal.hoje()
    return d.isoformat() if hoje < d <= hoje + timedelta(days=AVISO_18_DIAS) else None


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
                      "own_signature_required": precisa_assinar_sozinho(p, tipo), "turns_18_on": faz_18_em(p),
                      "status": "signed" if w else "none", "waiver_id": w["id"] if w else None,
                      "signed_at": w["completed_at"] if w else None, "valid_until": w["expires_at"] if w else None})
    c = um(con, "SELECT email, email_verified_at FROM portal_accounts WHERE id=?", (conta_id,))
    return {"enabled": ativa, "drivers": saida, "email": c["email"] if c else None,
            "email_verified": bool(c and c["email_verified_at"])}


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
    from command_center.providers.trilha_waiver import sem_surrogate     # revisão #329: `\ud800` solto dava 500
    v = re.sub(r"\s+", " ", sem_surrogate(v or "").strip())
    if len(v) < 3 or " " not in v:
        raise ErroWaiver("Type your full name, as your signature.")
    return v[:120]


def _preparar(con, conta_id, pid, dados):
    """O que a revisão e o clique final conferem igual (#112: tudo, menos o código do e-mail)."""
    from command_center.providers import revisao_waiver as rv
    if not ligada(con):
        raise ErroWaiver("Online waiver signing is not available yet. Our team will send you the waiver.")
    if not dados.get("read_and_agree") or not dados.get("consent_esign"):
        raise ErroWaiver("Check both boxes to sign: that you read and agree, and that you agree to sign electronically.")
    if not dados.get("english_understood"):
        raise ErroWaiver("Confirm that you read and understand English, or that you had the document translated.")
    c = portal.conta(con, conta_id)
    p = next((x for x in portal.pilotos(con, conta_id) if x["id"] == pid), None)
    if not c or not p:
        raise LookupError("driver")
    tipo = tipo_para(p)
    if precisa_assinar_sozinho(p, tipo):
        raise ErroWaiver(_so_ele_assina(p["name"]))
    parentesco, declaracao = _parentesco(dados, p["name"]) if tipo == "parental" else (None, None)
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
    _exigir_aviso(tipo, base)                              # #116: antes de gastar o código do e-mail
    entregue, lido, modo = _leitura(con, conta_id, tipo, dados, datetime.now(timezone.utc))
    verificado = um(con, "SELECT email_verified_at FROM portal_accounts WHERE id=?", (conta_id,))["email_verified_at"]
    if not verificado:
        raise ErroWaiver("Confirm your email before signing: we send a code to it.")
    ids = dict(account_id=conta_id, pilot_id=pid, client_id=p.get("client_id"), kind=tipo, template_version_id=m.get("version_id"))
    return {"c": c, "p": p, "tipo": tipo, "parentesco": parentesco, "declaracao": declaracao, "m": m, "nome": nome, "png": png,
            "base": base, "entregue": entregue, "lido": lido, "modo": modo, "verificado": verificado, "ids": ids,
            "conteudo": rv.conteudo(dados, nome, _sha(png), pid, tipo, m["sha256"])}


def _validade_hoje(tipo, nascimento):
    """(até, motivo) para uma assinatura feita agora, no dia da Flórida."""
    hoje = datetime.now(timezone.utc).astimezone(portal.FUSO).date()
    ate = validade(tipo, date.fromisoformat(nascimento), hoje)
    motivo = ("the day before the minor turns 18" if tipo == "parental" and ate < hoje + timedelta(days=VALIDADE_DIAS)
              else "one year")
    return ate.isoformat(), motivo


def resumo(r, m, tipo, piloto, nascimento, nome_cadastro, parentesco, declaracao, png):
    """#112: o que a tela de revisão mostra antes do clique final (e o servidor vai assinar exatamente isto)."""
    from command_center.providers import revisao_waiver as rv
    ate, motivo = _validade_hoje(tipo, nascimento)
    return {"review_id": r["id"], "review_expires_at": r["expires_at"], "document": m["name"], "pages": m["pages"],
            "kind": tipo, "driver": piloto, "driver_birth_date": nascimento,
            "signing_as": "Parent (natural guardian)" if tipo == "parental" else "Participant (signing for yourself)",
            "relationship": parentesco, "guardian_declaration": declaracao, "typed_name": r["typed_name"],
            "name_on_file": nome_cadastro, "name_matches": bool(r["name_matches"]), "signature_sha256": _sha(png),
            "valid_until": ate, "valid_until_reason": motivo, "legal_effect": rv.EFEITO_LEGAL, "button": rv.BOTAO}


def revisar(con, conta_id, pid, dados, ip=None, aparelho=None):
    """#112, passo 1: confere tudo menos o código e devolve o resumo. A revisão vai para a trilha (`reviewed`)."""
    from command_center.providers import revisao_waiver as rv
    x = _preparar(con, conta_id, pid, dados)
    r = rv.criar(con, "account", x["ids"], x["m"]["sha256"], x["conteudo"], x["nome"], x["c"]["name"], x["parentesco"],
                 ip=ip, user_agent=aparelho, detail={"read_and_agree": True, "consent_esign": True, "language_ack": True,
                                                     "guardian_declaration": bool(x["declaracao"]),
                                                     "signature_png_sha256": _sha(x["png"])})
    return resumo(r, x["m"], x["tipo"], x["p"]["name"], x["p"]["birth_date"], x["c"]["name"], x["parentesco"],
                  x["declaracao"], x["png"])


def assinar(con, conta_id, pid, dados, ip=None, aparelho=None):
    """Assina a waiver do piloto `pid` pela conta `conta_id`. Devolve a linha de `waivers`.
    #112: só com a revisão (`review_id`) desta conta e piloto, válida, nunca usada e com o mesmo conteúdo."""
    from command_center.providers import codigos, revisao_waiver as rv, trilha_waiver as tw
    x = _preparar(con, conta_id, pid, dados)
    c, p, tipo, m, nome, png, ids = x["c"], x["p"], x["tipo"], x["m"], x["nome"], x["png"], x["ids"]
    rev = rv.exigir(con, dados.get("review_id"), "account", ids, m["sha256"], x["conteudo"], dados.get("name_mismatch_confirmed"))
    try:
        cod = codigos.conferir(con, conta_id, "waiver_sign", dados.get("sign_code"))
    except codigos.ErroCodigo as e:
        raise ErroWaiver(str(e))
    tw.registrar(con, "code_verified", "account", ip=ip, user_agent=aparelho,                       # #111
                 detail={"sent_to": codigos.mascarar(cod["sent_to"]), "sent_at": cod["created_at"]}, **ids)
    agora_utc = datetime.now(timezone.utc)                # a hora da assinatura vem depois do último passo da trilha
    login = um(con, """SELECT created_at, ip FROM portal_sessions WHERE account_id=? AND revoked_at IS NULL
                        ORDER BY created_at DESC LIMIT 1""", (conta_id,))
    ny = agora_utc.astimezone(portal.FUSO)
    nasc = date.fromisoformat(p["birth_date"])
    ate_d = validade(tipo, nasc, ny.date())
    ate = ate_d.isoformat()
    ate_motivo = ("the day before the minor turns 18" if tipo == "parental" and ate_d < ny.date() + timedelta(days=VALIDADE_DIAS)
                  else "one year")
    sid = str(uuid.uuid4())
    verificado = x["verificado"]
    revisao = rv.na_trilha(rev, agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), dados.get("name_mismatch_confirmed"))
    trilha = {
        "signature_id": sid, "template": tipo, "template_name": m["name"], "template_sha256": m["sha256"],
        "template_pages": m["pages"], "account_id": conta_id, "account_email": c["email"], "signer_name": c["name"],
        "typed_name": nome, "driver_id": pid, "driver_name": p["name"], "driver_birth_date": p["birth_date"],
        "signer_relationship": x["parentesco"], "guardian_declaration": x["declaracao"],
        "signed_at_utc": agora_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "signed_at_local": ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ip": ip, "user_agent": (aparelho or "")[:300], "read_and_agree": True, "consent_esign": True,
        "language_ack": IDIOMA, "governing_law": "Florida law; courts in Orange County, Florida",
        "document_delivered_at": x["entregue"], "document_all_pages_viewed_at": x["lido"],
        "reading_mode": x["modo"], "reading_requirement": MODOS_LEITURA[x["modo"]],
        "authentication": (f"URACE client account (email + password); email verified {verificado}; "
                           f"one-time code sent to {cod['sent_to']} at {cod['created_at']}, confirmed {cod['used_at']}"),
        "email_verified_at": verificado, "otp_sent_to": cod["sent_to"], "otp_sent_at": cod["created_at"],
        "otp_verified_at": cod["used_at"], "otp_message_id": cod["message_id"],
        "session_login_at": login["created_at"] if login else None, "session_login_ip": login["ip"] if login else None,
        "signature_png_sha256": _sha(png), "valid_until": ate, "valid_until_reason": ate_motivo,
        "review": revisao, "reviewed_at_utc": revisao["reviewed_at"], "confirmed_at_utc": revisao["confirmed_at"],
    }
    return gravar(con, x["base"], m, trilha, png, client_id=p.get("client_id"), pilot_id=pid,
                  signer_name=c["name"], signer_email=c["email"],
                  link_reason="assinada na área do cliente" if p.get("client_id") else None,
                  link_by="sync" if p.get("client_id") else None,
                  resumo=f"waiver de {c['name']} assinada na área do cliente ({p['name']})",
                  antes=lambda c2: rv.marcar_usada(c2, rev["id"]),
                  eventos={"fluxo": "account", "cobrir": dict(account_id=conta_id, pilot_id=pid, kind=tipo), "ids": ids,
                           "ip": ip, "user_agent": aparelho, "detalhe": _no_signed(revisao)})


def _no_signed(revisao):
    """#112: o que o `signed` da trilha guarda da revisão: as duas horas e os dois nomes."""
    return {k: revisao[k] for k in ("review_id", "reviewed_at", "confirmed_at", "typed_name", "name_on_file", "name_matches",
                                    "name_mismatch_confirmed")}


def pdf_final(base, trilha, png):
    """Monta e guarda o PDF assinado (o modelo + página de certificado); põe o hash na trilha."""
    final = _pdf_assinado(base, trilha, png)
    caminho = os.path.join(pasta(), f"urace-{trilha['signature_id']}.pdf")
    with open(caminho, "wb") as f:
        f.write(final)
    os.chmod(caminho, 0o400)                      # #109: só leitura, nem o dono do processo regrava
    trilha["document_sha256"] = _sha(final)
    return caminho


def gravar(con, base, m, trilha, png, client_id, pilot_id, signer_name, signer_email, link_reason, link_by, resumo,
           caminho=None, antes=None, eventos=None):
    """Grava a waiver assinada na MESMA tabela das do DocuSign (card, anexo e agenda tratam igual).
    `antes(con)` roda dentro da mesma transação, antes do INSERT (o convite se marca usado ali).
    #109: a trilha inteira vai também para o `audit_logs` (append-only), na mesma transação: a linha da
    waiver é imutável por trigger e o audit_logs guarda uma segunda cópia que ninguém reescreve.
    #111: `eventos` = {fluxo, cobrir, ids, ip, user_agent}. Os eventos de antes (pelo escopo `cobrir`) vão
    para a trilha e para o certificado; o `signed` entra em `waiver_events`, na mesma transação, com os ids."""
    from command_center.db import auditar, transacao
    from command_center.providers import trilha_waiver as tw
    tipo = trilha["template"]
    cob = tw.cobertos(con, **eventos["cobrir"]) if eventos else []
    if eventos:
        trilha["events"] = tw.para_o_certificado(cob, portal.FUSO)
        trilha["events_chain_hash"] = cob[-1]["hash"] if cob else None
    trilha.setdefault("template_version_id", m.get("version_id"))      # #116: a versão do modelo que valia
    if tipo == "parental":                                               # e como ela se saiu na conferência do aviso
        from command_center.providers import aviso_744
        a = aviso_744.conferir(base)
        trilha.setdefault("notice_744_check", {k: a.get(k) for k in ("configured", "ok", "approved_sha256", "notice_pt", "body_pt")})
    caminho = caminho or pdf_final(base, trilha, png)
    quando = agora()
    with transacao(con):
        if antes:
            antes(con)
        wid = inserir(con, "waivers", client_id=client_id, signer_name=signer_name, signer_email=signer_email,
                      template=tipo, status="completed", sent_at=quando, completed_at=quando, expires_at=trilha["valid_until"],
                      minor_name=trilha["driver_name"] if tipo == "parental" else None, pdf_path=caminho,
                      subject=f"{m['name']} — {trilha['driver_name']}"[:200], source="urace", pilot_id=pilot_id,
                      doc_sha256=trilha["document_sha256"], audit=json.dumps(trilha, ensure_ascii=False),
                      link_reason=link_reason, link_by=link_by, synced_at=quando)
        con.execute("INSERT INTO entity_links (entity_type, entity_id, system, external_id) VALUES ('waiver', ?, 'urace', ?)",
                    (wid, trilha["signature_id"]))
        quem = f"portal:{trilha['account_id']}" if trilha.get("account_id") else f"invite:{trilha.get('invitation_id')}"
        auditar(con, "waiver.signed.trail", quem, entity_type="waiver", entity_id=wid, detail=trilha, ip=trilha.get("ip"))
        if eventos:
            tw.registrar(con, "signed", eventos["fluxo"], ip=eventos.get("ip"), user_agent=eventos.get("user_agent"),
                         detail={"covers": [e["id"] for e in cob], "document_sha256": trilha["document_sha256"],
                                 "template_sha256": trilha["template_sha256"], **(eventos.get("detalhe") or {})},
                         waiver_id=wid, signature_id=trilha["signature_id"], **eventos["ids"])
        if client_id:
            from command_center.api import motor
            motor.registrar_evento(con, "waiver.completed", "waiver", wid, client_id, resumo)
    return um(con, "SELECT * FROM waivers WHERE id=?", (wid,))


def da_conta(con, conta_id, wid):
    """A waiver nativa `wid`, só se for de um piloto desta conta."""
    return um(con, """SELECT w.* FROM waivers w JOIN portal_pilots p ON p.id=w.pilot_id
                      WHERE w.id=? AND w.source='urace' AND p.account_id=?""", (wid, conta_id))


def listar(con, limit=50, offset=0):
    """As assinadas aqui, das mais novas para as mais velhas, paginadas."""
    total = um(con, "SELECT COUNT(*) AS n FROM waivers WHERE source='urace'")["n"]
    itens = todos(con, """SELECT w.id, w.client_id, w.pilot_id, w.signer_name, w.signer_email, w.minor_name, w.template,
                                 w.completed_at, w.expires_at, w.doc_sha256,
                                 v.at AS voided_at, v.by_name AS voided_by, v.reason AS void_reason
                            FROM waivers w LEFT JOIN waiver_voids v ON v.waiver_id = w.id WHERE w.source='urace'
                          ORDER BY w.completed_at DESC, w.id DESC LIMIT ? OFFSET ?""", (limit, offset))
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------------ anular (#109)
MIN_MOTIVO = 10


class NaoAnula(Exception):
    """Não é uma waiver que se anula aqui, ou já foi anulada (a rota devolve 409)."""


def anulacao(con, wid):
    return um(con, "SELECT * FROM waiver_voids WHERE waiver_id=?", (wid,))


def anular(con, wid, usuario, motivo, ip=None):
    """Tira de vigor uma waiver assinada no próprio sistema, sem mexer nela (dono, 06/10: "nunca apagar").

    A linha da waiver é imutável (trigger); a anulação vai para `waiver_voids` (append-only), com quem,
    quando e por quê, e para a auditoria (`waiver.void`). A waiver continua no card, na lista e no backup,
    marcada como anulada; `vigente` deixa de vê-la e o cliente pode assinar outra. Não se desfaz."""
    from command_center.db import auditar, transacao
    from command_center.providers.trilha_waiver import sem_surrogate
    motivo = re.sub(r"\s+", " ", sem_surrogate(motivo or "").strip())[:500]
    if len(re.sub(r"[\W_]+", "", motivo)) < MIN_MOTIVO:      # letras e números: "........." não é motivo
        raise ErroWaiver(f"Escreva o motivo da anulação (pelo menos {MIN_MOTIVO} letras).")
    w = um(con, "SELECT * FROM waivers WHERE id=?", (wid,))
    if not w:
        raise LookupError("waiver")
    if w["source"] != "urace" or w["status"] != "completed":
        raise NaoAnula("Só a waiver assinada no próprio sistema se anula aqui. A do DocuSign se resolve no DocuSign.")
    try:
        with transacao(con, imediata=True):
            if anulacao(con, wid):
                raise NaoAnula("Esta waiver já foi anulada.")
            inserir(con, "waiver_voids", waiver_id=wid, user_id=usuario.get("id"), by_name=usuario.get("name") or "?", reason=motivo)
            from command_center.providers import trilha_waiver as tw       # #111: depois de assinar, na trilha
            tw.registrar(con, "voided", "staff", ip=ip, detail={"reason": motivo, "by": usuario.get("name"), "user_id": usuario.get("id")},
                         waiver_id=wid, client_id=w["client_id"], pilot_id=w["pilot_id"], kind=w["template"])
            auditar(con, "waiver.void", f"user:{usuario.get('id')}", user_id=usuario.get("id"), entity_type="waiver", entity_id=wid,
                    detail={"reason": motivo, "client_id": w["client_id"], "template": w["template"],
                            "signed_at": w["completed_at"], "sha256": w["doc_sha256"]}, ip=ip)
    except sqlite3.IntegrityError:                         # duas anulações ao mesmo tempo: a segunda bate no UNIQUE
        raise NaoAnula("Esta waiver já foi anulada.")
    return anulacao(con, wid)


# ------------------------------------------------------------------ o PDF
MARGEM_PE = 54                     # pontos: abaixo disto o certificado muda de página (#111)


def _pdf_assinado(base, t, png):
    """O PDF do modelo, intacto, + a página de assinatura e certificado no fim (#111: quantas páginas
    precisar; o texto nunca passa do pé, muda de página)."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=letter)
    cv.setTitle(f"Signature and certificate — {t['template_name']}")
    larg, alt = letter
    x, y = 54, alt - 64

    def nova_pagina():
        nonlocal y
        cv.showPage()
        y = alt - 64
        cv.setFont("Helvetica-Oblique", 8)
        cv.drawString(x, y + 22, f"Electronic signature and certificate of completion (continued) · Signature ID {t['signature_id']}")

    def cabe(altura):
        if y - altura < MARGEM_PE:
            nova_pagina()

    def linha(txt, tam=10, fonte="Helvetica", passo=14):
        nonlocal y
        for pedaco in _quebra(txt, 95 if tam <= 10 else 70):
            cabe(passo)
            cv.setFont(fonte, tam)
            cv.drawString(x, y, pedaco)
            y -= passo

    linha("Electronic signature and certificate of completion", 15, "Helvetica-Bold", 22)
    linha(f"Document: {t['template_name']} ({t['template_pages']} page(s) above this one)")
    linha(f"Signature ID: {t['signature_id']}")
    y -= 6
    rotulo = "Parent (natural guardian)" if t["template"] == "parental" else "Participant"
    linha(f"{rotulo}: {t['signer_name']}   ·   {t.get('email_label') or 'Account'}: {t['account_email']}", 11, "Helvetica-Bold", 16)
    if t["template"] == "parental":
        linha(f"Minor participant: {t['driver_name']}   ·   Date of birth: {t['driver_birth_date']}")
        linha(f"Relationship to the minor: {t.get('signer_relationship') or '—'}")
        if t.get("guardian_declaration"):
            linha(f"Declaration accepted: \"{t['guardian_declaration']}\"")
    y -= 4
    linha("By signing below I confirm that I have read the document above, that I agree to its terms, and that I "
          "agree to sign it electronically. My electronic signature has the same effect as a handwritten signature.")
    y -= 8
    cabe(140)                                         # a assinatura, a linha e o nome ficam juntos
    img = ImageReader(io.BytesIO(png))
    iw, ih = img.getSize()
    w = min(260.0, iw * 80.0 / max(ih, 1))
    cv.drawImage(img, x, y - 80, width=w, height=w * ih / max(iw, 1), mask="auto")
    y -= 90
    cv.line(x, y, x + 300, y)
    y -= 14
    linha(f"Signature of {t['signer_name']}   ·   Typed name: {t['typed_name']}")
    linha(f"Signed: {t['signed_at_local']}  ({t['signed_at_utc']} UTC)   ·   Valid until: {t['valid_until']}"
          f" ({t.get('valid_until_reason') or 'one year'})")
    rev = t.get("review")
    if rev:                                           # #112: as duas etapas, com as duas horas, e os dois nomes
        linha(f"Reviewed the summary: {_hora_local(rev['reviewed_at'])} ({_hora_utc(rev['reviewed_at'])} UTC)   ·   "
              f"Confirmed and signed: {t['signed_at_local']} ({t['signed_at_utc']} UTC)")
        if not rev.get("name_matches"):
            linha(f"Name on file: {rev.get('name_on_file') or '—'}   ·   Typed name: {rev.get('typed_name')}   ·   "
                  "The signer was told the names differ and confirmed signing with the typed name.")
    y -= 10
    linha("Audit trail", 11, "Helvetica-Bold", 16)
    for k, v in (("Authentication", t["authentication"]),
                 ("Document delivered to the signer", t.get("document_delivered_at") or "—"),
                 ("Whole document read", f"{t.get('document_all_pages_viewed_at') or '—'} ({t.get('reading_requirement') or '—'})"),
                 ("IP address", t["ip"] or "—"),
                 ("Device", t["user_agent"] or "—"), ("Agreed: read and agree", "yes"),
                 ("Agreed: sign electronically", "yes"),
                 ("Language", t.get("language_ack") or "—"),
                 ("Document hash (SHA-256)", t["template_sha256"]),
                 ("Template version ID", t.get("template_version_id") or "—"),
                 ("Signature image hash (SHA-256)", t["signature_png_sha256"]),
                 *((("Shown next to the final button", t["review"]["legal_effect_statement"]),) if t.get("review") else ())):
        linha(f"{k}: {v}", 9, "Helvetica", 12)
    if t.get("events") is not None:                   # #111: os passos até a assinatura, um por um
        y -= 8
        cabe(16 + 36)
        linha("Event history (Florida time, America/New_York, and UTC)", 11, "Helvetica-Bold", 16)
        for e in [*t["events"], {"label": "Signed", "source": "server", "at_local": t["signed_at_local"],
                                 "at_utc": t["signed_at_utc"], "ip": t.get("ip"), "user_agent": t.get("user_agent")}]:
            quem = "reported by the signer's browser" if e["source"] == "client" else "recorded by URACE's server"
            if e.get("count", 1) > 1:                 # o mesmo passo repetido em seguida: uma linha, do primeiro ao último
                topo = (f"{e['at_local']} ({e['at_utc']} UTC) to {e['last_at_local']} ({e['last_at_utc']} UTC) · "
                        f"{e['label']} ×{e['count']} · {quem}")
            else:
                topo = f"{e['at_local']} ({e['at_utc']} UTC) · {e['label']} · {quem}"
            aparelho = f"IP {e.get('ip') or '—'} · Device: {(e.get('user_agent') or '—')[:160]}"
            cabe(12 * len(_quebra(topo, 95)) + 11 * len(_quebra(aparelho, 95)))     # o evento não se parte entre páginas
            linha(topo, 9, "Helvetica-Bold", 12)
            linha(aparelho, 8, "Helvetica", 11)
        if t.get("events_chain_hash"):
            linha(f"Event chain: each event above is kept in URACE's append-only, hash-chained record; hash of the last one: "
                  f"{t['events_chain_hash']}", 8, "Helvetica-Oblique", 11)
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


def _hora_utc(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hora_local(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(portal.FUSO).strftime("%Y-%m-%d %H:%M:%S %Z")


def _quebra(txt, n):
    palavras, linhas, atual = str(txt).split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > n and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return linhas + ([atual] if atual else [])
