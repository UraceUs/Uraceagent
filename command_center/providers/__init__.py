"""Providers do Command Center = os servidores MCP que já existem.

`adminai/mcp/{asana,docusign,gmail}_mcp.py` são importados como módulo.
As regras do dono (ADM URACE só leitura, Matt tasks intocável, envio
recusado em demo, arquivar só com wNews…) já estão dentro deles — o
Command Center não as reimplementa, e não tem como contorná-las.

Sem credencial, o provider responde "not connected". Nunca dado falso.
"""
import importlib
import os
import sys
import traceback

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MCP_DIR = os.path.join(REPO, "adminai", "mcp")
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

SISTEMAS = ("asana", "docusign", "gmail", "quickbooks", "kommo")


class NaoConectado(Exception):
    """Credencial ausente ou inválida. A tela mostra 'Integration not connected'."""


_mods = {}


def _carregar(nome):
    """Importa o servidor MCP e roda o carregamento de ambiente dele.
    Os módulos chamam sys.exit quando falta credencial: aqui isso vira
    NaoConectado, que a API traduz em 'not connected' — sem derrubar nada."""
    if nome in _mods:
        if isinstance(_mods[nome], Exception):
            raise _mods[nome]
        return _mods[nome]
    try:
        m = importlib.import_module(f"{nome}_mcp")
        m._carregar_env()
        if hasattr(m, "_carregar_contas"):
            m._carregar_contas()
        _mods[nome] = m
        return m
    except SystemExit as e:
        _mods[nome] = NaoConectado(str(e))
        raise _mods[nome]
    except Exception as e:
        _mods[nome] = NaoConectado(f"{type(e).__name__}: {e}")
        raise _mods[nome]


def recarregar():
    """Depois de credencial nova, esquecer o cache."""
    _mods.clear()
    for k in list(sys.modules):
        if k.endswith("_mcp") or k == "mcp_stdio":
            del sys.modules[k]


def chamar(sistema, ferramenta, **args):
    """Chama uma ferramenta do provider. Erros de negócio (ErroFerramenta)
    viram texto para o chamador; falta de credencial vira NaoConectado."""
    m = _carregar(sistema)
    fn = getattr(m, ferramenta, None)
    if fn is None:
        raise AttributeError(f"{sistema}.{ferramenta} não existe")
    try:
        return fn(**args)
    except Exception as e:  # ErroFerramenta dos MCP herda de Exception
        if type(e).__name__ == "ErroFerramenta":
            raise
        traceback.print_exc(file=sys.stderr)
        raise


# ------------------------------------------------------------ saúde
def saude(sistema):
    """CONNECTED / DISCONNECTED / ERROR + detalhe. Faz UMA chamada leve real."""
    try:
        if sistema == "asana":
            r = chamar("asana", "asana_projetos")
            return "CONNECTED", {"projetos": len(r)}
        if sistema == "docusign":
            r = chamar("docusign", "docusign_ambiente")
            return "CONNECTED", {"ambiente": r.get("ambiente"), "usuario": r.get("usuario"),
                                 "envio_permitido": r.get("envio_permitido")}
        if sistema == "gmail":
            r = chamar("gmail", "gmail_contas")
            contas = r.get("contas", {})
            ok = [k for k, v in contas.items() if v.get("ok")]
            if not ok:
                return "ERROR", {"contas": contas}
            return ("CONNECTED" if len(ok) == len(contas) else "DEGRADED"), {"contas": contas}
        if sistema == "quickbooks":
            r = chamar("quickbooks", "qbo_empresa")
            return "CONNECTED", {"empresa": r.get("empresa"), "realm_id": r.get("realm_id"), "envio_permitido": r.get("envio_permitido")}
        if sistema == "kommo":
            r = chamar("kommo", "kommo_conta")
            return "CONNECTED", {"conta": r.get("nome"), "subdominio": r.get("subdominio"),
                                 "funis": r.get("funis"), "responder_habilitado": r.get("responder_habilitado")}
        return "DISCONNECTED", {"nota": "sistema desconhecido"}
    except NaoConectado as e:
        return "DISCONNECTED", {"motivo": str(e)}
    except Exception as e:
        return "ERROR", {"motivo": f"{type(e).__name__}: {str(e)[:200]}"}


def modulo(sistema):
    """O módulo do MCP em si, para as portas humanas (funções que não são
    ferramentas do agente). Levanta NaoConectado como `chamar`."""
    return _carregar(sistema)
