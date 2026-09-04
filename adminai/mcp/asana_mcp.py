#!/usr/bin/env python3
"""Servidor MCP do Asana para o Administrative AI.

Roda no HOST, espalhado pelo gateway do OpenClaw. O agente, isolado no
container, recebe só as ferramentas -- o token fica aqui, lido de
~/.urace/adminai.env, e nunca entra no sandbox.

As regras do dono que viram código, não instrução:

  - ADM URACE (1205530439507169) é SOMENTE LEITURA. Qualquer escrita em
    tarefa que pertença a ele é recusada antes de chamar a API.
  - "Matt tasks" não recebe automação nenhuma. A seção é resolvida pelo
    nome em tempo de execução (o gid não está registrado) e toda escrita
    em tarefa que esteja nela é recusada.
  - Não existe ferramenta de apagar. Não existe ferramenta de
    desconcluir. Se a IA precisar disso, é um humano que faz.
  - APLICAR=0 (o padrão) transforma toda escrita em simulação: a
    ferramenta responde o que TERIA feito e não toca no Asana.

Ver brain/40_SISTEMAS/Asana.md e docs/adminai/mapa-asana-4-projetos.md.

Teste do protocolo sem rede:
    printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
                  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
        | ASANA_TOKEN=x python3 adminai/mcp/asana_mcp.py
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

API = "https://app.asana.com/api/1.0"
WORKSPACE = "1205450084498489"

# fonte: docs/adminai/mapa-asana-4-projetos.md
PROJETOS = {
    "1205450093098920": ("U-RACE", "ler · escrever com APLICAR=1"),
    "1205661933760052": ("SUITS", "ler · escrever com APLICAR=1"),
    "1215968721507536": ("Shipping Orders", "ler · escrever com APLICAR=1"),
    "1205530439507169": ("ADM URACE", "SOMENTE LEITURA"),
}
PROJETO_ADM = "1205530439507169"
PROJETO_URACE = "1205450093098920"
SECAO_SEM_AUTOMACAO = "Matt tasks"

CAMPOS_TAREFA = ("gid,name,completed,completed_at,due_on,due_at,notes,permalink_url,"
                 "assignee.name,parent.gid,parent.name,"
                 "memberships.project.gid,memberships.project.name,"
                 "memberships.section.gid,memberships.section.name,"
                 "custom_fields.name,custom_fields.type,custom_fields.display_value,"
                 "num_subtasks,modified_at,created_at")
CAMPOS_LISTA = ("gid,name,completed,due_on,assignee.name,num_subtasks,"
                "memberships.section.name,custom_fields.name,custom_fields.display_value")


# ------------------------------------------------------------- ambiente
def _carregar_env():
    """ASANA_TOKEN e APLICAR: do ambiente, senão de ~/.urace/adminai.env."""
    caminho = os.environ.get("URACE_ENV", os.path.expanduser("~/.urace/adminai.env"))
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("ASANA_TOKEN"):
        sys.exit(f"ERRO: falta ASANA_TOKEN (ambiente ou {caminho})")


def _aplicar():
    return os.environ.get("APLICAR", "0") == "1"


def _workspace_host():
    """Onde o workspace do agente mora no host, para traduzir /workspace/..."""
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    return os.path.expanduser(f"~/.openclaw/workspace/{agente}")


# ------------------------------------------------------------------ REST
def _req(caminho, metodo="GET", corpo=None, bruto=None, content_type=None):
    token = os.environ["ASANA_TOKEN"]
    if bruto is not None:
        dados = bruto
    elif corpo is not None:
        dados = json.dumps({"data": corpo}).encode()
    else:
        dados = None
    req = urllib.request.Request(f"{API}{caminho}", data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", content_type or "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # o modelo precisa saber que NÃO foi aplicado, com o motivo real
        raise ErroFerramenta(f"HTTP {e.code} em {metodo} {caminho}: "
                             f"{e.read()[:400].decode(errors='replace')}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"sem conexão com o Asana: {e.reason}")


def _paginar(caminho, params, limite=500):
    params = dict(params, limit=100)
    itens = []
    while True:
        r = _req(f"{caminho}?{urllib.parse.urlencode(params)}")
        itens.extend(r["data"])
        prox = (r.get("next_page") or {}).get("offset")
        if not prox or len(itens) >= limite:
            return itens
        params["offset"] = prox


# --------------------------------------------------------------- proteção
_cache_secao_matt = {}


def _gid_matt_tasks():
    """Resolve a seção "Matt tasks" pelo nome, uma vez por processo."""
    if "gid" not in _cache_secao_matt:
        secs = _req(f"/projects/{PROJETO_URACE}/sections?opt_fields=name")["data"]
        achada = [s["gid"] for s in secs if s["name"].strip() == SECAO_SEM_AUTOMACAO]
        _cache_secao_matt["gid"] = achada[0] if achada else None
        if not achada:
            log(f"aviso: seção '{SECAO_SEM_AUTOMACAO}' não encontrada no U-RACE")
    return _cache_secao_matt["gid"]


def _ler_tarefa(gid, campos=CAMPOS_TAREFA):
    return _req(f"/tasks/{gid}?opt_fields={campos}")["data"]


def _recusar_se_protegida(tarefa, acao):
    """Aplica as duas regras que não dependem do modelo obedecer."""
    for m in tarefa.get("memberships", []):
        proj = (m.get("project") or {}).get("gid")
        sec = m.get("section") or {}
        if proj == PROJETO_ADM:
            raise ErroFerramenta(
                f"RECUSADO ({acao}): a tarefa {tarefa['gid']} está no ADM URACE, "
                "que é somente leitura por ordem do dono.")
        if sec.get("gid") and sec["gid"] == _gid_matt_tasks():
            raise ErroFerramenta(
                f"RECUSADO ({acao}): a tarefa {tarefa['gid']} está em "
                f"'{SECAO_SEM_AUTOMACAO}', que não recebe automação nenhuma.")
    # subtarefa herda a proteção do pai
    pai = (tarefa.get("parent") or {}).get("gid")
    if pai:
        _recusar_se_protegida(_ler_tarefa(pai, "gid,memberships.project.gid,"
                                               "memberships.section.gid,parent.gid"),
                              acao)


def _simulado(descricao):
    log("SIMULAÇÃO:", descricao)
    return {"aplicado": False, "modo": "SIMULAÇÃO (APLICAR=0)",
            "teria_feito": descricao,
            "aviso": "Nada foi alterado no Asana. Registre no relatório como pendente de liberação."}


# ----------------------------------------------------------- utilidades
def _resumo_tarefa(t):
    cfs = {cf["name"]: cf.get("display_value") for cf in t.get("custom_fields", [])
           if cf.get("display_value") not in (None, "")}
    return {
        "gid": t["gid"], "nome": t.get("name"), "concluida": t.get("completed"),
        "vence_em": t.get("due_on"),
        "responsavel": (t.get("assignee") or {}).get("name"),
        "secao": ", ".join(sorted({(m.get("section") or {}).get("name") or "?"
                                   for m in t.get("memberships", [])})) or None,
        "subtarefas": t.get("num_subtasks"),
        "campos": cfs or None,
    }


srv = Servidor("urace-asana", "0.1")


# ----------------------------------------------------------- LEITURA
@srv.ferramenta(
    "asana_projetos",
    "Os 4 projetos que o Administrative AI conhece, com gid e nível de acesso. "
    "ADM URACE é somente leitura. Comece por aqui se não souber o gid.")
def asana_projetos():
    return [{"gid": g, "nome": n, "acesso": a} for g, (n, a) in PROJETOS.items()]


@srv.ferramenta(
    "asana_secoes",
    "Lista as seções (colunas do quadro) de um projeto, com gid. No U-RACE as "
    "seções TUESDAY..SUNDAY são o calendário de serviços; RACES são corridas; "
    "'Matt tasks' está fora de qualquer automação.",
    {"projeto_gid": {"type": "string"}}, ["projeto_gid"])
def asana_secoes(projeto_gid):
    secs = _req(f"/projects/{projeto_gid}/sections?opt_fields=name")["data"]
    return [{"gid": s["gid"], "nome": s["name"]} for s in secs]


@srv.ferramenta(
    "asana_tarefas_da_secao",
    "Tarefas de uma seção. Por padrão só as não concluídas. Devolve resumo "
    "(gid, nome, vencimento, responsável, seção, campos personalizados). Use "
    "asana_tarefa para ver notas e subtarefas.",
    {"secao_gid": {"type": "string"},
     "incluir_concluidas": {"type": "boolean", "default": False}},
    ["secao_gid"])
def asana_tarefas_da_secao(secao_gid, incluir_concluidas=False):
    params = {"section": secao_gid, "opt_fields": CAMPOS_LISTA}
    if not incluir_concluidas:
        params["completed_since"] = "now"
    return [_resumo_tarefa(t) for t in _paginar("/tasks", params)]


@srv.ferramenta(
    "asana_buscar",
    "Busca tarefas por texto dentro de um projeto. ATENÇÃO: o índice de busca "
    "do Asana atrasa minutos a horas -- ausência aqui NÃO prova que a tarefa "
    "não existe. Para confirmar, leia a seção diretamente com "
    "asana_tarefas_da_secao.",
    {"projeto_gid": {"type": "string"}, "texto": {"type": "string"},
     "incluir_concluidas": {"type": "boolean", "default": False}},
    ["projeto_gid", "texto"])
def asana_buscar(projeto_gid, texto, incluir_concluidas=False):
    params = {"text": texto, "projects.any": projeto_gid,
              "opt_fields": CAMPOS_LISTA, "sort_by": "modified_at"}
    if not incluir_concluidas:
        params["completed"] = "false"
    r = _req(f"/workspaces/{WORKSPACE}/tasks/search?{urllib.parse.urlencode(params)}")
    return {"aviso": "índice do Asana pode estar atrasado; confirme por leitura direta",
            "resultados": [_resumo_tarefa(t) for t in r["data"]]}


@srv.ferramenta(
    "asana_tarefa",
    "Lê uma tarefa completa: notas, vencimento, seções, campos personalizados, "
    "subtarefas (nome, gid, concluída) e link.",
    {"gid": {"type": "string"}}, ["gid"])
def asana_tarefa(gid):
    t = _ler_tarefa(gid)
    subs = _req(f"/tasks/{gid}/subtasks?opt_fields=gid,name,completed,due_on&limit=100")["data"]
    r = _resumo_tarefa(t)
    r.update({
        "notas": t.get("notes"), "link": t.get("permalink_url"),
        "projetos": [(m.get("project") or {}).get("name") for m in t.get("memberships", [])],
        "pai": (t.get("parent") or {}).get("name"),
        "criada_em": t.get("created_at"), "modificada_em": t.get("modified_at"),
        "subtarefas_lista": [{"gid": s["gid"], "nome": s["name"],
                              "concluida": s["completed"], "vence_em": s.get("due_on")}
                             for s in subs],
    })
    return r


@srv.ferramenta(
    "asana_comentarios",
    "Comentários (stories de comentário) de uma tarefa, do mais antigo ao mais novo.",
    {"gid": {"type": "string"}}, ["gid"])
def asana_comentarios(gid):
    st = _req(f"/tasks/{gid}/stories?opt_fields=created_at,created_by.name,text,type,"
              f"resource_subtype&limit=100")["data"]
    return [{"quando": s["created_at"], "quem": (s.get("created_by") or {}).get("name"),
             "texto": s.get("text")}
            for s in st if s.get("resource_subtype") == "comment_added"]


@srv.ferramenta(
    "asana_anexos",
    "Lista os anexos de uma tarefa (nome, tipo, link de download).",
    {"gid": {"type": "string"}}, ["gid"])
def asana_anexos(gid):
    a = _req(f"/tasks/{gid}/attachments?opt_fields=name,download_url,created_at,host,size")["data"]
    return [{"gid": x["gid"], "nome": x.get("name"), "origem": x.get("host"),
             "quando": x.get("created_at"), "download": x.get("download_url")} for x in a]


# ----------------------------------------------------------- ESCRITA
# Todas passam por _recusar_se_protegida e por APLICAR. Não existe apagar.
@srv.ferramenta(
    "asana_comentar",
    "Adiciona um comentário numa tarefa. Recusado em ADM URACE e em 'Matt tasks'. "
    "Com APLICAR=0 é simulação.",
    {"gid": {"type": "string"}, "texto": {"type": "string"}}, ["gid", "texto"])
def asana_comentar(gid, texto):
    t = _ler_tarefa(gid)
    _recusar_se_protegida(t, "comentar")
    if not _aplicar():
        return _simulado(f"comentar em '{t['name']}' ({gid}): {texto[:200]}")
    r = _req(f"/tasks/{gid}/stories", "POST", {"text": texto})["data"]
    return {"aplicado": True, "story_gid": r["gid"], "tarefa": t["name"]}


@srv.ferramenta(
    "asana_mover_para_secao",
    "Move uma tarefa para uma seção do mesmo projeto. Recusado em ADM URACE e "
    "'Matt tasks' (origem OU destino). Com APLICAR=0 é simulação.",
    {"gid": {"type": "string"}, "secao_gid": {"type": "string"}}, ["gid", "secao_gid"])
def asana_mover_para_secao(gid, secao_gid):
    t = _ler_tarefa(gid)
    _recusar_se_protegida(t, "mover")
    if secao_gid == _gid_matt_tasks():
        raise ErroFerramenta("RECUSADO: não se move nada PARA 'Matt tasks'.")
    de = ", ".join((m.get("section") or {}).get("name") or "?" for m in t.get("memberships", []))
    if not _aplicar():
        return _simulado(f"mover '{t['name']}' ({gid}) de [{de}] para seção {secao_gid}")
    _req(f"/sections/{secao_gid}/addTask", "POST", {"task": gid})
    return {"aplicado": True, "tarefa": t["name"], "de": de, "para": secao_gid}


@srv.ferramenta(
    "asana_concluir",
    "Marca uma tarefa ou subtarefa como concluída (ex.: a subtarefa 'Signed "
    "waiver?' depois da assinatura confirmada). Só conclui; nunca reabre. "
    "Recusado em ADM URACE e 'Matt tasks'. Com APLICAR=0 é simulação.",
    {"gid": {"type": "string"}}, ["gid"])
def asana_concluir(gid):
    t = _ler_tarefa(gid)
    _recusar_se_protegida(t, "concluir")
    if t.get("completed"):
        return {"aplicado": False, "motivo": "já estava concluída", "tarefa": t["name"]}
    if not _aplicar():
        return _simulado(f"concluir '{t['name']}' ({gid})")
    _req(f"/tasks/{gid}", "PUT", {"completed": True})
    return {"aplicado": True, "tarefa": t["name"]}


@srv.ferramenta(
    "asana_criar_tarefa",
    "Cria uma tarefa num projeto (e opcionalmente numa seção). Recusado no ADM "
    "URACE e em 'Matt tasks'. Com APLICAR=0 é simulação.",
    {"projeto_gid": {"type": "string"}, "nome": {"type": "string"},
     "secao_gid": {"type": "string"}, "notas": {"type": "string"},
     "vence_em": {"type": "string", "description": "AAAA-MM-DD"}},
    ["projeto_gid", "nome"])
def asana_criar_tarefa(projeto_gid, nome, secao_gid=None, notas=None, vence_em=None):
    if projeto_gid == PROJETO_ADM:
        raise ErroFerramenta("RECUSADO: não se cria nada no ADM URACE.")
    if secao_gid and secao_gid == _gid_matt_tasks():
        raise ErroFerramenta("RECUSADO: não se cria nada em 'Matt tasks'.")
    corpo = {"name": nome, "workspace": WORKSPACE, "projects": [projeto_gid]}
    if notas:
        corpo["notes"] = notas
    if vence_em:
        corpo["due_on"] = vence_em
    if not _aplicar():
        return _simulado(f"criar '{nome}' em {PROJETOS.get(projeto_gid, (projeto_gid,))[0]}"
                         + (f", seção {secao_gid}" if secao_gid else ""))
    r = _req("/tasks", "POST", corpo)["data"]
    if secao_gid:
        _req(f"/sections/{secao_gid}/addTask", "POST", {"task": r["gid"]})
    return {"aplicado": True, "gid": r["gid"], "link": r.get("permalink_url")}


@srv.ferramenta(
    "asana_anexar_arquivo",
    "Sobe um arquivo como anexo da tarefa (ex.: a waiver assinada em PDF). O "
    "caminho pode ser do container (/workspace/...) ou de ~/.urace/. Recusado "
    "em ADM URACE e 'Matt tasks'. Com APLICAR=0 é simulação.",
    {"gid": {"type": "string"}, "caminho": {"type": "string"}}, ["gid", "caminho"])
def asana_anexar_arquivo(gid, caminho):
    # o agente enxerga /workspace; o host enxerga ~/.openclaw/workspace/<agente>
    if caminho.startswith("/workspace/"):
        caminho = os.path.join(_workspace_host(), caminho[len("/workspace/"):])
    caminho = os.path.expanduser(caminho)
    raizes = (_workspace_host(), os.path.expanduser("~/.urace"))
    real = os.path.realpath(caminho)
    if not any(real.startswith(os.path.realpath(r) + os.sep) for r in raizes):
        raise ErroFerramenta(f"RECUSADO: só anexo arquivos do workspace ou de ~/.urace, não {caminho}")
    if not os.path.isfile(real):
        raise ErroFerramenta(f"arquivo não existe: {caminho}")
    t = _ler_tarefa(gid)
    _recusar_se_protegida(t, "anexar")
    nome = os.path.basename(real)
    if not _aplicar():
        return _simulado(f"anexar '{nome}' ({os.path.getsize(real)} bytes) em '{t['name']}' ({gid})")
    # multipart à mão: sem dependência, e o Asana só aceita assim
    limite = uuid.uuid4().hex
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    with open(real, "rb") as f:
        conteudo = f.read()
    corpo = b"".join([
        f"--{limite}\r\nContent-Disposition: form-data; name=\"parent\"\r\n\r\n{gid}\r\n".encode(),
        f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}\"\r\n"
        f"Content-Type: {tipo}\r\n\r\n".encode(), conteudo,
        f"\r\n--{limite}--\r\n".encode(),
    ])
    r = _req("/attachments", "POST", bruto=corpo,
             content_type=f"multipart/form-data; boundary={limite}")["data"]
    return {"aplicado": True, "anexo_gid": r["gid"], "nome": nome, "tarefa": t["name"]}


if __name__ == "__main__":
    _carregar_env()
    log("APLICAR =", os.environ.get("APLICAR", "0"), "| projetos:", len(PROJETOS))
    srv.rodar()
