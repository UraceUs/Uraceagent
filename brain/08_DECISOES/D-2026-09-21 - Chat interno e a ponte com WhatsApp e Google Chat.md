---
tipo: decisao
tipo_info: DECISION
status: ativo
owner: Italo Silveira
data: 2026-09-21
fonte: dono, 21/09/2026 + leitura das APIs (Meta e Google) na mesma data
---

# D-2026-09-21 — Chat interno: ponte, não substituição

[[URACE]] · [[Command Center - Proximos passos]] · [[Administrative AI]]

## O que o dono decidiu

*"queria uma ponte, onde unisse ambos tanto o whatsapp e o google chat"*.

Quem está onde hoje:

| onde | quem |
|---|---|
| **WhatsApp** | mecânicos, coach, designers, fornecedor de suit |
| **Google Chat** | staff administrativo, financeiro e comercial |

## O que as APIs permitem (lido em 21/09, não de memória)

### Google Chat — dá para fazer ponte de verdade

Um app do Chat assina eventos pela **Google Workspace Events API** e recebe mensagem
nova, reação, entrada e saída de gente. Com **assinatura de nível de organização**
(`chat.app.all.messages.readonly`), o app vê as conversas da empresa **sem precisar ser
membro de cada espaço**. Escrever é uma chamada de API comum.

Sem janela de tempo. Sem custo por mensagem. Sem aprovação prévia de texto.
**Este lado é o fácil.**

### WhatsApp — dá, com três pedágios que mudam o projeto

1. **Janela de 24 h.** Livre para responder até 24 h depois da última mensagem da pessoa.
   Fora disso, só **template aprovado pela Meta**, e cada um **custa**. Para um chat de
   equipe isso é sério: "chegou a peça do kart 12" às 22h para um mecânico que não fala
   desde ontem não sai como texto solto — sai como template pago, ou não sai.
2. **Grupo tem limite duro.** A Groups API existe (2026), mas: **no máximo 8
   participantes**, entrada só por link de convite, exige **Official Business Account**,
   **uma só empresa Cloud API por grupo** e o número **não pode ser um número do app
   WhatsApp Business**. Ou seja: os grupos que a equipe já usa **não são "conectáveis"** —
   teriam de ser recriados como grupos de API, com até 8 pessoas, e todo mundo entrando de
   novo pelo convite.
3. **Bibliotecas não oficiais** (whatsapp-web.js, Baileys) contornariam tudo isso e
   **violam os termos do WhatsApp**, com risco real de banir o número da empresa — o mesmo
   número por onde entram os leads. **Não vou por esse caminho**, e registro aqui para não
   ser proposto de novo daqui a três meses.

## A decisão de desenho

**O Command Center vira o hub; os dois viram canais — mas com pesos diferentes.**

- **Google Chat: ponte completa.** O que é escrito lá aparece no painel, e o que é escrito
  no painel aparece lá. Espelho de mão dupla, sem pedágio.
- **WhatsApp: ponte com o que a API permite**, e com o painel assumindo o papel de origem.
  Conversa 1:1 (fornecedor de suit, um mecânico específico) funciona bem dentro da janela.
  Grupo de equipe **não** se espelha sem recriar como grupo de API de até 8.
- **Chat nativo no painel**, com **notificação push no celular via PWA**. Este é o ponto
  que decide a adoção: se o mecânico recebe no celular sem custo por mensagem e sem janela
  de 24 h, o painel deixa de perder para o WhatsApp — que era a objeção certa do dono. Web
  Push funciona em Android e em iPhone a partir do iOS 16.4, com o site instalado na tela
  inicial.

A regra que resolve a tensão: **o que é operação (serviço, corrida, peça, cliente) tem
casa no painel**; WhatsApp e Google Chat são por onde a mensagem *alcança* quem ainda não
está no painel.

## O que fica travado no dono

- [ ] Número do WhatsApp para a API: o atual dos leads (via Kommo) ou um segundo número?
      Um número no app WhatsApp Business **não** pode ter grupos de API.
- [ ] Official Business Account na Meta (verificação da empresa) — sem isso, grupo nem
      começa
- [ ] Aceitar recriar os grupos de equipe como grupos de API de até 8 pessoas, ou manter
      grupo no WhatsApp comum e usar o painel para o que é operação
- [ ] Workspace: confirmar que dá para instalar um app do Chat na organização (precisa de
      admin do Google Workspace)

## Ordem de construção

1. **Chat nativo + push** — não depende de ninguém, e é o que segura os mecânicos
2. **Ponte do Google Chat** — depois do admin liberar o app
3. **Ponte do WhatsApp** — depois das decisões acima; 1:1 primeiro, grupo só se ele aceitar
   o limite de 8

## Fontes

- WhatsApp Groups API e limites — [imBee](https://www.imbee.io/resource/whatsapp-groups-api-business-guide-2026) · [Unipile](https://www.unipile.com/whatsapp-group-api/) · [Sanuker](https://sanuker.com/whatsapp-groups-api-en/)
- Janela de 24 h e templates — [smsmode](https://www.smsmode.com/en/whatsapp-business-api-customer-care-window-ou-templates-comment-les-utiliser/) · [Twilio](https://www.twilio.com/docs/whatsapp/key-concepts)
- Google Chat e eventos — [Subscribe to Google Chat events](https://developers.google.com/workspace/events/guides/events-chat) · [Work with events from Google Chat](https://developers.google.com/workspace/chat/events-overview)
