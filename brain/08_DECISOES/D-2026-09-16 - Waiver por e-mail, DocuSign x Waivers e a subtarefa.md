---
tipo: decisao
data: 2026-09-16
fonte: dono (ditado)
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-16 — DocuSign × Waivers, e o que a IA faz quando a waiver chega por e-mail

[[Taxonomia do Gmail]] · [[Triagem de e-mail]] · [[DocuSign]] · [[D-2026-09-10 - Waiver em toda tarefa]]

## A regra dos dois marcadores (support@)

> *"Quando chegue alguma coisa do DocuSign, sempre tenha o marcador
> `Softwares|Apps/Docusign`. E só quando for uma waiver que foi enviada, ou uma
> waiver que foi recebida assinada, marcar com a `Waivers`."*

- **Todo** e-mail do DocuSign → `Softwares|Apps/Docusign`, sem exceção.
- Waiver **enviada** ("Please Complete the Docusign: … Waiver of Liability") ou
  **assinada** ("Completed: …") → leva **também** `Waivers`.
- "Visualizou" e "anulada" **não** entram em `Waivers`.

Vira filtro nativo ditado (`REGRAS_DO_DONO` no gerador): remetente fixo + nome do
modelo. É a única regra com assunto que existe, e por isso.

## O que a IA faz num e-mail com `Waivers`

> *"Vai abrir o e-mail, vai abrir o anexo, vai baixar aquele anexo para colocar dentro
> do Command Center. Já marcar na tarefa daquele serviço que a waiver já está assinada.
> Nas próximas tarefas daquele cliente, já deixar pré-marcado."*

1. **Descobre de quem é**: o nome do signatário (ou do menor) da waiver conhecida
   que aparece no assunto/corpo. Sem casar com ninguém, o e-mail fica para uma
   pessoa — nunca chuta.
2. **Liga o e-mail ao cliente** (`emails.client_id`) — aparece no card dele.
3. **Garante o PDF no card**: primeiro pela API do DocuSign (fonte de verdade, traz
   o certificado); se a API falhar, **pelo anexo do próprio e-mail**.
4. **Fecha a subtarefa da waiver** ("Signed waiver?") e anexa o PDF em **todas as
   tarefas abertas** do cliente que ainda não a tinham.
5. As **próximas** tarefas já nascem com a waiver: isso o `task.created` cobria
   desde 10/09 — só faltava fechar a subtarefa, que agora fecha junto.

Tudo mecânico e auditado (`email.waiver_ligada`, `task.waiver_anexada`,
`waiver.assinada.tarefas`). Nada passa pelo agente nem por aprovação: é o
procedimento que o dono descreveu, palavra por palavra.

## O que já existia e o que faltava

Já existia (11/09): espelho dos envelopes, vínculo waiver → cliente, download do
PDF pela API, anexo na tarefa nova. **Faltava**: fechar a subtarefa, agir quando a
assinada chega em tarefa que **já existia**, ligar o e-mail ao cliente, e a reserva
pelo anexo. O evento `waiver.completed`, que só acordava a IA para comentar, agora
faz o trabalho mecânico antes.
