#!/usr/bin/env python3
"""Catálogo da Comet Kart Sales → referência de compra no painel.

Dono, 22/09: *"a base para as peças serão as peças e códigos de SKU desse site"* e
*"o SKU vai ser uma referência para o módulo de compras futuro"*.

    python3 adminai/importar_comet.py --ver            # só diz o que achou, não grava
    python3 adminai/importar_comet.py --aplicar        # grava em supplier_products
    python3 adminai/importar_comet.py --aplicar --completo   # varre tudo e marca sumidos

**Educação com o site dos outros não é enfeite, é o que mantém isto funcionando:**

- lê e obedece o `robots.txt` — caminho proibido não é buscado, ponto;
- se identifica no User-Agent, com um contato configurável (`COMET_CONTATO`);
- espera entre uma página e outra (`--pausa`, padrão 1,5 s) e respeita `Retry-After`;
- guarda em disco o que já buscou (`~/.urace/cache/comet/`), então repetir a importação
  não volta a bater no site;
- tenta o JSON da loja ANTES de qualquer página: uma chamada paginada no lugar de
  milhares de páginas.

Se as duas estratégias estruturadas falharem, a ferramenta PARA e diz. Não existe aqui
raspador de HTML genérico: parser escrito contra um site que ninguém olhou é adivinhação.

Nada aqui apaga catálogo: produto que sumiu é marcado com `gone_at`.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from adminai._venv import garantir_venv  # noqa: E402

garantir_venv()

from command_center.db import aplicar_schema, conectar  # noqa: E402
from command_center.providers import fornecedor  # noqa: E402

SITE = os.environ.get("COMET_SITE", "https://cometkartsales.com")
CONTATO = os.environ.get("COMET_CONTATO", "")
AGENTE = ("URACE-CommandCenter/1.0 (catálogo interno de compras"
          + (f"; contato: {CONTATO}" if CONTATO else "") + ")")
CACHE = os.path.join(os.environ.get("URACE_DIR", os.path.expanduser("~/.urace")), "cache", "comet")
PAUSA = 1.5
TENTATIVAS = 3


class Educado:
    """Busca com robots.txt, pausa, repetição com espera crescente e cache em disco."""

    def __init__(self, site=SITE, pausa=PAUSA, cache=CACHE, usar_cache=True):
        self.site, self.pausa, self.cache, self.usar_cache = site, pausa, cache, usar_cache
        self.ultima = 0.0
        self.buscadas = self.do_cache = 0
        self.robots = urllib.robotparser.RobotFileParser()
        self.robots_lido = False
        os.makedirs(self.cache, exist_ok=True)

    def _ler_robots(self):
        if self.robots_lido:
            return
        self.robots_lido = True
        url = urllib.parse.urljoin(self.site, "/robots.txt")
        try:
            self.robots.parse(self._baixar(url, respeitar=False).decode("utf-8", "replace").splitlines())
        except Exception as e:
            # Sem robots legível, o respeito manda PARAR, não seguir em frente.
            raise SystemExit(f"não consegui ler {url} ({e}). Sem robots.txt eu não varro o site.")

    def permitido(self, url):
        self._ler_robots()
        return self.robots.can_fetch(AGENTE, url)

    def _caminho(self, url):
        return os.path.join(self.cache, hashlib.sha256(url.encode()).hexdigest()[:32] + ".bin")

    def _baixar(self, url, respeitar=True):
        if respeitar and not self.permitido(url):
            raise PermissionError(f"robots.txt não permite: {url}")
        espera = self.pausa - (time.time() - self.ultima)
        if espera > 0:
            time.sleep(espera)
        req = urllib.request.Request(url, headers={
            "User-Agent": AGENTE, "Accept": "application/json, text/html;q=0.9",
            "Accept-Language": "en-US,en;q=0.9"})
        erro = None
        for n in range(TENTATIVAS):
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    self.ultima = time.time()
                    return r.read()
            except urllib.error.HTTPError as e:
                self.ultima = time.time()
                if e.code in (429, 503):
                    # O site pediu calma. Obedecer é o mínimo.
                    pausa = float(e.headers.get("Retry-After") or (5 * (n + 1)))
                    print(f"    site pediu para esperar {pausa:g}s ({e.code})")
                    time.sleep(min(pausa, 120))
                    erro = e
                    continue
                if 400 <= e.code < 500:
                    raise
                erro = e
            except (urllib.error.URLError, TimeoutError) as e:
                erro = e
            time.sleep(2 ** n)
        raise erro

    def pegar(self, url):
        arq = self._caminho(url)
        if self.usar_cache and os.path.exists(arq):
            self.do_cache += 1
            with open(arq, "rb") as f:
                return f.read()
        dados = self._baixar(url)
        self.buscadas += 1
        with open(arq, "wb") as f:
            f.write(dados)
        return dados


# ------------------------------------------------------------ as três estratégias
def pelo_json_da_loja(bus, limite=None):
    """Shopify e parecidos: `/products.json` paginado. Uma chamada por 250 produtos."""
    achados, pagina = [], 1
    while True:
        url = urllib.parse.urljoin(bus.site, f"/products.json?limit=250&page={pagina}")
        if not bus.permitido(url):
            print("    /products.json bloqueado pelo robots.txt — pulando estratégia")
            return []
        try:
            dados = json.loads(bus.pegar(url))
        except (urllib.error.HTTPError, ValueError, PermissionError):
            return achados                    # não é Shopify, ou acabou
        lote = fornecedor.do_shopify(dados, base=bus.site)
        if not (dados.get("products") or []):
            break
        achados += lote
        print(f"    página {pagina}: {len(lote)} SKU (total {len(achados)})")
        if limite and len(achados) >= limite:
            break
        pagina += 1
        if pagina > 400:                       # trava de segurança contra laço infinito
            break
    return achados


def pelo_sitemap(bus, limite=None):
    """Sem JSON da loja: pega as URLs de produto no sitemap e lê o JSON-LD de cada uma.

    É mais pesado para o site deles, então só roda quando a primeira estratégia falha —
    e com pausa entre as páginas.
    """
    urls = []
    for nome in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap_products_1.xml"):
        alvo = urllib.parse.urljoin(bus.site, nome)
        if not bus.permitido(alvo):
            continue
        try:
            xml = bus.pegar(alvo)
        except Exception:
            continue
        encontradas = fornecedor.urls_do_sitemap(xml)
        filhos = [u for u in encontradas if u.endswith(".xml")]
        for f in filhos[:50]:
            if bus.permitido(f):
                try:
                    encontradas += fornecedor.urls_do_sitemap(bus.pegar(f))
                except Exception:
                    pass
        urls += [u for u in encontradas if "/product" in u or "/products/" in u]
        if urls:
            break
    urls = list(dict.fromkeys(urls))
    if not urls:
        return []
    print(f"    {len(urls)} páginas de produto no sitemap")
    achados = []
    for n, u in enumerate(urls[:limite] if limite else urls, 1):
        if not bus.permitido(u):
            continue
        try:
            achados += fornecedor.do_jsonld(bus.pegar(u), url=u)
        except Exception as e:
            print(f"    !! {u}: {e}")
        if n % 25 == 0:
            print(f"    {n}/{len(urls)} páginas · {len(achados)} SKU")
    return achados


def de_arquivo(caminho):
    """Export do fornecedor (JSON ou CSV), para quando a rede não é o caminho — é assim
    que isto roda numa máquina sem acesso ao site."""
    with open(caminho, "rb") as f:
        bruto = f.read()
    texto = bruto.decode("utf-8", "replace").lstrip()
    if texto.startswith("{"):
        dados = json.loads(texto)
        return fornecedor.do_shopify(dados) if "products" in dados else []
    if texto.startswith("["):
        return [{"sku": p.get("sku"), "name": p.get("name") or p.get("title"),
                 "url": p.get("url"), "price": fornecedor._preco(p.get("price")),
                 "brand": p.get("brand") or p.get("vendor"),
                 "category": p.get("category") or p.get("product_type"),
                 "raw": json.dumps(p, ensure_ascii=False)[:20000]}
                for p in json.loads(texto)]
    import csv
    import io as _io
    linhas = list(csv.DictReader(_io.StringIO(texto)))
    def _c(d, *nomes):
        for n in nomes:
            for k in d:
                if k and k.strip().lower() == n:
                    return d[k]
        return None
    return [{"sku": _c(l, "sku", "item", "part number", "part_number"),
             "name": _c(l, "name", "title", "product", "description"),
             "url": _c(l, "url", "link"), "price": fornecedor._preco(_c(l, "price", "msrp")),
             "brand": _c(l, "brand", "vendor", "manufacturer"),
             "category": _c(l, "category", "type", "product_type"),
             "raw": json.dumps(l, ensure_ascii=False)[:20000]} for l in linhas]


def main():
    ap = argparse.ArgumentParser(description="Catálogo da Comet → referência de compra")
    ap.add_argument("--aplicar", action="store_true", help="grava (sem isto é só olhar)")
    ap.add_argument("--ver", action="store_true", help="mostra uma amostra do que achou")
    ap.add_argument("--limite", type=int, help="para em N SKU (prova de fogo curta)")
    ap.add_argument("--completo", action="store_true",
                    help="varreu tudo: marca como sumido o que não apareceu. "
                         "NÃO use com --limite")
    ap.add_argument("--arquivo", help="importa de um export (JSON/CSV) em vez da rede")
    ap.add_argument("--pausa", type=float, default=PAUSA, help="segundos entre páginas")
    ap.add_argument("--sem-cache", action="store_true", help="ignora o que já baixou")
    ap.add_argument("--site", default=SITE)
    a = ap.parse_args()

    if a.completo and a.limite:
        print("--completo com --limite marcaria como sumido tudo que o limite cortou.")
        return 2

    if a.arquivo:
        print(f"lendo export: {a.arquivo}")
        produtos = de_arquivo(a.arquivo)
        origem = "arquivo"
    else:
        bus = Educado(site=a.site, pausa=a.pausa, usar_cache=not a.sem_cache)
        print(f"site: {a.site}\nagente: {AGENTE}")
        if not CONTATO:
            print("dica: ponha COMET_CONTATO=<e-mail ou telefone> para o site saber quem somos")
        print("\n1) JSON da loja (/products.json)")
        produtos, origem = pelo_json_da_loja(bus, a.limite), "products.json"
        if not produtos:
            print("   nada. 2) sitemap + JSON-LD")
            produtos, origem = pelo_sitemap(bus, a.limite), "sitemap+json-ld"
        print(f"\nbuscadas {bus.buscadas} página(s) · {bus.do_cache} vieram do cache")

    if not produtos:
        print("\nNenhum produto reconhecido. As duas estratégias estruturadas falharam.")
        print("Antes de raspar HTML na unha: peça o export do catálogo ao fornecedor e")
        print("rode com --arquivo. É mais confiável e não incomoda o site deles.")
        return 1

    unicos = {}
    for p in produtos:                     # o mesmo SKU pode vir por dois caminhos
        if p.get("sku"):
            unicos[p["sku"]] = p
    print(f"\n{len(unicos)} SKU distintos ({origem})")
    if a.ver or not a.aplicar:
        for p in list(unicos.values())[:20]:
            preco = f"${p['price']:,.2f}" if p.get("price") else "—"
            print(f"  {str(p['sku'])[:22]:<22} {str(p['name'])[:48]:<48} {preco:>10}")
        if len(unicos) > 20:
            print(f"  … e mais {len(unicos) - 20}")

    if not a.aplicar:
        print("\nNada foi gravado. Para gravar: --aplicar")
        return 0

    con = conectar()
    aplicar_schema(con)
    try:
        r = fornecedor.salvar(con, list(unicos.values()), marcar_sumidos=a.completo)
        ligados = fornecedor.ligar_no_estoque(con)
        con.commit()
        print(f"\nGRAVADO: {r['novos']} novos · {r['atualizados']} atualizados · "
              f"{r['sumidos']} marcados como sumidos · {ligados} item(ns) de estoque ligados")
        orfaos = fornecedor.sem_cadastro(con)
        if orfaos:
            print(f"\n!! {len(orfaos)} SKU que o estoque usa e o catálogo não conhece:")
            for o in orfaos[:15]:
                print(f"   {o['sku']:<22} {o['name'][:48]}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
