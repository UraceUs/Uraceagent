# Prompt da extensão — levantar tudo do site público na Hostinger (SÓ LEITURA)

Cole isto na extensão do navegador, com a sessão da Hostinger (hPanel) aberta e o
WordPress do urace.us logado como administrador. Issue #39.

---

Você vai **levantar informações** sobre o site urace.us na Hostinger e no WordPress dele.
**Não altere nada.** Nenhum botão de salvar, publicar, atualizar, instalar, desinstalar,
ativar, desativar, excluir, restaurar, migrar, trocar senha ou mudar DNS. Se uma tela pedir
confirmação de qualquer mudança, **cancele** e anote. Se não tiver certeza de que um clique
só mostra informação, **não clique**: anote o que viu e siga.

**Nunca copie** senha, chave de API, token, segredo de SMTP, chave SSH, código de
autenticação nem dado de cartão. Quando aparecer um, anote só que existe e onde (ex.:
"chave de API do Kommo configurada no plugin X"). Dado de cliente (nome, e-mail, pedido)
também não entra: conte, não copie.

## O que levantar

### 1. Hostinger (hPanel)
1. **Plano** de hospedagem, validade, renovação automática (sim/não), data de vencimento.
2. **Domínios** na conta:
   - `urace.us` e `lp.urace.us`: externo ou registrado na Hostinger; **nameservers atuais**; onde o DNS é gerido;
   - os **registros DNS** que a Hostinger mostrar (tipo, nome, destino). Registro que contenha token/verificação: anote só o tipo e o nome.
3. **Sites** da conta: quais, qual está em cada domínio, **tipo** (WordPress, construtor da Hostinger, outro).
4. **Servidor**: versão do PHP, limites (memória, tempo), LiteSpeed Cache ligado?, CDN da Hostinger ligada?, SSL (emissor e validade).
5. **Backups**: automáticos?, frequência, quantos existem, data do mais recente. **Não restaure.**
6. **E-mails**: há caixas de e-mail na Hostinger para urace.us? Quantas e quais endereços (sem senha). O MX aponta para a Hostinger ou para o Google?
7. **Banco de dados**: nome do banco, versão do MySQL/MariaDB, tamanho. **Não abra o phpMyAdmin.**
8. **Acesso**: SSH habilitado?, contas FTP (quantas, sem senha), **quem mais tem acesso à conta** (colaboradores).
9. **Cron jobs** configurados (o comando e a frequência; esconda token no comando).
10. Qualquer **aviso** do painel (vencimento, segurança, malware, recurso no limite).

### 2. WordPress do urace.us (wp-admin)
1. **Versão** do WordPress, **tema** ativo (nome, versão, se é filho) e temas inativos.
2. **Plugins**: a lista completa, com nome, versão, **ativo ou não** e se há atualização pendente. Dê atenção a:
   - `sxs-lp-for-urace`: o que diz a descrição, quem é o autor e quais telas ou configurações ele tem. **Só abra para ler.**
   - WooCommerce: versão, moeda, **meios de pagamento ativos** (nomes, sem chave), frete, impostos;
   - Elementor/Elementor Pro: licença ativa (sim/não);
   - Yoast, GTM4WP, GTranslate, SliceWP, Jetpack, All-in-One WP Migration, Contact Form 7, Facebook for WooCommerce.
3. **WooCommerce › Produtos**: quantos são, e o **status** destes:
   - Arrive and Drive (`go-kart-driving-experience`);
   - Kart School (`urace-kart-school`);
   - Intensive Training Camp (`urace-intensive-training-camp`);
   - Corporate Events (`corporate-karting-events`);
   - Professional Coaching (`professional-coaching`).

   Estão na lixeira, em rascunho, com outro endereço (slug)? Os botões de reservar do site levam a 404 em 4 deles.
4. **Como o Arrive and Drive monta o formulário** de pilotos/categoria/dias/adicionais: qual plugin, onde se configuram as categorias e os preços dos adicionais. Só leitura.
5. **Pedidos**: **quantos** existem no total e nos últimos 90 dias, e quais status aparecem. Não abra nenhum pedido e não copie nome de cliente.
6. **Clientes / usuários**: **quantas** contas de cliente (papel "customer") existem, e quantos usuários com papel de administrador ou editor (só os nomes de usuário da equipe).
7. **Formulários**: Contact Form 7 (quais formulários e para qual e-mail vão) e o formulário do Kommo (onde está inserido).
8. **Configurações › Geral e Links permanentes**: endereço do site, e-mail do administrador, fuso horário, estrutura dos links.
9. **Integrações**: Google Tag Manager (ID do contêiner), Meta/Facebook (pixel ligado?), Kommo (onde o código está: tema, plugin ou Elementor).
10. **Saúde do site** (Ferramentas › Saúde do site): os avisos críticos e recomendados.
11. **Onde fica o endereço da empresa**. O site mostra três diferentes: 10724 Cosmonaut Blvd; "Cosmonaut Blvd, Box 5"; 6149 Cyril Ave. Diga em qual tela ou widget está cada um.

## Como entregar

Responda num relatório em Markdown, com estas seções nesta ordem:
- `## Hostinger`
- `## WordPress`
- `## Produtos de reserva`
- `## Plugins` (uma tabela)
- `## Avisos e riscos`
- `## Perguntas para o dono`

Em cada item, diga **onde viu** (menu › tela). O que não conseguiu ver, escreva
"não encontrado" e por quê. No fim, confirme em uma linha: **"Nada foi alterado."**
