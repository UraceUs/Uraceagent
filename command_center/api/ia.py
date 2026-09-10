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
def _acha_openclaw():
    """OPENCLAW_BIN se definido; senão procura no PATH e nos lugares usuais do npm/nvm.
    Autocorreção: o serviço não precisa que alguém descubra o caminho à mão."""
    import glob
    import shutil
    if os.environ.get("OPENCLAW_BIN"):
        return os.environ["OPENCLAW_BIN"]
    achado = shutil.which("openclaw")
    if achado:
        return achado
    home = os.path.expanduser("~")
    for pad in (f"{home}/.npm-global/bin/openclaw", "/usr/local/bin/openclaw", f"{home}/.local/bin/openclaw",
                f"{home}/.nvm/versions/node/*/bin/openclaw", "/opt/*/bin/openclaw"):
        for c in sorted(glob.glob(pad), reverse=True):
            if os.access(c, os.X_OK):
                return c
    return "openclaw"


OPENCLAW = _acha_openclaw()
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
    global OPENCLAW
    if os.environ.get("OPENCLAW_BIN"):                 # a variável manda, sempre (também no teste)
        OPENCLAW = os.environ["OPENCLAW_BIN"]
    cmd = [OPENCLAW, "--no-color", "agent", "--agent", AGENTE, "--session-key", session_key,
           "--thinking", "medium", "--timeout", str(TIMEOUT), "--json", "-m", texto]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 30)
    except FileNotFoundError:
        OPENCLAW = _acha_openclaw()                    # tenta redescobrir para a próxima
        return False, "", (f"'{OPENCLAW}' não encontrado neste serviço. Procurei no PATH, ~/.npm-global, ~/.nvm e /usr/local/bin. "
                           "Defina OPENCLAW_BIN=<caminho> em ~/.urace/adminai.env e reinicie urace-command-center.")
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
    """`--json` devolve um objeto; o texto do agente vive em lugares diferentes
    conforme a versão do OpenClaw. Procura em todos; devolve None se não achar."""
    bruto = (saida or "").strip()
    j = None
    for candidato in (bruto, bruto.split("\n")[-1]):
        try:
            j = json.loads(candidato)
            break
        except Exception:
            continue
    if not isinstance(j, dict):
        return None
    res = j.get("result") if isinstance(j.get("result"), dict) else {}
    pay = res.get("payloads") or j.get("payloads") or []
    textos = [p.get("text") for p in pay if isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"].strip()]
    if textos:
        return "\n\n".join(textos)
    for k in ("finalAssistantVisibleText", "finalAssistantRawText", "text", "reply", "output", "content", "message"):
        v = res.get(k) if k in res else j.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


RUNNER = runner_openclaw
# Cada execução do agente sobe um processo Node + sandbox Docker. Em paralelo
# isso derruba o VPS (09/09: 6 eventos → 6 agentes → site fora do ar).
_PARALELO = threading.Semaphore(int(os.environ.get("CC_AI_PARALELO", "1")))

# Anexado a todo comando: transforma "o que eu faria" em linhas que o
# Command Center lê sem adivinhar. O agente já trabalha em simulação
# (APLICAR=0); isto só pede que ele declare as ações no fim.
SUFIXO = (
    "\n\n[Command Center] COMO RESPONDER: você é um colega de operação da URACE falando com o dono pelo painel. "
    "Português direto, frases curtas, sem jargão interno: não cite 'trava', 'APLICAR', 'política', ids de template ou nomes de ferramenta no texto. "
    "Se faltar dado, faça as perguntas numa lista curta (só o que realmente impede agir) e pare. "
    "Se der para agir com o que tem, aja e diga o que fez em uma linha. Não explique regras internas, aplique-as. "
    "Se precisar de preço, leia a Rate Card (planilha) antes de perguntar ao dono."
    "\nAo terminar, liste TODAS as ações que você executaria em produção, "
    "uma por linha, exatamente neste formato e nada mais nessas linhas:\n"
    "ACAO: <nome_da_ferramenta_mcp> | <alvo (pessoa, gid, e-mail)> | <resumo curto> | <JSON com os argumentos EXATOS da ferramenta>\n"
    "O JSON é obrigatório e precisa ter os mesmos nomes de parâmetro da ferramenta (ex.: "
    '{"templateId":"…","nome":"…","email":"…","idade_confirmada":true,"nome_email_conferidos":true,"servico":"…"}). '
    "Quem aprovar no painel executa exatamente esse JSON. Se não houver ação nenhuma, escreva: ACAO: nenhuma"
    "\nInvoice (qbo_criar_e_enviar_invoice / qbo_criar_invoice) SEMPRE assim: "
    '{"cliente_id":"<id numérico do RESPONSÁVEL no QBO, via qbo_clientes_buscar>","linhas":[{"item_id":"<id numérico via qbo_itens_buscar>","quantidade":1,"unitario":<valor em dólares, nunca 0>,"descricao":"<serviço - piloto - data>"}],"vence_em":"AAAA-MM-DD","memo":"…","email":"…"}. '
    "O valor que o dono disse manda sobre qualquer outro. Nunca proponha de novo uma ação que já foi aprovada ou feita hoje. "
    "Consultas (buscar, ler, listar) você executa AGORA, durante a resposta — nunca as liste como ACAO. "
    "Serviço novo é uma tarefa NOVA no quadro com os dados do cliente (o histórico é só referência): diga 'criar', nunca 'recriar'. "
    "Se o CONTEXTO DO PAINEL já trouxer o id do cliente e dos itens do QuickBooks, use-os sem buscar de novo.")


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


def _buscar_item_qbo(nome):
    """Item do catálogo do QBO pelo nome (leitura). Sem QBO, lista vazia."""
    from command_center.providers import chamar
    try:
        r = chamar("quickbooks", "qbo_itens_buscar", termos=[nome])
        return [{"id": i.get("id"), "nome": i.get("nome")} for i in (r[0].get("itens") if r else [])]
    except Exception:
        return []


def _buscar_cliente_qbo(texto):
    from command_center.providers import chamar
    try:
        r = chamar("quickbooks", "qbo_clientes_buscar", texto=texto, maximo=5)
        return [{"id": c.get("id"), "nome": c.get("nome"), "email": c.get("email")} for c in (r if isinstance(r, list) else r.get("clientes", []))]
    except Exception:
        return []


def _criar_item_qbo(nome, preco, descricao=None):
    from command_center.providers import modulo
    return modulo("quickbooks").criar_item_sistema(nome, preco, descricao)


_SISTEMA_DO_NOME = {"qbo": "quickbooks", "quickbooks": "quickbooks", "asana": "asana", "docusign": "docusign",
                    "gmail": "gmail", "google": "gmail", "calendar": "gmail", "sheets": "gmail"}


def executar_consultas(consultas):
    """Roda as buscas/leituras que o agente listou (só leitura; sem APLICAR). Devolve linhas de texto
    com o resultado, para voltar ao agente na mesma conversa. Parâmetro desconhecido é descartado."""
    import inspect
    from command_center.providers import NaoConectado, modulo
    saida = []
    for nome, args in consultas[:6]:
        sistema = _SISTEMA_DO_NOME.get(nome.split("_")[0], nome.split("_")[0])
        try:
            fn = getattr(modulo(sistema), nome, None)
            if fn is None:
                saida.append(f"- {nome}: ferramenta não existe"); continue
            aceitos = inspect.signature(fn).parameters
            kw = {k: v for k, v in (args or {}).items() if k in aceitos} if not any(p.kind == p.VAR_KEYWORD for p in aceitos.values()) else dict(args or {})
            res = fn(**kw)
            saida.append(f"- {nome} {json.dumps(kw, ensure_ascii=False)[:120]} → {json.dumps(res, ensure_ascii=False)[:1500]}")
        except NaoConectado as e:
            saida.append(f"- {nome}: não conectado ({e})")
        except Exception as e:
            saida.append(f"- {nome}: {type(e).__name__}: {str(e)[:200]}")
    return saida


def extrair_acoes(con, command_id, texto, notas=None, consultas=None):
    """Lê as ações que o agente declarou. Três fontes, na ordem:
    1. linhas `ACAO: ferramenta | alvo | resumo` (o protocolo pedido no SUFIXO)
    2. JSON de simulação dos MCP (`"teria_feito": ...`), se o agente o ecoou
    3. prosa ("teria enviado a waiver para…") — último recurso, marcado como tal
    Antes de gravar: argumentos normalizados (acoes.py), item do QBO resolvido,
    ação igual já aprovada não é reproposta, pendente igual é substituída.
    `notas` (lista) recebe avisos para o dono ("já aprovada em #11").
    """
    from command_center.api import acoes
    achadas, vistos = [], set()
    notas = notas if notas is not None else []

    def registra(nome, descricao, fonte, alvo=None, args=None):
        nome = acoes.nome_canonico(nome)
        nome, args = acoes.converter(nome, args, con, texto)
        chave = (nome, (alvo or descricao)[:80])
        if chave in vistos:
            return
        vistos.add(chave)
        if acoes.eh_consulta(nome):                       # busca/leitura: o painel executa na hora e devolve ao agente
            if consultas is not None and isinstance(args, dict):
                consultas.append((nome, args))
            else:
                notas.append(f"{nome} é consulta, não ação: a IA executa na hora, não propõe.")
            return
        pol = _politica(con, nome)
        problemas = []
        if isinstance(args, dict):
            args, problemas = acoes.normalizar(nome, args, texto, _buscar_item_qbo, _buscar_cliente_qbo, con, alvo, _criar_item_qbo, notas)
        assin = acoes.assinatura(nome, args, alvo)
        estado, antiga = acoes.ja_decidida(con, assin)
        if estado == "feita":
            notas.append(f"{nome} → {alvo or descricao[:60]}: já aprovada/feita em #{antiga['id']} (comando #{antiga['command_id']}); não proposta de novo.")
            achadas.append({"id": antiga["id"], "action": nome, "policy": pol, "alvo": alvo, "descricao": descricao[:200], "repetida": True})
            return
        aid = inserir(con, "ai_actions", command_id=command_id, action=nome,
                      system=nome.split("_")[0] if "_" in nome else None, policy=pol,
                      status="BLOCKED" if pol == "BLOCKED" else "PROPOSED",
                      payload=json.dumps({"alvo": alvo, "descricao": descricao[:500], "fonte": fonte, "args": args,
                                          "assinatura": assin, "problemas": problemas or None}, ensure_ascii=False),
                      reason=("incompleta: " + "; ".join(problemas)) if problemas else
                             ("proposta pelo agente" + ("" if args else " (sem argumentos estruturados)")))
        if pol == "REQUIRES_APPROVAL":
            inserir(con, "approvals", action_id=aid)
        if estado == "pendente":                          # a mesma ação ainda pendente (mesmo comando ou anterior): a nova manda
            acoes.substituir(con, antiga["id"], aid)
            if antiga["command_id"] != command_id:
                notas.append(f"{nome} → {alvo or descricao[:60]}: substitui a proposta #{antiga['id']} (instrução mais recente).")
        achadas.append({"id": aid, "action": nome, "policy": pol, "alvo": alvo, "descricao": descricao[:200], "problemas": problemas})

    for linha in (texto or "").split("\n"):
        l = linha.strip()
        m = re.match(r"^ACAO:\s*(.+)$", l, re.I)
        if m:
            corpo = m.group(1).strip()
            if corpo.lower().startswith("nenhuma"):
                continue
            args = None
            mj = re.search(r"\|\s*(\{.*\})\s*$", corpo)
            if mj:
                try:
                    args = json.loads(mj.group(1))
                except ValueError:
                    args = None
                corpo = corpo[:mj.start()].rstrip()
            partes = [p.strip() for p in corpo.split("|")]
            nome = re.sub(r"[^a-z0-9_]", "", partes[0].lower()) or "acao_desconhecida"
            registra(nome, " | ".join(partes[1:]) or corpo, "protocolo", partes[1] if len(partes) > 1 else None, args if isinstance(args, dict) else None)
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
def _executa(command_id, texto, session_key, user_id, prompt=None):
    """`texto` é o que o dono escreveu (fica no histórico); `prompt` é o que vai ao agente (texto + contexto)."""
    con = conectar()
    try:
        prompt = prompt or texto
        with _PARALELO:                                   # fila: um agente por vez
            atualizar(con, "ai_commands", command_id, status="RUNNING", started_at=agora())
            ok, saida, erro = RUNNER(prompt + SUFIXO, session_key)
            if not ok and erro and ("não respondeu" in erro or "não encontrado" in erro):
                ok, saida, erro = RUNNER(prompt + SUFIXO, session_key)
        if ok:
            # ações ANTES do DONE: quem lê o comando no instante em que ele
            # termina já vê as propostas (a tela faz polling nesse status)
            from command_center.api import acoes as _ac
            notas, consultas = [], []
            lista = extrair_acoes(con, command_id, saida, notas, consultas)
            incompletas = []
            for _rodada in range(2):                      # buscas viram resultado; proposta incompleta ganha correção
                resultados = executar_consultas(consultas) if consultas else []
                incompletas = [a for a in lista if a.get("problemas")]
                if not resultados and not incompletas:
                    break
                pedido = ""
                if resultados:
                    pedido += "\n\n[Command Center] Executei as consultas que você listou (não peça de novo). RESULTADOS:\n" + "\n".join(resultados)
                if incompletas:
                    pedido += "".join(_ac.pedido_de_correcao(a["action"], a["problemas"]) for a in incompletas[:3])
                pedido += ("\n\nAgora CONCLUA o pedido do dono: reescreva SOMENTE as linhas ACAO finais que faltam, com os campos exatos "
                           "(cliente_id e item_id numéricos, unitario com o valor dito). Nada de consulta: se um item não existir, use qbo_criar_item.")
                with _PARALELO:
                    ok2, saida2, _ = RUNNER(pedido, session_key)
                if not ok2 or not re.search(r"^ACAO:", saida2 or "", re.M):
                    break
                for a in incompletas:
                    atualizar(con, "ai_actions", a["id"], status="REJECTED", finished_at=agora(), result="substituída pela correção da própria IA")
                    con.execute("UPDATE approvals SET decided_at=?, decision='REJECTED', comment='corrigida' WHERE action_id=? AND decided_at IS NULL", (agora(), a["id"]))
                consultas = []
                lista = [a for a in lista if not a.get("problemas")] + extrair_acoes(con, command_id, saida2, notas, consultas)
                saida = saida + "\n\n" + saida2.strip()
            incompletas = [a for a in lista if a.get("problemas")]
            if notas:
                saida = saida + "\n\n" + "\n".join("(Command Center) " + n for n in notas)
            from command_center.api import motor
            auto = motor.executar_safe(con, command_id, user_id)
            atualizar(con, "ai_commands", command_id, status="DONE", finished_at=agora(), output=saida)
            auditar(con, "ai.command.done", f"ai:{AGENTE}", user_id=user_id, entity_type="ai_command",
                    entity_id=command_id, detail={"acoes_propostas": len(lista), "executadas_safe": auto, "corrigidas": len(incompletas), "notas": notas[:5]})
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
    from command_center.api import acoes, motor
    prompt = texto + motor.aprendizados(con) + motor.contexto_do_comando(con, texto) + acoes.estado_do_dia(con, u["id"])
    session_key = f"agent:{AGENTE}:web-{u['id']}-{date.today().isoformat()}"
    cid = inserir(con, "ai_commands", user_id=u["id"], text=texto, prompt=prompt, session_key=session_key)
    auditar(con, "ai.command", f"user:{u['id']}", user_id=u["id"], entity_type="ai_command",
            entity_id=cid, detail={"text": texto[:300]}, ip=auth._ip(request))
    threading.Thread(target=_executa, args=(cid, texto, session_key, u["id"], prompt), daemon=True).start()
    return {"id": cid, "status": "QUEUED"}


@r.get("/commands")
def command_list(limit: int = 30, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    limit = max(1, min(limit, 200))
    mine = not auth.pode(u["role"], "MANAGER")
    sql = "SELECT id, user_id, text, status, created_at, started_at, finished_at, error FROM ai_commands"
    sql += " WHERE user_id=?" if mine else ""
    sql += " ORDER BY id DESC LIMIT ?"
    return todos(con, sql, ((u["id"], limit) if mine else (limit,)))


_AUTO_PREFIXOS = ("EVENTO AUTOMÁTICO", "TAREFA:")


def _eh_auto(texto):
    return (texto or "").startswith(_AUTO_PREFIXOS)


@r.get("/threads")
def threads(u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """Uma conversa por usuário (decisão do dono, 10/09). Gerente/admin vê a de todos e a automática;
    os demais só a própria."""
    rows = todos(con, """SELECT us.id, us.name, us.role, COUNT(c.id) AS n, MAX(c.created_at) AS last_at
                         FROM users us LEFT JOIN ai_commands c ON c.user_id=us.id
                              AND c.text NOT LIKE 'EVENTO AUTOMÁTICO%' AND c.text NOT LIKE 'TAREFA:%'
                         WHERE us.active=1 GROUP BY us.id ORDER BY last_at DESC NULLS LAST, us.name""")
    if not auth.pode(u["role"], "MANAGER"):
        rows = [r_ for r_ in rows if r_["id"] == u["id"]]
        return {"threads": rows, "auto": None}
    auto = um(con, "SELECT COUNT(*) AS n, MAX(created_at) AS last_at FROM ai_commands WHERE text LIKE 'EVENTO AUTOMÁTICO%' OR text LIKE 'TAREFA:%'")
    return {"threads": rows, "auto": auto}


@r.get("/thread")
def thread(user_id: int | None = None, kind: str = "chat", before: int | None = None, limit: int = 40,
           u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    """A conversa contínua: comandos do usuário (mais antigos primeiro), cada um com suas ações."""
    limit = max(1, min(limit, 200))
    gerente = auth.pode(u["role"], "MANAGER")
    if kind == "auto":
        if not gerente:
            raise HTTPException(403, "Only managers see the automatic thread.")
        where, p = ["(text LIKE 'EVENTO AUTOMÁTICO%' OR text LIKE 'TAREFA:%')"], []
    else:
        alvo = user_id if (user_id and gerente) else u["id"]
        where, p = ["user_id=?", "text NOT LIKE 'EVENTO AUTOMÁTICO%'", "text NOT LIKE 'TAREFA:%'"], [alvo]
    if before:
        where.append("id<?"); p.append(before)
    rows = todos(con, f"SELECT id, user_id, text, status, created_at, started_at, finished_at, output, error FROM ai_commands WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", (*p, limit + 1))
    mais = len(rows) > limit
    rows = list(reversed(rows[:limit]))
    for c in rows:
        c["actions"] = todos(con, "SELECT * FROM ai_actions WHERE command_id=? ORDER BY id", (c["id"],))
    return {"commands": rows, "has_more": mais}


@r.get("/commands/{cid}")
def command_get(cid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    c = um(con, "SELECT * FROM ai_commands WHERE id=?", (cid,))
    if not c or (c["user_id"] != u["id"] and not auth.pode(u["role"], "MANAGER")):
        raise HTTPException(404, "Command not found.")
    c["actions"] = todos(con, "SELECT * FROM ai_actions WHERE command_id=? ORDER BY id", (cid,))
    return c


@r.get("/actions")
def actions(status: str | None = None, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    if status:
        return todos(con, "SELECT * FROM ai_actions WHERE status=? ORDER BY id DESC LIMIT 200", (status.upper(),))
    return todos(con, "SELECT * FROM ai_actions ORDER BY id DESC LIMIT 200")


@r.get("/actions/{aid}")
def action_get(aid: int, u=Depends(auth.usuario_atual), con: sqlite3.Connection = Depends(get_db)):
    a = um(con, "SELECT * FROM ai_actions WHERE id=?", (aid,))
    if not a:
        raise HTTPException(404, "Action not found.")
    return a


class DecisaoIn(BaseModel):
    comment: str | None = None


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
    if decisao == "APPROVED":
        from command_center.api import motor
        threading.Thread(target=motor.executar_acao, args=(aid, u["id"]), daemon=True).start()
        return {"ok": True, "status": "APPROVED", "note": "Aprovada: executando agora pelo sistema. O resultado aparece na ação em segundos."}
    return {"ok": True, "status": "REJECTED"}


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
