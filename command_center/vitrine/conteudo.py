"""O que o site novo diz, copiado do urace.us (#148; texto atualizado em 13/10/2026, #207).

Dono, 07/10: *"use todas as informações que ja temos no site"*; dono, 13/10 (#207): *"vou pegar o
copy que tá no site atual e jogar naquele outro site lá, o novo.urace.us"*. Nada aqui é inventado:
cada texto saiu da página citada ao lado, do jeito que está no urace.us de 13/10.

O que fica diferente do site atual, de propósito:
- endereço da pista com o Box 3 (decisão de 01/10, `docs/site-publico/decisoes-2026-10-01.md`);
- remarcação com **24 horas** de antecedência e a taxa de US$ 95 (dono, 08/10; o site atual ainda
  diz 48 h em parte das páginas);
- idade dos karts: a do produto (Baby 4–7, 4-stroke 7+, 2-stroke 7+, Adult Shifter 14+; dono, 08/10);
- o depoimento do Ken McKay sai sem a frase do pagamento da invoice (dado de cliente);
- o nome da marca sai sempre "URACE" (o site atual alterna Urace, URace e URrace);
- preço de serviço não é texto fixo: vem do sistema (`KARTS`, os planos do painel) ou não aparece.
"""

SITE = {
    "nome": "URACE",
    "slogan": "the Champion's Factory",
    "endereco": {"rua": "10724 Cosmonaut Blvd, Box 3", "cidade": "Orlando", "estado": "FL", "cep": "32824",
                 "pais": "US", "onde": "inside the Orlando Kart Center"},
    "telefone": "+1 (407) 250 2291",
    "telefone_e164": "+14072502291",
    "emails": ("support@urace.us", "urace@urace.us"),
    "redes": {
        "Instagram": "https://www.instagram.com/urace.us/",
        "Facebook": "https://www.facebook.com/Urace.us/",
        "TikTok": "https://www.tiktok.com/@urace.usa",
    },
    "whatsapp": "https://wa.me/14072502291?text=Hi!%20I%27d%20like%20to%20know%20more%20about%20karting%20at%20URACE.",
    "horario": "Open every day, 8 AM – 8 PM",
    # #252: o resto do LocalBusiness que o urace.us de hoje já publica (Yoast). Tudo isto vem de lá,
    # e sem isto a troca de domínio perderia o SEO local: mapa, cidade atendida, Yelp e TripAdvisor.
    # #254 (dono, 15/10): "o kart school se tornou Urace academy" — o nome alternativo que o Yoast
    # publicava passa a ser o nome novo, para o Google não ensinar o nome que acabou
    "outro_nome": "URACE Academy",
    "descricao_negocio": ("Kart racing school in Orlando, Florida. Arrive and drive days in real race karts, "
                          "professional coaching and a monthly kart academy, based at the Orlando Kart Center."),
    "faixa_preco": "$$$",
    "moeda": "USD",
    "geo": (28.4108348, -81.377619),
    "mapa": "https://www.google.com/maps/place/Urace+-+Kart+team+and+school/@28.4108348,-81.377619,17z",
    "atende": (("City", "Orlando"), ("City", "Kissimmee"), ("City", "Winter Garden"), ("State", "Florida")),
    "perfis": ("https://www.yelp.com/biz/urace-kart-school-orlando",
               "https://www.tripadvisor.com/Attraction_Review-g34515-d32848914-Reviews-Urace_Us_Kart_And_School-"
               "Orlando_Florida.html",
               "https://www.google.com/maps/place/Urace+-+Kart+team+and+school/@28.4108348,-81.377619,17z"),
}

# O site inteiro mora aqui (#164): nenhum link do menu volta ao WordPress.
ANTIGO = "https://urace.us"
# #207: os rótulos do menu do urace.us de 13/10, nos caminhos do site novo. "Events" (um submenu sem
# página própria) e o "Home" (o logo já leva à home) ficam de fora do topo.
MENU = (
    ("About URACE", "/about/"),
    ("Our Services", "/services/"),
    ("Plan Your Career", "/career/"),
    ("For Beginners", "/for-beginners/"),
    ("Sim 2 Grid", "/services/#sim2grid"),
    ("Arrive and Drive", "/services/arrive-and-drive/"),
    ("Academy", "/academy/"),
    ("Racing Team", "/pro-team/"),
    ("Store", "/store/"),
    ("Blog", "/blog/"),
    ("Contact us", "/contact/"),
)
# O rodapé do urace.us de 13/10 ("Navigation"); "Sponsors" não tem página no site novo.
RODAPE = (
    ("Home", "/"),
    ("Store", "/store/"),
    ("Our Services", "/services/"),
    ("About", "/about/"),
    ("Blog", "/blog/"),
    ("Contact Us", "/contact/"),
)

# ------------------------------------------------------------------ blocos comuns (FAQ das páginas de serviço)
TRACK = ("Orlando Kart Center’s 8/10 mile professional kart racing track is your textbook. A challenging circuit, the "
         "variety of corners is the ideal training ground. URACE is not the racetrack; we are a racing team that provides "
         "services to racers using a third-party track. We must adhere to their rules and operating hours. Both team "
         "members and drivers are required to pay admission fees to access the track.")

TERMOS = (
    "The program price is URACE’s fee for coaching and trackside support only. Track fees are not included: driver and "
    "guest passes are paid directly to the Orlando Kart Center, and the amount changes with the day. Extra guests must "
    "pay $15 each.",
    # idades: decisão do dono de 08/10 (o site atual ainda lista Micro/Mini 6–13 e Junior/Senior 11+)
    "There are different categories of kart available: Baby Kart (ages 4–7), 4-stroke (7+), 2-stroke (7+) and Adult "
    "Shifter (14+, experience required). The difference between 2t and 4t kart options is the performance. We recommend "
    "new entrants to the sport to start with the 4t options, and we can move the driver to the 2t option whenever we "
    "judge that the driver is capable of handling the 2t kart.",
    "This package consists of 3 or 6 sessions of 10 minutes each, 30 minutes or 1 hour of total track time, according to "
    "your choice. The scheduled arrival time at the track is 8 am. We kindly request that you arrive on time. If less "
    "than 75% track time is achieved, there is a possibility of receiving a proportional credit for a future session. "
    "Each case will be decided individually based on the reason for not meeting the minimum track time.",
    "To cover potential crash damage caused by the driver and track fees a $400 deposit will be charged in advance for "
    "security purposes, however this amount will be fully refunded at the end of the event in case of no "
    "incidents/damages to the kart.",
    "Any damages caused to the kart are not included in this price, regardless of the driver’s fault or not in the "
    "incident, and will be billed to you for the costs of repair. Clarifying: If the kart breaks down and it was not "
    "caused by the driver, (crash, going off of the track or aggressive driving style) the costs of repair will be "
    "covered by URACE. If the kart gets damaged in the result of a crash, regardless of driver’s fault in the incident, "
    "the costs of repair will be billed to you. Understanding why: each driver in a race track is fully liable for his "
    "own equipment and safety. Meaning, even if someone else crashes into you or your child, you are responsible for "
    "your and or child’s equipment. You are not responsible for the other person in the other kart, nor the other "
    "person’s equipment even if you or your child caused the incident.",
    "Kids under 10 years old must be accompanied by an adult. We provide a childcare assistant for extra $200 in case "
    "you are unable to stay with your child. This service must be requested beforehand.",
    "Racing is a high-risk activity. By booking this appointment you agree and acknowledge that URACE is not responsible "
    "for any injuries, damages, or losses of any nature that might happen to you, or your family during track "
    "activities or while on site.",
)

# Dono, 08/10: "24 horas com a taxa" (o site atual ainda diz 48 h).
REEMBOLSO = (
    "Our service requires planning, preparation, coordination and transportation to the track on our end, for those "
    "reasons we do not offer refunds. Rescheduling will be available with a minimum notice of 24h and potential costs "
    "of rearrangement.",
    "Rescheduling Policy: if a class is rescheduled with less than 24 hours’ notice, a flat fee of $95 will be charged. "
    "If a Driver Pass is required, it will be charged additionally.",
    "To avoid this fee, we recommend notifying us of any changes at least 24 hours in advance.",
)

HORARIO = ("We’re open every day, from 8 AM to 8 PM.",)

FAQ_COMUM = (
    ("The track", (TRACK,)),
    ("Terms and conditions", TERMOS),
    ("Refund policy", REEMBOLSO),
    ("Opening hours", HORARIO),
)

# Os termos de grupos e eventos (urace.us/services/, bloco "Birthday party / Corporate Events", e
# urace.us/plan-your-career/, bloco "Not on the ladder").
FAQ_EVENTO = (
    ("The track", ("Orlando Kart Center’s 8/10 mile professional kart racing track is your textbook. A challenging "
                   "circuit, the variety of corners is the ideal training ground.",
                   "URACE is not the racetrack; we are a racing team that provides services to racers and enthusiasts "
                   "using a third-party track. We must adhere to their rules and operating hours.")),
    ("Terms and conditions", ("Crashes or damages caused by the driver are not included in the price. The program listed "
                              "price is the URACE fee for kart rental and trackside support only. A deposit for "
                              "incidentals will be collected the day before the event. The deposit is refunded in case "
                              "of no incidents at the end of the event after deducting the 3.5% credit card processing fee.",
                              "Racing is a high-risk sports activity and environment. By booking this appointment, you "
                              "agree and acknowledge that URACE is not responsible for any injuries, damages, or losses "
                              "of any nature that may happen while on site.")),
    ("Refund policy", ("Our service requires planning, preparation, coordination and transportation to the track on our "
                       "end, for those reasons we cannot offer a refund. Rescheduling will be available with a minimum "
                       "of 24h notice.",
                       "Rescheduling policy. If a class is rescheduled with less than 24 hours’ notice: a flat fee of $95 "
                       "will be charged, and if a Driver Pass is required it will be charged additionally. To avoid this "
                       "fee, we recommend notifying us of any changes at least 24 hours in advance.",
                       "Please note that if a training session needs to be rescheduled due to circumstances outside of "
                       "URACE’s control, a fee will be charged to cover our costs of preparation. This fee will be "
                       "calculated based on the cost to reschedule the session and the amount of drivers involved. This "
                       "fee will be in addition to any other costs associated with the session itself. By using URACE’s "
                       "services, you agree to this policy and understand that rescheduling fees may apply in the event "
                       "of unforeseen circumstances.")),
)

# "What Our Clients Say" das páginas de serviço (o terceiro nome, "Christopher H.", não tem texto no
# site atual e fica de fora).
DEPOIMENTOS_EVENTOS = (
    ("Ivan P.", "My son’s birthday was a hit! The kids had the time of their lives, and everything was so well organized!"),
    ("Daniel M., Team Leader", "Best corporate outing we’ve done! Everyone’s still talking about it weeks later."),
)

# "Built by URACE": os depoimentos da home e do About, na ordem do site atual.
DEPOIMENTOS = (
    ("Ken McKay", None,
     "Hello Jeyson, My son Henryk and I enjoyed the experience. I was impressed with the business from mechanics to "
     "coaching. I wish my son would have not been so timid. He made a breakthrough in the last session; only wish we had "
     "another day or two. We will definitely keep an eye on the team and be interested in future training with the team. "
     "We are looking forward to Italo’s report. […] Thank you and all the best."),
    ("Leo Portnov", None, "Hi Jeyson, today was great. Italo is awesome. Sean is looking forward to tomorrow. Thanks for everything."),
    ("Aaron Benoit", "SKUSA X30",
     "I’ve had the pleasure of learning from Italo since I was a rookie. Through coaching, data review, and lead/follow "
     "sessions, my on track skills have improved significantly. Italo also does a great job helping with soft skills — "
     "kart set-up or driver promotion. Whether you’re an experienced driver or newbie, Italo’s personality and knowledge "
     "make URACE a great choice."),
    ("Zack Skolnick", "Serial Entrepreneur",
     "I’ve been around the racing industry for awhile now and very impressed with my URACE Suit! Not only is the quality "
     "of material top notch but so is Italo and his team’s customer service. To anyone looking for a custom suit, go talk "
     "to URACE!"),
    ("Steve Collins", None,
     "I have been impressed by the thoroughness Italo uses. He gives instruction and then sends the driver on track with a "
     "GoPro. He reviews the video turn by turn with the driver giving feedback. I’m seeing results. My son is improving "
     "while mastering the techniques to be safe and fast."),
)

SOBRE = ("Racing has been our passion for generations! Our kart racing story started 26+ years ago in Brazil. Team "
         "principal Italo Silveira began by racing karts, winning numerous Brazilian regional and national championships. "
         "A successful professional car racing career followed in the internationally recognized Brazilian stock car "
         "series. In 2016, Italo moved to Florida and launched URACE, a karting team, to pass along his extensive knowledge "
         "and passion to young drivers.")

GRUPOS = ("Team Up for a Turbo-Charged Experience! Bring your crew and get ready for an unforgettable adventure! Our "
          "high-speed racing kart experience is perfect for corporate events, birthday parties, and group outings. "
          "Challenge your colleagues or friends to a thrilling competition, reaching speeds of over 50mph on our "
          "professional-grade track. Our expert staff ensure a safe and enjoyable experience for all.")

FECHO_DUVIDAS = ("Do you still have questions?",
                 "Contact our team by clicking the button below to get all the information about our products and services.")

# ------------------------------------------------------------------ home (urace.us/)
HOME = {
    "titulo": "Kart Racing School & Driver Training in Orlando | URACE",
    "descricao": ("Learn real kart racing with professional coaching in Orlando. URACE develops beginners and competitive "
                  "drivers through its Kart Academy, coaching and race team."),
    "h1": "The Champions Factory",
    "sub": ("We are a race team in Orlando that runs its own drivers — simulator to grid. We do not sell seat time. We find "
            "where your tenths are, show you the trace, and tell you straight whether the next step is worth your money."),
    "foto": "home-hero.webp",
    "metodo": ("Five years old or fifty. Same method.",
               "A kid in a Baby Kart and a grown man in a Shifter get the same session: data pulled after every run, onboard "
               "gone through corner by corner, and a coach who names the two things costing you time — not twenty."),
    "eventos": ("Birthdays, Corporate Events, Groups & Social Gatherings",
                "Real race karts on a real circuit, run like a race weekend: practice, grid order, timed final, results on "
                "a sheet at the end. Nobody goes home arguing about who won."),
    "eventos_links": (("Birthdays", "/services/birthday-party/"), ("Corporate Events", "/services/corporate-events/"),
                      ("Groups & Social Gatherings", "/services/group-events/")),
    "escada": ("The ladder ends on our grid",
               "Sim 2 Grid. Arrive and Drive. URACE Academy. URACE Racing Team. Four steps, one team. Nobody skips to the "
               "top and nobody buys their way in — your coach tells you when you are ready, and not before."),
    "numeros": (("+300", "Drivers Trained by Italo and URACE Since 2004"),
                ("+500", "Race Wins Since 2004 by Drivers Trained by Italo and URACE")),
    # (nome, o que o site atual diz de cada um); Alexander Savage e Alexander Jacoby saem sem texto no site atual
    "campeoes": (("Enzo Vidmontiene", "Multi National race winner"),
                 ("Leonardo Escorpioni", "Multi National race winner - currently racing USF200 Pro"),
                 ("Emmo Fittipaldi", "Son of the three-time Formula 1 world champion Emerson Fittipaldi. He currently runs at Eurocup3."),
                 ("Alexander Savage", ""), ("Alexander Jacoby", "")),
    "fotos_campeoes": ("piloto-1.webp", "piloto-2.webp", "piloto-3.webp", "piloto-4.webp"),
    "treino": ("Our teaching method includes data analysis, onboard video study, and explanation of the theories "
               "involved in all the driving aspects we discuss. We ensure that drivers not only do what they are "
               "told to do, but also understand why they need to do it. We believe that understanding the process "
               "makes the difference.",
               "Personalized coaching with a dedicated professional coach, designed to accelerate driver development "
               "through structured training, advanced telemetry, technical analysis, and precise driving corrections. "
               "Each session focuses on building correct technique, consistency, and confidence on track. Ideal for "
               "drivers who want to train with purpose, evolve continuously, and reduce lap times with a "
               "high-performance approach."),
    # o preço do Arrive and Drive sai de KARTS (o mesmo da página e da reserva), não daqui
    "servicos": (
        {"nome": "Arrive and Drive", "texto": ("Taxes and fees not included. Track access fee (Orlando Kart Center) is "
                                               "required and separate from this price. Rescheduling: requests made at least "
                                               "24 hours before your session will be accommodated based on availability. "
                                               "Sessions missed without notice may be forfeited."),
         "link": "/services/arrive-and-drive/", "preco_kart": True},
        {"nome": "Professional Team", "texto": ("The only team that is capable of helping beginners to get to the top in one "
                                                 "season, our professional driver development program includes data analysis. "
                                                 "Our teaching method includes data analysis, on-board video study and "
                                                 "explanation of the theories involved in all the driving aspects we discuss."),
         "link": "/pro-team/"},
        {"nome": "Group events", "texto": GRUPOS, "link": "/services/group-events/"},
    ),
    "depoimentos_titulo": "Built by URACE",
    "depoimentos_sub": "Check out testimonials from parents and drivers",
    "depoimentos": DEPOIMENTOS,
    "sobre": SOBRE,
    "blog_titulo": "Our Contents",
    "blog_sub": "Check out the blog:",
    "fecho": FECHO_DUVIDAS,
}

# ------------------------------------- Arrive and Drive (urace.us/services/arrive-and-drive/ e o produto 4787)
# #254 (dono, 15/10): *"o professional coaching se tornou o arrive and drive"* — o texto que fazia sentido da
# página /services/professional-coaching/ entrou aqui; a página antiga virou 301 para esta.
# Preços e idades: as variações do produto 4787 que o site público mostra (Store API pública).
# A "Your Own Kart" ($500) existe no WooCommerce mas não aparece no site, então também não aparece aqui.
#
# #263 (dono, 15/10): `nome` é a **chave do kart**. É ela que viaja no `?kart=` da reserva e é ela
# que o painel guarda em `booking_services.site_kart` para dizer "este serviço é deste kart". O site
# casa serviço e kart por essa chave, igual e exata — nunca por "o nome do serviço contém o nome do
# kart", que foi o que fez um serviço chamado "teste" aparecer como se fosse o produto.
# Trocar o nome de um kart aqui é trocar a chave: o `site_kart` dos serviços muda no mesmo passo
# (`test_servico_do_kart.py` tranca).
KARTS = (
    {"nome": "Baby Kart", "idade": "Ages 4–7", "min": 4, "max": 7, "preco": 719},
    {"nome": "4-stroke", "idade": "Ages 7+", "min": 7, "max": None, "preco": 719},
    {"nome": "2-stroke", "idade": "Ages 7+", "min": 7, "max": None, "preco": 819},
    {"nome": "Adult Shifter", "idade": "Ages 14+, experience required", "min": 14, "max": None, "preco": 899},
)

ARRIVE = {
    "caminho": "/services/arrive-and-drive/",
    "titulo": "Arrive and Drive Kart Racing in Orlando | URACE",
    "descricao": ("Drive a real racing kart in Orlando. Kart, safety gear and professional coaching included - bring "
                  "nothing. No licence needed. Book your session."),
    "eyebrow": "Kart Arrive and Drive in Orlando",
    "h1": "Live the real Kart Racing Experience in Orlando",
    "sub": ("Feel the speed, control the kart, and enjoy a full track day with professional equipment and coaching — "
            "with video and data analysis to sharpen your technique. No license required."),
    "foto": "arrive-and-drive-hero.webp",
    "foto_equipe": "arrive-and-drive-equipe.webp",
    # #254: os quatro últimos vêm do "What to expect from your Coaching Session" da página de
    # Professional Coaching, que se fundiu aqui (dono, 15/10).
    "esperar": ("Feel the rush of real speed. Up to 70 MPH on a pro racing track",
                "Get race-ready with a safety + driving technique briefing from expert coaches",
                "Suit up and strap in: this isn’t a theme park ride, it’s the real thing",
                "Create unforgettable memories for families, friends, and adrenaline junkies alike",
                "Walk away buzzing with adrenaline, confidence, and maybe a new obsession",
                "A training program tailored to the driver’s level",
                "Professional coaching, data and video analysis",
                "Technique and mindset training",
                "Performance tracking, session after session"),
    "fornece": ("The high performance go-kart", "Safety instructions", "Safety equipment.",
                "Expert coaching from professional instructors"),
    "trazer": ("MUST wear long pants, closed toe shoes and a jacket.", "Make a reservation",
               "Come prepared for fun and leave with lasting smiles"),
    "porque": ("Real Racing Karts – Not slow rental karts.", "Feel Like a Racer - This is the real deal.",
               "Just Arrive & Drive – No prep, no hassle.", "Pro-Level Track",
               "Gear up, get briefed, go fast – We handle everything.",
               # #254: do "Real coaching from a championship-level kart team" da página de coaching
               "Theory and mechanics simplified", "Mentorship by winning drivers",
               "Confidence, reflexes and racing mindset"),
    "porque_fecho": "Ready to feel what real racing is like? Spots are limited.",
    "quem": ("Adults and kids looking for real speed", "Racing fans visiting Orlando", "Families seeking next-level fun",
             "First-timers curious about karting",
             # #254: a página de coaching era para quem já corre
             "Drivers who already race and want to find real lap time",
             "Drivers aiming for confidence, speed and race results"),
    # os 3 primeiros passos são os da reserva do site (agenda e área do cliente); o resto é o texto do site atual
    # #262 (dono, 15/10): um caminho só — carrinho → conta → Stripe → waiver. Nada de invoice no site.
    "passos": ("Pick your kart, your day and morning or afternoon, and add it to your cart",
               "Sign in or create your account and add your drivers",
               "Tell us if you want Lead and Follow — a coach on track with you — and we add it to your session",
               "Pay with Stripe (card, Apple Pay or Google Pay) and sign the driver’s waiver in your account — "
               "your spot is confirmed",
               "Arrive 10 minutes early. Check in, get settled, feel the excitement building.",
               "Gear up + Safety Briefing",
               "Hit the track. Time to feel the speed, the grip, the thrill — like a real racer.",
               "Enjoy the speed and excitement. It’s just the beginning!",
               "Schedule your next race. Already hooked? Let’s get your next session booked and keep the adrenaline going!"),
    "faq": (
        ("The experience",
         ("Are you visiting Orlando and looking for something more exciting than the go karts at Magic Kingdom’s "
          "Tomorrowland Speedway or the monotony of Epcot’s Test Track? This experience is for kids and adults, all ages "
          "are welcome!",
          "Book your reservation and be ready to have a blast!",
          "These are not the typical put-put go-karts, they are authentic, professional racing karts.",
          "We will start by providing safety and driving technique instructions, after the first instructions you will have "
          "3 or 6 10 minutes driving sessions, according to your choice. The experience total time, will be around 2h for "
          "3 sessions and 4-5 h for 6 sessions from arrival until the end.",
          "Available Experience Days: Experiences are available every day, 8 AM – 8 PM. Please confirm availability when "
          "booking.")),
        # #254: o que a página de Professional Coaching dizia; o preço do Lead and Follow é o da Rate Card
        # (fechado com antecedência, $769 por piloto; pacote de 5 sessões, $3,460.50).
        ("Coaching, data and Lead and Follow",
         ("Our teaching method includes data analysis, on-board video study and explanation of the theories involved in "
          "all the driving aspects we discuss: the driver leaves knowing what to change, not only how fast they went.",
          "Lead and Follow is an additional fee for a partner trainer to make your driving or training experience more "
          "exciting, if you don’t wanna do it alone. Booked in advance it is $769 per driver, and a package of five "
          "sessions is $3,460.50.",
          "All weekday training sessions must be confirmed by Sunday. All weekend sessions must be confirmed 24h in "
          "advance. Please call if you have any questions.")),
        ("Track fees (paid to the Orlando Kart Center)",
         ("Driver pass Wednesday to Friday $100–230.", "Driver pass Saturday and Sunday $100–125.",
          "Spectator pass any day $22.")),
        *FAQ_COMUM,
    ),
    "depoimentos": DEPOIMENTOS_EVENTOS,
    "fecho": "If you're serious about racing, this is where it starts. Shall we begin?",
    "fecho_sub": "With an affordable price aimed at the democratization of Karting.",
}


def preco_minimo():
    return min(k["preco"] for k in KARTS)


def chaves_dos_karts():
    """As chaves dos karts do site, na ordem da página (`booking_services.site_kart`)."""
    return tuple(k["nome"] for k in KARTS)


def kart_da_chave(chave):
    """O kart do site com essa chave, sem distinguir maiúscula nem espaço à toa. None se não é kart."""
    c = " ".join(str(chave or "").split()).lower()
    return next((k for k in KARTS if k["nome"].lower() == c), None)
