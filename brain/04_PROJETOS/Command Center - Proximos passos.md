---
tipo: projeto
tipo_info: CONTEXT
status: ativo
owner: Italo Silveira
data: 2026-09-21
fonte: dono, 21/09/2026 (lista dos próximos módulos)
responsavel: Italo Silveira
---

# Command Center — Próximos passos

[[URACE]] · [[Administrative AI]] · [[Projetos]]

Lista viva. O dono pediu em 21/09: *"deixe sempre os próximos passos como checkboxes
para conseguirmos ter um bom track do que precisa ser feito"*. Quem marca o que está
feito é o trabalho entregue, não a intenção.

**Legenda:** 🔒 travado esperando alguma coisa · 👤 depende do dono · 🤖 posso tocar sozinho

## A ordem importa

Os seis módulos não são independentes. **Estoque é a espinha**: o PDV não existe sem ele,
e tanto pedido interno quanto envio são movimentos que entram e saem dele. Construir PDV
antes de estoque é construir caixa sem saber o que tem na prateleira.

    Estoque ──┬── Pedidos internos (entra no estoque)
              ├── Envios (sai do estoque / vai para o cliente)
              └── PDV (vende o que está no estoque, fatura no QuickBooks)

Chat interno e Checklists não dependem de nada disso e podem andar em paralelo.

---

## 1. Chat interno da equipe

Hoje a equipe se fala por WhatsApp e Google Chat. O objetivo é unificar dentro do
Command Center.

- [x] 👤 **Decidido em 21/09: ponte**, unindo WhatsApp e Google Chat — não substituição
- [x] 👤 Quem usa o quê: **WhatsApp** mecânicos, coach, designers, fornecedor de suit ·
      **Google Chat** staff adm, financeiro e comercial
- [x] 🤖 APIs levantadas em 21/09 (ver [[D-2026-09-21 - Chat interno e a ponte com WhatsApp e Google Chat]]):
      Google Chat espelha inteiro, sem pedágio; WhatsApp cobra três pedágios — janela de
      24 h com template pago fora dela, grupo de API com **no máximo 8 pessoas** e que não
      conecta em grupo já existente, e número que não pode estar no app WhatsApp Business
- [x] Desenhar o modelo: canal ligado a corrida, serviço, cliente ou livre; mensagem já
      nasce com `origem` e `external_id` para a ponte não precisar migrar conversa depois
- [x] 🤖 **Base construída** (21/09): tabelas, API e testes do chat interno
- [x] 🤖 Tela do chat interno no painel (lista + conversa, pensada para celular)
- [x] 🤖 **Chat de gente** (dono, 21/09): conversa direta em um clique pela lista de
      pessoas, grupo com nome/ícone/foto/participantes, e silenciar por pessoa — vale para
      conversa individual e para grupo
- [x] 🤖 **Notificação push (PWA)** — construída em 21/09: chave VAPID própria, assinatura
      por pessoa e por aparelho, aviso sem o texto da conversa, aparelho morto limpo sozinho
- [x] 🤖 Instalação na tela inicial (manifest, ícone, instrução própria para iPhone)
- [ ] 👤 Ligar a notificação no seu celular e mandar o teste (Equipe → "Ligar notificação")
- [x] 👤 **App nativo: não por ora.** PWA instalado na tela inicial; Capacitor só se
      aparecer maquininha, código de barras pesado ou offline longo
- [ ] 👤 Admin do Google Workspace liberar o app do Chat na organização — **é o único
      bloqueio que sobrou** nesta frente
- [ ] 🤖 Ponte do Google Chat (depois do admin liberar)

**WhatsApp: parado por decisão do dono em 21/09** — *"não vamos usar o wpp por enquanto"*.
Os limites já estão medidos em [[D-2026-09-21 - Chat interno e a ponte com WhatsApp e Google Chat]];
quando voltar, ninguém precisa redescobrir. O WhatsApp de cliente segue pelo Kommo, como
hoje. O da equipe continua onde está, sem ponte.

## 2. Checklists de serviço e corrida

O que mecânicos e staff preenchem hoje no Google Forms.

- [ ] 🔒👤 **Receber os formulários atuais do Google Forms** — travado nisto. Sem ver o
      que eles já preenchem, eu inventaria checklist, e checklist inventado ninguém usa.
- [ ] 🤖 Ler os Forms e as respostas (o painel já tem acesso ao Google Drive)
- [ ] Mapear: quais são por serviço, quais por corrida, o que é obrigatório, quem preenche
- [ ] Modelo de checklist (template) + preenchimento (resposta), ligado a serviço/corrida
- [ ] Tela de preencher pensada para celular e para mão suja: poucos toques, offline se der
- [ ] Foto anexada no item (pneu, dano, peça trocada)
- [ ] O que fazer com checklist incompleto: vira item em "Precisa de atenção"

## 3. Tracking de pedidos internos (peças, ferramentas, pneus)

O que a URACE compra para si.

- [ ] 👤 Como o pedido nasce hoje? (alguém pede no WhatsApp? Eduardo compra? tem
      aprovação?) — o fluxo real, não o ideal
- [ ] Modelo: pedido → itens → fornecedor → status → chegada
- [ ] Estados do pedido (pedido, confirmado, em trânsito, chegou, conferido)
- [ ] Quando chega, **entra no estoque** (liga com o módulo 5)
- [ ] Nota fiscal / recibo anexado e ligado ao QuickBooks (despesa)
- [ ] Aviso de pedido que não chegou no prazo

## 4. Tracking de envios

Suits, peças da loja do eBay, peças específicas compradas para clientes.

- [ ] 👤 Quais transportadoras e quais lojas (eBay, outras?)
- [ ] Modelo: envio → itens → destinatário (cliente ou endereço) → rastreio → status
- [ ] Rastreio automático (código da transportadora), se a API permitir
- [ ] Ligar ao cliente: o envio aparece no card dele
- [ ] Sai do estoque quando despachado (liga com o módulo 5)
- [ ] Avisar o cliente do envio — e decidir se é automático ou com aprovação

## 5. Estoque — a espinha

Chassis, motores, pneus e peças. Inclui **peça que está com a URACE mas é do cliente**
(normalmente cliente Pro).

- [x] 👤 **Dois tipos, decidido em 22/09.** Chassi e motor: ficha individual com número de
      série. Pneu e peça de consumo: quantidade. São dois comportamentos no mesmo módulo —
      misturar num modelo só é o erro clássico que trava o sistema depois.
- [x] 👤 **Dois locais, decidido em 22/09:** sede e trailer de corrida.
- [ ] Modelo: item → tipo → quantidade ou série → local → **dono** (URACE ou cliente)
- [ ] Peça de cliente: ligada ao card do cliente, nunca vendável para outro, aparece no
      card dele
- [ ] Movimentos: entrada (pedido chegou), saída (venda, uso em serviço, envio), ajuste
      (contagem), transferência (sede ↔ trailer)
- [ ] Contagem física / inventário, com quem contou e quando
- [ ] Estoque mínimo por item → avisa em "Precisa de atenção" antes de faltar
- [ ] 👤 **Decidir a fronteira com o QuickBooks.** Proposta: o painel manda no estoque
      físico, o QuickBooks manda no financeiro. Controlar quantidade nos dois lados gera
      divergência garantida, e aí ninguém acredita em nenhum dos dois.
- [ ] 🤖 Construir o módulo (agora destravado pelas duas decisões acima)

## 6. PDV no celular, integrado

Mecânico vende peça direto ao cliente pelo celular, com ou sem ajuda da IA.

- [ ] 🔒 **Depende do módulo 5** (estoque) — sem saber o que tem, não há o que vender
- [x] 👤 **Como o cliente paga: QuickBooks**, sempre (dono, 21/09). Link ou QR aberto no
      celular do próprio cliente — sem maquininha, sem hardware no box. Isso também
      decidiu o app: PWA basta, ver [[D-2026-09-21 - Celular e PWA, sem app nativo]]
- [ ] Tela de venda pensada para celular: acha o cliente, acha a peça, quantidade, pronto
- [ ] Preço vem da **Rate Card** (regra do dono, 18/09) — e peça mantém o preço
- [ ] Baixa no estoque na hora da venda
- [ ] Vira invoice ou recibo no QuickBooks, ligado ao cliente certo
- [ ] Papel de quem pode vender (mecânico = OPERATOR) e o que ele **não** pode (dar
      desconto? vender fiado?) 👤
- [ ] Venda offline (sem sinal no box) e sincroniza depois — decidir se entra agora
- [ ] Ajuda da IA: achar a peça pela descrição do mecânico ("pastilha do kart do Pedro")

---

## Decisões do portão — fechadas em 22/09

Ver [[D-2026-09-22 - Lembrete de waiver, arquivar no Gmail e o guarda-chuva do apagar]].

- [x] 👤 As 8 decisões pendentes respondidas na página editável
- [x] 🤖 `apagar_qualquer_coisa` → `REQUIRES_APPROVAL`, e voltou a ser **piso** de todo
      apagar: ação nova com apagar/excluir/deletar/remover no nome não passa mais por baixo
- [x] 🤖 `gmail_rotular` → `SAFE`, com a trava: arquivar só com marcador **confirmado** no
      painel. Sem banco, volta à regra estreita de antes (só `wNews`)
- [x] 🤖 `docusign_send_reminder` → `SAFE`, com a trava: só cliente com serviço marcado,
      3 dias antes e 1 dia antes, **no máximo 2 por envelope**
- [x] 🤖 23 testes das três travas (`test_travas_decididas.py`)

## De quem é cada serviço (22/09) — o card do David Pera

Ver [[D-2026-09-22 - O titulo da tarefa diz de quem e o servico]].

- [x] 🤖 Extrator do nome no título reescrito com o gabarito do dono: de 27/70 para 70/70
- [x] 🤖 Primeiro nome sozinho, inicial abreviada e categoria colada passaram a ser lidos
- [x] 🤖 Camadas para achar o card certo; ambíguo volta para humano, nunca é chutado
- [x] 🤖 Varredura e conserto do quadro inteiro (`/service-attribution` e
      `adminai/atribuir_servicos.py`), auditado
- [ ] 👤 **Rodar a varredura na VPS e olhar a lista antes de aplicar**
- [ ] 👤 Decidir os nomes ambíguos que a varredura apontar (ex.: `Alexander` — Savage ou Jacoby?)
- [ ] 👤 Decidir os nomes de uma palavra só que não têm card (ex.: `Mariano`, `G.J`, `Levi`)
- [ ] 🤖 Depois de aplicar: rever os pares de duplicados que aparecerem no painel

## Vem de antes (21/09, aprovado e ainda devendo)

- [ ] 🤖 Artifact editável do APLICAR=1: o que o agente escreveria sozinho × o que ainda
      precisa de aprovação
- [ ] 🤖 Asana P-01/02/03: os consertos seguros, como ações com política
- [ ] 🤖 Order Number P-08: extrair o código do pedido
- [ ] 👤 Responder Charles (#33988589) e True X Miami (#33998731) — sem resposta desde 19/09
- [ ] 👤 Anular o envelope duplicado da Letícia no DocuSign
- [ ] 👤 Decidir se o Austin precisa de waiver nova
