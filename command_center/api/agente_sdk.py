"""O AI Command no Claude Agent SDK (#152): o mesmo motor das sessões do Claude Code.

Dono, 08/10: *"eu não quero mais esse vai e vem ... Gostei desse limite de pedido. O custo
não precisa ficar no painel. E o modelo pode ser o Opus 5.5 para praticamente tudo. O Haiku
fica ali no e-mail. Quando o Haiku tiver dificuldade, ele aciona o Opus no e-mail também.
Mas os dois sempre ligados à nossa inteligência, ao nosso cérebro."*

Antes (OpenClaw): o agente trabalhava em simulação (APLICAR=0), tudo virava proposta, e o
painel lia linhas "ACAO:"/"CONSULTA:" do texto e voltava ao agente até três vezes.

Agora o agente chama as ferramentas de verdade, num loop, até terminar o pedido:
- **ler** (QuickBooks, Asana, Gmail, DocuSign, Kommo, painel, web, cérebro): direto;
- **trabalho interno** (tarefa, comentário e seção no Asana; cliente, item, invoice e
  estimate criados SEM enviar; rascunho; marcador): direto, e fica registrado como ação feita;
- **o que sai da empresa ou não volta atrás** (enviar, lembrete, apagar, anular, unir cards,
  trocar o documento da waiver, preço do catálogo, pagamento, recorrência): a ferramenta
  NÃO roda; vira um "aprovar" de um clique no painel, e quem aprova executa pelo motor;
- o que a política bloqueia: não roda.

O cérebro (`brain/`) e as skills (`skills/`) entram só para leitura. O teto é de US$ 2 por
pedido (`CC_IA_LIMITE_USD`); o custo vai para o log do servidor, não para a tela.

Contrato com o resto do painel: `rodar(...)` devolve um `Resultado`, e `runner(...)` o
`(ok, saida, erro)` de sempre, para a triagem e quem mais chamava o OpenClaw.
"""
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from command_center import providers
from command_center.db import agora, auditar, conectar, inserir, um

log = logging.getLogger("command_center.ia")

MODELO = os.environ.get("CC_IA_MODELO", "claude-opus-5-5")
MODELO_EMAIL = os.environ.get("CC_IA_MODELO_EMAIL", "claude-haiku-5-5")
LIMITE_USD = float(os.environ.get("CC_IA_LIMITE_USD", "2"))
LIMITE_EMAIL_USD = float(os.environ.get("CC_IA_LIMITE_EMAIL_USD", "0.5"))
ESFORCO = os.environ.get("CC_IA_ESFORCO", "medium")
TIMEOUT = int(os.environ.get("CC_AI_TIMEOUT", "900"))
FUSO = ZoneInfo("America/New_York")

CEREBRO = os.path.join(providers.REPO, "brain")
SKILLS = os.path.join(providers.REPO, "skills")


def _contexto_dir():
    """Onde o painel guarda os arquivos de contexto que o dono sobe (Integrações)."""
    agente = os.environ.get("OPENCLAW_AGENT", "urace-admin")
    return os.path.expanduser(f"~/.openclaw/workspace/{agente}/contexto")


def _suits_dir():
    """Os screenshots das notas da aba Suits (#153): a IA lê para entender a nota."""
    return os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "suits")


def pastas_de_leitura():
    return [CEREBRO, SKILLS, _contexto_dir(), _suits_dir()]


# Servidores MCP do adminai que o agente usa (um processo cada, com APLICAR=1: quem segura o
# que não pode rodar é o portão abaixo, antes de a chamada chegar ao servidor).
SERVIDORES = {"quickbooks": "quickbooks_mcp.py", "asana": "asana_mcp.py", "gmail": "gmail_mcp.py",
              "docusign": "docusign_mcp.py", "kommo": "kommo_mcp.py"}
NOME_PAINEL = "painel"
NOME_SUITS = "suits"
FERRAMENTAS_EMBUTIDAS = ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "ToolSearch"]

# Leituras que o `acoes.eh_consulta` (feito para o protocolo antigo) não conhece pelo nome.
LEITURAS = {"docusign_templates", "docusign_envelopes", "qbo_recorrencias", "gmail_baixar_anexo",
            "qbo_itens", "qbo_invoices", "qbo_invoice", "qbo_estimates",
            "suits_pedidos", "suits_pedido", "suits_leads", "suits_fornecedores"}
RX_APROVAR = re.compile(r"(^|_)(enviar|reenviar|send|lembrete|reminder|apagar|excluir|deletar|delete|remover|"
                        r"void|anular|unir|merge|substituir|atualizar_preco|pagamento|payment|pagar|recorrencia)(_|$)")


@dataclass
class Resultado:
    ok: bool
    texto: str = ""
    erro: str | None = None
    subtipo: str | None = None
    custo: float | None = None
    sessao: str | None = None


# ------------------------------------------------------------------ o portão
def nome_da_ferramenta(nome_cru):
    """'mcp__quickbooks__qbo_invoices' → 'qbo_invoices' (o nome que a política e o motor conhecem)."""
    return nome_cru.split("__", 2)[2] if nome_cru.startswith("mcp__") and nome_cru.count("__") >= 2 else nome_cru


def classificar(con, nome):
    """ler | fazer | aprovar | bloqueada — o que acontece quando o agente chama `nome`."""
    from command_center.api import acoes, ia
    if nome in LEITURAS or acoes.eh_consulta(nome) or nome.startswith(("urace_", "kommo_")):
        return "ler"
    if ia._politica(con, nome) == "BLOCKED":
        return "bloqueada"
    if RX_APROVAR.search(nome):
        return "aprovar"
    return "fazer"


_CHAVES_ALVO = ("email", "para", "to", "nome", "cliente", "cliente_nome", "piloto", "assunto", "subject",
                "gid", "id", "invoice_id", "envelope_id", "cliente_id", "conta")


def resumo(nome, args):
    """Uma linha legível do que a ferramenta faria — é o que aparece no cartão de aprovar."""
    a = args if isinstance(args, dict) else {}
    partes = [f"{k}: {a[k]}" for k in _CHAVES_ALVO if a.get(k) not in (None, "", [])][:4]
    linhas = a.get("linhas")
    if isinstance(linhas, list) and linhas:
        total = sum((l.get("quantidade") or 1) * (l.get("unitario") or 0) for l in linhas if isinstance(l, dict))
        partes.append(f"total: ${total:,.2f}")
    return f"{nome} — " + ("; ".join(partes) if partes else json.dumps(a, ensure_ascii=False)[:160])


def pedir_aprovacao(con, command_id, nome, args):
    """Cria o cartão de aprovar (ou reaproveita o que já existe). Devolve a frase que volta ao agente."""
    from command_center.api import acoes, ia
    assin = acoes.assinatura(nome, args, resumo(nome, args))
    estado, antiga = acoes.ja_decidida(con, assin)
    if estado == "feita":
        return (f"Não executei: '{nome}' com estes dados já foi aprovada ou feita (ação #{antiga['id']}). "
                "Não repita; diga ao dono que já está feito.")
    if estado == "pendente":
        return (f"Não executei: '{nome}' com estes dados já está esperando aprovação no painel (ação #{antiga['id']}). "
                "Não chame de novo; diga ao dono que está esperando o aprovar.")
    pol = ia._politica(con, nome)
    aid = inserir(con, "ai_actions", command_id=command_id, action=nome,
                  system=nome.split("_")[0] if "_" in nome else None,
                  policy="REQUIRES_APPROVAL" if pol != "BLOCKED" else "BLOCKED",
                  status="PROPOSED" if pol != "BLOCKED" else "BLOCKED",
                  payload=json.dumps({"alvo": resumo(nome, args), "descricao": resumo(nome, args), "fonte": "agente_sdk",
                                      "args": args, "assinatura": assin}, ensure_ascii=False),
                  reason="sai da empresa ou não volta atrás: um clique para aprovar")
    inserir(con, "approvals", action_id=aid)
    return (f"Não executei: '{nome}' sai da empresa ou não volta atrás. Criei o pedido de aprovação #{aid} no painel "
            "(um clique) com exatamente estes argumentos; quem aprovar executa. Não chame de novo nem tente outro "
            "caminho: siga com o resto e diga ao dono que está esperando o aprovar.")


def registrar_feita(con, command_id, nome, args, resposta):
    """Trabalho interno que o agente fez direto: fica no histórico do comando, como ação feita."""
    from command_center.api import acoes
    texto = resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False, default=str)
    aid = inserir(con, "ai_actions", command_id=command_id, action=nome,
                  system=nome.split("_")[0] if "_" in nome else None, policy="SAFE", status="DONE",
                  payload=json.dumps({"alvo": resumo(nome, args), "descricao": resumo(nome, args), "fonte": "agente_sdk",
                                      "args": args, "assinatura": acoes.assinatura(nome, args, resumo(nome, args))},
                                     ensure_ascii=False),
                  reason="trabalho interno: feito direto pela IA", result=(texto or "")[:2000], finished_at=agora())
    return aid


def _dentro(caminho, pastas):
    real = os.path.realpath(caminho if os.path.isabs(caminho) else os.path.join(CEREBRO, caminho))
    for p in pastas:
        p = os.path.realpath(p)
        if real == p or real.startswith(p + os.sep):
            return True
    return False


def leitura_permitida(ferramenta, args, pastas=None):
    """Read/Glob/Grep só no cérebro, nas skills e no contexto do dono. Nada de `..` em padrão."""
    pastas = pastas or pastas_de_leitura()
    a = args or {}
    alvo = a.get("file_path") or a.get("path") or "."
    if not _dentro(alvo, pastas):
        return False
    padrao = a.get("pattern") if ferramenta == "Glob" else a.get("glob")
    if padrao and (".." in padrao or os.path.isabs(padrao)):
        return False
    return True


def _negar(motivo):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": motivo}}


class Portao:
    """Os ganchos PreToolUse/PostToolUse de UMA execução (sabe de que comando é)."""

    def __init__(self, command_id=None, ferramentas=True, user_id=None):
        self.command_id = command_id
        self.ferramentas = ferramentas
        self.user_id = user_id
        self.aprovar = []                 # ids dos cartões criados nesta execução
        self.feitas = []

    def decidir(self, nome_cru, args):
        """None = pode rodar; texto = motivo para não rodar (o agente lê)."""
        if nome_cru in ("Read", "Glob", "Grep"):
            return None if leitura_permitida(nome_cru, args) else (
                "Só dá para ler o cérebro (brain/), as skills e os arquivos de contexto do painel.")
        if nome_cru in ("WebSearch", "WebFetch", "ToolSearch"):
            return None
        if not nome_cru.startswith("mcp__") or not self.ferramentas:
            return f"'{nome_cru}' não está liberada para o AI Command."
        nome = nome_da_ferramenta(nome_cru)
        con = conectar()
        try:
            tipo = classificar(con, nome)
            if tipo in ("ler", "fazer"):
                return None
            if tipo == "bloqueada":
                auditar(con, "ai.tool.blocked", "ai:agente_sdk", entity_type="ai_command", entity_id=self.command_id,
                        detail={"ferramenta": nome})
                return f"'{nome}' é bloqueada pela política do painel: não faça e diga ao dono que precisa ser feito à mão."
            if self.command_id is None:
                return f"'{nome}' precisa de aprovação, e esta execução não tem comando no painel."
            msg = pedir_aprovacao(con, self.command_id, nome, args)
            self.aprovar.append(nome)
            return msg
        finally:
            con.close()

    def registrar(self, nome_cru, args, resposta):
        if not nome_cru.startswith("mcp__") or self.command_id is None:
            return
        nome = nome_da_ferramenta(nome_cru)
        con = conectar()
        try:
            if classificar(con, nome) == "fazer":
                self.feitas.append(registrar_feita(con, self.command_id, nome, args, resposta))
        finally:
            con.close()

    async def antes(self, entrada, tool_use_id, contexto):
        motivo = await asyncio.to_thread(self.decidir, entrada.get("tool_name") or "", entrada.get("tool_input") or {})
        return _negar(motivo) if motivo else {}

    async def depois(self, entrada, tool_use_id, contexto):
        try:
            await asyncio.to_thread(self.registrar, entrada.get("tool_name") or "", entrada.get("tool_input") or {},
                                    entrada.get("tool_response"))
        except Exception as e:                     # registrar nunca derruba a execução
            log.warning("ai.registrar falhou: %s", e)
        return {}


# ------------------------------------------------------------ as ferramentas
def servidores_mcp():
    """Os servidores do adminai cuja credencial existe. Sem credencial, o servidor fica de fora."""
    saida = {}
    env = {"APLICAR": "1"}
    if os.environ.get("URACE_ENV"):
        env["URACE_ENV"] = os.environ["URACE_ENV"]
    for nome, script in SERVIDORES.items():
        try:
            providers.modulo(nome)
        except Exception:
            continue
        saida[nome] = {"type": "stdio", "command": sys.executable,
                       "args": [os.path.join(providers.MCP_DIR, script)], "env": env}
    return saida


def ferramentas_do_painel():
    """As leituras do painel (urace_*), as mesmas do conector, numa conexão só de leitura.
    `urace_operacoes` e `urace_api` ficam de fora: operar o painel pede a credencial de uma pessoa."""
    from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server

    from command_center.api import mcp_http
    from command_center.db import conectar_somente_leitura

    def fabrica(fn):
        def chamar(args):
            con = conectar_somente_leitura()
            try:
                return fn(con, **(args or {}))
            finally:
                con.close()

        async def handler(args):
            try:
                res = await asyncio.to_thread(chamar, args)
                return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)[:20000]}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"{type(e).__name__}: {str(e)[:300]}"}], "is_error": True}
        return handler

    lista = []
    for nome, (descricao, props, obrig, fn) in mcp_http.FERRAMENTAS.items():
        if nome in ("urace_operacoes", "urace_api"):
            continue
        lista.append(SdkMcpTool(name=nome, description=descricao,
                                input_schema={"type": "object", "properties": props, "required": obrig},
                                handler=fabrica(fn)))
    return create_sdk_mcp_server(NOME_PAINEL, "1.0.0", lista)


def ferramentas_dos_suits(user_id=None):
    """A aba Suits (#153) para o agente: ler, registrar, atualizar e anotar pedidos de macacão.
    Conexão normal (escreve): é trabalho interno, e o portão registra cada escrita como ação feita."""
    from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server

    from command_center.api import suits

    def fabrica(fn):
        def chamar(args):
            con = conectar()
            try:
                return fn(con, user_id, **(args or {}))
            finally:
                con.close()

        async def handler(args):
            try:
                res = await asyncio.to_thread(chamar, args)
                return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)[:20000]}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"{type(e).__name__}: {str(e)[:300]}"}], "is_error": True}
        return handler

    return create_sdk_mcp_server(NOME_SUITS, "1.0.0", [
        SdkMcpTool(name=nome, description=desc, input_schema={"type": "object", "properties": props, "required": obrig},
                   handler=fabrica(fn))
        for nome, desc, props, obrig, fn in suits.ferramentas_ia()])


# ---------------------------------------------------------------- instruções
def hoje():
    return datetime.now(FUSO)


def instrucoes():
    d = hoje()
    return f"""Você é a IA de operação da URACE (kart racing em Orlando, Flórida), dentro do Command Center, falando com a equipe pelo painel. Trabalhe como um colega experiente: entenda o pedido, pesquise o que precisar, faça e entregue pronto.

HOJE: {d.strftime('%A, %Y-%m-%d %H:%M')} no fuso da Flórida (America/New_York). Toda data e hora é nesse fuso.

O CÉREBRO é a memória da empresa (processos, clientes, equipe, fornecedores, preços, regras, sistemas), em {CEREBRO}. Comece por URACE.md e 00_SYSTEM/PARAMETROS.md; os processos estão em 10_PROCESSOS e as pessoas e empresas em 20_ENTIDADES. Um link [[Nome]] é o arquivo Nome.md (ache com Glob "**/Nome.md"). Consulte o cérebro sempre que o pedido envolver processo, cliente, fornecedor, preço ou regra. As skills ({SKILLS}) explicam como usar cada sistema. Os dois são só leitura.

COMO TRABALHAR
- Leia antes de perguntar: QuickBooks (todas as invoices, clientes, itens e o histórico de preços), Asana, Gmail, DocuSign, Kommo, o painel (urace_*), a web e o cérebro. Nunca diga que não tem acesso a uma leitura sem tentar.
- Faça direto o trabalho interno: tarefa, comentário e seção no Asana; cliente, item, invoice e estimate no QuickBooks SEM enviar; rascunho de e-mail; marcador no Gmail.
- O que sai da empresa ou não volta atrás (enviar invoice, waiver, lembrete ou e-mail; apagar; anular; unir cards; mudar preço do catálogo; pagamento; recorrência): chame a ferramenta normalmente. O painel não executa: transforma num "aprovar" de um clique e te devolve o número. Não insista nem procure outro caminho.
- Só pergunte o que realmente impede agir, numa lista curta, e pare.

REGRAS DO DONO (valem sempre)
- NO FAKE DATA: nunca invente valor, nome, e-mail, id, data ou link. Se não achou, diga que não achou.
- Nunca coloque o serviço de um cliente no card ou na tarefa de outro.
- Não use Turo nem Hostaway.
- Preço: serviço pelo Rate Card; peça pelo último valor cobrado no QuickBooks (qbo_historico_precos ou urace_precos_cobrados). Só pergunte o preço do que não estiver em nenhum dos dois. O valor que o dono disser manda.
- Invoice: cliente_id do RESPONSÁVEL no QuickBooks; linhas com item_id do catálogo, quantidade, unitário (nunca 0) e descrição "serviço - piloto - data"; vence 2 dias antes do serviço.
- Serviço novo é uma tarefa NOVA no quadro com os dados do cliente: diga "criar", nunca "recriar".
- Não refaça o que já foi feito ou aprovado hoje (o contexto do painel, abaixo do pedido, diz o que já foi).
- Macacão (Suits / Alpha Line): o pedido vive na aba Suits (suits_*); o processo está em 10_PROCESSOS/Pedido de macacão.md. Com o cliente e o designer, escreva no idioma do cliente, educado e comercial (ainda é venda) e respeite o que ele pediu; o designer recebe só o design, nunca pagamento ou contato do cliente.

COMO RESPONDER
- Português do Brasil, direto, frases curtas, sem jargão interno: não cite nomes de ferramenta, ids de template nem regras do painel.
- No fim: o que você fez (uma linha por coisa, com o link quando houver) e o que ficou esperando aprovação."""


def instrucoes_email():
    d = hoje()
    return f"""Você faz a triagem e a classificação de e-mail da URACE (kart racing em Orlando, Flórida). Hoje é {d.strftime('%Y-%m-%d')} no fuso da Flórida.
O cérebro da empresa está em {CEREBRO} (só leitura, com Read/Glob/Grep): consulte 10_PROCESSOS/Triagem de e-mail.md e 20_ENTIDADES quando precisar saber quem é um cliente, fornecedor ou parceiro.
Responda EXATAMENTE no formato que o pedido mandar, sem texto antes ou depois. Se não tiver certeza de um item, siga a regra do pedido para incerteza (normalmente null): outra IA, mais forte, revisa esses casos."""


# ------------------------------------------------------------------ execução
def disponivel():
    """O SDK está instalado e há credencial da Anthropic no ambiente do serviço."""
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))


def _sessao_salva(session_key):
    if not session_key:
        return None
    con = conectar()
    try:
        r = um(con, "SELECT sdk_session FROM ai_sdk_sessions WHERE session_key=?", (session_key,))
        return r["sdk_session"] if r else None
    finally:
        con.close()


def _guardar_sessao(session_key, sessao):
    if not session_key or not sessao:
        return
    con = conectar()
    try:
        con.execute("""INSERT INTO ai_sdk_sessions (session_key, sdk_session, updated_at) VALUES (?,?,?)
                       ON CONFLICT(session_key) DO UPDATE SET sdk_session=excluded.sdk_session, updated_at=excluded.updated_at""",
                    (session_key, sessao, agora()))
    finally:
        con.close()


def _opcoes(modelo, sistema, portao, limite, retomar, max_turnos):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
    servidores = {}
    if portao.ferramentas:
        servidores = servidores_mcp()
        servidores[NOME_PAINEL] = ferramentas_do_painel()
        servidores[NOME_SUITS] = ferramentas_dos_suits(portao.user_id)
    permitidas = list(FERRAMENTAS_EMBUTIDAS) + [f"mcp__{n}__*" for n in servidores]
    return ClaudeAgentOptions(
        model=modelo,
        system_prompt=sistema,
        tools=list(FERRAMENTAS_EMBUTIDAS),
        allowed_tools=permitidas,
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit", "Agent", "Task"],
        permission_mode="dontAsk",            # o que não está liberado é recusado, nunca perguntado
        mcp_servers=servidores,
        strict_mcp_config=True,
        setting_sources=[],                   # nada de configuração de disco: só o que está aqui
        cwd=CEREBRO,
        add_dirs=[d for d in pastas_de_leitura() if os.path.isdir(d)],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[portao.antes])],
               "PostToolUse": [HookMatcher(matcher=None, hooks=[portao.depois])]},
        max_budget_usd=limite,
        max_turns=max_turnos,
        effort=ESFORCO,
        resume=retomar,
        env={"TZ": "America/New_York"},
    )


def _fabrica_cliente(opcoes):
    from claude_agent_sdk import ClaudeSDKClient
    return ClaudeSDKClient(options=opcoes)


async def _conversar(prompt, opcoes):
    textos, fim, sessao = [], None, None
    async with _fabrica_cliente(opcoes) as cliente:
        await cliente.query(prompt)
        async for m in cliente.receive_response():
            tipo = type(m).__name__
            if tipo == "AssistantMessage":
                for b in getattr(m, "content", None) or []:
                    if type(b).__name__ == "TextBlock" and (getattr(b, "text", "") or "").strip():
                        textos.append(b.text.strip())
            elif tipo == "ResultMessage":
                fim = m
                sessao = getattr(m, "session_id", None)
    return textos, fim, sessao


NOTA_LIMITE = "\n\n(Parei aqui: este pedido chegou ao limite de US$ {:.0f}. Se quiser que eu continue, é só pedir.)"
NOTA_TURNOS = "\n\n(Parei aqui: o pedido ficou longo demais para uma vez só. Se quiser que eu continue, é só pedir.)"


def _resultado(textos, fim, sessao, limite):
    if fim is None:
        return Resultado(False, "", "o agente terminou sem resposta", sessao=sessao)
    custo = getattr(fim, "total_cost_usd", None)
    sub = getattr(fim, "subtype", None)
    parcial = textos[-1] if textos else ""
    if sub == "success" and not getattr(fim, "is_error", False):
        return Resultado(True, (getattr(fim, "result", None) or parcial or "").strip(), None, sub, custo, sessao)
    if sub == "error_max_budget_usd":
        return Resultado(True, (parcial + NOTA_LIMITE.format(limite)).strip(), None, sub, custo, sessao)
    if sub == "error_max_turns":
        return Resultado(True, (parcial + NOTA_TURNOS).strip(), None, sub, custo, sessao)
    erros = getattr(fim, "errors", None) or []
    erro = "; ".join(str(e) for e in erros) or getattr(fim, "result", None) or sub or "erro do agente"
    return Resultado(False, parcial, str(erro)[:2000], sub, custo, sessao)


def rodar(prompt, session_key=None, *, modelo=None, sistema=None, command_id=None, ferramentas=True,
          limite=None, max_turnos=60, user_id=None):
    """Uma execução completa do agente. Bloqueia (chame de uma thread). Nunca levanta."""
    modelo = modelo or MODELO
    limite = LIMITE_USD if limite is None else limite
    portao = Portao(command_id, ferramentas, user_id)
    retomar = _sessao_salva(session_key)
    prompt = prompt.replace("/workspace/contexto/", _contexto_dir().rstrip("/") + "/")
    inicio = datetime.now()
    res = None
    for tentativa in (retomar, None) if retomar else (None,):
        try:
            opcoes = _opcoes(modelo, sistema or instrucoes(), portao, limite, tentativa, max_turnos)
            textos, fim, sessao = asyncio.run(asyncio.wait_for(_conversar(prompt, opcoes), TIMEOUT))
            res = _resultado(textos, fim, sessao, limite)
            if res.ok or not tentativa:
                break
        except asyncio.TimeoutError:
            res = Resultado(False, "", f"o agente não respondeu em {TIMEOUT}s")
            break
        except Exception as e:                       # sessão antiga sumida, CLI que não subiu…
            res = Resultado(False, "", f"{type(e).__name__}: {str(e)[:1500]}")
            if not tentativa:
                break
    if res.sessao:
        _guardar_sessao(session_key, res.sessao)
    log.info("ai.run", extra={"evento": "ai.run", "modelo": modelo, "comando": command_id, "ok": res.ok,
                              "subtipo": res.subtipo, "custo_usd": res.custo,
                              "segundos": round((datetime.now() - inicio).total_seconds(), 1),
                              "aprovar": len(portao.aprovar), "feitas": len(portao.feitas)})
    return res


def runner(texto, session_key=None):
    """O contrato antigo (ok, saida, erro), no Opus, sem ferramentas que escrevem: só o cérebro e a web.
    Cada chamada é independente (sem retomar sessão): são lotes de JSON, e o histórico só encareceria."""
    r = rodar(texto, None, ferramentas=False, max_turnos=20)
    return r.ok, r.texto, r.erro


def dificuldade(texto):
    """O Haiku teve dificuldade? Sem JSON legível, ou com item que ele deixou sem decisão."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return True
    try:
        dados = json.loads(m.group(0))
    except ValueError:
        return True
    itens = dados.get("itens") if isinstance(dados, dict) else None
    if isinstance(itens, list):
        for it in itens:
            if not isinstance(it, dict):
                return True
            for chave in ("principal", "marcador"):
                if chave in it and it[chave] in (None, "", "null"):
                    return True
            if it.get("duvida"):
                return True
    return False


def runner_email(texto, session_key=None):
    """E-mail: o Haiku primeiro; se ele tiver dificuldade, o Opus refaz o mesmo lote. Os dois leem o cérebro.
    Cada lote é independente (sem retomar sessão), como em `runner`."""
    r = rodar(texto, None, modelo=MODELO_EMAIL, sistema=instrucoes_email(),
              ferramentas=False, limite=LIMITE_EMAIL_USD, max_turnos=10)
    if r.ok and not dificuldade(r.texto):
        return True, r.texto, None
    log.info("ai.email.escalada", extra={"evento": "ai.email.escalada", "motivo": r.erro or "dificuldade"})
    r2 = rodar(texto, None, modelo=MODELO, sistema=instrucoes_email(),
               ferramentas=False, limite=LIMITE_EMAIL_USD * 2, max_turnos=10)
    if r2.ok:
        return True, r2.texto, None
    if r.ok:                                         # o Opus falhou: a resposta do Haiku ainda serve
        return True, r.texto, None
    return False, "", r2.erro or r.erro
