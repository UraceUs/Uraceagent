"""Telefonia (Dialpad): espelho das ligações do número da empresa.

Contexto do dono (18/09/2026): a URACE tem **um número de empresa** que recebe todas as
ligações, o plano já dá API e Dialpad Ai, e o **aviso de consentimento já toca** na
chamada — então gravação e transcrição entram desde o começo (a Flórida exige
consentimento de todas as partes; o aviso é o que resolve isso, e a decisão foi dele).

Como funciona, igual ao Kommo:

  Dialpad → webhook `/ops/api/dialpad/webhook?key=…` → espelho em `calls`
          → casa pelo telefone com cliente, oportunidade ou lead
          → ligação na linha do tempo da venda, e perdida virando "Precisa de atenção"

O evento pode chegar de duas formas, e as duas são aceitas: **JSON cru** ou **JWT
assinado em HS256** (quando o webhook é criado com segredo no Dialpad). A verificação é
feita à mão com `hmac`, para não trazer dependência nova.

**O nome exato de cada campo do evento é confirmado no primeiro evento real**: o site de
desenvolvedores do Dialpad não é alcançável daqui, então o receptor guarda o evento como
chegou (`dialpad-webhook-ultimo.json`, do mesmo jeito que o do Kommo) e `_normaliza`
aceita as variações conhecidas de nome. Campo novo nunca se perde: o evento inteiro fica
em `calls.raw`.

Nada aqui liga para ninguém sozinho: `dialpad_ligar` é ação de confirmação obrigatória, e
o botão de ligar só existe para quem tem acesso de operador.
"""
import base64
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/api/dialpad", tags=["dialpad"])
SISTEMA = "dialpad"
ENV = "~/.urace/dialpad.env"

# estados que o Dialpad manda no ciclo da ligação; guardamos o último de cada ligação
FINAIS = ("hangup", "completed", "ended", "missed", "voicemail", "no_answer", "rejected", "failed")


# --------------------------------------------------------------------- credenciais
def _carrega_env():
    """Lê `~/.urace/dialpad.env` se o serviço subiu sem o EnvironmentFile. Segredo nunca
    vive no repositório — só no VPS."""
    caminho = os.path.expanduser(os.environ.get("DIALPAD_ENV", ENV))
    try:
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def _cfg(nome, padrao=""):
    if not os.environ.get(nome):
        _carrega_env()
    return os.environ.get(nome, padrao)


def _chave_hook():
    """Chave na URL do webhook (nossa), para ninguém postar evento de fora."""
    return _cfg("DIALPAD_HOOK_KEY")


def _segredo():
    """Segredo compartilhado com o Dialpad: quando existe, o evento vem em JWT HS256."""
    return _cfg("DIALPAD_HOOK_SECRET")


# --------------------------------------------------------------------- JWT (HS256)
def _b64(dado: str) -> bytes:
    return base64.urlsafe_b64decode(dado + "=" * (-len(dado) % 4))


def abre_jwt(token: str, segredo: str):
    """Payload de um JWT HS256 com a assinatura conferida. Erro de assinatura levanta
    ValueError — evento não verificado não entra no espelho."""
    partes = token.strip().split(".")
    if len(partes) != 3:
        raise ValueError("não é um JWT")
    cab, corpo, assinatura = partes
    alg = (json.loads(_b64(cab)) or {}).get("alg")
    if alg != "HS256":
        raise ValueError(f"algoritmo {alg} não aceito")
    esperada = hmac.new(segredo.encode(), f"{cab}.{corpo}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(assinatura), esperada):
        raise ValueError("assinatura não confere")
    return json.loads(_b64(corpo))


# --------------------------------------------------------------------- normalização
def _primeiro(d: dict, *nomes, padrao=None):
    for n in nomes:
        if isinstance(d.get(n), (str, int, float)) and d.get(n) not in ("", None):
            return d[n]
    return padrao


def _quando(v):
    """Dialpad manda milissegundos desde a época; ISO também é aceito."""
    if v in (None, ""):
        return None
    try:
        n = int(v)
        if n > 1e12:      # ms
            n = n / 1000
        return datetime.fromtimestamp(n, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return str(v)[:19] or None


def so_digitos(tel):
    return "".join(c for c in str(tel or "") if c.isdigit())


def _normaliza(ev: dict) -> dict:
    """Evento do Dialpad → colunas do espelho. Aceita as variações de nome conhecidas; o
    que não for reconhecido continua inteiro em `raw`."""
    if not isinstance(ev, dict):
        return {}
    call = ev.get("call") if isinstance(ev.get("call"), dict) else ev
    estado = str(_primeiro(call, "state", "call_state", "event", padrao="") or "").lower()
    direcao_bruta = str(_primeiro(call, "direction", "call_direction", padrao="") or "").lower()
    contato = call.get("contact") if isinstance(call.get("contact"), dict) else {}
    alvo = call.get("target") if isinstance(call.get("target"), dict) else {}
    gravacao = call.get("recording_url") or call.get("recording_urls") or call.get("call_recording_ids")
    if isinstance(gravacao, list):
        gravacao = gravacao[0] if gravacao else None
    segundos = _primeiro(call, "duration", "duration_seconds", "total_duration")
    try:
        segundos = int(float(segundos)) if segundos not in (None, "") else None
        if segundos and segundos > 100000:     # veio em ms
            segundos = segundos // 1000
    except (TypeError, ValueError):
        segundos = None
    return {
        "external_id": str(_primeiro(call, "call_id", "id", padrao="") or "") or None,
        "direction": "saida" if direcao_bruta.startswith("out") else "entrada" if direcao_bruta else None,
        "state": estado or None,
        "external_number": str(_primeiro(call, "external_number", "from_number", "contact_number", padrao="") or "") or None,
        "internal_number": str(_primeiro(call, "internal_number", "to_number", "target_number", padrao="") or "") or None,
        "contact_name": (contato.get("name") if isinstance(contato, dict) else None) or _primeiro(call, "contact_name"),
        "who": (alvo.get("name") or alvo.get("email") if isinstance(alvo, dict) else None) or _primeiro(call, "operator_name", "user_name"),
        "started_at": _quando(_primeiro(call, "date_started", "started_at", "date_connected")),
        "ended_at": _quando(_primeiro(call, "date_ended", "ended_at", "date_rang")),
        "seconds": segundos,
        "answered": 1 if (_primeiro(call, "date_connected") or estado in ("connected", "hangup", "completed", "ended")) and estado not in ("missed", "voicemail", "no_answer", "rejected") else 0,
        "voicemail": 1 if "voicemail" in estado else 0,
        "recording_url": str(gravacao) if gravacao else None,
        "transcript": _primeiro(call, "transcription_text", "transcript", "transcript_text"),
    }


# --------------------------------------------------------------------- casamento
def liga_a_quem(con, telefone):
    """Quem é o número de fora: cliente, oportunidade em aberto ou lead do Kommo.
    Compara pelos últimos 9 dígitos, que sobrevive a +1, 001 e formatação."""
    tel = so_digitos(telefone)
    if not tel or len(tel) < 7:
        return {}
    fim = tel[-9:]
    achado = {}
    from command_center.providers import identidade
    c, _ = identidade.acha_pessoa(con, telefone=telefone)
    if c:
        achado["client_id"] = c["id"]
    for o in todos(con, """SELECT id, phone FROM opportunities WHERE phone IS NOT NULL
                           AND stage NOT IN ('GANHO','PERDIDO') ORDER BY updated_at DESC"""):
        if so_digitos(o["phone"])[-9:] == fim:
            achado["opportunity_id"] = o["id"]
            break
    for l in todos(con, "SELECT id, contact_phone FROM crm_leads WHERE contact_phone IS NOT NULL ORDER BY id DESC LIMIT 400"):
        if so_digitos(l["contact_phone"])[-9:] == fim:
            achado["lead_id"] = l["id"]
            break
    return achado


def _na_venda(con, oid, dados):
    """Ligação registrada sozinha na linha do tempo da oportunidade (o closer só diz o
    resultado e o próximo passo)."""
    from command_center.api import vendas
    minutos = round((dados.get("seconds") or 0) / 60) or None
    titulo = ("Ligou (Dialpad)" if dados.get("direction") == "saida" else "Recebeu ligação (Dialpad)")
    if not dados.get("answered"):
        titulo = "Não atendeu (Dialpad)" if dados.get("direction") == "saida" else "Ligação perdida (Dialpad)"
    elif minutos:
        titulo += f" · {minutos} min"
    corpo = (dados.get("transcript") or "").strip() or None
    vendas._ev(con, oid, "call", titulo, corpo, "dialpad", 1 if dados.get("answered") else 0)
    atualizar(con, "opportunities", oid, updated_at=agora())


# --------------------------------------------------------------------- webhook
@r.post("/webhook")
async def webhook(request: Request, con: sqlite3.Connection = Depends(get_db)):
    """Evento de ligação do Dialpad. JSON cru ou JWT assinado (HS256), os dois aceitos.

    A chave na URL (`?key=`) é a nossa; o segredo do JWT é o combinado com o Dialpad.
    Sem chave configurada a rota recusa — para não existir porta aberta sem querer."""
    chave = _chave_hook()
    if not chave:
        raise HTTPException(409, f"DIALPAD_HOOK_KEY ainda não está em {ENV}. Veja docs/adminai/dialpad-conexao.md.")
    if request.query_params.get("key") != chave:
        raise HTTPException(403, "chave do webhook não confere")

    bruto = (await request.body()).decode("utf-8", "replace").strip()
    if not bruto:
        raise HTTPException(400, "corpo vazio")
    ev = None
    if bruto.count(".") == 2 and not bruto.startswith("{"):
        segredo = _segredo()
        if not segredo:
            raise HTTPException(409, f"evento assinado chegou, mas DIALPAD_HOOK_SECRET não está em {ENV}.")
        try:
            ev = abre_jwt(bruto, segredo)
        except ValueError as e:
            raise HTTPException(403, f"JWT do Dialpad recusado: {e}")
    else:
        try:
            ev = json.loads(bruto)
        except json.JSONDecodeError:
            raise HTTPException(400, "corpo não é JSON nem JWT")

    # o evento como chegou, para conferir nome de campo com a fonte real (igual ao Kommo)
    try:
        from command_center.api.sistema import _dir
        (_dir() / "dialpad-webhook-ultimo.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

    dados = _normaliza(ev)
    if not dados.get("external_id"):
        auditar(con, "dialpad.webhook", "dialpad", detail={"ignorado": "evento sem call_id"})
        con.commit()
        return {"ok": True, "ignorado": "sem call_id"}

    dados["raw"] = json.dumps(ev, ensure_ascii=False)
    achado = liga_a_quem(con, dados.get("external_number"))
    ja = um(con, "SELECT * FROM calls WHERE external_id = ?", (dados["external_id"],))
    final = (dados.get("state") or "") in FINAIS
    if ja:
        campos = {k: v for k, v in dados.items() if v not in (None, "")}
        campos.update({k: v for k, v in achado.items() if not ja[k]})
        atualizar(con, "calls", ja["id"], **campos)
        cid = ja["id"]
    else:
        cid = inserir(con, "calls", **{**dados, **achado, "at": agora()})

    # a linha do tempo da venda recebe a ligação uma vez, quando ela termina
    novo_final = final and not (ja and (ja["state"] or "") in FINAIS)
    if novo_final and achado.get("opportunity_id"):
        _na_venda(con, achado["opportunity_id"], {**dados, **achado})
    auditar(con, "dialpad.webhook", "dialpad", entity_type="call", entity_id=cid,
            detail={"estado": dados.get("state"), "direcao": dados.get("direction"), **achado})
    con.commit()
    return {"ok": True, "id": cid, "ligado_a": achado or None}


# --------------------------------------------------------------------- leitura
@r.get("/status")
def status(u=Depends(auth.exige("OPERATOR")), con: sqlite3.Connection = Depends(get_db)):
    """Conectado ou não, a URL para colar no Dialpad e o último evento que chegou.
    Sem credencial NÃO inventa nada: diz que falta configurar."""
    chave, segredo, api = _chave_hook(), _segredo(), _cfg("DIALPAD_API_KEY")
    host = os.environ.get("CC_HOST", "urace-bridge.duckdns.org")
    ult = um(con, "SELECT at AS quando FROM audit_logs WHERE event='dialpad.webhook' ORDER BY id DESC LIMIT 1")
    n = um(con, "SELECT COUNT(*) AS n FROM calls")
    return {
        "connected": bool(chave and api),
        "falta": [x for x, v in (("DIALPAD_HOOK_KEY", chave), ("DIALPAD_HOOK_SECRET", segredo), ("DIALPAD_API_KEY", api)) if not v],
        "webhook_url": (f"https://{host}/ops/api/dialpad/webhook?key={chave}" if chave else None),
        "assinado": bool(segredo),
        "ultimo_evento": ult["quando"] if ult else None,
        "ligacoes": n["n"],
        "env": ENV,
    }


@r.get("/calls")
def lista(dias: int = 14, so_perdidas: int = 0, u=Depends(auth.exige("OPERATOR")),
          con: sqlite3.Connection = Depends(get_db)):
    """Espelho das ligações, mais recente primeiro."""
    corte = (datetime.utcnow() - timedelta(days=max(1, min(dias, 120)))).strftime("%Y-%m-%dT%H:%M:%S")
    sql = """SELECT c.*, cl.name AS client_name, o.name AS opp_name
             FROM calls c LEFT JOIN clients cl ON cl.id = c.client_id
             LEFT JOIN opportunities o ON o.id = c.opportunity_id
             WHERE COALESCE(c.started_at, c.at) >= ?"""
    if so_perdidas:
        sql += " AND c.answered = 0"
    return {"calls": todos(con, sql + " ORDER BY COALESCE(c.started_at, c.at) DESC LIMIT 300", (corte,))}


class TratarIn(BaseModel):
    handled: bool = True


@r.post("/calls/{cid}/handled")
def tratar(cid: int, dados: TratarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
           con: sqlite3.Connection = Depends(get_db)):
    """Ligação perdida já resolvida: sai de 'Precisa de atenção'."""
    if not um(con, "SELECT id FROM calls WHERE id = ?", (cid,)):
        raise HTTPException(404, "ligação não encontrada")
    atualizar(con, "calls", cid, handled=1 if dados.handled else 0)
    auditar(con, "dialpad.handled", f"user:{u['id']}", user_id=u["id"], entity_type="call", entity_id=cid,
            detail={"handled": dados.handled}, ip=auth._ip(request))
    con.commit()
    return {"ok": True}


# --------------------------------------------------------------------- discar
class LigarIn(BaseModel):
    numero: str
    opportunity_id: int | None = None
    client_id: int | None = None


@r.post("/call")
def ligar(dados: LigarIn, request: Request, u=Depends(auth.exige("OPERATOR")),
          con: sqlite3.Connection = Depends(get_db)):
    """Botão "Ligar": o Dialpad toca no aparelho de quem clicou e disca para o número.

    A IA nunca chega aqui sozinha — `dialpad_ligar` é confirmação obrigatória e a chamada
    é sempre de uma pessoa logada. O `user_id` do Dialpad de cada pessoa vem de
    `DIALPAD_USER_<id do usuário no painel>`, com `DIALPAD_USER_ID` como padrão."""
    api = _cfg("DIALPAD_API_KEY")
    if not api:
        raise HTTPException(409, f"DIALPAD_API_KEY ainda não está em {ENV}.")
    quem = _cfg(f"DIALPAD_USER_{u['id']}") or _cfg("DIALPAD_USER_ID")
    if not quem:
        raise HTTPException(409, f"Falta o seu usuário do Dialpad em {ENV} (DIALPAD_USER_{u['id']} ou DIALPAD_USER_ID).")
    tel = dados.numero.strip()
    if len(so_digitos(tel)) < 7:
        raise HTTPException(400, "número incompleto")

    import urllib.error
    import urllib.request
    corpo = json.dumps({"user_id": quem, "phone_number": tel, "group_id": None}).encode()
    req = urllib.request.Request("https://dialpad.com/api/v2/call", data=corpo, method="POST",
                                 headers={"Authorization": f"Bearer {api}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            saida = json.loads(res.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        raise HTTPException(502, f"Dialpad recusou ({e.code}): {detalhe}")
    except OSError as e:
        raise HTTPException(502, f"Dialpad fora de alcance: {e}")
    auditar(con, "dialpad.ligar", f"user:{u['id']}", user_id=u["id"],
            entity_type="opportunity" if dados.opportunity_id else "client",
            entity_id=dados.opportunity_id or dados.client_id,
            detail={"numero": tel}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, "dialpad": saida}
