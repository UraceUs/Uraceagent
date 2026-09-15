"""O manual de classificação do Gmail — lido da caixa urace@urace.us em 11/09/2026.

O dono, em 11/09: *"em momento nenhum eu falei que era para criar marcadores… eu
preciso que a IA leia marcador por marcador que existia antes, entenda o que se
coloca em cada um, me dê o manual e eu confirmo — só daí ela sabe como agir."*

Ele leu marcador por marcador e CONFIRMOU em 11/09/2026 (145 dos 156), corrigindo dois
textos com a própria mão: "LOC | Practice" virou "treino independente da pista" e
"Shipping Status" ganhou o 'purchased'. Os 11 "Email Review/…" ele deixou de fora.

É este manual que a triagem usa — e só ele. Marcador que aparecer na caixa depois disto
entra como `pendente` e a IA não o enxerga até o dono confirmar no painel
(Gmail → Manual dos marcadores).

Regras que valem para o manual inteiro:
  * A IA nunca cria marcador (o MCP recusa) e nunca usa marcador que não esteja
    confirmado aqui.
  * `principal` é a pasta onde a thread vai viver (o caminho completo);
    `marcadores` são etiquetas extras (loja, pessoa, série).
  * Marcador de família "Email Review" NÃO é do dono: entra como `fora` até ele dizer
    o contrário (ver a nota em brain/40_SISTEMAS/Taxonomia do Gmail.md). Os 11 foram
    APAGADOS da caixa em 11/09, a pedido dele (714 conversas perderam a etiqueta;
    nenhum e-mail foi apagado). As linhas ficam aqui de propósito: se algo os recriar,
    já nascem `fora` e a IA não os enxerga.

O volume é o número de threads lido da conta em 11/09 — serve para o dono ver o peso
de cada marcador ao confirmar.
"""

FORA = "fora"            # não usar na triagem
OK = "confirmado"        # CONFIRMADO PELO DONO em 11/09/2026, marcador por marcador
PENDENTE = "pendente"    # proposta nova (marcador que aparecer na caixa depois disto)

CONFIRMADO_EM = "2026-09-11"
CONFIRMADO_POR = "dono (manual confirmado em 11/09/2026)"

# (nome exato no Gmail, família, o que vai aqui, threads, estado inicial)
MANUAL = [
    # ---------------------------------------------------------------- dinheiro
    ("Finances", "Finances", "Dinheiro da empresa que não cabe em nenhuma pasta filha.", 63, OK),
    ("Finances/Receipt", "Finances", "COMPROVANTE de algo já pago: 'your receipt', recibo, confirmação de cobrança no cartão.", 2183, OK),
    ("Finances/Receipt/Purchase refund", "Finances", "Estorno e reembolso de compra.", 18, OK),
    ("Finances/Shopping", "Finances", "COMPRA que a URACE fez: pedido feito, confirmação do pedido, fatura da loja.", 2606, OK),
    ("Finances/Shopping/Amazon", "Finances", "Compra na Amazon (pedido, cobrança, resumo de gastos).", 159, OK),
    ("Finances/Shopping/Orlando Kart Center", "Finances", "Compra no Orlando Kart Center.", 934, OK),
    ("Finances/Shopping/Orlando Kart Center/Track Pass", "Finances", "Passe de pista comprado no OKC.", 296, OK),
    ("Finances/Square", "Finances", "Square: recebimento, depósito, relatório de vendas.", 5609, OK),
    ("Finances/QuickBooks", "Finances", "QuickBooks: invoice emitida, pagamento recebido, aviso da conta.", 748, OK),
    ("Finances/Clover/Invoiss", "Finances", "Clover e Invoiss (maquininha e cobrança).", 282, OK),
    ("Finances/Accounting", "Finances", "Contabilidade: contador, fechamento, balanço.", 88, OK),
    ("Finances/Pending Invoices ❗", "Finances", "CONTA A PAGAR: cobrança que chegou e ainda não foi paga (decisão do dono, 28/08 — não é a receber).", 18, OK),
    ("Finances/Tolls", "Finances", "Pedágio (SunPass e afins).", 196, OK),
    ("Finances/Auto Loan", "Finances", "Financiamento de veículo.", 90, OK),
    ("Finances/2025 Taxes", "Finances", "Imposto do ano de 2025.", 3, OK),
    ("Finances/Anderson_EB3", "Finances", "Processo EB3 do Anderson (custos e documentos).", 13, OK),
    # ---------------------------------------------------------------- bancos
    ("Banks", "Banks", "Banco e meio de pagamento que não tem pasta própria.", 61, OK),
    ("Banks/Bank of America", "Banks", "Bank of America: extrato, aviso, movimentação.", 1805, OK),
    ("Banks/American Express", "Banks", "American Express: fatura, aviso, pontos.", 648, OK),
    ("Banks/PayPal", "Banks", "PayPal.", 344, OK),
    ("Banks/Robinhood", "Banks", "Robinhood (investimento).", 389, OK),
    ("Banks/Stripe", "Banks", "Stripe (recebimento online).", 62, OK),
    ("Banks/Venmo", "Banks", "Venmo.", 63, OK),
    ("Banks/Seacoast Bank", "Banks", "Seacoast Bank.", 71, OK),
    ("Banks/Idea Financial", "Banks", "Idea Financial (linha de crédito).", 89, OK),
    ("Banks/Financial Proposals", "Banks", "Proposta de crédito/empréstimo que chega sem ser pedida.", 112, OK),
    # ---------------------------------------------------------------- comercial
    ("Marketing & Sales", "Marketing & Sales", "Marketing e vendas que não cabe nas pastas filhas.", 130, OK),
    ("Marketing & Sales/Comercial", "Marketing & Sales", "Comercial em geral.", 3, OK),
    ("Marketing & Sales/Comercial/Leads", "Marketing & Sales", "LEAD novo: pessoa interessada em pilotar/treinar, com nome e contato.", 122, OK),
    ("Marketing & Sales/Comercial/Leads por e-mail - acompanhar", "Marketing & Sales", "Lead que já foi respondido e está em acompanhamento.", 87, OK),
    ("Marketing & Sales/Comercial/Formulario do site", "Marketing & Sales", "Formulário do site urace.us (o e-mail automático 'Welcome to Urace' / '[Form] new lead').", 959, OK),
    ("Marketing & Sales/Comercial/Canais | Social Media", "Marketing & Sales", "Instagram, Facebook, YouTube: aviso do canal, mensagem, desempenho.", 513, OK),
    ("Marketing & Sales/Comercial/Landipage Old", "Marketing & Sales", "Landing page antiga (histórico).", 206, OK),
    ("Marketing & Sales/Comercial/CRM", "Marketing & Sales", "Kommo e ferramentas de CRM.", 45, OK),
    ("Marketing & Sales/Partnership", "Marketing & Sales", "Proposta de parceria e patrocínio.", 82, OK),
    ("Marketing & Sales/Colina | Site e ADS", "Marketing & Sales", "Agência Colina: site e anúncios.", 227, OK),
    ("Marketing & Sales/TKART - Conteúdo de Kart", "Marketing & Sales", "TKART (conteúdo de kart).", 144, OK),
    ("Marketing & Sales/CapCut | Canva", "Marketing & Sales", "CapCut e Canva (ferramentas de criação).", 20, OK),
    ("Marketing & Sales/Apple business", "Marketing & Sales", "Apple Business.", 8, OK),
    ("Marketing & Sales/Three Marketers Company", "Marketing & Sales", "Three Marketers Company.", 6, OK),
    # ---------------------------------------------------------------- corridas
    ("RACES", "RACES", "Corrida que não é de uma série com pasta própria.", 250, OK),
    ("RACES/National", "RACES", "Série nacional sem pasta própria.", 0, OK),
    ("RACES/National/SKUSA", "RACES", "SKUSA: inscrição, regulamento, resultado.", 295, OK),
    ("RACES/National/USPKS", "RACES", "USPKS.", 113, OK),
    ("RACES/National/Star Champions Series", "RACES", "Star Champions Series.", 107, OK),
    ("RACES/National/Supernats", "RACES", "SuperNationals (Las Vegas).", 48, OK),
    ("RACES/National/ROTAX", "RACES", "ROTAX.", 32, OK),
    ("RACES/National/ROK Vegas", "RACES", "ROK Vegas.", 39, OK),
    ("RACES/National/CKNA", "RACES", "CKNA.", 12, OK),
    ("RACES/National/IAME USA Grand National", "RACES", "IAME USA Grand National.", 27, OK),
    ("RACES/Local (FL)", "RACES", "Corrida na Flórida sem pasta própria.", 35, OK),
    ("RACES/Local (FL)/FLKC", "RACES", "Florida Karting Championship.", 131, OK),
    ("RACES/Local (FL)/Orlando Cup | BFO", "RACES", "Orlando Cup / BFO.", 80, OK),
    ("RACES/Local (FL)/FWT", "RACES", "Florida Winter Tour.", 74, OK),
    ("RACES/Local (FL)/AMR Homestead Karting Challenge", "RACES", "AMR Homestead.", 16, OK),
    ("RACES/Local (FL)/WKA Daytona", "RACES", "WKA Daytona.", 10, OK),
    ("RACES/Local (FL)/The North Florida Kart Club", "RACES", "North Florida Kart Club.", 4, OK),
    ("RACES/Local (FL)/Championship Kart Series Race", "RACES", "Championship Kart Series.", 1, OK),
    ("RACES/F4", "RACES", "Fórmula 4.", 34, OK),
    ("RACES/F4/JFC", "RACES", "JFC (F4).", 31, OK),
    ("RACES/F4/Fara", "RACES", "FARA (F4).", 17, OK),
    ("RACES/F4/Lucas Oil", "RACES", "Lucas Oil (F4).", 1, OK),
    # ---------------------------------------------------------------- operação
    ("LOC | Practice", "LOC | Practice", "Treino independente da pista", 14, OK),
    ("LOC | Practice/Practice Orlando", "LOC | Practice", "Treino no Orlando Kart Center.", 370, OK),
    ("LOC | Practice/Practice Bushnell", "LOC | Practice", "Treino em Bushnell.", 65, OK),
    ("Kart Racing School | Client talks", "Kart Racing School", "CONVERSA com cliente da escola: dúvida, agendamento, retorno do piloto.", 346, OK),
    ("Kart Racing School | Client talks/Pro Team Urace", "Kart Racing School", "Conversa com piloto do time Pro.", 44, OK),
    ("Kart Racing School | Client talks/Insights", "Kart Racing School", "Opinião e feedback de cliente que vale guardar.", 2, OK),
    ("Shipping Status", "Shipping Status", "RASTREIO e entrega do que foi comprado: 'purchased' 'shipped', 'on its way', tracking.", 908, OK),
    ("Suits", "Suits", "Macacão: pedido, medidas, arte, produção.", 432, OK),
    ("Suits/Homologação", "Suits", "Homologação FIA 8877-2022 do macacão.", 7, OK),
    ("Suppliers", "Suppliers", "Fornecedor sem pasta própria.", 339, OK),
    ("Suppliers/Stickers - Jake", "Suppliers", "Jake (adesivos).", 26, OK),
    ("Suppliers/Mudflap", "Suppliers", "Mudflap.", 36, OK),
    ("Comet Kart Sales", "Suppliers", "Comet Kart Sales.", 1, OK),
    ("KartSport - Vantage Group", "Suppliers", "KartSport / Vantage Group.", 38, OK),
    # ---------------------------------------------------------------- loja
    ("URace Store", "URace Store", "Loja URACE em geral.", 12, OK),
    ("URace Store/Purchase", "URace Store", "Pedido feito por um cliente na loja.", 43, OK),
    ("URace Store/Shipped Orders", "URace Store", "Pedido da loja já enviado.", 36, OK),
    ("URace Store/Pending order", "URace Store", "Pedido da loja parado, esperando algo.", 5, OK),
    ("URace Store/Parts_Loja", "URace Store", "Peças da loja.", 136, OK),
    # ---------------------------------------------------------------- plataformas
    ("Platforms & Subscriptions", "Platforms & Subscriptions", "Plataforma ou assinatura sem pasta própria.", 61, OK),
    ("Platforms & Subscriptions/ASANA", "Platforms & Subscriptions", "Asana: resumo diário, tarefa atribuída, comentário.", 3247, OK),
    ("Platforms & Subscriptions/Ecwid", "Platforms & Subscriptions", "Ecwid (loja online).", 438, OK),
    ("Platforms & Subscriptions/Dialpad", "Platforms & Subscriptions", "Dialpad (telefone).", 361, OK),
    ("Platforms & Subscriptions/ebay", "Platforms & Subscriptions", "eBay em geral.", 265, OK),
    ("Platforms & Subscriptions/ebay/Orders", "Platforms & Subscriptions", "Pedido no eBay.", 34, OK),
    ("Platforms & Subscriptions/ebay/Offer", "Platforms & Subscriptions", "Oferta/proposta no eBay.", 87, OK),
    ("Platforms & Subscriptions/ebay/Case", "Platforms & Subscriptions", "Disputa/caso no eBay.", 11, OK),
    ("Platforms & Subscriptions/Docusign", "Platforms & Subscriptions", "DocuSign: envelope, assinatura, aviso da conta.", 54, OK),
    ("Platforms & Subscriptions/Google", "Platforms & Subscriptions", "Google Workspace e conta Google.", 24, OK),
    ("Platforms & Subscriptions/AI", "Platforms & Subscriptions", "Ferramentas de IA (Anthropic, OpenAI e afins) — aviso da conta e acesso.", 69, OK),
    ("Platforms & Subscriptions/Heroku", "Platforms & Subscriptions", "Heroku.", 28, OK),
    ("Platforms & Subscriptions/LegalShield", "Platforms & Subscriptions", "LegalShield.", 82, OK),
    ("Platforms & Subscriptions/magicJack", "Platforms & Subscriptions", "magicJack.", 88, OK),
    ("Platforms & Subscriptions/NordVPN", "Platforms & Subscriptions", "NordVPN.", 31, OK),
    ("Platforms & Subscriptions/simplybook", "Platforms & Subscriptions", "SimplyBook (agendamento).", 103, OK),
    ("Platforms & Subscriptions/subscription", "Platforms & Subscriptions", "Assinatura pequena sem pasta própria.", 74, OK),
    ("Platforms & Subscriptions/Straight", "Platforms & Subscriptions", "Straight.", 24, OK),
    ("Platforms & Subscriptions/Alibaba", "Platforms & Subscriptions", "Alibaba (conta e pedidos).", 6, OK),
    ("Platforms & Subscriptions/Amazon", "Platforms & Subscriptions", "Conta Amazon/AWS (não é compra — compra vai em Finances/Shopping/Amazon).", 4, OK),
    ("Platforms & Subscriptions/ETSY", "Platforms & Subscriptions", "Etsy.", 3, OK),
    ("Platforms & Subscriptions/GitHub", "Platforms & Subscriptions", "GitHub.", 1, OK),
    ("Urace Command Center Platform", "Urace Command Center", "O próprio painel: avisos da plataforma.", 2, OK),
    ("Urace Command Center Platform/AWS VPS", "Urace Command Center", "VPS na AWS (Lightsail): aviso, cobrança, alerta.", 2, OK),
    # ---------------------------------------------------------------- equipe
    ("Team", "Team", "Equipe em geral.", 6, OK),
    ("Team/LARA", "Team", "Lara Carvalho.", 329, OK),
    ("Team/Samira", "Team", "Samira.", 151, OK),
    ("Team/Anabelly", "Team", "Anabelly.", 68, OK),
    ("Team/Eduardo", "Team", "Eduardo Resende.", 34, OK),
    ("Team/Lucas", "Team", "Lucas.", 2, OK),
    ("Team/E-mails do Support", "Team", "E-mail vindo da caixa support@urace.us.", 87, OK),
    ("Team/Ex-Employees", "Team", "Ex-funcionário sem pasta própria.", 0, OK),
    ("Team/Ex-Employees/MANU", "Team", "Manu (ex-funcionária).", 334, OK),
    ("Team/Ex-Employees/Nathalia", "Team", "Nathalia (ex-funcionária).", 26, OK),
    ("Resumes (CVs)", "Team", "Currículo de candidato.", 508, OK),
    # ---------------------------------------------------------------- empresas e pessoal
    ("CORP", "CORP", "Empresa do grupo sem pasta própria.", 1, OK),
    ("CORP/CORP Getavan", "CORP", "Getavan.", 208, OK),
    ("CORP/CORP Canotops", "CORP", "Canotops.", 37, OK),
    ("CORP/CORP Silveira Logistics", "CORP", "Silveira Logistics.", 11, OK),
    ("CORP/CORP AZ", "CORP", "CORP AZ.", 1, OK),
    ("CORP/Betim", "CORP", "Betim.", 6, OK),
    ("CORP/Urace Autosales", "CORP", "Urace Autosales.", 9, OK),
    ("ITALO", "ITALO", "Pessoal do Italo (não é da operação).", 561, OK),
    ("ITALO/Casamento", "ITALO", "Casamento.", 44, OK),
    ("ITALO/Hannah", "ITALO", "Hannah.", 24, OK),
    ("ITALO/Pending email", "ITALO", "Pessoal esperando resposta do Italo.", 5, OK),
    ("Travels", "Travels", "Viagem sem pasta própria.", 27, OK),
    ("Travels/Flights", "Travels", "Passagem aérea.", 1166, OK),
    ("Travels/Flights/Refunds and Travel Credits", "Travels", "Reembolso e crédito de viagem.", 61, OK),
    ("Travels/Hotels Reservation", "Travels", "Reserva de hotel.", 732, OK),
    ("Travels/Car rental/ Uber", "Travels", "Aluguel de carro e Uber.", 175, OK),
    # ---------------------------------------------------------------- ruído e arquivo
    ("wNews", "wNews", "PROPAGANDA: newsletter, promoção, 'unsubscribe'. Sai da inbox sozinho (decisão do dono).", 1981, OK),
    ("wNews/Study", "wNews", "Conteúdo de estudo.", 839, OK),
    ("wNews/Study/Programa Imperium", "wNews", "Programa Imperium.", 57, OK),
    ("wNews/Study/Coach - Peaksports", "wNews", "Peaksports (coach mental).", 83, OK),
    ("wNews/George | Atendente", "wNews", "George (atendente) — envio em massa.", 280, OK),
    ("wNews/Italo| MAA", "wNews", "MAA.", 216, OK),
    ("Notes", "Notes", "Anotação que o Italo manda para ele mesmo.", 71, OK),
    ("Years 2019-2023", "Arquivo", "Arquivo morto por ano — a triagem NÃO usa.", 0, OK),
    ("Years 2019-2023/y.2019", "Arquivo", "Arquivo de 2019.", 59, OK),
    ("Years 2019-2023/y.2020", "Arquivo", "Arquivo de 2020.", 540, OK),
    ("Years 2019-2023/y.2021", "Arquivo", "Arquivo de 2021.", 361, OK),
    ("Years 2019-2023/y.2022", "Arquivo", "Arquivo de 2022.", 1074, OK),
    ("Years 2019-2023/y.2023", "Arquivo", "Arquivo de 2023.", 131, OK),
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


# ============================================================ support@urace.us
# Lido da caixa em 14/09/2026 (adminai/ler_marcadores_caixa.py). O manual acima é da
# urace@; esta caixa nunca tinha sido lida, e é outra coisa: atendimento, funil de
# cliente e operação com fornecedor — não finanças e plataformas.
#
# TUDO entra como PENDENTE. O dono confirma marcador por marcador no painel
# (Gmail → Manual dos marcadores → aba support@), como fez na urace@ em 11/09.
# As descrições dizem o que ESTÁ dentro, não o que o nome promete: onde as duas
# coisas divergem, está marcado com ⚠️ para ele decidir.
MANUAL_SUPPORT = [
    # ------------------------------------------------- não são do dono
    ("Action Required", "Intruso (confira)", "⚠️ NÃO parece ser seu: mesmo nome de uma das categorias 'Email Review/' que foram apagadas da urace@ em 11/09. 3 conversas, aplicadas por fora. Sugiro deixar de fora da triagem.", 3, FORA),
    ("Lead or Customer", "Intruso (confira)", "⚠️ NÃO parece ser seu: mesmo nome de outra categoria 'Email Review/'. 2 conversas. Sugiro deixar de fora.", 2, FORA),
    ("Operations", "Intruso (confira)", "⚠️ NÃO parece ser seu: mesmo nome de outra categoria 'Email Review/'. 1 conversa, do Kommo. Sugiro deixar de fora.", 1, FORA),
    # ------------------------------------------------- atendimento
    ("Customer Service", "Customer Service", "Pasta-mãe do atendimento. Está vazia: as conversas vivem nas filhas.", 0, PENDENTE),
    ("Customer Service/LP Leads", "Customer Service", "LEAD que entrou pela landing page: o disparo 'Welcome to Urace - <nome>' do site. É o maior volume da caixa.", 413, PENDENTE),
    ("Customer Service/Leads", "Customer Service", "LEAD que virou conversa: a pessoa respondeu e há troca sobre começar no kart.", 102, PENDENTE),
    ("Customer Service/Leads/Acompanhar", "Customer Service", "Lead que ficou de responder e depende de um follow-up NOSSO.", 17, PENDENTE),
    ("Customer Service/Leads/Leads Forms", "Customer Service", "Lead do formulário do site ('New message from Urace - The Driver Factory').", 21, PENDENTE),
    ("Customer Service/Leads/Leads Newsletter", "Customer Service", "Lead que veio do formulário da newsletter.", 3, PENDENTE),
    ("Customer Service/Urace Clients", "Customer Service", "Conversa com quem JÁ É cliente: coaching, sessão, dúvida de quem está treinando.", 53, PENDENTE),
    ("Customer Service/Venda fechada", "Customer Service", "Conversa que terminou em VENDA. O lead comprou.", 43, PENDENTE),
    ("Customer Service/Summer Camp", "Customer Service", "Summer Camp: interesse, vaga, agenda e retorno do responsável.", 159, PENDENTE),
    ("Customer Service/Service/New Order", "Customer Service", "Pedido novo na loja/agendamento ('You've got a new order: #...').", 1, PENDENTE),
    ("Customer Service/Services - Canceled", "Customer Service", "Compra ou agendamento CANCELADO, e pedido que falhou.", 16, PENDENTE),
    ("Customer Service/Kommo", "Customer Service", "Notificação do Kommo: aviso de lead, limite de sessão, código de login.", 53, PENDENTE),
    ("Curriculos", "Curriculos", "⚠️ O nome diz currículo, mas o que está dentro é conversa com candidato/lead ('Thank you for reaching out'). Só 2 conversas. Confira antes de confirmar.", 2, PENDENTE),
    # ------------------------------------------------- escola e pilotos
    ("Karting School", "Karting School", "ESCOLA: conversa com aluno e responsável — confirmação, retorno, recado da temporada.", 187, PENDENTE),
    ("Karting School/URace confirmation", "Karting School", "Confirmação de sessão marcada com o piloto ('URACE - Session Confirmation').", 63, PENDENTE),
    ("Karting School/Welcome", "Karting School", "Boas-vindas ao aluno novo e o formulário inicial ('Tell Us a Bit About You').", 67, PENDENTE),
    ("Events & National Races", "Events & National Races", "Corrida e evento: inscrição, logística, passagem e reembolso ligados à prova.", 33, PENDENTE),
    ("Events & National Races/FWT", "Events & National Races", "Florida Winter Tour: agenda de treino do piloto na semana da prova.", 2, PENDENTE),
    # ------------------------------------------------- documento e contrato
    ("Waivers", "Waivers", "WAIVER de responsabilidade no DocuSign: enviada, vista, assinada ou anulada. É daqui que sai a waiver do cliente.", 57, PENDENTE),
    ("Share request", "Share request", "Pedido e aviso de compartilhamento do Google Drive (documento, planilha, pasta).", 19, PENDENTE),
    # ------------------------------------------------- dinheiro
    ("Financeiro", "Financeiro", "Pasta-mãe do financeiro. Está vazia: o dinheiro vive nas filhas.", 0, PENDENTE),
    ("Financeiro/Charges", "Financeiro", "COBRANÇA ao cliente: saldo em aberto e lembrete de pagamento que nós enviamos.", 51, PENDENTE),
    ("Financeiro/Recibos", "Financeiro", "Recibo do que a URACE pagou (n8n/Paddle, GitHub, QuickBooks).", 11, PENDENTE),
    ("Financeiro/Pit Pass and Driver Pass OKC", "Financeiro", "Ingresso de pit pass e driver pass do Orlando Kart Center (eveyevents).", 72, PENDENTE),
    ("Financeiro/Wise | Paid", "Financeiro", "Wise: aviso da conta, mudança de termos e pagamento feito por lá.", 35, PENDENTE),
    ("Financeiro/Others purchases", "Financeiro", "⚠️ Compras avulsas, mas o conteúdo está misturado (propaganda do Alibaba, aviso de login). Vale rever o que deve ficar aqui.", 13, PENDENTE),
    ("Financeiro/Anabelly", "Financeiro", "Financeiro tratado pela Anabelly. Está vazio hoje.", 0, PENDENTE),
    # ------------------------------------------------- fornecedor e produto
    ("Fornecedores", "Fornecedores", "FORNECEDOR: negociação, amostra, medida de macacão, conversa com fábrica (Alibaba, Speed, Palace).", 285, PENDENTE),
    ("Fornecedores/Pendente", "Fornecedores", "Pedido ao fornecedor em ABERTO: falta pagar, falta enviar, falta responder.", 7, PENDENTE),
    ("Fornecedores/Recebido", "Fornecedores", "Pedido ao fornecedor que já CHEGOU.", 7, PENDENTE),
    ("Suits Order", "Suits Order", "MACACÃO: medidas do piloto, acerto do pedido e acompanhamento até a entrega.", 60, PENDENTE),
    ("Canotops", "Canotops", "Compra da Canotops no Alibaba: pedido Trade Assurance, pagamento, envio e encerramento.", 141, PENDENTE),
    ("Shipping", "Shipping", "Transporte: FedEx (chamado, tarifa, programa de pontos).", 13, PENDENTE),
    ("Site - Loja", "Site - Loja", "Loja do site: pedido que falhou.", 2, PENDENTE),
    # ------------------------------------------------- marketing
    ("Marketing", "Marketing", "Marketing e parceria que chegam no support@: proposta, patrocínio, fornecedor de brinde, formulário de qualificação.", 71, PENDENTE),
    ("Marketing/RD Station /MailMarketing", "Marketing", "⚠️ RD Station — MAS ATENÇÃO: há mensagens de `rdstation-fin.com` e `rdstation-security.com`, que NÃO são domínios da RD Station (o verdadeiro é rdstation.com.br). Cheiro de golpe de cobrança. Confira antes de confirmar.", 10, PENDENTE),
    ("Marketing/Samira", "Marketing", "Marketing tratado pela Samira.", 2, PENDENTE),
    # ------------------------------------------------- plataformas
    ("Softwares|Apps", "Softwares|Apps", "Pasta-mãe das plataformas. Praticamente vazia: cada serviço tem a sua filha.", 1, PENDENTE),
    ("Softwares|Apps/Docusign", "Softwares|Apps", "DocuSign, TODO o tráfego de envelope (399 conversas). ⚠️ Se sobrepõe a `Waivers`: aqui é o envelope em geral, lá é a waiver do cliente. Vale decidir qual manda.", 399, PENDENTE),
    ("Softwares|Apps/Ecwid", "Softwares|Apps", "Ecwid (loja): relatório semanal e avisos da plataforma.", 322, PENDENTE),
    ("Softwares|Apps/Dialpad", "Softwares|Apps", "Dialpad: recado de voz e aviso de login. É por aqui que chega ligação perdida de cliente.", 173, PENDENTE),
    ("Softwares|Apps/GitHub", "Softwares|Apps", "GitHub: falha de execução, aviso de segurança e app conectado à conta.", 28, PENDENTE),
    ("Softwares|Apps/LinkedLn", "Softwares|Apps", "LinkedIn: vaga publicada e candidatura recebida.", 8, PENDENTE),
    ("Softwares|Apps/Zoho", "Softwares|Apps", "Zoho: conta, MFA e cobrança.", 3, PENDENTE),
    ("Simplybook", "Simplybook", "Simplybook (agenda): reserva nova, alteração, lembrete e cancelamento de sessão.", 85, PENDENTE),
    ("Simplybook/Order", "Simplybook", "Simplybook: o pedido em si — reserva confirmada e pedido que falhou.", 5, PENDENTE),
    ("subscriptions", "subscriptions", "Assinatura de serviço: Supabase, Heroku, Salesforce — cobrança, aviso e pausa de projeto.", 6, PENDENTE),
    ("Eduardo", "Equipe", "O que o Eduardo tratou no atendimento.", 95, PENDENTE),
    ("Eduardo/n8n", "Equipe", "n8n: recibo do Paddle, aviso da plataforma e workflow desativado.", 14, PENDENTE),
    ("Tests", "Tests", "Mensagem de teste (formulário do site, projeto de teste). Não é trabalho real.", 22, PENDENTE),
    # ------------------------------------------------- histórico de quem saiu
    ("Ex-Funcionários", "Ex-Funcionários", "Pasta-mãe do histórico de quem já saiu. Vazia: as conversas vivem nas filhas.", 0, PENDENTE),
    ("Ex-Funcionários/Jeyson Herrera", "Ex-Funcionários", "Atendimento que o Jeyson tratou (Summer Camp, boas-vindas).", 247, PENDENTE),
    ("Ex-Funcionários/George | Atendente", "Ex-Funcionários", "⚠️ O nome diz atendente, mas o conteúdo é o 'Relatório Kommo - Leads Diários' que o Samuel (Cygnus) mandava todo dia. Não é conversa de cliente. Confira.", 227, PENDENTE),
    ("Ex-Funcionários/Lara", "Ex-Funcionários", "Atendimento que a Lara tratou (lead, boas-vindas, primeira sessão).", 185, PENDENTE),
    ("Ex-Funcionários/MANU", "Ex-Funcionários", "O que a Manu tratou — inclui a experiência no Airbnb e confirmação de piloto.", 178, PENDENTE),
    ("Ex-Funcionários/Carolina Salinovic", "Ex-Funcionários", "O que a Carolina tratou — muito pedido de macacão.", 164, PENDENTE),
    ("Ex-Funcionários/Mariana", "Ex-Funcionários", "O que a Mariana tratou — imprensa, direito de imagem, documento.", 114, PENDENTE),
    ("Ex-Funcionários/Nathalia (MKT)", "Ex-Funcionários", "Marketing da Nathalia: parceria, mídia e rotina de tarefas.", 8, PENDENTE),
    ("Ex-Funcionários/Thiers", "Ex-Funcionários", "O que o Thiers tratou — lead do site e recado de voz.", 5, PENDENTE),
    ("Ex-Funcionários/Felipe", "Ex-Funcionários", "O que o Felipe tratou — corrida, mapa de pista, recado de voz.", 4, PENDENTE),
    ("Ex-Funcionários/Paula", "Ex-Funcionários", "O que a Paula tratou — boas-vindas e primeira ida à pista.", 2, PENDENTE),
]


def por_nome_support():
    return {n: (f, q, t, e) for n, f, q, t, e in MANUAL_SUPPORT}
