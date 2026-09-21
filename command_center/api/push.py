"""Notificação no celular (Web Push).

Dono, 21/09: o chat interno só substitui o WhatsApp se **tocar no celular**. Isto é o que
faz isso acontecer — o painel instalado na tela inicial avisa mesmo fechado, em Android e
em iPhone (iOS 16.4+, com o site adicionado à tela inicial).

**O que a notificação leva, e por quê:** só quem escreveu, em que conversa, e o link.
Nunca o texto da mensagem. O aviso passa pelo servidor de push da Apple ou do Google, que
são terceiros; conversa de cliente, preço e combinado interno não têm por que passar por
lá. Quem quer ler abre o painel.

**Chave VAPID:** gerada uma vez e guardada em `~/.urace/vapid.json`, **fora do
repositório** — é uma credencial. Trocar a chave desassina todo mundo, então ela nasce uma
vez e fica.

A criptografia (ECDH + HKDF + AES-GCM) e a assinatura VAPID ficam com a `pywebpush`, que é
a implementação de referência. Fazer isso à mão é caminho conhecido de bug silencioso:
notificação que não chega e ninguém descobre por quê.
"""
import base64
import json
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, get_db, todos, um

r = APIRouter(prefix="/ops/api/push", tags=["push"])

# quem recebe o aviso precisa saber a quem responder; o padrão vale para a conta da URACE
CONTATO = os.environ.get("CC_PUSH_CONTATO", "mailto:urace@urace.us")
LIMITE_FALHAS = 5


def _arquivo():
    return os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "vapid.json")


def chaves(criar=True):
    """As chaves VAPID desta instalação. Cria na primeira vez; depois só lê.

    Ficam em ~/.urace porque são credencial: nunca no repositório, nunca no banco que sai
    em backup de dados."""
    caminho = _arquivo()
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    if not criar:
        return None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    chave = ec.generate_private_key(ec.SECP256R1())
    pem = chave.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    ponto = chave.public_key().public_bytes(serialization.Encoding.X962,
                                            serialization.PublicFormat.UncompressedPoint)
    dados = {"publica": base64.urlsafe_b64encode(ponto).rstrip(b"=").decode(), "pem": pem}
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.chmod(caminho, 0o600)
    return dados


def disponivel():
    """Push pronto para usar? Precisa da biblioteca E de conseguir gerar/ler a chave.

    O `except BaseException` é de propósito, e não é exagero: numa máquina com a
    `cryptography` quebrada (faltando o `_cffi_backend`), gerar chave não levanta
    ImportError nem Exception — levanta `pyo3_runtime.PanicException`, que herda de
    **BaseException**. Descobri isso apanhando em 21/09: o `except Exception` não pegava e
    a requisição de quem só queria conversar morria. Ctrl+C e encerramento seguem passando,
    que é o motivo de eles serem relançados antes."""
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return False
    try:
        return bool(chaves()["publica"])
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:                                          # noqa: BLE001
        return False


def _mandar_uma(assinatura, carga, vapid):
    """Manda para UM aparelho. Devolve (ok, morta). `morta` = o navegador disse que essa
    assinatura não existe mais (404/410): a pessoa desinstalou ou trocou de aparelho."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info={"endpoint": assinatura["endpoint"],
                               "keys": {"p256dh": assinatura["p256dh"], "auth": assinatura["auth"]}},
            data=json.dumps(carga),
            vapid_private_key=vapid["pem"],
            vapid_claims={"sub": CONTATO},
            timeout=10,
        )
        return True, False
    except WebPushException as e:                                  # noqa: PERF203
        codigo = getattr(getattr(e, "response", None), "status_code", None)
        return False, codigo in (404, 410)
    except Exception:                                              # noqa: BLE001
        return False, False


def avisar(con, user_ids, titulo, corpo, url="/ops/"):
    """Avisa estas pessoas em todos os aparelhos delas. Nunca levanta exceção: notificação
    que falha não pode derrubar a ação que a gerou — a mensagem já foi salva.

    Assinatura morta é apagada na hora. Sem isso a tabela vira lixo e cada envio fica mais
    lento para todo mundo."""
    ids = [i for i in dict.fromkeys(user_ids) if i]
    if not ids:
        return {"enviados": 0, "motivo": "ninguém para avisar"}
    try:
        vapid = chaves()
        import pywebpush  # noqa: F401
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:                                          # noqa: BLE001 — ver `disponivel`
        return {"enviados": 0, "motivo": "push não está pronto neste servidor"}
    marcas = ",".join("?" * len(ids))
    assinaturas = todos(con, f"SELECT * FROM push_subscriptions WHERE user_id IN ({marcas})", tuple(ids))
    enviados, limpas = 0, 0
    for a in assinaturas:
        ok, morta = _mandar_uma(a, {"titulo": titulo, "corpo": corpo, "url": url}, vapid)
        if ok:
            enviados += 1
            con.execute("UPDATE push_subscriptions SET last_ok_at=?, falhas=0 WHERE id=?", (agora(), a["id"]))
        elif morta:
            con.execute("DELETE FROM push_subscriptions WHERE id=?", (a["id"],))
            limpas += 1
        else:
            con.execute("UPDATE push_subscriptions SET falhas=falhas+1 WHERE id=?", (a["id"],))
            con.execute("DELETE FROM push_subscriptions WHERE id=? AND falhas>=?", (a["id"], LIMITE_FALHAS))
    con.commit()
    return {"enviados": enviados, "limpas": limpas, "aparelhos": len(assinaturas)}


# --------------------------------------------------------------------- rotas
@r.get("/chave")
def chave_publica(u=Depends(auth.usuario_atual)):
    """A chave pública que o navegador precisa para criar a assinatura."""
    if not disponivel():
        return {"ativo": False, "motivo": "o servidor ainda não está pronto para notificar"}
    return {"ativo": True, "chave": chaves()["publica"]}


class AssinarIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@r.post("/assinar", status_code=201)
def assinar(dados: AssinarIn, request: Request, u=Depends(auth.usuario_atual),
            con: sqlite3.Connection = Depends(get_db)):
    """O navegador criou a assinatura; aqui ela ganha dono.

    Mesmo endpoint de novo = mesmo aparelho (recarregou a página, reinstalou): atualiza em
    vez de duplicar, senão a pessoa recebe o aviso três vezes."""
    if not (dados.endpoint or "").startswith("https://"):
        raise HTTPException(400, "Assinatura inválida.")
    ja = um(con, "SELECT id FROM push_subscriptions WHERE endpoint=?", (dados.endpoint,))
    agente = (request.headers.get("user-agent") or "")[:200]
    if ja:
        con.execute("""UPDATE push_subscriptions SET user_id=?, p256dh=?, auth=?, user_agent=?, falhas=0
                       WHERE id=?""", (u["id"], dados.p256dh, dados.auth, agente, ja["id"]))
    else:
        con.execute("""INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
                       VALUES (?,?,?,?,?)""", (u["id"], dados.endpoint, dados.p256dh, dados.auth, agente))
    con.commit()
    return {"ok": True}


class CancelarIn(BaseModel):
    endpoint: str


@r.post("/cancelar")
def cancelar(dados: CancelarIn, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Desligar neste aparelho não desliga nos outros."""
    con.execute("DELETE FROM push_subscriptions WHERE endpoint=? AND user_id=?", (dados.endpoint, u["id"]))
    con.commit()
    return {"ok": True}


@r.get("/estado")
def estado(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    ap = todos(con, """SELECT id, substr(user_agent,1,80) AS aparelho, created_at, last_ok_at
                       FROM push_subscriptions WHERE user_id=? ORDER BY id""", (u["id"],))
    return {"ativo": disponivel(), "aparelhos": ap}


@r.post("/teste")
def teste(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Manda um aviso para a própria pessoa. Existe porque 'ativei e não sei se funciona'
    é o jeito mais rápido de alguém desistir da notificação."""
    if not disponivel():
        raise HTTPException(503, "A biblioteca de push não está instalada no servidor.")
    r_ = avisar(con, [u["id"]], "Está funcionando", "Se você está lendo isto no celular, o aviso chega.", "/ops/equipe")
    if not r_["enviados"]:
        raise HTTPException(400, "Nenhum aparelho recebeu. Ative a notificação neste celular e tente de novo.")
    return r_
