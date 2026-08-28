# Skills da URACE — uma por aplicação

Decisão do dono (28/08/2026): **cada aplicação vira uma skill separada**
(Asana, Gmail, Calendar, QuickBooks…), e **tudo alimenta o segundo
cérebro da URACE no Obsidian**. O sistema é a IA — o Claude Code é
backup, não o destino final.

## Por que skill, e não script

A skill é **portátil**: o mesmo arquivo vale nos dois lugares.

| Onde | Como instalar |
|---|---|
| **VPS / OpenClaw** (destino) | copiar a pasta da skill para o diretório de skills do agente |
| **Claude Code** (backup e desenvolvimento) | `ln -s $(pwd)/skills ~/.claude/skills/urace` ou copiar para `.claude/skills/` |

Script resolve uma tarefa; skill carrega **o julgamento** — a taxonomia,
as regras de negócio, o tom, o que nunca fazer. É por isso que o
conhecimento levantado nestes dias mora aqui e não dentro de um `.py`.

## As skills

| Skill | Aplicação | Estado |
|---|---|---|
| `urace-obsidian` | **contrato compartilhado** — como toda skill escreve no segundo cérebro | base das demais |
| `urace-asana` | U-RACE, SUITS, Shipping Orders, ADM URACE | operação mapeada e validada |
| `urace-gmail` | triagem diária de `urace@urace.us` | taxonomia lida da conta |
| `urace-calendar` | corridas do Asana → Urace Race Calendar | mínima, depende do Asana |

## Perfil por área (o que o dono chamou de "sessão diferente")

Cada skill é pensada para um **agente/perfil próprio** no OpenClaw, com
só as ferramentas da sua área. Um agente que cuida do Gmail não precisa
de acesso ao QuickBooks. Isso é menor privilégio — a mesma regra que já
vale para o agente de vendas não ter shell.

## Valores que mudam: um lugar só

Fornecedor atual, valores, prazos, contas, IDs — tudo em
**`brain/00_SYSTEM/PARAMETROS.md`**. Nenhuma skill repete esses valores;
todas leem de lá. O dono muda num lugar e o sistema inteiro acompanha.

## Invariantes que valem em TODAS as skills

1. **A IA não envia invoice.** Prepara, preenche, revisa. Enviar é humano.
2. **A IA não envia e-mail** — só rascunho. Exceções autorizadas, e
   só estas duas: pedido de medidas ao cliente do macacão e pedido de
   produção ao fornecedor.
3. **Não apagar, não destruir, não regenerar credencial.** Antes de
   qualquer coisa com risco real de perda, pedir autorização.
4. **Nunca inventar dado.** Sem fonte, escalar — não deduzir.
5. **Conferir por leitura direta**, nunca pelo retorno da escrita nem
   pela busca (a busca do Asana atrasa; `rc=0` não é prova).
6. **Chave externa é a identidade** (gid do Asana, número do pedido, id
   do QuickBooks). Nunca casar por nome.
7. **Registrar o que fez** — comentário na tarefa e linha no diário do
   Obsidian. "Por que a IA fez isso?" tem que ter resposta.
