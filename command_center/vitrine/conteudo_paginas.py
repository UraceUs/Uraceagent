"""As páginas institucionais do site novo (#164), copiadas do urace.us de 08/10/2026: Academy, Pro
Team, For Beginners, Career (The Driver Factory), About, Contact e Accessibility.

Nada inventado: cada texto saiu da página citada. Correções de propósito: endereço com o Box 3
(decisão de 01/10); o telefone da acessibilidade era "205 2291" no site antigo e aqui é o da
empresa, (407) 250 2291; os botões de comprar levam à reserva do site.
"""
from command_center.vitrine.conteudo import SITE

RESERVAR = "/ops/portal/reserve"
CONTATO = "/contact/"
CARREIRA = "/career/"

# ------------------------------------------------------------------ Academy (urace.us/urace-academy/ + /kart-training-packages/)
ACADEMY = {
    "caminho": "/academy/",
    "antigos": ("/urace-academy/", "/kart-training-packages/", "/kart-driving-school/"),
    "titulo": "Kart Academy in Orlando - Monthly Driver Training | URACE",
    "descricao": ("The URACE Kart Academy in Orlando: monthly kart training with professional coaching, race equipment and "
                  "a clear path from first laps into competition."),
    "eyebrow": "Driver Development · Orlando, FL",
    "h1": "Four coached sessions a month. One driver getting faster.",
    "sub": ("The URACE Academy is a monthly program for drivers who are past their first day in a kart. You bring the "
            "driver; we bring the kart, the equipment, the mechanic and a professional coach, four times a month."),
    "foto": "imagem-segunda-dobra.webp",
    "cta": ("Join URACE Academy", RESERVAR + "?service=academy"),
    "mais_titulo": "More than a karting school. We develop drivers.",
    "mais": ("URACE is a driver development program based in Florida, created to guide young drivers through every stage "
             "of their motorsport journey. From the first experience behind the wheel to competitive racing, we provide "
             "professional coaching, structured development, mentorship and racing opportunities.",
             "Because becoming a driver requires more than speed. Motorsport develops discipline, focus, decision-making, "
             "emotional control and a competitive mindset: skills that matter on the track and far beyond it."),
    "planos_titulo": "Choose your commitment",
    "planos_sub": "The longer you commit, the less each session costs.",
    "planos": (
        ("1 Month", "Four sessions in 30 days.", "No contract and no minimum term. Kart, full safety equipment, maintenance and a professional coach included. $689.23 per session.", "$2,756.90", "per month"),
        ("3 Months", "Twelve sessions, up to four a month.", "Everything in the monthly plan, with 2.5% off every session: $672.11 instead of $689.23. Total of $8,065.29 over three months.", "$2,688.43", "per month"),
        ("6 Months", "Twenty-four sessions, up to four a month.", "Our best per-session rate: 5% off, $654.76 a session. Total of $15,714.36 over six months. For drivers building a season.", "$2,619.06", "per month"),
    ),
    "boost": ("URACE Boost", "Eight sessions in 30 days.", "A standalone intensive month for drivers preparing for a race or a season: eight track sessions in 30 days at $625 a session, our lowest per-session rate. No contract.", "$5,000", "per month"),
    "para_quem_titulo": "Who is this for?",
    "para_quem": ("Drivers already competing or preparing to compete", "Individuals seeking structured, high-performance training",
                  "Drivers committed to long-term development", "Those looking for real coaching, not just seat time",
                  "Drivers focused on consistency, speed, and race performance"),
    "curriculo": (("Driving Fundamentals", "Master acceleration, braking, cornering, and racing techniques"),
                  ("Theoretical Foundations", "Understand racing principles, track dynamics, and safety protocols"),
                  ("Kart Mechanics", "Develop technical knowledge of kart setup, adjustments, and performance optimization"),
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
    "carreira_extras": ("Press & PR advisory for the driver and family.", "Video content production for the driver's own highlight reels and sponsor material."),
    "inclui_titulo": "Package includes",
    "inclui": ("Kart: high-performance kart provided for each session.", "Coach: expert coaching from professional instructors.",
               "Mechanic: on-site mechanical support to keep the kart race-ready.", "Career planning: ongoing guidance from your career specialist.",
               "In-depth safety instructions.", "Driver Pass: access to the track for the driver.",
               "1 Guest Pass: bring one guest (family or friend) to accompany and support you (additional guests subject to track pass price)."),
    "caminho_titulo": "Your path: Arrive and Drive → Academy → Racing Team",
    "caminho_texto": ("URACE Academy isn't a standalone class: it's the middle rung of a ladder. Drivers usually start at Arrive and "
                      "Drive, where they get their first real laps and we get our first read on their potential. Academy is where "
                      "that potential becomes a plan: four sessions a month of structured coaching, video and data review, and a "
                      "career specialist tracking progress alongside the driving. From there, Academy drivers who are ready move "
                      "up to the Racing Team.",),
    "etapas": (("Experience", "Discover karting and take your first laps with professional guidance.", "icon-experience.webp"),
               ("Develop", "Build technique, discipline, consistency and a competitive mindset through structured training.", "icon-develop.webp"),
               ("Compete", "Gain race experience and learn to perform in competitive environments.", "icon-compete.webp"),
               ("Pursue the next level", "Continue developing with professional coaching, racing experience and long-term guidance.", "icon-pursue.webp")),
    "faq": (("Why motorsport builds champions", ("Karting looks like a hobby from the outside, but the skills it demands behind the wheel "
                                                "are the ones researchers tie to healthy child development. A young driver is constantly "
                                                "reading the track, adjusting their line, and making split-second calls under pressure: "
                                                "fast, consequence-driven decision-making that's hard to practice anywhere else.",)),
            ("Terms and conditions", ("The program price is URACE's fee for coaching, trackside support, kart rental, driver and one guest pass only; anything not in this list is excluded.",
                                      "This training consists of 4 days per month, scheduled once a week; each day has 6 sessions of 10 minutes, a total of 1 hour of track time per day. The arrival time at the track is 8 AM. If less than 40 minutes of track time is achieved, there is a possibility of a proportional credit for a future session, decided case by case.",
                                      "Any damage caused to the kart is not included in this price and will be billed for the costs of repair. If the kart breaks down and it was not caused by the driver, the costs of repair are covered by URACE.",
                                      "Kids under 10 years old must be accompanied by an adult. We provide a childcare assistant for an extra $200/day, requested beforehand.",
                                      "Racing is a high-risk activity. By booking you agree and acknowledge that URACE is not responsible for any injuries, damages or losses of any nature that might happen during track activities or while on site.")),
            ("Refund and rescheduling policy", ("Our service requires planning, preparation, coordination and transportation to the track on our end; for those reasons we do not offer refunds. Rescheduling is available with a minimum notice of 24 hours. With less than 24 hours' notice, a flat fee of $95 is charged, plus the Driver Pass if required.",
                                                "If a training session needs to be rescheduled due to circumstances outside of URACE's control, a fee is charged to cover personnel costs, in addition to any other costs associated with the session.")),
            ("Cancelling the plan", ("The Academy renews month by month. Cancel with 30 days' written notice.",))),
    "fecho": "Future pros start here.",
    "fecho_sub": "Every driver has a next step. Let's find yours.",
    "fecho_cta": ("Join URACE Academy", RESERVAR + "?service=academy"),
}

# ------------------------------------------------------------------ Pro Team (urace.us/pro-team/ + /professional-kart-team-racing-team/)
PRO_TEAM = {
    "caminho": "/pro-team/",
    "antigos": ("/professional-kart-team-racing-team/",),
    "titulo": "Kart Racing Team in Florida - Join the URACE Team",
    "descricao": ("URACE runs a professional kart racing team in Florida: engine programme, coaching, race support and a "
                  "selection path from club karting upward."),
    "eyebrow": "Racing Team · Orlando, FL",
    "h1": "You already race. Now race with a team behind you.",
    "sub": ("URACE prepares the kart, runs the race weekend and puts a professional coach alongside the driver, based at "
            "the Orlando Kart Center and entered in the Florida and national calendars."),
    "foto": "banner-topo-lp-urace-1.webp",
    "cta": ("Talk to our racing team", CONTATO),
    "metodo": ("Our teaching method includes data analysis, on-board video study and explanation of the theories involved "
               "in all the driving aspects we discuss. We offer full support for local, regional and national events."),
    "suporte_titulo": "Full service race support",
    "suporte": (("Travel logistics", "We handle everything; you only need to book your flights and hotel."),
                ("Equipment prep", "Storage, maintenance and transportation to and from the track."),
                ("Engineering", "Setup and data on every session, with the same mechanic who preps the kart."),
                ("Coaching", "A professional coach alongside the driver all weekend."),
                ("Hospitality", "A place for the family in the paddock."),
                ("High speed wifi", "For the data, the video and the team at home.")),
    "opcoes_titulo": "How we work with competitive drivers",
    "opcoes_sub": "Three ways in, depending on where the driver is today.",
    "opcoes": (("URACE Academy", "Not racing yet? Start here.", "Four coached sessions a month with kart, full equipment, maintenance and a professional coach included. Month to month, no minimum term.", "$2,756.90", "per month", "/academy/"),
               ("URACE Boost", "Eight sessions in 30 days.", "A standalone intensive month for drivers preparing for a race or a season: eight track sessions in 30 days at $625 a session, our lowest per-session rate. No contract.", "$5,000", "per month", RESERVAR + "?service=boost"),
               ("Race Weekend Support", "We run the kart. You drive.", "Kart preparation and trackside support at the rounds we are entered in. Race entries, tyres, fuel and consumables are quoted per event and are not part of the fee.", "Let's talk", "per event", CONTATO)),
    "calendario_titulo": "Where we are racing",
    "calendario_sub": "The rounds URACE is entered in. If your driver comes with us, this is the season. Dates and venues as published by the series.",
    "calendario": (("Oct 18, 2026", "SKAPA Winter Series — Rounds 4 & 5"),
                   ("Oct 25, 2026", "AMR Karting Challenge — Round 9, Homestead, Florida"),
                   ("Nov 22, 2026", "AMR Karting Challenge — Round 10, Homestead, Florida"),
                   ("Dec 6, 2026", "Florida Karting Championship — Rounds 11 & 12, AMR Motorplex")),
    "fecho": "Future pros start here.",
    "fecho_sub": "Every driver has a next step. Let's find yours.",
    "fecho_cta": ("Talk to our racing team", CONTATO),
}

# ------------------------------------------------------------------ For Beginners (urace.us/for-beginners/ + /kart-lessons-for-beginners/)
BEGINNERS = {
    "caminho": "/for-beginners/",
    "antigos": ("/kart-lessons-for-beginners/",),
    "titulo": "How to Get Into Karting - Start in Orlando | URACE",
    "descricao": ("Never driven a race kart? Start here. How karting works, what to expect on your first day in Orlando, "
                  "and the path from first lap to competition."),
    "eyebrow": "For Beginners · All ages",
    "h1": "How to Get Into Karting in Orlando",
    "sub": "Your first step to becoming a professional racing driver starts here.",
    "foto": "banner-topo-lp-urace-1.webp",
    "cta": ("Experience karting", "/services/arrive-and-drive/"),
    "primeira_titulo": "First time in a kart?",
    "primeira": ("No stress. We've got you covered. From safety gear to first-time instructions, our team guides every step so "
                 "you can focus on enjoying the ride, learning, and discovering what you're made of.",
                 "At URACE, beginners are treated like future athletes. Our method is structured and serious, for kids who want "
                 "to start young or adults ready to take on a new challenge.",
                 "You'll learn real technique from day one: driving position, control, racing discipline, and decision-making. "
                 "You'll build the right foundation to progress with confidence."),
    "contato_titulo": "Arrive and Drive: first contact with karting",
    "contato": ("One full day, no program and no commitment. The category is set by the driver's age and experience: Baby Kart "
                "(4–7), 4-stroke (7+), 2-stroke (7+) or Adult Shifter (14+, prior experience required). Every session includes "
                "the race kart, all the safety equipment, the mechanic, the track briefing and a professional coach on track "
                "with you. You bring closed shoes.",),
    "proximo_titulo": "Where are you in your racing journey?",
    "proximo": (("Arrive & Drive", "Experience karting for one day.", "Your first opportunity to experience real karting with professional guidance and URACE support. Perfect for first-time drivers and families who want to discover motorsport.", "Starting at $719", "/services/arrive-and-drive/"),
                ("URACE Academy", "Start your development as a racing driver.", "A structured driver development program for young athletes who want to train, improve and build the foundations required for competitive karting.", "Programs starting at $2,619.06/mo", "/academy/"),
                ("Racing Team", "Already competing? Pursue the next level.", "Professional support for competitive drivers who want to improve their performance and pursue higher levels of motorsport.", "Programs starting at $5,000/mo", "/pro-team/")),
    "faq": (("How do I get my child into racing?", ("From four years old a child can drive a Baby Kart and learn driving lines and fundamentals. From seven they fit a 4-stroke, and from fourteen, with experience, the Adult Shifter. Start with one day: a race kart, full gear, a coach watching, and let the coach and the data tell you whether there's something there. Children under ten must be accompanied by an adult at the track.",)),
            ("How do I know if my kid has potential?", ("Lap time on day one tells you almost nothing. What a coach reads is how fast a driver corrects a mistake, whether they repeat it, and how they behave when the session goes badly. That's visible within a few runs, and it's visible in the data rather than in opinion. We'll tell you what we saw honestly, including when the answer is that your child loves driving and isn't a future professional, which is a perfectly good answer.",)),
            ("Am I too old to start racing?", ("For Formula 1, almost certainly: that ladder is normally climbed from childhood. For racing itself, no. Masters karting categories exist precisely for adult drivers, and adults often learn the technical side faster than children because they can absorb data and theory. If your goal is to race competitively, be good, and enjoy it, age is not the barrier.",)),
            ("What do I need to bring?", ("Long pants, closed toe shoes and a jacket. We provide the kart, the safety equipment and the instructions.",))),
    "fecho": "Every driver has a next step. Let's find yours.",
    "fecho_sub": ("Whether you want to experience karting for the first time, begin structured driver development or pursue "
                  "higher levels of competition, URACE is ready to help you move forward."),
    "fecho_cta": ("Book my first day", "/services/arrive-and-drive/"),
}

# ------------------------------------------------------------------ Career (urace.us/the-driver-factory/ + /plan-your-career/)
CAREER = {
    "caminho": "/career/",
    "antigos": ("/the-driver-factory/", "/plan-your-career/"),
    "titulo": "How to Become a Professional Racing Driver | URACE Orlando",
    "descricao": ("How to become a racing driver, step by step: where karting fits, what a real development path looks like, "
                  "and what it costs, from a simulator seat in Orlando to Formula 1, IndyCar or NASCAR."),
    "eyebrow": "Career Plan · Orlando",
    "h1": "How to become a racing driver: one ladder. Start at the bottom.",
    "sub": ("Nobody is born on a grid. Every professional driver climbed a ladder, and every rung of it was paid for and "
            "earned. This page is that ladder, laid out end to end, from a simulator seat in Orlando to Formula 1, IndyCar "
            "or NASCAR. We run the bottom of it and we prepare drivers for the rest."),
    "foto": "enzo-1.webp",
    "cta": ("Find my next step", CONTATO),
    "degraus_titulo": "The URACE ladder",
    "degraus": (("Sim 2 Grid", "From $60 an hour, $150 with a coach, $1,200 a month for twelve coached hours. Opening 1 November 2026.", "/services/#sim2grid"),
                ("Arrive and Drive", "A full day in a real race kart, with the kart, the gear and a coach: $719.", "/services/arrive-and-drive/"),
                ("URACE Academy", "Four coached sessions a month, $2,756.90, dropping to $2,688.43 over three months and $2,619.06 over six.", "/academy/"),
                ("Racing Team", "We prepare the kart and run the race weekend; the driver races the Florida and national calendars.", "/pro-team/")),
    "perguntas_titulo": "Questions people actually ask",
    "perguntas_sub": "Straight answers, including the ones that cost us a sale.",
    "faq": (("Does my kid show potential?", ("There's one honest way to find out, and it isn't a quiz. Put them in a real race kart with a coach watching, and read the data afterwards. One day tells us more than a year of wondering, and we'll tell you what we actually saw, including when the answer is \"they love it, and that's enough\".",)),
            ("I'm over 18. Is it too late?", ("For Formula 1, honestly, yes: that route is built around drivers already karting at ten, and it closes in your teens. For racing, no. Stock cars and sports cars have no age-gated junior ladder, and Masters leagues exist precisely for drivers who started as adults. We coach adults and seven-year-olds on the same day, on the same circuit.",)),
            ("How do I become a racing driver?", ("You start in a kart, you get coached, and you build a record that the next category will look at. There is no shortcut, and no talent-spotting shortcut either: every professional on a grid today climbed the same kind of ladder, one paid rung at a time. What changes between drivers is how early they start, how good the coaching is, and how well the season is planned.",)),
            ("How much does it cost to start racing?", ("At URACE the ladder starts at $60 for an hour in the simulator on your own, or $150 with a coach beside you. Twelve coached hours a month is $1,200. A full day in a real race kart, with kart, gear and a coach all day, is $719. The Academy is $2,756.90 a month, dropping to $2,688.43 over three months and $2,619.06 over six. The circuit's track fee is separate and paid to the Orlando Kart Center: $100–230 for a driver pass Wednesday to Friday, $100–125 on weekends, $22 for a spectator.",)),
            ("How do I get into NASCAR?", ("The stock car route leaves karting earlier than the open-wheel ones. A driver typically moves from karting into Legends or Bandolero cars, then regional Late Models, then the ARCA Menards Series, then NASCAR's three national series in order: the Craftsman Truck Series, the Xfinity Series, and the Cup Series. Because the branch happens young, the decision about which destination you're aiming at matters earlier than most families expect.",)),
            ("How do I get to IndyCar?", ("Through the Road to Indy, which is the most clearly defined ladder in motorsport: USF Juniors, then USF2000, then USF Pro 2000, then Indy NXT, then IndyCar. Each rung has a scholarship structure attached to winning it, which makes it the cheapest of the single-seater paths to a top-level seat, and the reason we map American drivers onto it early.",)),
            ("How do I get to Formula 1?", ("Karting, then Formula 4, then Formula Regional, then FIA Formula 3, then FIA Formula 2, then one of twenty seats in the world. It is the longest and most expensive of the three routes and the one where a karting record counts for most, which is why drivers aiming at it start young and race nationally as early as they can. Nobody can promise this rung. What can be promised is that every rung below it is real.",)),
            ("Can a simulator really prepare you for real racing?", ("For circuit knowledge, braking points and racecraft, yes: our own drivers learn a circuit on the simulator before they ever see it. A full motion cockpit loads the driver up in the corners and punishes the same mistakes a real car does. What it can't teach is the physical load of a real race weekend, which is why it's the first rung and not the only one.",)),
            ("Where are you based?", ("We operate at the Orlando Kart Center, 10724 Cosmonaut Blvd, Orlando FL 32824, an 8/10 mile professional kart circuit just off the Florida Turnpike, minutes from most of Orlando's attractions. URACE is a racing team, not the racetrack: we provide coaching and programs at a third-party circuit and follow their rules and operating hours.",))),
    "pessoa_titulo": "We are building a person, not only a driver",
    "pessoa": ("Karting looks like a hobby from the outside. What it actually asks of a seven-year-old is to read a track, adjust a line, and make consequence-driven decisions at speed, over and over, for an hour. There are very few childhood activities that demand that much processing per second.",
               "Every URACE session is built around that cycle. A coach doesn't only teach a driving line: they walk the driver through onboard video and lap-time data, then set one specific target for next time. Goal, attempt, review, adjust. It happens to be happening at 50 mph.",
               "We're not claiming karting replaces school, coaching or therapy. We're saying the driver who comes back to you is more focused, steadier under pressure and harder to rattle, and that part is yours to keep whether or not they ever reach a professional grid."),
    "fotos": (("enzo-1.webp", "Enzo Vidmontiene, URACE driver"), ("leonardo-1.webp", "Leonardo Escorpioni, URACE driver"), ("emmo-2.webp", "Emmo Fittipaldi, URACE driver")),
    "profissional_titulo": "And a professional, not only an athlete",
    "profissional": ("Most people who make a living in motorsport never drive for one. They engineer, they manage, they run teams, they handle the commercial side. A driver who understands that industry is worth more inside it, and has somewhere to go if the seat never comes.",
                     "So we teach the business alongside the driving. From the Academy onward a driver works with a career specialist, not only a coach. By the time they reach the Racing Team, the work is as much about building a professional as a lap time."),
    "profissional_itens": ("Helmet and livery design, team kit, the visual identity a driver carries from one category to the next.",
                           "How to talk to media, how to handle a bad weekend in public, and advisory for the driver and the family.",
                           "Building the channels, producing highlight reels and sponsor material that a brand can actually use.",
                           "Shaping the driver's story and connecting it with brands once there's a record worth presenting.",
                           "Which categories, which tracks, what it costs, and how it fits around school and family life.",
                           "Reading a contract, running a weekend, working with a mechanic and an engineer as a professional does."),
    "aviso": ("URACE runs the four red rungs. The championships above them are run by their own organisers and governing bodies. "
              "URACE is not affiliated with, endorsed by or a partner of any of them: we prepare and enter drivers, nothing more."),
    "fecho": "You don't need to know which rung is yours",
    "fecho_sub": ("Tell us who the driver is and whether they've been in a race kart before. That one answer decides the rest, "
                  "and we'll tell you honestly where to start, even if it's the cheapest rung on the ladder."),
    "fecho_cta": ("Find my next step", CONTATO),
}

# ------------------------------------------------------------------ About (urace.us/about/)
ABOUT = {
    "caminho": "/about/",
    "titulo": "About URACE - Kart School & Racing Team in Orlando",
    "descricao": ("URACE is a professional kart school and racing team in Orlando, taking drivers from their first lap to "
                  "national competition."),
    "eyebrow": "About · since 2016 in Orlando",
    "h1": "Since 2016, building champions on and off the race track",
    "foto": "sobre.webp",
    "historia_titulo": "About URACE",
    "historia": ("Racing has been our passion for generations! Our kart racing story started 26+ years ago in Brazil. Team "
                 "principal Italo Silveira began by racing karts, winning numerous Brazilian regional and national championships. "
                 "A successful professional car racing career followed in the internationally recognized Brazilian stock car "
                 "series. In 2016, Italo moved to Florida and launched URACE, a karting team, to pass along his experience:",),
    "historia_itens": ("Kart School, for beginners learning about the sport;", "URACE Academy, for local drivers racing in Orlando, FL;",
                       "URACE Pro Team, for drivers ready to challenge for the podium nationwide."),
    "historia_fecho": "URACE builds winners on and off the tracks due to experience, professionalism, and the passion we have for the sport.",
    "metodo_titulo": "Structure & methodology",
    "metodo_intro": "URACE is built on the real-world experience of a former pro driver, and that makes all the difference. Our method combines:",
    "metodo": ("Pro-level driving technique", "In-depth understanding of kart setup & dynamics", "High-performance mental training and decision-making", "Constant progress through individual coaching"),
    "metodo_fecho": "From first lap to national-level racing, our method prepares drivers every step of the way.",
    "diferente_titulo": "Why is URACE different?",
    "diferente": ("URACE is different because it was not created as a traditional race team, but as a complete driver development "
                  "program designed by Italo Silveira, someone who has lived the sport firsthand and achieved real results. He began "
                  "competing at the age of seven and has been coaching drivers since 2004, with a deep understanding of every aspect "
                  "of racing. Because of this, our drivers learn:",),
    "diferente_itens": ("Not just how to drive, but how to think like professional drivers;", "Not just how to compete, but how to develop the mindset and preparation required to win;",
                        "Not just how to improve quickly, but how to achieve consistent excellence."),
    "diferente_fecho": "This combination of experience, methodology, and close mentorship is what makes URACE a reference in driver development.",
    "equipe_titulo": "Our team",
    "equipe": ("URACE is led by Italo Silveira, a former professional race car driver and the founder of the team. His career includes:",),
    "equipe_itens": ("Starting in karting at the age of seven;", "Regional and national titles in Brazil;", "Competing in Stock Car, the country's premier racing category;",
                     "Nearly three decades of experience driving, coaching, and developing drivers."),
    "equipe_fecho": ("Italo began coaching drivers at just fourteen years old and has continued this work throughout his entire career, "
                     "building a comprehensive understanding of athlete development, technical progression, and the formation of a "
                     "winning mindset, both on and off the track. Alongside him, Italo is supported by a team of experienced "
                     "professionals at URACE who are deeply passionate about the sport. They are responsible for preparing the "
                     "equipment, overseeing training sessions, guiding drivers, and ensuring continuous improvement."),
    "visao": ("We are working to become the most victorious karting team in the United States. We are a reference in professional "
              "driver training, proving many times to train drivers that excel and become a reference at the national level in "
              "record time. Now our goal as a team is to retain those drivers so they can win as every URACE driver does: win wearing our colors."),
    "missao": ("\"I founded URACE to provide the support and mentorship I wish I had received during my own career. My mission is to "
               "transform the lives of drivers who have both talent and resources to become professionals, and to truly help them get there.",
               "I always had the necessary conditions to go far: skill, dedication, and investment, but I did not reach the professional "
               "level because I lacked the right support at a critical moment. Even today, whenever I return to the track, my results "
               "reflect the depth of my knowledge and my racecraft.",
               "That is exactly why URACE exists: to give drivers the structure, knowledge, and competitive advantage I did not have, "
               "allowing them to reach their full potential, whether they are just starting their journey or already pursuing "
               "excellence at the highest level.\" — Italo Silveira"),
    "suporte_titulo": "Full service race support",
    "suporte": ("URACE is a full-service racing team built to support drivers at every level. We take care of storage, maintenance, "
                "transportation to and from the track, and full trackside support. From preparation to race day execution, we handle "
                "every detail so you can focus on what truly matters: driving. You show up. You race. We handle the rest.",),
    "seguranca_titulo": "Safety",
    "seguranca_intro": "Safety is a top priority at every stage of the URACE process. Every training, session, and race follows strict standards to ensure that:",
    "seguranca": ("Drivers use approved safety gear", "Clear instructions are given before each session", "All driving is done in a supervised, controlled environment",
                  "Skill development focuses on control, awareness, and risk prevention"),
    "seguranca_fecho": "Our mission is to help drivers grow with confidence, discipline, and the protection needed to aim high.",
    "fecho": "Do you still have questions?",
    "fecho_sub": "Contact our team to get all the information about our programs and services.",
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
    "sub": "New lead, question, or planning a group or corporate event? Fill out the form and our team will get back to you.",
    "assuntos": (("arrive-and-drive", "Arrive and Drive"), ("academy", "URACE Academy"), ("coaching", "Professional Coaching"),
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
    "conformidade": ("The Web Content Accessibility Guidelines (WCAG) define requirements for designers and developers to improve "
                     "accessibility for people with disabilities. It defines three levels of conformance: Level A, Level AA, and "
                     "Level AAA. URACE is partially conformant with WCAG 2.1 level AA. Partially conformant means that some parts "
                     "of the content do not fully conform to the accessibility standard.",),
    "feedback_titulo": "Feedback",
    "feedback": "We welcome your feedback on the accessibility of URACE. Please let us know if you encounter accessibility barriers:",
    "data_titulo": "Date",
    "data": "This statement was created on 15 April 2026 using the W3C Accessibility Statement Generator Tool.",
}

PAGINAS = (ACADEMY, PRO_TEAM, BEGINNERS, CAREER, ABOUT, CONTACT, ACCESSIBILITY)
