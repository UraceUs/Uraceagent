"""Preço do catálogo, vindo da Rate Card do Drive.

Decisão do dono (18/09/2026), palavra por palavra: *"use o rate card sempre; ele será
atualizado no Drive, sempre consultar lá"*, *"não preciso aprovar se o valor estiver como
está no rate card"*, *"peças podem manter o mesmo valor"* e *"faça ele ler isso uma vez por
semana e atualizar o quickbooks"*.

Então: **segunda de manhã** o painel lê a planilha na origem, compara com o catálogo e
aplica o que está no mapa revisado (`db/ratecard_mapa.json`). O que não está no mapa **não é
aplicado** — vira item em "Precisa de atenção", porque nome parecido já provou que não é o
mesmo item ("Summer Camp 3 Days" × "5 Days"; um item do catálogo escrito "Pratice").

Quem escreve no QuickBooks é `quickbooks_mcp.preco_item_sistema`, que recusa peça, preço
fora da faixa e item inativo. Tudo auditado, item a item.
"""
import sqlite3

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, auditar, get_db, um
from command_center.providers import ratecard

r = APIRouter(prefix="/ops/api/precos", tags=["precos"])
SISTEMA = "qbo"


def _itens_do_catalogo():
    from command_center.providers import chamar
    return chamar(SISTEMA, "qbo_itens", maximo=400)


def montar_plano():
    """Lê a Rate Card e o catálogo e devolve o que fazer. Não escreve nada."""
    grade = ratecard.ler_planilha()
    entradas = ratecard.extrair(grade)
    itens = _itens_do_catalogo()
    plano = ratecard.planejar(entradas, itens)
    plano["lidas"] = len(entradas)
    plano["catalogo"] = len(itens)
    return plano


def aplicar(con, plano, quem="rotina", user_id=None, criar=True):
    """Aplica preço (e cria o que o dono marcou para criar). Falha de um item não derruba
    os outros: cada linha vira um resultado próprio, como no fechamento da venda."""
    from adminai.mcp import quickbooks_mcp as qb
    feitos, falhas = [], []
    for it in plano.get("atualizar", []):
        try:
            res = qb.preco_item_sistema(it["id"], it["novo"], quem=quem)
            feitos.append({"acao": "preco", "qbo": it["qbo"], "antes": it["atual"], "novo": it["novo"],
                           "aplicado": bool(res.get("aplicado"))})
            auditar(con, "precos.item", quem, user_id=user_id, entity_type="qbo_item", entity_id=None,
                    detail={"item": it["qbo"], "antes": it["atual"], "novo": it["novo"],
                            "rc": it["rc"], "linha": it["linha"], "aplicado": bool(res.get("aplicado"))})
        except Exception as e:                                        # noqa: BLE001
            falhas.append({"acao": "preco", "qbo": it["qbo"], "erro": str(e)[:200]})
    if criar:
        for novo in plano.get("criar", []):
            nome = novo["nome"].replace(":", " -")                    # o QBO recusa ':' no nome
            try:
                res = qb.criar_item_sistema(nome, novo["valor"], descricao=f"Rate Card 2026, linha {novo['linha']}")
                feitos.append({"acao": "criar", "qbo": nome, "novo": novo["valor"], "aplicado": True, "id": res.get("id")})
                auditar(con, "precos.criar", quem, user_id=user_id, entity_type="qbo_item", entity_id=None,
                        detail={"item": nome, "preco": novo["valor"], "rc": novo["rc"], "linha": novo["linha"]})
            except Exception as e:                                    # noqa: BLE001
                falhas.append({"acao": "criar", "qbo": nome, "erro": str(e)[:200]})
    con.commit()
    return {"feitos": feitos, "falhas": falhas, "duvida": plano.get("duvida", []), "em": agora()}


# --------------------------------------------------------------------- rotas
@r.get("/plano")
def rota_plano(u=Depends(auth.exige("MANAGER"))):
    """O que a Rate Card mudaria hoje — sem tocar em nada."""
    try:
        p = montar_plano()
    except Exception as e:                                            # noqa: BLE001
        return {"erro": str(e)[:300], "atualizar": [], "criar": [], "duvida": []}
    return {**p, "resumo": ratecard.resumo(p)}


class AplicarIn(BaseModel):
    criar: bool = True


@r.post("/aplicar")
def rota_aplicar(dados: AplicarIn, request: Request, u=Depends(auth.exige("MANAGER")),
                 con: sqlite3.Connection = Depends(get_db)):
    """Aplica agora o que a rotina aplicaria segunda-feira."""
    plano = montar_plano()
    saida = aplicar(con, plano, quem=f"user:{u['id']}", user_id=u["id"], criar=dados.criar)
    auditar(con, "precos.aplicar", f"user:{u['id']}", user_id=u["id"],
            detail={"feitos": len(saida["feitos"]), "falhas": len(saida["falhas"])}, ip=auth._ip(request))
    con.commit()
    return saida


# --------------------------------------------------------------------- rotina semanal
def rodar_semanal(con, hoje=None):
    """Segunda de manhã: lê a Rate Card e aplica. Nos outros dias não faz nada.

    A rotina roda todo dia no horário da regra; o recorte de dia fica aqui para não
    inventar um formato de agenda novo só por causa disto."""
    from command_center.api import vendas
    dia = hoje or vendas.hoje_local()
    if dia.weekday() != 0:                       # 0 = segunda, no fuso da Flórida
        return {"pulou": "só roda segunda-feira", "dia": dia.isoformat()}
    plano = montar_plano()
    saida = aplicar(con, plano, quem="rotina")
    if plano.get("duvida"):
        _atencao_das_duvidas(con, plano["duvida"])
    auditar(con, "precos.semanal", "rotina",
            detail={"feitos": len(saida["feitos"]), "falhas": len(saida["falhas"]),
                    "duvida": len(plano.get("duvida", [])), "lidas": plano.get("lidas")})
    con.commit()
    return {**saida, "resumo": ratecard.resumo(plano)}


def _atencao_das_duvidas(con, duvidas):
    """A Rate Card mudou algo que ninguém ligou a um item: isso é pergunta, não escrita.
    Um evento por dia — o índice único de `ai_events` cuida do resto."""
    from command_center.db import atualizar, inserir
    exemplos = ", ".join(d["nome"][:40] for d in duvidas[:5])
    resumo = (f"{len(duvidas)} preço(s) da Rate Card sem item ligado no catálogo: {exemplos}"
              + ("…" if len(duvidas) > 5 else ""))
    ja = um(con, "SELECT id FROM ai_events WHERE kind='precos.duvida' AND entity_type='qbo_item' AND entity_id IS NULL")
    if ja:
        atualizar(con, "ai_events", ja["id"], summary=resumo, status="NEW", detected_at=agora())
        return
    inserir(con, "ai_events", kind="precos.duvida", entity_type="qbo_item", summary=resumo, status="NEW")
