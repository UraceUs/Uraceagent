"""O manual de classificação do Gmail — lido da caixa urace@urace.us em 11/09/2026.

O dono, em 11/09: *"em momento nenhum eu falei que era para criar marcadores… eu
preciso que a IA leia marcador por marcador que existia antes, entenda o que se
coloca em cada um, me dê o manual e eu confirmo — só daí ela sabe como agir."*

Então este arquivo é a PROPOSTA de manual: para cada marcador que existe na caixa,
o que vai dentro. Nada aqui vale até o dono confirmar no painel (Gmail → Manual dos
marcadores). Enquanto não houver marcador confirmado, a triagem NÃO roda.

Regras que valem para o manual inteiro:
  * A IA nunca cria marcador (o MCP recusa) e nunca usa marcador que não esteja
    confirmado aqui.
  * `principal` é a pasta onde a thread vai viver (o caminho completo);
    `marcadores` são etiquetas extras (loja, pessoa, série).
  * Marcador de família "Email Review" NÃO é do dono: entra como `fora` até ele dizer
    o contrário (ver a nota em brain/40_SISTEMAS/Taxonomia do Gmail.md).

O volume é o número de threads lido da conta em 11/09 — serve para o dono ver o peso
de cada marcador ao confirmar.
"""

FORA = "fora"            # não usar na triagem (a decidir com o dono)
PENDENTE = "pendente"    # proposta, esperando confirmação

# (nome exato no Gmail, família, o que vai aqui, threads, estado inicial)
MANUAL = [
    # ---------------------------------------------------------------- dinheiro
    ("Finances", "Finances", "Dinheiro da empresa que não cabe em nenhuma pasta filha.", 63, PENDENTE),
    ("Finances/Receipt", "Finances", "COMPROVANTE de algo já pago: 'your receipt', recibo, confirmação de cobrança no cartão.", 2183, PENDENTE),
    ("Finances/Receipt/Purchase refund", "Finances", "Estorno e reembolso de compra.", 18, PENDENTE),
    ("Finances/Shopping", "Finances", "COMPRA que a URACE fez: pedido feito, confirmação do pedido, fatura da loja.", 2606, PENDENTE),
    ("Finances/Shopping/Amazon", "Finances", "Compra na Amazon (pedido, cobrança, resumo de gastos).", 159, PENDENTE),
    ("Finances/Shopping/Orlando Kart Center", "Finances", "Compra no Orlando Kart Center.", 934, PENDENTE),
    ("Finances/Shopping/Orlando Kart Center/Track Pass", "Finances", "Passe de pista comprado no OKC.", 296, PENDENTE),
    ("Finances/Square", "Finances", "Square: recebimento, depósito, relatório de vendas.", 5609, PENDENTE),
    ("Finances/QuickBooks", "Finances", "QuickBooks: invoice emitida, pagamento recebido, aviso da conta.", 748, PENDENTE),
    ("Finances/Clover/Invoiss", "Finances", "Clover e Invoiss (maquininha e cobrança).", 282, PENDENTE),
    ("Finances/Accounting", "Finances", "Contabilidade: contador, fechamento, balanço.", 88, PENDENTE),
    ("Finances/Pending Invoices ❗", "Finances", "CONTA A PAGAR: cobrança que chegou e ainda não foi paga (decisão do dono, 28/08 — não é a receber).", 18, PENDENTE),
    ("Finances/Tolls", "Finances", "Pedágio (SunPass e afins).", 196, PENDENTE),
    ("Finances/Auto Loan", "Finances", "Financiamento de veículo.", 90, PENDENTE),
    ("Finances/2025 Taxes", "Finances", "Imposto do ano de 2025.", 3, PENDENTE),
    ("Finances/Anderson_EB3", "Finances", "Processo EB3 do Anderson (custos e documentos).", 13, PENDENTE),
    # ---------------------------------------------------------------- bancos
    ("Banks", "Banks", "Banco e meio de pagamento que não tem pasta própria.", 61, PENDENTE),
    ("Banks/Bank of America", "Banks", "Bank of America: extrato, aviso, movimentação.", 1805, PENDENTE),
    ("Banks/American Express", "Banks", "American Express: fatura, aviso, pontos.", 648, PENDENTE),
    ("Banks/PayPal", "Banks", "PayPal.", 344, PENDENTE),
    ("Banks/Robinhood", "Banks", "Robinhood (investimento).", 389, PENDENTE),
    ("Banks/Stripe", "Banks", "Stripe (recebimento online).", 62, PENDENTE),
    ("Banks/Venmo", "Banks", "Venmo.", 63, PENDENTE),
    ("Banks/Seacoast Bank", "Banks", "Seacoast Bank.", 71, PENDENTE),
    ("Banks/Idea Financial", "Banks", "Idea Financial (linha de crédito).", 89, PENDENTE),
    ("Banks/Financial Proposals", "Banks", "Proposta de crédito/empréstimo que chega sem ser pedida.", 112, PENDENTE),
    # ---------------------------------------------------------------- comercial
    ("Marketing & Sales", "Marketing & Sales", "Marketing e vendas que não cabe nas pastas filhas.", 130, PENDENTE),
    ("Marketing & Sales/Comercial", "Marketing & Sales", "Comercial em geral.", 3, PENDENTE),
    ("Marketing & Sales/Comercial/Leads", "Marketing & Sales", "LEAD novo: pessoa interessada em pilotar/treinar, com nome e contato.", 122, PENDENTE),
    ("Marketing & Sales/Comercial/Leads por e-mail - acompanhar", "Marketing & Sales", "Lead que já foi respondido e está em acompanhamento.", 87, PENDENTE),
    ("Marketing & Sales/Comercial/Formulario do site", "Marketing & Sales", "Formulário do site urace.us (o e-mail automático 'Welcome to Urace' / '[Form] new lead').", 959, PENDENTE),
    ("Marketing & Sales/Comercial/Canais | Social Media", "Marketing & Sales", "Instagram, Facebook, YouTube: aviso do canal, mensagem, desempenho.", 513, PENDENTE),
    ("Marketing & Sales/Comercial/Landipage Old", "Marketing & Sales", "Landing page antiga (histórico).", 206, PENDENTE),
    ("Marketing & Sales/Comercial/CRM", "Marketing & Sales", "Kommo e ferramentas de CRM.", 45, PENDENTE),
    ("Marketing & Sales/Partnership", "Marketing & Sales", "Proposta de parceria e patrocínio.", 82, PENDENTE),
    ("Marketing & Sales/Colina | Site e ADS", "Marketing & Sales", "Agência Colina: site e anúncios.", 227, PENDENTE),
    ("Marketing & Sales/TKART - Conteúdo de Kart", "Marketing & Sales", "TKART (conteúdo de kart).", 144, PENDENTE),
    ("Marketing & Sales/CapCut | Canva", "Marketing & Sales", "CapCut e Canva (ferramentas de criação).", 20, PENDENTE),
    ("Marketing & Sales/Apple business", "Marketing & Sales", "Apple Business.", 8, PENDENTE),
    ("Marketing & Sales/Three Marketers Company", "Marketing & Sales", "Three Marketers Company.", 6, PENDENTE),
    # ---------------------------------------------------------------- corridas
    ("RACES", "RACES", "Corrida que não é de uma série com pasta própria.", 250, PENDENTE),
    ("RACES/National", "RACES", "Série nacional sem pasta própria.", 0, PENDENTE),
    ("RACES/National/SKUSA", "RACES", "SKUSA: inscrição, regulamento, resultado.", 295, PENDENTE),
    ("RACES/National/USPKS", "RACES", "USPKS.", 113, PENDENTE),
    ("RACES/National/Star Champions Series", "RACES", "Star Champions Series.", 107, PENDENTE),
    ("RACES/National/Supernats", "RACES", "SuperNationals (Las Vegas).", 48, PENDENTE),
    ("RACES/National/ROTAX", "RACES", "ROTAX.", 32, PENDENTE),
    ("RACES/National/ROK Vegas", "RACES", "ROK Vegas.", 39, PENDENTE),
    ("RACES/National/CKNA", "RACES", "CKNA.", 12, PENDENTE),
    ("RACES/National/IAME USA Grand National", "RACES", "IAME USA Grand National.", 27, PENDENTE),
    ("RACES/Local (FL)", "RACES", "Corrida na Flórida sem pasta própria.", 35, PENDENTE),
    ("RACES/Local (FL)/FLKC", "RACES", "Florida Karting Championship.", 131, PENDENTE),
    ("RACES/Local (FL)/Orlando Cup | BFO", "RACES", "Orlando Cup / BFO.", 80, PENDENTE),
    ("RACES/Local (FL)/FWT", "RACES", "Florida Winter Tour.", 74, PENDENTE),
    ("RACES/Local (FL)/AMR Homestead Karting Challenge", "RACES", "AMR Homestead.", 16, PENDENTE),
    ("RACES/Local (FL)/WKA Daytona", "RACES", "WKA Daytona.", 10, PENDENTE),
    ("RACES/Local (FL)/The North Florida Kart Club", "RACES", "North Florida Kart Club.", 4, PENDENTE),
    ("RACES/Local (FL)/Championship Kart Series Race", "RACES", "Championship Kart Series.", 1, PENDENTE),
    ("RACES/F4", "RACES", "Fórmula 4.", 34, PENDENTE),
    ("RACES/F4/JFC", "RACES", "JFC (F4).", 31, PENDENTE),
    ("RACES/F4/Fara", "RACES", "FARA (F4).", 17, PENDENTE),
    ("RACES/F4/Lucas Oil", "RACES", "Lucas Oil (F4).", 1, PENDENTE),
    # ---------------------------------------------------------------- operação
    ("LOC | Practice", "LOC | Practice", "Treino sem pista definida.", 14, PENDENTE),
    ("LOC | Practice/Practice Orlando", "LOC | Practice", "Treino no Orlando Kart Center.", 370, PENDENTE),
    ("LOC | Practice/Practice Bushnell", "LOC | Practice", "Treino em Bushnell.", 65, PENDENTE),
    ("Kart Racing School | Client talks", "Kart Racing School", "CONVERSA com cliente da escola: dúvida, agendamento, retorno do piloto.", 346, PENDENTE),
    ("Kart Racing School | Client talks/Pro Team Urace", "Kart Racing School", "Conversa com piloto do time Pro.", 44, PENDENTE),
    ("Kart Racing School | Client talks/Insights", "Kart Racing School", "Opinião e feedback de cliente que vale guardar.", 2, PENDENTE),
    ("Shipping Status", "Shipping Status", "RASTREIO e entrega do que foi comprado: 'shipped', 'on its way', tracking.", 908, PENDENTE),
    ("Suits", "Suits", "Macacão: pedido, medidas, arte, produção.", 432, PENDENTE),
    ("Suits/Homologação", "Suits", "Homologação FIA 8877-2022 do macacão.", 7, PENDENTE),
    ("Suppliers", "Suppliers", "Fornecedor sem pasta própria.", 339, PENDENTE),
    ("Suppliers/Stickers - Jake", "Suppliers", "Jake (adesivos).", 26, PENDENTE),
    ("Suppliers/Mudflap", "Suppliers", "Mudflap.", 36, PENDENTE),
    ("Comet Kart Sales", "Suppliers", "Comet Kart Sales.", 1, PENDENTE),
    ("KartSport - Vantage Group", "Suppliers", "KartSport / Vantage Group.", 38, PENDENTE),
    # ---------------------------------------------------------------- loja
    ("URace Store", "URace Store", "Loja URACE em geral.", 12, PENDENTE),
    ("URace Store/Purchase", "URace Store", "Pedido feito por um cliente na loja.", 43, PENDENTE),
    ("URace Store/Shipped Orders", "URace Store", "Pedido da loja já enviado.", 36, PENDENTE),
    ("URace Store/Pending order", "URace Store", "Pedido da loja parado, esperando algo.", 5, PENDENTE),
    ("URace Store/Parts_Loja", "URace Store", "Peças da loja.", 136, PENDENTE),
    # ---------------------------------------------------------------- plataformas
    ("Platforms & Subscriptions", "Platforms & Subscriptions", "Plataforma ou assinatura sem pasta própria.", 61, PENDENTE),
    ("Platforms & Subscriptions/ASANA", "Platforms & Subscriptions", "Asana: resumo diário, tarefa atribuída, comentário.", 3247, PENDENTE),
    ("Platforms & Subscriptions/Ecwid", "Platforms & Subscriptions", "Ecwid (loja online).", 438, PENDENTE),
    ("Platforms & Subscriptions/Dialpad", "Platforms & Subscriptions", "Dialpad (telefone).", 361, PENDENTE),
    ("Platforms & Subscriptions/ebay", "Platforms & Subscriptions", "eBay em geral.", 265, PENDENTE),
    ("Platforms & Subscriptions/ebay/Orders", "Platforms & Subscriptions", "Pedido no eBay.", 34, PENDENTE),
    ("Platforms & Subscriptions/ebay/Offer", "Platforms & Subscriptions", "Oferta/proposta no eBay.", 87, PENDENTE),
    ("Platforms & Subscriptions/ebay/Case", "Platforms & Subscriptions", "Disputa/caso no eBay.", 11, PENDENTE),
    ("Platforms & Subscriptions/Docusign", "Platforms & Subscriptions", "DocuSign: envelope, assinatura, aviso da conta.", 54, PENDENTE),
    ("Platforms & Subscriptions/Google", "Platforms & Subscriptions", "Google Workspace e conta Google.", 24, PENDENTE),
    ("Platforms & Subscriptions/AI", "Platforms & Subscriptions", "Ferramentas de IA (Anthropic, OpenAI e afins) — aviso da conta e acesso.", 69, PENDENTE),
    ("Platforms & Subscriptions/Heroku", "Platforms & Subscriptions", "Heroku.", 28, PENDENTE),
    ("Platforms & Subscriptions/LegalShield", "Platforms & Subscriptions", "LegalShield.", 82, PENDENTE),
    ("Platforms & Subscriptions/magicJack", "Platforms & Subscriptions", "magicJack.", 88, PENDENTE),
    ("Platforms & Subscriptions/NordVPN", "Platforms & Subscriptions", "NordVPN.", 31, PENDENTE),
    ("Platforms & Subscriptions/simplybook", "Platforms & Subscriptions", "SimplyBook (agendamento).", 103, PENDENTE),
    ("Platforms & Subscriptions/subscription", "Platforms & Subscriptions", "Assinatura pequena sem pasta própria.", 74, PENDENTE),
    ("Platforms & Subscriptions/Straight", "Platforms & Subscriptions", "Straight.", 24, PENDENTE),
    ("Platforms & Subscriptions/Alibaba", "Platforms & Subscriptions", "Alibaba (conta e pedidos).", 6, PENDENTE),
    ("Platforms & Subscriptions/Amazon", "Platforms & Subscriptions", "Conta Amazon/AWS (não é compra — compra vai em Finances/Shopping/Amazon).", 4, PENDENTE),
    ("Platforms & Subscriptions/ETSY", "Platforms & Subscriptions", "Etsy.", 3, PENDENTE),
    ("Platforms & Subscriptions/GitHub", "Platforms & Subscriptions", "GitHub.", 1, PENDENTE),
    ("Urace Command Center Platform", "Urace Command Center", "O próprio painel: avisos da plataforma.", 2, PENDENTE),
    ("Urace Command Center Platform/AWS VPS", "Urace Command Center", "VPS na AWS (Lightsail): aviso, cobrança, alerta.", 2, PENDENTE),
    # ---------------------------------------------------------------- equipe
    ("Team", "Team", "Equipe em geral.", 6, PENDENTE),
    ("Team/LARA", "Team", "Lara Carvalho.", 329, PENDENTE),
    ("Team/Samira", "Team", "Samira.", 151, PENDENTE),
    ("Team/Anabelly", "Team", "Anabelly.", 68, PENDENTE),
    ("Team/Eduardo", "Team", "Eduardo Resende.", 34, PENDENTE),
    ("Team/Lucas", "Team", "Lucas.", 2, PENDENTE),
    ("Team/E-mails do Support", "Team", "E-mail vindo da caixa support@urace.us.", 87, PENDENTE),
    ("Team/Ex-Employees", "Team", "Ex-funcionário sem pasta própria.", 0, PENDENTE),
    ("Team/Ex-Employees/MANU", "Team", "Manu (ex-funcionária).", 334, PENDENTE),
    ("Team/Ex-Employees/Nathalia", "Team", "Nathalia (ex-funcionária).", 26, PENDENTE),
    ("Resumes (CVs)", "Team", "Currículo de candidato.", 508, PENDENTE),
    # ---------------------------------------------------------------- empresas e pessoal
    ("CORP", "CORP", "Empresa do grupo sem pasta própria.", 1, PENDENTE),
    ("CORP/CORP Getavan", "CORP", "Getavan.", 208, PENDENTE),
    ("CORP/CORP Canotops", "CORP", "Canotops.", 37, PENDENTE),
    ("CORP/CORP Silveira Logistics", "CORP", "Silveira Logistics.", 11, PENDENTE),
    ("CORP/CORP AZ", "CORP", "CORP AZ.", 1, PENDENTE),
    ("CORP/Betim", "CORP", "Betim.", 6, PENDENTE),
    ("CORP/Urace Autosales", "CORP", "Urace Autosales.", 9, PENDENTE),
    ("ITALO", "ITALO", "Pessoal do Italo (não é da operação).", 561, PENDENTE),
    ("ITALO/Casamento", "ITALO", "Casamento.", 44, PENDENTE),
    ("ITALO/Hannah", "ITALO", "Hannah.", 24, PENDENTE),
    ("ITALO/Pending email", "ITALO", "Pessoal esperando resposta do Italo.", 5, PENDENTE),
    ("Travels", "Travels", "Viagem sem pasta própria.", 27, PENDENTE),
    ("Travels/Flights", "Travels", "Passagem aérea.", 1166, PENDENTE),
    ("Travels/Flights/Refunds and Travel Credits", "Travels", "Reembolso e crédito de viagem.", 61, PENDENTE),
    ("Travels/Hotels Reservation", "Travels", "Reserva de hotel.", 732, PENDENTE),
    ("Travels/Car rental/ Uber", "Travels", "Aluguel de carro e Uber.", 175, PENDENTE),
    # ---------------------------------------------------------------- ruído e arquivo
    ("wNews", "wNews", "PROPAGANDA: newsletter, promoção, 'unsubscribe'. Sai da inbox sozinho (decisão do dono).", 1981, PENDENTE),
    ("wNews/Study", "wNews", "Conteúdo de estudo.", 839, PENDENTE),
    ("wNews/Study/Programa Imperium", "wNews", "Programa Imperium.", 57, PENDENTE),
    ("wNews/Study/Coach - Peaksports", "wNews", "Peaksports (coach mental).", 83, PENDENTE),
    ("wNews/George | Atendente", "wNews", "George (atendente) — envio em massa.", 280, PENDENTE),
    ("wNews/Italo| MAA", "wNews", "MAA.", 216, PENDENTE),
    ("Notes", "Notes", "Anotação que o Italo manda para ele mesmo.", 71, PENDENTE),
    ("Years 2019-2023", "Arquivo", "Arquivo morto por ano — a triagem NÃO usa.", 0, FORA),
    ("Years 2019-2023/y.2019", "Arquivo", "Arquivo de 2019.", 59, FORA),
    ("Years 2019-2023/y.2020", "Arquivo", "Arquivo de 2020.", 540, FORA),
    ("Years 2019-2023/y.2021", "Arquivo", "Arquivo de 2021.", 361, FORA),
    ("Years 2019-2023/y.2022", "Arquivo", "Arquivo de 2022.", 1074, FORA),
    ("Years 2019-2023/y.2023", "Arquivo", "Arquivo de 2023.", 131, FORA),
    # ------------------------------------------------- não é do dono (11/09/2026)
    ("Email Review/Action Required", "Email Review", "NÃO é marcador do dono: apareceu em setembro, aplicado por algo de fora do painel. A triagem não usa.", 204, FORA),
    ("Email Review/Finance", "Email Review", "NÃO é marcador do dono (ver acima).", 206, FORA),
    ("Email Review/Lead or Customer", "Email Review", "NÃO é marcador do dono (ver acima).", 107, FORA),
    ("Email Review/Legal & Contract", "Email Review", "NÃO é marcador do dono (ver acima).", 47, FORA),
    ("Email Review/Notification", "Email Review", "NÃO é marcador do dono (ver acima).", 47, FORA),
    ("Email Review/Operations", "Email Review", "NÃO é marcador do dono (ver acima).", 87, FORA),
    ("Email Review/Promotion", "Email Review", "NÃO é marcador do dono (ver acima).", 5, FORA),
    ("Email Review/Security", "Email Review", "NÃO é marcador do dono (ver acima).", 12, FORA),
    ("Email Review/Staff", "Email Review", "NÃO é marcador do dono (ver acima).", 1, FORA),
    ("Email Review/Vendor", "Email Review", "NÃO é marcador do dono (ver acima).", 1, FORA),
    ("Email Review/Verification Code", "Email Review", "NÃO é marcador do dono (ver acima).", 7, FORA),
]

# Casos do dia a dia que o dono citou — o manual responde cada um.
EXEMPLOS = [
    ("compra feita pela URACE (pedido, confirmação)", "Finances/Shopping (+ a pasta da loja, se existir)"),
    ("recibo do que já foi pago", "Finances/Receipt"),
    ("estorno de compra", "Finances/Receipt/Purchase refund"),
    ("rastreio / 'seu pedido foi enviado'", "Shipping Status"),
    ("cobrança que a URACE precisa pagar", "Finances/Pending Invoices ❗"),
    ("pagamento recebido de cliente", "Finances/QuickBooks ou Finances/Square (pelo sistema que avisou)"),
    ("formulário do site urace.us", "Marketing & Sales/Comercial/Formulario do site"),
    ("lead novo pedindo informação", "Marketing & Sales/Comercial/Leads"),
    ("cliente da escola perguntando/agendando", "Kart Racing School | Client talks"),
    ("propaganda e newsletter", "wNews"),
    ("aviso do Asana", "Platforms & Subscriptions/ASANA"),
    ("envelope do DocuSign", "Platforms & Subscriptions/Docusign"),
    ("currículo", "Resumes (CVs)"),
    ("extrato do banco", "Banks/<o banco>"),
]


def por_nome():
    return {nome: (familia, o_que, threads, estado) for nome, familia, o_que, threads, estado in MANUAL}
