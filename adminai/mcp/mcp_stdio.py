#!/usr/bin/env python3
"""Servidor MCP mínimo por stdio, sem dependência nenhuma.

Por que existe: o OpenClaw desta instalação só faz OAuth com registro
dinâmico de cliente, e Asana/DocuSign exigem app pré-registrado. Os
servidores oficiais ficaram fora de alcance; este é o esqueleto dos
nossos. Fala o protocolo MCP diretamente (JSON-RPC 2.0, uma mensagem
por linha), o suficiente para `initialize`, `tools/list` e `tools/call`.

A vantagem que se ganha com servidor próprio não é técnica: é que as
regras do dono viram código. A ferramenta que não deve existir --
enviar invoice, apagar tarefa -- simplesmente não é registrada. O
modelo não precisa obedecer; ele não tem como desobedecer.

Uso, num servidor concreto:

    srv = Servidor("urace-asana", "0.1")

    @srv.ferramenta("asana_tarefa", "Lê uma tarefa pelo gid",
                    {"gid": {"type": "string"}}, obrigatorios=["gid"])
    def tarefa(gid):
        ...
        return {"nome": ...}       # dict/list vira JSON; str vai como está

    srv.rodar()

stdout é SÓ protocolo. Qualquer log vai para stderr.
"""
import json
import sys
import traceback

PROTOCOLO_PADRAO = "2025-06-18"
PROTOCOLOS_ACEITOS = {"2024-11-05", "2025-03-26", "2025-06-18"}


def log(*partes):
    print("[mcp]", *partes, file=sys.stderr, flush=True)


# --------------------------------------------------------------- assinatura
# Dono, 21/09, depois de descobrir tarefa de agente no Asana dele sem saber de quem era:
# *"tudo que for feito pelo command center de agora em diante tem que ter a assinatura
# by Urace Ai agent"*.
#
# Um lugar só, usado por todo caminho que escreve em sistema de fora. Quem lê a tarefa, a
# anotação ou o comentário sabe na hora o que veio do painel e o que veio de gente.
#
# **Onde NÃO se assina, e por quê:** o que chega ao cliente com cara de pessoa. Resposta
# no chat do Kommo é o texto que o dono digitou, não da IA; invoice e waiver saem no nome
# da empresa. Carimbar "Ai agent" ali mudaria o que o cliente entende da conversa — isso é
# decisão de negócio, não de código, e ficou perguntada em vez de assumida.
AGENTE = "URACE AI Agent"
ASSINATURA = f"by {AGENTE}"
FUSO = "America/New_York"                      # tudo no sistema roda no fuso da Flórida


def agora_local():
    """Data e hora na Flórida, do jeito que o dono lê: 21/09/2026 15:42 (EDT)."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        t = datetime.now(ZoneInfo(FUSO))
        return t.strftime("%d/%m/%Y %H:%M ") + f"({t.strftime('%Z')})"
    except Exception:                          # noqa: BLE001 — sem tzdata, a hora ainda sai
        return datetime.now().strftime("%d/%m/%Y %H:%M")


def assinar(texto, marca=ASSINATURA):
    """Acrescenta a assinatura ao fim, em linha própria. Idempotente: texto que já tem a
    marca volta igual — senão a mesma tarefa editada três vezes ganharia três carimbos.

    A checagem é pelo NOME do agente, não pela frase inteira: assim um texto que já diz
    "Criado pelo URACE AI Agent em 21/09" também não ganha um segundo carimbo."""
    corpo = (texto or "").rstrip()
    if AGENTE.lower() in corpo.lower():
        return corpo or None
    return (corpo + "\n\n" + marca).strip() if corpo else marca


def rastro(o_que):
    """A frase que fica no Asana quando o painel faz alguma coisa em OUTRO sistema.

    Dono, 21/09: *"moveu uma tarefa, coloca um comentário dizendo que foi movido tal dia,
    tal hora, pelo agente de IA"* — e o mesmo para invoice e waiver enviadas. É o que
    transforma o Asana no diário do que o agente fez, em vez de só assinar o que ele
    escreve. Uso: rastro("Movida para QUA") → "Movida para QUA em 21/09/2026 15:42 (EDT)
    pelo URACE AI Agent"."""
    return f"{o_que} em {agora_local()} pelo {AGENTE}"


class ErroFerramenta(Exception):
    """Erro que o modelo deve ler como resultado, não como falha do servidor."""


class Servidor:
    def __init__(self, nome, versao):
        self.nome = nome
        self.versao = versao
        self._ferramentas = {}   # nome -> (descricao, schema, funcao)

    def ferramenta(self, nome, descricao, propriedades=None, obrigatorios=None):
        schema = {
            "type": "object",
            "properties": propriedades or {},
            "required": obrigatorios or [],
            "additionalProperties": False,
        }

        def registrar(fn):
            self._ferramentas[nome] = (descricao, schema, fn)
            return fn
        return registrar

    # ------------------------------------------------------------ protocolo
    def _responder(self, id_, resultado=None, erro=None):
        msg = {"jsonrpc": "2.0", "id": id_}
        if erro is not None:
            msg["error"] = erro
        else:
            msg["result"] = resultado
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _tratar(self, req):
        metodo = req.get("method")
        id_ = req.get("id")
        params = req.get("params") or {}

        # notificações não têm id e não recebem resposta
        if id_ is None:
            return

        if metodo == "initialize":
            pedido = params.get("protocolVersion")
            versao = pedido if pedido in PROTOCOLOS_ACEITOS else PROTOCOLO_PADRAO
            self._responder(id_, {
                "protocolVersion": versao,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.nome, "version": self.versao},
            })
        elif metodo == "ping":
            self._responder(id_, {})
        elif metodo == "tools/list":
            self._responder(id_, {"tools": [
                {"name": n, "description": d, "inputSchema": s}
                for n, (d, s, _) in self._ferramentas.items()
            ]})
        elif metodo == "tools/call":
            self._chamar(id_, params.get("name"), params.get("arguments") or {})
        else:
            self._responder(id_, erro={"code": -32601,
                                       "message": f"método desconhecido: {metodo}"})

    def _chamar(self, id_, nome, args):
        if nome not in self._ferramentas:
            self._responder(id_, erro={"code": -32602,
                                       "message": f"ferramenta desconhecida: {nome}"})
            return
        _, schema, fn = self._ferramentas[nome]
        faltando = [k for k in schema["required"] if k not in args]
        if faltando:
            self._resultado(id_, f"faltam argumentos obrigatórios: {faltando}", erro=True)
            return
        try:
            saida = fn(**args)
            self._resultado(id_, saida)
        except ErroFerramenta as e:
            self._resultado(id_, str(e), erro=True)
        except Exception as e:  # nunca derrubar o servidor por uma chamada
            log("exceção em", nome, "->", repr(e))
            traceback.print_exc(file=sys.stderr)
            self._resultado(id_, f"erro interno em {nome}: {e!r}", erro=True)

    def _resultado(self, id_, saida, erro=False):
        if not isinstance(saida, str):
            saida = json.dumps(saida, ensure_ascii=False, indent=1)
        self._responder(id_, {"content": [{"type": "text", "text": saida}],
                              "isError": bool(erro)})

    # ------------------------------------------------------------------ loop
    def rodar(self):
        log(self.nome, self.versao, "pronto;", len(self._ferramentas), "ferramentas")
        for linha in sys.stdin:
            linha = linha.strip()
            if not linha:
                continue
            try:
                req = json.loads(linha)
            except json.JSONDecodeError:
                log("linha ignorada (não é JSON):", linha[:120])
                continue
            try:
                self._tratar(req)
            except Exception as e:
                log("falha ao tratar", req.get("method"), "->", repr(e))
                if req.get("id") is not None:
                    self._responder(req["id"], erro={"code": -32603,
                                                     "message": repr(e)})
