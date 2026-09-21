#!/usr/bin/env python3
"""Servidor MCP do próprio Command Center — para um Claude de fora consultar o painel.

Dono, 21/09: *"preciso montar uma chave api desse command center"* → *"vai ser um Claude
provavelmente"*. Chave crua serve para script; um Claude fala MCP. Então este servidor
traduz as consultas do painel em ferramentas, usando a chave de API por baixo.

**Só leitura, por construção.** Não existe aqui nenhuma ferramenta que escreva — nem
responder no chat, nem mudar preço, nem criar cliente. Isso não é confiança no modelo:
a ferramenta que não deve existir simplesmente não é registrada, e o modelo não tem como
desobedecer. A chave que alimenta isto também deve ser criada como **só leitura** no
painel; as duas travas valem juntas, de propósito.

O que **não** está aqui e é bom lembrar: o Command Center já tem a IA de dentro, com
política por ação e portão de APLICAR. Um Claude de fora é outra coisa — é um leitor.
Se um dia ele precisar agir, o caminho certo é propor ação no painel para uma pessoa
aprovar, não ganhar uma chave que escreve.

Ambiente (nunca no código, nunca no repositório):

    CC_API_KEY=urk_...        chave criada em Usuários → Chaves de API
    CC_URL=https://urace-bridge.duckdns.org      (padrão)

Lidos do ambiente ou de ~/.urace/command-center.env (ou URACE_ENV).

Ligar no Claude Code:

    claude mcp add urace-cc --env CC_API_KEY=urk_... -- \
      /home/ubuntu/.urace/cc-venv/bin/python \
      /home/ubuntu/Uraceagent/adminai/mcp/command_center_mcp.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import ErroFerramenta, Servidor, log  # noqa: E402

PADRAO_URL = "https://urace-bridge.duckdns.org"
TEMPO_LIMITE = 45


# ------------------------------------------------------------- ambiente
def _carregar_env():
    caminho = os.environ.get("URACE_ENV", os.path.expanduser("~/.urace/command-center.env"))
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("CC_API_KEY"):
        sys.exit(f"ERRO: falta CC_API_KEY (ambiente ou {caminho}). "
                 "Crie a chave em Usuários → Chaves de API, com 'só leitura' marcado.")


def _base():
    return (os.environ.get("CC_URL") or PADRAO_URL).rstrip("/")


# ------------------------------------------------------------- HTTP (só GET)
def _pegar(caminho, params=None):
    """GET em /ops/api. Não existe verbo de escrita neste arquivo — de propósito."""
    if not caminho.startswith("/"):
        caminho = "/" + caminho
    limpos = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    url = f"{_base()}/ops/api{caminho}" + (f"?{urllib.parse.urlencode(limpos)}" if limpos else "")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {os.environ['CC_API_KEY']}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as r:
            bruto = r.read()
    except urllib.error.HTTPError as e:
        corpo = e.read()[:300].decode("utf-8", "replace")
        if e.code == 401:
            raise ErroFerramenta("a chave não foi aceita: pode estar revogada, vencida, ou a pessoa "
                                 "dela foi desativada. Crie outra em Usuários → Chaves de API.")
        if e.code == 403:
            raise ErroFerramenta(f"a chave não tem acesso a isto: {corpo}")
        raise ErroFerramenta(f"HTTP {e.code} em {caminho}: {corpo}")
    except urllib.error.URLError as e:
        raise ErroFerramenta(f"não consegui falar com o Command Center ({_base()}): {e.reason}")
    try:
        return json.loads(bruto)
    except ValueError:
        raise ErroFerramenta(f"{caminho} não devolveu JSON (o painel pode estar em manutenção)")


srv = Servidor("urace-command-center", "0.1")


# ------------------------------------------------------------- o dia
@srv.ferramenta("cc_dashboard", "Números do dia no Command Center da URACE: vendas, clientes, "
                                "tarefas, waivers, e-mails e estado das integrações. Só leitura.")
def cc_dashboard():
    return _pegar("/dashboard")


@srv.ferramenta("cc_atencao", "O que precisa de ação humana hoje, já priorizado pelo painel "
                              "(waiver parada, invoice vencida, conversa sem resposta, mensagem não "
                              "entregue…). É a melhor primeira pergunta sobre o estado do negócio.")
def cc_atencao():
    return _pegar("/needs-attention")


# ------------------------------------------------------------- dinheiro
@srv.ferramenta("cc_invoices", "Invoices da URACE (QuickBooks espelhado no painel): quem deve, "
                               "quanto, desde quando.", {"status": {"type": "string",
                "description": "opcional: OPEN, PAID, OVERDUE"}})
def cc_invoices(status=None):
    return _pegar("/invoices", {"status": status})


@srv.ferramenta("cc_financeiro", "Resumo do QuickBooks: contas, faturamento e o que o painel "
                                 "conseguiu ler da conta da empresa.")
def cc_financeiro():
    return _pegar("/qbo/summary")


@srv.ferramenta("cc_oportunidades", "Funil de vendas do painel: oportunidades por etapa, valor e dono.")
def cc_oportunidades():
    return _pegar("/sales/board")


# ------------------------------------------------------------- gente
@srv.ferramenta("cc_clientes", "Clientes da URACE. Sem busca, devolve a lista; com `busca`, filtra "
                               "por nome, e-mail ou telefone.", {"busca": {"type": "string"}})
def cc_clientes(busca=None):
    return _pegar("/clients", {"q": busca})


@srv.ferramenta("cc_cliente", "Um cliente inteiro: dados, piloto, equipamento, waivers, invoices e "
                              "histórico.", {"id": {"type": "integer"}}, ["id"])
def cc_cliente(id):
    return _pegar(f"/clients/{int(id)}")


@srv.ferramenta("cc_corridas", "Corridas e eventos da URACE no calendário do painel.")
def cc_corridas():
    return _pegar("/races")


# ------------------------------------------------------------- conversas
@srv.ferramenta("cc_conversas", "Caixa de entrada do chat (Instagram, Facebook, WhatsApp pelo Kommo): "
                                "quem falou por último e quem espera resposta.")
def cc_conversas():
    return _pegar("/crm/inbox")


@srv.ferramenta("cc_conversa", "Uma conversa inteira, mensagem a mensagem, com o estado de entrega "
                               "de cada resposta nossa.", {"lead_id": {"type": "integer"}}, ["lead_id"])
def cc_conversa(lead_id):
    return _pegar(f"/crm/leads/{int(lead_id)}")


# ------------------------------------------------------------- registro
@srv.ferramenta("cc_auditoria", "Registro imutável do painel: logins, comandos, decisões, mudanças de "
                                "política e de preço. Para entender o que aconteceu e quem fez.",
                {"limite": {"type": "integer", "default": 100}})
def cc_auditoria(limite=100):
    # não dizer nada é 100; dizer um número é respeitado dentro do teto do painel (500)
    n = 100 if limite in (None, "") else max(1, min(int(limite), 500))
    return _pegar("/audit", {"limit": n})


@srv.ferramenta("cc_buscar", "Busca geral do painel (clientes, tarefas, e-mails, conversas) pelo "
                             "mesmo caminho que a barra de busca usa.", {"texto": {"type": "string"}}, ["texto"])
def cc_buscar(texto):
    return _pegar("/search", {"q": texto})


@srv.ferramenta("cc_consultar", "Escape: qualquer consulta GET da API do painel, quando nenhuma "
                                "ferramenta acima serve. Ex.: '/crm/board', '/tasks?status=all'. "
                                "Só GET — não existe escrita neste servidor.",
                {"caminho": {"type": "string", "description": "caminho depois de /ops/api"}}, ["caminho"])
def cc_consultar(caminho):
    if "://" in caminho or caminho.strip().startswith("//"):
        raise ErroFerramenta("passe só o caminho de dentro da API, como '/clients'")
    return _pegar(caminho)


if __name__ == "__main__":
    _carregar_env()
    log("Command Center em", _base(), "| chave", os.environ["CC_API_KEY"][:8] + "…(oculta)")
    srv.rodar()
