"""WhatsApp da EQUIPE — a API oficial da Meta (WhatsApp Cloud API), número próprio.

Dono, 30/09: *"quero que o Command Center envie mensagem como se fosse uma pessoa para o
time interno (administrativo, mecânicos, coachs)"*, e que a resposta volte para o painel.

Três regras que não dependem de ninguém lembrar:

1. **Número próprio.** O número dos clientes vive no Kommo, e um número só pode estar numa
   conexão de API por vez: usar o mesmo aqui derrubaria o atendimento. Por isso nada aqui
   lê ou escreve pelo Kommo.
2. **Só a API oficial.** Biblioteca não oficial (whatsapp-web.js, Baileys) viola os termos
   e bane o número — está em D-2026-09-21 para não ser proposta de novo.
3. **Simulação até liberar.** Sem `WA_TOKEN` e `WA_PHONE_NUMBER_ID`, ou sem `WA_APLICAR=1`,
   nada sai: o envio é registrado como simulação e a tela diz isso.

Credenciais em `~/.urace/whatsapp.env` (ou no ambiente do serviço), nunca no repositório:
  WA_TOKEN            token permanente de usuário do sistema (Business Manager)
  WA_PHONE_NUMBER_ID  id do número na Meta (não é o telefone)
  WA_APP_SECRET       segredo do app: assina o webhook (X-Hub-Signature-256)
  WA_VERIFY_TOKEN     texto combinado para a Meta validar o webhook
  WA_APLICAR          1 = envia de verdade
  WA_TEMPLATE         template aprovado para fora da janela de 24 h (ex.: aviso_equipe)
  WA_TEMPLATE_IDIOMA  idioma do template (padrão pt_BR)
"""
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request

ENV = "~/.urace/whatsapp.env"
API = "https://graph.facebook.com"
VERSAO = "v20.0"
JANELA_H = 24


def _carrega_env():
    caminho = os.path.expanduser(os.environ.get("WA_ENV", ENV))
    try:
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def cfg(nome, padrao=""):
    if not os.environ.get(nome):
        _carrega_env()
    return os.environ.get(nome, padrao)


def configurado():
    return bool(cfg("WA_TOKEN") and cfg("WA_PHONE_NUMBER_ID"))


def aplicar():
    return configurado() and cfg("WA_APLICAR") == "1"


def estado():
    """Para a tela: o que falta e se está enviando de verdade. Nunca devolve segredo."""
    return {"configurado": configurado(), "enviando_de_verdade": aplicar(),
            "webhook_assinado": bool(cfg("WA_APP_SECRET")), "verify_token": bool(cfg("WA_VERIFY_TOKEN")),
            "template_fora_da_janela": cfg("WA_TEMPLATE") or None}


def normaliza_fone(fone):
    """Só dígitos, com DDI. Número dos EUA digitado sem o 1 (10 dígitos) ganha o 1."""
    d = re.sub(r"\D+", "", fone or "")
    if len(d) == 10:
        d = "1" + d
    if not 10 <= len(d) <= 15:
        raise ValueError("telefone inválido: use o número com DDI (ex.: +1 407 555 1234)")
    return d


class ErroWhatsApp(Exception):
    pass


def _post(corpo):
    url = f"{API}/{cfg('WA_API_VERSION', VERSAO)}/{cfg('WA_PHONE_NUMBER_ID')}/messages"
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {cfg('WA_TOKEN')}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            erro = json.loads(e.read().decode()).get("error", {})
            msg = erro.get("error_user_msg") or erro.get("message") or str(e)
        except Exception:                               # noqa: BLE001
            msg = str(e)
        raise ErroWhatsApp(f"{e.code}: {msg}"[:300])
    except urllib.error.URLError as e:
        raise ErroWhatsApp(f"rede: {e.reason}"[:300])


def _enviar(corpo, descricao):
    if not aplicar():
        return {"simulado": True, "teria_feito": descricao}
    r = _post(corpo)
    wamid = ((r.get("messages") or [{}])[0]).get("id")
    if not wamid:
        raise ErroWhatsApp("a Meta não devolveu o id da mensagem")
    return {"simulado": False, "id": wamid}


def enviar_texto(para, texto):
    """Texto livre: só vale dentro da janela de 24 h desde a última mensagem da pessoa."""
    para = normaliza_fone(para)
    return _enviar({"messaging_product": "whatsapp", "to": para, "type": "text",
                    "text": {"body": texto[:4096], "preview_url": False}},
                   f"texto para {para}: {texto[:80]}")


def enviar_template(para, nome, idioma, parametros):
    """Fora da janela, só template aprovado pela Meta (e cada um é cobrado)."""
    para = normaliza_fone(para)
    corpo = {"messaging_product": "whatsapp", "to": para, "type": "template",
             "template": {"name": nome, "language": {"code": idioma},
                          "components": [{"type": "body", "parameters": [
                              {"type": "text", "text": str(p)[:1000]} for p in parametros]}]}}
    return _enviar(corpo, f"template {nome} para {para}")


def assinatura_ok(corpo_bruto, cabecalho):
    """X-Hub-Signature-256 = 'sha256=' + HMAC do corpo cru com o segredo do app. Sem
    segredo configurado, nada é aceito: webhook aberto é porta para mensagem falsa."""
    segredo = cfg("WA_APP_SECRET")
    if not segredo or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho.split("=", 1)[1])
