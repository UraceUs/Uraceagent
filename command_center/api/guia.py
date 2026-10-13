"""Como usar (#223): os guias da plataforma dentro do painel, e o MD para a IA de cada um.

Dono, 13/10: *"uma seção chamada como usar … o guia de como usar a plataforma, cada função,
tudo totalmente descrito, tudo totalmente detalhado. É, MD para IA também, uma parte onde a
pessoa consegue baixar o MD para colocar no chat da IA dela, que já tem o nosso MCP ou a nossa
API, para poder operar dentro do Command Center."*

Uma fonte só: os guias são os arquivos de `docs/` que o "Playbook junto" (CLAUDE.md) já obriga
a atualizar em todo PR que mexe em tela, rota ou processo. O painel lê, converte para HTML (com
os títulos um nível abaixo: a página já tem o h1) e entrega também o `.md` cru para baixar.

O MD para a IA junta os guias num arquivo e abre com o que a IA precisa saber para operar pelo
MCP ou pela API. Não leva chave, token nem senha: quem conecta é a pessoa, com o próprio usuário.
O que dá para fazer muda com o papel de cada um; por isso o arquivo manda a IA perguntar ao painel
(`urace_operacoes`) em vez de trazer uma lista que envelhece.
"""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from command_center.api import auth
from command_center.providers.balcao import hoje

r = APIRouter(prefix="/ops/api/guia", tags=["guia"])

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"

# slug → (arquivo, título, para quem, para que serve). A ordem é a da tela.
GUIAS = {
    "geral": ("playbooks/playbook-geral.md", "Guia geral", "todo mundo da equipe e a IA de cada um",
              "Para que serve o painel, quem vê o quê, o mapa de todas as telas, as rotinas do dia, a IA, as regras e o que fazer quando algo dá errado."),
    "vendas": ("playbooks/playbook-vendas.md", "Vendas", "quem vende e a IA dessa pessoa",
               "Oportunidades, agenda de retornos, Kommo, Robô SDR, preços da tabela, fechamento, agendamentos do site e os roteiros do dia a dia."),
    "mecanicos": ("playbooks/playbook-mecanicos-e-coaches.md", "Mecânicos e coaches", "o box: mecânico e coach",
                  "Calendário, balcão de peças no celular, etiquetas QR, contagem do estoque, checklists e pedidos."),
    "suits": ("suits-guia-do-lucas.md", "Suits · Alpha Line", "quem opera os macacões e a IA dessa pessoa",
              "Os pedidos de macacão sob medida: etapas, e-mail com o cliente e o fornecedor, a IA de cada pedido e o descarte."),
    "conectar-ia": ("command-center-mcp-operar.md", "Conectar a sua IA (MCP e API)", "quem quer operar o painel pelo Claude",
                    "Como ligar o Claude (app, claude.ai ou terminal) ao painel com o seu usuário, e as chaves de API."),
}
PDF = {"mecanicos": "playbooks/playbook-mecanicos-e-coaches.pdf"}
_ARQ_PARA_SLUG = {Path(a).name: s for s, (a, *_r) in GUIAS.items()}
_CACHE: dict[str, tuple[float, str]] = {}


def _arquivo(slug):
    if slug not in GUIAS:
        raise HTTPException(404, "Guia não encontrado.")
    p = DOCS / GUIAS[slug][0]
    if not p.is_file():
        raise HTTPException(404, "O arquivo deste guia não está no servidor.")
    return p


def _slug_titulo(texto, sep="-"):
    """O mesmo âncora do GitHub: o sumário dos guias foi escrito assim (#1-para-que-serve-…)."""
    t = re.sub(r"<[^>]+>", "", texto).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    return t.replace(" ", sep)


def _link_interno(m):
    """Link entre guias (`playbook-vendas.md`, `../suits-guia-do-lucas.md#x`) vira a tela do guia."""
    alvo, ancora = m.group(2), m.group(3) or ""
    slug = _ARQ_PARA_SLUG.get(Path(alvo).name)
    if slug:
        return f'{m.group(1)}"/ops/como-usar/{slug}{ancora}"'
    if Path(alvo).name.endswith(".pdf") and "mecanicos" in alvo:
        return f'{m.group(1)}"/ops/api/guia/mecanicos.pdf"'
    return m.group(0)


def html(slug):
    """O guia em HTML, guardado até o arquivo mudar."""
    import markdown
    p = _arquivo(slug)
    mt = p.stat().st_mtime
    if slug in _CACHE and _CACHE[slug][0] == mt:
        return _CACHE[slug][1]
    md = p.read_text(encoding="utf-8")
    md = re.sub(r"(?m)^ {2,3}(- |\d+\. )", r"    \1", md)        # o python-markdown só aninha com 4 espaços
    corpo = markdown.markdown(md, extensions=["tables", "sane_lists", "fenced_code", "toc"],
                              extension_configs={"toc": {"slugify": _slug_titulo}})
    for n in range(5, 0, -1):                                        # um h1 por página: o da tela
        corpo = re.sub(rf"<(/?)h{n}([ >])", rf"<\1h{n + 1}\2", corpo)
    corpo = re.sub(r'(href=)"((?:\.\./|\./)?[\w\-/]+\.(?:md|pdf))(#[^"]*)?"', _link_interno, corpo)
    corpo = re.sub(r"<table>", '<div class="guia-tbl"><table>', corpo).replace("</table>", "</table></div>")
    _CACHE[slug] = (mt, corpo)
    return corpo


@r.get("")
def lista(u=Depends(auth.usuario_atual)):
    out = []
    for slug, (arq, titulo, quem, para) in GUIAS.items():
        p = DOCS / arq
        if p.is_file():
            out.append({"slug": slug, "titulo": titulo, "para_quem": quem, "resumo": para, "pdf": slug in PDF,
                        "linhas": p.read_text(encoding="utf-8").count("\n")})
    return {"guias": out}


@r.get("/para-ia.md")
def para_ia(u=Depends(auth.usuario_atual)):
    """Um arquivo só para a IA: cole no Projeto do Claude ou salve como CLAUDE.md."""
    partes = [_CABECALHO_IA.format(data=hoje())]
    for slug, (_arq, titulo, *_r) in GUIAS.items():
        partes.append(f"\n\n---\n\n<!-- guia: {titulo} -->\n\n" + _arquivo(slug).read_text(encoding="utf-8"))
    return Response("".join(partes), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="urace-command-center-para-ia.md"',
                             "Cache-Control": "private, no-store"})


@r.get("/{slug}.md")
def baixar(slug: str, u=Depends(auth.usuario_atual)):
    return Response(_arquivo(slug).read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="urace-{slug}.md"', "Cache-Control": "private, no-store"})


@r.get("/{slug}.pdf")
def baixar_pdf(slug: str, u=Depends(auth.usuario_atual)):
    if slug not in PDF or not (DOCS / PDF[slug]).is_file():
        raise HTTPException(404, "Este guia não tem PDF.")
    return FileResponse(DOCS / PDF[slug], media_type="application/pdf", filename=f"urace-{slug}.pdf",
                        headers={"Cache-Control": "private, no-store"})


@r.get("/{slug}")
def ler(slug: str, u=Depends(auth.usuario_atual)):
    arq, titulo, quem, para = GUIAS[slug] if slug in GUIAS else (None, None, None, None)
    return {"slug": slug, "titulo": titulo, "para_quem": quem, "resumo": para, "pdf": slug in PDF, "html": html(slug)}


_CABECALHO_IA = """# URACE Command Center — instruções para a IA

> Arquivo gerado pelo painel em {data} (Administrativo › Como usar › MD para a sua IA).
> **Como usar:** cole este arquivo inteiro nas instruções de um Projeto do Claude
> (claude.ai › Projetos › Instruções do projeto) ou salve como `CLAUDE.md` na pasta em que você
> abre o Claude Code. Baixe de novo quando o painel mudar: o arquivo sai sempre dos guias atuais.

## Antes de tudo: conectar

- **MCP (recomendado):** no Claude, Configurações › Conectores › Adicionar conector personalizado,
  URL `https://ops.urace.us/ops/mcp`. Entre com o **seu** usuário do painel e deixe marcado
  **"Também operar o painel como você"**. No terminal: `claude mcp add --transport http urace
  https://ops.urace.us/ops/mcp` e depois `/mcp` › urace › Authenticate. Detalhe no guia
  "Conectar a sua IA", no fim deste arquivo.
- **API:** chave criada por um administrador em Usuários › Chaves de API. Chave "só leitura" só lê;
  para operar, o administrador toca em **Liberar para operar**. A chave vai no cabeçalho
  `Authorization: Bearer …` e **nunca** é colada em chat, arquivo ou repositório.
- Este arquivo **não** traz chave, token nem senha, e você nunca deve pedir um no chat.

## Como operar (a regra de ouro)

1. **Pergunte ao painel o que dá para fazer:** chame `urace_operacoes` (pode filtrar com `busca`).
   A lista vem do seu papel (operador, gerente…) e do seu cargo; o que não aparece, você não faz.
2. **Leia antes de escrever:** `urace_resumo`, `urace_atencao`, `urace_cliente`, `urace_clientes`
   e as outras ferramentas de leitura mostram o estado de hoje.
3. **Faça com `urace_api`** (método, caminho, corpo). O que vai para o cliente ou cobra (invoice,
   waiver, e-mail, QuickBooks, Asana) primeiro **devolve o que vai acontecer**: mostre à pessoa e
   só repita com `confirmar=true` depois que ela disser sim.
4. Tudo o que você faz fica na auditoria com o nome da pessoa conectada.

## Regras que nunca mudam

- Não destruir dados, não apagar nada, não unir cards sem a pessoa decidir.
- Nunca colocar serviço, peça ou cobrança de um cliente no card de outro.
- Nada de dado inventado: se não está no painel, diga que não está.
- Preço só da tabela. Fuso: Flórida (America/New_York).
- Secret nunca no chat, no código ou no repositório.

A seguir, os guias completos, na ordem: geral, vendas, mecânicos e coaches, Suits e conectar a IA.
"""
