"""O que o site novo diz, copiado do urace.us de 07/10/2026 (#148).

Dono, 07/10: *"use todas as informações que ja temos no site"* e, sobre o preço,
*"mantenha como esta no site publico hoje"*. Nada aqui é inventado: cada texto saiu da
página citada ao lado, e os preços são os das variações do WooCommerce naquele dia.

Correções de propósito (registradas na PR):
- endereço da pista com o Box 3 (decisão de 01/10, `docs/site-publico/decisoes-2026-10-01.md`);
- o depoimento do Ken McKay sai sem a frase do pagamento da invoice (dado de cliente).
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
}

# Páginas que ainda não estão no site novo levam ao urace.us de hoje (etapas 2 a 4 do #148).
ANTIGO = "https://urace.us"
MENU = (
    ("Arrive and Drive", "/services/arrive-and-drive/"),
    ("Academy", ANTIGO + "/kart-training-packages/"),
    ("Events", ANTIGO + "/corporate-events/"),
    ("Pro Team", ANTIGO + "/professional-kart-team-racing-team/"),
    ("Store", ANTIGO + "/store/"),
    ("Blog", ANTIGO + "/blog/"),
    ("About", ANTIGO + "/about/"),
    ("Contact", ANTIGO + "/contact/"),
)

# ------------------------------------------------------------------ home (urace.us/)
HOME = {
    "titulo": "URACE | Drive a 70MPH Racing Kart in Orlando",
    "descricao": ("Real racing karts in Orlando for all ages starting at 5: Arrive and Drive sessions, "
                  "kart driver training and a professional racing team since 2004."),
    "h1": "Drive a 70MPH Racing Kart in Orlando",
    "sub": "(for all ages starting at 5)",
    "foto": "home-hero.webp",
    "numeros": (("+300", "Drivers trained by Italo and URACE since 2004"),
                ("+500", "Race wins since 2004 by drivers trained by Italo and URACE")),
    "campeoes": ("Enzo Vidmontiene", "Leonardo Escorpioni", "Emmo Fittipaldi", "Alexander Savage", "Alexander Jacoby"),
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
    "servicos": (
        {"nome": "Arrive and Drive", "texto": "Real racing karts for all ages and experience levels, on a pro track.",
         "link": "/services/arrive-and-drive/", "preco": "Starting at $719"},
        {"nome": "Professional Team", "texto": ("The only team that is capable of helping beginners to get to the top "
                                                 "in one season. Our professional driver development program includes "
                                                 "data analysis, on-board video study and explanation of the theories "
                                                 "involved in all the driving aspects we discuss."),
         "link": ANTIGO + "/professional-kart-team-racing-team/"},
        {"nome": "Group events", "texto": ("Bring your crew and get ready for an unforgettable adventure! Our high-speed "
                                            "racing kart experience is perfect for corporate events, birthday parties, "
                                            "and group outings."),
         "link": ANTIGO + "/corporate-events/"},
    ),
    "depoimentos": (
        ("Aaron Benoit", "SKUSA X30",
         "I’ve had the pleasure of learning from Italo since I was a rookie. Through coaching, data review, and "
         "lead/follow sessions, my on track skills have improved significantly. Italo also does a great job helping "
         "with soft skills — kart set-up or driver promotion. Whether you’re an experienced driver or newbie, Italo’s "
         "personality and knowledge make Urace a great choice."),
        ("Steve Collins", None,
         "I have been impressed by the thoroughness Italo uses. He gives instruction and then sends the driver on "
         "track with a GoPro. He reviews the video turn by turn with the driver giving feedback. I’m seeing results. "
         "My son is improving while mastering the techniques to be safe and fast."),
        ("Ken McKay", None,
         "My son Henryk and I enjoyed the experience. I was impressed with the business from mechanics to coaching. "
         "[…] We will definitely keep an eye on the team and be interested in future training with the team."),
        ("Leo Portnov", None, "Today was great. Italo is awesome. Sean is looking forward to tomorrow. Thanks for everything."),
        ("Zack Skolnick", "Serial Entrepreneur",
         "I’ve been around the racing industry for awhile now and very impressed with my URace Suit! Not only is the "
         "quality of material top notch but so is Italo and his team’s customer service. To anyone looking for a "
         "custom suit, go talk to URace!"),
    ),
    "sobre": ("Racing has been our passion for generations! Our kart racing story started 26+ years ago in Brazil. "
              "Team principal Italo Silveira began by racing karts, winning numerous Brazilian regional and national "
              "championships. A successful professional car racing career followed in the internationally recognized "
              "Brazilian stock car series. In 2016, Italo moved to Florida and launched Urace, a karting team, to pass "
              "along his extensive knowledge and passion to young drivers."),
}

# ------------------------------------- Arrive and Drive (urace.us/services/arrive-and-drive/ e o produto 4787)
# Preços e idades: as variações do produto 4787 que o site público mostra em 07/10 (Store API pública).
# A "Your Own Kart" ($500) existe no WooCommerce mas não aparece no site, então também não aparece aqui.
KARTS = (
    {"nome": "Baby Kart", "idade": "Ages 4–7", "min": 4, "max": 7, "preco": 719},
    {"nome": "4-stroke", "idade": "Ages 7+", "min": 7, "max": None, "preco": 719},
    {"nome": "2-stroke", "idade": "Ages 7+", "min": 7, "max": None, "preco": 819},
    {"nome": "Adult Shifter", "idade": "Ages 14+, experience required", "min": 14, "max": None, "preco": 899},
)

ARRIVE = {
    "caminho": "/services/arrive-and-drive/",
    "titulo": "Kart Arrive and Drive in Orlando | URACE",
    "descricao": ("Live the real kart racing experience in Orlando: real racing karts up to 70 MPH, safety briefing "
                  "and coaching, no license required. Pick your kart and book your day online."),
    "eyebrow": "Kart Arrive and Drive in Orlando",
    "h1": "Live the real Kart Racing Experience in Orlando",
    "sub": ("Feel the speed, control the kart, and enjoy a full track day with professional equipment and coaching. "
            "No license required."),
    "foto": "arrive-and-drive-hero.webp",
    "foto_equipe": "arrive-and-drive-equipe.webp",
    "esperar": ("Feel the rush of real speed. Up to 70 MPH on a pro racing track",
                "Get race-ready with a safety + driving technique briefing from expert coaches",
                "Suit up and strap in: this isn’t a theme park ride, it’s the real thing",
                "Create unforgettable memories for families, friends, and adrenaline junkies alike",
                "Walk away buzzing with adrenaline, confidence, and maybe a new obsession"),
    "fornece": ("The high performance go-kart", "Safety instructions", "Safety equipment"),
    "trazer": ("You must wear long pants, closed toe shoes and a jacket",),
    "porque": ("Real Racing Karts – Not slow rental karts", "Feel Like a Racer – This is the real deal",
               "Just Arrive & Drive – No prep, no hassle", "Pro-Level Track",
               "Gear up, get briefed, go fast – We handle everything"),
    "quem": ("Adults and kids looking for real speed", "Racing fans visiting Orlando", "Families seeking next-level fun",
             "First-timers curious about karting"),
    "passos": ("Pick your kart, your day and morning or afternoon",
               "Sign in or create your account and add your drivers",
               "We confirm your spot and send the invoice and the waiver",
               "Arrive 10 minutes early, check in and get settled",
               "Gear up, safety briefing, and hit the track"),
    "faq": (
        ("The experience",
         ("These are not the typical put-put go-karts, they are authentic, professional racing karts. This experience "
          "is for kids and adults, all ages are welcome!",
          "We will start by providing safety and driving technique instructions, after the first instructions you will "
          "have 3 or 6 10-minute driving sessions, according to your choice. The experience total time will be around "
          "2h for 3 sessions and 4–5h for 6 sessions from arrival until the end.")),
        ("The track",
         ("Orlando Kart Center’s 8/10 mile professional kart racing track is your textbook. A challenging circuit, the "
          "variety of corners is the ideal training ground.",
          "Urace is not the racetrack; we are a racing team that provides services to racers using a third-party track. "
          "We must adhere to their rules and operating hours. Both team members and drivers are required to pay "
          "admission fees to access the track.")),
        ("Terms and conditions",
         ("The program price is Urace’s fee for coaching and trackside support only. Track fees are not included: driver "
          "and guest passes are paid directly to the Orlando Kart Center, and the amount changes with the day. Extra "
          "guests must pay $15 each.",
          "We recommend new entrants to the sport to start with the 4-stroke options, and we can move the driver to the "
          "2-stroke option whenever we judge that the driver is capable of handling the 2-stroke kart.",
          "The scheduled arrival time at the track is 8 am. We kindly request that you arrive on time. If less than 75% "
          "track time is achieved, there is a possibility of receiving a proportional credit for a future session. Each "
          "case will be decided individually based on the reason for not meeting the minimum track time.",
          "To cover potential crash damage caused by the driver and track fees a $400 deposit will be charged in advance "
          "for security purposes, however this amount will be fully refunded at the end of the event in case of no "
          "incidents/damages to the kart.",
          "Any damages caused to the kart are not included in this price. If the kart breaks down and it was not caused "
          "by the driver (crash, going off of the track or aggressive driving style) the costs of repair will be covered "
          "by Urace. If the kart gets damaged as the result of a crash, regardless of the driver’s fault in the incident, "
          "the costs of repair will be billed to you.",
          "Kids under 10 years old must be accompanied by an adult. We provide a childcare assistant for an extra $200 in "
          "case you are unable to stay with your child. This service must be requested beforehand.",
          "Racing is a high-risk activity. By booking this appointment you agree and acknowledge that Urace is not "
          "responsible for any injuries, damages, or losses of any nature that might happen to you, or your family "
          "during track activities or while on site.")),
        ("Refund policy",
         ("Our service requires planning, preparation, coordination and transportation to the track on our end, for "
          "those reasons we do not offer refunds. Rescheduling will be available with a minimum notice of 48h and "
          "potential costs of rearrangement.",
          "If a class is rescheduled with less than 48 hours’ notice, a flat fee of $95 will be charged. If a Driver Pass "
          "is required, it will be charged additionally. To avoid this fee, we recommend notifying us of any changes at "
          "least 48 hours in advance.")),
        ("Opening hours", ("We’re open every day, from 8 AM to 8 PM.",)),
    ),
    "depoimentos": (("Ivan P.", "My son’s birthday was a hit! The kids had the time of their lives, and everything was "
                                "so well organized!"),
                    ("Daniel M., Team Leader", "Best corporate outing we’ve done! Everyone’s still talking about it "
                                               "weeks later.")),
    "fecho": "If you're serious about racing, this is where it starts. Shall we begin?",
}


def preco_minimo():
    return min(k["preco"] for k in KARTS)
