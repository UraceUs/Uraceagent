"""Google Calendar de cada vendedor, nos dois sentidos (#220).

Dono, 13/10: *"na agenda de vendas, a possibilidade de cada usuário conseguir conectar com sua agenda
do Google Calendar, cada usuário de vendas"*. 14/10: *"conectar ao Google Calendar e aí coloca um
login com o Google, que aí ele consegue logar com a conta dele do Google"* — qualquer conta Google.

- **Login de cada um.** OAuth 2.0 Web (código de autorização + PKCE S256), `access_type=offline`,
  `prompt=consent`. Escopo `calendar.events` e `openid email` (só para mostrar qual conta ligou).
- **O cliente OAuth fica só na VPS**: `~/.urace/google-web-credentials.json` (o JSON que o Google
  Cloud baixa, chave `"web"`), ou o caminho de `CC_GOOGLE_WEB_CREDENTIALS`. Sem o arquivo, o botão
  aparece desligado e diz por quê; nada quebra.
- **Token cifrado** com a chave do Cofre (AES-GCM, `providers/cofre.py`); o campo cifrado leva o
  id do usuário como dado associado (o token de um não abre como de outro). Token nunca vai para
  log, auditoria ou resposta.
- **Painel → Google.** O retorno de cada oportunidade (`opportunities.next_at`) vira evento no
  calendário do closer conectado; mudou a data, o evento muda; concluiu, perdeu ou limpou o
  retorno, o evento sai. Só mexemos em evento que NÓS criamos: o id fica em
  `google_cal_events` e é só por ele que se altera ou remove.
- **Google → Painel.** A Agenda de vendas lê, só leitura, os eventos do Google da própria pessoa
  no período visto, para ela ver conflito. Os eventos que o painel criou não voltam duplicados.

Falha do Google nunca derruba a tela de vendas: a sincronia é "melhor esforço", grava o erro na
conexão e o laço automático (`rodar`) tenta de novo.

`CC_GOOGLE_BASE` aponta tudo para um Google falso (testes e end-to-end). Em produção fica vazio.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone

from command_center.db import agora, um, todos
from command_center.providers import cofre

ESCOPO_AGENDA = "https://www.googleapis.com/auth/calendar.events"
ESCOPOS = ("openid", "email", ESCOPO_AGENDA)
ESTADO_VALE_MIN = 10
MARCA = "urace_opp"            # extendedProperties.private: o evento é do painel
FECHADAS = ("GANHO", "PERDIDO")
TIMEOUT_S = 15


class NaoConfigurado(Exception):
    pass


class GoogleErro(Exception):
    def __init__(self, status, motivo):
        super().__init__(f"Google: HTTP {status} {motivo}")
        self.status, self.motivo = status, motivo


class ConexaoExpirada(Exception):
    pass


# --------------------------------------------------------------- endereços
def _base_falsa():
    return (os.environ.get("CC_GOOGLE_BASE") or "").rstrip("/")


def url_autorizar():
    return (_base_falsa() + "/auth") if _base_falsa() else "https://accounts.google.com/o/oauth2/v2/auth"


def url_token():
    return (_base_falsa() + "/token") if _base_falsa() else "https://oauth2.googleapis.com/token"


def url_revogar():
    return (_base_falsa() + "/revoke") if _base_falsa() else "https://oauth2.googleapis.com/revoke"


def url_agenda():
    return (_base_falsa() + "/calendar/v3") if _base_falsa() else "https://www.googleapis.com/calendar/v3"


def redirect_uri():
    """`https://ops.urace.us/ops/api/google/callback`: derivado do endereço principal do painel
    (`CC_PUBLIC_URL`), ou fixo por `CC_GOOGLE_REDIRECT_URI` quando precisar (end-to-end)."""
    fixo = (os.environ.get("CC_GOOGLE_REDIRECT_URI") or "").strip()
    if fixo:
        return fixo
    from command_center import enderecos
    return enderecos.principal() + "/ops/api/google/callback"


def caminho_credenciais():
    p = (os.environ.get("CC_GOOGLE_WEB_CREDENTIALS") or "").strip()
    if p:
        return os.path.expanduser(p)
    return os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "google-web-credentials.json")


def cliente():
    """(client_id, client_secret) do cliente OAuth Web. Lido a cada chamada: o gerente salva o
    arquivo na VPS e o botão liga sem reiniciar nada."""
    p = caminho_credenciais()
    if not os.path.isfile(p):
        raise NaoConfigurado("O gerente ainda não configurou o acesso ao Google: falta o arquivo do cliente "
                             "OAuth Web na VPS (Como usar › Vendas › Google Calendar).")
    try:
        with open(p, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        raise NaoConfigurado("O arquivo do cliente OAuth do Google na VPS não é um JSON válido.")
    if "web" not in dados:
        if "installed" in dados:
            raise NaoConfigurado("O arquivo na VPS é de um cliente OAuth do tipo Desktop; precisa ser "
                                 "do tipo Aplicativo da Web.")
        raise NaoConfigurado("O arquivo do cliente OAuth do Google na VPS não tem a chave \"web\".")
    web = dados["web"] or {}
    cid, segredo = (web.get("client_id") or "").strip(), (web.get("client_secret") or "").strip()
    if not cid or not segredo:
        raise NaoConfigurado("O arquivo do cliente OAuth do Google na VPS está sem client_id ou client_secret.")
    return cid, segredo


def configurado():
    """(ligado, motivo). Precisa do cliente OAuth Web e da chave do Cofre (que cifra os tokens)."""
    try:
        cliente()
    except NaoConfigurado as e:
        return False, str(e)
    ok, motivo = cofre.ligado()
    if not ok:
        return False, "O Google Calendar precisa da chave do cofre para guardar os tokens cifrados: " + motivo
    return True, None


# --------------------------------------------------------------- HTTP
def _http(metodo, url, token=None, json_corpo=None, form=None, params=None):
    """Uma chamada ao Google. Nunca põe token, código ou corpo em mensagem de erro."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    dados, tipo = None, None
    if form is not None:
        dados, tipo = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    elif json_corpo is not None:
        dados, tipo = json.dumps(json_corpo).encode(), "application/json"
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Accept", "application/json")
    if tipo:
        req.add_header("Content-Type", tipo)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            b = r.read()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        motivo = ""
        try:
            corpo = json.loads(e.read() or b"{}")
            err = corpo.get("error")
            motivo = err if isinstance(err, str) else (err or {}).get("status") or (err or {}).get("message") or ""
        except (ValueError, AttributeError):
            pass
        raise GoogleErro(e.code, str(motivo)[:80])
    except urllib.error.URLError as e:
        raise GoogleErro(0, f"sem conexão ({str(e.reason)[:60]})")


# --------------------------------------------------------------- state + PKCE
def _chave_estado():
    return hashlib.sha256(b"google-state:" + cofre._chave()).digest()


def _assinar(aleatorio, user_id):
    sig = hmac.new(_chave_estado(), f"{aleatorio}:{user_id}".encode(), hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _hash(v):
    return hashlib.sha256(v.encode()).hexdigest()


def iniciar(con, user_id):
    """Começa a conexão: devolve (url do Google, nonce do navegador). O `state` é assinado, de uso
    único e vale `ESTADO_VALE_MIN` minutos; o verificador PKCE fica só no servidor, cifrado. O
    nonce vai num cookie do navegador que começou: quem abrir o link em outro navegador volta
    recusado (ninguém liga a conta Google de outra pessoa ao seu usuário)."""
    cid, _ = cliente()
    aleatorio = secrets.token_urlsafe(24)
    state = f"{aleatorio}.{_assinar(aleatorio, user_id)}"
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    nonce = secrets.token_urlsafe(24)
    vence = (datetime.now(timezone.utc) + timedelta(minutes=ESTADO_VALE_MIN)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("""INSERT INTO google_oauth_states (state_hash, user_id, verifier_enc, nonce_hash, expires_at)
                   VALUES (?,?,?,?,?)""",
                (_hash(state), user_id, cofre.cifrar(verificador, f"google:{user_id}:pkce"), _hash(nonce), vence))
    url = url_autorizar() + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": " ".join(ESCOPOS), "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    return url, nonce


class EstadoInvalido(Exception):
    pass


def consumir_estado(con, state, nonce):
    """Confere e queima o `state`. Devolve (user_id, verificador). Qualquer coisa fora do lugar
    (assinatura, desconhecido, usado, vencido, outro navegador) é recusada."""
    state = state or ""
    if "." not in state:
        raise EstadoInvalido("state sem assinatura")
    aleatorio, assinatura = state.rsplit(".", 1)
    linha = um(con, "SELECT * FROM google_oauth_states WHERE state_hash=?", (_hash(state),))
    if not linha:
        raise EstadoInvalido("state desconhecido")
    if not hmac.compare_digest(assinatura, _assinar(aleatorio, linha["user_id"])):
        raise EstadoInvalido("assinatura do state não confere")
    if linha["used_at"]:
        raise EstadoInvalido("state já usado")
    con.execute("UPDATE google_oauth_states SET used_at=? WHERE state_hash=? AND used_at IS NULL", (agora(), linha["state_hash"]))
    if linha["expires_at"] <= agora():
        raise EstadoInvalido("state vencido")
    if not nonce or not hmac.compare_digest(_hash(nonce), linha["nonce_hash"]):
        raise EstadoInvalido("o retorno chegou em outro navegador")
    return linha["user_id"], cofre.decifrar(linha["verifier_enc"], f"google:{linha['user_id']}:pkce")


def _email_do_id_token(id_token):
    """O e-mail da conta, do id_token que veio direto do endpoint de token do Google (TLS): é só
    para mostrar qual conta ligou, não para autenticar ninguém."""
    try:
        meio = id_token.split(".")[1]
        dados = json.loads(base64.urlsafe_b64decode(meio + "=" * (-len(meio) % 4)))
        return (dados.get("email") or "").lower() or None
    except (IndexError, ValueError, AttributeError):
        return None


def _vence_em(segundos):
    return (datetime.now(timezone.utc) + timedelta(seconds=int(segundos or 3600))).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def trocar_codigo(con, user_id, codigo, verificador):
    """Código → tokens, guardados cifrados. Devolve o e-mail da conta Google."""
    cid, segredo = cliente()
    t = _http("POST", url_token(), form={
        "grant_type": "authorization_code", "code": codigo, "redirect_uri": redirect_uri(),
        "client_id": cid, "client_secret": segredo, "code_verifier": verificador})
    if not t.get("access_token"):
        raise GoogleErro(0, "o Google não devolveu o token")
    escopo = t.get("scope") or ""
    if ESCOPO_AGENDA not in escopo.split():
        raise GoogleErro(0, "a permissão de agenda não foi concedida")
    email = _email_do_id_token(t.get("id_token") or "")
    anterior = um(con, "SELECT refresh_enc FROM google_conexoes WHERE user_id=?", (user_id,))
    refresh = cofre.cifrar(t["refresh_token"], f"google:{user_id}:refresh") if t.get("refresh_token") else None
    if not refresh and anterior and anterior["refresh_enc"]:
        refresh = anterior["refresh_enc"]
    if not refresh:
        raise GoogleErro(0, "o Google não devolveu o token de renovação")
    agora_ = agora()
    con.execute("""INSERT INTO google_conexoes (user_id, google_email, status, scope, access_enc, refresh_enc,
                                                expires_at, key_fp, connected_at, updated_at, last_error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,NULL)
                   ON CONFLICT(user_id) DO UPDATE SET google_email=excluded.google_email, status='ativo',
                     scope=excluded.scope, access_enc=excluded.access_enc, refresh_enc=excluded.refresh_enc,
                     expires_at=excluded.expires_at, key_fp=excluded.key_fp, connected_at=excluded.connected_at,
                     updated_at=excluded.updated_at, last_error=NULL""",
                (user_id, email, "ativo", escopo, cofre.cifrar(t["access_token"], f"google:{user_id}:access"),
                 refresh, _vence_em(t.get("expires_in")), cofre.impressao(), agora_, agora_))
    return email


def conexao(con, user_id):
    return um(con, """SELECT user_id, google_email, status, scope, expires_at, key_fp, connected_at, updated_at,
                             last_sync_at, last_error FROM google_conexoes WHERE user_id=?""", (user_id,)) if user_id else None


def _anotar_erro(con, user_id, texto):
    con.execute("UPDATE google_conexoes SET last_error=?, updated_at=? WHERE user_id=?", (texto[:240] if texto else None, agora(), user_id))


def token_de(con, user_id):
    """Access token válido da pessoa (renova sozinho). `None` sem conexão ativa."""
    c = um(con, "SELECT * FROM google_conexoes WHERE user_id=? AND status='ativo'", (user_id,))
    if not c:
        return None
    if c["expires_at"] and c["expires_at"] > (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z"):
        return cofre.decifrar(c["access_enc"], f"google:{user_id}:access")
    cid, segredo = cliente()
    refresh = cofre.decifrar(c["refresh_enc"], f"google:{user_id}:refresh")
    try:
        t = _http("POST", url_token(), form={"grant_type": "refresh_token", "refresh_token": refresh,
                                             "client_id": cid, "client_secret": segredo})
    except GoogleErro as e:
        if e.status in (400, 401) and e.motivo in ("invalid_grant", "unauthorized_client", "invalid_client"):
            # revogado pela pessoa, senha trocada ou o modo "Testing" do Google (7 dias): o token morreu
            con.execute("""UPDATE google_conexoes SET status='expirado', access_enc=NULL, refresh_enc=NULL,
                           expires_at=NULL, updated_at=?, last_error=? WHERE user_id=?""",
                        (agora(), "O Google recusou a renovação: conecte de novo.", user_id))
            raise ConexaoExpirada("O Google recusou a renovação: conecte de novo.")
        raise
    con.execute("UPDATE google_conexoes SET access_enc=?, expires_at=?, updated_at=? WHERE user_id=?",
                (cofre.cifrar(t["access_token"], f"google:{user_id}:access"), _vence_em(t.get("expires_in")), agora(), user_id))
    return t["access_token"]


def desconectar(con, user_id):
    """Revoga no Google (melhor esforço) e apaga o token desta pessoa — o único "apagar" daqui, e é
    da própria pessoa. Os eventos que o painel já criou ficam no calendário dela."""
    c = um(con, "SELECT * FROM google_conexoes WHERE user_id=?", (user_id,))
    if not c:
        return False, None
    revogou = None
    try:
        tok = cofre.decifrar(c["refresh_enc"], f"google:{user_id}:refresh") if c["refresh_enc"] else None
        if tok:
            _http("POST", url_revogar(), form={"token": tok})
            revogou = True
    except Exception:                                     # noqa: BLE001 — revogar é melhor esforço
        revogou = False
    con.execute("DELETE FROM google_conexoes WHERE user_id=?", (user_id,))
    return True, revogou


# --------------------------------------------------------------- Painel → Google
def _instante(iso):
    """next_at → ("dt", datetime UTC) ou ("dia", date). Sem fuso = UTC, como o resto do painel."""
    t = str(iso or "").strip().replace("Z", "+00:00")
    if not t:
        return None
    if len(t) == 10:
        try:
            return "dia", datetime.fromisoformat(t).date()
        except ValueError:
            return None
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return "dt", d.astimezone(timezone.utc)


def duracao_min():
    try:
        return max(5, min(240, int(os.environ.get("CC_GOOGLE_EVENTO_MIN", "30"))))
    except ValueError:
        return 30


def corpo_evento(o):
    """O evento do retorno. Sem telefone nem e-mail do cliente: só o nome, o que fazer e o link."""
    from command_center import enderecos
    from command_center.api.agenda import FUSO
    q = _instante(o["next_at"])
    if not q:
        return None
    oque = (o.get("next_what") or "retorno").strip()
    titulo = f"URACE · {oque[:60]}: {(o.get('name') or '').strip()[:80]}"
    linhas = [f"Retorno da oportunidade #{o['id']} no painel de vendas da URACE."]
    if o.get("service"):
        linhas.append(f"Interesse: {o['service']}")
    linhas.append(f"{enderecos.principal()}/ops/sales/{o['id']}")
    linhas.append("Criado pelo painel: mude a data no painel, não aqui.")
    corpo = {"summary": titulo, "description": "\n".join(linhas),
             "extendedProperties": {"private": {MARCA: str(o["id"])}},
             "reminders": {"useDefault": True}}
    if q[0] == "dia":
        corpo["start"] = {"date": q[1].isoformat()}
        corpo["end"] = {"date": (q[1] + timedelta(days=1)).isoformat()}
    else:
        ini = q[1].astimezone(FUSO)
        fim = ini + timedelta(minutes=duracao_min())
        corpo["start"] = {"dateTime": ini.isoformat(), "timeZone": str(FUSO)}
        corpo["end"] = {"dateTime": fim.isoformat(), "timeZone": str(FUSO)}
    return corpo


def _assinatura(corpo):
    return hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _ev_url(event_id=None):
    base = url_agenda() + "/calendars/primary/events"
    return base + ("/" + urllib.parse.quote(event_id, safe="") if event_id else "")


def _remover_nosso(con, m):
    """Remove do Google o evento que o painel criou (pelo id guardado). Devolve o que fez."""
    c = um(con, "SELECT google_email FROM google_conexoes WHERE user_id=? AND status='ativo'", (m["user_id"],))
    if not c:
        return "sem_conexao"                   # fica 'ativo': quando a pessoa reconectar, sai
    if (c["google_email"] or "") != (m["google_email"] or ""):
        con.execute("UPDATE google_cal_events SET status='orfao', updated_at=? WHERE opp_id=?", (agora(), m["opp_id"]))
        return "outra_conta"
    tok = token_de(con, m["user_id"])
    try:
        _http("DELETE", _ev_url(m["event_id"]), token=tok)
    except GoogleErro as e:
        if e.status not in (404, 410):          # já não existe lá: está feito
            raise
    con.execute("UPDATE google_cal_events SET status='removido', updated_at=? WHERE opp_id=?", (agora(), m["opp_id"]))
    return "removido"


def sincronizar_opp(con, oid):
    """Deixa o Google igual ao painel para UMA oportunidade. Devolve o que fez:
    criado | atualizado | igual | removido | nada | sem_conexao | outra_conta."""
    o = um(con, "SELECT id, name, service, stage, next_at, next_what, closer_user_id FROM opportunities WHERE id=?", (oid,))
    m = um(con, "SELECT * FROM google_cal_events WHERE opp_id=? AND status='ativo'", (oid,))
    quer = bool(o and o["closer_user_id"] and o["next_at"] and o["stage"] not in FECHADAS and _instante(o["next_at"]))
    dono = o["closer_user_id"] if quer else None
    c = um(con, "SELECT google_email FROM google_conexoes WHERE user_id=? AND status='ativo'", (dono,)) if dono else None
    feito = "nada"
    if m and (not quer or m["user_id"] != dono or (c and (c["google_email"] or "") != (m["google_email"] or ""))):
        feito = _remover_nosso(con, m)
        m = None
    if not quer:
        return feito
    if not c:
        return "sem_conexao"
    corpo = corpo_evento(o)
    assin = _assinatura(corpo)
    if m and m["signature"] == assin:
        return "igual"
    tok = token_de(con, dono)
    novo = None
    if m:
        try:
            _http("PATCH", _ev_url(m["event_id"]), token=tok, json_corpo=corpo)
            novo, feito = m["event_id"], "atualizado"
        except GoogleErro as e:
            if e.status not in (404, 410):      # a pessoa apagou o evento lá: cria de novo
                raise
    if not novo:
        r = _http("POST", _ev_url(), token=tok, json_corpo=corpo)
        novo, feito = r.get("id"), "criado"
        if not novo:
            raise GoogleErro(0, "o Google não devolveu o id do evento")
    agora_ = agora()
    con.execute("""INSERT INTO google_cal_events (opp_id, user_id, google_email, event_id, signature, next_at, status,
                                                  created_at, updated_at)
                   VALUES (?,?,?,?,?,?,'ativo',?,?)
                   ON CONFLICT(opp_id) DO UPDATE SET user_id=excluded.user_id, google_email=excluded.google_email,
                     event_id=excluded.event_id, signature=excluded.signature, next_at=excluded.next_at,
                     status='ativo', updated_at=excluded.updated_at""",
                (oid, dono, c["google_email"], novo, assin, o["next_at"], agora_, agora_))
    return feito


def sincronizar_opp_seguro(con, oid):
    """Melhor esforço: o erro vai para a conexão do closer, nunca para a tela de vendas."""
    try:
        return sincronizar_opp(con, oid)
    except Exception as e:                                # noqa: BLE001
        o = um(con, "SELECT closer_user_id FROM opportunities WHERE id=?", (oid,))
        if o and o["closer_user_id"]:
            try:
                _anotar_erro(con, o["closer_user_id"], _texto_erro(e))
            except Exception:                             # noqa: BLE001
                pass
        return "erro"


def _texto_erro(e):
    if isinstance(e, (GoogleErro, ConexaoExpirada, NaoConfigurado)):
        return str(e)
    if isinstance(e, cofre.ChaveErrada):
        return "O token foi guardado com outra chave do cofre: conecte de novo."
    return f"{type(e).__name__}"


def alguem_conectado(con):
    return bool(um(con, "SELECT 1 AS x FROM google_conexoes WHERE status='ativo' LIMIT 1"))


def sincronizar_em_segundo_plano(oid):
    """Para `BackgroundTasks`: a resposta da tela sai antes; abre a própria conexão do banco."""
    from command_center.db import conectar
    con = conectar()
    try:
        if alguem_conectado(con) or um(con, "SELECT 1 AS x FROM google_cal_events WHERE opp_id=? AND status='ativo'", (oid,)):
            sincronizar_opp_seguro(con, oid)
    finally:
        con.close()


def sincronizar_usuario(con, user_id):
    """Todos os retornos da pessoa (e os eventos nossos que sobraram dela). Contagem por resultado."""
    ids = {r["id"] for r in todos(con, """SELECT id FROM opportunities WHERE closer_user_id=? AND next_at IS NOT NULL
                                          AND stage NOT IN ('GANHO','PERDIDO')""", (user_id,))}
    ids |= {r["opp_id"] for r in todos(con, "SELECT opp_id FROM google_cal_events WHERE user_id=? AND status='ativo'", (user_id,))}
    conta = {}
    erro = None
    for oid in sorted(ids):
        try:
            r = sincronizar_opp(con, oid)
        except ConexaoExpirada as e:
            erro = str(e)
            break
        except Exception as e:                            # noqa: BLE001
            r, erro = "erro", _texto_erro(e)
        conta[r] = conta.get(r, 0) + 1
    con.execute("UPDATE google_conexoes SET last_sync_at=?, last_error=?, updated_at=? WHERE user_id=?",
                (agora(), erro, agora(), user_id))
    return conta, erro


def rodar(con):
    """Laço automático: acerta o Google de cada pessoa conectada. Pega o que falhou na hora."""
    if not configurado()[0]:
        return {}
    feito = {}
    for c in todos(con, "SELECT user_id FROM google_conexoes WHERE status='ativo'"):
        conta, _ = sincronizar_usuario(con, c["user_id"])
        for k, v in conta.items():
            if k not in ("igual", "nada"):
                feito[k] = feito.get(k, 0) + v
    return feito


# --------------------------------------------------------------- Google → Painel
def eventos(con, user_id, de, ate):
    """Os eventos do Google da pessoa entre dois dias (AAAA-MM-DD, na Florida), só leitura. Os que o
    painel criou ficam de fora (já aparecem como retorno)."""
    from command_center.api.agenda import FUSO
    tok = token_de(con, user_id)
    if not tok:
        return None
    ini = datetime.combine(de, time(0, 0), tzinfo=FUSO)
    fim = datetime.combine(ate + timedelta(days=1), time(0, 0), tzinfo=FUSO)
    nossos = {r["event_id"] for r in todos(con, "SELECT event_id FROM google_cal_events WHERE user_id=?", (user_id,))}
    saida, pagina = [], None
    for _ in range(4):                                     # até 1000 eventos no período
        params = {"timeMin": ini.isoformat(), "timeMax": fim.isoformat(), "singleEvents": "true",
                  "orderBy": "startTime", "maxResults": "250", "timeZone": str(FUSO)}
        if pagina:
            params["pageToken"] = pagina
        r = _http("GET", _ev_url(), token=tok, params=params)
        for ev in r.get("items") or []:
            if ev.get("status") == "cancelled" or ev.get("id") in nossos:
                continue
            if ((ev.get("extendedProperties") or {}).get("private") or {}).get(MARCA):
                continue
            eu = [a for a in ev.get("attendees") or [] if a.get("self")]
            if eu and eu[0].get("responseStatus") == "declined":
                continue
            s, e = ev.get("start") or {}, ev.get("end") or {}
            dia_todo = "date" in s and "dateTime" not in s
            saida.append({"id": hashlib.sha256(str(ev.get("id")).encode()).hexdigest()[:12],
                          "titulo": (ev.get("summary") or "").strip()[:120] or None,
                          "inicio": s.get("dateTime") or s.get("date"), "fim": e.get("dateTime") or e.get("date"),
                          "dia_todo": dia_todo, "ocupado": ev.get("transparency") != "transparent"})
        pagina = r.get("nextPageToken")
        if not pagina:
            break
    return saida


# --------------------------------------------------------------- log
_MASCARA = re.compile(r"([?&](?:code|state)=)[^&\s\"']+")


def mascarar(texto):
    return _MASCARA.sub(r"\1***", texto) if isinstance(texto, str) else texto
