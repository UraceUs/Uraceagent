#!/usr/bin/env python3
"""A resposta do humano chegando ao lead — o elo que faltava no ciclo.

O brief de 25/08 desenha: cliente → agente → (não sei) → Italo/Eduardo →
resposta humana → cliente. Até hoje o último passo era impossível: a ponte
não tinha como falar com um lead fora da janela de ~58s do widget, e
`FOLLOWUP_BOT_ID` nunca esteve configurado. Isso foi resolvido em 25/08
(disparo por `bots/{id}/run` validado ponta a ponta), e esta ferramenta é o
primeiro uso real dele.

É o núcleo DETERMINÍSTICO do loop humano: o parser de intenções do WhatsApp
(próxima etapa) vai chamar exatamente estas mesmas operações. Fazer por CLI
primeiro significa que o caminho crítico já está exercitado e testado antes
de qualquer parsing de linguagem natural entrar no meio.

Uso (no VPS):
    # responder o lead e devolver a conversa ao agente
    python3 salesagent/tools/human_reply.py --lead 31764961 \
        --message "Pode sim trazer seu kart. A gente inspeciona antes." \
        --action resume --by italo

    # responder e encerrar
    python3 salesagent/tools/human_reply.py --lead 31764961 \
        --message "..." --action close --by eduardo

    # só ver em que estado o lead está
    python3 salesagent/tools/human_reply.py --lead 31764961 --status
"""
import argparse
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
sys.path.insert(0, str(BRIDGE))

import app  # noqa: E402
import state  # noqa: E402
import textproc  # noqa: E402
from config import HUMAN_OPERATORS  # noqa: E402

OPERADORES = {o["id"]: o for o in HUMAN_OPERATORS.get("operators", [])}


def mostrar_status(lead_id: int) -> int:
    conv = state.get_conversation(lead_id)
    print(f"lead {lead_id}")
    print(f"  estado:            {conv['state']}")
    print(f"  motivo escalação:  {conv.get('escalation_reason') or '-'}")
    print(f"  re-alertas:        {conv.get('realert_count') or 0}")
    print(f"  esperas enviadas:  {conv.get('holding_count') or 0}")
    print(f"  trilha follow-up:  {conv.get('followup_track') or '-'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int, required=True)
    ap.add_argument("--message", help="texto que o LEAD vai receber")
    ap.add_argument("--action", choices=["resume", "close", "none"], default="resume",
                    help="resume devolve a conversa ao agente; close encerra; "
                         "none só entrega a mensagem e mantém o estado")
    ap.add_argument("--by", default="", help=f"quem autoriza: {', '.join(OPERADORES) or '-'}")
    ap.add_argument("--status", action="store_true", help="só mostra o estado do lead")
    args = ap.parse_args()

    if args.status:
        return mostrar_status(args.lead)
    if not args.message:
        print("--message é obrigatório (ou use --status)")
        return 2

    # Autoridade: §3 do brief. Só operador listado pode responder por um lead.
    if OPERADORES and args.by not in OPERADORES:
        print(f"--by precisa ser um operador autorizado: {', '.join(OPERADORES)}")
        print("(a lista vive em salesagent/config/human-operators.json)")
        return 2
    quem = OPERADORES.get(args.by, {}).get("name", args.by or "humano")

    conv = state.get_conversation(args.lead)
    print(f"lead {args.lead} — estado atual: {conv['state']}")

    # A mensagem passa pelo MESMO saneamento do texto do agente: a regra de
    # dash e a remoção de diretiva valem para tudo que chega a um lead,
    # inclusive texto escrito por gente.
    texto = textproc.customer_facing(args.message)

    entregue = app.deliver_followup(args.lead, texto)
    if entregue:
        print("  bot disparado — a mensagem aparece no chat em segundos")
        print("  (o bot chama a ponte de volta; confira com show_recent_audit.py)")
    else:
        app.kommo.add_note(args.lead, f"[resposta humana — enviar manualmente]\n{texto}")
        print("  NÃO entregue no chat — gravada como nota no card do lead.")
        print("  Causa provável: FOLLOWUP_BOT_ID ausente ou bot recusou o disparo.")

    state.log("human_reply", args.lead, f"{quem} ({args.action}): {texto[:300]}")
    app.kommo.add_note(args.lead, f"[resposta de {quem}] {texto}")

    if args.action == "resume":
        ok = state.transition(args.lead, "RESUMED", f"respondido por {quem}", by_human=True)
        conv2 = state.get_conversation(args.lead)
        state.add_confirmation(args.lead, quem,
                               conv2.get("pending_question")
                               or conv2.get("last_inbound_text") or "", texto)
        state.update_conversation(args.lead, pending_question=None)
        # Zera o alarme: escalação atendida não deve continuar cutucando
        # ninguém, e a próxima escalação deste lead merece alarme novo.
        state.update_conversation(args.lead, realert_count=0, holding_count=0)
        print(f"  estado -> RESUMED {'OK' if ok else '(transição recusada)'}")
    elif args.action == "close":
        ok = state.transition(args.lead, "CLOSED", f"encerrado por {quem}", by_human=True)
        state.update_conversation(args.lead, realert_count=0)
        print(f"  estado -> CLOSED {'OK' if ok else '(transição recusada)'}")
    else:
        print("  estado mantido (--action none)")

    print("\nSe esta resposta é conhecimento novo que o Chase deveria ter na "
          "próxima conversa, o próximo passo do ciclo (knowledge_writer) vai "
          "transformá-la em documento no Brain. Ainda não está implementado — "
          "por ora, registre no Obsidian se valer a pena.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
