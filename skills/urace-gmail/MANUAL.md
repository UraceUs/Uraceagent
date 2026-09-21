<!-- GERADO por adminai/gerar_manual_marcadores.py — NÃO EDITE À MÃO.
     A fonte é command_center/providers/taxonomia_gmail.py. -->

# Manual dos marcadores do Gmail — confirmado pelo dono

O dono leu **marcador por marcador** e confirmou em **11/09/2026**: **145 de 156**.

Este é o **único** lugar de onde sai a classificação. Vale também no painel
(Command Center → Gmail → Manual dos marcadores), que lê a mesma fonte.

## Regras invioláveis

1. **A IA não cria marcador.** O MCP recusa marcador que não existe na conta.
2. **Só classifica com marcador confirmado aqui.** Marcador que aparecer na
   caixa depois disto entra como `pendente` e a IA **não o enxerga** até o
   dono confirmar no painel. Marcador fora desta lista NÃO EXISTE para ela.
3. **Nada de apagar e nada de spam.** Arquivar, só `wNews`.
4. Na dúvida, **não chutar**: deixa na inbox e pergunta.

## O que chega → onde vai

| Chega isto | Vai para |
|---|---|
| compra feita pela URACE (pedido, confirmação) | `Finances/Shopping (+ a pasta da loja, se existir)` |
| recibo do que já foi pago | `Finances/Receipt` |
| estorno de compra | `Finances/Receipt/Purchase refund` |
| rastreio / 'seu pedido foi enviado' | `Shipping Status` |
| cobrança que a URACE precisa pagar | `Finances/Pending Invoices ❗` |
| pagamento recebido de cliente | `Finances/QuickBooks ou Finances/Square (pelo sistema que avisou)` |
| formulário do site urace.us | `Marketing & Sales/Comercial/Formulario do site` |
| lead novo pedindo informação | `Marketing & Sales/Comercial/Leads` |
| cliente da escola perguntando/agendando | `Kart Racing School \| Client talks` |
| propaganda e newsletter | `wNews` |
| aviso do Asana | `Platforms & Subscriptions/ASANA` |
| envelope do DocuSign | `Platforms & Subscriptions/Docusign` |
| currículo | `Resumes (CVs)` |
| extrato do banco | `Banks/<o banco>` |

## Os marcadores, um a um


### Finances

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Finances` | Dinheiro da empresa que não cabe em nenhuma pasta filha. | 63 |
| `Finances/Receipt` | COMPROVANTE de algo já pago: 'your receipt', recibo, confirmação de cobrança no cartão. | 2.183 |
| `Finances/Receipt/Purchase refund` | Estorno e reembolso de compra. | 18 |
| `Finances/Shopping` | COMPRA que a URACE fez: pedido feito, confirmação do pedido, fatura da loja. | 2.606 |
| `Finances/Shopping/Amazon` | Compra na Amazon (pedido, cobrança, resumo de gastos). | 159 |
| `Finances/Shopping/Orlando Kart Center` | Compra no Orlando Kart Center. | 934 |
| `Finances/Shopping/Orlando Kart Center/Track Pass` | Passe de pista comprado no OKC. | 296 |
| `Finances/Square` | Square: recebimento, depósito, relatório de vendas. | 5.609 |
| `Finances/QuickBooks` | QuickBooks: invoice emitida, pagamento recebido, aviso da conta. | 748 |
| `Finances/Clover/Invoiss` | Clover e Invoiss (maquininha e cobrança). | 282 |
| `Finances/Accounting` | Contabilidade: contador, fechamento, balanço. | 88 |
| `Finances/Pending Invoices ❗` | CONTA A PAGAR: cobrança que chegou e ainda não foi paga (decisão do dono, 28/08 — não é a receber). | 18 |
| `Finances/Tolls` | Pedágio (SunPass e afins). | 196 |
| `Finances/Auto Loan` | Financiamento de veículo. | 90 |
| `Finances/2025 Taxes` | Imposto do ano de 2025. | 3 |
| `Finances/Anderson_EB3` | Processo EB3 do Anderson (custos e documentos). | 13 |

### Banks

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Banks` | Banco e meio de pagamento que não tem pasta própria. | 61 |
| `Banks/Bank of America` | Bank of America: extrato, aviso, movimentação. | 1.805 |
| `Banks/American Express` | American Express: fatura, aviso, pontos. | 648 |
| `Banks/PayPal` | PayPal. | 344 |
| `Banks/Robinhood` | Robinhood (investimento). | 389 |
| `Banks/Stripe` | Stripe (recebimento online). | 62 |
| `Banks/Venmo` | Venmo. | 63 |
| `Banks/Seacoast Bank` | Seacoast Bank. | 71 |
| `Banks/Idea Financial` | Idea Financial (linha de crédito). | 89 |
| `Banks/Financial Proposals` | Proposta de crédito/empréstimo que chega sem ser pedida. | 112 |

### Marketing & Sales

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Marketing & Sales` | Marketing e vendas que não cabe nas pastas filhas. | 130 |
| `Marketing & Sales/Comercial` | Comercial em geral. | 3 |
| `Marketing & Sales/Comercial/Leads` | LEAD novo: pessoa interessada em pilotar/treinar, com nome e contato. | 122 |
| `Marketing & Sales/Comercial/Leads por e-mail - acompanhar` | Lead que já foi respondido e está em acompanhamento. | 87 |
| `Marketing & Sales/Comercial/Formulario do site` | Formulário do site urace.us (o e-mail automático 'Welcome to Urace' / '[Form] new lead'). | 959 |
| `Marketing & Sales/Comercial/Canais \| Social Media` | Instagram, Facebook, YouTube: aviso do canal, mensagem, desempenho. | 513 |
| `Marketing & Sales/Comercial/Landipage Old` | Landing page antiga (histórico). | 206 |
| `Marketing & Sales/Comercial/CRM` | Kommo e ferramentas de CRM. | 45 |
| `Marketing & Sales/Partnership` | Proposta de parceria e patrocínio. | 82 |
| `Marketing & Sales/Colina \| Site e ADS` | Agência Colina: site e anúncios. | 227 |
| `Marketing & Sales/TKART - Conteúdo de Kart` | TKART (conteúdo de kart). | 144 |
| `Marketing & Sales/CapCut \| Canva` | CapCut e Canva (ferramentas de criação). | 20 |
| `Marketing & Sales/Apple business` | Apple Business. | 8 |
| `Marketing & Sales/Three Marketers Company` | Three Marketers Company. | 6 |

### RACES

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `RACES` | Corrida que não é de uma série com pasta própria. | 250 |
| `RACES/National` | Série nacional sem pasta própria. | 0 |
| `RACES/National/SKUSA` | SKUSA: inscrição, regulamento, resultado. | 295 |
| `RACES/National/USPKS` | USPKS. | 113 |
| `RACES/National/Star Champions Series` | Star Champions Series. | 107 |
| `RACES/National/Supernats` | SuperNationals (Las Vegas). | 48 |
| `RACES/National/ROTAX` | ROTAX. | 32 |
| `RACES/National/ROK Vegas` | ROK Vegas. | 39 |
| `RACES/National/CKNA` | CKNA. | 12 |
| `RACES/National/IAME USA Grand National` | IAME USA Grand National. | 27 |
| `RACES/Local (FL)` | Corrida na Flórida sem pasta própria. | 35 |
| `RACES/Local (FL)/FLKC` | Florida Karting Championship. | 131 |
| `RACES/Local (FL)/Orlando Cup \| BFO` | Orlando Cup / BFO. | 80 |
| `RACES/Local (FL)/FWT` | Florida Winter Tour. | 74 |
| `RACES/Local (FL)/AMR Homestead Karting Challenge` | AMR Homestead. | 16 |
| `RACES/Local (FL)/WKA Daytona` | WKA Daytona. | 10 |
| `RACES/Local (FL)/The North Florida Kart Club` | North Florida Kart Club. | 4 |
| `RACES/Local (FL)/Championship Kart Series Race` | Championship Kart Series. | 1 |
| `RACES/F4` | Fórmula 4. | 34 |
| `RACES/F4/JFC` | JFC (F4). | 31 |
| `RACES/F4/Fara` | FARA (F4). | 17 |
| `RACES/F4/Lucas Oil` | Lucas Oil (F4). | 1 |

### LOC \| Practice

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `LOC \| Practice` | Treino independente da pista | 14 |
| `LOC \| Practice/Practice Orlando` | Treino no Orlando Kart Center. | 370 |
| `LOC \| Practice/Practice Bushnell` | Treino em Bushnell. | 65 |

### Kart Racing School

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Kart Racing School \| Client talks` | CONVERSA com cliente da escola: dúvida, agendamento, retorno do piloto. | 346 |
| `Kart Racing School \| Client talks/Pro Team Urace` | Conversa com piloto do time Pro. | 44 |
| `Kart Racing School \| Client talks/Insights` | Opinião e feedback de cliente que vale guardar. | 2 |

### Shipping Status

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Shipping Status` | RASTREIO e entrega do que foi comprado: 'purchased' 'shipped', 'on its way', tracking. | 908 |

### Suits

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Suits` | Macacão: pedido, medidas, arte, produção. | 432 |
| `Suits/Homologação` | Homologação FIA 8877-2022 do macacão. | 7 |

### Suppliers

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Suppliers` | Fornecedor sem pasta própria. | 339 |
| `Suppliers/Stickers - Jake` | Jake (adesivos). | 26 |
| `Suppliers/Mudflap` | Mudflap. | 36 |
| `Comet Kart Sales` | Comet Kart Sales. | 1 |
| `KartSport - Vantage Group` | KartSport / Vantage Group. | 38 |

### URace Store

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `URace Store` | Loja URACE em geral. | 12 |
| `URace Store/Purchase` | Pedido feito por um cliente na loja. | 43 |
| `URace Store/Shipped Orders` | Pedido da loja já enviado. | 36 |
| `URace Store/Pending order` | Pedido da loja parado, esperando algo. | 5 |
| `URace Store/Parts_Loja` | Peças da loja. | 136 |

### Platforms & Subscriptions

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Platforms & Subscriptions` | Plataforma ou assinatura sem pasta própria. | 61 |
| `Platforms & Subscriptions/ASANA` | Asana: resumo diário, tarefa atribuída, comentário. | 3.247 |
| `Platforms & Subscriptions/Ecwid` | Ecwid (loja online). | 438 |
| `Platforms & Subscriptions/Dialpad` | Dialpad (telefone). | 361 |
| `Platforms & Subscriptions/ebay` | eBay em geral. | 265 |
| `Platforms & Subscriptions/ebay/Orders` | Pedido no eBay. | 34 |
| `Platforms & Subscriptions/ebay/Offer` | Oferta/proposta no eBay. | 87 |
| `Platforms & Subscriptions/ebay/Case` | Disputa/caso no eBay. | 11 |
| `Platforms & Subscriptions/Docusign` | DocuSign: envelope, assinatura, aviso da conta. | 54 |
| `Platforms & Subscriptions/Google` | Google Workspace e conta Google. | 24 |
| `Platforms & Subscriptions/AI` | Ferramentas de IA (Anthropic, OpenAI e afins) — aviso da conta e acesso. | 69 |
| `Platforms & Subscriptions/Heroku` | Heroku. | 28 |
| `Platforms & Subscriptions/LegalShield` | LegalShield. | 82 |
| `Platforms & Subscriptions/magicJack` | magicJack. | 88 |
| `Platforms & Subscriptions/NordVPN` | NordVPN. | 31 |
| `Platforms & Subscriptions/simplybook` | SimplyBook (agendamento). | 103 |
| `Platforms & Subscriptions/subscription` | Assinatura pequena sem pasta própria. | 74 |
| `Platforms & Subscriptions/Straight` | Straight. | 24 |
| `Platforms & Subscriptions/Alibaba` | Alibaba (conta e pedidos). | 6 |
| `Platforms & Subscriptions/Amazon` | Conta Amazon/AWS (não é compra — compra vai em Finances/Shopping/Amazon). | 4 |
| `Platforms & Subscriptions/ETSY` | Etsy. | 3 |
| `Platforms & Subscriptions/GitHub` | GitHub. | 1 |

### Urace Command Center

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Urace Command Center Platform` | O próprio painel: avisos da plataforma. | 2 |
| `Urace Command Center Platform/AWS VPS` | VPS na AWS (Lightsail): aviso, cobrança, alerta. | 2 |

### Team

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Team` | Equipe em geral. | 6 |
| `Team/LARA` | Lara Carvalho. | 329 |
| `Team/Samira` | Samira. | 151 |
| `Team/Anabelly` | Anabelly. | 68 |
| `Team/Eduardo` | Eduardo Resende. | 34 |
| `Team/Lucas` | Lucas. | 2 |
| `Team/E-mails do Support` | E-mail vindo da caixa support@urace.us. | 87 |
| `Team/Ex-Employees` | Ex-funcionário sem pasta própria. | 0 |
| `Team/Ex-Employees/MANU` | Manu (ex-funcionária). | 334 |
| `Team/Ex-Employees/Nathalia` | Nathalia (ex-funcionária). | 26 |
| `Resumes (CVs)` | Currículo de candidato. | 508 |

### CORP

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `CORP` | Empresa do grupo sem pasta própria. | 1 |
| `CORP/CORP Getavan` | Getavan. | 208 |
| `CORP/CORP Canotops` | Canotops. | 37 |
| `CORP/CORP Silveira Logistics` | Silveira Logistics. | 11 |
| `CORP/CORP AZ` | CORP AZ. | 1 |
| `CORP/Betim` | Betim. | 6 |
| `CORP/Urace Autosales` | Urace Autosales. | 9 |

### ITALO

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `ITALO` | Pessoal do Italo (não é da operação). | 561 |
| `ITALO/Casamento` | Casamento. | 44 |
| `ITALO/Hannah` | Hannah. | 24 |
| `ITALO/Pending email` | Pessoal esperando resposta do Italo. | 5 |

### Travels

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Travels` | Viagem sem pasta própria. | 27 |
| `Travels/Flights` | Passagem aérea. | 1.166 |
| `Travels/Flights/Refunds and Travel Credits` | Reembolso e crédito de viagem. | 61 |
| `Travels/Hotels Reservation` | Reserva de hotel. | 732 |
| `Travels/Car rental/ Uber` | Aluguel de carro e Uber. | 175 |

### wNews

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `wNews` | PROPAGANDA: newsletter, promoção, 'unsubscribe'. Sai da inbox sozinho (decisão do dono). | 1.981 |
| `wNews/Study` | Conteúdo de estudo. | 839 |
| `wNews/Study/Programa Imperium` | Programa Imperium. | 57 |
| `wNews/Study/Coach - Peaksports` | Peaksports (coach mental). | 83 |
| `wNews/George \| Atendente` | George (atendente) — envio em massa. | 280 |
| `wNews/Italo\| MAA` | MAA. | 216 |

### Notes

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Notes` | Anotação que o Italo manda para ele mesmo. | 71 |

### Arquivo

| Marcador | O que vai aqui | Threads |
|---|---|---|
| `Years 2019-2023` | Arquivo morto por ano — a triagem NÃO usa. | 0 |
| `Years 2019-2023/y.2019` | Arquivo de 2019. | 59 |
| `Years 2019-2023/y.2020` | Arquivo de 2020. | 540 |
| `Years 2019-2023/y.2021` | Arquivo de 2021. | 361 |
| `Years 2019-2023/y.2022` | Arquivo de 2022. | 1.074 |
| `Years 2019-2023/y.2023` | Arquivo de 2023. | 131 |

## Fora da triagem — a IA ignora

O dono deixou **11** marcadores de fora. Eles existem na caixa, mas
**não são dele** e a IA não os lê nem os aplica. Quem os aplicou foi o conector
do Gmail do claude.ai (token de 16/07, rotulagem entre 9 e 12/08) — não o
Command Center. Ver `brain/40_SISTEMAS/Taxonomia do Gmail.md`.

- `Email Review/Action Required` (204 threads)
- `Email Review/Finance` (206 threads)
- `Email Review/Lead or Customer` (107 threads)
- `Email Review/Legal & Contract` (47 threads)
- `Email Review/Notification` (47 threads)
- `Email Review/Operations` (87 threads)
- `Email Review/Promotion` (5 threads)
- `Email Review/Security` (12 threads)
- `Email Review/Staff` (1 threads)
- `Email Review/Vendor` (1 threads)
- `Email Review/Verification Code` (7 threads)

> Fonte: `command_center/providers/taxonomia_gmail.py` · confirmado em 11/09/2026.
