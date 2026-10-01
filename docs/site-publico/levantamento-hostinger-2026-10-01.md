# Levantamento urace.us — Hostinger + WordPress

> Issue #47. É o relatório da extensão do navegador, de 01/10/2026, guardado como chegou. Só foram tirados um e-mail pessoal e a lista de usuários administradores. As decisões que saíram dele estão em `decisoes-2026-10-01.md`.

Data: 01/10/2026, entre 16h40 e 17h35 UTC. Só leitura.

Como acessei: hPanel com a sessão já aberta no Chrome. Entrei no wp-admin pelo botão "Admin WordPress" do hPanel, que faz login automático como o usuário **colinatech** (não digitei senha). Registros de DNS, cabeçalhos HTTP e páginas públicas foram consultados de fora, por consultas públicas. Também cliquei em coisas que só mudam a visualização: abas, um dropdown que fechei sem escolher nada e o "tamanho da página" de duas tabelas do hPanel, que passei para 50 linhas.

**O que precisa de atenção primeiro:**

1. O backup completo do site (.wpress, 1,8 GB) responde **HTTP 200** a quem souber o nome do arquivo. Hoje só o nome aleatório protege o arquivo.
2. Os leads estão indo para a Colina Tech, e não para a URACE. O e-mail admin do WordPress é `desenvolvimento@colinatech.com.br`. O pop-up de CF7 manda para esse e-mail. O plugin SXS LP/Kommo está **sem token** e manda os leads para o e-mail de reserva, também em colinatech.com.br.
3. Seis páginas de serviço linkam para 4 produtos que estão em **rascunho**, e por isso os botões de reservar dão 404. Os 4 produtos foram despublicados juntos em 13/05/2026 às 14:24.
4. O WordPress antigo do lp.urace.us continua instalado, com **12 plugins vulneráveis**, e o login dele está aberto em `urace.us/lp/wp-login.php`.
5. A licença do Elementor Pro está **cancelada** e ligada à conta da Colina Tech.
6. **Alguém está mexendo no site agora.** O produto 4787 "Arrive and Drive" passou de rascunho para publicado às 17:28 UTC, durante o levantamento. O produto 98 foi alterado hoje às 14:31 UTC. Não fui eu: todas as minhas consultas foram só de leitura.

---

## Hostinger

**1. Plano**

- **Premium Web Hosting**, válido até **07/10/2027** (Sites › lista de sites).
- Renovação automática **ligada**. Próxima cobrança em **23/09/2027**, de **R$ 443,88** (Faturas › Assinaturas).
- Recursos (Plano de hospedagem › Detalhes do plano): 25 GB de disco, 2 GB de RAM, 1 núcleo, 400 mil inodes, 25 sites, 80 processos, 40 PHP workers.
- Uso nas últimas 24h (Painel de controle): disco **16,42 de 25 GB**, inodes 69,7 mil, CPU 26%, memória 255 MB.
- Na mesma conta existe uma segunda assinatura: **Starter Business Email Trial** (lp.urace.us), com renovação automática **ligada**, cobrança em **05/03/2027** e preço de renovação de **R$ 41,88**. Tem 0 de 2 caixas criadas.

**2. Domínios**

- urace.us e lp.urace.us aparecem como **"Domínios externos"**: registrados fora da Hostinger (Domínios › Meus domínios).
- O registrador **não foi encontrado**. O hPanel não mostra, e a consulta pública (RDAP .us) não respondeu.
- Nameservers atuais: `ns-cloud-d1…d4.googledomains.com`, que são do **Squarespace Domains**, o antigo Google Domains. *Correção de 01/10: não é o Google Cloud DNS* (Plano › Detalhes do plano › Nameservers). O DNS é gerido no Google, **não na Hostinger**. O editor de DNS do hPanel só oferece "Transferir".
- Registros públicos, consultados por DNS público:

| Tipo | Nome | Destino |
|---|---|---|
| A | urace.us | 212.85.28.20 (Hostinger, server451) |
| CNAME | www | urace.us |
| A | lp.urace.us | 212.85.28.20 |
| MX | urace.us | Google Workspace (aspmx.l.google.com e alt1–alt4) |
| TXT | urace.us | SPF `include:_spf.google.com ~all` |
| TXT | google._domainkey | DKIM do Google (existe) |
| TXT | _dmarc | DMARC `p=none`, relatórios para dmarc@urace.us |

- O lp.urace.us **não tem MX**, então o e-mail trial da Hostinger nunca foi conectado. O hPanel mostra "O domínio não está conectado ao seu e-mail".
- Na prática, lp.urace.us responde **301 para urace.us**.

**3. Sites da conta** (Sites)

- **urace.us**: WordPress, criado em 08/10/2025.
- **lp.urace.us**: WordPress separado, criado em 03/03/2026. É um subdomínio da pasta `public_html/lp` (Domínios › Subdomínios).
- Não há domínios estacionados (0/100).

**4. Servidor**

- PHP **8.2** (Avançado › Configuração de PHP). Também há 8.3, 8.4 e 8.5 disponíveis.
- Limites no hPanel: memory_limit 512M, upload e post 256M, max_execution_time 300, max_input_vars 5000, max_input_time 240.
- O WordPress informa memory_limit de **1536M** em execução, então algo sobrescreve esse valor.
- Servidor web **LiteSpeed**, mas o **Cache Automático da Hostinger está desligado** (Avançado › Gerenciador de cache).
- O plugin LiteSpeed Cache **não está instalado** no urace.us. Mesmo assim existe o drop-in `advanced-cache.php` e o WP_CACHE está ligado.
- **CDN inativo** nos dois domínios (Desempenho › CDN).
- Cache de objetos não verificado.
- SSL "**Lifetime SSL**" ativo nos dois, criado em 04/03/2026, sem vencimento (Segurança › SSL).
- O **emissor do certificado não foi encontrado**: o hPanel não mostra, e minha conexão externa passa por um proxy que troca o certificado.
- Localização do servidor: EUA (Carolina do Norte). Backups ficam em Boston.

**5. Backups** (Arquivos › Backups)

- Automáticos e **semanais**. O plano não permite backup manual: aparece "Bloqueado".
- **5 disponíveis**: 24/09, 17/09, 10/09, 03/09 e 27/08/2026. O mais recente é de **24/09/2026, 18:58**. O próximo estava marcado para 01/10/2026.
- A Hostinger avisa que, desde 25/06/2026, arquivos de plugins de backup, cache e exportações de banco **não entram** nesses backups.
- À parte, existem **5 backups do All-in-One WP Migration** dentro do próprio site, de 23/07 a 26/09/2026, somando **cerca de 12 GB** (wp-admin › All-in-One WP Migration › Backups). Isso deve explicar a maior parte dos 16,4 GB usados.

**6. E-mails** (E-mails)

- **Nenhuma caixa na Hostinger para urace.us.** O único plano é o trial de lp.urace.us, com 0 caixas.
- O MX de urace.us aponta para o **Google**.

**7. Banco de dados** (Bancos de dados › Gerenciamento; o phpMyAdmin não foi aberto)

| Banco | Tamanho | Criado | Uso provável |
|---|---|---|---|
| u762058566_db_urace_2026 | 193 MB | 29/07/2026 | **Banco ativo do urace.us** (confirmado em Saúde do site) |
| u762058566_uracelp | 75 MB | 03/03/2026 | WordPress do lp |
| u762058566_iovVZ | 223 MB | 08/10/2025 | Parece o banco da instalação original. Não confirmei se ainda está em uso |

- Versão: **MariaDB 11.8.9**. Prefixo das tabelas: `wp_`.

**8. Acesso**

- **SSH desativado** (status INACTIVE), porta 65002 (Avançado › Acesso SSH). Não vi chaves cadastradas.
- **1 conta FTP**, só a principal, apontando para public_html (Arquivos › Contas FTP).
- **Colaboradores com acesso à conta** (Perfil › Compartilhamento de conta › Dar acesso): **1**, um endereço @gmail da Colina Tech, com acesso "Gerenciar serviços e faturamento" a 1 serviço, ativo.
- O 2FA da conta Hostinger é **por e-mail** (urace@urace.us), com verificação de dispositivo novo ligada. Não há app autenticador (Perfil › Segurança).

**9. Cron jobs** (Avançado › Cron Jobs)

- **Nenhum cadastrado.** O WP-Cron roda por visita, e a Saúde do site acusa evento atrasado (veja abaixo).

**10. Avisos do painel**

- urace.us: "Saúde do site – Ação necessária", **4 vulnerabilidades**, 11 atualizações de plugin e "Malware limpo" (Painel de controle).
- lp.urace.us: **40 vulnerabilidades** e 16 atualizações.
- A página "Detector de malware" não carregou o detalhe.
- O sino só tem promoções (e-mail grátis, domínio grátis, e-mail marketing).
- Atualização automática configurada como **"Atualizações automáticas inteligentes"** (WordPress › Segurança). Mesmo assim os plugins vulneráveis não foram atualizados.

---

## WordPress (urace.us)

**1. Versão e tema** (Ferramentas › Saúde do site › Info; Aparência › Temas)

- WordPress **7.1.2**.
- Tema ativo: **Urace**, da Colina Tech. Sem número de versão e **não é tema filho**.
- **Nenhum tema inativo**. A Saúde do site recomenda ter um tema padrão de reserva.
- Plugins de uso obrigatório (mu-plugins): Elementor Safe Mode e Hostinger Smart Auto Updates 1.0.8.
- Drop-in: advanced-cache.php.

**2. Plugins**: veja a seção Plugins.

- **sxs-lp-for-urace** ("SXS LP for Urace" 1.1.0, autor SXS Group, ativo): "Blocos Gutenberg e template para as landing pages da URACE, com formulário integrado ao Kommo".
- A tela dele fica em Configurações › SXS LP / Kommo, com os campos Subdomínio, Token de longa duração, ID do funil, ID da etapa e E-mail de reserva.
- **Subdomínio, token, funil e etapa estão vazios.** O e-mail de reserva é um endereço **@colinatech.com.br**.
- Pela própria descrição da tela, sem Kommo configurado todo lead dos blocos de LP vai para esse e-mail de reserva.

**WooCommerce 11.1.2** (WooCommerce › Configurações)

- Moeda USD.
- Endereço da loja: 10724 Cosmonaut Blvd, Orlando, FL 32824.
- Vende para países específicos.
- **Impostos desligados.** Cupons ligados.
- Pagamento: **Stripe ativo.** Square, Cash App Pay (Square) e Gift Cards (Square) aparecem como "Ação necessária / Completar configuração", ou seja, não estão operando. Clover está instalado, mas o plugin está **inativo**. Transferência, cheque e pagamento na entrega estão desativados.
- Frete: zona "US" com Standard shipping e Free shipping. "Resto do mundo" sem método.

**Elementor / Elementor Pro**

- Elementor 4.2.3 e Elementor Pro 4.2.2.
- Licença: **"Status: Cancelled"**, conectada a uma conta @colinatech.com.br (Elementor › Licença).
- Em todo o admin aparece o aviso "Your Elementor Pro subscription has expired".

**Outros plugins citados**

- Yoast SEO 28.5 (atualização pendente).
- GTM4WP 2.0.4.
- GTranslate 5.0.1.
- SliceWP 1.2.10: vulnerável, com 6 afiliados ativos.
- **Jetpack não está instalado.**
- All-in-One WP Migration 7.110 (vulnerável) + Unlimited Extension 2.87.
- Contact Form 7 6.1.7.
- Meta for WooCommerce 3.7.6, que é o antigo Facebook for WooCommerce.

**3. Produtos**: veja a seção Produtos de reserva.

**4. Como o Arrive and Drive monta o formulário** (só leitura)

- Quem monta é o **tema Urace**, não um plugin. O `functions.php` do tema gera o formulário e injeta três objetos na página: `window.ctKartOptions`, `ctKartCategories` e `ctKartBasePrice`.
- O `js/all.js` do tema desenha os campos:
  - número de pilotos (`ct_kart_drivers`);
  - para cada piloto, a **categoria** e o **número de dias** (`ct_kart_driver[n][days]`);
  - os **adicionais**, cobrados por dia.
- Existe template próprio por produto em `woocommerce/pages/page-98.php` (além de 96, 100, 236, 237 e 3518).
- **Preço base**: é o preço do produto no WooCommerce. Hoje o go-kart-driving-experience custa US$ 719.
- **Categorias**: vêm do atributo global **"Categories"** (Produtos › Atributos), com 7 termos: Baby kart 5–7, Micro 6–8, Mini 8–11, Junior 11–14, Senior 15–18, Adult 18+ e "Not sure yet".
- **Adicionais**: vêm do grupo ACF **"Content – Add On's"**, preenchido dentro da tela de edição de cada produto (ACF › Field Groups). Valores atuais na página:

| Adicional | Valor |
|---|---|
| Track fee | +$80 |
| Own kart | −$170 |
| Lead and follow | +$768 |

- **Divergência**: o atributo "Lead and Follow" diz "Yes (+$769.90)", e o adicional cobra $768.

**5. Pedidos** (contagem pela API, sem abrir pedido)

- **27 no total**, do primeiro em 11/09/2024 ao último em 27/09/2026.
- Status: **17 "processando", 9 "falhou", 1 "cancelado", 0 "concluído"**.
- **Últimos 90 dias** (desde 03/07/2026): **1 pedido**, em "processando".

**6. Usuários** (Usuários)

- 58 contas: **45 customer**, 9 administrador, 6 afiliado e 1 assinante. Não há editor nem gerente de loja.
- **9 administradores**, entre eles o usuário da agência que o hPanel usa no login automático. A lista de nomes ficou só no relatório entregue ao dono.

**7. Formulários**

Contact Form 7 (destinatários via API):

| Formulário | Vai para |
|---|---|
| Contact (166) | support@urace.us, urace@urace.us |
| Newsletter (167) | support@urace.us, urace@urace.us |
| Contact Services Page (1179) | support@urace.us, urace@urace.us |
| **[CT] Form Pop-up (1839)** | `[_site_admin_email]`, ou seja, **desenvolvimento@colinatech.com.br** |

Kommo:

- Widget/botão do Kommo carregado de `gso.kommo.com` em todas as páginas, via **WPCode › Header & Footer › Footer**.
- Formulário Kommo (amoForms) **fixo no código do tema**, em `page-contact.php` (form 1728856) e `page-pro-team.php`.
- Na página /the-driver-factory/ (Elementor Canvas) há outro amoForm (1728864) e também um formulário do Elementor Pro chamado "Form LP URace". Não abri as submissões.

Envio de e-mail: WP Mail SMTP com mailer **Gmail**, remetente @urace.us.

**8. Configurações › Geral e Links permanentes**

- Endereço do site e do WordPress: https://urace.us.
- E-mail do admin: **desenvolvimento@colinatech.com.br**.
- Fuso horário: **UTC+0**. Deveria ser America/New_York.
- Registro de novos usuários desligado. Função padrão: assinante.
- Links permanentes: `/%postname%/`. Base de produto: `/product/`.
- Configurações › Leitura: indexação permitida, página inicial "Home".

**9. Integrações**

- **Google Tag Manager: GTM-59CCNDC**, via GTM4WP (Configurações › Google Tag Manager). Não há GA4 ou Google Ads direto no HTML.
- **Pixel da Meta: ligado.** O `fbevents.js` é carregado pelo Meta for WooCommerce, com catálogo "[Urace] Catálogo" conectado e 3 produtos aprovados (Marketing › Facebook). O ID do pixel não aparece no HTML. Lojas do Facebook e do Instagram estão como "Adicionar canal", ou seja, não conectadas.
- **Código do Kommo**: em WPCode (rodapé), no tema (page-contact.php e page-pro-team.php), no Elementor (/the-driver-factory/) e no plugin SXS LP, que está sem configuração.
- **RD Station**: script no cabeçalho via WPCode, mais o plugin "RD Station" e as integrações "RD Station CF7".
- **Snippets WPCode ativos**, todos criados por Lucas Azaro em 26/09/2026:
  - Schema de Produto;
  - Schema LocalBusiness;
  - Botões flutuantes Instagram + WhatsApp;
  - CSS de título.

**10. Saúde do site** (Ferramentas › Saúde do site): status "Should be improved"

- **Crítico**: "Page cache is detected but the server response time is still slow". A mediana foi de **712 ms**, contra o limite de 600 ms, e não há cabeçalhos de cache.
- **Recomendados**:
  - remover plugins inativos;
  - ter um tema padrão;
  - PHP 8.2 antigo;
  - evento agendado atrasado (`action_scheduler_run_queue`);
  - usar cache de objetos persistente.

**11. Onde estão os endereços**

| Endereço exibido | Onde está |
|---|---|
| 10724 Cosmonaut Blvd, Orlando, FL 32824 | **Rodapé do tema** (`footer.php`, código fixo), **WooCommerce › Geral** (endereço da loja) e meta description do Yoast na página Contact |
| "10724 Cosmonaut Blvd, **Box 5**" | **Elementor**: widget de título "Address", seção "Location" das páginas de serviço (arrive-and-drive, kart-school, intensive-training-camp, professional-coaching, birthday-party, corporate-events, group-events-social-gatherings). A origem é o template Elementor "Página de serviço V2" (id 1212). Também está **fixo no tema** em `page-contact.php` (página Contact, id 31, que tem conteúdo vazio) |
| "10724 Cosmonaut Blvd, **Box 3**" (4º endereço, que não estava na lista) | Snippet WPCode **"URACE - Schema LocalBusiness"**, no schema JSON-LD que o Google lê |
| **6149 Cyril Ave** | **Não encontrado.** Procurei em todas as páginas, posts e produtos dos sitemaps, nos arquivos do tema, nos snippets WPCode, nos menus, widgets, e-mails do WooCommerce e na busca do admin de todos os tipos de post. Pode estar no WordPress do lp, que redireciona e eu não abri, ou fora do site (Google Business, Kommo, assinaturas de e-mail) |

---

## Produtos de reserva

86 produtos no total: 77 publicados, 8 rascunhos, 1 privado e 1 na lixeira (Produtos › Todos). A maioria é de peças.

| Slug pedido | ID | Nome atual | Status | Preço | Observação |
|---|---|---|---|---|---|
| go-kart-driving-experience | 98 | Arrive and Drive — 4-stroke (7+) | **Publicado** (200) | $719 | Renomeado, mas o slug foi mantido. Alterado **hoje, 14:31 UTC** |
| urace-kart-school | 237 | Urace Kart School | **Rascunho** (404) | $1.856,90 | Variável, 4 variações |
| urace-intensive-training-camp | 236 | Urace Intensive Training Camp | **Rascunho** (404) | $2.075,00 | Variável, 7 variações |
| corporate-karting-events | 96 | Birthday Party / Corporate Events | **Rascunho** (404) | $2.695,00 | Simples |
| professional-coaching | 100 | Professional Coaching | **Rascunho** (404) | $369,00 | Variável, 12 variações |

- Os 4 rascunhos têm a **mesma data de modificação: 13/05/2026 14:24**. Isso indica que foram despublicados juntos. Nenhum está na lixeira e nenhum mudou de slug.
- O tema tem template próprio para cada um (`woocommerce/pages/page-96/100/236/237.php`).
- Os botões "reservar" de 7 páginas de serviço (Elementor) apontam para esses slugs. Birthday Party e Group Events também apontam para `corporate-karting-events`.
- Outros produtos ligados:
  - 297 "Professional Coaching (Copy)", **privado**.
  - Rascunhos "Driving Experience (Copy)" (3647 e 4041) e "Default for Unmatched Products" (3659).
  - **4787 "Arrive and Drive"**, variável de $500 com 5 variações. Foi **criado hoje e publicado às 17:28 UTC, durante o levantamento**.
  - Também publicados (data de criação não verificada): os 4 "Arrive and Drive" por categoria (4770–4773, de $500 a $899) e os planos URACE Academy/Boost (4778–4783).

---

## Plugins

Fonte: wp-admin › Plugins, cruzado com hPanel › WordPress › Segurança (Patchstack). São 31 plugins, 27 ativos.

| Plugin | Versão | Ativo | Atualização pendente | Segurança (Patchstack) |
|---|---|---|---|---|
| Advanced Custom Fields PRO | 6.8.10 | Sim | — | Seguro |
| All-in-One WP Migration and Backup | 7.110 | Sim | **Sim** | **Vulnerável** |
| All-in-One WP Migration Unlimited Extension | 2.87 | Sim | — | Seguro |
| Cart Abandonment Recovery for WooCommerce | 2.1.3 | Sim | — | Seguro |
| CF7 Google Sheet Connector | 5.2.8 | Sim | — | Seguro |
| Clover Payments for WooCommerce | 2.3.2 | **Não** | — | Seguro |
| Contact Form 7 | 6.1.7 | Sim | — | Seguro |
| Copy & Delete Posts | 1.5.6 | Sim | **Sim** | Seguro |
| Elementor | 4.2.3 | Sim | **Sim** | Seguro |
| Elementor Pro (licença cancelada) | 4.2.2 | Sim | **Sim** | Seguro |
| EWWW Image Optimizer | 8.8.0 | Sim | — | Seguro |
| Flamingo | 2.6.4 | Sim | — | Seguro |
| GTM4WP | 2.0.4 | Sim | — | Seguro |
| GTranslate | 5.0.1 | Sim | — | Seguro |
| Hello Dolly | 1.7.2 | **Não** | — | Seguro |
| Meta for WooCommerce | 3.7.6 | Sim | — | Seguro |
| Post Types Order | 2.5 | Sim | **Sim** | Seguro |
| RD Station | 5.7.4 | Sim | — | Seguro |
| Really Simple Security | 9.8.3 | **Não** | — | Seguro |
| ReCaptcha v2 for Contact Form 7 | 1.5.0 | Sim | — | Seguro |
| SliceWP | 1.2.10 | Sim | **Sim** | **Vulnerável** |
| SVG Support | 2.6.1 | Sim | — | Seguro |
| SXS LP for Urace | 1.1.0 | Sim | — | Seguro |
| WooCommerce | 11.1.2 | Sim | — | Seguro |
| WooCommerce Square | 5.4.3 | Sim | **Sim** | Seguro |
| WooCommerce Stripe Gateway | 10.9.0 | Sim | **Sim** | Seguro |
| WP Activity Log | 5.6.5 | **Não** | **Sim** | **Vulnerável** |
| WP Mail SMTP | 4.9.0 | Sim | **Sim** | Seguro |
| WPCode Lite | 2.3.9 | Sim | — | Seguro |
| Yoast Duplicate Post | 4.7 | Sim | — | Seguro |
| Yoast SEO | 28.5 | Sim | **Sim** | Seguro |

- O hPanel diz "4 vulnerabilidades", mas lista só 3 plugins. A quarta não foi encontrada.

**lp.urace.us** (hPanel › lp.urace.us › WordPress › Segurança): 19 plugins, **12 vulneráveis**:

- Rank Math SEO 1.0.270
- Really Simple Security 9.5.8
- All-in-One WP Migration 7.102 + Unlimited 2.82
- Elementor 3.35.6 / Pro 3.35.1
- Copy & Delete Posts 1.5.2
- LiteSpeed Cache 7.8
- GSheetConnector for CF7 5.1.6
- GTM4WP 1.22.3
- HandL UTM Grabber 2.8.3
- WPCode Lite 2.3.4

Tema ativo URACE e Twenty Twenty-Five 1.4 (desatualizado).

---

## Avisos e riscos

Do mais grave para o menos grave:

1. **Backup completo exposto.** Ao pedir só o cabeçalho (sem baixar), `urace.us/wp-content/ai1wm-backups/<arquivo>.wpress` respondeu 200 com 1,8 GB. A listagem da pasta dá 403, então hoje só o nome aleatório protege. O arquivo contém o banco inteiro: clientes, pedidos e senhas com hash.
2. **WordPress do lp esquecido e vulnerável.** O domínio redireciona, mas os arquivos continuam acessíveis: `urace.us/lp/wp-login.php` e `/lp/readme.html` respondem 200. São 12 plugins vulneráveis, e o banco de 75 MB continua lá.
3. **Leads e controle com a agência.** O e-mail admin, o pop-up CF7, o e-mail de reserva do SXS/Kommo e a licença do Elementor estão em contas Colina Tech. O tema é deles e não tem tema filho, então qualquer atualização do tema sobrescreve ajustes. Há também um colaborador na Hostinger com acesso a **faturamento** (um @gmail da Colina Tech), e o login automático do hPanel entra como o usuário "colinatech".
4. **Kommo do SXS LP sem configuração.** Leads dos blocos de LP não chegam ao CRM, só ao e-mail de reserva.
5. **Reservas quebradas.** 4 produtos em rascunho geram 404 em 6 páginas de serviço. Nos últimos 90 dias entrou só 1 pedido.
6. **3 plugins vulneráveis** no urace.us (All-in-One WP Migration, SliceWP, WP Activity Log) e 11 atualizações pendentes, mesmo com a atualização automática "inteligente" ligada.
7. **Elementor Pro com licença cancelada.** Sem atualizações de segurança, e os widgets Pro podem parar de editar.
8. **Duas pessoas mexendo ao mesmo tempo.** Produtos estão sendo criados e publicados hoje. Há 9 administradores, incluindo contas @gmail e @itcygnus.com, e o WP Activity Log está **inativo**, então não fica registro de quem mudou o quê.
9. **Editor de arquivos de tema e plugin ligado** no wp-admin. Qualquer admin edita PHP direto em produção.
10. **Endereços divergentes**: Box 5 nas páginas, Box 3 no schema, sem box no rodapé, e o 6149 Cyril Ave não foi localizado. Isso confunde o Google e o cliente.
11. **Fuso UTC+0.** Datas de pedidos e reservas ficam 4–5h adiantadas em relação a Orlando.
12. **Desempenho**: resposta mediana de 712 ms. O cache automático da Hostinger e o CDN estão desligados, e o LiteSpeed Cache não está instalado, apesar do drop-in de cache.
13. **Disco**: 16,4 de 25 GB, dos quais cerca de 12 GB são backups .wpress dentro do site. Os backups semanais da Hostinger excluem pastas de plugins de backup.
14. **Pedidos nunca concluídos.** 17 estão em "processando" e nenhum em "concluído", o que distorce relatórios e o Meta/GTM.
15. **GTM4WP envia dados do cliente logado para o dataLayer** (nome e endereço de cobrança e entrega apareceram na home para o usuário logado). Vale revisar o que as tags do GTM fazem com isso.
16. Divergência de preço do Lead and Follow ($768 no adicional e $769,90 no atributo).
17. A API pública `/wp-json/wp/v2/users` expõe nomes de usuário (por exemplo, colinatech).
18. DMARC em `p=none` e 2FA da Hostinger só por e-mail.
19. Assinatura de e-mail trial no lp.urace.us com renovação automática (R$ 41,88 em 05/03/2027) sem nenhuma caixa em uso.
20. Banco `u762058566_iovVZ` (223 MB, de 2025) aparentemente sem uso.

---

## Perguntas para o dono

1. A Colina Tech ainda presta serviço? Se não, quem assume o e-mail admin, a licença do Elementor, o acesso de colaborador na Hostinger (com faturamento) e a conta admin "colinatech"?
2. Quem despublicou os 4 produtos em 13/05/2026, e por quê? Eles devem voltar como estão ou ser substituídos pelos novos "Arrive and Drive" e planos Academy criados hoje?
3. Quem está editando produtos hoje (o 4787 foi publicado às 17:28 UTC)? É o Lucas?
4. Qual é o endereço oficial: Box 3, Box 5 ou sem box? E o que é o 6149 Cyril Ave: endereço antigo, oficina, correspondência?
5. O lp.urace.us ainda serve para alguma coisa? Se não, pode ser removido, com o banco e o trial de e-mail?
6. Os leads das LPs devem ir para o Kommo? Se sim, quem tem o subdomínio e o token para configurar o SXS LP?
7. Os 5 backups .wpress dentro do site precisam ficar lá? Dá para mover para fora e apagar?
8. Os 9 administradores ainda precisam desse nível de acesso (a lista está no relatório entregue ao dono)?
9. Os 17 pedidos em "processando" já foram atendidos e podem ser marcados como concluídos?
10. Square e Clover: vão ser usados, ou fica só o Stripe?
11. Onde está registrado o domínio urace.us, e quem tem acesso ao Google Cloud DNS?

Nada foi alterado.
