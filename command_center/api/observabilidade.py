"""Observabilidade do painel (issue #17): o que o servidor e o navegador estão vivendo.

- **Toda requisição** ganha um `X-Request-ID` (o que veio do Caddy/cliente, se for são; senão
  um novo) e uma linha de log em JSON: rota, status, tempo, usuário. Lenta (> 1 s) e 5xx
  ficam marcadas. **Nunca** entra corpo, cookie, cabeçalho de autorização ou query string
  (e-mail e nome de cliente aparecem em busca).
- **Métricas por rota** desde o último restart, em memória: contagem, 4xx, 5xx, p50/p95.
- **O navegador reporta** erro de JavaScript e Web Vitals (LCP, INP, CLS, TTFB) em
  `POST /ops/api/system/cliente` — sem login, porque o erro pode ser na própria tela de login
  e `sendBeacon` não manda cabeçalho de CSRF. Por isso: corpo pequeno, campos cortados,
  limite por IP e buffer de tamanho fixo.

O log vai para o stderr do serviço (journald): `journalctl -u urace-command-center -o cat | grep cc.http`.
"""
import json
import logging
import re
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request

from command_center.api import auth

r = APIRouter(prefix="/ops/api/system", tags=["system"])

LENTA_MS = 1000
AMOSTRAS = 500                 # durações guardadas por rota (para p50/p95)
_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

log = logging.getLogger("cc.http")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False

_TRAVA = threading.Lock()
INICIO = time.time()
_ROTAS = defaultdict(lambda: {"n": 0, "e4": 0, "e5": 0, "lentas": 0, "ms": deque(maxlen=AMOSTRAS)})
_VITAIS = defaultdict(lambda: deque(maxlen=AMOSTRAS))            # (métrica, rota) -> valores
_ERROS_JS = deque(maxlen=100)
_POR_IP = defaultdict(deque)                                    # limite do POST /cliente
LIMITE_POR_MIN = 60


def zerar():
    """Para os testes."""
    with _TRAVA:
        _ROTAS.clear(); _VITAIS.clear(); _ERROS_JS.clear(); _POR_IP.clear()


def _rota(request):
    rt = request.scope.get("route")
    caminho = getattr(rt, "path", None)
    if caminho:
        return caminho
    p = request.url.path
    if p.startswith("/ops/assets/"):
        return "/ops/assets/*"
    return "/ops/*" if p.startswith("/ops") else "(fora)"


def _pct(valores, q):
    if not valores:
        return None
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


async def middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or ""
    if not _ID_OK.match(rid):
        rid = uuid.uuid4().hex[:16]
    request.state.request_id = rid
    t0 = time.perf_counter()
    status = 500
    try:
        resp = await call_next(request)
        status = resp.status_code
    finally:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        rota = _rota(request)
        with _TRAVA:
            m = _ROTAS[f"{request.method} {rota}"]
            m["n"] += 1
            m["ms"].append(ms)
            if status >= 500:
                m["e5"] += 1
            elif status >= 400:
                m["e4"] += 1
            if ms > LENTA_MS:
                m["lentas"] += 1
        api = request.url.path.startswith("/ops/api/")
        if api or status >= 500 or ms > LENTA_MS:
            linha = {"log": "cc.http", "id": rid, "metodo": request.method, "rota": rota, "status": status, "ms": ms,
                     "usuario": getattr(request.state, "cc_user", None)}
            if ms > LENTA_MS:
                linha["lenta"] = True
            (log.warning if status >= 500 or ms > LENTA_MS else log.info)(json.dumps(linha, ensure_ascii=False))
    resp.headers["X-Request-ID"] = rid
    return resp


def metricas():
    with _TRAVA:
        rotas = [{"rota": k, "n": v["n"], "erros_4xx": v["e4"], "erros_5xx": v["e5"], "lentas": v["lentas"],
                  "p50_ms": _pct(v["ms"], 0.5), "p95_ms": _pct(v["ms"], 0.95)} for k, v in _ROTAS.items()]
        vitais = [{"metrica": m, "rota": rota, "n": len(vs), "p75": _pct(vs, 0.75)} for (m, rota), vs in _VITAIS.items()]
        erros = list(_ERROS_JS)[-30:][::-1]
    rotas.sort(key=lambda x: (-x["erros_5xx"], -(x["p95_ms"] or 0)))
    return {"desde": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(INICIO)), "uptime_s": int(time.time() - INICIO),
            "requisicoes": sum(x["n"] for x in rotas), "erros_5xx": sum(x["erros_5xx"] for x in rotas),
            "rotas": rotas[:60], "vitais": sorted(vitais, key=lambda x: (x["metrica"], -x["n"])), "erros_js": erros}


@r.get("/metricas")
def ver_metricas(u=Depends(auth.exige("MANAGER"))):
    return metricas()


VITAIS_OK = {"LCP", "INP", "CLS", "TTFB", "FCP"}


def _corta(v, n):
    return None if v is None else str(v)[:n]


def _rota_do_cliente(rota):
    """Id vira :id — a métrica é por tela, e a URL não guarda dado de cliente."""
    rota = (rota or "")[:120].split("?")[0]
    return re.sub(r"/\d+(?=/|$)", "/:id", rota)


@r.post("/cliente", status_code=204)
async def do_navegador(request: Request):
    corpo = await request.body()
    if len(corpo) > 4096:
        raise HTTPException(413, "grande demais")
    ip = request.client.host if request.client else "?"
    agora_ = time.time()
    with _TRAVA:
        fila = _POR_IP[ip]
        while fila and fila[0] < agora_ - 60:
            fila.popleft()
        if len(fila) >= LIMITE_POR_MIN:
            raise HTTPException(429, "devagar")
        fila.append(agora_)
    try:
        d = json.loads(corpo or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON inválido")
    itens = d.get("itens") if isinstance(d, dict) and isinstance(d.get("itens"), list) else [d]
    for it in itens[:20]:
        if not isinstance(it, dict):
            continue
        rota = _rota_do_cliente(it.get("rota"))
        if it.get("tipo") == "vital" and it.get("nome") in VITAIS_OK:
            try:
                v = float(it.get("valor"))
            except (TypeError, ValueError):
                continue
            if 0 <= v < 600000:
                with _TRAVA:
                    _VITAIS[(it["nome"], rota)].append(round(v, 4 if it["nome"] == "CLS" else 1))
        elif it.get("tipo") == "erro":
            e = {"em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rota": rota,
                 "mensagem": _corta(it.get("mensagem"), 300), "origem": _corta(it.get("origem"), 200),
                 "pilha": _corta(it.get("pilha"), 800), "versao": _corta(it.get("versao"), 40)}
            with _TRAVA:
                _ERROS_JS.append(e)
            log.warning(json.dumps({"log": "cc.navegador", **{k: v for k, v in e.items() if k != "pilha"}}, ensure_ascii=False))
    return None
