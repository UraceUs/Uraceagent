"""As páginas de serviço do site novo (#164), com o texto do urace.us de 13/10/2026 (#207).

Dono, 08/10: *"estamos refazendo todo o site ... eu preciso de uma cópia com as novas URLs e também
com a nossa identidade visual"*; dono, 13/10: *"vou pegar o copy que tá no site atual e jogar naquele
outro site"*. Nada aqui é inventado: cada texto saiu da página citada. O que fica diferente do site
atual, de propósito (decisões do dono, ver `conteudo.py`): remarcação com 24 h, idade dos karts do
produto, endereço com o Box 3, os botões de reservar levam à reserva do site e o passo a passo da
reserva é o do site (o atual fala do carrinho do WooCommerce).

Preço de serviço não é texto fixo aqui: o do Arrive and Drive vem de `conteudo.KARTS` (o mesmo da
reserva); o resto fica sem preço até existir no painel.

Cada página é um dicionário; `paginas_site.servico()` desenha todas com o mesmo esqueleto.
"""
from command_center.vitrine.conteudo import DEPOIMENTOS_EVENTOS, FAQ_COMUM, GRUPOS, HORARIO, SITE  # noqa: F401

RESERVAR = "/ops/portal/reserve"
CONTATO = "/contact/"

# As idades da decisão do dono de 08/10 (o site atual ainda diz "Adult Kart 4-Stroke: Age 11+").
KARTS_FAQ = (
    "Baby Kart: for kids aged 4 to 7, perfect to learn the driving lines and fundamentals of racing.",
    "4-stroke: ages 7+, the standard entry for kids and adults, with a 4-cycle engine capable of speeds exceeding 50 MPH.",
    "2-stroke: ages 7+, for drivers who already have track time, with a 2-cycle engine reaching speeds of 65+ MPH.",
    "Adult Shifter: ages 14+, prior experience required, the fastest kart we run.",
)

ENDERECO = f"{SITE['endereco']['rua']}, {SITE['endereco']['cidade']}, {SITE['endereco']['estado']} {SITE['endereco']['cep']} — {SITE['endereco']['onde']}."

# O passo a passo da reserva do site (agenda + área do cliente), no lugar do "Click add to cart" do WooCommerce.
COMO_RESERVAR = (
    "Pick the kart, the day and the time on this page.",
    "Sign in or create your URACE account and tell us who the driver is (height and weight, so the kart is prepared).",
    "Pay the invoice online (session + refundable security deposit) and sign the waiver.",
    "Your spot confirms by itself. Show up ready to have a blast!",
)

FECHO_SERIO = "If you're serious about racing, this is where it starts. Shall we begin?"
FECHO_PRECO = "With an affordable price aimed at the democratization of Karting."

TRAZER = ("MUST wear long pants, closed toe shoes and a jacket.", "Make a reservation",
          "Come prepared for fun and leave with lasting smiles.")

# ------------------------------------------------------------------ Kart School (urace.us/services/kart-school/)
KART_SCHOOL = {
    "caminho": "/services/kart-school/",
    "titulo": "Kart Racing Lessons in Orlando - Learn to Race | URACE",
    "descricao": ("Kart and racing lessons in Orlando for every level. Practical training and theory in real race karts, "
                  "with a professional coach on track with you."),
    "eyebrow": "Kart School · Orlando, FL",
    "h1": "Kart School in Orlando",
    "sub": ("Become a racing driver. Start at URACE Kart School. Practical training, theory, real karts, and a professional "
            "environment. For kids and adults."),
    "foto": "group-482140-1.webp",
    "cta": ("Be part of the team", RESERVAR),
    "fornece_titulo": "What to expect from your Kart School",
    "fornece": ("Kart: High-performance kart provided for each session.", "Coach: Expert coaching from professional instructors.",
                "In-depth safety instructions.", "Driver Pass: Access to the track for the driver.",
                "1 Guest Pass: Bring one guest (family or friend) to accompany and support you (Additional guests subject to track pass price)."),
    "trazer": TRAZER,
    "porque_titulo": "Kart School with real training, theory, and pro coaching",
    "porque": ("Professional Track - where real races happen.", "Theory and mechanics simplified", "Mentorship by winning drivers",
               "Confidence, reflexes and racing mindset", "Monthly Program = Continuous Evolution"),
    "para_quem_titulo": "Who is this for?",
    "para_quem": ("Kids aged 6–14", "Beginners or early-stage racers", "Families serious about long-term development",
                  "Parents looking for real coaching, not just seat time", "Drivers aiming for confidence, speed, and race results"),
    "curriculo": (("Driving Fundamentals", "Master acceleration, braking, cornering, and racing techniques"),
                  ("Theoretical Foundations", "Understand racing principles, track dynamics, and safety protocols"),
                  ("Kart Mechanics", "Learn about chassis, engine, and component maintenance"),
                  ("Practical Sessions", "Guided track time with expert instructors")),
    "objetivos": ("Develop essential racing skills and muscle memory", "Understand kart handling and karting mechanisms",
                  "Build confidence and mental strength", "Prepare for competitive racing or advanced training"),
    "passos_titulo": "How to book your Kart School session",
    "passos": COMO_RESERVAR,
    "faq": (("How will this work?", COMO_RESERVAR),
            ("The Kart School", ("Embark on a comprehensive racing education with URACE Kart School, designed specifically for "
                                 "novice drivers eager to excel. Our structured program combines theoretical knowledge with hands-on "
                                 "training, equipping students with the skills and confidence to succeed.",)),
            *FAQ_COMUM),
    "fecho": FECHO_SERIO,
    "fecho_sub": FECHO_PRECO,
    "fecho_cta": ("Start driving today", RESERVAR),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

# ------------------------------------------------------------------ Professional Coaching
COACHING = {
    "caminho": "/services/professional-coaching/",
    "titulo": "Professional Kart Coaching in Orlando | URACE",
    "descricao": ("Kart coaching in Orlando for drivers who already race. Video, telemetry and data analysis with a "
                  "professional coach to find real lap time."),
    "eyebrow": "Professional Coaching · Orlando, FL",
    "h1": "Professional Kart Racing Coaching in Orlando",
    "sub": ("Get faster with expert-level kart training and data-driven analysis. A custom training session designed to sharpen your racing technique. Full coaching, video breakdown, benchmark "
            "comparison and hands-on learning — all in 4 hours."),
    "foto": "group-482140-1-1.webp",
    "cta": ("Be part of the team", RESERVAR),
    "fornece_titulo": "What to expect from your Coaching Session",
    "espera": ("Tailored Training Program", "Professional Coaching, Data & Video Analysis", "Technique & Mindset Training",
               "Advanced Safety Briefing", "Performance Tracking", "\"Lead and Follow\" option (additional fee applies)."),
    "fornece": ("1-Day Practice (4 hours)", "High-Performance Kart Provided", "Expert Coaching from Professional Instructors",
                "In-Depth Safety Instructions"),
    "trazer": ("Your kart (or you can rent ours!)", "Your personal safety equipment (We may have equipment to lend at no cost, inquire beforehand)"),
    "porque_titulo": "Real coaching from a championship-level kart team",
    "porque": ("Professional Track - Where real races happen.", "Theory and mechanics simplified", "Mentorship by winning drivers",
               "Confidence, reflexes and racing mindset", "Immersive 4-hour practice session"),
    "para_quem_titulo": "Who can join Professional Kart Coaching in Orlando?",
    "para_quem": ("Kids aged 6–14", "Beginners or early-stage racers", "Families serious about long-term development",
                  "Parents looking for real coaching, not just seat time", "Drivers aiming for confidence, speed, and race results"),
    "passos_titulo": "How the Professional Coaching Works",
    "passos_intro": "Your step-by-step path to becoming a driver:",
    "passos": ("Choose your kart type or use your own", "Decide if you want “Lead & Follow” training",
               "Complete checkout and receive confirmation", "Our team contacts you to schedule and collect data",
               "Show up ready — and leave as a faster driver"),
    "faq": (("Professional Coaching", ("Lead and Follow is an additional fee for a partner trainer to make your driving or "
                                       "training experience more exciting, if you don’t wanna do it alone.",
                                       "Available training days: Experiences are available every day, 8 AM – 8 PM. Add your "
                                       "classes to the cart and contact us to inquire about the date you would like to attend.",
                                       "All weekday training sessions must be confirmed by Sunday. All weekend sessions must be "
                                       "confirmed 24h in advance. Please call if you have any questions.")),
            ("Which kart?", KARTS_FAQ),
            ("Track fees (paid to the Orlando Kart Center)", ("Driver pass Wednesday to Friday $100~230", "Driver pass Saturday and Sunday $100~125",
                                                               "Spectator pass any day $22")),
            *FAQ_COMUM),
    "fecho": FECHO_SERIO,
    "fecho_sub": FECHO_PRECO,
    "fecho_cta": ("Let’s start training", RESERVAR),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

# ------------------------------------------------------------------ Intensive Training Camp
CAMP = {
    "caminho": "/services/intensive-training-camp/",
    "titulo": "Intensive Kart Racing Camp in Orlando | URACE",
    "descricao": ("Five days of intensive kart training in Orlando. Structured curriculum, race karts, coaching and data "
                  "review, built for drivers who want to progress."),
    "eyebrow": "Intensive Training Camp · Orlando, FL",
    "h1": "Intensive Kart Racing Camp in Orlando",
    "sub": ("Build Skills. Build Confidence. Fuel the Passion. 5 Days of Racing, a Lifetime of Memories! Give your child a chance to grow on and off the track with URACE's "
            "Intensive training camp experience."),
    "foto": "group-482140-3.webp",
    "cta": ("Ready to Race With Us?", CONTATO),
    "intro_titulo": "An Unforgettable Journey Into Racing",
    "intro": ("URACE Intensive training camp runs from Wednesday to Sunday, with 4 hours of daily training, designed for "
              "young drivers who want to go beyond the basics and dive deeper into the art of racing. In a supportive, "
              "exciting, and motivating environment, kids will learn valuable skills that go far beyond the track — from "
              "focus and discipline to teamwork and self-confidence.",),
    "porque_titulo": "Kart Racing Camp with real training, theory, and pro coaching",
    "porque": ("Real track time with professional karts", "Theory and mechanics simplified", "Mentorship by winning drivers",
               "Confidence, reflexes and racing mindset", "Data + video analysis to boost performance"),
    "porque_fecho": "*limited spots",
    "fornece_titulo": "What’s included in the URACE Intensive training camp",
    "fornece_intro": ("A complete 5-day journey into the world of kart racing, combining physical practice with strategy, "
                      "analysis, and mechanical learning — all supported by professional coaches."),
    "fornece_rotulo": "What’s included",
    "fornece": ("20+ hours of coaching", "Small group training (personalized attention)", "High-performance kart included",
                "Track pass + 1 guest pass per day", "Safety gear & full guidance", "Friendly, high-energy learning environment"),
    "trazer": TRAZER,
    "dias_titulo": "5 days of immersive training",
    "dias_intro": "What to Expect:",
    "dias": (("Day 1: On-Track Coaching + Post-Session Analysis", "Track sessions focused on improving driving skills, followed by a detailed performance breakdown with feedback and tips for improvement.", "frame-1321317985.webp"),
             ("Day 2: Race Strategy & Track Reading", "Emphasis on race strategy and track awareness, helping drivers develop quick decision-making skills and improve their vision and understanding of the racing line.", "frame-1321317985-1.webp"),
             ("Day 3: Data Analysis & Kart Setup", "Data review sessions aimed at enhancing performance, along with an in-depth explanation of kart setup and how to make adjustments for optimal results.", "frame-1321317985-2.webp"),
             ("Day 4: Kart Assembly & Basic Maintenance", "Hands-on training in kart assembly, adjustments, and basic maintenance—giving drivers more independence and technical understanding of their equipment.", "frame-1321317985-3.webp"),
             ("Day 5: Final Coaching Session + Evaluation", "A final on-track session focused on overall progress, review of everything covered during the camp, and guidance on next steps for continued development.", "frame-1321317985-4.webp")),
    "para_quem_titulo": "Who should join the URACE Intensive training camp?",
    "para_quem": ("Young drivers looking to level up (Age 5+)", "Kids who want to explore karting in a fun and safe environment",
                  "Drivers preparing for upcoming championships", "International drivers visiting Orlando looking for intensive training"),
    "passos_titulo": "How the URACE Intensive training camp works",
    "passos_intro": "Here’s how to get started and what to expect during your racing week:",
    "passos": ("Sign Up Online", "Confirmation & Driver Info", "Arrive at the Track Ready to Go", "Train, Learn, Improve",
               "Finish the Week a Better Driver"),
    "faq": (("Intensive training camp", ("Are you visiting Orlando and looking for something more exciting than the go karts at "
                                         "Magic Kingdom’s Tomorrowland Speedway or the monotony of Epcot’s Test Track? This "
                                         "experience is for kids and adults, all ages are welcome!",
                                         "Book your reservation and be ready to have a blast!",
                                         "These are not the typical put-put go-karts, they are authentic, professional racing karts.",
                                         "Available Experience Days: Experiences are available every day, 8 AM – 8 PM. Please "
                                         "confirm availability when booking.")),
            ("Which kart?", KARTS_FAQ),
            *FAQ_COMUM),
    "fecho": "Ready to Race With Us?",
    "fecho_sub": "Spots are limited to keep the experience personal and impactful. Secure your seat today and make this summer one to remember.",
    "fecho_cta": ("Secure my Winter Camp spot", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

# ------------------------------------------------------------------ eventos (aniversário, corporativo, grupos)
# O "Grand Prix" / "Championship" do site atual é só o título, sem texto embaixo: aqui também.
DECORACAO = ("You’re welcome to bring your own decorations, food, drinks, or anything else to make the party feel extra "
             "special and personal! We have a cozy lounge area where you can set up a birthday table or snack station if "
             "you’d like. The only thing we ask is a small cleaning fee after the event, just to help us keep the space "
             "fresh and ready for the next celebration.")

FORMATOS_FESTA = (
    ("Fun races", "For a relaxed, good-vibes kind of day:", ("Laid-back racing sessions", "Driver rotation between rounds", "Pace and format fully customized")),
    ("Birthday Grand Prix", "", ()),
    ("Build your experience your way", DECORACAO, ()),
    ("Perfect for all ages! (Participants must be 5+ to race)", "", ()),
)

PASSOS_EVENTO = ("Contact us with your date, group size, and preferences", "Choose kart types and race formats",
                 "We handle safety, gear and event flow", "Show up, race, and celebrate")
PASSOS_EVENTO_TITULO = "How to book your group Karting Event"
PASSOS_EVENTO_INTRO = "Your step-by-step guide to celebrating with us:"

# "+$50 per guest" é a taxa de convidado; o preço por piloto sai de KARTS (paginas_site.servico)
INVESTIMENTO_EVENTO = "Starting at {preco} per racing participant +$50 per guest (non-racers)"

BIRTHDAY = {
    "caminho": "/services/birthday-party/",
    "antigos": ("/birthday-party/",),                   # o menu do urace.us de hoje aponta para cá
    "titulo": "Kart Racing Birthday Parties in Orlando | URACE",
    "descricao": ("Throw a birthday party on a real racing track in Orlando. Racing karts, safety gear and coaches included, "
                  "organised end to end by the URACE team."),
    "eyebrow": "Birthday Party · Orlando, FL",
    "h1": "Kart Racing Birthday Parties in Orlando",
    "sub": ("Celebrate with speed, adrenaline, and a fully personalized experience. At URACE, every birthday is one of a kind. You tell us how you want to celebrate — and we’ll build a fun, safe, "
            "and unforgettable event for all ages."),
    "foto": "group-482141.webp",
    "cta": ("I want to book my birthday with URACE", CONTATO),
    "formatos_titulo": "How your party can happen",
    "formatos_intro": ("No pre-set packages. Just possibilities. You mix and match to create the perfect event for your crew. "
                       "Here are some ways to make your birthday celebration even more epic:"),
    "formatos": FORMATOS_FESTA,
    "logistica_titulo": "Event Setup",
    "logistica": ("Up to 6 drivers can race at the same time.", "Guests can cheer from our designated viewing areas.",
                  "Our team takes care of everything, ensuring your event runs smoothly, safely, and stress-free."),
    "extras_titulo": "Extras to make it even more special",
    "extras": ("Custom trophies", "Medals", "Professional photos & video", "Personalized T-shirts, caps, race suits, or gift kits", "Official race certificate"),
    "passos_titulo": PASSOS_EVENTO_TITULO,
    "passos_intro": PASSOS_EVENTO_INTRO,
    "passos": PASSOS_EVENTO,
    "faq": FAQ_COMUM,
    "investimento": INVESTIMENTO_EVENTO,
    "fecho": "You dream it. URACE makes it happen.",
    "fecho_sub": "Turn your birthday into a high-speed, unforgettable, fully custom experience: just the way you imagined it.",
    "fecho_cta": ("Want my event on track!", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

CORPORATE = {
    "caminho": "/services/corporate-events/",
    "antigos": ("/corporate-events/",),
    "titulo": "Corporate Karting Events in Orlando | URACE",
    "descricao": ("Corporate events on a professional racing track in Orlando. Real race karts, full safety gear and coaching - "
                  "a team day people actually remember."),
    "eyebrow": "Corporate Events at URACE",
    "h1": "Corporate Karting Events in Orlando",
    "sub": ("Boost team building, motivation, and performance with an experience that combines adrenaline, strategy, and real "
            "teamwork. At URACE, no two events are the same: you choose the format, and we create a dynamic, safe, and "
            "unforgettable experience for your team."),
    "foto": "group-482140.webp",
    "cta": ("I want to book my corporate event", CONTATO),
    "beneficios_titulo": "Why host a corporate event at URACE?",
    "beneficios_intro": ("Karting isn’t just fun: it’s a powerful, hands-on way to develop essential team skills. Our race formats "
                         "naturally build decision-making, focus, collaboration, and communication — all in an exciting, "
                         "real-time environment. Key benefits for your company:"),
    "beneficios": (("Teamwork", "Group races strengthen collaboration and unity."),
                   ("Fast Communication", "Race strategy requires quick coordination and clear communication."),
                   ("Confidence Building", "Taking the wheel builds both personal and professional confidence."),
                   ("Leadership & Decision-Making", "On-track dynamics push quick thinking and smart risk-taking."),
                   ("Emotional Management", "High-speed pressure sharpens focus, self-control, and resilience."),
                   ("Cross-Team Bonding", "Breaks down silos and connects employees from different departments."),
                   ("Motivating Atmosphere", "Intense, energizing experience that boosts engagement and company culture."),
                   ("Unforgettable Experience", "Your team leaves pumped, connected — and talking about it for weeks.")),
    "formatos_titulo": "How your event can run",
    "formatos_intro": ("No one-size-fits-all packages — just flexible options you can build around your team’s goals, whether "
                       "it's connection, celebration, training, or recognition. Here are a few popular formats:"),
    "formatos": (("Fun Team Races", "Perfect for casual bonding and relaxed competition.", ("Easygoing heats", "Driver rotation", "Flexible pace based on group")),
                 ("Corporate Championship", "", ()),
                 ("Customize your experience", DECORACAO, ())),
    "para_quem_titulo": "For all types of teams",
    "para_quem_intro": "We adapt the experience to your group’s size and event goals:",
    "para_quem": ("Team-building sessions", "Leadership training", "Cross-department challenges", "Reward and incentive events", "Small squads or large companies"),
    "para_quem_fecho": "Our staff leads every event with a clear, focused briefing — keeping things safe, organized, and at the perfect pace for your group.",
    "logistica_titulo": "Event Logistics",
    "logistica": ("Up to 6 drivers can be on track at once", "Guests and team members can watch and cheer from special viewing zones",
                  "Dedicated staff to manage and run your event", "Full, start-to-finish scheduling and coordination", "Complete support to customize your race format"),
    "extras_titulo": "Extras to take your event to the next level",
    "extras": ("Branded trophies", "Medals", "Professional photo and video coverage", "Customized shirts, caps, race suits, or group kits", "Official race certificate"),
    "porque_titulo": "Why Choose URACE?",
    "porque_intro": "At URACE, we go beyond the laps. Our Driving Experience is not only exciting, it’s:",
    "porque": ("Safe – with safety gear and staff supervision", "Inclusive – fun for kids, teens, and adults",
               "Memorable – guaranteed to be a highlight of your celebration", "Customizable – ask us about group sizes, extra sessions, or branded surprises"),
    "passos_titulo": PASSOS_EVENTO_TITULO,
    "passos_intro": PASSOS_EVENTO_INTRO,
    "passos": PASSOS_EVENTO,
    "faq": FAQ_COMUM,
    "investimento": INVESTIMENTO_EVENTO,
    "fecho": "You bring your team. URACE delivers an unforgettable experience.",
    "fecho_sub": "Turn your corporate event into a moment of connection, adrenaline, and impact, 100% personalized for your company.",
    "fecho_cta": ("I want my corporate event on track!", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

GROUPS = {
    "caminho": "/services/group-events/",
    "antigos": ("/services/group-events-social-gatherings/", "/group-events-social-gatherings/"),
    "titulo": "Group Kart Racing Events in Orlando | URACE",
    "descricao": ("Group karting in Orlando for friends, clubs and social gatherings. Real race karts, gear and coaching "
                  "included, built around your group size and pace."),
    "eyebrow": "Group Events · Orlando, FL",
    "h1": "Group Kart Racing Events & Social Gatherings in Orlando",
    "sub": ("Bring your crew together with adrenaline, fun, and a one-of-a-kind experience. At URACE, every group event is "
            "custom-built. You pick the vibe and we’ll design a safe, thrilling, and unforgettable experience for your "
            "friends, family, travel team, or crew."),
    "foto": "group-482140-2.webp",
    "cta": ("I want to book a group event", CONTATO),
    "porque_titulo": "Why celebrate with URACE?",
    "porque_intro": ("We mix excitement, challenge, and laughs, perfect for bonding and making memories. Karting brings people "
                     "together through teamwork, friendly rivalry, and tons of fun. Top reasons to bring your group to URACE:"),
    "porque": ("Guaranteed fun", "Real connection and team spirit", "Personal breakthrough moments", "High-energy, relaxed atmosphere", "An unforgettable experience"),
    "formatos_titulo": "How your event can run",
    "formatos_intro": ("No off-the-shelf packages, just flexible options designed around your group’s goals, whether it’s to "
                       "celebrate, connect, compete, or just have a blast. Options include:"),
    "formatos": (("Fun races", "Light, fun, and packed with laughs.", ("Chill racing heats", "Driver rotation", "Fully adjustable pace and flow")),
                 ("Mini Championship", "", ()),
                 ("Customize your experience", DECORACAO, ())),
    "para_quem_titulo": "For all types of groups",
    "para_quem_intro": "We tailor each event to your crew’s size and vibe:",
    "para_quem": ("Friend groups", "Families", "Travel crews", "Clubs, communities, and social teams", "Special celebrations", "Informal get-togethers"),
    "para_quem_fecho": "Our team leads a simple, friendly briefing that’s perfect for first-timers — and we crank it up for experienced drivers.",
    "logistica_titulo": "Event Setup",
    "logistica": ("Up to 6 drivers can race at the same time.", "Guests can cheer from our designated viewing areas.",
                  "Dedicated staff for guidance and support", "Full start-to-finish coordination", "Fully customizable experience"),
    "extras_titulo": "Extras to make it even more special",
    "extras": ("Personalized trophies", "Medals", "Pro photos and videos", "Custom shirts, caps, or event kits", "Official race certificate"),
    "passos_titulo": PASSOS_EVENTO_TITULO,
    "passos_intro": PASSOS_EVENTO_INTRO,
    "passos": PASSOS_EVENTO,
    "faq": FAQ_COMUM,
    "investimento": INVESTIMENTO_EVENTO,
    "fecho": "Turn your group gathering into a moment of speed, connection, and epic memories.",
    "fecho_sub": "",
    "fecho_cta": ("I want to make a reservation for my group", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

SERVICOS = (KART_SCHOOL, COACHING, CAMP, BIRTHDAY, CORPORATE, GROUPS)

# ------------------------------------------------------------------ o hub (urace.us/services/)
# Os cartões levam o texto de cada página do site atual (o hub de hoje só tem 4 blocos); o preço só
# aparece onde o sistema tem o valor ("kart": o menor de KARTS).
HUB = {
    "caminho": "/services/",
    "titulo": "Kart Lessons, Coaching & Racing Programs in Orlando | URACE",
    "descricao": ("Every URACE program in Orlando, from a first arrive and drive to the kart academy, professional coaching "
                  "and race team support. Real karts, real coaches."),
    "eyebrow": "Driver Development · Orlando, FL",
    "h1": "Kart racing in Orlando — from the simulator to the grid",
    "sub": ("URACE Racing Team develops its own drivers. Everyone on our grid started on one of the four steps below — find "
            "the one you are on today, and we will tell you straight which it is."),
    "cartoes": (
        ("Arrive and Drive", ("Drive one of our 70 MPH racing karts at Orlando Kart Center. This experience is for kids and "
                              "adults, all ages are welcome!"),
         "kart", "/services/arrive-and-drive/", "arrive-and-drive-hero.webp"),
        ("Kart School", "Become a racing driver. Practical training, theory, real karts, and a professional environment. For kids and adults.",
         "", "/services/kart-school/", "group-482140-1.webp"),
        ("URACE Academy", ("Structured driver development program with professional coaching, track experience, evaluation and "
                           "mentorship. Month-to-month, no long-term contract required."),
         "", "/academy/", "imagem-segunda-dobra.webp"),
        ("Professional Coaching", ("A custom training session designed to sharpen your racing technique. Full coaching, video "
                                   "breakdown, benchmark comparison and hands-on learning — all in 4 hours."),
         "", "/services/professional-coaching/", "group-482140-1-1.webp"),
        ("Intensive Training Camp", "5 Days of Racing, a Lifetime of Memories! Wednesday to Sunday, with 4 hours of daily training.",
         "", "/services/intensive-training-camp/", "group-482140-3.webp"),
        ("Racing Team", ("URACE prepares the kart, runs the race weekend and puts a professional coach alongside the driver — "
                         "based at the Orlando Kart Center and entered in the Florida and national calendars."),
         "", "/pro-team/", "banner-topo-lp-urace-1.webp"),
        ("Birthday Party", "At URACE, every birthday is one of a kind. Perfect for all ages! (Participants must be 5+ to race)",
         "kart", "/services/birthday-party/", "group-482141.webp"),
        ("Corporate Events", "Boost team building, motivation, and performance with an experience that combines adrenaline, strategy, and real teamwork.",
         "kart", "/services/corporate-events/", "group-482140.webp"),
        ("Group Events", GRUPOS, "kart", "/services/group-events/", "group-482140-2.webp"),
    ),
    "sim_titulo": "Sim 2 Grid",
    "sim_abertura": "Opening 1 November 2026",
    "sim": ("Most people’s idea of a racing simulator is a game. This is not that. It is a full motion cockpit — competition "
            "seat and harness, direct-drive wheel, racing pedals, triple screen. It moves. It loads you up in the corners and "
            "punishes the same mistakes a real car does, and our own drivers learn a circuit on it before they ever see it. No "
            "track fee, no equipment, no weather.",
            "That makes it the cheapest honest way to find out whether this is a hobby or a career — and it is the first rung "
            "of the ladder that leads to Arrive and Drive, the URACE Academy and the URACE Racing Team. The rig opens on 1 "
            "November 2026. Until then you cannot book an hour on it, but you can book a call and we will plan the first one "
            "with you."),
    # #207: os preços do Sim 2 Grid ainda não estão no painel; o texto sai sem os valores
    "sim_faq": (("What it will cost", ("Launch pricing, from 1 November 2026.",
                                       "Sim School. This is the step. Twelve coached hours a month with the same coach, a plan "
                                       "behind them, and your data reviewed between sessions, so the programme is a third cheaper "
                                       "than buying hours as you go. Month to month, thirty days’ notice to stop.",
                                       "Coached Hour. One hour with a URACE coach beside you. We set the car up, watch your inputs "
                                       "live and tell you what to change while you are still driving. You leave with one thing to "
                                       "fix and the laps that prove it worked.",
                                       "Sim Time. The rig, a circuit, and you. No coach, no programme. The cheapest hour in the "
                                       "building, and the one our own drivers use to put the work in between lessons.")),
                ("How will this work?", ("Tell us the driver’s level — never driven, drives a kart, races on weekends. It changes "
                                         "the car, the circuit and the assists we set up. From 1 November, book your hour. Give "
                                         "us a date and a time. Turn up. Nothing to bring: no helmet, no suit, no licence, no "
                                         "track fee.",)),
                ("What you are actually buying", ("The rig is not what you are buying. You are buying the first step. This is "
                                                  "where a career will start — not a toy and not an arcade, but the bottom rung "
                                                  "of the same ladder that runs through Arrive and Drive and the URACE Academy to "
                                                  "the Racing Team. A kart day depends on the circuit’s hours, the forecast and a "
                                                  "driver pass. This step depends on nothing but you showing up.",))),
    "sim_fotos": ("driver-kv.webp", "simulator-kv.webp"),
    "fecho": "Not sure which one is right?",
    "fecho_sub": ("Tell us who the driver is and whether they have been in a race kart before. That one answer decides "
                  "everything else — and we will tell you honestly which of these is your starting point, even if it is the "
                  "cheapest one."),
}
