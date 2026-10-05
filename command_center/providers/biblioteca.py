"""BIBLIOTECA — todos os documentos de cada cliente, num lugar só, e o backup no Drive (#88).

Dono, 05/10: *"todos os tipos de contrato, waivers, recibos de pagamento, invoices que forem
enviadas, históricos de serviço — a gente precisa de um backup no nosso Google Drive"* e
*"dentro do Command Center, uma aba chamada Biblioteca"*. E as decisões do mesmo dia:

- **todas** as invoices do QuickBooks, no PDF que o próprio QuickBooks imprime; se a invoice
  muda, o PDF é baixado de novo;
- **recibo** é o comprovante do pagamento recebido no QuickBooks;
- atualizada **todo dia por rotina programada, sem IA** — não gasta token;
- a Biblioteca é de **gerente para cima**;
- no Drive: pasta **Command Center**, por cliente, compartilhada com o Eduardo.

Regras que mandam aqui:
- **Só leitura nas origens.** QuickBooks e DocuSign só são lidos.
- **Nunca no card errado.** O documento só entra no card de um cliente quando o vínculo é
  certo (a invoice já ligada pela sincronia, ou um cliente do QuickBooks que aponta para um
  card só). Na dúvida, vai para "Sem cliente" — e uma pessoa resolve.
- **Só baixa o que mudou.** Cada documento guarda a versão da origem; igual, não baixa.
- **Nada é apagado.** No Drive, um documento que mudou substitui o arquivo, e o Drive guarda
  a versão anterior no histórico dele.
"""
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone

from command_center.db import agora, atualizar, inserir, todos, um

KINDS = ("invoice", "recibo", "contrato", "waiver", "historico")
PASTA_KIND = {"invoice": "Invoices", "recibo": "Recibos", "contrato": "Contratos", "waiver": "Waivers",
              "historico": "Histórico de serviço"}
RAIZ_DRIVE = "Command Center"
COMPARTILHAR = [e.strip() for e in os.environ.get("BIBLIOTECA_COMPARTILHAR", "eduardo@urace.us").split(",") if e.strip()]


def pasta(kind=None):
    p = os.environ.get("CC_BIBLIOTECA_DIR") or os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "biblioteca")
    p = os.path.join(p, kind) if kind else p
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _sha_arquivo(caminho):
    with open(caminho, "rb") as f:
        return _sha(f.read())


def estado(con, chave, valor=None):
    if valor is None:
        r = um(con, "SELECT value FROM library_state WHERE key=?", (chave,))
        return r["value"] if r else None
    con.execute("INSERT INTO library_state (key, value, at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, at=excluded.at",
                (chave, valor, agora()))
    return valor


def _gravar(kind, ref, dados):
    caminho = os.path.join(pasta(kind), re.sub(r"[^A-Za-z0-9._-]+", "_", f"{kind}-{ref}")[:120] + ".pdf")
    with open(caminho, "wb") as f:
        f.write(dados)
    os.chmod(caminho, 0o600)
    return caminho


def _upsert(con, kind, ref, **campos):
    d = um(con, "SELECT * FROM library_docs WHERE kind=? AND ref=?", (kind, str(ref)))
    campos["updated_at"] = agora()
    if d:
        atualizar(con, "library_docs", d["id"], **campos)
        return d["id"]
    return inserir(con, "library_docs", kind=kind, ref=str(ref), **campos)


# ------------------------------------------------------------------ de quem é
def _cliente_da_invoice(con, qbo_id):
    r = um(con, """SELECT i.client_id FROM entity_links l JOIN invoices i ON i.id=l.entity_id
                    WHERE l.entity_type='invoice' AND l.system='quickbooks' AND l.external_id=?""", (str(qbo_id),))
    return r["client_id"] if r else None


def _cliente_do_cliente_qbo(con, cliente_qbo):
    """Um cliente do QuickBooks aponta para UM card? Então é dele. Família com dois pilotos (dois
    cards com o mesmo cliente do QuickBooks) fica sem card: chutar seria pôr no card do outro."""
    if not cliente_qbo:
        return None
    cards = {r["client_id"] for r in todos(con, "SELECT DISTINCT client_id FROM invoices WHERE customer_ref=? AND client_id IS NOT NULL",
                                           (str(cliente_qbo),))}
    return cards.pop() if len(cards) == 1 else None


# ------------------------------------------------------------------ QuickBooks: invoices e recibos
def _qbo():
    from command_center.providers import modulo
    return modulo("quickbooks")


def _recibo_pdf(p, cliente):
    """Comprovante do pagamento com os dados do próprio QuickBooks, para quando ele não entrega
    o PDF do pagamento. Diz de onde veio: não se passa pelo documento do QuickBooks."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b, pagesize=letter)
    cv.setTitle(f"Payment receipt {p.get('numero') or p['id']}")
    y = 720
    cv.setFont("Helvetica-Bold", 16); cv.drawString(72, y, "URACE.US INC — Payment receipt"); y -= 30
    cv.setFont("Helvetica", 11)
    for rot, val in (("Customer", cliente or p.get("cliente") or "—"), ("Date", p.get("data") or "—"),
                     ("Amount", f"US$ {float(p.get('total') or 0):,.2f}"), ("Method", p.get("metodo") or "—"),
                     ("Reference", p.get("numero") or "—"), ("QuickBooks payment id", p["id"]),
                     ("Applied to invoices", ", ".join(p.get("invoices") or []) or "—")):
        cv.drawString(72, y, f"{rot}: {val}"); y -= 18
    cv.setFont("Helvetica-Oblique", 8)
    cv.drawString(72, 72, "Generated by the URACE Command Center from the QuickBooks payment record.")
    cv.showPage(); cv.save()
    return b.getvalue()


def sincronizar_qbo(con, qbo=None, log=print):
    """Invoices e pagamentos novos ou alterados desde a última rodada: grava o PDF de cada um."""
    qbo = qbo or _qbo()
    feitos = {"invoice": 0, "recibo": 0, "erros": 0}
    for tipo, kind in (("invoice", "invoice"), ("payment", "recibo")):
        chave = f"qbo_{tipo}_desde"
        desde = estado(con, chave)
        inicio = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        docs = qbo.documentos_sistema(tipo, desde=desde)
        for d in docs:
            ja = um(con, "SELECT * FROM library_docs WHERE kind=? AND ref=?", (kind, str(d["id"])))
            versao = f"{d.get('atualizado_em')}|{d.get('versao')}"
            if ja and ja["source_version"] == versao and ja["file_path"] and os.path.isfile(ja["file_path"]):
                continue
            if kind == "invoice":
                cid = _cliente_da_invoice(con, d["id"]) or _cliente_do_cliente_qbo(con, d.get("cliente_id"))
                titulo = f"Invoice {d.get('numero') or d['id']}"
                situacao = "paga" if d.get("total") and not float(d.get("saldo") or 0) else \
                           ("enviada" if d.get("email_status") == "EmailSent" else "aberta")
            else:
                cid = next((c for c in (_cliente_da_invoice(con, i) for i in d.get("invoices") or []) if c), None) \
                      or _cliente_do_cliente_qbo(con, d.get("cliente_id"))
                titulo = f"Payment {d.get('numero') or d['id']}"
                situacao = "recebido"
            campos = dict(client_id=cid, title=titulo, number=d.get("numero"), doc_date=d.get("data"),
                          amount=d.get("total"), status=situacao)
            try:
                try:
                    pdf = qbo.pdf_sistema(tipo, d["id"])
                except Exception:
                    if kind != "recibo":
                        raise
                    pdf = _recibo_pdf(d, d.get("cliente"))
                caminho = _gravar(kind, d["id"], pdf)
                _upsert(con, kind, d["id"], file_path=caminho, sha256=_sha(pdf), source_version=versao, error=None, **campos)
                feitos[kind] += 1
            except Exception as e:                                   # noqa: BLE001 — fica no documento
                _upsert(con, kind, d["id"], error=str(e)[:300], **campos)
                feitos["erros"] += 1
            con.commit()
        estado(con, chave, inicio)
        con.commit()
        log(f"biblioteca: {tipo}s do QuickBooks — {len(docs)} lidos")
    return feitos


# ------------------------------------------------------------------ contratos e waivers
def sincronizar_contratos_e_waivers(con, log=print):
    """O que o sistema já guarda (ou já sabe buscar): contratos e waivers assinados."""
    feitos = {"contrato": 0, "waiver": 0, "erros": 0}
    for k in todos(con, "SELECT * FROM contracts WHERE COALESCE(status,'completed')='completed'"):
        caminho = k["file_path"] if k["file_path"] and os.path.isfile(k["file_path"]) else None
        campos = dict(client_id=k["client_id"], title=k["title"] or "Contrato", doc_date=(k["signed_at"] or k["added_at"] or "")[:10],
                      status=k["status"] or "completed")
        try:
            if not caminho and k["envelope_id"]:
                ja = um(con, "SELECT file_path FROM library_docs WHERE kind='contrato' AND ref=?", (str(k["id"]),))
                if ja and ja["file_path"] and os.path.isfile(ja["file_path"]):
                    caminho = ja["file_path"]
                else:
                    from command_center.providers import modulo
                    caminho = _gravar("contrato", k["id"], modulo("docusign").baixar_documento_humano(k["envelope_id"]))
            if not caminho:
                continue
            sha = _sha_arquivo(caminho)
            _upsert(con, "contrato", k["id"], file_path=caminho, sha256=sha, source_version=sha, error=None, **campos)
            feitos["contrato"] += 1
        except Exception as e:                                       # noqa: BLE001
            _upsert(con, "contrato", k["id"], error=str(e)[:300], **campos)
            feitos["erros"] += 1
        con.commit()
    from command_center.api.motor import pdf_da_waiver
    for w in todos(con, "SELECT * FROM waivers WHERE status='completed' AND COALESCE(hidden,0)=0"):
        nome = w["minor_name"] or w["signer_name"] or "Waiver"
        campos = dict(client_id=w["client_id"], title=f"Waiver — {nome}", doc_date=(w["completed_at"] or "")[:10],
                      status="assinada" + (" na área do cliente" if w["source"] == "urace" else ""))
        try:
            caminho = pdf_da_waiver(con, w)
            sha = _sha_arquivo(caminho)
            _upsert(con, "waiver", w["id"], file_path=caminho, sha256=sha, source_version=sha, error=None, **campos)
            feitos["waiver"] += 1
        except Exception as e:                                       # noqa: BLE001
            _upsert(con, "waiver", w["id"], error=str(e)[:300], **campos)
            feitos["erros"] += 1
        con.commit()
    log(f"biblioteca: {feitos['contrato']} contratos e {feitos['waiver']} waivers")
    return feitos


# ------------------------------------------------------------------ histórico de serviço
def _historico_pdf(c, linhas):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b, pagesize=letter)
    nome = c["pilot_name"] or c["name"]
    cv.setTitle(f"Service history — {nome}")
    y = 0

    def topo():
        nonlocal y
        y = 730
        cv.setFont("Helvetica-Bold", 15); cv.drawString(72, y, f"URACE.US INC — Service history: {nome}"); y -= 22
        cv.setFont("Helvetica", 9); cv.drawString(72, y, f"Responsible: {c['name']}"); y -= 22
        cv.setFont("Helvetica-Bold", 9)
        cv.drawString(72, y, "Date"); cv.drawString(150, y, "Service"); cv.drawString(470, y, "Status"); y -= 14
        cv.setFont("Helvetica", 9)
    topo()
    for t in linhas:
        if y < 80:
            cv.showPage(); topo()
        cv.drawString(72, y, (t["due_on"] or "")[:10]); cv.drawString(150, y, (t["title"] or "")[:62])
        cv.drawString(470, y, "done" if t["status"] == "completed" else "scheduled"); y -= 13
    cv.showPage(); cv.save()
    return b.getvalue()


def sincronizar_historicos(con, log=print):
    """Um PDF por card, refeito só quando a lista de serviços daquele card muda."""
    n = 0
    for c in todos(con, "SELECT DISTINCT c.* FROM clients c JOIN tasks t ON t.client_id=c.id WHERE t.due_on IS NOT NULL"):
        linhas = todos(con, "SELECT due_on, title, status FROM tasks WHERE client_id=? AND due_on IS NOT NULL ORDER BY due_on DESC",
                       (c["id"],))
        versao = _sha(json.dumps([dict(x) for x in linhas], sort_keys=True).encode())
        ja = um(con, "SELECT source_version, file_path FROM library_docs WHERE kind='historico' AND ref=?", (str(c["id"]),))
        if ja and ja["source_version"] == versao and ja["file_path"] and os.path.isfile(ja["file_path"]):
            continue
        pdf = _historico_pdf(c, linhas)
        caminho = _gravar("historico", c["id"], pdf)
        _upsert(con, "historico", c["id"], client_id=c["id"], title=f"Histórico de serviço — {c['pilot_name'] or c['name']}",
                doc_date=(linhas[0]["due_on"] or "")[:10] if linhas else None, status=f"{len(linhas)} serviço(s)",
                file_path=caminho, sha256=_sha(pdf), source_version=versao, error=None)
        n += 1
        con.commit()
    log(f"biblioteca: {n} histórico(s) refeito(s)")
    return {"historico": n}


# ------------------------------------------------------------------ Drive
def _nome_pasta_cliente(con, client_id):
    if not client_id:
        return "Sem cliente"
    c = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (client_id,))
    nome = (c["pilot_name"] or c["name"]) if c else "Cliente"
    return re.sub(r"[\\/:*?\"<>|]+", " ", f"{nome} #{client_id}").strip()


def espelhar_no_drive(con, drive=None, log=print, limite=None):
    """Sobe ao Drive o que é novo ou mudou. Command Center/Clientes/<card>/<tipo>/arquivo.pdf."""
    from command_center.providers import drive as drv
    drive = drive or drv
    tok = drive.token()
    raiz = drive.pasta(tok, RAIZ_DRIVE)
    clientes = drive.pasta(tok, "Clientes", raiz)
    if estado(con, "drive_raiz") != clientes:
        estado(con, "drive_raiz", clientes)
    # compartilha só "Clientes": na raiz mora também o backup do banco, que é privado
    for email in COMPARTILHAR:
        chave = f"drive_compartilhado:{email}"
        if estado(con, chave) != clientes:
            drive.compartilhar(tok, clientes, email)
            estado(con, chave, clientes)
    con.commit()
    pastas = {}
    feitos = erros = 0
    pend = todos(con, """SELECT * FROM library_docs WHERE file_path IS NOT NULL AND sha256 IS NOT NULL
                           AND (drive_sha256 IS NULL OR drive_sha256 != sha256) ORDER BY id""")
    for d in pend[:limite] if limite else pend:
        if not os.path.isfile(d["file_path"]):
            continue
        try:
            nome_cli = _nome_pasta_cliente(con, d["client_id"])
            if nome_cli not in pastas:
                pastas[nome_cli] = drive.pasta(tok, nome_cli, clientes)
            chave = (nome_cli, d["kind"])
            if chave not in pastas:
                pastas[chave] = drive.pasta(tok, PASTA_KIND[d["kind"]], pastas[nome_cli])
            nome = re.sub(r"[\\/:*?\"<>|]+", " ", f"{d['doc_date'] or ''} {d['title']}".strip())[:150] + ".pdf"
            with open(d["file_path"], "rb") as f:
                dados = f.read()
            fid = drive.enviar(tok, nome, dados, pastas[chave], file_id=d["drive_file_id"])
            atualizar(con, "library_docs", d["id"], drive_file_id=fid, drive_sha256=d["sha256"], drive_error=None)
            feitos += 1
        except Exception as e:                                       # noqa: BLE001
            atualizar(con, "library_docs", d["id"], drive_error=str(e)[:300])
            erros += 1
        con.commit()
    log(f"biblioteca: {feitos} arquivo(s) no Drive, {erros} erro(s)")
    return {"drive": feitos, "drive_erros": erros}


# ------------------------------------------------------------------ a rodada diária
def rodada(con, qbo=None, drive=None, usar_drive=True, log=print):
    """Tudo, em ordem. Cada parte que falha (sem QuickBooks, sem Drive) não derruba as outras."""
    from command_center.providers import NaoConectado
    r = {"inicio": agora()}
    for nome, fn in (("qbo", lambda: sincronizar_qbo(con, qbo, log)),
                     ("documentos", lambda: sincronizar_contratos_e_waivers(con, log)),
                     ("historicos", lambda: sincronizar_historicos(con, log)),
                     ("drive", (lambda: espelhar_no_drive(con, drive, log)) if usar_drive else None)):
        if fn is None:
            continue
        try:
            r[nome] = fn()
        except NaoConectado as e:
            r[nome] = {"erro": f"não conectado: {e}"}
        except Exception as e:                                       # noqa: BLE001
            r[nome] = {"erro": str(e)[:300]}
        log(f"biblioteca: {nome} → {r[nome]}")
    r["fim"] = agora()
    estado(con, "ultima_rodada", json.dumps(r, ensure_ascii=False))
    con.commit()
    return r


# ------------------------------------------------------------------ o que a tela mostra
def listar(con, kind=None, q=None, client_id=None, limit=50, offset=0):
    onde, p = ["1=1"], []
    if kind:
        onde.append("d.kind=?"); p.append(kind)
    if client_id:
        onde.append("d.client_id=?"); p.append(client_id)
    if q:
        like = f"%{q.strip()}%"
        onde.append("(d.title LIKE ? OR d.number LIKE ? OR c.name LIKE ? OR c.pilot_name LIKE ?)"); p += [like] * 4
    w = " AND ".join(onde)
    total = um(con, f"SELECT COUNT(*) AS n FROM library_docs d LEFT JOIN clients c ON c.id=d.client_id WHERE {w}", tuple(p))["n"]
    itens = todos(con, f"""SELECT d.id, d.kind, d.client_id, d.title, d.number, d.doc_date, d.amount, d.status, d.error,
                                  d.drive_file_id IS NOT NULL AS no_drive, d.drive_error, d.file_path IS NOT NULL AS tem_pdf,
                                  d.updated_at, COALESCE(c.pilot_name, c.name) AS cliente
                             FROM library_docs d LEFT JOIN clients c ON c.id=d.client_id WHERE {w}
                            ORDER BY COALESCE(d.doc_date,'') DESC, d.id DESC LIMIT ? OFFSET ?""", (*p, limit, offset))
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


def resumo(con):
    contagem = {r["kind"]: r["n"] for r in todos(con, "SELECT kind, COUNT(*) AS n FROM library_docs GROUP BY kind")}
    ult = estado(con, "ultima_rodada")
    raiz = estado(con, "drive_raiz")
    return {"contagem": {k: contagem.get(k, 0) for k in KINDS},
            "sem_cliente": um(con, "SELECT COUNT(*) AS n FROM library_docs WHERE client_id IS NULL")["n"],
            "com_erro": um(con, "SELECT COUNT(*) AS n FROM library_docs WHERE error IS NOT NULL OR drive_error IS NOT NULL")["n"],
            "a_subir": um(con, "SELECT COUNT(*) AS n FROM library_docs WHERE sha256 IS NOT NULL AND (drive_sha256 IS NULL OR drive_sha256!=sha256)")["n"],
            "ultima_rodada": json.loads(ult) if ult else None,
            "drive": f"https://drive.google.com/drive/folders/{raiz}" if raiz else None,
            "compartilhado_com": COMPARTILHAR}
