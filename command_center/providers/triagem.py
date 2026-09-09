"""Triagem automática da inbox pela IA — manhã, tarde e noite.

Decisão do dono (09/09): "a IA leia cada e-mail, adicione marcadores e mova
pro marcador principal". O marcador principal vem da hierarquia da caixa
(a "pasta" onde a thread vive); os outros são etiquetas. Exemplo dele:
compra na Amazon → etiqueta "Amazon", principal "Receipts".

Como funciona:
1. pega as threads da inbox espelhada ainda não triadas;
2. lê o corpo de cada uma (ao vivo, texto, cortado) — a IA recebe tudo
   num pedido só, em lotes, e responde JSON estrito;
3. valida cada marcador contra a lista REAL da caixa (nunca inventa);
4. aplica pela porta `triar_ia` do módulo do Gmail (todos os marcadores +
   tira da inbox) e grava no espelho quem fez e por quê;
5. o que a IA marca como "precisa humano" continua em Precisa de atenção,
   mesmo fora da inbox (needs_human=1).

Não é ferramenta do agente: o agente só classifica; quem escreve é este
módulo, com as regras em código (nunca TRASH/SPAM, marcador tem de existir).
"""
import json
import re

from command_center.db import agora, atualizar, auditar, todos, um
from command_center.providers import NaoConectado, chamar, modulo
from command_center.providers.classificar import SISTEMA, _acha

CAIXAS = ("urace", "support")
LOTE = 12                  # threads por pedido à IA (o corpo entra, então menos que a classificação)
MAXIMO_POR_RODADA = 48     # por caixa; o resto fica para a próxima rodada
CORPO_MAX = 1200           # caracteres de corpo por thread no prompt


def _corpo_thread(mailbox, thread_id):
    try:
        t = chamar("gmail", "gmail_thread", conta=mailbox, thread_id=thread_id)
    except Exception:
        return ""
    partes = []
    for m in t.get("mensagens", [])[-2:]:            # as duas últimas mensagens bastam
        partes.append(f"[{m.get('de') or ''} · {m.get('data') or ''}]\n{(m.get('corpo') or m.get('snippet') or '')}")
    texto = "\n\n".join(partes)
    return texto[:CORPO_MAX] + ("…" if len(texto) > CORPO_MAX else "")


def prompt(emails, nomes, mailbox, aprendizados=""):
    linhas = []
    for e in emails:
        linhas.append(f"### id={e['id']}\nde: {e.get('sender') or ''}\nassunto: {e.get('subject') or ''}\n"
                      f"marcadores atuais: {e.get('labels') or '[]'}\ncorpo:\n{e.get('_corpo') or e.get('snippet') or ''}")
    return (f"TAREFA: triagem da inbox de {mailbox}@urace.us. Leia cada thread abaixo e decida os marcadores, "
            "seguindo brain/10_PROCESSOS/Triagem de e-mail.md e brain/40_SISTEMAS/Taxonomia do Gmail.md.\n"
            "REGRAS:\n"
            "- Use SOMENTE marcadores desta lista, com o nome EXATO (a hierarquia é o '/'): " + json.dumps(nomes, ensure_ascii=False) + ".\n"
            "- 'principal' é a PASTA onde a thread vai viver, escolhida pela hierarquia (o caminho completo, ex.: 'Finances/Receipts'). "
            "'marcadores' são etiquetas extras (fornecedor, pessoa, série). Ex.: compra na Amazon → marcadores ['Amazon'] (se existir), principal = o marcador de recibos.\n"
            "- 'precisa_humano' = true quando a thread pede resposta ou decisão de uma pessoa (cliente perguntando, cobrança a pagar, problema). "
            "Notificação, propaganda, recibo, extrato e confirmação automática = false.\n"
            "- Se não tiver certeza do principal, use null: a thread fica na inbox para uma pessoa decidir.\n"
            "- Não rotule, não mova, não escreva nada: só responda.\n"
            "RESPONDA APENAS com JSON no formato "
            "{\"itens\":[{\"id\":<int>,\"principal\":\"<nome exato ou null>\",\"marcadores\":[\"<nome exato>\"],\"precisa_humano\":<bool>,\"motivo\":\"<até 15 palavras>\"}]} "
            "e nada mais." + aprendizados + "\n\n" + "\n\n".join(linhas))


def parse(texto, nomes):
    """id -> (principal, [marcadores], precisa_humano, motivo); tudo validado contra a caixa."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    try:
        dados = json.loads(m.group(0))
    except ValueError:
        return {}
    saida = {}
    for it in dados.get("itens", []) or []:
        try:
            i = int(it.get("id"))
        except (TypeError, ValueError):
            continue
        principal = _acha(nomes, it.get("principal"))
        extras = []
        for l in it.get("marcadores") or []:
            real = _acha(nomes, l)
            if real and real != principal and real not in extras:
                extras.append(real)
        saida[i] = (principal, extras, bool(it.get("precisa_humano")), (it.get("motivo") or "")[:200])
    return saida


def rodar(con, runner, session_key, mailboxes=CAIXAS, aprendizados="", por="agenda"):
    """Uma rodada completa. Devolve o resumo (também gravado na auditoria)."""
    saida = {"lidos": 0, "movidos": 0, "ficaram": 0, "precisa_humano": 0, "erros": []}
    for mailbox in mailboxes:
        try:
            nomes = [m["nome"] for m in chamar("gmail", "gmail_marcadores", conta=mailbox)]
        except NaoConectado as e:
            saida["erros"].append(f"{mailbox}: não conectado ({e})"); continue
        except Exception as e:
            saida["erros"].append(f"{mailbox}: {type(e).__name__}: {str(e)[:120]}"); continue
        nomes = [n for n in nomes if n.upper() not in SISTEMA and not n.startswith("CATEGORY_")]
        emails = todos(con, "SELECT * FROM emails WHERE mailbox=? AND is_inbox=1 AND triaged_at IS NULL ORDER BY last_at DESC LIMIT ?",
                       (mailbox, MAXIMO_POR_RODADA))
        for e in emails:
            l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='email' AND entity_id=? AND system='gmail'", (e["id"],))
            e["_thread"] = l["external_id"] if l else None
            e["_corpo"] = _corpo_thread(mailbox, e["_thread"]) if e["_thread"] else ""
        for i in range(0, len(emails), LOTE):
            lote = emails[i:i + LOTE]
            ok, texto, erro = runner(prompt(lote, nomes, mailbox, aprendizados), session_key)
            if not ok:
                saida["erros"].append(f"{mailbox}: IA falhou: {str(erro)[:160]}"); break
            res = parse(texto, nomes)
            for e in lote:
                saida["lidos"] += 1
                principal, extras, humano, motivo = res.get(e["id"], (None, [], False, "sem resposta da IA"))
                if not principal or not e["_thread"]:
                    atualizar(con, "emails", e["id"], triaged_at=agora(), triage_reason=f"ficou na inbox: {motivo}",
                              suggested_label=None if not extras else extras[0], suggested_by="ia", suggested_at=agora())
                    saida["ficaram"] += 1; continue
                try:
                    modulo("gmail").triar_ia(mailbox, e["_thread"], extras, principal)
                except Exception as ex:
                    saida["erros"].append(f"{mailbox} thread {e['id']}: {str(ex)[:120]}")
                    atualizar(con, "emails", e["id"], triaged_at=agora(), triage_reason=f"não deu para mover: {str(ex)[:120]}")
                    saida["ficaram"] += 1; continue
                labels = [x for x in json.loads(e["labels"] or "[]") if x != "INBOX"]
                for x in [principal] + extras:
                    if x not in labels:
                        labels.append(x)
                atualizar(con, "emails", e["id"], labels=json.dumps(labels, ensure_ascii=False), is_inbox=0,
                          triaged_at=agora(), triage_reason=motivo, needs_human=1 if humano else 0,
                          suggested_label=principal, suggested_reason=motivo, suggested_by="ia", suggested_at=agora(),
                          handled=0 if humano else 1, handled_by=None if humano else "ia",
                          handled_reason=None if humano else f"triagem: {principal}" + (f" + {', '.join(extras)}" if extras else ""),
                          synced_at=agora())
                saida["movidos"] += 1
                saida["precisa_humano"] += 1 if humano else 0
    auditar(con, "gmail.triage", por, detail=saida)
    return saida
