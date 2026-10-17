"""Trilha de eventos da waiver nativa, append-only e encadeada (#111, lacuna C-3).

O certificado do DocuSign traz enviado, visto e assinado. Num "não fui eu", a sequência de passos com hora e IP
é o que mostra o processo (*Espejo v. So. Cal. Permanente*, 2016). Aqui cada passo é uma linha de
`waiver_events`, que o banco não deixa mudar nem apagar (trigger, como no `audit_logs`), e cada linha leva o
hash da anterior: `hash = sha256(prev_hash | json canônico da linha)`. `verificar` refaz a cadeia e acha a
primeira linha mexida.

- **Antes de assinar** (vão para o certificado dentro do PDF selado): convite enviado, abriu a tela, recebeu o
  PDF, leu todas as páginas, código enviado, código confirmado, revisou e assinou. "Abriu a tela" e "leu todas
  as páginas" só a tela sabe: chegam por `POST /drivers/{pid}/waiver/events` e `POST /invite/{token}/events`,
  com lista fechada (`DA_TELA`) e limite de chamadas; ficam marcados `source='client'`.
- Os eventos de antes se ligam à waiver pelo **escopo** (conta + piloto + modelo desde a última assinatura da
  conta, nas últimas 24 h; ou o convite inteiro). O `signed` lista em `detail.covers` os ids que cobre: nada
  precisa de UPDATE.
- **Depois de assinar** (PDF baixado, anulada; e-mail da cópia, conferência no balcão e pacote de prova nas
  próximas tarefas) não entram no PDF selado, que não muda: ficam aqui, com o `waiver_id`, e no painel.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from command_center.db import agora, todos, transacao, um

# evento → como sai no certificado (inglês: é o que o cliente lê) e no painel
EVENTOS = {
    "invite_sent": "Invitation link emailed to the signer",
    "screen_opened": "Signing page opened",
    "pdf_delivered": "Document (PDF) delivered to the signer",
    "all_pages_viewed": "Every page of the document shown on screen",
    "code_sent": "One-time code emailed to the signer",
    "code_verified": "One-time code confirmed",
    "reviewed": "Signer confirmed the boxes, the relationship and the typed name",
    "signed": "Signed",
    "copy_emailed": "Signed copy emailed to the signer",
    "id_checked": "Photo ID checked at the track",
    "voided": "Voided by URACE",
    "downloaded": "Signed PDF downloaded",
    "evidence_exported": "Evidence package exported",
}
ANTES = ("invite_sent", "screen_opened", "pdf_delivered", "all_pages_viewed", "code_sent", "code_verified", "reviewed")
DEPOIS = ("copy_emailed", "id_checked", "voided", "downloaded", "evidence_exported")
DA_TELA = {"screen_opened", "all_pages_viewed"}           # o que só o navegador sabe
FLUXOS = ("account", "invite", "staff")
JANELA_HORAS = 24                                        # a mesma da leitura (#107)
TELA_POR_HORA = 30                                       # eventos da tela por conta (ou convite) por hora
_CAMPOS = ("at", "flow", "account_id", "invite_id", "pilot_id", "client_id", "kind", "template_version_id", "waiver_id",
           "signature_id", "event", "source", "ip", "user_agent", "detail")


class Demais(Exception):
    """A tela mandou eventos demais na última hora (a rota devolve 429)."""


def _canonico(linha):
    return json.dumps({k: linha.get(k) for k in _CAMPOS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(anterior, linha):
    return hashlib.sha256(f"{anterior or ''}|{_canonico(linha)}".encode("utf-8")).hexdigest()


def registrar(con, evento, fluxo, source="server", ip=None, user_agent=None, detail=None, **ids):
    """Acrescenta um evento na ponta da cadeia. `ids`: account_id, invite_id, pilot_id, client_id, kind,
    template_version_id, waiver_id, signature_id. Fora de transação, abre uma IMMEDIATE: ler a ponta e
    gravar não deixam outra gravação entrar no meio (a cadeia não bifurca)."""
    if evento not in EVENTOS:
        raise ValueError(f"evento desconhecido: {evento}")
    if fluxo not in FLUXOS or source not in ("server", "client"):
        raise ValueError("fluxo ou origem inválidos")
    desconhecidos = set(ids) - set(_CAMPOS)
    if desconhecidos:
        raise ValueError(f"campos desconhecidos: {sorted(desconhecidos)}")
    linha = {k: None for k in _CAMPOS}
    linha.update(ids)
    linha.update(at=agora(), flow=fluxo, event=evento, source=source, ip=ip, user_agent=(user_agent or "")[:300] or None,
                 detail=json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail is not None else None)

    def gravar():
        ponta = um(con, "SELECT hash FROM waiver_events ORDER BY id DESC LIMIT 1")
        linha["prev_hash"] = ponta["hash"] if ponta else None
        linha["hash"] = _hash(linha["prev_hash"], linha)
        cur = con.execute(f"INSERT INTO waiver_events ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
                          tuple(linha.values()))
        return {"id": cur.lastrowid, **linha}

    if con.in_transaction:
        return gravar()
    with transacao(con, imediata=True):
        return gravar()


def verificar(con):
    """Refaz a cadeia inteira: {ok, total, first_bad_id, last_hash}. Uma linha mexida (ou tirada do meio)
    quebra o hash dela ou o `prev_hash` da seguinte."""
    anterior, n = None, 0
    for r in con.execute(f"SELECT id, prev_hash, hash, {', '.join(_CAMPOS)} FROM waiver_events ORDER BY id"):
        r = dict(r)
        n += 1
        if r["prev_hash"] != anterior or _hash(anterior, r) != r["hash"]:
            return {"ok": False, "total": None, "first_bad_id": r["id"], "last_hash": None}
        anterior = r["hash"]
    return {"ok": True, "total": n, "first_bad_id": None, "last_hash": anterior}


# ------------------------------------------------------------------ escopo: o que a assinatura cobre
def cobertos(con, account_id=None, pilot_id=None, kind=None, invite_id=None):
    """Os eventos de antes de assinar que esta assinatura cobre, na ordem.
    Convite: todos os do convite. Conta: os desta conta desde a última assinatura dela (no máximo 24 h),
    do piloto (ou sem piloto, como o código) e do modelo (ou sem modelo)."""
    marcas = ",".join("?" * len(ANTES))
    if invite_id is not None:
        return todos(con, f"SELECT * FROM waiver_events WHERE invite_id=? AND event IN ({marcas}) ORDER BY id",
                     (invite_id, *ANTES))
    ult = um(con, "SELECT MAX(id) AS id FROM waiver_events WHERE account_id=? AND event='signed'", (account_id,))["id"] or 0
    desde = (datetime.now(timezone.utc) - timedelta(hours=JANELA_HORAS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return todos(con, f"""SELECT * FROM waiver_events WHERE account_id=? AND id > ? AND at >= ? AND event IN ({marcas})
                          AND (pilot_id IS NULL OR pilot_id=?) AND (kind IS NULL OR kind=?) ORDER BY id""",
                 (account_id, ult, desde, *ANTES, pilot_id, kind))


def para_o_certificado(eventos, fuso):
    """O que o certificado imprime de cada evento: hora na Flórida e em UTC, o que foi, quem registrou, IP e aparelho."""
    saida = []
    for e in eventos:
        t = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
        saida.append({"id": e["id"], "event": e["event"], "label": EVENTOS[e["event"]], "source": e["source"],
                      "at_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "at_local": t.astimezone(fuso).strftime("%Y-%m-%d %H:%M:%S %Z"),
                      "ip": e["ip"], "user_agent": e["user_agent"], "hash": e["hash"]})
    return saida


def da_waiver(con, wid):
    """A trilha de uma waiver: os eventos que o `signed` cobre, o próprio `signed` e o que veio depois."""
    s = um(con, "SELECT * FROM waiver_events WHERE waiver_id=? AND event='signed' ORDER BY id LIMIT 1", (wid,))
    antes = []
    if s:
        ids = (json.loads(s["detail"] or "{}").get("covers") or [])
        if ids:
            antes = todos(con, f"SELECT * FROM waiver_events WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", tuple(ids))
    depois = todos(con, "SELECT * FROM waiver_events WHERE waiver_id=? AND event<>'signed' ORDER BY id", (wid,))
    saida = []
    for fase, lista in (("before", antes), ("signed", [s] if s else []), ("after", depois)):
        for e in lista:
            saida.append({**e, "detail": json.loads(e["detail"]) if e["detail"] else None, "phase": fase,
                          "label": EVENTOS.get(e["event"], e["event"])})
    return saida


def _na_ultima_hora(con, fluxo, ids, source, evento=None):
    escopo, valor = ("invite_id", ids["invite_id"]) if fluxo == "invite" else ("account_id", ids["account_id"])
    desde = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return um(con, f"""SELECT COUNT(*) AS n FROM waiver_events WHERE {escopo}=? AND source=? AND at >= ?
                       AND (? IS NULL OR event=?)""", (valor, source, desde, evento, evento))["n"]


def da_tela(con, evento, fluxo, ip=None, user_agent=None, detail=None, **ids):
    """Um evento que a tela relatou: só os da lista fechada e no máximo `TELA_POR_HORA` por conta (ou convite)."""
    if evento not in DA_TELA:
        raise ValueError(f"a tela não registra este evento: {evento}")
    if _na_ultima_hora(con, fluxo, ids, "client") >= TELA_POR_HORA:
        raise Demais("Too many events from this page. Try again later.")
    return registrar(con, evento, fluxo, source="client", ip=ip, user_agent=user_agent, detail=detail, **ids)


def abriu_pelo_link(con, ip=None, user_agent=None, detail=None, **ids):
    """O convite aberto (o servidor vê o GET do link). Recarregar em loop não enche a trilha: passou de
    `TELA_POR_HORA` aberturas na última hora, a página abre e a trilha não repete."""
    if _na_ultima_hora(con, "invite", ids, "server", "screen_opened") >= TELA_POR_HORA:
        return None
    return registrar(con, "screen_opened", "invite", ip=ip, user_agent=user_agent, detail=detail, **ids)
