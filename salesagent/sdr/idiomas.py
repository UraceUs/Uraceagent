"""Idiomas do robô SDR (dono, 16/10): "prepare para os principais idiomas mundiais para lidar com objeções,
vocabulário, abreviações".

Duas coisas moram aqui, e as duas são código (não dependem do modelo):

1. `detectar(texto)`: em que idioma o lead escreveu. Primeiro pela escrita (cirílico, árabe, devanágari,
   hangul, kana, ideogramas); no alfabeto latino, por palavras e abreviações típicas de cada idioma
   ("vc", "qto", "xq", "svp", "thx"). Sem nenhum sinal, inglês, que é o padrão da URACE.
2. `TEXTOS`: as frases fixas que a ponte manda sem passar pelo modelo (oferta de call, "agora não",
   opt-out, espera, apresentação) nos idiomas além de pt/es/en, que continuam em holding.py e roteador.py.

O modelo escreve em qualquer idioma; o que precisa estar aqui é o que sai sem ele.
"""
import re

IDIOMAS = ("en", "pt", "es", "fr", "it", "de", "ru", "zh", "ja", "ko", "ar", "hi")

# Como a ponte diz ao modelo o idioma do turno (o bloco [SYSTEM] é em português).
NOMES = {"pt": "português do Brasil (com você)", "es": "espanhol", "fr": "francês", "it": "italiano",
         "de": "alemão", "ru": "russo", "zh": "chinês (simplificado)", "ja": "japonês", "ko": "coreano",
         "ar": "árabe", "hi": "hindi"}

# ------------------------------------------------------------------ detecção pela escrita
_ESCRITAS = (
    ("ko", re.compile(r"[가-힯ᄀ-ᇿ]")),
    ("ja", re.compile(r"[぀-ヿ]")),          # hiragana/katakana: japonês, mesmo com kanji junto
    ("zh", re.compile(r"[一-鿿]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("ar", re.compile(r"[؀-ۿ]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
)

# ------------------------------------------------------------------ alfabeto latino: palavras e abreviações
# Só palavras que praticamente não existem nos outros idiomas da lista: "para", "caro", "barato", "esta",
# "quanto" (pt e it), "no", "si" ficam de fora, ou entram só onde não confundem.
_MARCAS = {
    "pt": (r"não|nao|quanto|você|voce|vocês|voces|obrigad[oa]|custa|preço|preco|posso|meu|minha|olá|oi|"
           r"bom dia|boa tarde|boa noite|qual|quero|gostaria|criança|crianca|filho|filha|aulas?|corrida|"
           r"mais|sim|fosse|então|entao|tá|isso|desconto|muito|muita|hoje|amanhã|amanha|fecho|fechar|"
           r"fecha|faz|fazer|faço|agora|tem|pra|pro|também|tambem|ainda|valor|está|estou|gente|vou|"
           # abreviações do WhatsApp/Instagram
           r"vc|vcs|qto|qnto|qt|pq|tbm|blz|obg|hj|dps|agr|td|msg|pfv|pfvr|mto|mt|nd|kd|cmg|ctg|oq|vlw|"
           r"bjs|tmj|slk|sqn|nn"),
    "es": (r"hola|gracias|cuánto|cuanto|cuesta|puedo|quiero|quisiera|ustedes|niñ[oa]|nino|hij[oa]|"
           r"clases?|carrera|buenos días|buenas tardes|precio|dónde|donde|cómo|como está|descuento|muy|"
           r"mucho|hoy|ahora|tiene|también|vale|"
           r"xq|porq|tmb|xfa|porfa|grax|ntp|tqm|salu2|dnd|ke|bno"),
    "fr": (r"bonjour|bonsoir|salut|merci|combien|coûte|coute|prix|tarif|mon|fils|fille|enfant|je|"
           r"vous|est-ce|pourquoi|réduction|reduction|remise|cher|trop|voudrais|oui|c'est|ça|aujourd'hui|"
           r"maintenant|plus tard|s'il|svp|stp|slt|bjr|pk|pcq|jsp|dsl|mdr|tkt|bcp"),
    "it": (r"ciao|grazie|costa|prezzo|prezzi|mio|mia|figlio|figlia|bambin[oa]|sconto|troppo|vorrei|"
           r"perché|perche|buongiorno|buonasera|sì|adesso|oggi|dopo|grz|cmq|xké|xche|tvb|nn|qlc"),
    "de": (r"hallo|danke|bitte|wie viel|wieviel|kostet|preis|mein|meine|sohn|tochter|ich|sie|rabatt|"
           r"teuer|möchte|moechte|guten|nein|heute|jetzt|später|spaeter|vielleicht|"
           r"lg|vg|mfg|hdl|bzw|gerne|danke schön|kannst|könnt"),
    # inglês também pontua, para mensagens misturadas ("Oi, how much is it?") não virarem português
    "en": (r"the|is|are|my|you|how|much|price|cost|kid|son|daughter|want|can|does|please|thanks|hi|hello|"
           r"what|when|where|book|expensive|discount|"
           r"u|ur|thx|pls|plz|rn|idk|lmk|tmrw|tmr|bc|cuz|wanna|gonna|gotta|btw|asap|nvm|ty|yeah|yep"),
}
_REGEX = {k: re.compile(rf"(?<![\w']){'(?:' + v + ')'}(?![\w'])", re.IGNORECASE) for k, v in _MARCAS.items()}
_SO_PT = re.compile(r"[ãõçâê]")
_SO_ES = re.compile(r"[ñ¿¡]")
_SO_DE = re.compile(r"[äöüß]")
_SO_FR = re.compile(r"[œëïîû]")   # à/è/ù são do italiano também
# frases que separam idiomas vizinhos ("quanto costa" é italiano, "quanto custa" é português)
_BONUS = (("it", re.compile(r"quanto cost|c'è|c è|perch[eé]", re.IGNORECASE)),
          ("pt", re.compile(r"quanto cust|quanto fica|quanto é", re.IGNORECASE)))


def detectar(texto):
    """Código do idioma ('en', 'pt', 'es', 'fr', 'it', 'de', 'ru', 'zh', 'ja', 'ko', 'ar', 'hi')."""
    texto = texto or ""
    for codigo, escrita in _ESCRITAS:
        if escrita.search(texto):
            return codigo
    pontos = {k: len(r.findall(texto)) for k, r in _REGEX.items()}
    pontos["pt"] += 2 * len(_SO_PT.findall(texto))
    pontos["es"] += 2 * len(_SO_ES.findall(texto))
    pontos["de"] += 2 * len(_SO_DE.findall(texto))
    pontos["fr"] += 2 * len(_SO_FR.findall(texto))
    for codigo, frase in _BONUS:
        pontos[codigo] += 2 * len(frase.findall(texto))
    if not any(v for k, v in pontos.items() if k != "en"):
        return "en"
    # empate entre idiomas: a ordem decide (pt e es primeiro, são os leads mais comuns depois do inglês)
    ordem = ("pt", "es", "en", "fr", "it", "de")
    return max(ordem, key=lambda k: (pontos[k], -ordem.index(k)))


# ------------------------------------------------------------------ frases fixas (além de pt, es e en)
TEXTOS = {
    "oferta_call": {
        "objecao": {
            "fr": ["Je comprends{nome}. Un appel rapide de 15 minutes avec notre équipe, ça vous dit ?",
                   "On parle des objectifs du pilote et du meilleur parcours.", "Choisissez un créneau ici :",
                   "{link}"],
            "it": ["Capisco{nome}. Che ne dici di una breve chiamata di 15 minuti con il nostro team?",
                   "Parliamo degli obiettivi del pilota e del percorso migliore.", "Scegli un orario qui:", "{link}"],
            "de": ["Verstehe{nome}. Wie wäre ein kurzer 15-Minuten-Call mit unserem Team?",
                   "Wir sprechen über die Ziele des Fahrers und den besten Weg.", "Such dir hier einen Termin aus:",
                   "{link}"],
            "ru": ["Понимаю{nome}. Как насчёт короткого 15-минутного звонка с нашей командой?",
                   "Обсудим цели пилота и лучший путь.", "Выберите удобное время здесь:", "{link}"],
            "zh": ["明白{nome}。和我们团队约个15分钟的简短通话怎么样？", "我们聊聊车手的目标和最适合的路线。",
                   "在这里选个时间：", "{link}"],
            "ja": ["承知しました{nome}。私たちのチームと15分ほどの短い通話はいかがですか？",
                   "ドライバーの目標と最適な進め方についてお話しします。", "こちらからご都合の良い時間をお選びください：",
                   "{link}"],
            "ko": ["이해합니다{nome}. 저희 팀과 15분 정도 짧게 통화해 보시는 건 어떨까요?",
                   "드라이버의 목표와 가장 좋은 방향을 함께 이야기해요.", "여기에서 시간을 선택해 주세요:", "{link}"],
            "ar": ["أفهمك{nome}. ما رأيك بمكالمة سريعة مدتها 15 دقيقة مع فريقنا؟", "نتحدث عن أهداف السائق وأفضل طريق.",
                   "اختر موعدًا من هنا:", "{link}"],
            "hi": ["समझ गया{nome}. हमारी टीम के साथ 15 मिनट की एक छोटी कॉल कैसी रहेगी?",
                   "हम ड्राइवर के लक्ष्यों और सबसे अच्छे रास्ते पर बात करेंगे।", "यहाँ से समय चुनें:", "{link}"],
        },
        "decisao": {
            "fr": ["Super{nome} !", "La prochaine étape est un appel rapide de 15 minutes avec notre équipe pour caler "
                   "les détails.", "Choisissez un créneau ici :", "{link}"],
            "it": ["Ottimo{nome}!", "Il prossimo passo è una breve chiamata di 15 minuti con il nostro team per i "
                   "dettagli.", "Scegli un orario qui:", "{link}"],
            "de": ["Super{nome}!", "Der nächste Schritt ist ein kurzer 15-Minuten-Call mit unserem Team für die "
                   "Details.", "Such dir hier einen Termin aus:", "{link}"],
            "ru": ["Отлично{nome}!", "Следующий шаг: короткий 15-минутный звонок с нашей командой, чтобы обсудить "
                   "детали.", "Выберите удобное время здесь:", "{link}"],
            "zh": ["太好了{nome}！", "下一步是和我们团队进行一次15分钟的简短通话，确认细节。", "在这里选个时间：", "{link}"],
            "ja": ["素晴らしいです{nome}！", "次のステップは、詳細を詰めるための私たちのチームとの15分の短い通話です。",
                   "こちらからご都合の良い時間をお選びください：", "{link}"],
            "ko": ["좋습니다{nome}!", "다음 단계는 세부 사항을 맞추기 위한 저희 팀과의 15분 짧은 통화입니다.",
                   "여기에서 시간을 선택해 주세요:", "{link}"],
            "ar": ["رائع{nome}!", "الخطوة التالية مكالمة سريعة مدتها 15 دقيقة مع فريقنا لترتيب التفاصيل.",
                   "اختر موعدًا من هنا:", "{link}"],
            "hi": ["बढ़िया{nome}!", "अगला कदम हमारी टीम के साथ 15 मिनट की एक छोटी कॉल है, ताकि सब कुछ तय हो सके।",
                   "यहाँ से समय चुनें:", "{link}"],
        },
        "competidor": {
            "fr": ["Top{nome} ! Quand on court déjà, le mieux est de parler directement à notre équipe.",
                   "Un appel rapide de 15 minutes pour voir le calendrier et les objectifs.",
                   "Choisissez un créneau ici :", "{link}"],
            "it": ["Bene{nome}! Per chi corre già, la cosa migliore è parlare direttamente con il nostro team.",
                   "Una breve chiamata di 15 minuti per calendario e obiettivi.", "Scegli un orario qui:", "{link}"],
            "de": ["Klasse{nome}! Wer schon Rennen fährt, spricht am besten direkt mit unserem Team.",
                   "Ein kurzer 15-Minuten-Call zu Rennkalender und Zielen.", "Such dir hier einen Termin aus:", "{link}"],
            "ru": ["Здорово{nome}! Если вы уже участвуете в гонках, лучше поговорить напрямую с нашей командой.",
                   "Короткий 15-минутный звонок о календаре и целях.", "Выберите удобное время здесь:", "{link}"],
            "zh": ["很棒{nome}！已经在比赛的车手，最好直接和我们团队聊。", "15分钟的简短通话，聊聊赛历和目标。", "在这里选个时间：",
                   "{link}"],
            "ja": ["いいですね{nome}！すでにレースに出ている方は、チームと直接話すのが一番です。",
                   "カレンダーと目標について15分の短い通話をしましょう。", "こちらからご都合の良い時間をお選びください：",
                   "{link}"],
            "ko": ["멋지네요{nome}! 이미 레이스를 하고 계시다면 저희 팀과 직접 이야기하는 게 가장 좋아요.",
                   "일정과 목표에 대해 15분 짧게 통화해요.", "여기에서 시간을 선택해 주세요:", "{link}"],
            "ar": ["رائع{nome}! لمن يتسابق بالفعل، الأفضل التحدث مباشرة مع فريقنا.",
                   "مكالمة سريعة مدتها 15 دقيقة للحديث عن الجدول والأهداف.", "اختر موعدًا من هنا:", "{link}"],
            "hi": ["बहुत बढ़िया{nome}! जो पहले से रेस करते हैं, उनके लिए सीधे हमारी टीम से बात करना सबसे अच्छा है।",
                   "कैलेंडर और लक्ष्यों पर 15 मिनट की छोटी कॉल।", "यहाँ से समय चुनें:", "{link}"],
        },
    },
    "adiar": {
        "fr": "Pas de souci ! Quand ce sera le bon moment pour vous, écrivez-nous ici.\nOn reste à votre disposition.",
        "it": "Nessun problema! Quando ti sembra il momento giusto, scrivici qui.\nSiamo a disposizione.",
        "de": "Kein Problem! Wenn es für dich passt, schreib uns einfach hier.\nWir sind da, wenn du so weit bist.",
        "ru": "Без проблем! Когда будет удобно, просто напишите нам здесь.\nМы на связи.",
        "zh": "没问题！等你方便的时候，在这里给我们留言就好。\n我们随时都在。",
        "ja": "大丈夫です！ご都合の良いときに、こちらからメッセージをください。\nいつでもお待ちしています。",
        "ko": "괜찮아요! 편하실 때 여기로 메시지 주세요.\n언제든 기다리고 있을게요.",
        "ar": "لا مشكلة! متى ما ناسبك الوقت، راسلنا هنا.\nنحن في الخدمة.",
        "hi": "कोई बात नहीं! जब भी आपके लिए सही समय हो, यहाँ मैसेज कर दीजिए।\nहम आपके लिए यहाँ हैं।",
    },
    "opt_out": {
        "fr": "C'est noté, nous ne vous enverrons plus de messages ici. Si besoin, écrivez-nous.",
        "it": "Ricevuto, non ti invieremo più messaggi qui. Se ti serve, scrivici pure.",
        "de": "Alles klar, wir schreiben dir hier nicht mehr. Wenn du uns brauchst, melde dich einfach.",
        "ru": "Понял, больше не будем писать вам здесь. Если понадобимся, просто напишите.",
        "zh": "好的，我们不会再在这里给你发消息了。如有需要，随时联系我们。",
        "ja": "承知しました。今後こちらからメッセージはお送りしません。必要なときはいつでもご連絡ください。",
        "ko": "알겠습니다. 앞으로 여기로 메시지를 보내지 않을게요. 필요하시면 언제든 연락 주세요.",
        "ar": "تم، لن نرسل لك رسائل هنا بعد الآن. إذا احتجت إلينا، راسلنا في أي وقت.",
        "hi": "ठीक है, हम आपको यहाँ और मैसेज नहीं भेजेंगे। ज़रूरत हो तो कभी भी लिखिए।",
    },
    "ack": {
        "fr": "Parfait. Je reviens vers vous dès que j'ai la confirmation.",
        "it": "Perfetto. Ti faccio sapere appena ho la conferma.",
        "de": "Passt. Ich melde mich, sobald ich die Bestätigung habe.",
        "ru": "Хорошо. Напишу, как только будет подтверждение.",
        "zh": "好的，一有确认我就告诉你。",
        "ja": "承知しました。確認が取れ次第ご連絡します。",
        "ko": "알겠습니다. 확인되는 대로 바로 알려드릴게요.",
        "ar": "تمام. سأعود إليك فور وصول التأكيد.",
        "hi": "ठीक है। पुष्टि मिलते ही मैं आपको बताता हूँ।",
    },
    "espera": {
        "fr": ["Bonne question, je préfère la confirmer avec l'équipe pour vous donner la bonne info. Je reviens vers "
               "vous ici."],
        "it": ["Bella domanda, preferisco confermarla con il team per darti l'informazione giusta. Ti rispondo qui."],
        "de": ["Gute Frage, die kläre ich lieber mit dem Team, damit du die richtige Info bekommst. Ich melde mich hier."],
        "ru": ["Хороший вопрос, лучше уточню у команды, чтобы ответить точно. Вернусь к вам здесь."],
        "zh": ["好问题，我先和团队确认一下，给你准确的答复。稍后在这里回复你。"],
        "ja": ["良いご質問です。正確にお伝えするため、チームに確認します。こちらでご返信します。"],
        "ko": ["좋은 질문이에요. 정확한 답을 드리기 위해 팀에 확인할게요. 여기로 답장드릴게요."],
        "ar": ["سؤال جيد، أفضّل التأكد منه مع الفريق لأعطيك المعلومة الصحيحة. سأعود إليك هنا."],
        "hi": ["अच्छा सवाल है, सही जानकारी देने के लिए मैं इसे टीम से कन्फ़र्म कर लेता हूँ। यहीं जवाब दूँगा।"],
    },
    "espera_citando": {
        "fr": ["Pour « {q} », je vérifie avec l'équipe pour vous donner la bonne réponse. Je reviens vers vous ici."],
        "it": ['Su "{q}" sto verificando con il team per darti la risposta giusta. Ti rispondo qui.'],
        "de": ['Zu "{q}" frage ich beim Team nach, damit du die richtige Antwort bekommst. Ich melde mich hier.'],
        "ru": ["По вопросу «{q}» уточняю у команды, чтобы ответить точно. Вернусь к вам здесь."],
        "zh": ["关于“{q}”，我正在和团队确认，给你准确的答复。稍后在这里回复你。"],
        "ja": ["「{q}」について、正確にお答えするためチームに確認中です。こちらでご返信します。"],
        "ko": ['"{q}"에 대해 정확한 답을 드리려고 팀에 확인 중이에요. 여기로 답장드릴게요.'],
        "ar": ['بخصوص "{q}"، أتأكد من الفريق لأعطيك الإجابة الصحيحة. سأعود إليك هنا.'],
        "hi": ['"{q}" के बारे में सही जवाब देने के लिए मैं टीम से पूछ रहा हूँ। यहीं जवाब दूँगा।'],
    },
    "apresentacao": {
        "fr": "Bonjour{nome}, ici Chase, l'assistant d'URACE.",
        "it": "Ciao{nome}, sono Chase, l'assistente di URACE.",
        "de": "Hallo{nome}, hier ist Chase, der Assistent von URACE.",
        "ru": "Здравствуйте{nome}, это Chase, ассистент URACE.",
        "zh": "你好{nome}，我是 URACE 的助理 Chase。",
        "ja": "こんにちは{nome}、URACEのアシスタントのChaseです。",
        "ko": "안녕하세요{nome}, URACE 어시스턴트 Chase입니다.",
        "ar": "مرحبًا{nome}، معك Chase، مساعد URACE.",
        "hi": "नमस्ते{nome}, मैं Chase हूँ, URACE का असिस्टेंट।",
    },
}


def completar(tabela, chave):
    """Junta as frases desta tabela (fr, it, de, ...) num dicionário que já tem pt, es e en."""
    for idioma, texto in TEXTOS[chave].items():
        tabela.setdefault(idioma, texto)
    return tabela
