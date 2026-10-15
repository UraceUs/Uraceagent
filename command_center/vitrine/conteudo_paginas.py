"""As páginas institucionais do site novo (#164) com o texto do urace.us de 13/10/2026 (#207): Academy,
Pro Team, For Beginners, Career (The Driver Factory + Plan Your Career), About, Contact e Accessibility.

Nada inventado: cada texto saiu da página citada. Correções de propósito: endereço com o Box 3
(decisão de 01/10); o telefone da acessibilidade era "205 2291" no site antigo e aqui é o da
empresa, (407) 250 2291; remarcação com 24 h e as idades dos karts do produto (dono, 08/10); os
botões de comprar levam à reserva do site. Preço de serviço não é texto fixo: os planos vêm do painel
(Site › Serviços) e o Arrive and Drive de `conteudo.KARTS`; o que o sistema não tem fica sem preço.
"""
from command_center.vitrine.conteudo import FAQ_EVENTO, FECHO_DUVIDAS, SITE

RESERVAR = "/ops/portal/reserve"
CONTATO = "/contact/"
CARREIRA = "/career/"

MAIS_TITULO = "More than a karting school. We develop drivers."
MAIS = ("URACE is a driver development program based in Florida, created to guide young drivers through every stage of "
        "their motorsport journey. From the first experience behind the wheel to competitive racing, we provide "
        "professional coaching, structured development, mentorship and racing opportunities.",
        "Because becoming a driver requires more than speed. Motorsport develops discipline, focus, decision-making, "
        "emotional control and a competitive mindset — skills that matter on the track and far beyond it.",
        "We are the first step toward becoming a professional racing driver.")

FECHO_PROXIMO = ("Every driver has a next step. Let's find yours.",
                 "Whether you want to experience karting for the first time, begin structured driver development or pursue "
                 "higher levels of competition, URACE is ready to help you move forward.")

# ------------------------------------------------------------------ Academy (urace.us/urace-academy/ + /kart-training-packages/ + /services/)
# #254 (dono, 15/10): *"o kart school se tornou Urace academy"* — o texto que fazia sentido da página
# /services/kart-school/ entrou aqui, e aquele endereço virou 301 para esta página.
ACADEMY = {
    "caminho": "/academy/",
    "antigos": ("/urace-academy/", "/kart-training-packages/", "/kart-driving-school/", "/services/kart-school/"),
    "titulo": "Kart Academy in Orlando - Monthly Driver Training | URACE",
    "descricao": ("The URACE Kart Academy in Orlando: monthly kart training with professional coaching, race equipment and "
                  "a clear path from first laps into competition."),
    "eyebrow": "Driver Development · Orlando, FL",
    "h1": "Four coached sessions a month. One driver getting faster.",
    "sub": ("The URACE Academy is a monthly program for drivers who are past their first day in a kart: practical "
            "training, theory, real karts and a professional environment, for kids and adults. You bring the driver — we "
            "bring the kart, the full equipment, the maintenance and a professional coach."),
    "foto": "imagem-segunda-dobra.webp",
    "cta": ("Join URACE Academy", RESERVAR + "?service=academy"),
    "mais_titulo": MAIS_TITULO,
    "mais": MAIS,
    "planos_titulo": "Choose your commitment",
    "planos_sub": "The longer you commit, the less each session costs.",
    # Só aparecem sem plano cadastrado no painel; aí o botão abre o contato. O texto é o do site atual,
    # sem os valores por sessão (o preço do plano é o do painel).
    # #273 (dono, 15/10): a planilha de preços é a fonte, e a Academy tem preço próprio para 4 stroke (e Baby
    # Kart) e para 2 stroke — "veja que tem academy para 4t e 2t". As contas batem com 4 × sessão,
    # 27 × sessão × 0,96 e 54 × sessão × 0,92, com entrada de 33% / 20% (test_vitrine trava). Saíram
    # 3 Months, 6 Months a 5% e o URACE Boost: não estão na planilha.
    # grupo: (título, [(nome, sub, texto, preço, por)])
    "planos_grupos": (
        ("4-stroke and Baby Kart · $689 per session", (
            ("No contract", "4 sessions a month",
             "Kart, full safety equipment, maintenance and a professional coach included. No minimum term — cancel any "
             "time with thirty days written notice. Additional sessions $689 each.", "$2,756", "per month"),
            ("6-month contract", "27 sessions · 4% off",
             "Regular value $18,603.00. $5,893.43 at signing (33%), then 5 monthly installments of $2,393.09. "
             "Recurring billing.", "$17,858.88", "contract total"),
            ("12-month contract", "54 sessions · 8% off",
             "Regular value $37,206.00. $6,845.90 at signing (20%), then 11 monthly installments of $2,489.42. "
             "Recurring billing.", "$34,229.52", "contract total"))),
        ("2-stroke · $789 per session", (
            ("No contract", "4 sessions a month",
             "Kart, full safety equipment, maintenance and a professional coach included. No minimum term — cancel any "
             "time with thirty days written notice. Additional sessions $789 each.", "$3,156", "per month"),
            ("6-month contract", "27 sessions · 4% off",
             "Regular value $21,303.00. $6,748.79 at signing (33%), then 5 monthly installments of $2,740.42. "
             "Recurring billing.", "$20,450.88", "contract total"),
            ("12-month contract", "54 sessions · 8% off",
             "Regular value $42,606.00. $7,839.50 at signing (20%), then 11 monthly installments of $2,850.73. "
             "Recurring billing.", "$39,197.52", "contract total"))),
        ("Your own kart · no contract", (
            ("Your kart", "4 sessions a month",
             "You bring the kart; we bring the coaching, the track day and the support. Additional sessions $450 each.",
             "$1,800", "per month"),
            ("Your kart and your mechanic", "4 sessions a month",
             "You bring the kart and your mechanic; we bring the coaching and the track day. Additional sessions $300 each.",
             "$1,200", "per month"))),
    ),
    "para_quem_titulo": "Who is this for?",
    # os dois últimos vêm do "Who is this for?" da Kart School (#254)
    "para_quem": ("Drivers already competing or preparing to compete", "Individuals seeking structured, high-performance training",
                  "Drivers committed to long-term development", "Those looking for real coaching, not just seat time",
                  "Drivers focused on consistency, speed, and race performance",
                  "Kids aged 6–14 and adults", "Early-stage racers who already had their first day in a kart"),
    "curriculo": (("Driving Fundamentals", "Master acceleration, braking, cornering, and racing techniques"),
                  ("Theoretical Foundations", "Understand racing principles, track dynamics, and safety protocols"),
                  ("Kart Mechanics", "Learn about chassis, engine and component maintenance, and develop technical knowledge of kart setup, adjustments and performance optimization"),
                  ("Practical Sessions", "Structured on-track sessions with real-time coaching and feedback")),
    "objetivos": ("Develop advanced driving skills and race consistency", "Build a deep understanding of kart dynamics and performance",
                  "Strengthen mental focus and competitive mindset", "Prepare drivers for competitive racing and elite-level performance"),
    "carreira_titulo": "Career planning, specialists & add-on services",
    "carreira_intro": "Every Academy family works with a career specialist, not just a coach. That means real planning behind the driving, not only laps:",
    "carreira": ("Career path analysis: our specialists assess the driver's progress and lay out realistic next steps, categories, and timelines.",
                 "Track planning: deciding which tracks and race weekends make sense for where the driver is right now.",
                 "Logistics planning: coordinating travel, scheduling, and race-weekend logistics around school and family life.",
                 "Cost-efficiency planning: budgeting the season so spending matches the driver's actual stage and goals, not guesswork.",
                 "Brand & sponsorship association: once a driver is competitive, we help shape their story and connect it with potential sponsors and brand partners.",
                 "On-track team: the same mechanic who preps the equipment and the coach who reviews the laps, working together on every session."),
    "carreira_extras_intro": "Available as paid add-ons, negotiated separately once a driver is ready for them:",
    "carreira_extras": ("Press & PR advisory for the driver and family.", "Video content production for the driver's own highlight reels and sponsor material."),
    "inclui_titulo": "Package includes",
    "inclui": ("Kart: High-performance kart provided for each session.", "Coach: Expert coaching from professional instructors.",
               "Mechanic: On-site mechanical support to keep the kart race-ready.", "Career planning: Ongoing guidance from your career specialist.",
               "In-depth safety instructions.", "Driver Pass: Access to the track for the driver.",
               "1 Guest Pass: Bring one guest (family or friend) to accompany and support you (Additional guests subject to track pass price)."),
    # #254: da Kart School — o que levar, o "Why URACE" e o passo a passo de entrar (os passos são os
    # da compra do plano no site e o que os termos da Academy já dizem: 4 dias por mês, chegada às 8 am)
    "trazer_titulo": "What you need to bring",
    "trazer": ("MUST wear long pants, closed toe shoes and a jacket.",),
    "porque_titulo": "Real training, theory and pro coaching, month after month",
    "porque": ("Professional Track - where real races happen.", "Theory and mechanics simplified",
               "Mentorship by winning drivers", "Confidence, reflexes and racing mindset",
               "Monthly Program = Continuous Evolution"),
    "passos_titulo": "How to join the URACE Academy",
    "passos": ("Choose your commitment above — the longer you commit, the less each session costs.",
               "Sign in or create your URACE account and tell us who the driver is (height and weight, so the kart is prepared).",
               "Pay the first month online and sign the waiver.",
               "Your four sessions a month are scheduled once a week, with your coach. Arrival at the track is 8 am."),
    "caminho_titulo": "Your path: Arrive and Drive → Academy → Racing Team",
    "caminho_texto": ("URACE Academy isn't a standalone class — it's the middle rung of a ladder. Drivers usually start at Arrive "
                      "and Drive, where they get their first real laps and we get our first read on their potential. Academy is "
                      "where that potential becomes a plan: four sessions a month of structured coaching, video and data review, "
                      "and a career specialist tracking progress alongside the driving. From there, Academy drivers who are ready "
                      "move up to the URACE Racing Team — our motorsport hub, where they compete under the URACE banner on the "
                      "path toward the main leagues of the sport.",
                      "We're also building a racing simulator program, launching soon, to give Academy and Racing Team drivers "
                      "extra seat time between track days without the cost of extra track sessions. Not sure where your driver "
                      "fits on that path? Talk to Our Career Specialist and we'll map it out with you.",
                      "Every driver starts somewhere. URACE provides a structured environment where young drivers can experience "
                      "motorsport, develop their skills and progress toward increasingly competitive levels of racing."),
    "etapas": (("Experience", "Discover karting and take your first laps with professional guidance.", "icon-experience.webp"),
               ("Develop", "Build technique, discipline, consistency and a competitive mindset through structured training.", "icon-develop.webp"),
               ("Compete", "Gain race experience and learn to perform in competitive environments.", "icon-compete.webp"),
               ("Pursue the next level", "Continue developing with professional coaching, racing experience and long-term guidance.", "icon-pursue.webp")),
    "faq": (("Add-ons, travel and track fees", (
                # #273: da planilha de preços do dono (15/10)
                "Lead and Follow is an add-on for any training day: a partner trainer on track with the driver, for $769 per training day.",
                "Academy services provided outside of the Orlando Kart Center are charged an extra $250 for hotel, food and transport.",
                "Track fees are not included in the price and must be paid directly to the track.")),
            ("A complete racing education", (
                # da Kart School (#254): "URACE Kart School" virou "URACE Academy" e "novice drivers" saiu,
                # porque a Academy é para quem já teve o primeiro dia de kart
                "Embark on a comprehensive racing education with the URACE Academy, designed for drivers eager to excel. "
                "Our structured program combines theoretical knowledge with hands-on training, equipping students with the "
                "skills and confidence to succeed.",)),
            ("Why motorsport builds champions", (
                "Karting looks like a hobby from the outside, but the skills it demands behind the wheel are the ones researchers "
                "tie to healthy child development. A young driver is constantly reading the track, adjusting their line, and "
                "making split-second calls under pressure — fast, consequence-driven decision-making that's hard to practice "
                "anywhere else.",
                "The research on youth sport backs this up. A large study published in PLOS One found sport's overall impact on "
                "child development is strongly positive, including gains in self-esteem and communication. A separate study "
                "comparing competitive athletes to recreational and instructional-level peers found the competitive group scored "
                "significantly higher on cognitive skills and goal-setting. And researchers who study youth sport broadly — "
                "including work out of Texas A&M — point to competition itself as a key driver of resilience: learning to lose a "
                "race, work out what went wrong, and come back faster teaches persistence in a way few other childhood "
                "activities do.",
                "At URACE Academy, every session is built around that exact process. Coaches don't just teach a driving line — "
                "they walk each driver through onboard video and lap-time data, then set a specific target for the next session. "
                "It's the same cycle of goal-setting, performance, and reflection the research points to, just happening at 50 mph.",
                "We're not claiming karting replaces coaching, school, or therapy. But for a sport that asks a 7-year-old to "
                "process more information per second than almost any other youth activity, it's hard to find a better training "
                "ground for focus, composure under pressure, and the discipline to keep improving.")),
            ("Terms and conditions", (
                "The program price is URACE’s fee for coaching, trackside support, kart rental, driver and one guest pass only; "
                "anything not in this list is excluded.",
                "This training consists of 4 days per month to be scheduled once/week, each day consists of 6 sessions of 10 "
                "minutes each session, or a total 1 hour of track time/day. The arrival time at the track is 8 am. We kindly "
                "request that you arrive on time. If less than 40 minutes of track time is achieved, there is a possibility of "
                "receiving a proportional credit for a future session. Each case will be decided individually based on the "
                "reason for not meeting the minimum track time.",
                "Any damages caused to the kart are not included in this price, regardless of the driver's fault or not in the "
                "incident, and will be billed to you for the costs of repair. Clarifying: If the kart breaks down and it was not "
                "caused by the driver, (crash, going off of the track or aggressive driving style) the costs of repair will be "
                "covered by URACE. If the kart gets damaged in the result of a crash, regardless of driver's fault in the "
                "incident, the costs of repair will be billed to you. Understanding why: Each driver in a race track is fully "
                "liable for his own equipment and safety. Meaning, even if someone else crashes into you or your child, you are "
                "responsible for your and or child's equipment. You are not responsible for the other person in the other kart, "
                "nor the other person's equipment even if you or your child caused the incident.",
                "Kids under 10 years old must be accompanied by an adult. We provide a childcare assistant for an extra $200/day "
                "in case you are unable to stay with your child. This service must be requested beforehand.")),
            ("Refund and rescheduling policy", (
                "Our service requires planning, preparation, coordination and transportation to the track on our end; for those "
                "reasons we do not offer refunds. Rescheduling is available with a minimum notice of 24 hours. With less than "
                "24 hours' notice, a flat fee of $95 is charged, plus the Driver Pass if required. To avoid this fee, we "
                "recommend notifying us of any changes at least 24 hours in advance.",
                "Please note that if a training session needs to be rescheduled due to circumstances outside of URACE's control, "
                "a fee will be charged to cover personnel costs. This fee will be in addition to any other costs associated with "
                "the session itself. By using URACE's services, you agree to this policy and understand that rescheduling fees "
                "may apply.")),
            ("Cancelling the plan", ("Renews month by month; cancel with 30 days written notice.",))),
    "fecho": "Future pros start here.",
    "fecho_sub": " ".join(FECHO_PROXIMO),
    "fecho_cta": ("Join URACE Academy", RESERVAR + "?service=academy"),
}

# ------------------------------------------------------------------ Pro Team (urace.us/pro-team/ + /professional-kart-team-racing-team/)
PRO_TEAM = {
    "caminho": "/pro-team/",
    "antigos": ("/professional-kart-team-racing-team/",),
    "titulo": "Kart Racing Team in Florida - Join the URACE Team",
    "descricao": ("URACE runs a professional kart racing team in Florida: engine programme, coaching, race support and a "
                  "selection path from club karting upward."),
    "eyebrow": "Driver Development · Orlando, FL",
    "h1": "You already race. Now race with a team behind you.",
    "sub": ("URACE prepares the kart, runs the race weekend and puts a professional coach alongside the driver — based at "
            "the Orlando Kart Center and entered in the Florida and national calendars."),
    "foto": "banner-topo-lp-urace-1.webp",
    "cta": ("Talk to our racing team", CONTATO),
    "metodo": ("Our teaching method includes data analysis, on-board video study and explanation of the theories involved "
               "in all the driving aspects we discuss. We offer full support for local, regional and national events."),
    "suporte_titulo": "Professional Kart Racing Team",
    # o site atual só descreve o primeiro; os outros são só o título
    "suporte": (("Travel logistics", "We handle everything, you only need to book your flights and hotel."),
                ("Equipment prep", ""), ("Engineering", ""), ("Coaching", ""), ("Hospitality", ""), ("High speed wifi", "")),
    "mais_titulo": MAIS_TITULO,
    "mais": MAIS,
    "opcoes_titulo": "How we work with competitive drivers",
    "opcoes_sub": "Two ways in, depending on where the driver is today.",
    # (nome, sub, texto, preço, por, link): o preço "academy"/"boost" é o do plano no painel; sem plano, sem preço
    "opcoes": (("URACE Academy", "Not racing yet? Start here.", "Four coached sessions a month with kart, full equipment, maintenance and a professional coach included. Month to month, no minimum term.", "academy", "Per month", "/academy/"),
               ("Race Weekend Support", "We run the kart. You drive.", "Kart preparation and trackside support at the rounds we are entered in. Race entries, tyres, fuel and consumables are quoted per event and are not part of the fee.", "Let’s talk", "Per event", CONTATO)),
    "calendario_titulo": "Where we are racing",
    "calendario_sub": "The rounds URACE is entered in. If your driver comes with us, this is the season. Dates and venues as published by the series.",
    "calendario": (("Oct 18, 2026", "SKAPA Winter Series — Rounds 4 & 5"),
                   ("Oct 25, 2026", "AMR Karting Challenge — Round 9, Homestead, Florida"),
                   ("Nov 22, 2026", "AMR Karting Challenge — Round 10, Homestead, Florida"),
                   ("Dec 6, 2026", "Florida Karting Championship — Rounds 11 & 12, AMR Motorplex")),
    "fecho": "Future pros start here.",
    "fecho_sub": " ".join(FECHO_PROXIMO),
    "fecho_cta": ("Talk to our racing team", CONTATO),
}

# ------------------------------------------------------------------ For Beginners (urace.us/for-beginners/ + /kart-lessons-for-beginners/)
BEGINNERS = {
    "caminho": "/for-beginners/",
    "antigos": ("/kart-lessons-for-beginners/",),
    "titulo": "How to Get Into Karting - Start in Orlando | URACE",
    "descricao": ("Never driven a race kart? Start here. How karting works, what to expect on your first day in Orlando, "
                  "and the path from first lap to competition."),
    "eyebrow": "For Beginners",
    "h1": "How to Get Into Karting in Orlando",
    "sub": "(All ages)",
    "foto": "banner-topo-lp-urace-1.webp",
    "cta": ("I want to start karting!", "/services/arrive-and-drive/"),
    "primeira_titulo": "First time in a kart?",
    "primeira": ("No stress. We've got you covered. From safety gear to first-time instructions, our team guides every step so "
                 "you can focus on enjoying the ride, learning, and discovering what you're made of.",
                 "At URACE, beginners are treated like future athletes. Our method is structured and serious, for kids who want "
                 "to start young or adults ready to take on a new challenge.",
                 "You'll learn real technique from day one: driving position, control, racing discipline, and decision-making. "
                 "You'll build the right foundation to progress with confidence."),
    "contato_titulo": "Arrive and Drive: First contact with karting",
    "contato": ("Personalized coaching with a dedicated professional coach, designed to accelerate driver development through "
                "structured training, advanced telemetry, technical analysis, and precise driving corrections. Each session "
                "focuses on building correct technique, consistency, and confidence on track. Ideal for drivers who want to "
                "train with purpose, evolve continuously, and reduce lap times with a high-performance approach.",),
    "contato_cta": "Schedule now",
    "proximo_titulo": "Where are you in your racing journey?",
    # (nome, sub, texto, preço, link, botão): "kart" = o menor preço de KARTS; os outros não têm preço no sistema
    "proximo": (("Arrive & Drive", "Experience karting for one day.", "Your first opportunity to experience real karting with professional guidance and URACE support. Perfect for first-time drivers and families who want to discover motorsport.", "kart", "/services/arrive-and-drive/", "Experience karting"),
                ("URACE Academy", "Start your development as a racing driver.", "A structured driver development program for young athletes who want to train, improve and build the foundations required for competitive karting — with professional coaching, track experience, evaluation and mentorship.", "", "/academy/", "Join URACE Academy"),
                ("Racing Team", "Already competing? Pursue the next level.", "Professional support for competitive drivers who want to improve their performance and pursue higher levels of motorsport — coaching, race preparation, competition experience and professional guidance.", "", "/pro-team/", "Talk to our racing team")),
    # perguntas de urace.us/plan-your-career/ (idades: decisão do dono de 08/10)
    "faq": (("How do I get my child into racing?", ("From four years old a child can drive a Baby Kart and learn driving lines and fundamentals. From seven they fit a 4-stroke, and from fourteen, with experience, the Adult Shifter. Start with one day — a race kart, full gear, a coach watching — and let the coach and the data tell you whether there's something there. Children under ten must be accompanied by an adult at the track. If they love it and want more, the Academy turns one good day into a monthly plan.",)),
            ("How do I know if my kid has potential?", ("Lap time on day one tells you almost nothing. What a coach reads is how fast a driver corrects a mistake, whether they repeat it, and how they behave when the session goes badly. That's visible within a few runs, and it's visible in the data rather than in opinion. We'll tell you what we saw honestly — including when the answer is that your child loves driving and isn't a future professional, which is a perfectly good answer.",)),
            ("Am I too old to start racing?", ("For Formula 1, almost certainly — that ladder is normally climbed from childhood. For racing itself, no. Masters karting categories exist precisely for adult drivers, and adults often learn the technical side faster than children because they can absorb data and theory. If your goal is to race competitively, be good, and enjoy it, age is not the barrier. If your goal is a professional seat, we'll tell you straight what's realistic.",)),
            ("What do I need to bring?", ("Long pants, closed toe shoes and a jacket. We provide the kart, the safety equipment and the instructions.",))),
    "fecho": FECHO_DUVIDAS[0],
    "fecho_sub": FECHO_DUVIDAS[1],
    "fecho_cta": ("Talk to us", CONTATO),
}

# ------------------------------------------------------------------ Career (urace.us/the-driver-factory/ + /plan-your-career/)
CAREER = {
    "caminho": "/career/",
    "antigos": ("/the-driver-factory/", "/plan-your-career/"),
    "titulo": "How to Become a Professional Racing Driver | URACE Orlando",
    "descricao": ("How to become a racing driver, step by step: where karting fits, what a real development path looks like, "
                  "and how to get into racing from Orlando."),
    "eyebrow": "Career Plan · Orlando",
    "h1": "How to become a racing driver: one ladder. Start at the bottom.",
    "sub": ("Nobody is born on a grid. Every professional driver climbed a ladder, and every rung of it was paid for and "
            "earned. This page is that ladder, laid out end to end — from a simulator seat in Orlando to Formula 1, IndyCar "
            "or NASCAR. We run the bottom of it and we prepare drivers for the rest."),
    "foto": "enzo-1.webp",
    "cta": ("Find my next step", CONTATO),
    "degraus_titulo": "The ladder ends on our grid",
    "degraus_intro": ("Sim 2 Grid. Arrive and Drive. URACE Academy. URACE Racing Team. Four steps, one team. Nobody skips to "
                      "the top and nobody buys their way in — your coach tells you when you are ready, and not before."),
    "degraus": (("Sim 2 Grid", "Opening 1 November 2026. A full motion cockpit — competition seat and harness, direct-drive wheel, racing pedals, triple screen.", "/services/#sim2grid"),
                ("Arrive and Drive", "Experience karting for one day. Your first opportunity to experience real karting with professional guidance and URACE support.", "/services/arrive-and-drive/"),
                ("URACE Academy", "Start your development as a racing driver. Four coached sessions a month.", "/academy/"),
                ("Racing Team", "Already competing? Pursue the next level.", "/pro-team/")),
    "perguntas_titulo": "Questions people actually ask",
    "perguntas_sub": "Straight answers, including the ones that cost us a sale.",
    "faq": (("Does my kid show potential?", ("There’s one honest way to find out, and it isn’t a quiz. Put them in a real race kart with a coach watching, and read the data afterwards. One day tells us more than a year of wondering — and we’ll tell you what we actually saw, including when the answer is “they love it, and that’s enough”.",)),
            ("I’m over 18 — is it too late?", ("For Formula 1, honestly, yes: that route is built around drivers already karting at ten, and it closes in your teens. For racing, no. Stock cars and sports cars have no age-gated junior ladder, and Masters leagues exist precisely for drivers who started as adults. We coach adults and seven-year-olds on the same day, on the same circuit. The ladder asks whether you learn the technical way, not when you were born — and that is teachable at any age. And if you already race, you skip the simulator and the Academy entirely.",)),
            ("How do I become a racing driver?", ("You start in a kart, you get coached, and you build a record that the next category will look at. There is no shortcut and no talent-spotting shortcut either — every professional on a grid today climbed the same kind of ladder, one paid rung at a time. What changes between drivers is how early they start, how good the coaching is, and how well the season is planned. The cheapest honest first move is a simulator hour or a single day in a race kart, because both tell you whether you want the next rung before you’ve spent anything serious.",)),
            ("How do I get my child into racing?", ("From four years old a child can drive a Baby Kart and learn driving lines and fundamentals. From seven they fit a 4-stroke, and from fourteen, with experience, the Adult Shifter. Start with one day — a race kart, full gear, a coach watching — and let the coach and the data tell you whether there’s something there. Children under ten must be accompanied by an adult at the track. If they love it and want more, the Academy turns one good day into a monthly plan.",)),
            ("How do I know if my kid has potential?", ("Lap time on day one tells you almost nothing. What a coach reads is how fast a driver corrects a mistake, whether they repeat it, and how they behave when the session goes badly. That’s visible within a few runs, and it’s visible in the data rather than in opinion. We’ll tell you what we saw honestly — including when the answer is that your child loves driving and isn’t a future professional, which is a perfectly good answer.",)),
            ("Am I too old to start racing?", ("For Formula 1, almost certainly — that ladder is normally climbed from childhood. For racing itself, no. Masters karting categories exist precisely for adult drivers, and adults often learn the technical side faster than children because they can absorb data and theory. If your goal is to race competitively, be good, and enjoy it, age is not the barrier. If your goal is a professional seat, we’ll tell you straight what’s realistic.",)),
            ("How do I get into NASCAR?", ("The stock car route leaves karting earlier than the open-wheel ones. A driver typically moves from karting into Legends or Bandolero cars, then regional Late Models, then the ARCA Menards Series, then NASCAR’s three national series in order: the Craftsman Truck Series, the Xfinity Series, and the Cup Series. Because the branch happens young, the decision about which destination you’re aiming at matters earlier than most families expect.",)),
            ("How do I get to IndyCar?", ("Through the Road to Indy, which is the most clearly defined ladder in motorsport: USF Juniors, then USF2000, then USF Pro 2000, then Indy NXT, then IndyCar. Each rung has a scholarship structure attached to winning it, which makes it the cheapest of the single-seater paths to a top-level seat — and the reason we map American drivers onto it early.",)),
            ("How do I get to Formula 1?", ("Karting, then Formula 4, then Formula Regional, then FIA Formula 3, then FIA Formula 2, then one of twenty seats in the world. It is the longest and most expensive of the three routes and the one where a karting record counts for most, which is why drivers aiming at it start young and race nationally as early as they can. Nobody can promise this rung. What can be promised is that every rung below it is real and that the climb is known.",)),
            ("Can a simulator really prepare you for real racing?", ("For circuit knowledge, braking points and racecraft, yes — our own drivers learn a circuit on the simulator before they ever see it. A full motion cockpit loads the driver up in the corners and punishes the same mistakes a real car does. What it can’t teach is the physical load of a real race weekend, which is why it’s the first rung and not the only one. It is, though, the only rung with no track fee, no equipment and no weather.",)),
            ("Where are you based?", ("We operate at the Orlando Kart Center, 10724 Cosmonaut Blvd, Orlando FL 32824 — an 8/10 mile professional kart circuit just off the Florida Turnpike, minutes from most of Orlando’s attractions. URACE is a racing team, not the racetrack: we provide coaching and programs at a third-party circuit and follow their rules and operating hours.",))),
    "pessoa_titulo": "We are building a person, not only a driver",
    "pessoa": ("Karting looks like a hobby from the outside. What it actually asks of a seven-year-old is to read a track, adjust a line, and make consequence-driven decisions at speed, over and over, for an hour. There are very few childhood activities that demand that much processing per second.",
               "A large study published in PLOS One found sport’s overall impact on child development is strongly positive, including gains in self-esteem and communication. A separate study comparing competitive athletes to recreational and instructional-level peers found the competitive group scored significantly higher on cognitive skills and goal-setting. And researchers who study youth sport — including work out of Texas A&M — point to competition itself as a key driver of resilience: learning to lose a race, work out what went wrong, and come back faster teaches persistence in a way few other childhood activities do.",
               "Every URACE session is built around that cycle. A coach doesn’t only teach a driving line — they walk the driver through onboard video and lap-time data, then set one specific target for next time. Goal, attempt, review, adjust. It happens to be happening at 50 mph.",
               "We’re not claiming karting replaces school, coaching or therapy. We’re saying the driver who comes back to you is more focused, steadier under pressure and harder to rattle — and that part is yours to keep whether or not they ever reach a professional grid."),
    "fotos": (("enzo-1.webp", "Enzo Vidmontiene, URACE driver"), ("leonardo-1.webp", "Leonardo Escorpioni, URACE driver"), ("emmo-2.webp", "Emmo Fittipaldi, URACE driver")),
    "profissional_titulo": "And a professional, not only an athlete",
    "profissional": ("Most people who make a living in motorsport never drive for one. They engineer, they manage, they run teams, they handle the commercial side. A driver who understands that industry is worth more inside it — and has somewhere to go if the seat never comes.",
                     "So we teach the business alongside the driving. From the Academy onward a driver works with a career specialist, not only a coach. By the time they reach the Racing Team, the work is as much about building a professional as a lap time."),
    "profissional_itens": (("Brand & identity", "Helmet and livery design, team kit, the visual identity a driver carries from one category to the next."),
                           ("Press & PR", "How to talk to media, how to handle a bad weekend in public, and advisory for the driver and the family."),
                           ("Social & content", "Building the channels, producing highlight reels and sponsor material that a brand can actually use."),
                           ("Sponsorship", "Shaping the driver’s story and connecting it with brands once there’s a record worth presenting."),
                           ("Season planning", "Which categories, which tracks, what it costs, and how it fits around school and family life."),
                           ("Race craft", "Reading a contract, running a weekend, working with a mechanic and an engineer as a professional does.")),
    "eventos_titulo": "Not on the ladder: groups and corporate events",
    "eventos": ("Bring the whole group. Everyone drives a real race kart on a professional circuit, with our staff running the session start to finish. Birthdays, corporate days, team offsites. This one isn’t a development step — it’s a day out, and it’s meant to be.",),
    "eventos_faq": FAQ_EVENTO,
    "aviso": ("URACE runs the four red rungs. The championships above them are run by their own organisers and governing bodies. "
              "URACE is not affiliated with, endorsed by or a partner of any of them — we prepare and enter drivers, nothing more.",
              "URACE is not the racetrack. We are a racing team providing coaching and programs to racers and enthusiasts at the "
              "Orlando Kart Center, a third-party circuit, and we follow their rules and operating hours. Track fees are charged "
              "by the circuit, separately from URACE services: driver pass Wednesday to Friday $100–230, driver pass Saturday and "
              "Sunday $100–125, spectator pass any day $22. Extra guests must pay $15 each."),
    "fecho": "You don’t need to know which rung is yours",
    "fecho_sub": ("Tell us who the driver is and whether they’ve been in a race kart before. That one answer decides the rest — "
                  "and we’ll tell you honestly where to start, even if it’s the cheapest rung on the ladder."),
    "fecho_cta": ("Find my next step", CONTATO),
}

# ------------------------------------------------------------------ About (urace.us/about/)
ABOUT = {
    "caminho": "/about/",
    "titulo": "About URACE - Kart Academy & Racing Team in Orlando",
    "descricao": ("URACE is a professional kart academy and racing team in Orlando, taking drivers from their first lap to "
                  "national competition."),
    "eyebrow": "About URACE",
    "h1": "Since 2016, Building champions on and off the race track",
    "foto": "sobre.webp",
    "historia_titulo": "About URACE",
    "historia": ("Racing has been our passion for generations! Our kart racing story started 26+ years ago in Brazil. Team "
                 "principal Italo Silveira began by racing karts, winning numerous Brazilian regional and national championships. "
                 "A successful professional car racing career followed in the internationally recognized Brazilian stock car "
                 "series. In 2016, Italo moved to Florida and launched URACE, a karting team, to pass along his extensive "
                 "knowledge and passion to young drivers. URACE is divided in 3 racing operations:",),
    # #254: o primeiro item dizia "Kart School"; a porta de entrada de quem está conhecendo o esporte
    # é o Arrive and Drive (o Kart School virou a URACE Academy)
    "historia_itens": ("Arrive and Drive, for beginners learning about the sport;", "URACE Academy, for local drivers racing in Orlando FL;",
                       "URACE Pro Team, for drivers ready to challenge for the podium Nationwide."),
    "historia_fecho": "URACE builds winners on and off the tracks due to experience, professionalism, and the passion we have for the sport.",
    "metodo_titulo": "Structure & Methodology",
    "metodo_intro": "URACE is built on the real-world experience of a former pro driver — and that makes all the difference. Our method combines:",
    "metodo": ("Pro-level driving technique", "In-depth understanding of kart setup & dynamics", "High-performance mental training and decision-making", "Constant progress through individual coaching"),
    "metodo_fecho": "From first lap to national-level racing, our method prepares drivers every step of the way.",
    "diferente_titulo": "Why is URACE different?",
    "diferente": ("URACE is different because it was not created as a traditional race team, but as a complete driver development "
                  "program designed by Italo Silveira, someone who has lived the sport firsthand and achieved real results. "
                  "URACE’s advantage lies in Italo Silveira’s unique perspective. He began competing at the age of seven and has "
                  "been coaching drivers since 2004, with a deep understanding of every aspect of racing: driving technique, "
                  "mechanics, strategy, and the winning mindset.",
                  "Because of this, our drivers learn:"),
    "diferente_itens": ("Not just how to drive, but how to think like professional drivers;", "Not just how to compete, but how to develop the mindset and preparation required to win;",
                        "Not just how to improve quickly, but how to achieve consistent excellence."),
    "diferente_fecho": "This combination of experience, methodology, and close mentorship is what makes URACE a reference in driver development.",
    "equipe_titulo": "Our team",
    "equipe": ("URACE is led by Italo Silveira, a former professional race car driver and the founder of the team.", "His career includes:"),
    "equipe_itens": ("Starting in karting at the age of seven;", "Regional and national titles in Brazil;", "Competing in Stock Car, the country's premier racing category;",
                     "Nearly three decades of experience driving, coaching, and developing drivers."),
    "equipe_fecho": ("Italo began coaching drivers at just fourteen years old and has continued this work throughout his entire career, "
                     "building a comprehensive understanding of athlete development, technical progression, and the formation of a "
                     "winning mindset, both on and off the track.",
                     "Alongside him, Italo is supported by a team of experienced professionals at URACE who are deeply passionate "
                     "about the sport. They are responsible for preparing the equipment, overseeing training sessions, guiding "
                     "drivers, and ensuring continuous improvement."),
    "visao": ("We are working to become the most victorious karting team in the United States. We are a reference in professional "
              "driver training, proving many times to train drivers that excel and become a reference at the National level in "
              "record time. Now our goal as a team is to retain those drivers so they can win as every URACE driver does, win "
              "wearing our colors."),
    "missao": ("Italo Silveira - “I founded URACE to provide the support and mentorship I wish I had received during my own career. "
               "My mission is to transform the lives of drivers who have both talent and resources to become professionals, and "
               "to truly help them get there.",
               "I always had the necessary conditions to go far: skill, dedication, and investment, but I did not reach the professional "
               "level because I lacked the right support at a critical moment. Even today, whenever I return to the track, my results "
               "reflect the depth of my knowledge and my racecraft.",
               "That is exactly why URACE exists: to give drivers the structure, knowledge, and competitive advantage I did not have, "
               "allowing them to reach their full potential, whether they are just starting their journey or already pursuing "
               "excellence at the highest level.”"),
    "suporte_titulo": "Full Service Race Support",
    "suporte": ("URACE is a full-service racing team built to support drivers at every level.",
                "We take care of storage, maintenance, transportation to and from the track, and full trackside support.",
                "From preparation to race day execution, we handle every detail so you can focus on what truly matters — driving.",
                "You show up. You race. We handle the rest."),
    "seguranca_titulo": "Safety",
    "seguranca_intro": "Safety is a top priority at every stage of the URACE process. Every training, session, and race follows strict standards to ensure that:",
    "seguranca": ("Drivers use approved safety gear", "Clear instructions are given before each session", "All driving is done in a supervised, controlled environment",
                  "Skill development focuses on control, awareness, and risk prevention"),
    "seguranca_fecho": "Our mission is to help drivers grow with confidence, discipline, and the protection needed to aim high.",
    "depoimentos_titulo": "Built by URACE",
    "depoimentos_sub": "Check out testimonials from parents and drivers",
    "fecho": FECHO_DUVIDAS[0],
    "fecho_sub": FECHO_DUVIDAS[1],
    "fecho_cta": ("Talk to us", CONTATO),
}

# ------------------------------------------------------------------ Contact (urace.us/contact/)
CONTACT = {
    "caminho": "/contact/",
    "titulo": "Contact URACE - Kart Racing School in Orlando",
    "descricao": (f"Talk to the URACE team about kart lessons, the academy or race support. Orlando Kart Center, "
                  f"{SITE['endereco']['rua']}. Call {SITE['telefone']}."),
    "eyebrow": "Contact",
    "h1": "Talk to URACE",
    "sub": "New lead, question, or planning a group / corporate event? Fill out the form below and our team will get back to you.",
    # #254: não existe mais o programa "Professional Coaching"; o coaching na pista é o Lead and Follow
    "assuntos": (("arrive-and-drive", "Arrive and Drive"), ("academy", "URACE Academy"), ("coaching", "Lead and Follow coaching"),
                 ("camp", "Intensive Training Camp"), ("team", "Racing Team"), ("event", "Birthday, corporate or group event"),
                 ("store", "Store: parts, suits and apparel"), ("other", "Something else")),
    "local_titulo": "Location",
}

# ------------------------------------------------------------------ Accessibility (urace.us/accessibility/)
ACCESSIBILITY = {
    "caminho": "/accessibility/",
    "titulo": "Accessibility - URACE",
    "descricao": ("Accessibility statement for URACE, the kart racing school at the Orlando Kart Center. How we work to keep "
                  "the site and the track usable for everyone."),
    "h1": "Accessibility Statement for URACE",
    "texto": ("This is an accessibility statement from URACE.",),
    "conformidade_titulo": "Conformance status",
    "conformidade": ("The Web Content Accessibility Guidelines (WCAG) defines requirements for designers and developers to improve "
                     "accessibility for people with disabilities. It defines three levels of conformance: Level A, Level AA, and "
                     "Level AAA. URACE is partially conformant with WCAG 2.1 level AA. Partially conformant means that some parts "
                     "of the content do not fully conform to the accessibility standard.",),
    "feedback_titulo": "Feedback",
    "feedback": "We welcome your feedback on the accessibility of URACE. Please let us know if you encounter accessibility barriers on URACE:",
    "data_titulo": "Date",
    "data": "This statement was created on 15 April 2026 using the W3C Accessibility Statement Generator Tool.",
}

PAGINAS = (ACADEMY, PRO_TEAM, BEGINNERS, CAREER, ABOUT, CONTACT, ACCESSIBILITY)
