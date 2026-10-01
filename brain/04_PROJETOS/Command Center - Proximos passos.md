---
tipo: projeto
tipo_info: CONTEXT
status: ativo
owner: Italo Silveira
data: 2026-09-21
fonte: dono, 21/09/2026 (lista dos próximos módulos)
responsavel: Italo Silveira
---

# Command Center — Próximos passos

[[URACE]] · [[Administrative AI]] · [[Projetos]]

Lista viva. O dono pediu em 21/09: *"deixe sempre os próximos passos como checkboxes
para conseguirmos ter um bom track do que precisa ser feito"*. Quem marca o que está
feito é o trabalho entregue, não a intenção.

**Legenda:** 🔒 travado esperando alguma coisa · 👤 depende do dono · 🤖 posso tocar sozinho

## A ordem importa

Os seis módulos não são independentes. **Estoque é a espinha**: o PDV não existe sem ele,
e tanto pedido interno quanto envio são movimentos que entram e saem dele. Construir PDV
antes de estoque é construir caixa sem saber o que tem na prateleira.

    Estoque ──┬── Pedidos internos (entra no estoque)
              ├── Envios (sai do estoque / vai para o cliente)
              └── PDV (vende o que está no estoque, fatura no QuickBooks)

Chat interno e Checklists não dependem de nada disso e podem andar em paralelo.

---

## 1. Chat interno da equipe

Hoje a equipe se fala por WhatsApp e Google Chat. O objetivo é unificar dentro do
Command Center.

- [x] 👤 **Decidido em 21/09: ponte**, unindo WhatsApp e Google Chat — não substituição
- [x] 👤 Quem usa o quê: **WhatsApp** mecânicos, coach, designers, fornecedor de suit ·
      **Google Chat** staff adm, financeiro e comercial
- [x] 🤖 APIs levantadas em 21/09 (ver [[D-2026-09-21 - Chat interno e a ponte com WhatsApp e Google Chat]]):
      Google Chat espelha inteiro, sem pedágio; WhatsApp cobra três pedágios — janela de
      24 h com template pago fora dela, grupo de API com **no máximo 8 pessoas** e que não
      conecta em grupo já existente, e número que não pode estar no app WhatsApp Business
- [x] Desenhar o modelo: canal ligado a corrida, serviço, cliente ou livre; mensagem já
      nasce com `origem` e `external_id` para a ponte não precisar migrar conversa depois
- [x] 🤖 **Base construída** (21/09): tabelas, API e testes do chat interno
- [x] 🤖 Tela do chat interno no painel (lista + conversa, pensada para celular)
- [x] 🤖 **Chat de gente** (dono, 21/09): conversa direta em um clique pela lista de
      pessoas, grupo com nome/ícone/foto/participantes, e silenciar por pessoa — vale para
      conversa individual e para grupo
- [x] 🤖 **Notificação push (PWA)** — construída em 21/09: chave VAPID própria, assinatura
      por pessoa e por aparelho, aviso sem o texto da conversa, aparelho morto limpo sozinho
- [x] 🤖 Instalação na tela inicial (manifest, ícone, instrução própria para iPhone)
- [ ] 👤 Ligar a notificação no seu celular e mandar o teste (Equipe → "Ligar notificação")
- [x] 👤 **App nativo: não por ora.** PWA instalado na tela inicial; Capacitor só se
      aparecer maquininha, código de barras pesado ou offline longo
- [ ] 👤 Admin do Google Workspace liberar o app do Chat na organização — **é o único
      bloqueio que sobrou** nesta frente
- [ ] 🤖 Ponte do Google Chat (depois do admin liberar)

- [x] 🤖 **WhatsApp da equipe — reaberto pelo dono em 30/09** (*"quero que o Command Center
      envie mensagem como se fosse uma pessoa para o time interno"*). Backend pronto, em
      **simulação** até ter o número: cada pessoa da equipe (mecânico, coach, administrativo)
      é um contato com uma conversa no chat da equipe; o que se escreve ali sai no WhatsApp
      dela assinado com o primeiro nome ("*Italo:* …"), e a resposta volta para a mesma
      conversa (webhook assinado pela Meta). Sem aprovação, só para quem o gerente cadastrou;
      número desconhecido não vira conversa. Janela de 24 h respeitada: fora dela, só com
      template aprovado (`WA_TEMPLATE`) — senão a mensagem fica marcada "fora da janela".
- [ ] 👤 **Número próprio para a equipe** (não pode ser o 2291 do Kommo) + app na Meta,
      token, `~/.urace/whatsapp.env` e o webhook `…/ops/api/whatsapp/webhook`.
- [ ] 🤖 Tela: contatos da equipe no WhatsApp e status de cada mensagem no chat.
      **Em standby por decisão do dono (30/09).**
- [ ] 👤 **Número 2291 (clientes, Kommo)**: está na API oficial (canal `waba` do Kommo), por
      isso não abre no celular. O caminho para ter os dois é a **coexistência** da Meta
      (app WhatsApp Business + API no mesmo número) — depende do Kommo suportar e de alguém
      receber o código de verificação no próprio 2291. Ver conversa de 30/09.

**WhatsApp: parado por decisão do dono em 21/09** — *"não vamos usar o wpp por enquanto"*.
Os limites já estão medidos em [[D-2026-09-21 - Chat interno e a ponte com WhatsApp e Google Chat]];
quando voltar, ninguém precisa redescobrir. O WhatsApp de cliente segue pelo Kommo, como
hoje. O da equipe continua onde está, sem ponte.

## 2. Checklists de serviço e corrida

O que mecânicos e staff preenchem hoje no Google Forms.

- [ ] 🔒👤 **Receber os formulários atuais do Google Forms** — travado nisto. Sem ver o
      que eles já preenchem, eu inventaria checklist, e checklist inventado ninguém usa.
- [ ] 🤖 Ler os Forms e as respostas (o painel já tem acesso ao Google Drive)
- [ ] Mapear: quais são por serviço, quais por corrida, o que é obrigatório, quem preenche
- [ ] Modelo de checklist (template) + preenchimento (resposta), ligado a serviço/corrida
- [ ] Tela de preencher pensada para celular e para mão suja: poucos toques, offline se der
- [ ] Foto anexada no item (pneu, dano, peça trocada)
- [ ] O que fazer com checklist incompleto: vira item em "Precisa de atenção"

## 3. Tracking de pedidos internos (peças, ferramentas, pneus)

O que a URACE compra para si.

- [x] 🤖 **Construído em 30/09** (dono: *"siga com a tela de pedidos e compras"*), no
      desenho mínimo — ajustável quando o fluxo real for contado:
      **Pedido** (qualquer um da equipe, pelo celular): peça do estoque ou "outra coisa",
      quantidade, para quando, urgente, para o kart de quem → aberto → comprando → chegou →
      entregue. **Compra** (gerente): fornecedor (Comet por padrão), itens com custo, junta
      pedidos e o que está abaixo do mínimo → rascunho → pedida → parcial/recebida.
      **Receber** (quem abre a caixa): o que chegou **entra no estoque sozinho**, atualiza o
      custo da peça (e o preço final, se ela tem margem), e o pedido vira "chegou". Chegou
      mais do que foi pedido: recusado. Compra com algo recebido não cancela; cancelada,
      os pedidos voltam para a fila. "Precisa de atenção": pedido urgente parado e compra
      com previsão vencida. Custo só aparece para gerente.
- [ ] 👤 Como o pedido nasce hoje? (alguém pede no WhatsApp? Eduardo compra? tem
      aprovação?) — o fluxo real, para ajustar o que foi construído
- [ ] Nota fiscal / recibo anexado e ligado ao QuickBooks (despesa) — depende da
      fronteira com o QuickBooks
- [x] Aviso de pedido que não chegou no prazo (compra com previsão vencida)
- [x] 🤖 **E-mail de compra vira compra (30/09).** Dono: *"todo email relacionado a compra
      que chegar no urace@ se torne um item de compra, e toda atualização de envio /
      pagamento / entregue atualize; se tiver só a atualização do envio, crie também"*.
      A cada sincronia (15 min) o painel busca no urace@ (a caixa inteira — os filtros
      arquivam Finances/Shopping e Shipping Status), classifica cada mensagem em pedido ·
      pagamento · envio · entregue · cancelado · reembolso, tira nº do pedido, rastreio,
      transportadora, total e previsão, e acha a compra pelo nº do pedido (ou referência
      digitada), depois pelo rastreio; não achou, cria (origem e-mail). Cada e-mail vira
      evento na linha do tempo da compra, com link para o Gmail. Só lê o Gmail.
      **Fora, de propósito:** venda da nossa loja, pagamento de invoice nossa (QuickBooks),
      assinatura/renovação e propaganda. **Entregue ≠ recebido:** "delivered" não dá
      entrada no estoque — vira "Precisa de atenção: foi entregue, falta dar entrada".
      Compra do e-mail vem **sem itens** (não inventa): o gerente põe os itens ou **liga os
      pedidos da equipe**. Liga sozinho só quando o SKU da peça pedida aparece no e-mail;
      nome parecido fica como sugestão. Pedido ligado mostra o envio e o rastreio. Compra
      que não é de estoque (passe de pista, serviço) fecha com "Concluir sem estoque".
- [x] Recibos do Orlando Kart Center (passe de pista) **não** viram compra — dono, 30/09: "não"
      (PR #27, issue #15).

## 4. Tracking de envios

Suits, peças da loja do eBay, peças específicas compradas para clientes.

- [ ] 👤 Quais transportadoras e quais lojas (eBay, outras?)
- [x] 🤖 Rastreio das COMPRAS (o que chega para nós) sai dos e-mails desde 30/09 — ver módulo 3.
      O que falta aqui é o envio que a URACE DESPACHA (suits, eBay, peça para cliente).
- [ ] Modelo: envio → itens → destinatário (cliente ou endereço) → rastreio → status
- [ ] Rastreio automático (código da transportadora), se a API permitir
- [ ] Ligar ao cliente: o envio aparece no card dele
- [ ] Sai do estoque quando despachado (liga com o módulo 5)
- [ ] Avisar o cliente do envio — e decidir se é automático ou com aprovação

## 5. Estoque — a espinha

Chassis, motores, pneus e peças. Inclui **peça que está com a URACE mas é do cliente**
(normalmente cliente Pro).

- [x] 👤 **Dois tipos, decidido em 22/09.** Chassi e motor: ficha individual com número de
      série. Pneu e peça de consumo: quantidade. São dois comportamentos no mesmo módulo —
      misturar num modelo só é o erro clássico que trava o sistema depois.
- [x] 👤 **Dois locais, decidido em 22/09:** sede e trailer de corrida.
- [x] 👤 **A base das peças é o catálogo da Comet Kart Sales** (dono, 22/09), e o **SKU é
      referência de compra** para o módulo de compras futuro — não é a identidade do item.
      Peça avulsa e usado existem sem SKU.
- [x] 🤖 Modelo: item → tipo → quantidade ou série → local → **dono** (URACE ou cliente)
- [x] 🤖 Peça de cliente: nunca vendável para outro (trava em `estoque.py`), e
      `do_cliente()` devolve o que é dele para o card
- [x] 🤖 Movimentos: entrada, saída, ajuste, transferência (sede ↔ trailer) e contagem —
      todos no razão `stock_moves`, com saldo antes e depois
- [x] 🤖 Contagem física, com quem contou e quando; `conferir()` refaz o saldo pelo razão
      e **acusa divergência sem consertar sozinho**
- [x] 🤖 Estoque mínimo por item → `abaixo_do_minimo()` já devolve SKU e link do fornecedor
- [x] 🤖 Ligar o mínimo em "Precisa de atenção" e abrir a API/tela do módulo (28/09).
      Em "Precisa de atenção" são **dois itens separados**: *"N peças nunca foram contadas"*
      (leva direto para a contagem) e *"Repor …"*, que só lista peça **já contada** abaixo
      do mínimo. Ficha nunca contada fica fora da reposição — mandar comprar o que talvez
      esteja na prateleira é o alarme falso que faz a equipe parar de ler o painel.
- [x] 🤖 **Tela do estoque, fase 2 (28/09):** botão **"Contar prateleira"** (sede ou
      trailer; filtro "só as nunca contadas"; em branco fica como está; grava **tudo ou
      nada** — uma linha ruim e nenhuma é gravada, e a tela diz qual). Clicar numa peça
      abre a ficha: histórico de movimentos, **Movimentar** (uso em serviço, compra,
      sede ↔ trailer) e **Catálogo da Comet** (sugestões de SKU pelo nome; número da peça
      pesa o dobro). Mecânico vê as sugestões; **só gerente liga o SKU**, e só SKU que
      existe no catálogo — casar errado é comprar a peça errada. O nome da casa não muda.
- [x] 🤖 O conector do claude.ai (`urace_estoque`, `urace_resumo`) agora diz quais peças
      **nunca foram contadas** e avisa que o zero delas não é falta.
- [x] 👤 **Estoque em prateleiras, decidido em 29/09.** *"Contar prateleira"* virou
      **"Adicionar peça"**. A tela é uma **fileira horizontal de cards por prateleira**:
      Pneus · Motores · Peças de motor · Chassis · Hardware e chassi · Combustível e óleo ·
      Telemetria e eletrônica · Outros · **Vestuário (Alpha Line) por último**. Dentro de
      cada fileira, filtro por marca/tipo; cada peça tem marca e medida (pneu 4.60-5, 7.10-5…
      — vocabulário tirado da apostila de kartismo da equipe, como sugestão, não trava).
- [x] 🤖 Peça antiga sem prateleira aparece na **sugerida pelo nome** (só na tela; o banco
      não é reescrito por palpite). Ao editar e salvar, a escolha passa a ser de gente.
- [x] 🤖 **Assinalar para cliente** — pelo card da peça (aba Cliente) ou pelo card do
      cliente (aba **Peças guardadas**). A peça fica na prateleira e passa a ser dele; de um
      cliente para outro não vai. Também dá para cadastrar já como "de um cliente".
- [x] 🤖 **Preço**: valor de compra + margem em campo livre (**"15%"** é porcentagem,
      **"20"** é valor fixo, "15% + 10" soma) = preço final; ou o preço final digitado
      direto. Esse preço entra no contexto do AI Command como o valor da invoice da peça, e
      a linha com esse valor não é marcada para conferir.
- [x] 👤 **Ajustes do dono (29/09, segunda rodada):** "De quem é" (URACE ou cliente) já no
      registro — quanto tem agora, chegou, usei, levar; locais **Galpão · Trailer de
      corrida · Pista (OKC)**; "Adicionar imagem"; margem com **chave % / $**; última
      fileira se chama **Alpha Line**, com Boné, Camisa, Moletom e Macacão URACE (standard)
      criados sem quantidade e sem preço (`adminai/semear_alpha_line.py`); fileira sem
      barra de rolagem — no computador, clicar, segurar e arrastar.
- [x] 🤖 **Peça usada → cobrança do cliente (30/09).** Em "Usei em serviço", o mecânico diz
      em qual kart (cliente) a peça foi usada. Peça DA URACE vira **cobrança pendente** dele,
      com o preço final congelado naquele momento (peça que já era do cliente não se cobra).
      A lista aparece no card do cliente (aba **Peças**) e em "Precisa de atenção"; a IA
      recebe as peças a cobrar quando monta a invoice dele (comando e dia 1). Quando a invoice
      chega do QuickBooks com a peça — mesmo nome e mesmo preço —, a cobrança sai sozinha. O
      gerente resolve o resto: pôr preço em peça que estava sem, "cobrada" (foi por fora) ou
      "não cobrar" (garantia, cortesia).
- [ ] 🤖 Painel todo em inglês: mais para frente (dono, 29/09). Por ora, português.
- [ ] 👤 **Confirmar três escolhas minhas** (fáceis de mudar): (1) mecânico = papel
      Operador — um papel "Mecânico" que só vê o estoque exige mexer na tabela de usuários
      do banco, e isso eu só faço com sua autorização; (2) custo e margem só o gerente vê,
      o mecânico vê o preço final; (3) devolver peça do cliente para a URACE é do gerente.
- [ ] 👤 Mandar os arquivos que a equipe usava para diferenciar as peças (a apostila já
      entrou). Com eles, as marcas/tipos de cada prateleira ficam mais completos.
- [ ] 🤖 SKU da Comet: fica para depois (dono, 29/09). A aba existe só para gerente.
- [x] 🤖 **Importador do catálogo da Comet construído** (`adminai/importar_comet.py`).
      Tenta o JSON da loja → sitemap + JSON-LD → e só então HTML. Obedece `robots.txt`,
      se identifica, pausa entre páginas, respeita `Retry-After` e guarda em disco o que
      já buscou. `supplier_products` é espelho do catálogo deles — separado do nosso
      estoque, porque eles vendem milhares de peças e nós carregamos uma fração.
- [x] 🤖 **Catálogo da Comet carregado na VPS (22/09): 12.315 SKU, varredura COMPLETA**
      em 32 páginas do `/products.json`. A paginação corrigida foi o que destravou — a
      prova de 50 tinha trazido 479 e parecia ser tudo.
- [x] 👤 **"Quais peças a URACE carrega?" — respondido pelas invoices** (dono, 23/09:
      *"leia todas as invoices criadas desde o início do ano"*). 348 invoices do
      QuickBooks, linha a linha, 02/01 a 22/09: **161 itens físicos distintos, 32 em 3+
      vendas, 16 em 5+**. Em `dados/pecas-mais-usadas-2026.json`.
- [x] 🤖 O relatório pronto do QuickBooks teria mentido: põe **Travel Fee no topo com
      684** (milhas a $0,85) e joga fora o prefixo que separa peça de serviço. Ler
      invoice por invoice foi a decisão certa do dono.
- [x] 👤 **Os 16 itens criados na VPS em 23/09** — fichas sem saldo, como tem de ser.
- [x] 🤖 **Contagem física existe como comando** (`adminai/contar_estoque.py`): imprime a
      folha com os `#id` e recebe `--contar 3=12 5=0`. Item não contado **fica como
      está**, nunca vira zero; contar zero é registro válido e diferente de não contar.
- [ ] 👤 **Contar a prateleira** (Estoque → *Contar prateleira*, ou o item de "Precisa de
      atenção") — é o que tira o estoque do zero. Depois da contagem a
      lista de reposição passa a valer de verdade. (25/09: pelo conector, os 16 estão
      com total 0 e nenhum é peça de cliente — o "16 abaixo do mínimo" é estoque nunca
      contado, não falta confirmada.)
- [ ] 👤 (conferido) A lista dos 16:
      `Rear sprocket` (31 vendas), `Rk Non Oring Chain` (29), `Fuel charge Jr/Senior`
      (27), `Spark Plug` (18), `Tonykart brake pads` (17), `MG SH2 Red Tires` (16),
      `Tie rod` (15), `Levanto KRT Tires` (13), `Evinco Tires` (12), `Fuel mix` (10),
      `Tonykart Steering column` (10), `Tonykart Rear bumper fixing bolt` (7),
      `Number Sticker` (6), `MG SW2 Rain Tire` (6), `RK Oring Chain` (6),
      `IAME Front Sprocket Z10` (5).
- [ ] 👤 **Os mínimos são chute honesto**: um mês de consumo medido nessas invoices.
      Faltam três coisas que os números não mostram e você sabe — prazo de entrega da
      Comet, peça que quebra em lote, e corrida grande no calendário.
- [ ] 👤 **Ficaram de fora de propósito, discorde se quiser:** roupa sob medida (suit,
      camisa — feito por encomenda), tenda/parede/bandeira (estrutura de evento) e kart
      completo (é ficha com número de série, não quantidade).
- [ ] 👤 (resolvido em parte) **Importação: caminho escolhido foi a raspagem.** Esta sessão não alcança o site (a
      política de saída recusa `cometkartsales.com`, 403 — não contornei). Duas saídas:
      rodar na VPS, que tem rede própria (`python3 adminai/importar_comet.py --limite 50`
      primeiro), **ou** pedir o export do catálogo ao fornecedor e rodar com
      `--arquivo catalogo.csv`. O export é o caminho melhor: é o dado na fonte, não
      incomoda o site e não quebra quando mudam o layout.
- [ ] 👤 **Decidir a fronteira com o QuickBooks.** Proposta: o painel manda no estoque
      físico, o QuickBooks manda no financeiro. Controlar quantidade nos dois lados gera
      divergência garantida, e aí ninguém acredita em nenhum dos dois.
- [ ] 🤖 Construir o módulo (agora destravado pelas duas decisões acima)

## 6. PDV no celular, integrado

Mecânico vende peça direto ao cliente pelo celular, com ou sem ajuda da IA.

- [ ] 🔒 **Depende do módulo 5** (estoque) — sem saber o que tem, não há o que vender
- [x] 👤 **Como o cliente paga: QuickBooks**, sempre (dono, 21/09). Link ou QR aberto no
      celular do próprio cliente — sem maquininha, sem hardware no box. Isso também
      decidiu o app: PWA basta, ver [[D-2026-09-21 - Celular e PWA, sem app nativo]]
- [ ] Tela de venda pensada para celular: acha o cliente, acha a peça, quantidade, pronto
- [ ] Preço vem da **Rate Card** (regra do dono, 18/09) — e peça mantém o preço
- [ ] Baixa no estoque na hora da venda
- [ ] Vira invoice ou recibo no QuickBooks, ligado ao cliente certo
- [ ] Papel de quem pode vender (mecânico = OPERATOR) e o que ele **não** pode (dar
      desconto? vender fiado?) 👤
- [ ] Venda offline (sem sinal no box) e sincroniza depois — decidir se entra agora
- [ ] Ajuda da IA: achar a peça pela descrição do mecânico ("pastilha do kart do Pedro")

---

## Decisões do portão — fechadas em 22/09

Ver [[D-2026-09-22 - Lembrete de waiver, arquivar no Gmail e o guarda-chuva do apagar]].

- [x] 👤 As 8 decisões pendentes respondidas na página editável
- [x] 🤖 `apagar_qualquer_coisa` → `REQUIRES_APPROVAL`, e voltou a ser **piso** de todo
      apagar: ação nova com apagar/excluir/deletar/remover no nome não passa mais por baixo
- [x] 🤖 `gmail_rotular` → `SAFE`, com a trava: arquivar só com marcador **confirmado** no
      painel. Sem banco, volta à regra estreita de antes (só `wNews`)
- [x] 🤖 `docusign_send_reminder` → `SAFE`, com a trava: só cliente com serviço marcado,
      3 dias antes e 1 dia antes, **no máximo 2 por envelope**
- [x] 🤖 23 testes das três travas (`test_travas_decididas.py`)

## De quem é cada serviço (22/09) — o card do David Pera

Ver [[D-2026-09-22 - O titulo da tarefa diz de quem e o servico]].

- [x] 🤖 Extrator do nome no título reescrito com o gabarito do dono: de 27/70 para 70/70
- [x] 🤖 Primeiro nome sozinho, inicial abreviada e categoria colada passaram a ser lidos
- [x] 🤖 Camadas para achar o card certo; ambíguo volta para humano, nunca é chutado
- [x] 🤖 Varredura e conserto do quadro inteiro (`/service-attribution` e
      `adminai/atribuir_servicos.py`), auditado
- [x] 👤 Varredura rodada na VPS 4 vezes, lista olhada, **distribuição aplicada** (189 movidos)
- [x] 👤 Regra dada: *"nunca colocar serviço de outro cliente em card de outro cliente"* — na
      dúvida, card próprio com o nome do título (`Mike`, `Sean`, `G.J`)
- [x] 👤 Princípio dado: *"para cruzar e confirmar, use o nome do responsável e informações de
      contato"* — virou `mesmo_contato` e `por_contato`
- [x] 👤 Cards unidos pelo dono: Liam Bourghol (4→1), Charlie Marron (4→1), Alexander Savage
      (4→1, Kenneth fica como responsável), Alex Alonzo, Hank Lai, Reinaldo Arroyo; #238 é Alex Donnell
- [x] 🤖 "Pode só separar": card que é corrida/tarefa não é apagado — `kind='separado'`, fora
      da lista (filtro "Separados" na tela de clientes)
- [x] 🤖 Princípio na fonte: a sincronia guarda responsável/e-mail/telefone da descrição na
      tarefa; a atribuição decide por **contato antes do título**; `--ler-descricoes` busca no
      Asana o que ficou em dúvida
- [x] 🤖 `[Canceled] Erik Mendoza Jr_…` → Erik Mendoza (tag na frente sai; Jr é marca de criança)
- [x] 🤖 **Fechado em 22/09: a varredura convergiu** (segunda rodada seguida: 0 movidos,
      0 cards novos, 0 para unir). De 508 para **956 serviços no card certo**; David Pera
      com os 3 dele; "sem nome no título" de 266 para 228 (corridas e tarefas internas).
- [x] 🤖 Revisão adversarial (6 lentes, 3 céticos por achado): 12 defeitos confirmados,
      5 críticos, todos corrigidos — ver a decisão
- [ ] 👤 `Charles Andrew Marron` e `Charlie Marron` parecem a mesma criança — unir?
- [ ] 👤 Olhar os baldes que sobraram (`Isabel`, `Calix`, `Enzo`, `Mia`, `Baturalp`,
      `Enrico BR`) e unir os que você reconhecer
- [ ] 🤖 `limpar_nao_clientes` na VPS (separa `Battle for Orlando` e afins) — roda na próxima sincronia completa
- [x] 🤖 **Soltar uma linha por vez** (`--soltar ID`): a extensão da VPS recusou tirar a
      corrida `Lucas Oil … | Sebring` do card `#15 Alexander Savage` porque a flag levaria
      junto `Inventário Hank Lai_ caixa`. Ela estava certa. Recusa id que não está na lista
      e respeita o carimbo; sem `--aplicar` não escreve.
- [x] 👤 **`Inventário Hank Lai_ caixa`: "tarefa interna"** (dono, 22/09). Sai do card junto
      com a corrida, e a regra que lê `Inventário <nome>` como tarefa de galpão fica como
      está — travada em teste, com a resposta dele escrita lá.
- [x] 👤 **Waiver `#31` Pablo Santiago: "desconsiderar por hora"** (dono, 22/09). Fica no
      relatório, não vira tarefa.
- [x] 🤖 **`urace-waivers` morto às 07:33: encerrado sem causa.** As unidades agora carimbam
      o código de saída; a próxima falha se explica sozinha. Não vale caçar log que não existe.

## Conector MCP (23/09) — o painel como ferramenta de um Claude de fora

- [x] 🤖 **`POST /ops/mcp`**: MCP por HTTP com nove ferramentas de leitura. O servidor
      MCP já existia desde 21/09, em stdio; faltava só o transporte.
- [x] 🤖 **"Só leitura" deixou de ser promessa.** A rota abre o banco em `mode=ro` — o
      SQLite recusa escrita por ela. Foi o que permitiu isentar o MCP da trava por método
      HTTP (JSON-RPC manda leitura por POST) sem abrir buraco.
- [x] 🤖 Vai atrás do mesmo `handle /ops*` do Caddy: nada novo no servidor web.
- [ ] 👤 **Criar a chave** (Usuários → Chaves de API, papel VIEWER, só leitura) e
      **conectar** em claude.ai/customize/connectors, depois abrir sessão nova.
- [x] 🤖 **A incerteza se resolveu do jeito difícil (24/09): exigia OAuth.** O conector
      recusou chave fixa e falhou em "registrar no serviço de login". O painel virou
      servidor OAuth — descoberta na raiz, registro dinâmico, consentimento humano,
      PKCE, código de uso único que revoga tudo se reusado. No ar, 761 testes.
- [x] 🤖 O caminho até lá teve três defeitos de diagnóstico que custaram tempo, e cada
      um virou trava: o serviço antigo servia HTML com 200 em `/ops/mcp` (agora 404), o
      POST caía na regra só-GET do painel (405), e uma asserção de data escrita à mão
      quebrou sozinha no dia seguinte.
- [x] 👤 **Conector confirmado (25/09)**: login pelo claude.ai completo e `urace_resumo`
      com os números reais (257 clientes, 1.186 serviços, 43 invoices abertas). Faltava a
      tela de login voltar ao `next` da autorização — o cookie `SameSite=Strict` não
      acompanha a chegada vinda do claude.ai. Corrigido em `6a65332`, provado num
      Chromium de verdade. O Kommo entrou no conector (`urace_kommo_*`, só leitura,
      `3821fdd`); `urace_kommo_conta` respondeu Support Urace, 7 funis.
- [ ] 👤 **Revogar a chave `urk_a4cb58019a_…`**, que apareceu inteira num print em 24/09.
      Só leitura, mas da base inteira. Usuários → Chaves de API → revogar.
- [ ] 👤 Liberar `urace-bridge.duckdns.org` na política de rede **só** se quiser que eu
      alcance a VPS direto daqui — o conector não precisa disso, porque roda pelo
      claude.ai.

## Banco: estrutura e segurança (23/09) — o dono pediu a garantia

Ele perguntou antes de olhar a tela, e a pergunta achou um buraco.

- [x] 🤖 **Auditoria que roda e responde** (`adminai/auditar_banco.py`, só leitura):
      integridade do arquivo, órfãos entre tabelas, durabilidade, permissões, backup,
      gatilhos de auditoria, senha/chave só em hash, e quantos ADMIN existem. Fecha com
      o que há por área — clientes, financeiro, estoque, contratos, operação, segurança.
- [x] 🤖 **O buraco: não havia backup nenhum.** Tudo num arquivo só, numa máquina só.
      `adminai/backup_banco.py` faz cópia com `VACUUM INTO` (consistente, não `cp`),
      **abre e confere cada cópia** antes de contar, comprime, guarda 14 dias e só apaga
      o velho depois de o novo existir. `--restaurar` guarda o banco atual antes.
- [x] 🤖 Timer `urace-backup` às 03:15, com `Persistent=true` — backup que só acontece
      com a máquina de pé não protege de queda.
- [x] 🤖 Conferido e **está bem**: scrypt com sal por usuário, chave de API só em hash,
      `audit_logs` append-only por gatilho, arquivo 600 e pasta 700, `journal=wal` com
      `synchronous=FULL`, nenhum segredo no repositório.
- [x] 👤 **Auditoria rodada na VPS (23/09): tudo verde.** 20,2 MB, sem corrupção, **sem
      um único órfão** entre 3.831 vínculos externos. 272 clientes · 510 invoices · 1.184
      serviços · 132 corridas · 108 waivers · 12.315 SKUs · 3.865 registros de auditoria.
      Primeiro backup feito (2,5 MB comprimidos) e timer diário ativo.
- [x] 👤 **Backup fora da VPS: o Drive** (dono, 23/09, *"pasta no drive com o nome Backup
      urace command center com o backup semanal"*). `adminai/backup_drive.py`, toda
      segunda às 04:00. Escopo `drive.file` — o app só enxerga o que ele mesmo criou, e
      não lê o resto do Drive.
- [ ] 👤 **Reautorizar o Google na VPS** — é o único passo travado: o token atual é
      `drive.readonly` e não escreve. `python3 adminai/google_auth.py --conta urace`.
- [ ] 👤 **Não compartilhar a pasta do Drive.** Dentro dela está a base inteira: nome,
      e-mail, telefone e valor de cada cliente. Um link "qualquer pessoa com o link" ali
      é o vazamento de tudo de uma vez.
- [ ] 👤 Segundo ADMIN no painel: hoje há um só. Perder esse acesso é ficar sem
      administração.
- [ ] 🤖 19 sessões vencidas sem limpeza — sujeira, não risco. Posso pôr a faxina no
      mesmo trabalho noturno do backup.

## Bancada de testes (22/09) — o instável era um teste fraco

- [x] 🤖 **Caçado em 30 rodadas: `test_criar_e_revogar_ficam_na_auditoria`.** A causa não
      era ordem nem tempo: `chave.split("_")[2]` supunha que o segredo não tem underscore,
      mas `secrets.token_urlsafe` usa o alfabeto `A-Za-z0-9-_`. **47,4%** das chaves reais
      têm underscore no segredo — nessas, a asserção "o segredo não vazou" conferia só um
      **fragmento**, e quase não provava nada. Em 5,1% o fragmento saía com 1–2 letras
      ("e" está em qualquer JSON) e o teste falhava sozinho.
- [x] 🤖 `split("_", 2)` nas duas ocorrências: o teste ficou **estável e mais forte** ao
      mesmo tempo. O instável era o sintoma; o buraco era a asserção fraca.

## Segunda rodada da extensão (22/09) — a waiver destravou

- [x] ✅ **Waiver da Nadine: `completed`, assinada 17/09 20:21.** A paginação era a causa.
      113 envelopes, 69 ligados a cliente, em 17s.
- [x] 🤖 **As ferramentas rodavam no `python3` do sistema**, que não tem as dependências.
      A extensão achou o venv (`~/.urace/cc-venv`) e repetiu sozinha — mas quem usa não
      deveria precisar saber. `adminai/_venv.py` re-executa no Python certo.
- [x] 🤖 **Eu esqueci uma unidade.** O comando que passei copiava 3 e deixava a 4ª, e o
      aviso de specifier continuou no `urace-brain-health`. Agora
      `adminai/deploy/instalar_unidades.sh` varre todas, com teste que proíbe lista fixa.
- [ ] 👤 Ainda há **6 waivers em sent/delivered** — conferir se são mesmo não assinadas
- [ ] 🔒👤 **O push da VPS segue bloqueado (403).** O relatório continua preso na máquina.

## Primeira rodada da extensão na VPS (22/09) — o que ela achou

A extensão rodou a rodada completa e reportou honestamente, inclusive a própria falha.

- [x] 🤖 **Sem comando de linha para as sincronias.** Ela precisou rodar a do DocuSign e
      só achou o botão do painel, que exige login. Não improvisou — reportou. Agora existe
      `python3 adminai/sincronizar.py docusign` (e `--listar` mostra todas).
- [x] 🤖 **`%20` no `Documentation=` das unidades systemd.** `%` abre especificador no
      systemd, então `%20` vira "Unknown specifier" a cada recarga. Escapado nas 4 unidades.
- [x] 🤖 **Serviço de waivers morreu 07:33, código 1, sem mensagem.** A causa não dá para
      saber sem rastro — então agora as três unidades de agente carimbam
      `resultado` e `código de saída` no próprio log ao morrer. A próxima falha se explica.
- [ ] 🔒👤 **A ponte está furada: o token da VPS só LÊ o repositório.** O push foi recusado
      4× com 403 (`Permission to UraceUs/Uraceagent.git denied to UraceUs`). Enquanto não
      houver permissão de escrita, nada que a extensão escrever chega ao Claude por esse
      caminho. O relatório `0ecc3cf` está commitado só na máquina.
- [x] 👤 **Savage: sim**, os 18 "Savage" e 2 "Savege" do #15 são do Alexander.
- [x] 👤 **Alex: sim**, o solitário do #238 é do Alex Donnell.
- [x] 👤 **Unir: sim**, os cinco pares.
- [x] 🤖 As duas confirmações viraram **carimbo** (`tasks.client_by='human'`): a varredura
      nunca mais mexe neles. "Está certo hoje" não durava — bastava um homônimo novo no
      cadastro para o nome virar ambíguo e o serviço sair de lá.
- [ ] 👤 Rodar o bloco que carimba (#15 e #238) e une os cinco pares

## Para logo depois da organização dos cards (dono, 22/09)

- [x] 🤖 **RESOLVIDO em 22/09: era paginação.** `docusign_envelopes` pedia `count=100` e
      não paginava — só os 100 primeiros envelopes do ano voltavam, e o resto ficava
      congelado no status da última vez que coube na janela. Era o suspeito (a). Agora
      pagina até o fim e diz `completo: true/false`. `_envelopes_de` tinha o mesmo bug,
      o que também afetava a trava de "waiver válida" antes de enviar uma nova.
- [ ] 👤 Conferir no painel que a waiver da Nadine virou "assinada" depois da sincronia
- [ ] 🤖 (contexto original) **Waiver assinada aparecendo como "enviada, não assinada".** Envelope
      `1ceee462-2383-8726-825b-424ddf410785`, Parental Consent, assinado por Nadine Kozora
      Garcia (nkozora1@gmail.com) em 17/09/2026 16:21 — no DocuSign está **Completed**; o
      Command Center ainda mostra como enviada. Dono: *"é um erro, né?"* — é. Suspeitos, na
      ordem: (a) a sincronia de waivers só relê envelopes de uma janela/estado e este ficou
      de fora; (b) o espelho `waivers` guarda o status da primeira leitura e não atualiza
      `completed_at`; (c) o envelope está ligado a outro card e a tela do cliente lê o errado.
      Conferir os três antes de mexer; corrigir na sincronia, não à mão.
- [ ] 🤖 Depois de corrigir: varrer todos os envelopes `sent/delivered` do espelho contra o
      DocuSign — se um ficou para trás, outros ficaram

## Vem de antes (21/09, aprovado e ainda devendo)

- [ ] 🤖 Artifact editável do APLICAR=1: o que o agente escreveria sozinho × o que ainda
      precisa de aprovação
- [ ] 🤖 Asana P-01/02/03: os consertos seguros, como ações com política
- [ ] 🤖 Order Number P-08: extrair o código do pedido
- [ ] 👤 Responder Charles (#33988589) e True X Miami (#33998731) — sem resposta desde 19/09
- [ ] 👤 Anular o envelope duplicado da Letícia no DocuSign
- [ ] 👤 Decidir se o Austin precisa de waiver nova

## Preços já cobrados no AI Command (28/09)

O dono montou as invoices do Bryan, do Frankie e do Brody pelo AI Command e a IA travou
pedindo o valor de cada peça ("não consigo puxar o histórico de faturas"). O valor estava nas
invoices já enviadas; faltava o painel guardar as **linhas** delas.

- [x] 🤖 Sincronia do QuickBooks guarda cada linha de invoice (`invoice_lines`, com id do item).
- [x] 🤖 Todo comando que fala de invoice/preço leva a tabela **PREÇOS JÁ COBRADOS NO
      QUICKBOOKS** (último valor, quando e de quem, mais comum, faixa) das peças da conversa —
      inclusive as que estavam na pergunta anterior da IA — e o `cliente_id` de cada e-mail.
- [x] 🤖 Valor já cobrado do mesmo item deixa de sair marcado "confira na Rate Card".
- [x] 🤖 `qbo_historico_precos` no conector do QuickBooks (a IA consulta outra peça ao vivo)
      e `urace_precos_cobrados` no conector do claude.ai.
- [ ] 👤 Rodar o bloco de deploy + reinstalar o Admin AI (registra a consulta nova no agente).

## Card do cliente: mensalidade combinada e serviços (29/09)

Dono, no card do Enzo Kurian: o valor da mensalidade tem de ser editável ("às vezes um
deal diferente"), virar invoice recorrente no QuickBooks, e os serviços têm de poder ir para
o cliente certo e mudar de nome.

- [x] 🤖 **Mensalidade e contrato → "Valor da mensalidade e recorrência"** (só gerente):
      valor mensal deste cliente + item do QuickBooks. É o que vai na invoice do dia 1 — a IA
      recebe `monthly_amount` e ele manda sobre a Rate Card.
- [x] 🤖 **Invoice recorrente no QuickBooks**: 6 meses (padrão), 12 ou personalizado (1–36),
      todo dia 1, enviada sozinha. Com recorrência ativa, o dia 1 do painel **não** monta outra
      invoice do cliente (cobrar duas vezes, não). Cada pedido fica registrado — ativa,
      simulação ou falha, com a resposta do QuickBooks.
- [x] 👤 **Uma recorrência só (dono, 29/09):** ao abrir a aba, o painel lê as recorrências do
      cliente no QuickBooks. Se já houver uma ativa que o painel não conhece, aparece um aviso
      grande com **"Vincular ao Command Center"** e o botão de criar fica bloqueado (o
      servidor também recusa). Vincular liga a do QuickBooks ao card — o valor do card passa
      a ser o dela — e a tabela mostra se cada recorrência do painel existe mesmo lá
      ("vinculada ✓", "inativa lá", "não encontrada lá"). Sem conseguir ler o QuickBooks,
      criar fica bloqueado: sem conferir, não se cria cobrança.
- [ ] 👤 **Conferir a primeira recorrência no QuickBooks** (Sales → Recurring transactions):
      numeração da invoice gerada e o envio automático do e-mail. Não deu para testar contra o
      QuickBooks de verdade daqui; o formato segue a API da Intuit.
- [x] 🤖 **Serviços → Mover** (gerente): leva o serviço para o cliente certo e grava o carimbo
      "confirmado por gente" — a sincronia do Asana passou a respeitar esse carimbo (antes ela
      relia a tarefa aberta e decidia o cliente de novo pela descrição).
- [x] 🤖 **Serviços → Renomear** (operador): troca o nome **no Asana** e no painel; dá para
      marcar outros serviços para receberem o mesmo nome. Se o Asana não confirmar (modo
      simulação, tarefa protegida), o nome do painel não muda.
- [x] 🤖 O servidor stdio do QuickBooks registrava as ferramentas só até o meio do arquivo —
      o lembrete de invoice nunca existia por ali. Corrigido junto.

## Endereço da URACE para o painel (30/09)

Dono: *"conseguimos deixar a url do site como o da urace?"* / *"tenho esse urace.us que quero
colocar o command center lá dentro"* (o domínio está na Hostinger, com o site na raiz).

- [x] 🤖 `servir_command_center.sh` aceita `CC_DOMINIOS_EXTRAS="ops.urace.us"`: cria um
      site a mais no Caddy com o mesmo painel (raiz redireciona para /ops/), certificado
      automático. Só entra se o DNS do nome novo já aponta para este servidor.
      O duckdns continua: webhooks do Kommo, OAuth do QuickBooks e o conector do claude.ai
      apontam para ele — trocar esses é um segundo passo, um por um.
- [ ] 👤 **O DNS do urace.us não está na Hostinger**: em "Gerenciar DNS" ela mostra o domínio como
      externo ("conecte um domínio externo ou transfira"). O registro tem de ser criado onde o
      domínio foi comprado / para onde os nameservers apontam (consulta:
      https://lookup.icann.org/en/lookup?name=urace.us). Lá: **CNAME** `ops` →
      `urace-bridge.duckdns.org`, TTL 300, sem mexer na raiz e no www. Depois, o deploy com
      `CC_DOMINIOS_EXTRAS=ops.urace.us`. Issue #26.

## Padrão de engenharia (30/09) — issue #14, vale daqui em diante

Dono: *"preciso que faça também nos nossos projetos de agora pra frente"* (otimização de
interface, paginação no backend, sitemap, hierarquia de cabeçalho, meta, Core Web Vitals,
cache de API, slugs, canonical, imagens, schema, um h1, robots.txt, mobile, issues e PRs
ligados, motion, observabilidade, lint, testes unitários, de integração e end-to-end).
E: *"vc faz [o merge] e garante que tudo vá para a vps"*.

O padrão está escrito em `CLAUDE.md` (lido em toda sessão). Feito em 30/09, um PR por issue,
cada um com CI verde antes do merge:

| Issue | PR | O quê |
|---|---|---|
| #15 | #27 | recibo do Orlando Kart Center fora das compras |
| #16 | #28 | ruff + oxlint + CI (pytest, build, e2e com Playwright) + templates + CLAUDE.md |
| #17 | #29 | request id, log JSON por requisição, métricas por rota, erros e Web Vitals do navegador (Integrações › Saúde do painel) |
| #18 | #30 | um h1 por tela, sem pular nível, título da aba por tela |
| #19 | #31 | JS inicial 688 → 261 KB (código por tela), build com cache imutável, gzip |
| #20 | #32 | ETag/304 nos GET da API, paginação no backend (auditoria com busca no servidor) |
| #21 | #33 | foto vira WebP ≤ 1600 px sem EXIF; foto do login 363 → 142 KB; script para as antigas |
| #22 | #34 | nenhuma tela rola para o lado (360/390 px); alvo de toque de 40 px |
| #23 | #35 | tokens de motion; animação só em transform/opacity |
| #24 | #36 | /compras/12, /crm/chat/57, /equipe/3 (o endereço antigo redireciona) |
| #25 | #37 | robots.txt, sitemap.xml, canonical, meta e JSON-LD nas páginas legais |

- [ ] 👤 O **site urace.us** (Hostinger) não está no repositório: SEO, imagens e Web Vitals dele
      se fazem no construtor da Hostinger — dizer se quer que eu escreva o passo a passo.
- [ ] Comprimir as fotos já salvas no VPS: `~/.urace/cc-venv/bin/python adminai/comprimir_fotos.py`
      (mostra) e `--aplicar` (grava .webp ao lado, sem apagar a original).

## Site público + área do cliente + agenda (30/09) — issue #38

Dono: *"esse site continua sendo o site onde todos os clientes terão acesso, e o Command
Center vai ser como uma área escondida dele […] um calendário conectado ao site e ao Command
Center, onde o cliente marca a sessão dele […] uma área do cliente […] vincular o perfil do
cliente no site público com o perfil no site interno"*. **Nomes:** site interno = Command
Center; site público = urace.us. Tudo nasce e é testado no site interno, em `/ops/portal`.

| Issue | PR | O quê |
|---|---|---|
| #40 | #43 | área do cliente: conta 18+, responsável, pilotos, medidas (em inglês, como o site público) |
| #41 | #44 | agenda: semana por período com vagas, bloqueios, antecedência, horizonte; cliente marca, equipe confirma |
| #42 | #45 | vínculo conta ↔ cliente interno: o sistema sugere, a equipe confirma; histórico só depois do vínculo |
| #39 | — | mapa do urace.us (`docs/site-publico/mapa-2026-09-30.md`) + prompt da Hostinger (`docs/extensao/PROMPT-HOSTINGER.md`) |

- [ ] 👤 Abrir a agenda: Site público › Disponibilidade (ela nasce **fechada**, sem dia inventado)
- [ ] 👤 Testar como cliente em `/ops/portal` (criar conta, piloto, marcar) e como equipe (confirmar, vincular)
- [x] 👤 Rodar o prompt da Hostinger na extensão. O relatório chegou em 01/10:
      `docs/site-publico/levantamento-hostinger-2026-10-01.md` (#47)
- [x] 🤖 Destino dos botões "Book" com 404 decidido (dono: *"resolva p onde elas teriam que ir"*):
      Kart School → Academy 1 mês · Professional Coaching → Arrive and Drive (4787) ·
      Intensive Camp e eventos → `/contact/`. Detalhes em `docs/site-publico/decisoes-2026-10-01.md`
- [ ] 👤 Rodar `docs/extensao/PROMPT-HOSTINGER-BOTOES.md`, que só troca os links dos 25 botões
- [ ] 👤 **Urgente**: rodar `docs/extensao/PROMPT-HOSTINGER-BACKUP.md`. Ele fecha o download público
      do backup de 1,8 GB, sem apagar nada
- [x] 🤖 Endereço: o site mostra o da pista, 10724 Cosmonaut Blvd. O 6149 Cyril Ave é o de cobrança
      e do galpão, e não estava no urace.us (o mapa de 30/09 errou nisso)
- [x] 👤 Box no Orlando Kart Center: **3** (dono, 01/10)
- [ ] 👤 Rodar `docs/extensao/PROMPT-HOSTINGER-COLINA.md`: Box 3, e-mails para a URACE, tira o
      colaborador da agência e liga o registro de atividades (#49)
- [ ] 👤 Pessoalmente: trocar a senha do admin `colinatech` do WP, confirmar o e-mail admin novo,
      decidir a licença do Elementor Pro e pôr o token do Kommo no SXS LP
- [x] 👤 Área do cliente: `my.urace.us` → VPS, aprovado em 01/10. O DNS está no **Squarespace Domains**
      (conta urace@urace.us), e não no Google Cloud. Em 01/10 a extensão criou `ops` e `my` (CNAME para o
      duckdns). `my.urace.us` abre direto a área do cliente (#57)
- [x] 👤 Pagamento da sessão: QuickBooks (01/10). A sessão só é confirmada com o pagamento e a waiver (#50)
- [ ] 👤 Responder as 11 perguntas do levantamento: a Colina Tech (e-mail admin, pop-up, licença do
      Elementor, colaborador com faturamento), o lp.urace.us vulnerável, o token do Kommo no SXS LP,
      os 9 admins e o fuso UTC+0 do WordPress
- [ ] Falta (depois): e-mail de confirmação e "esqueci a senha" — precisam de envio de e-mail, que hoje o painel não faz
