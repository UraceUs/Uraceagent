"""Os funis da equipe no Kommo: Urace (página 1) e Comercial (página 2).

A ponte nunca guarda id de etapa no repositório: lê os funis da conta, acha
Urace e Comercial pelo nome e resolve cada etapa pelo nome.

Regra de segurança: o SDR não cria funil nem etapa. Os funis são da equipe
(D-09-17); aqui só se confere se tudo que as regras usam existe. O que
faltar vira pendência para uma pessoa corrigir.
"""
from . import regras
from .classificador import normalizar

TIPO_INCOMING = 1
_FECHAMENTOS = ("GANHO", "PERDIDO")


def chave(nome):
    return normalizar(nome)


def _etapas(pipeline):
    return (pipeline or {}).get("_embedded", {}).get("statuses", []) or []


def achar(pipelines, zona):
    alvo = chave(regras.FUNIS[zona])
    return next((p for p in pipelines if chave(p.get("name")) == alvo), None)


def etapas_usadas(zona):
    """Nomes de etapa (sem repetir) que as regras usam em cada página."""
    nomes = regras.ETAPAS_ENTRADA.values() if zona == regras.ENTRADA else regras.ETAPAS_COMERCIAL.values()
    usadas = [n for n in nomes if n not in _FECHAMENTOS]
    if zona == regras.ENTRADA:
        usadas += regras.ETAPAS_RESGATE
    return list(dict.fromkeys(usadas))


def planejar(pipelines):
    """Confere se as regras batem com a conta. Não escreve nada."""
    funis_faltando, faltando, duplicadas = [], [], []
    for zona in (regras.ENTRADA, regras.COMERCIAL):
        funil = achar(pipelines, zona)
        if not funil:
            funis_faltando.append(regras.FUNIS[zona])
            continue
        nomes = [chave(s.get("name")) for s in _etapas(funil)]
        for etapa in etapas_usadas(zona):
            n = nomes.count(chave(etapa))
            if n == 0:
                faltando.append({"funil": regras.FUNIS[zona], "etapa": etapa})
            elif n > 1:
                duplicadas.append({"funil": regras.FUNIS[zona], "etapa": etapa, "ocorrencias": n})
    return {"ok": not funis_faltando and not faltando, "funis_faltando": funis_faltando,
            "etapas_faltando": faltando, "etapas_duplicadas": duplicadas}


class Mapa:
    """Ids de Urace e Comercial lidos da conta."""

    def __init__(self, pipelines):
        self.funis = {}
        self._nomes_dos_funis = {int(p["id"]): p.get("name") for p in pipelines if p.get("id")}
        for zona in (regras.ENTRADA, regras.COMERCIAL):
            funil = achar(pipelines, zona)
            if not funil:
                continue
            etapas, ordem, incoming = {}, {}, set()
            for s in sorted(_etapas(funil), key=lambda s: int(s.get("sort") or 0)):
                sid = int(s["id"])
                if int(s.get("type") or 0) == TIPO_INCOMING:
                    incoming.add(sid)
                etapas.setdefault(chave(s.get("name")), sid)
                ordem[sid] = int(s.get("sort") or 0)
            resgate = set()
            if zona == regras.ENTRADA:
                resgate = {etapas[chave(n)] for n in regras.ETAPAS_RESGATE if chave(n) in etapas}
            self.funis[zona] = {
                "id": int(funil["id"]),
                "etapas": etapas,
                "nome_por_id": {v: k for k, v in etapas.items()},
                "ordem": ordem,
                "incoming": incoming,
                # Etapas que o SDR gerencia: na página 1, só First Contact.
                "gerenciadas": {etapas[chave(n)] for n in etapas_usadas(zona)
                                if chave(n) in etapas and n not in regras.ETAPAS_RESGATE},
                "resgate": resgate,
            }
        self.existe = len(self.funis) == 2

    def pipeline_id(self, zona):
        f = self.funis.get(zona)
        return f["id"] if f else None

    def nome_funil(self, pipeline_id):
        return self._nomes_dos_funis.get(int(pipeline_id or 0)) or str(pipeline_id)

    def _zona_do_funil(self, pipeline_id):
        pid = int(pipeline_id or 0)
        return next((z for z, f in self.funis.items() if f["id"] == pid), None)

    def status_id(self, etapa, zona):
        """(pipeline_id, status_id) de uma etapa numa página. GANHO/PERDIDO
        são os fechamentos nativos daquela página."""
        f = self.funis.get(zona)
        if not f:
            return None, None
        if etapa == "GANHO":
            return f["id"], regras.STATUS_GANHO
        if etapa == "PERDIDO":
            return f["id"], regras.STATUS_PERDIDO
        return f["id"], f["etapas"].get(chave(etapa))

    def ordem(self, pipeline_id, status_id):
        """Posição da etapa no funil (sort do Kommo); fechamento não tem."""
        zona = self._zona_do_funil(pipeline_id)
        sid = int(status_id or 0)
        if not zona or sid in (regras.STATUS_GANHO, regras.STATUS_PERDIDO):
            return None
        return self.funis[zona]["ordem"].get(sid)

    def localizar(self, pipeline_id, status_id):
        """Onde o card está, do ponto de vista do SDR."""
        sid = int(status_id or 0)
        fechado = sid in (regras.STATUS_GANHO, regras.STATUS_PERDIDO)
        zona = self._zona_do_funil(pipeline_id)
        if not zona:
            return {"do_sdr": False, "zona": None, "fechado": fechado, "incoming": False,
                    "gerenciada": False, "resgate": False, "etapa": None}
        f = self.funis[zona]
        return {"do_sdr": True, "zona": zona, "fechado": fechado,
                "incoming": sid in f["incoming"], "gerenciada": sid in f["gerenciadas"],
                "resgate": sid in f["resgate"], "etapa": f["nome_por_id"].get(sid)}

    @staticmethod
    def tag_de_origem_faltando(tags):
        """Tag que a REGRA 1 da equipe daria a um card sem tag de origem."""
        if any(t in tags for t in regras.TAGS_DE_ORIGEM):
            return None
        return regras.TAG_SEM_ORIGEM
