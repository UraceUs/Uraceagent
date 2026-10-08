"""As páginas de serviço do site novo (#164), copiadas do urace.us de 08/10/2026.

Dono, 08/10: *"estamos refazendo todo o site ... eu preciso de uma cópia com as novas URLs e também
com a nossa identidade visual"*. Nada aqui é inventado: cada texto saiu da página citada. O que
mudou de propósito, pelas decisões do dono de 08/10 (página de decisões):
- remarcação: **24 horas**, com a taxa de US$ 95 (o site antigo dizia 48 h);
- idade dos karts: a do produto (Baby 4–7, 4-stroke 7+, 2-stroke 7+, Adult Shifter 14+);
- endereço com o Box 3 (decisão de 01/10);
- os botões de reservar levam à reserva do site (antes, 4 deles davam 404).

Cada página é um dicionário; `paginas.servico()` desenha todas com o mesmo esqueleto.
"""
from command_center.vitrine.conteudo import SITE

RESERVAR = "/ops/portal/reserve"
CONTATO = "/contact/"

# ------------------------------------------------------------------ blocos comuns
TRACK = ("Orlando Kart Center's 8/10 mile professional kart racing track is your textbook. A challenging circuit, "
         "the variety of corners is the ideal training ground. URACE is not the racetrack; we are a racing team that "
         "provides services to racers using a third-party track. We must adhere to their rules and operating hours. "
         "Both team members and drivers are required to pay admission fees to access the track.")

KARTS_FAQ = (
    "Baby Kart: for kids aged 4 to 7, perfect to learn the driving lines and fundamentals of racing.",
    "4-stroke: ages 7+, the standard entry for kids and adults, with a 4-cycle engine capable of speeds exceeding 50 MPH.",
    "2-stroke: ages 7+, for drivers who already have track time, with a 2-cycle engine reaching speeds of 65+ MPH.",
    "Adult Shifter: ages 14+, prior experience required, the fastest kart we run.",
)

TERMOS = (
    "The program price is URACE's fee for coaching and trackside support only. Track fees are not included: driver "
    "and guest passes are paid directly to the Orlando Kart Center, and the amount changes with the day. Extra guests "
    "must pay $15 each.",
    "There are different categories of kart available: Baby Kart (ages 4–7), 4-stroke (7+), 2-stroke (7+) and Adult "
    "Shifter (14+, experience required). The difference between 2-stroke and 4-stroke is the performance. We recommend "
    "new entrants to the sport to start with the 4-stroke, and we can move the driver up as they progress.",
    "The scheduled arrival time at the track is 8 AM. We kindly request that you arrive on time. If less than 75% of the "
    "track time is achieved, there is a possibility of receiving a proportional credit for a future session. Each case "
    "is decided individually based on the reason for not meeting the time.",
    "To cover potential crash damage caused by the driver, a refundable $400 security deposit is charged in advance. "
    "It is fully refunded within 5 business days after the session if there are no incidents or damage to the kart.",
    "Any damage caused to the kart is not included in this price, regardless of fault, and will be billed to you for "
    "the costs of repair. If the kart breaks down and it was not caused by the driver (crash, going off the track or "
    "aggressive driving), the costs of repair are covered by URACE.",
    "Kids under 10 years old must be accompanied by an adult. We provide a childcare assistant for an extra $200 in "
    "case you are unable to stay with your child. This service must be requested beforehand.",
    "Racing is a high-risk activity. By booking you agree and acknowledge that URACE is not responsible for any "
    "injuries, damages or losses of any nature that might happen to you or your family during track activities or "
    "while on site.",
)

# Dono, 08/10: "24 horas com a taxa".
REEMBOLSO = (
    "Our service requires planning, preparation, coordination and transportation to the track on our end. For those "
    "reasons we do not offer refunds. Rescheduling is available with a minimum notice of 24 hours.",
    "If a session is rescheduled with less than 24 hours' notice, a flat fee of $95 is charged, and if a Driver Pass "
    "is required it is charged additionally. To avoid this fee, let us know of any change at least 24 hours in advance.",
)

HORARIO = ("We're open every day, from 8 AM to 8 PM.",)

FAQ_COMUM = (
    ("The track", (TRACK,)),
    ("Terms and conditions", TERMOS),
    ("Refund and rescheduling policy", REEMBOLSO),
    ("Opening hours", HORARIO),
)

DEPOIMENTOS_EVENTOS = (
    ("Ivan P.", "My son's birthday was a hit! The kids had the time of their lives, and everything was so well organized!"),
    ("Daniel M., Team Leader", "Best corporate outing we've done! Everyone's still talking about it weeks later."),
)

ENDERECO = f"{SITE['endereco']['rua']}, {SITE['endereco']['cidade']}, {SITE['endereco']['estado']} {SITE['endereco']['cep']} — {SITE['endereco']['onde']}."

COMO_RESERVAR = (
    "Pick the kart, the day and the time on this page.",
    "Sign in or create your URACE account and tell us who the driver is (height and weight, so the kart is prepared).",
    "Pay the invoice online (session + refundable security deposit) and sign the waiver.",
    "Your spot confirms by itself. Show up ready to have a blast!",
)

# ------------------------------------------------------------------ Kart School (urace.us/services/kart-school/)
KART_SCHOOL = {
    "caminho": "/services/kart-school/",
    "titulo": "Kart Racing Lessons in Orlando - Learn to Race | URACE",
    "descricao": ("Kart and racing lessons in Orlando for every level. Practical training and theory in real race karts, "
                  "with a professional coach on track with you."),
    "eyebrow": "Kart School · Orlando, FL",
    "h1": "Kart School in Orlando",
    "sub": "Become a racing driver. Start at URACE Kart School. Practical training, theory, real karts, and a professional environment. For kids and adults.",
    "foto": "group-482140-1.webp",
    "cta": ("Be part of Kart School", RESERVAR),
    "fornece": ("Kart: high-performance kart provided for each session.", "Coach: expert coaching from professional instructors.",
                "In-depth safety instructions.", "Driver Pass: access to the track for the driver.",
                "1 Guest Pass: bring one guest (family or friend) to accompany and support you (additional guests subject to track pass price)."),
    "trazer": ("Long pants, closed toe shoes and a jacket.", "A reservation.", "Come prepared for fun and leave with lasting smiles."),
    "porque_titulo": "Kart School with real training, theory, and pro coaching",
    "porque": ("Professional track, where real races happen.", "Theory and mechanics simplified.", "Mentorship by winning drivers.",
               "Confidence, reflexes and racing mindset.", "Monthly program = continuous evolution."),
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
    "fecho": "If you're serious about racing, this is where it starts. Shall we begin?",
    "fecho_sub": "With an affordable price aimed at the democratization of karting.",
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
    "sub": ("Get faster with expert-level kart training and data-driven analysis. A custom training session designed to "
            "sharpen your racing technique: full coaching, video breakdown, benchmark comparison and hands-on learning, all in 4 hours."),
    "foto": "group-482140-1-1.webp",
    "cta": ("Book my coaching", RESERVAR),
    "espera": ("Tailored training program", "Professional coaching, data & video analysis", "Technique & mindset training",
               "Advanced safety briefing", "Performance tracking", "\"Lead and Follow\" option (additional fee applies)"),
    "fornece": ("1-day practice (4 hours)", "High-performance kart provided (or bring your own)", "Expert coaching from professional instructors",
                "In-depth safety instructions"),
    "trazer": ("Your kart (or you can rent ours!)", "Your personal safety equipment (we may have equipment to lend at no cost; inquire beforehand)"),
    "porque_titulo": "Real coaching from a championship-level kart team",
    "porque": ("Professional track, where real races happen.", "Theory and mechanics simplified.", "Mentorship by winning drivers.",
               "Confidence, reflexes and racing mindset.", "Immersive 4-hour practice session."),
    "para_quem_titulo": "Who can join Professional Kart Coaching in Orlando?",
    "para_quem": ("Kids aged 6–14", "Beginners or early-stage racers", "Families serious about long-term development",
                  "Parents looking for real coaching, not just seat time", "Drivers aiming for confidence, speed, and race results"),
    "passos_titulo": "How the Professional Coaching works",
    "passos": ("Choose your kart type, or use your own.", "Decide if you want \"Lead & Follow\" training.",
               "Book online: sign in, pay the invoice and sign the waiver.", "Our team contacts you to collect the driver's data.",
               "Show up ready, and leave as a faster driver."),
    "faq": (("Professional Coaching", ("Professional Coaching is your customized driver training program designed to meet your "
                                       "needs. Our program is offered as an intensive 4-hour karting instructional course. An initial "
                                       "briefing session sets the agenda for the day. Sessions include highly instructive onboard video "
                                       "review and data analysis. Your laps are compared to benchmark laps to identify the points for improvement.",
                                       "Lead and Follow is an additional fee for a partner trainer to make your driving or training "
                                       "experience more exciting, if you don't want to do it alone.",
                                       "Available training days: every day, 8 AM – 8 PM. All weekday training sessions must be confirmed "
                                       "by Sunday. All weekend sessions must be confirmed 24h in advance.")),
            ("Which kart?", KARTS_FAQ),
            ("Track fees (paid to the Orlando Kart Center)", ("Driver pass Wednesday to Friday: $100–230.", "Driver pass Saturday and Sunday: $100–125.",
                                                               "Spectator pass any day: $22.")),
            *FAQ_COMUM),
    "fecho": "If you're serious about racing, this is where it starts. Shall we begin?",
    "fecho_sub": "With an affordable price aimed at the democratization of karting.",
    "fecho_cta": ("Let's start training", RESERVAR),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

# ------------------------------------------------------------------ Intensive Training Camp
CAMP = {
    "caminho": "/services/intensive-training-camp/",
    "titulo": "Intensive Kart Racing Camp in Orlando | URACE",
    "descricao": ("Five days of intensive kart training in Orlando. Structured curriculum, race karts, coaching and data "
                  "review, built for drivers who want to go beyond the basics."),
    "eyebrow": "Intensive Training Camp · Orlando, FL",
    "h1": "Intensive Kart Racing Camp in Orlando",
    "sub": ("Build skills. Build confidence. Fuel the passion. 5 days of racing, a lifetime of memories! Give your child a "
            "chance to grow on and off the track with URACE's Intensive Training Camp."),
    "foto": "group-482140-3.webp",
    "cta": ("Join the Camp", CONTATO),
    "intro_titulo": "An unforgettable journey into racing",
    "intro": ("URACE Intensive Training Camp runs from Wednesday to Sunday, with 4 hours of daily training, designed for "
              "young drivers who want to go beyond the basics and dive deeper into the art of racing. In a supportive, "
              "exciting, and motivating environment, kids learn valuable skills that go far beyond the track, from focus "
              "and discipline to teamwork and self-confidence.",),
    "porque_titulo": "Kart racing camp with real training, theory, and pro coaching",
    "porque": ("Real track time with professional karts.", "Theory and mechanics simplified.", "Mentorship by winning drivers.",
               "Confidence, reflexes and racing mindset.", "Data + video analysis to boost performance."),
    "fornece_titulo": "What's included in the URACE Intensive Training Camp",
    "fornece": ("20+ hours of coaching", "Small group training (personalized attention)", "High-performance kart included",
                "Track pass + 1 guest pass per day", "Safety gear & full guidance", "Friendly, high-energy learning environment"),
    "trazer": ("Long pants, closed toe shoes and a jacket.", "A reservation.", "Come prepared for fun and leave with lasting smiles."),
    "dias_titulo": "5 days of immersive training",
    "dias": (("Day 1: On-track coaching + post-session analysis", "Track sessions focused on improving driving skills, followed by a detailed performance breakdown with feedback and tips for improvement.", "frame-1321317985.webp"),
             ("Day 2: Race strategy & track reading", "Emphasis on race strategy and track awareness, helping drivers develop quick decision-making skills and improve their vision and understanding of the racing line.", "frame-1321317985-1.webp"),
             ("Day 3: Data analysis & kart setup", "Data review sessions aimed at enhancing performance, along with an in-depth explanation of kart setup and how to make adjustments for optimal results.", "frame-1321317985-2.webp"),
             ("Day 4: Kart assembly & basic maintenance", "Hands-on training in kart assembly, adjustments, and basic maintenance, giving drivers more independence and technical understanding of their equipment.", "frame-1321317985-3.webp"),
             ("Day 5: Final coaching session + evaluation", "A final on-track session focused on overall progress, review of everything covered during the camp, and guidance on next steps for continued development.", "frame-1321317985-4.webp")),
    "para_quem_titulo": "Who should join the URACE Intensive Training Camp?",
    "para_quem": ("Young drivers looking to level up (age 5+)", "Kids who want to explore karting in a fun and safe environment",
                  "Drivers preparing for upcoming championships", "International drivers visiting Orlando looking for intensive training"),
    "passos_titulo": "How the URACE Intensive Training Camp works",
    "passos": ("Tell us the driver's age and experience, and the week you have in mind.", "We confirm the dates and collect the driver's info.",
               "Arrive at the track ready to go.", "Train, learn, improve.", "Finish the week a better driver."),
    "faq": (("Intensive Training Camp", ("These are not the typical put-put go-karts: they are authentic, professional racing karts. "
                                         "We start by providing safety and driving technique instructions, and each day has 4 hours of "
                                         "training, from Wednesday to Sunday.",)),
            ("Which kart?", KARTS_FAQ),
            *FAQ_COMUM),
    "fecho": "Ready to race with us?",
    "fecho_sub": "Spots are limited to keep the experience personal and impactful. Secure your seat today and make this week one to remember.",
    "fecho_cta": ("Secure my Camp spot", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

# ------------------------------------------------------------------ eventos (aniversário, corporativo, grupos)
FORMATOS_FESTA = (
    ("Fun races", "For a relaxed, good-vibes kind of day:", ("Laid-back racing sessions", "Driver rotation between rounds", "Pace and format fully customized")),
    ("Birthday Grand Prix", "A real race format for the group: qualifying, heats and a final, with a podium at the end.", ()),
    ("Build your experience your way", ("You're welcome to bring your own decorations, food, drinks, or anything else to make the "
                                        "party feel extra special and personal! We have a cozy lounge area where you can set up a "
                                        "birthday table or snack station if you'd like. The only thing we ask is a small cleaning fee "
                                        "after the event, just to help us keep the space fresh and ready for the next celebration."), ()),
    ("Perfect for all ages (participants must be 5+ to race)", "Guests who don't race cheer from our designated viewing areas.", ()),
)

PASSOS_EVENTO = ("Contact us with your date, group size, and preferences.", "Choose kart types and race formats.",
                 "We handle safety, gear and event flow.", "Show up, race, and celebrate.")

INVESTIMENTO_EVENTO = "Starting at $719 per racing participant, +$50 per guest (non-racers)."

FAQ_EVENTO = (
    ("The track", ("Orlando Kart Center's 8/10 mile professional kart racing track is your textbook. A challenging circuit, the "
                   "variety of corners is the ideal training ground. URACE is not the racetrack; we are a racing team that provides "
                   "services to racers and enthusiasts using a third-party track. We must adhere to their rules and operating hours.",)),
    ("Terms and conditions", ("Crashes or damages caused by the driver are not included in the price. The program listed price is "
                              "URACE's fee for kart rental and trackside support only. A deposit for incidentals is collected the day "
                              "before the event, and refunded in case of no incidents at the end of the event, after deducting the 3.5% "
                              "credit card processing fee.",
                              "Racing is a high-risk sports activity and environment. By booking, you agree and acknowledge that URACE "
                              "is not responsible for any injuries, damages or losses of any nature that may happen while on site.")),
    ("Refund and rescheduling policy", REEMBOLSO + ("If an event needs to be rescheduled due to circumstances outside of URACE's "
                                                  "control, a fee is charged to cover our costs of preparation, calculated on the "
                                                  "cost to reschedule and the number of drivers involved.",)),
    ("Opening hours", HORARIO),
)

BIRTHDAY = {
    "caminho": "/services/birthday-party/",
    "titulo": "Kart Racing Birthday Parties in Orlando | URACE",
    "descricao": ("Throw a birthday party on a real racing track in Orlando. Racing karts, safety gear and coaches included, "
                  "organised end to end by the URACE team."),
    "eyebrow": "Birthday Party · Orlando, FL",
    "h1": "Kart Racing Birthday Parties in Orlando",
    "sub": ("Celebrate with speed, adrenaline, and a fully personalized experience. At URACE, every birthday is one of a kind. "
            "You tell us how you want to celebrate, and we'll build a fun, safe, and unforgettable event for all ages."),
    "foto": "group-482141.webp",
    "cta": ("I want to book my birthday with URACE", CONTATO),
    "formatos_titulo": "How your party can happen",
    "formatos_intro": "No pre-set packages. Just possibilities. You mix and match to create the perfect event for your crew.",
    "formatos": FORMATOS_FESTA,
    "logistica_titulo": "Event setup",
    "logistica": ("Up to 6 drivers can race at the same time.", "Guests can cheer from our designated viewing areas.",
                  "Our team takes care of everything, ensuring your event runs smoothly, safely, and stress-free."),
    "extras_titulo": "Extras to make it even more special",
    "extras": ("Custom trophies", "Medals", "Professional photos & video", "Personalized T-shirts, caps, race suits, or gift kits", "Official race certificate"),
    "passos_titulo": "How to book your birthday on track",
    "passos": PASSOS_EVENTO,
    "faq": FAQ_EVENTO,
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
    "descricao": ("Corporate events on a professional racing track in Orlando. Real race karts, full safety gear and coaching: "
                  "a team day people actually remember."),
    "eyebrow": "Corporate Events · Orlando, FL",
    "h1": "Corporate Karting Events in Orlando",
    "sub": ("Boost team building, motivation, and performance with an experience that combines adrenaline, strategy, and real "
            "teamwork. At URACE, no two events are the same: you choose the format, and we create a dynamic, safe, and "
            "unforgettable experience for your team."),
    "foto": "group-482140.webp",
    "cta": ("I want to book my corporate event", CONTATO),
    "beneficios_titulo": "Why host a corporate event at URACE?",
    "beneficios_intro": ("Karting isn't just fun: it's a powerful, hands-on way to develop essential team skills. Our race formats "
                         "naturally build decision-making, focus, collaboration, and communication, all in an exciting, real-time environment."),
    "beneficios": (("Teamwork", "Group races strengthen collaboration and unity."),
                   ("Fast communication", "Race strategy requires quick coordination and clear communication."),
                   ("Confidence building", "Taking the wheel builds both personal and professional confidence."),
                   ("Leadership & decision-making", "On-track dynamics push quick thinking and smart risk-taking."),
                   ("Emotional management", "High-speed pressure sharpens focus, self-control, and resilience."),
                   ("Cross-team bonding", "Breaks down silos and connects employees from different departments."),
                   ("Motivating atmosphere", "Intense, energizing experience that boosts engagement and company culture."),
                   ("Unforgettable experience", "Your team leaves pumped, connected, and talking about it for weeks.")),
    "formatos_titulo": "How your event can run",
    "formatos_intro": ("No one-size-fits-all packages, just flexible options you can build around your team's goals, whether it's "
                       "connection, celebration, training, or recognition."),
    "formatos": (("Fun team races", "Perfect for casual bonding and relaxed competition.", ("Easygoing heats", "Driver rotation", "Flexible pace based on group")),
                 ("Corporate championship", "Qualifying, heats and a final, with a podium: a real race weekend compressed into one event.", ()),
                 ("Customize your experience", ("Bring your own branding, food and drinks. We have a lounge area where you can set up a "
                                                "table or snack station; the only thing we ask is a small cleaning fee after the event."), ())),
    "para_quem_titulo": "For all types of teams",
    "para_quem_intro": "We adapt the experience to your group's size and event goals:",
    "para_quem": ("Team-building sessions", "Leadership training", "Cross-department challenges", "Reward and incentive events", "Small squads or large companies"),
    "logistica_titulo": "Event logistics",
    "logistica": ("Up to 6 drivers can be on track at once", "Guests and team members can watch and cheer from special viewing zones",
                  "Dedicated staff to manage and run your event", "Full, start-to-finish scheduling and coordination", "Complete support to customize your race format"),
    "extras_titulo": "Extras to take your event to the next level",
    "extras": ("Branded trophies", "Medals", "Professional photo and video coverage", "Customized shirts, caps, race suits, or group kits", "Official race certificate"),
    "porque_titulo": "Why choose URACE?",
    "porque": ("Safe, with safety gear and staff supervision.", "Inclusive, fun for kids, teens, and adults.",
               "Memorable, guaranteed to be a highlight of your celebration.", "Customizable: ask us about group sizes, extra sessions, or branded surprises."),
    "passos_titulo": "How to book your corporate karting event",
    "passos": PASSOS_EVENTO,
    "faq": FAQ_EVENTO,
    "investimento": INVESTIMENTO_EVENTO,
    "fecho": "You bring your team. URACE delivers an unforgettable experience.",
    "fecho_sub": "Turn your corporate event into a moment of connection, adrenaline, and impact, 100% personalized for your company.",
    "fecho_cta": ("I want my corporate event on track!", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

GROUPS = {
    "caminho": "/services/group-events/",
    "antigos": ("/services/group-events-social-gatherings/",),
    "titulo": "Group Kart Racing Events in Orlando | URACE",
    "descricao": ("Group karting in Orlando for friends, clubs and social gatherings. Real race karts, gear and coaching "
                  "included, built around your group size."),
    "eyebrow": "Group Events · Orlando, FL",
    "h1": "Group Kart Racing Events & Social Gatherings in Orlando",
    "sub": ("Bring your crew together with adrenaline, fun, and a one-of-a-kind experience. At URACE, every group event is "
            "custom-built. You pick the vibe and we'll design a safe, thrilling, and unforgettable experience for your "
            "friends, family, travel team, or crew."),
    "foto": "group-482140-2.webp",
    "cta": ("I want to book a group event", CONTATO),
    "porque_titulo": "Why celebrate with URACE?",
    "porque_intro": ("We mix excitement, challenge, and laughs, perfect for bonding and making memories. Karting brings people "
                     "together through teamwork, friendly rivalry, and tons of fun."),
    "porque": ("Guaranteed fun", "Real connection and team spirit", "Personal breakthrough moments", "High-energy, relaxed atmosphere", "An unforgettable experience"),
    "formatos_titulo": "How your event can run",
    "formatos_intro": "No off-the-shelf packages, just flexible options designed around your group's goals, whether it's to celebrate, connect, compete, or just have a blast.",
    "formatos": (("Fun races", "Light, fun, and packed with laughs.", ("Chill racing heats", "Driver rotation", "Fully adjustable pace and flow")),
                 ("Mini championship", "Qualifying, heats and a final, with a podium at the end.", ()),
                 ("Customize your experience", ("Bring your own decorations, food and drinks. We have a lounge area where you can set up "
                                                "a table or snack station; the only thing we ask is a small cleaning fee after the event."), ())),
    "para_quem_titulo": "For all types of groups",
    "para_quem_intro": "We tailor each event to your crew's size and vibe:",
    "para_quem": ("Friend groups", "Families", "Travel crews", "Clubs, communities, and social teams", "Special celebrations", "Informal get-togethers"),
    "logistica_titulo": "Event setup",
    "logistica": ("Up to 6 drivers can race at the same time.", "Guests can cheer from our designated viewing areas.",
                  "Dedicated staff for guidance and support", "Full start-to-finish coordination", "Fully customizable experience"),
    "extras_titulo": "Extras to make it even more special",
    "extras": ("Personalized trophies", "Medals", "Pro photos and videos", "Custom shirts, caps, or event kits", "Official race certificate"),
    "passos_titulo": "How to book your group karting event",
    "passos": PASSOS_EVENTO,
    "faq": FAQ_EVENTO,
    "investimento": INVESTIMENTO_EVENTO,
    "fecho": "Turn your group gathering into a moment of speed, connection, and epic memories.",
    "fecho_sub": "Our team leads a simple, friendly briefing that's perfect for first-timers, and we crank it up for experienced drivers.",
    "fecho_cta": ("I want to make a reservation for my group", CONTATO),
    "depoimentos": DEPOIMENTOS_EVENTOS,
}

SERVICOS = (KART_SCHOOL, COACHING, CAMP, BIRTHDAY, CORPORATE, GROUPS)

# ------------------------------------------------------------------ o hub (urace.us/services/)
HUB = {
    "caminho": "/services/",
    "titulo": "Kart Lessons, Coaching & Racing Programs in Orlando | URACE",
    "descricao": ("Every URACE program in Orlando, from a first arrive and drive to the kart academy, professional coaching "
                  "and race team support. Real karts, real coaching."),
    "h1": "Kart Racing Services in Orlando",
    "sub": "Tell us who the driver is and whether they have been in a race kart before. That one answer decides everything else.",
    "cartoes": (
        ("Arrive and Drive", "One day in a real 70 MPH racing kart, with the kart, the gear and a coach. For all ages starting at 4.",
         "From $719 per driver", "/services/arrive-and-drive/", "arrive-and-drive-hero.webp"),
        ("Kart School", "Practical training, theory, real karts and a professional environment. For kids and adults starting out.",
         "From $719 per session", "/services/kart-school/", "group-482140-1.webp"),
        ("URACE Academy", "Four coached sessions a month with the same coach, a career specialist and a clear path forward.",
         "From $2,619.06 per month", "/academy/", "imagem-segunda-dobra.webp"),
        ("Professional Coaching", "A 4-hour session with video breakdown, data analysis and benchmark laps, for drivers who already race.",
         "From $719", "/services/professional-coaching/", "group-482140-1-1.webp"),
        ("Intensive Training Camp", "Five days, Wednesday to Sunday, 4 hours a day. For young drivers who want to go beyond the basics.",
         "By quote", "/services/intensive-training-camp/", "group-482140-3.webp"),
        ("Racing Team", "We prepare the kart, run the race weekend and put a professional coach alongside the driver.",
         "Per event", "/pro-team/", "banner-topo-lp-urace-1.webp"),
        ("Birthday Party", "A birthday on a real racing track, organised end to end. Participants must be 5+ to race.",
         "From $719 per racer", "/services/birthday-party/", "group-482141.webp"),
        ("Corporate Events", "Team building on track: real karts, safety gear and coaching. A team day people remember.",
         "From $719 per racer", "/services/corporate-events/", "group-482140.webp"),
        ("Group Events", "Friends, families, clubs and crews. Up to 6 drivers on track at the same time.",
         "From $719 per racer", "/services/group-events/", "group-482140-2.webp"),
    ),
    "sim_titulo": "Sim 2 Grid",
    "sim_abertura": "Opening 1 November 2026",
    "sim": ("Most people's idea of a racing simulator is a game. This is not that. It is a full motion cockpit: competition seat "
            "and harness, direct-drive wheel, racing pedals, triple screen. It moves. It loads you up in the corners and punishes "
            "the same mistakes a real car does, and our own drivers learn a circuit on it before they ever see it. No track fee, "
            "no equipment, no weather.",),
    "sim_faq": (("What it will cost", ("Launch pricing, from 1 November 2026. Sim School: $1,200 a month, twelve coached hours a month "
                                       "with the same coach, a plan behind them, and your data reviewed between sessions. That works out "
                                       "at $100 an hour against $150 for a one-off. Month to month, thirty days' notice to stop. Coached "
                                       "Hour: $150. Solo hour: $60.",)),
                ("How will this work?", ("Tell us the driver's level: never driven, drives a kart, races on weekends. It changes the car, "
                                         "the circuit and the assists we set up. From 1 November, book your hour. Give us a date and a "
                                         "time. Turn up. Nothing to bring: no helmet, no suit, no licence, no track fee.",)),
                ("What you are actually buying", ("The rig is not what you are buying. You are buying the first step. This is where a "
                                                  "career starts: not a toy and not an arcade, but the bottom rung of the same ladder "
                                                  "that runs through Arrive and Drive and the URACE Academy to the Racing Team.",))),
    "sim_fotos": ("driver-kv.webp", "simulator-kv.webp"),
    "fecho": "Not sure which one is right?",
    "fecho_sub": ("Tell us who the driver is and whether they have been in a race kart before. We will tell you honestly which "
                  "of these is your starting point, even if it is the cheapest one."),
}
