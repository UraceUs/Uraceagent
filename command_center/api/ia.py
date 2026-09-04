"""AI Command — o chat que comanda o agente `urace-admin` do OpenClaw.

Decisão (ADR §2): o Command Center NÃO tem um segundo agente. Ele chama
o mesmo `urace-admin` que roda as rotinas — mesmo cérebro, mesmas 27
ferramentas, mesmas regras dentro dos servidores MCP.

Fluxo:
  POST /api/ai/commands  → grava ai_commands (QUEUED), dispara em thread
  o `openclaw agent`, grava a saída (DONE/FAILED), e extrai AÇÕES
  PROPOSTAS. Com APLICAR=0 os MCP devolvem "teria feito X" — cada uma
  vira uma linha em ai_actions com a política do momento
  (SAFE / CONFIRMATION / APPROVAL / BLOCKED). Nada executa por trás.
  GET  /api/ai/commands, /{id}       → histórico e status (polling)
  POST /api/ai/actions/{id}/approve  → registra aprovação humana
  POST /api/ai/actions/{id}/reject
  A EXECUÇÃO de ação aprovada é a Fase 6 (motor). Aqui ela fica
  APPROVED, auditada, esperando o motor.

O runner é injetável: em teste, um falso; no VPS, o `openclaw` real.
"""
import json
import os
import re
import sqlite3
import subprocess
import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, atualizar, auditar, conectar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/api/ai")
AGENTE = os.environ.get("OPENCLAW_AGENT", "urace-admin")
TIMEOUT = int(os.environ.get("CC_AI_TIMEOUT", "900"))
SUGESTOES = [
    "O que precisa da minha atenção hoje?",
    "Quais serviços desta semana estão sem waiver assinada?",
    "Quem tem invoice vencida há mais de 30 dias?",
    "Prepare o relatório de operações de hoje",
    "Verifique a saúde das integrações",
    "Chegou um cliente novo — vou passar os dados; prepare o onboarding",
    "Quais e-mails de cliente estão sem resposta?",
]


# ------------------------------------------------------------- runner
def runner_openclaw(texto, session_key):
    """Roda o agente real. Devolve (ok, saida, erro)."""
    cmd = ["openclaw", "--no-color", "agent", "--agent", AGENTE, "--session-key", session_key,
           "--thinking", "medium", "--timeout", str(TIMEOUT), "--json", "-m", texto]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 30)
    except FileNotFoundError:
        return False, "", "openclaw não está no PATH deste serviço"
    except subprocess.TimeoutExpired:
        return False, "", f"o agente não respondeu em {TIMEOUT}s"
    saida = _limpa(p.stdout)
    texto_final = _extrai_texto(saida) or saida
    if p.returncode != 0 and not texto_final.strip():
        return False, "", _limpa(p.stderr)[-2000:] or f"rc={p.returncode}"
    return True, texto_final, None


def _limpa(s):
    s = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", s or "")
    return "\n".join(l for l in s.split("\n") if not l.startswith("OpenClaw 20"))


def _extrai_texto(saida):
    """`--json` pode devolver um objeto; pega o campo de texto se houver."""
    try:
        j = json.loads(saida.strip().split("\n")[-1])
    except Exception:
        return None
    for k in ("text", "reply", "output", "content", "message"):
        v = j.get(k) if isinstance(j, dict) else None
        if isinstance(v, str) and v.strip():
            return v
    return None


RUNNER = runner_openclaw

# Anexado a todo comando: transforma "o que eu faria" em linhas que o
# Command Center lê sem adivinhar. O agente já trabalha em simulação
# (APLICAR=0); isto só pede que ele declare as ações no fim.
SUFIXO = (
    "\n\n[Command Center] Ao terminar, liste TODAS as ações que você executaria em produção, "
    "uma por linha, exatamente neste formato e nada mais nessas linhas:\n"
    "ACAO: <nome_da_ferramenta_mcp> | <alvo (pessoa, gid, e-mail)> | <resumo curto>\n"
    "Se não houver ação nenhuma, escreva: ACAO: nenhuma")


# ------------------------------------------------- ações propostas
# O que os servidores MCP escrevem em simulação, e o nome da ferramenta
# que a política reconhece.
_VERBOS = [
    (r"(?:teria enviado|enviaria|enviar)\s+(?:a\s+)?(?:waiver|'?(?:Parental|Adult))", "docusign_enviar_waiver"),
    (r"(?:teria comentado|comentaria|comentar)\b", "asana_comentar"),
    (r"(?:teria movido|moveria|mover)\b.*(?:se[çc][ãa]o|coluna)", "asana_mover_para_secao"),
    (r"(?:teria conclu[íi]do|concluiria|concluir)\b", "asana_concluir"),
    (r"(?:teria criado|criaria|criar)\b.*tarefa", "asana_criar_tarefa"),
    (r"(?:teria anexado|anexaria|anexar)\b", "asana_anexar_arquivo"),
    (r"rascunho", "gmail_rascunho"),
    (r"(?:teria rotulado|rotularia|rotular|arquivar)\b", "gmail_rotular"),
]


def _adivinha(descricao):
    for pad, acao in _VERBOS:
        if re.search(pad, descricao, re.I):
            return acao
    return "acao_desconhecida"


def _politica(con, acao):
    p = um(con, "SELECT policy FROM action_policies WHERE action=?", (acao,))
    return p["policy"] if p else "REQUIRES_CONFIRMATION"


def extrair_acoes(con, command_id, texto):
    """Lê as ações que o agente declarou. Três fontes, na ordem:
    1. linhas `ACAO: ferramenta | alvo | resumo` (o protocolo pedido no SUFIXO)
    2. JSON de simulação dos MCP (`"teria_feito": ...`), se o agente o ecoou
    3. prosa ("teria enviado a waiver para…") — último recurso, marcado como tal
    """
    achadas, vistos = [], set()

    def registra(nome, descricao, fonte, alvo=None):
        chave = (nome, (alvo or descricao)[:80])
        if chave in vistos:
            return
        vistos.add(chave)
        pol = _politica(con, nome)
        aid = inserir(con, "ai_actions", command_id=command_id, action=nome,
                      system=nome.split("_")[0] if "_" in nome else None, policy=pol,
                      status="BLOCKED" if pol == "BLOCKED" else "PROPOSED",
                      payload=json.dumps({"alvo": alvo, "descricao": descricao[:500], "fonte": fonte}, ensure_ascii=False),
                      reason="proposta pelo agente em simulação (APLICAR=0)")
        if pol == "REQUIRES_APPROVAL":
            inserir(con, "approvals", action_id=aid)
        achadas.append({"id": aid, "action": nome, "policy": pol, "alvo": alvo, "descricao": descricao[:200]})

    for linha in (texto or "").split("\n"):
        l = linha.strip()
        m = re.match(r"^ACAO:\s*(.+)$", l, re.I)
        if m:
            corpo = m.group(1).strip()
            if corpo.lower().startswith("nenhuma"):
                continue
            partes = [p.strip() for p in corpo.split("|")]
            nome = re.sub(r"[^a-z0-9_]", "", partes[0].lower()) or "acao_desconhecida"
            registra(nome, " | ".join(partes[1:]) or corpo, "protocolo", partes[1] if len(partes) > 1 else None)
            continue
        if "teria_feito" in l:
            desc = None
            try:
                j = json.loads(l.rstrip(","))
                desc = j.get("teria_feito") if isinstance(j, dict) else None
            except Exception:
                m2 = re.search(r'"teria_feito"\s*:\s*"(.*?)"\s*(?:,|\})', l)
                desc = m2.group(1) if m2 else None
            if desc:
                registra(_adivinha(desc), desc, "simulacao_mcp")
            continue
        m3 = re.search(r"SIMULA[ÇC][ÃA]O[^:]*:\s*(.+)$", l)
        if m3:
            registra(_adivinha(m3.group(1)), m3.group(1), "simulacao_mcp")
    return achadas


# ------------------------------------------------------------ execução
def _executa(command_id, texto, session_key, user_id):
    con = conectar()
    try:
        atualizar(con, "ai_commands", command_id, status="RUNNING", started_at=agora())
        ok, saida, erro = RUNNER(texto + SUFIXO, session_key)
        if ok:
            # ações ANTES do DONE: quem lê o comando no instante em que ele
            # termina já vê as propostas (a tela faz polling nesse status)
            acoes = extrair_acoes(con, command_id, saida)
            atualizar(con, "ai_commands", command_id, status="DONE", finished_at=agora(), output=saida)
            auditar(con, "ai.command.done", f"ai:{AGENTE}", user_id=user_id, entity_type="ai_command",
                    entity_id=command_id, detail={"acoes_propostas": len(acoes)})
        else:
            atualizar(con, "ai_commands", command_id, status="FAILED", finished_at=agora(), error=erro)
            auditar(con, "ai.command.failed", f"ai:{AGENTE}", user_id=user_id, entity_type="ai_command",
                    entity_id=command_id, detail={"erro": (erro or "")[:300]})
    except Exception as e:
        atualizar(con, "ai_commands", command_id, status="FAILED", finished_at=agora(), error=f"{type(e).__name__}: {e}")
    finally:
        con.close()


# ------------------------------------------------------------- rotas
class ComandoIn(BaseModel):
    text: str


@r.get("/suggestions")
def suggestions(u=Depends(auth.usuario_atual)):
    return SUGESTOES


@r.post("/commands", status_code=202)
def command_create(dados: ComandoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                   con: sqlite3.Connection = Depends(get_db)):
    texto = (dados.text or "").strip()
    if not texto or len(texto) > 4000:
        raise HTTPException(400, "Command must be between 1 and 4000 characters.")
    session_key = f"agent:{AGENTE}:web-{u['id']}-{date.today().isoformat()}"
    cid = inserir(con, "ai_commands", user_id=u["id"], text=texto, session_key=session_key)
    auditar(con, "ai.command", f"user:{u['id']}", user_id=u["id"], entity_type="ai_command",
            entity_id=cid, detail={"text": texto[:300]}, ip=auth._ip(request))
    threading.Thread(target=_executa, args=(cid, texto, session_key, u["id"]), daemon=True).start()
    return {"id": cid, "status": "QUEUED"}


@r.get("/commands")
def command_list(limit: int = 30, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    limit = max(1, min(limit, 200))
    mine = not auth.pode(u["role"], "MANAGER")
    sql = "SELECT id, user_id, text, status, created_at, started_at, finished_at, error FROM ai_commands"
    sql += " WHERE user_id=?" if mine else ""
    sql += " ORDER BY id DESC LIMIT ?"
    return todos(con, sql, ((u["id"], limit) if mine else (limit,)))


@r.get("/commands/{cid}")
def command_get(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT * FROM ai_commands WHERE id=?", (cid,))
    if not c or (c["user_id"] != u["id"] and not auth.pode(u["role"], "MANAGER")):
        raise HTTPException(404, "Command not found.")
    c["actions"] = todos(con, "SELECT * FROM ai_actions WHERE command_id=? ORDER BY id", (cid,))
    return c


@r.get("/actions")
def actions(status: str = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    if status:
        return todos(con, "SELECT * FROM ai_actions WHERE status=? ORDER BY id DESC LIMIT 200", (status.upper(),))
    return todos(con, "SELECT * FROM ai_actions ORDER BY id DESC LIMIT 200")


class DecisaoIn(BaseModel):
    comment: str = None


def _decide(con, aid, u, decisao, comentario, ip):
    a = um(con, "SELECT * FROM ai_actions WHERE id=?", (aid,))
    if not a:
        raise HTTPException(404, "Action not found.")
    if a["policy"] == "BLOCKED":
        raise HTTPException(403, "This action is blocked by policy and cannot be approved.")
    if a["status"] != "PROPOSED":
        raise HTTPException(409, f"Action is already {a['status']}.")
    ap = um(con, "SELECT id FROM approvals WHERE action_id=? AND decided_at IS NULL", (aid,))
    if ap:
        con.execute("UPDATE approvals SET decided_at=?, decided_by=?, decision=?, comment=? WHERE id=?",
                    (agora(), u["id"], decisao, comentario, ap["id"]))
    else:
        inserir(con, "approvals", action_id=aid, decided_at=agora(), decided_by=u["id"],
                decision=decisao, comment=comentario)
    atualizar(con, "ai_actions", aid, status="APPROVED" if decisao == "APPROVED" else "REJECTED")
    auditar(con, f"action.{decisao.lower()}", f"user:{u['id']}", user_id=u["id"], entity_type="ai_action",
            entity_id=aid, detail={"action": a["action"], "policy": a["policy"], "comment": comentario}, ip=ip)
    return {"ok": True, "status": "APPROVED" if decisao == "APPROVED" else "REJECTED",
            "note": "Execução de ações aprovadas chega com o motor (Fase 6). Até lá fica registrada e auditada."}


@r.post("/actions/{aid}/approve")
def action_approve(aid: int, dados: DecisaoIn, request: Request, u=Depends(auth.exige("MANAGER")),
                   con: sqlite3.Connection = Depends(get_db)):
    return _decide(con, aid, u, "APPROVED", dados.comment, auth._ip(request))


@r.post("/actions/{aid}/reject")
def action_reject(aid: int, dados: DecisaoIn, request: Request, u=Depends(auth.exige("OPERATOR")),
                  con: sqlite3.Connection = Depends(get_db)):
    return _decide(con, aid, u, "REJECTED", dados.comment, auth._ip(request))


@r.get("/activity")
def activity(limit: int = 100, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Tudo que a IA fez, na ordem: comandos, ações, decisões."""
    limit = max(1, min(limit, 500))
    return todos(con, """SELECT at, actor, event, entity_type, entity_id, detail FROM audit_logs
                         WHERE event LIKE 'ai.%' OR event LIKE 'action.%' ORDER BY id DESC LIMIT ?""", (limit,))
