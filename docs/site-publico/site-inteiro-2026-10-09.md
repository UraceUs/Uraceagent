# Site inteiro no novo.urace.us — 09/10/2026 (#164)

Dono, 08/10 (voz): *"estamos reconstruindo todo o site … eu preciso de uma cópia com as novas
URLs e também com … identidade visual mesclada de Command Center com o site nativo urace.us
… tudo conectado por ali"* e *"um site totalmente automático que venda sozinho"*.

## O que existe agora (106 páginas, tudo em `command_center/vitrine/`)

| Parte | Endereço novo | Vem de |
|---|---|---|
| Home, Arrive and Drive | `/`, `/services/arrive-and-drive/` | `conteudo.py` (etapa 1, 07/10) |
| Hub de serviços + Sim 2 Grid | `/services/` | `conteudo_servicos.py` |
| Kart School, Coaching, Camp, Birthday, Corporate, Groups | `/services/<slug>/` | `conteudo_servicos.py` |
| Academy, Pro Team, For Beginners, Career, About, Contact, Accessibility | `/academy/` … | `conteudo_paginas.py` |
| Blog (7 artigos, 4 categorias) | `/blog/`, `/blog/category/<c>/`, `/blog/<slug>/` | `dados/posts.json` |
| Loja (69 produtos, 8 categorias) | `/store/`, `/store/<cat>/`, `/store/p/<slug>/` | `dados/produtos.json` |

- Os textos saíram do urace.us de 08/10 (REST do WordPress + HTML das páginas); nada inventado.
  Correções de propósito: Box 3 no endereço; remarcação **24 h com taxa de US$ 95**; kart adulto
  **7+** (decisões do dono de 08/10).
- Fotos: 173 WebP em `static/img/`, ≤ 1600 px, sem EXIF, < 190 KB cada.
- Cada página: um `h1`, título e `meta description` únicos, canonical, Open Graph, JSON-LD
  (LocalBusiness + Service/Product/BlogPosting/FAQPage/BreadcrumbList), CSP só `'self'`.
- **Endereços antigos → novos (301)**: `paginas_site.redirecionamentos()` cobre as páginas do
  WordPress, `/product/<slug>/`, `/product-category/<c>/`, `/<post>/`, `/category/<c>/`, `/shop/`,
  `/book-online/`, `/my-account/`. O teste `test_nenhum_link_volta_ao_wordpress…` garante que
  nenhum link interno quebra e que o menu não aponta para o urace.us.
- `sitemap.xml` lista todas as páginas (`paginas_site.caminhos()`); `robots.txt` continua
  "prévia" (`Disallow: /`) até `CC_SITE_PREVIEW=0`.

## Tudo conectado ao Command Center

- **Reserva** (`Continue to booking`) → `/ops/portal/reserve`: sessão → entrar ou criar conta →
  piloto → pagar (invoice do QuickBooks com link) + waiver → acompanhamento em
  `/ops/portal/sessions/<id>`. Mesmo visual do site (`.psite`).
- **Contato** (`/contact/`, com `?assunto=` e `?produto=`) → `POST /ops/api/vitrine/contato`:
  vira **oportunidade em Vendas** (origem *Site*, etapa NOVO, com nota), e-mail para
  `support@urace.us` com o link da oportunidade e confirmação para a pessoa.
- **Pedido da loja** (página do produto) → `POST /ops/api/vitrine/pedido`: oportunidade com o
  produto, a variação, a quantidade e o valor estimado; a equipe confirma estoque e frete e manda a
  invoice do QuickBooks. Com o Stripe ligado (#174), o produto com preço e em estoque é **pago na
  hora** pelo Stripe Checkout e entra pago em Vendas: veja `loja-stripe.md`. O pedido continua para
  "Ask for price", fora de estoque e dúvidas.
- **Planos mensais (#169, dono 09/10: "vender online já")**: a equipe cadastra o plano em Site ›
  Serviços (tipo *Plano mensal*, preço por mês, meses, sessões por mês, item do QuickBooks). A
  página da Academy passa a mostrar os planos cadastrados com o botão **Choose** →
  `/ops/portal/reserve?plan=<id>` (sem plano cadastrado, a página pede contato). O cliente entra,
  escolhe o piloto e paga: o card ganha o contrato (`plan_type=monthly`, valor, item, sessões/mês),
  a **primeira mensalidade sai na hora** pelo QuickBooks (link de pagamento) e as outras ficam
  agendadas no dia 1 às 01:00 (`monthly_invoices`, a mesma tela Mensalidade do painel); waiver
  pelo DocuSign; pago + waiver → plano **ativo** (`/ops/portal/plans/<id>`), e as sessões marcadas
  depois contam no plano sem cobrar de novo. Pro Team continua pelo contato.
- Proteções dos formulários: honeypot (`site`), 8 envios por IP a cada 10 min, validação de e-mail,
  só texto. Funcionam sem JavaScript (POST normal e volta com `?sent=1`).

## Como atualizar

- Texto de página: edite `conteudo_*.py` (os testes conferem h1, títulos e links).
- Produto ou artigo novo: edite `dados/produtos.json` / `dados/posts.json` (os scripts que geraram
  a cópia estão descritos em `scratchpad/site/copia` da sessão de 08/10: REST do WooCommerce
  `wc/store/v1/products` e `wp/v2/posts`; a foto entra em `static/img/` já em WebP).
- Preços do Arrive and Drive: continuam vindo do painel (Site › Serviços).

## Trocar o urace.us (quando o dono disser)

1. DNS do `urace.us` e `www.urace.us` → IP do VPS (registro A), como foi feito com `novo.urace.us`.
2. No VPS, em `~/.urace/adminai.env`: `CC_SITE_HOSTS=novo.urace.us,urace.us,www.urace.us` e
   `CC_SITE_PREVIEW=0`; `CC_DOMINIOS_EXTRAS="ops.urace.us my.urace.us novo.urace.us urace.us www.urace.us"`.
3. `bash adminai/deploy/command_center/servir_command_center.sh` (o Caddy pede o certificado e
   passa tudo ao FastAPI). O WordPress na Hostinger fica guardado como está.
4. Google Search Console: enviar `https://urace.us/sitemap.xml`.
