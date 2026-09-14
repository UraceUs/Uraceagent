"""Triagem automática da inbox pela IA — manhã, tarde e noite.

Decisão do dono (09/09): "a IA leia cada e-mail, adicione marcadores e mova
pro marcador principal". O marcador principal vem da hierarquia da caixa
(a "pasta" onde a thread vive); os outros são etiquetas. Exemplo dele:
compra na Amazon → etiqueta "Amazon", principal "Receipts".

Decisão do dono (14/09): os **filtros nativos do Gmail** passam a fazer o
trabalho determinístico — quem manda o e-mail já diz onde ele vai
(`adminai/gerar_filtros_gmail.py`). A IA deixa de classificar tudo do zero e
passa a ter duas tarefas: **confirmar** o que o filtro marcou e **classificar**
o que o filtro não conseguiu, usando contexto e conhecimento.

Isso parte a rodada em duas:
  * thread que já chegou com marcador do manual → "o filtro disse X; confirma,
    completa ou corrige?". Discordância vira `needs_human`, porque quem precisa
    de conserto é o filtro, e isso é decisão do dono.
  * thread sem marcador nenhum → classifica do zero.

**O corpo é lido nos dois casos** (dono, 14/09: *"sempre leia para colocar mais
marcadores caso seja preciso e escalar em situações que te ensinarei no
futuro"*). O filtro acerta a pasta pelo remetente, mas só o conteúdo diz se
falta etiqueta e se aquilo precisa de gente. Os `aprendizados` — o que o dono
ensina com o tempo — entram nos dois pedidos pelo mesmo motivo.

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
    """O corpo, ou string vazia. Nunca levanta: uma thread ilegível não pode
    derrubar a rodada inteira — a IA classifica pelo remetente e pelo assunto."""
    try:
        t = chamar("gmail", "gmail_thread", conta=mailbox, thread_id=thread_id)
        partes = []
        for m in (t.get("mensagens") or [])[-2:]:    # as duas últimas mensagens bastam
            partes.append(f"[{m.get('de') or ''} · {m.get('data') or ''}]\n{(m.get('corpo') or m.get('snippet') or '')}")
        texto = "\n\n".join(partes)
        return texto[:CORPO_MAX] + ("…" if len(texto) > CORPO_MAX else "")
    except Exception:
        return ""


def confirmados(con):
    """Os marcadores que o dono confirmou no manual. Vazio = a triagem não roda."""
    return [l["name"] for l in todos(con, "SELECT name FROM gmail_labels WHERE status='confirmado' AND in_gmail=1 ORDER BY name")]


def manual(con):
    """O manual como texto para o prompt: marcador → o que vai nele."""
    linhas = todos(con, """SELECT name, what FROM gmail_labels WHERE status='confirmado' AND in_gmail=1
                           ORDER BY family, name""")
    return "\n".join(f"- {l['name']}: {l['what']}" for l in linhas if l["what"])


def do_filtro(email, permitidos):
    """Marcadores do manual que a thread JÁ tem — postos pelo filtro nativo do Gmail.

    O que não está no manual é ignorado de propósito: foi assim que os
    `Email Review/…` entraram na caixa em agosto sem serem do dono."""
    try:
        atuais = json.loads(email.get("labels") or "[]")
    except ValueError:
        return []
    aceitos = set(permitidos)
    return [l for l in atuais
            if l and l.upper() not in SISTEMA and not l.startswith("CATEGORY_") and l in aceitos]


def _principal_provavel(marcadores):
    """O mais específico vira a pasta: 'Finances/Shopping/Amazon' manda em 'Finances'."""
    return max(marcadores, key=lambda n: (n.count("/"), len(n))) if marcadores else None


def prompt_confirmar(emails, nomes, mailbox, aprendizados="", livro=""):
    """O que o filtro nativo já marcou: confirmar, COMPLETAR e escalar.

    O dono (14/09) recusou a versão barata sem corpo: *"sempre leia para colocar
    mais marcadores caso seja preciso e escalar em situações que te ensinarei no
    futuro"*. O filtro acerta a pasta pelo remetente; só o conteúdo diz se falta
    etiqueta e se aquilo precisa de uma pessoa."""
    linhas = []
    for e in emails:
        linhas.append(f"### id={e['id']}\nde: {e.get('sender') or ''}\nassunto: {e.get('subject') or ''}\n"
                      f"marcador aplicado pelo filtro: {e.get('_filtro_principal')}\n"
                      f"outros marcadores na thread: {json.dumps(e.get('_filtro_todos') or [], ensure_ascii=False)}\n"
                      f"corpo:\n{e.get('_corpo') or e.get('snippet') or ''}")
    return (f"TAREFA: conferir e COMPLETAR a classificação automática da inbox de {mailbox}@urace.us.\n"
            "Um filtro nativo do Gmail já marcou estas threads pelo remetente. Ele acerta a pasta na "
            "grande maioria das vezes, mas ele não lê o e-mail — você lê. Seu trabalho é:\n"
            "  1. CONFIRMAR o marcador do filtro (só corrija se estiver claramente errado pelo manual);\n"
            "  2. ACRESCENTAR os marcadores que faltarem — fornecedor, pessoa, série, loja;\n"
            "  3. ESCALAR: dizer precisa_humano=true quando o conteúdo pedir decisão de uma pessoa.\n"
            + (f"MANUAL DOS MARCADORES (o dono confirmou isto; é a única regra que vale):\n{livro}\n" if livro else "")
            + "REGRAS:\n"
            "- Use SOMENTE marcadores desta lista, com o nome EXATO: " + json.dumps(nomes, ensure_ascii=False) + ".\n"
            "- Na dúvida, CONFIRME o que o filtro pôs. Corrigir sem certeza é pior que não corrigir.\n"
            "- 'principal' = o marcador do filtro, ou o correto se ele errou feio.\n"
            "- 'marcadores' = etiquetas extras que o filtro não tinha como saber, lidas do corpo.\n"
            "- 'precisa_humano' = true quando a thread pede resposta ou decisão de uma pessoa. "
            "Notificação, propaganda, recibo, extrato e confirmação automática = false.\n"
            "- Não rotule, não mova, não escreva nada: só responda.\n"
            "RESPONDA APENAS com JSON no formato "
            "{\"itens\":[{\"id\":<int>,\"principal\":\"<nome exato>\",\"marcadores\":[\"<nome exato>\"],\"precisa_humano\":<bool>,\"motivo\":\"<até 15 palavras>\"}]} "
            "e nada mais." + aprendizados + "\n\n" + "\n\n".join(linhas))


def prompt(emails, nomes, mailbox, aprendizados="", livro=""):
    linhas = []
    for e in emails:
        linhas.append(f"### id={e['id']}\nde: {e.get('sender') or ''}\nassunto: {e.get('subject') or ''}\n"
                      f"marcadores atuais: {e.get('labels') or '[]'}\ncorpo:\n{e.get('_corpo') or e.get('snippet') or ''}")
    return (f"TAREFA: triagem da inbox de {mailbox}@urace.us. Leia cada thread abaixo e decida os marcadores, "
            "seguindo o MANUAL confirmado pelo dono (abaixo).\n"
            + (f"MANUAL DOS MARCADORES (o dono confirmou isto; é a única regra que vale):\n{livro}\n" if livro else "")
            + "REGRAS:\n"
            "- Use SOMENTE marcadores desta lista, com o nome EXATO (a hierarquia é o '/'): " + json.dumps(nomes, ensure_ascii=False) + ".\n"
            "- Marcador que não está na lista NÃO EXISTE para você, mesmo que apareça no e-mail.\n"
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
    saida = {"lidos": 0, "movidos": 0, "ficaram": 0, "precisa_humano": 0,
             "do_filtro": 0, "confirmados": 0, "corrigidos": 0, "erros": []}
    # TRAVA (dono, 11/09): sem manual confirmado, a IA não classifica nada. E quando
    # rodar, só com os marcadores que ele confirmou — nunca um que apareceu na caixa.
    permitidos = confirmados(con)
    if not permitidos:
        saida["pulada"] = ("manual dos marcadores não confirmado: abra Gmail → Manual dos marcadores, "
                           "confira o que vai em cada um e confirme. Até lá a triagem não roda.")
        auditar(con, "gmail.triagem.bloqueada", "system", detail={"motivo": "manual não confirmado"})
        return saida
    livro = manual(con)
    for mailbox in mailboxes:
        try:
            nomes = [m["nome"] for m in chamar("gmail", "gmail_marcadores", conta=mailbox)]
        except NaoConectado as e:
            saida["erros"].append(f"{mailbox}: não conectado ({e})"); continue
        except Exception as e:
            saida["erros"].append(f"{mailbox}: {type(e).__name__}: {str(e)[:120]}"); continue
        nomes = [n for n in nomes if n in permitidos]        # só o que o dono confirmou
        if not nomes:
            saida["erros"].append(f"{mailbox}: nenhum marcador confirmado existe nesta caixa"); continue
        emails = todos(con, "SELECT * FROM emails WHERE mailbox=? AND is_inbox=1 AND triaged_at IS NULL ORDER BY last_at DESC LIMIT ?",
                       (mailbox, MAXIMO_POR_RODADA))
        for e in emails:
            l = um(con, "SELECT external_id FROM entity_links WHERE entity_type='email' AND entity_id=? AND system='gmail'", (e["id"],))
            e["_thread"] = l["external_id"] if l else None
            e["_filtro_todos"] = do_filtro(e, permitidos)
            e["_filtro_principal"] = _principal_provavel(e["_filtro_todos"])
            # sempre lê o corpo (dono, 14/09): é ele que diz se falta marcador e se escala
            e["_corpo"] = _corpo_thread(mailbox, e["_thread"]) if e["_thread"] else ""
        com_filtro = [e for e in emails if e["_filtro_principal"]]
        sem_filtro = [e for e in emails if not e["_filtro_principal"]]
        saida["do_filtro"] += len(com_filtro)
        grupos = ((com_filtro, lambda lote: prompt_confirmar(lote, nomes, mailbox, aprendizados, livro)),
                  (sem_filtro, lambda lote: prompt(lote, nomes, mailbox, aprendizados, livro)))
        for grupo, montar in grupos:
            for i in range(0, len(grupo), LOTE):
                lote = grupo[i:i + LOTE]
                ok, texto, erro = runner(montar(lote), session_key)
                if not ok:
                    saida["erros"].append(f"{mailbox}: IA falhou: {str(erro)[:160]}"); break
                res = parse(texto, nomes)
                for e in lote:
                    saida["lidos"] += 1
                    principal, extras, humano, motivo = res.get(e["id"], (None, [], False, "sem resposta da IA"))
                    do_gmail = e["_filtro_principal"]
                    if do_gmail:
                        if not principal:
                            # a IA não respondeu: o filtro continua valendo, é evidência do remetente
                            principal, motivo = do_gmail, "filtro do Gmail (a IA não respondeu)"
                        elif principal != do_gmail:
                            # quem precisa de conserto é o filtro, e isso é decisão do dono
                            humano = True
                            motivo = f"IA discorda do filtro (filtro: {do_gmail}): {motivo}"[:200]
                            saida["corrigidos"] += 1
                        else:
                            saida["confirmados"] += 1
                        for x in e["_filtro_todos"]:
                            if x != principal and x not in extras:
                                extras.append(x)
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
                              suggested_label=principal, suggested_reason=motivo,
                              suggested_by="filtro+ia" if do_gmail else "ia", suggested_at=agora(),
                              handled=0 if humano else 1, handled_by=None if humano else "ia",
                              handled_reason=None if humano else f"triagem: {principal}" + (f" + {', '.join(extras)}" if extras else ""),
                              synced_at=agora())
                    saida["movidos"] += 1
                    saida["precisa_humano"] += 1 if humano else 0
    auditar(con, "gmail.triage", por, detail=saida)
    return saida
