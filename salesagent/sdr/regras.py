"""Diretivas do SDR — a parametrização inteira num lugar só.

O Chase volta como SDR (D-2026-09-25). Estas são as regras que decidem, para
cada mensagem que chega no Kommo:

  1. se ela é lead ou não (e onde o card fica: Urace, a página 1, ou
     Comercial, a página 2);
  2. se o robô responde, cala ou chama uma pessoa — antes do modelo.

Mudar política de atendimento = mudar este arquivo. A lógica (classificador,
triagem, roteador, funil) não precisa ser tocada. Os testes em
salesagent/tests/test_sdr.py travam o comportamento.

Texto dos termos: minúsculo e sem acento (o classificador normaliza antes).
"""

VERSAO = "3.0.0"

# ---------------------------------------------------------------- canais
# Todos os canais continuam recebendo normalmente. As listas só dizem onde o
# robô pode responder sozinho.
CANAIS_CONHECIDOS = ["whatsapp", "instagram", "messenger", "telegram", "site", "email", "telefone"]

# Canais onde a equipe já tem quem responda: o agente de IA do Kommo
# ("Agente qualificador de leads"), sempre ligado por decisão do dono em
# 28/09, e os bots da equipe (relatório Meta e Kommo de 25/09/2026). Um
# segundo robô ali responderia em dobro ao mesmo lead: o SDR só organiza e
# chama gente. Tirar um canal daqui é decisão do dono.
CANAIS_COM_BOT_DA_EQUIPE = ["instagram", "messenger", "whatsapp", "site"]
CANAIS_COM_ROBO = [c for c in ["whatsapp", "instagram", "messenger", "telegram", "site"]
                   if c not in CANAIS_COM_BOT_DA_EQUIPE]

# Janela de 24 h da Meta: 24 h depois da última mensagem do lead não existe
# mensagem livre no Instagram, no Messenger nem no WhatsApp (só modelo
# aprovado). Follow-up automático só vale dentro dela.
CANAIS_JANELA_24H = ["whatsapp", "instagram", "messenger"]
JANELA_MENSAGEM_LIVRE_HORAS = 24

# ---------------------------------------------------------------- zonas
# Duas páginas no Kommo, que já são da equipe (desenho do time de vendas,
# relatório de 25/09/2026):
#   ENTRADA   = funil Urace. Recebe tudo na etapa First Contact.
#   COMERCIAL = funil Comercial. Só lead, a partir de ENTRADA.
# Quem sobe o card novo de uma página para a outra são as regras do próprio
# Kommo, já no ar em Urace > First Contact:
#   REGRA 1  sem Meta_Ads / Website / Ads Forms / nao_e_lead, +5 min: tag DM
#   REGRA 2  com DM / Meta_Ads / Ads Forms / Website, +10 min: Comercial > ENTRADA
# O SDR complementa, não duplica: marca nao_e_lead no lixo antes dos 5 min
# (para a REGRA 1 não carimbar DM nele), resgata conversa antiga que volta
# com sinal comercial e cuida do card depois que ele chegou ao Comercial.
ENTRADA = "Entrada"
COMERCIAL = "Comercial"

FUNIS = {ENTRADA: "Urace", COMERCIAL: "Comercial"}

# Na página 1 o card fica onde a REGRA 1/2 espera por ele: First Contact. O
# que separa lixo de lead ali é a tag nao_e_lead, não a etapa.
ETAPAS_ENTRADA = {
    "TRIAGEM": "First Contact",
    "AGUARDANDO_CONTEXTO": "First Contact",
    "SEM_SINAL": "First Contact",
    "AUTOMATICO": "First Contact",
    "RUIDO": "First Contact",
    "NAO_CONTATAR": "PERDIDO",  # fechamento nativo 143 + tag opt_out
}

# Página 2. Depois de ENTRADA quem move é o vendedor; o SDR só avança
# (nunca devolve card para etapa anterior).
ETAPAS_COMERCIAL = {
    "NOVO": "ENTRADA",
    "QUALIFICANDO": "ENTRADA",
    "HUMANO": "ATENDIMENTO",
    "ETAPA1": "QUALIFICADO",
    "ETAPA2": "QUALIFICADO",
    "CONFIRMADA": "GANHO",  # fechamento nativo 142
    "PERDIDO": "PERDIDO / NÃO QUALIFICADO",
}

# Etapas da página 1 onde conversa antiga fica enterrada (107 DMs em 60 dias
# foram parar em Cold Leads). Mensagem nova com sinal comercial num card
# daqui sobe para Comercial > ENTRADA. Nas demais etapas da Urace (Hot Leads,
# Closing the sale...) a equipe está trabalhando: o SDR não mexe.
ETAPAS_RESGATE = ["Cold Leads", "Follow Up 1"]

# ---------------------------------------------------------------- Kommo
# O SDR não cria funil nem etapa: tudo aponta para etapas que a equipe usa.
STATUS_GANHO = 142
STATUS_PERDIDO = 143

# Tags de origem que a REGRA 1 da equipe usa. Card que o SDR sobe para o
# Comercial sem nenhuma delas ganha DM, como a REGRA 1 faria.
TAGS_DE_ORIGEM = ["DM", "Meta_Ads", "Website", "Ads Forms"]
TAG_SEM_ORIGEM = "DM"

# Convenções de tag que a equipe já usa no Kommo.
TAGS_POR_MOTIVO = {
    "MENSAGEM_AUTOMATICA": ["nao_e_lead"],
    "SPAM_OU_OFERTA": ["nao_e_lead"],
    "CONTATO_INTERNO": ["nao_e_lead"],
    "OPT_OUT": ["opt_out"],
    "PEDIDO_HUMANO": ["Quer atendimento"],
}
TAG_ROBO_SILENCIADO = "sdr:bot-silenciado"

# nao_e_lead tira o card da REGRA 1 para sempre. Por isso o SDR só marca a
# partir do nome do lead criado (assunto de e-mail de sistema) ou de mensagem
# de e-mail. Numa conversa de chat (Instagram, WhatsApp, site) uma frase com
# cara de código não pode tirar uma pessoa do funil: ali fica só
# sdr:automatico no log (teste ponta a ponta de 28/09).
TAG_NAO_LEAD = "nao_e_lead"
CANAIS_QUE_MARCAM_NAO_LEAD = ["email"]

# A REGRA 2 da equipe sobe o card +10 min depois de ele nascer em First
# Contact. O SDR só segura o card para ela nessa janela, com folga. Card mais
# velho em First Contact (movido para lá, ou que já estava) não recebe a
# REGRA 2 (teste de 28/09: 32 min parado); com sinal comercial, o SDR sobe
# ele mesmo para Comercial > ENTRADA, com a tag DM que a REGRA 1 daria.
JANELA_REGRA_2_MINUTOS = 15

# ---------------------------------------------------------------- ações
CRIAR = "criar_card"          # contato sem card: nasce direto na zona Comercial
PROMOVER = "promover_card"    # card da Entrada passa para a zona Comercial
ANEXAR = "anexar_card"        # já está na zona Comercial: só registra
REABRIR = "reabrir_card"      # fechado há pouco, voltou com sinal
FICA = "somente_conversa"     # fica na Entrada
IGNORAR = "ignorar"           # ruído estrutural (grupo, interno)
ACOES_NO_COMERCIAL = [CRIAR, PROMOVER, ANEXAR, REABRIR]

# ---------------------------------------------------------------- atendimento
# Uma pessoa no comercial: sem rodízio. Só prioridade alta interrompe; o
# resto vira fila de tarefas.
ATENDIMENTO = {
    "pessoas_no_comercial": 1,
    "atribuicao": "responsavel_unico",
    "interrompe_somente": "alta",
}

# ---------------------------------------------------------------- motivos
MOTIVOS_ENTRADA = {
    "RESERVA_ETAPA1": "Reserva iniciada no site (Pit ID gerado).",
    "RESERVA_ETAPA2": "Driver Briefing concluído (Etapa 2).",
    "RESERVA_PARADA": "Reserva na Etapa 1 parada além do SLA.",
    "FORMULARIO_SITE": "Formulário do site preenchido com contato.",
    "CHAMADA_PERDIDA": "Chamada perdida de número desconhecido.",
    "INTENCAO_COMERCIAL": "Sinal comercial explícito (preço, agenda, contratação).",
    "PEDIDO_HUMANO": "Lead pediu falar com uma pessoa.",
    "DEMANDA_CORPORATIVA": "Demanda corporativa, evento ou grupo.",
    "TEMA_SENSIVEL": "Tema sensível que exige dono humano.",
    "SCORE_QUALIFICACAO": "Soma de sinais atingiu o limiar de qualificação.",
    "DADOS_QUALIFICACAO": "Lead informou serviço, data e contato.",
    "PIT_ID_INFORMADO": "Lead informou um Pit ID.",
}

MOTIVOS_NAO_ENTRADA = {
    "CONTATO_INTERNO": "Contato interno ou teste da equipe.",
    "GRUPO_OU_TRANSMISSAO": "Grupo ou lista de transmissão.",
    "MENSAGEM_AUTOMATICA": "E-mail automático, código de verificação ou notificação de sistema.",
    "SPAM_OU_OFERTA": "Spam, prospecção de fornecedor ou currículo.",
    "OPT_OUT": "Lead pediu para não receber mensagens.",
    "SAUDACAO_ISOLADA": "Apenas saudação, sem intenção declarada.",
    "AGRADECIMENTO_OU_ENCERRAMENTO": "Agradecimento, confirmação ou encerramento.",
    "MIDIA_SEM_CONTEXTO": "Áudio, imagem ou figurinha sem texto útil.",
    "SEM_SINAL_COMERCIAL": "Conversa sem sinal comercial suficiente.",
    "CARD_ABERTO_EXISTENTE": "Contato já está na zona Comercial (sem duplicar).",
}

MOTIVOS_ESCALONAMENTO = {
    "SINAL_CONVERSAO": "Lead sinalizou que quer avançar; não espera formulário.",
    "PILOTO_COMPETIDOR": "Piloto que compete atualmente (classificação D).",
    "PEDIDO_HUMANO": "Lead pediu atendimento humano.",
    "TEMA_SENSIVEL": "Tema sensível (jurídico, saúde, cobrança, imprensa).",
    "LEAD_INSATISFEITO": "Lead demonstrou irritação ou insatisfação.",
    "NEGOCIACAO": "Pedido de desconto ou condição comercial especial.",
    "CORPORATIVO": "Demanda corporativa, evento ou grupo grande.",
}

# Prioridade de cada escalonamento. Alta interrompe a pessoa; média vira fila.
PRIORIDADE_ESCALONAMENTO = {
    "SINAL_CONVERSAO": "alta",
    "PILOTO_COMPETIDOR": "alta",
    "PEDIDO_HUMANO": "alta",
    "TEMA_SENSIVEL": "alta",
    "LEAD_INSATISFEITO": "alta",
    "NEGOCIACAO": "media",
    "CORPORATIVO": "media",
}

# ---------------------------------------------------------------- palavras
PALAVRAS = {
    "preco": [
        "preco", "precos", "valor", "valores", "quanto custa", "quanto fica", "quanto sai",
        "orcamento", "tabela de preco", "pacote", "pacotes",
        "price", "prices", "pricing", "how much", "cost", "costs", "rates",
        "precio", "cuanto cuesta", "cuanto vale",
    ],
    "agenda": [
        "agenda", "agendar", "disponibilidade", "disponivel", "disponiveis", "vaga", "vagas",
        "reservar", "reserva para", "marcar", "horario disponivel", "tem data", "que dias",
        "book", "booking", "schedule", "availability", "available",
        "reservar", "disponibilidad",
    ],
    "contratacao": [
        "quero contratar", "quero agendar", "quero reservar", "como faco para",
        "como contrato", "como reservo", "gostaria de agendar", "gostaria de contratar",
        "quero marcar", "quero fazer", "inscricao", "inscrever", "matricula",
        "i want to book", "i would like to book", "sign up", "enroll", "register",
    ],
    # Só termos de interesse em programa. Palavras genéricas do negócio
    # ("kart", "pista", "piloto") ficam de fora: sozinhas não são sinal.
    "servico": [
        "arrive and drive", "1-day", "one day", "1 day", "academy", "training camp",
        "summer camp", "lead and follow", "lead & follow", "coaching", "professional coaching",
        "trackside", "treino", "treinamento", "aula", "aulas", "instrutor", "lessons",
    ],
    "informacao": [
        "como funciona", "o que e", "quanto tempo", "duracao", "onde fica", "endereco",
        "localizacao", "idade minima", "requisito", "requisitos", "precisa levar",
        "o que preciso", "how does it work", "where are you", "what age",
    ],
    "humano": [
        "falar com alguem", "falar com uma pessoa", "atendente", "atendimento humano", "humano",
        "me liga", "me ligue", "quero falar com", "talk to someone", "talk to a human",
        "real person", "call me", "speak to someone", "hablar con alguien",
    ],
    "desconto": [
        "desconto", "cupom", "condicao especial", "parcelar", "parcelamento", "mais barato",
        "discount", "coupon", "promo code", "cheaper", "descuento",
    ],
    "corporativo": [
        "empresa", "corporativo", "cnpj", "team building", "confraternizacao",
        "patrocinio", "corporate", "company event", "sponsorship",
    ],
    "sensivel": [
        "acidente", "lesao", "machuquei", "ambulancia", "advogado", "juridico",
        "processo judicial", "reembolso", "estorno", "cobranca indevida", "cobrado duas vezes",
        "jornalista", "imprensa", "reportagem", "injury", "injured", "lawyer", "refund",
        "chargeback", "charged twice", "journalist", "press",
    ],
    "spam": [
        "divulgacao", "trafego pago", "marketing digital", "seguidores", "impulsionar",
        "emprestimo", "consorcio", "investimento garantido", "cripto", "bitcoin",
        "curriculo", "vaga de emprego", "trabalhe conosco", "sou representante",
        "nossa empresa oferece", "parceria de divulgacao", "planos de internet",
        "paid partnership", "collaborate with your brand", "grow your followers", "seo services",
        "we manufacture", "racewear manufacturer", "manufacturer of", "suits manufacturer",
    ],
    # Mensagens de máquina: códigos, confirmações de cadastro, notificações,
    # newsletters. Checado antes de opt-out: rodapé de newsletter traz
    # "unsubscribe" e não é o lead pedindo para sair.
    "automatico": [
        "codigo de verificacao", "codigo de confirmacao", "codigo de acesso", "seu codigo e",
        "seu codigo de", "verification code", "your code is", "security code", "one-time code",
        "one time password", "nao responda este e-mail", "nao responda a este e-mail",
        "do not reply", "please do not reply", "this is an automated", "mensagem automatica",
        "e-mail automatico", "confirme seu e-mail", "confirme seu email", "confirm your email",
        "verify your email", "redefinir sua senha", "reset your password", "new sign-in",
        "novo acesso a sua conta", "view this email in your browser", "you are receiving this email",
        # Vistos no Kommo da URACE marcados à mão como nao_e_lead.
        "is your code", "your code to log in", "verify a new device", "senha de acesso foi alterada",
        "sua senha foi alterada", "periodo de avaliacao expirou", "validacao de email",
        # Cards do Inbox de e-mail listados no relatório de 25/09 (37 em 60
        # dias, nenhum era lead).
        "seu codigo para", "codigo para fazer login", "alerta de seguranca", "security alert",
        "personal access token", "reconnect your", "new notifications", "new seller message",
        # Vistos no Kommo em 28/09 (Urace > Cold Leads, 120 leads mais recentes).
        "novas notificacoes", "e-mail de recuperacao", "email de recuperacao", "recovery email",
    ],
    "opt_out": [
        "nao quero mais receber", "nao quero mais mensagem", "pare de mandar", "parem de mandar",
        "sair da lista", "descadastrar", "remover meu numero", "unsubscribe", "stop messaging",
        "stop texting", "remove me", "do not contact",
    ],
    "saudacao": [
        "oi", "ola", "opa", "eai", "e ai", "bom dia", "boa tarde", "boa noite", "tudo bem",
        "hello", "hi", "hey", "hola", "buenas",
    ],
    "encerramento": [
        "obrigado", "obrigada", "valeu", "agradecido", "ok", "okay", "blz", "beleza",
        "entendi", "perfeito", "show", "thanks", "thank you", "gracias", "great", "perfect",
    ],
    # Sinal de conversão: escala na hora, mesmo com dado faltando (cenário 19
    # do Chase: lead convertendo nunca espera atrás de pergunta de formulário).
    "conversao": [
        "quero fechar", "vamos fechar", "pode fechar", "quando pode comecar",
        "quando ele comeca", "quando podemos comecar", "como faco o pagamento",
        "como pago", "manda o link", "me manda o link", "fechado entao",
        "lets do it", "let s do it", "let's do it", "when can he start", "when can she start",
        "when can we start", "we want to move forward", "move forward", "sign me up",
        "how do i pay",
    ],
    # Piloto que compete hoje (classificação D): escalação imposta (G2).
    "compete": [
        "compito", "corro atualmente", "estou competindo", "piloto federado",
        "i compete", "currently racing", "we race in", "he races in", "she races in",
        "skusa", "rotax series", "florida winter tour", "rok cup",
    ],
    "insatisfacao": [
        "pessimo", "absurdo", "ridiculo", "descaso", "ninguem responde", "ate agora nada",
        "cansei", "horrivel", "ja pedi", "terrible", "ridiculous", "no one answers",
        "still waiting",
    ],
}

# Classificação de experiência (C1 do Chase): vem antes de qualquer valor.
CLASSIFICACAO_EXPERIENCIA = {
    "A": "nunca andou de kart",
    "B": "já andou de kart de aluguel",
    "C": "já correu kart de competição no passado",
    "D": "compete atualmente",
}
PROSA_CLASSIFICACAO = [
    ("D", ["compito", "corro atualmente", "estou competindo", "i compete", "currently racing"]),
    ("C", ["ja corri", "ja competi", "corria antes", "parei de correr", "i used to race", "raced before"]),
    ("B", ["kart de aluguel", "kart indoor", "rental kart", "rental karts", "go kart", "ja andei de kart"]),
    ("A", ["nunca andei", "nunca pilotei", "primeira vez", "never driven", "first time", "never raced"]),
]

# ---------------------------------------------------------------- pontuação
PESOS = {
    "conversao": 40, "compete": 40, "preco": 40, "agenda": 40, "contratacao": 40,
    "humano": 40, "corporativo": 30, "pit_id": 30, "servico": 20, "informacao": 20,
    "classificacao": 20, "data": 15, "pilotos": 15, "contato": 15,
}
# Sinais que sozinhos já levam à zona Comercial.
GATILHOS_DIRETOS = ["preco", "agenda", "contratacao", "humano", "corporativo", "conversao", "compete"]
# Soma mínima de sinais fracos sem gatilho direto.
LIMIAR = 40
JANELA_REABERTURA_DIAS = 30
GRUPO_LIMITE_PILOTOS = 4

# ---------------------------------------------------------------- estilo
# Aplicado à resposta do modelo antes de sair para o lead.
ESTILO = {
    "max_mensagens": 2,
    "max_caracteres": 350,
    "emoji": False,       # o manual do Chase proíbe emoji com o lead
    "travessao": False,   # travessão denuncia texto de IA
}

# Frases que nunca saem. Cada uma custou um incidente real no Chase.
NUNCA_DIZER = [
    ("all-inclusive", "driver pass e pit pass são pagos direto à pista, nunca inclusos"),
    ("all inclusive", "driver pass e pit pass são pagos direto à pista, nunca inclusos"),
    ("tudo incluso", "driver pass e pit pass são pagos direto à pista, nunca inclusos"),
    ("come by", "todo serviço é por agendamento"),
    ("stop by", "todo serviço é por agendamento"),
    ("drop by", "todo serviço é por agendamento"),
    ("passe por aqui", "todo serviço é por agendamento"),
    ("apareca quando quiser", "todo serviço é por agendamento"),
    ("reserva confirmada", "reserva só é confirmada depois do pagamento compensar"),
    ("your booking is confirmed", "reserva só é confirmada depois do pagamento compensar"),
    ("vandalismo", "explicar o depósito de forma simples e neutra"),
    ("vandalism", "explicar o depósito de forma simples e neutra"),
    ("garanto sua vaga", "não prometer disponibilidade"),
    ("guarantee your spot", "não prometer disponibilidade"),
]

# ---------------------------------------------------------------- cadência
# Trilha 1 (C11 do Chase): +2h, +1 dia, +3 dias, +7 dias, fecha como perdido.
FOLLOW_UP_MINUTOS = [120, 1440, 4320, 10080]
# Nos canais da Meta a trilha cabe inteira na janela de 24 h contada da
# última mensagem do lead: +2 h e mais +20 h (22 h no total), e para.
FOLLOW_UP_MINUTOS_JANELA_24H = [120, 1200]
# Margem da ponte: toque de follow-up com a última mensagem do lead mais
# velha que isto não sai; vira tarefa para uma pessoa.
JANELA_24H_MARGEM_MINUTOS = 60
MAX_REALERTAS = 4
SLA_MINUTOS = {"alta": 5, "media": 15}

# Horário de atendimento humano. PENDENTE: o valor veio do arquivo do Chase e
# não vale como regra até ser reconfirmado (D-2026-08-31). A pista opera
# quarta a domingo, 8h-13h (Italo, atendimento real) — confirmar a janela
# de atendimento com o dono.
HORARIO = {
    "fuso": "America/New_York",
    "dias": [2, 3, 4, 5, 6],  # seg=0 ... dom=6 → quarta a domingo
    "inicio": 9,
    "fim": 18,
    "confirmacao_pendente": True,
}

# Remetentes de máquina: pelo nome antes do @ ou por subdomínio de sistema.
REMETENTES_AUTOMATICOS = (
    r"^(?:(?:no-?reply|do-?not-?reply|nao-?responda|notifications?|notificacoes|"
    r"mailer-daemon|postmaster|bounces?|mfa|news)(?:[+._-][^@]*)?@"
    r"|[^@]+@(?:[^@]*\.)?(?:notice|account|account-d|notifications?|support|[a-z0-9-]*-security)\.)"
)
