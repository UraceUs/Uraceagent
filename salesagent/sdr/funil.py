"""O Novo funil no Kommo: estrutura, plano de criação e leitura de ids.

A ponte nunca guarda id de etapa no repositório: lê os funis da conta,
acha o "Novo funil" pelo nome e resolve cada etapa pelo nome. Quem cria o
funil pode ser a extensão (pela tela) ou tools/sdr_funil.py (pela API) —
o resultado é o mesmo.

Regra de segurança: nunca se acrescenta etapa em funil que já existe. Se
faltar etapa, o plano aponta e uma pessoa corrige.
"""
from . import regras
from .classificador import normalizar

TIPO_INCOMING = 1
COR = "#e6e8ea"


def chave(nome):
    return normalizar(nome)


_ZONA_POR_ETAPA = {}
for _nome in regras.ETAPAS_ENTRADA.values():
    if _nome not in ("PERDIDO", "GANHO"):
        _ZONA_POR_ETAPA[chave(_nome)] = regras.ENTRADA
for _nome in regras.ETAPAS_COMERCIAL.values():
    if _nome not in ("PERDIDO", "GANHO"):
        _ZONA_POR_ETAPA[chave(_nome)] = regras.COMERCIAL


def _etapas(pipeline):
    return (pipeline or {}).get("_embedded", {}).get("statuses", []) or []


def achar(pipelines):
    alvo = chave(regras.NOVO_FUNIL)
    return next((p for p in pipelines if chave(p.get("name")) == alvo), None)


def planejar(pipelines):
    """O que falta no Kommo para o SDR funcionar. Não escreve nada."""
    funil = achar(pipelines)
    if not funil:
        return {"ok": False, "criar_funil": True, "etapas": list(regras.ORDEM_ETAPAS),
                "etapas_faltando": [], "etapas_duplicadas": [], "incoming_ligado": False}
    nomes = [chave(s.get("name")) for s in _etapas(funil)]
    faltando = [e for e in regras.ORDEM_ETAPAS if chave(e) not in nomes]
    duplicadas = [e for e in regras.ORDEM_ETAPAS if nomes.count(chave(e)) > 1]
    incoming = any(int(s.get("type") or 0) == TIPO_INCOMING for s in _etapas(funil))
    return {"ok": not faltando, "criar_funil": False, "pipeline_id": funil.get("id"),
            "etapas": list(regras.ORDEM_ETAPAS), "etapas_faltando": faltando,
            "etapas_duplicadas": duplicadas, "incoming_ligado": incoming}


def corpo_criacao(sort=1000):
    """Corpo do POST /api/v4/leads/pipelines que cria o Novo funil."""
    return [{
        "name": regras.NOVO_FUNIL,
        "sort": sort,
        "is_main": False,
        # Sem "Incoming leads": conversa nova cai direto em Triagem.
        "is_unsorted_on": False,
        "_embedded": {"statuses": [
            {"name": nome, "sort": 20 + i * 10, "color": COR}
            for i, nome in enumerate(regras.ORDEM_ETAPAS)
        ]},
    }]


class Mapa:
    """Ids do Novo funil lidos da conta."""

    def __init__(self, pipelines):
        funil = achar(pipelines)
        self.existe = funil is not None
        self.pipeline_id = int(funil["id"]) if funil else None
        self.etapas = {}
        self.incoming = set()
        for s in sorted(_etapas(funil), key=lambda s: int(s.get("sort") or 0)):
            if int(s.get("type") or 0) == TIPO_INCOMING:
                self.incoming.add(int(s["id"]))
            self.etapas.setdefault(chave(s.get("name")), int(s["id"]))
        self._nome_por_id = {v: k for k, v in self.etapas.items()}

    def status_id(self, etapa):
        """Etapa (nome do motor) -> status_id. GANHO/PERDIDO são os nativos."""
        if etapa == "GANHO":
            return regras.STATUS_GANHO
        if etapa == "PERDIDO":
            return regras.STATUS_PERDIDO
        return self.etapas.get(chave(etapa))

    def localizar(self, pipeline_id, status_id):
        """Onde o card está, do ponto de vista do SDR."""
        sid = int(status_id or 0)
        fechado = sid in (regras.STATUS_GANHO, regras.STATUS_PERDIDO)
        if not self.existe or int(pipeline_id or 0) != self.pipeline_id:
            return {"do_sdr": False, "zona": None, "fechado": fechado, "incoming": False,
                    "gerenciada": False, "etapa": None}
        nome = self._nome_por_id.get(sid)
        zona = _ZONA_POR_ETAPA.get(nome) if nome else None
        if fechado:
            zona = regras.COMERCIAL  # fechado conta como venda: reabre/recebe anexo
        return {"do_sdr": True, "zona": zona, "fechado": fechado,
                "incoming": sid in self.incoming, "gerenciada": zona is not None and not fechado,
                "etapa": nome}
