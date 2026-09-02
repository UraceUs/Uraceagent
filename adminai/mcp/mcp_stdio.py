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
