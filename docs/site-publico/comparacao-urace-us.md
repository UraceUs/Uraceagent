# urace.us (hoje) × novo.urace.us (nosso) — comparação do processo de compra, 15/10/2026 (#252)

Dono, 15/10: *"teste tbm o urace.us para verificar como funciona hoje e como funciona no
novo.urace.us precisamos de ter esse processo totalmente otimizado e polido"*.

Levantamento feito **só por leitura pela rede** (curl e Chromium/Playwright) nos dois sites em
15/10/2026: nada foi comprado, nenhuma conta criada, nenhum formulário enviado, nada postado. Os
sitemaps do Yoast e todo link interno das páginas do urace.us foram lidos; o robots dos dois sites
foi respeitado (o `Disallow: /` do novo.urace.us é o nosso, da prévia).

- **Hoje**: WordPress + WooCommerce na Hostinger, tema da agência, Elementor, Yoast, WooCommerce
  Stripe Gateway, Subscriptions for WooCommerce, SliceWP (afiliados), Contact Form 7 (+ Google
  Sheets Connector e reCAPTCHA), GTranslate, Google Tag Manager (`GTM-59CCNDC`), Meta pixel e
  Facebook for WooCommerce.
- **Novo**: `command_center/vitrine/` servido pelo próprio Command Center (FastAPI), páginas
  montadas no servidor, carrinho único (sessão + loja), Stripe Checkout, conta obrigatória,
  página pessoal do pedido, tudo caindo em Vendas e no QuickBooks.

---

## 1. Resumo em uma tabela

| | urace.us (hoje) | novo.urace.us |
|---|---|---|
| Páginas no sitemap | 24 páginas + 7 artigos + 4 categorias + 70 produtos + 13 categorias de produto + 2 etiquetas | 106 (tudo num `sitemap.xml`) |
| Home: peso total / arquivos / `load` | **7.044 kB · 110 arquivos · 6,40 s** | **244 kB · 8 arquivos · 0,63 s** |
| Loja: peso / arquivos / `load` | 3.928 kB · 82 · 5,98 s | 382 kB · 10 · 0,79 s |
| Produto: peso / arquivos / `load` | 3.358 kB · 99 · 2,87 s | 239 kB · 9 · 0,66 s |
| Carrinho: peso / arquivos / `load` | 5.852 kB · 131 · 4,43 s | 145 kB · 8 · 0,64 s |
| Hosts de terceiros por página | 4 a 7 (696–1.312 kB) | **0** |
| Onde a sessão é vendida | `/book-online/` → `?add-to-cart=<id>` → `/cart/` → `/checkout/` → Stripe | `/services/arrive-and-drive/` → carrinho ou portal |
| Onde a peça é vendida | `/product/<slug>/` → `/cart/` → `/checkout/` → Stripe | `/store/p/<slug>/` → carrinho → Stripe Checkout |
| Conta para comprar | opcional (checkout de visitante) | **obrigatória** (#248) |
| O pedido chega ao Command Center? | **não** (só o pedido com macacão, pelo e-mail — §6) | sim: Vendas + QuickBooks + e-mail |
| Busca e filtro na loja | sim (`?s=`, `min_price`, `max_price`, ordenação, paginação) | **não** |
| Idiomas | GTranslate (widget) | EN/PT nas páginas da compra (`/language/`) |

---

## 2. Mapa das páginas

### 2.1 As páginas que existem nos dois

| urace.us | título de hoje | h1 de hoje | novo.urace.us | o que mudou |
|---|---|---|---|---|
| `/` | Kart Racing School & Driver Training in Orlando \| URACE | The Champions Factory | `/` | mesmo título e `meta description`; mesmo h1 |
| `/for-beginners/` | How to Get Into Karting - Start in Orlando \| URACE | How to Get Into Karting in Orlando | `/for-beginners/` | igual; o novo ganhou FAQPage |
| `/about/` | About URACE - Kart School & Racing Team in Orlando | Since 2016, Building champions… | `/about/` | igual |
| `/pro-team/` | Kart Racing Team in Florida - Join the URACE Team | Professional Kart Racing Team | `/pro-team/` | h1 novo ("You already race. Now race with a team behind you."), preço dos planos vem do painel (#207) |
| `/urace-academy/` | Kart Academy in Orlando - Monthly Driver Training \| URACE | Kart Academy in Orlando | `/academy/` | endereço novo; h1 novo; planos do painel |
| `/contact/` | Contact URACE - Kart Racing School in Orlando | Talk to Urace | `/contact/` | **o novo tem formulário** (vira oportunidade em Vendas); o de hoje só telefone/WhatsApp/e-mail |
| `/accessibility/` | Accessibility - Urace | Accessibility Statement for Urace | `/accessibility/` | igual (o de hoje pula de h1 para h3) |
| `/services/` | Kart Lessons, Coaching & Racing Programs in Orlando \| URACE | Kart racing in Orlando — from the simulator to the grid | `/services/` | igual |
| `/services/arrive-and-drive/` | Arrive and Drive Kart Racing in Orlando \| URACE | Kart Arrive and Drive in Orlando | `/services/arrive-and-drive/` | h1 novo; o novo tem a **agenda pública** com vagas e preço do painel |
| `/services/kart-school/` | Kart Racing Lessons in Orlando - Learn to Race \| URACE | Kart School in Orlando | igual | |
| `/services/professional-coaching/` | Professional Kart Coaching in Orlando \| URACE | Professional Kart Racing Coaching in Orlando | igual | |
| `/services/intensive-training-camp/` | Intensive Kart Racing Camp in Orlando \| URACE | Intensive Kart Racing Camp in Orlando | igual | |
| `/services/birthday-party/` | Kart Racing Birthday Parties in Orlando \| URACE | Kart Racing Birthday Parties in Orlando | igual | |
| `/services/corporate-events/` | Corporate Karting Events in Orlando \| URACE | Corporate Karting Events in Orlando | igual | |
| `/services/group-events-social-gatherings/` | Group Kart Racing Events in Orlando \| URACE | Group Kart Racing Events & Social Gatherings in Orlando | `/services/group-events/` | endereço encurtado |
| `/the-driver-factory/` e `/plan-your-career/` | How to Become a Professional Racing Driver / Plan Your Career - Urace | duas páginas, conteúdo quase igual | `/career/` | **duas viraram uma** |
| `/blog/` + 7 artigos + 4 categorias | Kart Racing Blog - How to Race Karts \| URACE | Take advantage of our materials | `/blog/`, `/blog/<slug>/`, `/blog/category/<c>/` | os 7 artigos e as 4 categorias vieram inteiros; o artigo sai de `/` para `/blog/` |
| `/store/` + 70 produtos | Kart Parts Store - Chassis, Engines & Tires \| URACE | Everything you need to race faster | `/store/`, `/store/p/<slug>/` | 69 dos 70 produtos (§4) |
| `/cart/` | Cart - Urace | Cart | `/cart/` | o novo junta **sessão + loja** no mesmo carrinho |
| `/my-account/` | My account - Urace | My account | `/ops/portal` | a área do cliente é o portal do Command Center |

### 2.2 Só no urace.us de hoje

| Endereço | Para que serve hoje |
|---|---|
| `/shop/` | a loja "crua" do WooCommerce: **busca por texto, filtro de preço, ordenação e paginação** |
| `/book-online/` | página pública que **vende a sessão**: 9 variantes com link `?add-to-cart=<id>` direto |
| `/checkout/` | o checkout do WooCommerce (endereço, cupom, conta opcional, Stripe UPE + Apple/Google Pay) |
| `/my-account/`, `/my-account/lost-password/` | conta do WooCommerce: pedidos, downloads, endereços, senha |
| `/affiliate-account/`, `/affiliate-registration/`, `/affiliate-reset-password/` | **programa de afiliados** (SliceWP) |
| `/kart-lessons-for-beginners/`, `/kart-driving-school/`, `/kart-training-packages/`, `/professional-kart-team-racing-team/` | 4 landing pages de anúncio (plugin `sxs-lp-for-urace`), com formulário CF7 que carrega `utm_*`, `gclid`, `fbclid`, `fbp`, `fbc` |
| `/lp1-cancelada/` … `/lp4-cancelada/`, `/typ/`, `/the-driver-factory-thank-you-page/` | páginas de obrigado das campanhas |
| `/product-category/<pai>/<filho>/…` | **~120 subcategorias** de peça (chassis › tony-kart-otk › brakes, engines › iame-x30, tires › mg-tires…) |
| `/product-tag/jecko/`, `/product-tag/parolin/` | páginas de etiqueta de produto |
| `/store/page/2/`, `/blog/page/2/`, `/product-category/<c>/page/2/` | paginação |
| `/sitemap_index.xml` + 6 sitemaps do Yoast | o mapa do site |

### 2.3 Só no novo.urace.us

| Endereço | Para que serve |
|---|---|
| `/cart/` (unificado) | sessão da agenda **e** item da loja no mesmo carrinho, com entrega e um pagamento só (#236) |
| `/order/<id>-<selo>/` | **página pessoal do pedido** com um estado por evento do Stripe, "Try again" e "Restore cart" (#245) |
| `/cart/thanks/`, `/store/thanks/`, `/store/cancelled/` | a volta do Stripe (confere a sessão mesmo se o webhook atrasar) e o "desistiu, nada cobrado" |
| `/language/` | chave EN/PT nas páginas da compra (#248) |
| `/legal/privacy.html` | política de privacidade (**no urace.us de hoje o link do rodapé é `href=""`: não leva a nada, e não existe página de privacidade**) |
| `/ops/portal/...` | conta do cliente, reserva, piloto, waiver, plano mensal, sessões |
| `/robots.txt`, `/sitemap.xml` | gerados pelo sistema a partir de `paginas_site.caminhos()` |

---

## 3. O caminho de compra, passo a passo

### 3.1 Sessão de pista — hoje (urace.us)

1. A pessoa chega em `/`, `/services/arrive-and-drive/` ou numa das 4 landing pages.
2. **Dois caminhos diferentes na mesma página**: o formulário Contact Form 7 ("fale com a gente",
   que vira e-mail + linha no Google Sheets) **ou** o botão que leva a `/book-online/`.
3. Em `/book-online/`, cada variante é um link `https://urace.us/?add-to-cart=<id>` (9 ids:
   `98`, `4770`…`4783`). Um clique põe no carrinho e volta para a home.
4. `/cart/` — quantidade, cupom, subtotal.
5. `/checkout/` — nome, e-mail, telefone, endereço de cobrança, conta opcional, cupom, observações.
6. Pagamento no próprio site com o **WooCommerce Stripe Gateway** (elemento universal do Stripe:
   cartão, mais Apple Pay/Google Pay/Link pelo Express Checkout).
7. Depois: e-mail do WooCommerce. **A data da sessão não é escolhida em nenhum passo** — fica para
   combinar depois, por telefone ou WhatsApp. Nada entra no Command Center.

**6 passos até pagar, e a vaga não é reservada.** `/checkout/` com o carrinho vazio devolve 301 para
`/cart/` (medido).

### 3.2 Sessão de pista — no novo

1. `/services/arrive-and-drive/` — escolhe o kart (preço vem de `KARTS`, não do texto) e **o dia na
   agenda pública** (vagas de verdade, do painel).
2. Dois botões: **"Add to cart"** (vai para `/cart/`) ou **"Continue to booking"** (vai para o
   portal, `/ops/portal/reserve`, onde o pagamento é a invoice do QuickBooks + waiver).
3. `/cart/` — itens, entrega dos itens de loja, e o aviso de que a conta é necessária.
4. "Checkout" → pede a conta do site se não tiver (`/ops/portal?volta=/cart/`) e abre o **Stripe
   Checkout** (cartão, Apple Pay, Google Pay).
5. Volta em `/cart/thanks/?session_id=…`, que confere a sessão no Stripe e mostra a **página do
   pedido** com o estado; o link pessoal `/order/<id>-<selo>/` fica valendo.
6. Em segundo plano: oportunidade em **Vendas** (ligada ao card quando e-mail **e** nome batem),
   e-mail para quem comprou, aviso em `support@urace.us`, **Sales Receipt no QuickBooks**.

**4 passos até pagar.** Problema: os **dois botões do passo 2 levam a dois pagamentos diferentes**
(Stripe no carrinho, invoice do QuickBooks no portal) e o texto embaixo só explica o do portal
("Next: sign in or create your account … Then you get the invoice … to pay online"). É o ponto mais
confuso do caminho hoje — veja §9.

### 3.3 Peça da loja — hoje

`/store/` (busca, filtro de preço, ordenação) ou `/shop/` → `/product/<slug>/` (variação, quantidade,
"Add to cart") → `/cart/` → `/checkout/` → Stripe. Mesma coisa que a sessão, com endereço de entrega.

### 3.4 Peça da loja — no novo

`/store/` ou `/store/<categoria>/` → `/store/p/<slug>/`:

- produto com preço e em estoque: **"Buy now"** (opção, quantidade, retirada na pista ou envio) →
  conta obrigatória → Stripe Checkout → `/store/thanks/` → página do pedido;
- produto "Ask for price", fora de estoque, ou dúvida: o formulário **"Send an order request"**,
  que vira oportunidade em Vendas, e a equipe manda a invoice.

O servidor **sempre confere produto, variação e preço no catálogo**, nunca no formulário.

---

## 4. O que o antigo faz e o novo ainda não faz

A lista que importa para trocar o urace.us. Cada linha diz onde a coisa está hoje.

| # | O que falta no novo | Onde está hoje | Peso |
|---|---|---|---|
| 1 | **Busca na loja** (`?s=`), **filtro de preço** (`min_price`/`max_price`) e **ordenação** | formulário em `https://urace.us/store/#products` e a loja crua em `/shop/` | alto: 69 produtos sem busca |
| 2 | **Paginação** da loja e do blog | `/store/page/2/`, `/blog/page/2/` | médio (hoje o novo mostra tudo numa página: a loja carrega 60 imagens) |
| 3 | **Árvore de ~120 subcategorias de peça** | `/product-category/karts-parts/chassis/tony-kart-otk/brakes/` e companhia | médio: quem busca "IAME X30" cai numa página que o novo não tem (agora redireciona para a categoria mãe ou para a loja) |
| 4 | **Páginas de etiqueta** de produto | `/product-tag/jecko/`, `/product-tag/parolin/` | baixo |
| 5 | **Cupom de desconto** | campo no `/cart/` e no `/checkout/` do WooCommerce | médio: é o que a equipe usa em campanha |
| 6 | **Assinatura/cobrança recorrente do WooCommerce** | plugin `subscriptions-for-woocommerce` (aparece em 11 páginas) | o novo cobra mensalidade pelo QuickBooks (#169): confirmar se cobre o mesmo |
| 7 | **Programa de afiliados** | SliceWP: `/affiliate-account/`, `/affiliate-registration/` | precisa de decisão do dono (§10) |
| 8 | **Google Tag Manager / Google Analytics / Meta pixel / Facebook for WooCommerce** | `GTM-59CCNDC` e `fbq(` em todas as páginas | **alto**: o novo não tem nenhuma medição; sem isso, campanha paga fica cega |
| 9 | **Catálogo do Facebook/Instagram** alimentado pelo WooCommerce | `facebook-for-woocommerce` | médio (loja no Instagram) |
| 10 | **Formulário com `utm_*`, `gclid`, `fbclid`, `fbp`, `fbc`** nas landing pages | CF7 nas 4 LPs e nas páginas de serviço | **alto**: hoje a origem do lead chega ao e-mail; o `/contact/` do novo grava origem "Site" e nada da campanha |
| 11 | **Lead do CF7 em planilha do Google** | `cf7-google-sheets-connector` | baixo (o novo põe em Vendas, que é melhor — mas a equipe pode depender da planilha) |
| 12 | **reCAPTCHA** nos formulários | `wpcf7-recaptcha` | baixo: o novo usa honeypot + 8 envios por IP a cada 10 min |
| 13 | **Tradução de todo o site** | GTranslate (widget em 30 páginas) | médio: no novo, EN/PT só nas páginas da compra |
| 14 | **4 landing pages de anúncio** com o layout de campanha | `/kart-lessons-for-beginners/`, `/kart-driving-school/`, `/kart-training-packages/`, `/professional-kart-team-racing-team/` | médio: hoje redirecionam para `/for-beginners/`, `/academy/`, `/pro-team/`; se tiver anúncio ativo, confirmar |
| 15 | **Páginas de obrigado das campanhas** (`/typ/`, `/lp*-cancelada/`) | plugin da agência | baixo: redirecionam para `/career/` |
| 16 | **Carrinho sem JavaScript** | o `/cart/` do WooCommerce é HTML do servidor | baixo: o `/cart/` novo precisa de JS (tem aviso e links de saída) |
| 17 | **1 produto** | `/product/otk-magnesium-wheels-set-mxc-130mm-210mm/` (OTK MXC, jogo de rodas de magnésio) está no sitemap de hoje e **não está** em `dados/produtos.json` | baixo, mas é um produto a menos para vender |
| 18 | **Área do cliente com histórico de pedidos da loja** | `/my-account/` (orders, downloads, addresses) | o portal tem sessões e planos; o pedido da loja só pelo link pessoal `/order/<token>/` |

### Já resolvido neste PR

- Os 110 endereços do urace.us que cairiam no 404 (§7).
- Código do tema (CSS e JavaScript) aparecendo como texto na página do produto Arrive and Drive,
  que também fazia a página rolar para o lado em 360 e 390 px.
- `meta description` de 6 produtos cortada no meio da palavra ("…add it w.").
- O SEO local do LocalBusiness (coordenadas, mapa, faixa de preço, cidades atendidas, Yelp,
  TripAdvisor, Google Maps) e os blocos `Organization` e `WebSite` que o Yoast publica hoje.
- A página de 404 saiu do Google e deixou de ser um beco sem saída.

---

## 5. Peso, velocidade, SEO, acessibilidade e celular

### 5.1 Peso e velocidade (Chromium, 390 px, tudo que a página baixa)

| Página | arquivos | total | JS | CSS | imagens | de terceiros | DOM pronto | `load` |
|---|---|---|---|---|---|---|---|---|
| urace.us `/` | 110 | 7.044 kB | 1.150 kB | 890 kB | 3.853 kB | 696 kB (4 hosts) | 2,40 s | **6,40 s** |
| novo `/` | 8 | **244 kB** | 15 kB | 32 kB | 100 kB | 0 | 0,56 s | **0,63 s** |
| urace.us `/store/` | 82 | 3.928 kB | 1.150 kB | 903 kB | 1.500 kB | 696 kB | 5,70 s | 5,98 s |
| novo `/store/` | 10 | 382 kB | 15 kB | 32 kB | 215 kB | 0 | 0,63 s | 0,79 s |
| urace.us `/product/arrive-and-drive/` | 99 | 3.358 kB | 1.568 kB | 910 kB | 462 kB | 696 kB | 2,64 s | 2,87 s |
| novo `/store/p/arrive-and-drive/` | 9 | 239 kB | 17 kB | 32 kB | 96 kB | 0 | 0,61 s | 0,66 s |
| urace.us `/services/arrive-and-drive/` | 153 | 5.066 kB | 2.065 kB | 1.106 kB | 610 kB | 1.312 kB (7 hosts) | 2,79 s | 5,89 s |
| novo `/services/arrive-and-drive/` | 11 | 209 kB | 23 kB | 32 kB | 22 kB | 0 | 0,59 s | 0,64 s |
| urace.us `/cart/` | 131 | 5.852 kB | **3.568 kB** | 1.100 kB | 816 kB | 696 kB | 4,24 s | 4,43 s |
| novo `/cart/` | 8 | **145 kB** | 15 kB | 32 kB | 10 kB | 0 | 0,57 s | 0,64 s |

Só o HTML: o antigo entrega 99–263 kB por página em 0,84–3,20 s; o novo, 7–40 kB em 0,13–0,53 s.
O antigo carrega 42 a 91 arquivos de JavaScript e 15 a 27 folhas de estilo por página; o novo, 1 a 2
e uma só. **O carrinho do antigo baixa 3,5 MB de JavaScript.**

### 5.2 SEO

| Item | urace.us | novo.urace.us |
|---|---|---|
| `title` único | sim nas páginas principais; **vazio de conteúdo nas 4 LPs e em `/plan-your-career/`** ("Plan Your Career - Urace") | sim nas 106 |
| `meta description` | falta em `/plan-your-career/`, nas 4 LPs, nas categorias de produto e **nas páginas de produto** (medi 10 de 70: nenhuma tem) | nas 106, sempre ≥ 80 caracteres |
| `canonical` | sim (Yoast) | sim |
| Um `h1` por página | **não**: a página de produto tem 2 h1; as 4 LPs e `/plan-your-career/` abrem com h2 **antes** do h1; `/accessibility/` salta de h1 para h3 | sim, e sem pular nível (teste no CI) |
| JSON-LD | rico: `WebPage`, `WebSite` (+SearchAction), `Organization`, `BreadcrumbList`, `LocalBusiness` completo, `Product`, `FAQPage` em `/plan-your-career/` | `LocalBusiness` completo (agora com mapa, geo, faixa de preço, cidades e perfis), `Organization` + `WebSite` na home, `BreadcrumbList`, `Service`, `Product`, `AggregateOffer`, `FAQPage`, `BlogPosting`, `ItemList`, `Reservation` |
| `robots.txt` | libera tudo (bloco do Yoast com `Disallow:` vazio), bloqueia `?add-to-cart=` e `wc-logs` | **`Disallow: /` enquanto é prévia**; com `CC_SITE_PREVIEW=0` passa a `Disallow: /ops/` + `Allow: /` + link do sitemap |
| `sitemap.xml` | `sitemap_index.xml` + 6 | um `sitemap.xml` com as 106 |
| Open Graph / Twitter | sim | sim (`og:locale` fixo em `en_US`, mesmo na página em PT) |
| `hreflang` | não (GTranslate não publica alternates) | não (o idioma é cookie, o endereço é o mesmo) |

### 5.3 Acessibilidade básica (Chromium, 360 e 390 px)

| Item | urace.us | novo.urace.us |
|---|---|---|
| `<img>` sem `alt` | 0 | 0 |
| Campo de formulário sem rótulo | **2 a 25 por página** (25 em `/services/arrive-and-drive/`) | 0 |
| Link ou botão sem nome acessível | 3 na home, `/book-online/` e `/services/arrive-and-drive/` | 0 |
| `h1` por página | 1, menos a página de produto (2) | 1 |
| Link "pular para o conteúdo" | não | sim |
| `lang` do `<html>` | `en-US` | `en` (e `pt-BR` nas páginas da compra em português) |

### 5.4 Celular (360 px e 390 px)

- **Rolagem lateral**: nenhum dos dois empurra a página para o lado — **menos**
  `novo.urace.us/store/p/arrive-and-drive/`, que media 806 px de largura em 360 e em 390 px
  (o CSS do tema vindo do WooCommerce como texto). **Corrigido neste PR**, com o teste e2e nas
  duas larguras.
- **Alvo de toque < 40 px**: antigo, 20 a 91 elementos por página (91 em `/store/`); novo, 1 a 5.
  Os que sobram no novo são links curtos do menu ("Blog", 34 px de largura e 40 de altura) e os
  rádios nativos de dia e de entrega (20 px, com o rótulo clicável em volta).
- O menu do antigo deixa 56 a 552 elementos fora da tela (menu fechado fora do canvas); o novo,
  só o link de pular conteúdo.

---

## 6. O que acontece com os pedidos feitos hoje no WooCommerce

**Não chegam ao Command Center.** Não existe integração com a API do WooCommerce em lugar nenhum do
repositório. O único caminho que existe é indireto e estreito:

- `command_center/providers/suits_ponte.py` → `novas_vendas()` procura no Gmail da conta `urace`
  o assunto `new order` dos últimos 3 dias e **só** processa o pedido cujo corpo casa com
  `\bsuits?\b|macac` (`RX_VENDA`). Esse vira pedido de macacão (`suit_orders`).
- Qualquer outro pedido — chassi, motor, peça, pneu, roupa, programa, Arrive and Drive, Academy —
  **não vira card, não vira oportunidade em Vendas, não vira Sales Receipt no QuickBooks e não baixa
  estoque**. Fica só no WooCommerce e no e-mail.

Histórico medido no levantamento de 01/10 (`decisoes-2026-10-01.md`): **27 pedidos desde 2024, 0
concluídos, 9 falharam, 1 nos últimos 90 dias**. O volume é pequeno — o que diminui o risco de
migrar, e aumenta o custo de manter a loja velha de pé.

### Risco de ficar com duas lojas e dois carrinhos ao mesmo tempo

1. **Dois carrinhos, dois caminhos no Stripe.** Os dois cobram no Stripe por caminhos diferentes
   (gateway do WooCommerce × Stripe Checkout nosso). Se for a **mesma conta** do Stripe — o que não
   dá para confirmar sem olhar a conta, e eu não leio produção —, o relatório do Stripe mistura as
   duas origens e conciliar passa a ser manual.
2. **Dois estoques.** O WooCommerce tem o estoque dele; o Command Center tem o nosso. Vender o
   mesmo chassi nos dois lugares é questão de tempo, e nada avisa.
3. **Dois preços.** `dados/produtos.json` é uma **cópia** do catálogo de 08/10. Mudar o preço no
   WooCommerce não muda no novo (e vice-versa).
4. **Pedido perdido**: pedido que entra no WooCommerce não aparece em Vendas nem no QuickBooks, e a
   equipe só descobre pelo e-mail. Pedido que entra no novo não aparece no WooCommerce.
5. **SEO brigando**: os dois sites publicam o mesmo texto. Enquanto o `robots.txt` do novo é
   `Disallow: /`, está seguro; no dia em que virar `Allow: /` **sem** o urace.us redirecionar, são
   duas páginas idênticas competindo (conteúdo duplicado).
6. **Confiança**: a pessoa que já tem conta no `/my-account/` do WooCommerce não tem conta no
   portal, e o pedido antigo dela não aparece em lugar nenhum do novo.

**Recomendação**: não rodar as duas lojas ao mesmo tempo mais do que o necessário para a troca de
DNS. O caminho curto é desligar o checkout do WooCommerce (produtos ficam visíveis, botão de compra
sai) no mesmo dia em que o novo passa a ser `urace.us`.

---

## 7. Redirecionamentos: endereço antigo → endereço novo

Levantei **226 endereços** que o urace.us publica hoje (os 6 sitemaps do Yoast mais todo link
interno das páginas). Antes deste PR, **110 deles cairiam no 404** no site novo. Agora os 226 abrem:
16 são a mesma página e 210 são 301. A lista completa está em
`command_center/tests/enderecos_urace_us.txt` e o teste
`test_nenhum_endereco_do_urace_us_cai_no_404` trava isso no CI.

### 7.1 Página por página

| urace.us | → novo.urace.us |
|---|---|
| `/` | `/` (mesma) |
| `/for-beginners/`, `/about/`, `/pro-team/`, `/contact/`, `/accessibility/`, `/blog/`, `/services/`, `/services/<slug>/` (6) | mesmos endereços |
| `/urace-academy/`, `/kart-training-packages/`, `/kart-driving-school/` | `/academy/` |
| `/professional-kart-team-racing-team/` | `/pro-team/` |
| `/kart-lessons-for-beginners/` | `/for-beginners/` |
| `/the-driver-factory/`, `/plan-your-career/`, `/typ/`, `/the-driver-factory-thank-you-page/`, `/lp1-cancelada/` … `/lp4-cancelada/` | `/career/` |
| `/services/group-events-social-gatherings/`, `/group-events-social-gatherings/` | `/services/group-events/` |
| `/corporate-events/` | `/services/corporate-events/` |
| `/birthday-party/` | `/services/birthday-party/` |
| `/shop/` | `/store/` |
| `/book-online/` | `/services/arrive-and-drive/` *(era `/ops/portal/reserve`; mudou neste PR porque é página indexada e tem de ir para página pública — §10)* |
| `/checkout/` | `/cart/` |
| `/my-account/` e tudo abaixo (`/lost-password/`, `/orders/`, …) | `/ops/portal` |
| `/affiliate-account/`, `/affiliate-registration/`, `/affiliate-reset-password/` | `/ops/portal` |
| `/<slug-do-artigo>/` (7) | `/blog/<slug>/` |
| `/category/<c>/` (4) | `/blog/category/<c>/` |
| `/product/<slug>/` (69 conhecidos) | `/store/p/<slug>/` |
| `/product/<slug>/` fora do catálogo (ex. `otk-magnesium-wheels-set-mxc-130mm-210mm`) | `/store/` |
| `/product/go-kart-driving-experience/` | `/services/arrive-and-drive/` |
| `/product-category/chassis|competition-karts|engines|parts|tires|custom-kart-suits|official-urace-products|kart-driver-training/` | `/store/<mesma>/` |
| `/product-category/apparel/`, `/apparel-gear/` | `/store/official-urace-products/` |
| `/product-category/suits/`, `/apparel-gear/apparel/suits/` | `/store/custom-kart-suits/` |
| `/product-category/classes-programs/` | `/store/kart-driver-training/` |
| `/product-category/karts-parts/` | `/store/parts/` |
| `/product-category/<pai>/<filho>/…` (o resto das ~120) | `/store/<categoria do último pedaço>/` quando existe, senão `/store/` |
| `/product-category/used/`, `/teste/`, `/sem-categoria/`, `/accessories/` e as subcategorias delas | `/store/` |
| `/product-tag/jecko/`, `/product-tag/parolin/` | `/store/` |
| `/store/page/N/`, `/blog/page/N/`, `/product-category/<c>/page/N/` | a primeira página da lista |
| `/sitemap_index.xml`, `/post-sitemap.xml`, `/page-sitemap.xml`, `/product-sitemap.xml`, `/category-sitemap.xml`, `/product_cat-sitemap.xml`, `/product_tag-sitemap.xml` | `/sitemap.xml` |
| qualquer endereço **sem** a barra final | o mesmo com a barra (301), como o WordPress fazia |

### 7.2 Como o redirecionamento funciona

`paginas_site.destino(caminho)` resolve primeiro o mapa exato (`redirecionamentos()`, montado a
partir de `antigos` de cada página, dos produtos e das categorias) e depois as **famílias**
(`_familia`): subcategoria de produto, etiqueta, `page/N`, produto fora do catálogo, telas da conta
do WordPress e sitemaps do Yoast. `api/vitrine.pagina()` responde 301.

### 7.3 O que ainda depende do lado do WordPress

O redirecionamento acima só funciona **depois** que `urace.us` apontar para o nosso servidor. Para
não perder o indexado, no dia da troca é preciso:

1. **DNS**: `urace.us` e `www.urace.us` passam a apontar para o VPS; o Caddy emite o certificado e
   serve o site com `CC_SITE_HOSTS=urace.us,www.urace.us,novo.urace.us`.
2. `www.urace.us` → `urace.us` (301), um canonical só.
3. `CC_SITE_PREVIEW=0` para o `robots.txt` liberar e o `noindex` sair.
4. Reenviar o `sitemap.xml` no Google Search Console e **manter o domínio antigo redirecionando**
   (se o WordPress continuar de pé em outro endereço).

---

## 8. Formulários e proteção

| | urace.us | novo.urace.us |
|---|---|---|
| Formulário de contato | CF7 nas páginas de serviço e nas LPs (não há formulário em `/contact/`) | `/contact/` com assunto, produto, honeypot, 8 envios/IP a cada 10 min, funciona sem JS |
| Para onde vai o lead | e-mail (admin do WordPress) + Google Sheets | **oportunidade em Vendas** (origem *Site*, etapa NOVO) + e-mail para `support@urace.us` + confirmação para a pessoa |
| Campos de campanha | `utm_*`, `gclid`, `fbclid`, `fbp`, `fbc`, `campaign_id`, `adset_id`, `content_id` | nenhum |
| Anti-robô | reCAPTCHA | honeypot + limite por IP |
| Pedido da loja | não existe (é só carrinho) | `/ops/api/vitrine/pedido` vira oportunidade com produto, variação, quantidade e valor |

---

## 9. Lista de polimento do site novo (o que não entrou neste PR)

Cada item é uma coisa pequena e verificável. O que entrou neste PR está em §4 ("já resolvido").

1. **Dois botões, dois pagamentos, um texto** em `/services/arrive-and-drive/`: "Add to cart"
   (Stripe) e "Continue to booking" (invoice do QuickBooks), e o texto embaixo só explica a
   invoice. É o passo mais confuso do caminho de compra. *Não mexi: `static/agenda.js` está sendo
   alterado por outra frente agora.* Precisa de decisão do dono: **um** caminho de pagamento para a
   sessão, ou os dois com o texto explicando cada um.
2. **"URACE SHORTS" órfão** em `/store/p/arrive-and-drive/`: depois de tirar o código do tema,
   sobrou o título "URACE SHORTS" seguido dos títulos de 6 vídeos **sem os vídeos** (o carrossel
   do YouTube não veio na cópia). Ou volta o carrossel, ou o bloco sai de `dados/produtos.json`.
3. **Busca na loja** (item 1 do §4): 69 produtos sem busca. Dá para fazer no servidor
   (`/store/?s=`), sem JavaScript novo.
4. **`og:locale` fixo em `en_US`** mesmo quando a página renderiza em português.
5. **`/legal/privacy.html`**: endereço com `.html` (a regra da casa é endereço limpo) e fora do
   `sitemap.xml`. Deveria ser `/privacy/`, com o `.html` redirecionando.
6. **`/accessibility/` é órfã**: não há link para ela no menu nem no rodapé do site novo (no antigo
   também não havia).
7. **Links do rodapé com 20 px de altura** ("Birthdays", "Corporate Events" na home): abaixo dos
   40 px da regra da casa. Mexe no CSS do rodapé, que é compartilhado — fica para um PR só disso.
8. **Loja sem paginação**: `/store/` lista os 69 produtos numa página só — 60 `<img>` (59 com
   `loading="lazy"`, então o custo real é menor) e 40 kB de HTML.
9. **Carrinho precisa de JavaScript**: tem aviso e dois links de saída, mas o do WooCommerce
   funciona sem.
10. **Produto que falta** (item 17 do §4): `otk-magnesium-wheels-set-mxc-130mm-210mm`.

---

## 10. Precisa de decisão do dono

1. **Medição**: o novo não tem Google Tag Manager, Google Analytics nem Meta pixel. Sem eles,
   campanha paga fica cega e o Search Console perde a conversão. Entra? Com qual id? (A política de
   segurança do site hoje é `script-src 'self'`: aceitar script de fora muda essa política.)
2. **Campos de campanha no formulário** (`utm_*`, `gclid`, `fbclid`, `fbp`, `fbc`): o CF7 de hoje
   manda; o `/contact/` do novo não. Precisa?
3. **Programa de afiliados** (SliceWP): mantém, migra ou encerra? Hoje
   `/affiliate-account/` redireciona para o portal, que não tem afiliado.
4. **As 4 landing pages de anúncio**: tem campanha ativa apontando para
   `/kart-lessons-for-beginners/`, `/kart-driving-school/`, `/kart-training-packages/` ou
   `/professional-kart-team-racing-team/`? Hoje elas redirecionam para `/for-beginners/`,
   `/academy/` e `/pro-team/`. Se tiver anúncio, o layout de campanha precisa existir no novo.
5. **As duas lojas**: a recomendação é desligar o checkout do WooCommerce no mesmo dia da troca de
   DNS (§6). Confirma? Enquanto as duas estiverem no ar, estoque, preço e pedido ficam em dois
   lugares.
6. **Cupom de desconto** no carrinho novo: a equipe usa cupom hoje?
7. **Mensalidade**: o `subscriptions-for-woocommerce` cobra alguma assinatura hoje? O novo cobra
   mensalidade pelo QuickBooks (#169); se houver assinatura viva no WooCommerce, precisa migrar
   uma por uma.
8. **Busca na loja** (item 3 do §9): faço?
9. **Produto que falta**: `otk-magnesium-wheels-set-mxc-130mm-210mm` entra no catálogo do novo?
10. **`/book-online/`**: neste PR passou a redirecionar para `/services/arrive-and-drive/` (página
    pública, indexável, com a agenda e os preços) em vez de `/ops/portal/reserve`. Era decisão do
    #164; se o dono preferir mandar direto para o portal, é uma linha.
11. **Tradução**: o GTranslate traduz o site inteiro hoje. No novo, EN/PT só nas páginas da compra.
    Traduz o site inteiro?

### Depende de acesso que eu não tenho

- **WordPress / Hostinger**: desligar o checkout do WooCommerce, conferir se há assinatura viva,
  ver os pedidos de verdade, ver para onde o CF7 manda e-mail hoje, apagar as páginas depois da
  troca. (Aberto desde 01/10: o e-mail admin e o pop-up do CF7 iam para `@colinatech.com.br`.)
- **WooCommerce (API/painel)**: contar os pedidos de hoje, o estoque e os cupons; comparar preço
  com `dados/produtos.json`.
- **DNS do urace.us**: apontar para o VPS, `www` → raiz.
- **Gateway antigo**: ver na conta do Stripe quais pedidos vieram do WooCommerce e quais do novo
  (não li a conta do Stripe: isso é produção).
- **Google Tag Manager / Analytics / Meta**: os ids e o acesso são do dono.
- **Google Search Console**: reenviar o sitemap e acompanhar os 301 depois da troca.
