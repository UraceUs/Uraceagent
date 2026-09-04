---
tipo: estado
tipo_info: CONTEXT
data: 2026-09-04
fonte: consolidação do cérebro, diários e histórico do repositório
responsavel: Italo Silveira
status: ativo
---

# Administrative AI — estado completo em 04/09/2026

[[URACE]] · [[Administrative AI]] · [[Painel do Brain]] · [[Semana 2026-08-31 a 2026-09-04 - Resumo]]

> Este arquivo é a **fotografia inteira** do projeto: o que já existia
> antes desta semana, o que evoluiu nela, e como está agora. Abra por
> aqui para ver "como é que está". O detalhe de cada ponto está nas notas
> ligadas.

## 1. O que é

Uma camada de inteligência operacional sobre as ferramentas que a
[[URACE US INC]] já usa — [[Asana]], [[Gmail]], [[QuickBooks]],
[[DocuSign]], [[Google Calendar]] — com tudo alimentando o segundo cérebro
no Obsidian. Sucede o [[Projeto Chase]] (encerrado em 27/08/2026): o
gargalo real não era vender, era administrar. Construído **por partes e
por aplicação** ([[D-2026-08-28 - Construir por partes e por aplicacao]]).
Roda no **[[VPS e OpenClaw]]**; o Claude Code é oficina, não destino.

**Pessoas:** [[Italo Silveira]] (dono, decide tudo) · [[Eduardo Resende]]
(logística e compras; administrador do Command Center) · [[Lara Carvalho]]
· [[Luis Barros]] · [[Anabelly]] · [[Lucas Azaro]] (papel em aberto, U-06).

## 2. Onde tudo está

| O quê | Onde | Estado |
|---|---|---|
| **Command Center** | https://urace-bridge.duckdns.org/ops/ | no ar desde 04/09; login próprio |
| Pit Wall (painel do cérebro) | https://urace-bridge.duckdns.org/painel/ | código pronto, **não publicado** no VPS |
| Páginas legais (QuickBooks) | https://urace-bridge.duckdns.org/legal/privacy.html | no ar desde 01/09 |
| Repositório e PR | https://github.com/UraceUs/Uraceagent/pull/2 | branch `claude/configurar-open-claw-ooqo8x` |
| DNS | https://www.duckdns.org | `urace-bridge`, `urace-claw` → 34.230.114.116 |
| Asana, quadro U-RACE | https://app.asana.com/0/1205450093098920/board | modelo de sessão gid `1208702559561159` |
| DocuSign produção | https://app.docusign.com/home · https://apps.docusign.com/admin | conta `4261a166-…d657c52`, base `na4` |
| Gmail | https://mail.google.com/mail/u/0/ · https://mail.google.com/mail/u/1/ | `urace@` e `support@`, token por caixa |
| Google Cloud (OAuth interno) | https://console.cloud.google.com/apis/credentials?project=urace-administrative-ai | sem revisão do Google |
| QuickBooks | https://qbo.intuit.com/ | **stand-by** ([[P-11 - Producao do app QuickBooks travada]]) |
| Segredos | `~/.urace/adminai.env`, tokens do Google, chave RSA | só no VPS, permissão 600, nunca no git |

Documentos: `docs/adminai/command-center-adr.md` · `docs/adminai/docusign-go-live.md`
· `docs/adminai/google-conexao.md` · `docs/adminai/intuit-app-review.md` ·
`adminai/deploy/README.md`.

## 3. Linha do tempo — do começo até hoje

| Quando | O que aconteceu | Nota |
|---|---|---|
| 27/08 | Projeto Chase encerrado; nasce o Administrative AI | [[Projeto Chase]] |
| 28/08 | Cérebro reconstruído como rede; primeiras escritas reais no Asana; processos ditados pelo dono (macacão, depósito, triagem); regras corrigidas pelo dono | [[2026-08-28]] |
| 31/08 | Cérebro tipado (decisões, problemas, "Comece aqui"); QuickBooks sondado e POP fechado; DocuSign mapeado; pacote de deploy pronto | [[2026-08-31]] |
| 01/09 | **Deploy no VPS**: 4 timers; QuickBooks trava na Intuit (P-11); DocuSign trava na Integration Key (P-12) | [[2026-09-01]] |
| 02/09 | Descoberto P-13 (deploy verde sem agente); agente criado de verdade; **MCP próprios** de Asana e DocuSign; primeira varredura de waivers conferida | [[2026-09-02]] |
| 04/09 manhã | **DocuSign em produção**; **Google conectado**; primeira triagem; VIP dispensa waiver; RACES fora | [[2026-09-04]] |
| 04/09 tarde/noite | **Command Center** construído e publicado; Gmail por dentro; DocuSign com ações; um card por cliente; Asana por dentro; **IA age a cada mudança e aprende pelo balão** | [[2026-09-04]] |

## 4. Estado por aplicação — antes da semana × agora

| Aplicação | Em 31/08 | Em 04/09 |
|---|---|---|
| [[Asana]] | mapeado, escrita liberada, sem token no VPS | **MCP próprio no VPS**; quadro inteiro espelhado (menos "Matt tasks"); calendário, quadro, lista e detalhe ao vivo no Command Center; ADM URACE e Matt tasks só leitura em código |
| [[DocuSign]] | conector sondado, sem credencial própria | **produção**, JWT, 50+ envelopes; envio com 4 travas (aprovação); download, lixeira, reenvio, vínculo ao cliente pelo painel |
| [[Gmail]] | só `urace@`, triagem especificada | **as duas caixas** por MCP próprio; triagem real; inbox por dentro no painel; sugestão de marcador por regras e IA; mover por clique humano |
| [[QuickBooks]] | processo completo, pode criar, não envia | **stand-by** (Intuit); painel honesto; invoice só depois de aprovada ([[D-2026-09-04 - Invoice sai depois de aprovada no painel]]) |
| [[Google Calendar]] | mínimo | leitura pelo MCP do Google (`calendar_eventos`) |
| [[Rate Card]] | fonte de preço | leitura pelo MCP (`sheets_ler`); 4 células ainda a corrigir à mão |
| Cérebro | reorganizado | 24 decisões, 13 problemas, 5 diários; sincronizado para dentro do agente a cada rotina |
| Painel | Pit Wall desenhado | Pit Wall roda mas não publicado; **Command Center** o substitui |

## 5. O que a IA faz hoje, e com que gate

| Área | Sozinha (leitura e proposta) | Com aprovação humana | Nunca |
|---|---|---|---|
| [[Asana]] | ler, buscar, comentar, criar/mover tarefa (SAFE) | — | mexer em ADM URACE e Matt tasks |
| [[DocuSign]] | ler, varredura diária, ligar envelope a cliente | **enviar waiver** | apagar; anular assinada |
| [[Gmail]] | triar, classificar, sugerir marcador, rascunhar | — | **enviar e-mail**; TRASH/SPAM |
| [[QuickBooks]] | (quando conectar) criar invoice/estimate | **enviar invoice** | apagar |
| Painel | acordar em cada mudança, propor, aprender | aprovar executa | agir sem registro |

Regras em código, fora do alcance do agente: os **botões humanos** do
Command Center (mover e-mail, anular/reenviar waiver) são funções que o
MCP não expõe.

## 6. Como a IA opera (o ciclo)

1. **Fontes → espelho.** A cada 15 min (ou no botão) o Command Center lê Asana, DocuSign e Gmail. Sem credencial: "não conectado". Sem dado inventado.
2. **Mudança → evento.** Tarefa nova de cliente, e-mail de cliente conhecido, waiver devolvida ou assinada.
3. **Evento → agente.** Regra ligada (Automação) → comando ao `urace-admin` com contexto do cliente e a memória.
4. **Agente → proposta.** Ações declaradas com argumentos exatos (`ACAO: ferramenta | alvo | resumo | json`).
5. **Política → gate.** SAFE executa; waiver e invoice **exigem aprovação**; apagar e enviar e-mail **bloqueados**.
6. **Aprovar → executar → auditar.** Pelo próprio painel.
7. **Balão → memória.** O que o dono ensina em "Precisa de atenção" entra em `ai_learnings` e em todo comando seguinte.

## 7. Decisões (todas)

**28/08** — [[D-2026-08-28 - Autonomia para corrigir erro rastreado]] · [[D-2026-08-28 - Construir por partes e por aplicacao]] · [[D-2026-08-28 - Deposito e um por cliente]] · [[D-2026-08-28 - IA envia a invoice do deposito]] · [[D-2026-08-28 - PARAMETROS e o ponto unico de alteracao]]

**31/08** — [[D-2026-08-31 - Agente de invoice pode criar]] · [[D-2026-08-31 - Cobranca por lote]] · [[D-2026-08-31 - Conhecimento da era Chase fica no arquivo]] · [[D-2026-08-31 - IA envia a waiver]] · [[D-2026-08-31 - Margem de 15 por cento na peca]] · [[D-2026-08-31 - Rate Card acima do catalogo do QuickBooks]] · [[D-2026-08-31 - Sem modelo de email de invoice]] · [[D-2026-08-31 - Sessao extra e mensal do Academy]] · [[D-2026-08-31 - Templates vazios do DocuSign]] · [[D-2026-08-31 - Texto do Adult Waiver fica como esta]] · [[D-2026-08-31 - Waiver vale um ano]]

**01/09** — [[D-2026-09-01 - Manter o par RSA do DocuSign demo]]

**04/09** — [[D-2026-09-04 - Renato Pionti sem waiver nesta sessao]] · [[D-2026-09-04 - Invoice sai depois de aprovada no painel]] · [[D-2026-09-04 - Senha do Command Center com minimo de 5]] · [[D-2026-09-04 - Clique humano move e-mail para o marcador]] · [[D-2026-09-04 - Lixeira e reenvio de waiver pelo painel]] · [[D-2026-09-04 - O que e cliente, ativo, e um card por pessoa]] · [[D-2026-09-04 - IA age a cada mudanca e aprende pelo balao]]

## 8. Problemas (todos) e estado

| | Estado |
|---|---|
| [[P-01 - Modelo de tarefa fora do padrao]] | aberto — modelo corrigido; tarefas antigas seguem fora |
| [[P-02 - Campos do modelo em branco]] | aberto — o parser tolera; a IA agora identifica a pessoa pelo título |
| [[P-03 - Colunas dos dias com servico velho]] | aberto — "Precisa de atenção" aponta tarefa vencida |
| [[P-04 - Contas a receber concentradas]] | aberto — depende do QuickBooks (P-11) |
| [[P-05 - Security deposit quase nao aparece]] | aberto |
| [[P-06 - Precos defasados no catalogo do QuickBooks]] | aberto — Rate Card manda |
| [[P-07 - Waivers paradas desde junho]] | aberto — agora com reenviar/corrigir e-mail pelo painel |
| [[P-08 - Order Number guardando URL]] | aberto — clique do dono no Asana |
| [[P-09 - Conector do Asana nao sobe anexo]] | **resolvido** pelo MCP próprio (`asana_anexar_arquivo`) |
| [[P-10 - Email de cliente trocado]] | aberto — a varredura por cliente ajuda a achar |
| [[P-11 - Producao do app QuickBooks travada]] | **aguardando a Intuit** |
| [[P-12 - Integration Key do DocuSign so nasce em demo]] | **resolvido** 04/09 (produção) |
| [[P-13 - Deploy verde sem agente existir]] | **resolvido** 02/09 |

## 9. Pendente de clique do dono

| O quê | Onde | Por quê |
|---|---|---|
| Sincronizar agora e conferir Clientes / Possíveis duplicados | Command Center | primeira leitura completa com as regras novas |
| Aprovar ou rejeitar a primeira proposta da IA | Command Center → Aprovações | fecha o ciclo evento → proposta → execução |
| Ensinar os valores do [[Rate Card]] | Command Center → Automação e memória | a IA prepara invoice sem perguntar |
| Corrigir 4 células de preço | [[Rate Card]] (Sheets) | mensal e extra do 4T/Baby Kart |
| Remover `Order number` do SUITS | [[Asana]] | API deu `Access denied` |
| Criar 14 regras status ↔ quadro | [[Asana]] | não existe endpoint |
| Criar `wNews` na `support@` | [[Gmail]] | sem ele a propaganda fica na inbox |
| Decidir `APLICAR=1` para as rotinas | VPS | hoje o agente simula; o painel executa |
| Publicar o Pit Wall | VPS (`servir_painel.sh`) | opcional |
| `sendReminder` do DocuSign | decisão | a IA pode cutucar quem não assinou? (U-01) |

## 10. Lacunas de conhecimento

Ver [[Conflitos e lacunas]]: U-06 papel do Lucas Azaro · U-08 Offsight ·
C-02 horário (qua–dom 8h–13h) × coluna TUESDAY.

## 11. As armadilhas que mais custaram (para não repetir)

1. O cliente do QuickBooks e quem assina a waiver é o **responsável**, não o piloto.
2. A busca do Asana atrasa; conferir por leitura direta.
3. `delivered` no DocuSign **não é assinado**; só `completed`.
4. Preço sai da Rate Card, não do catálogo do QBO; pacote se calcula do mensal.
5. Um deploy "verde" pode não ter criado o agente (P-13). Sempre provar na fonte.
6. Terminal do Lightsail cai no silêncio; usar `tmux`.
7. Teste "sem credencial" no VPS pode falar com o sistema real se a credencial estiver no caminho padrão; isolar HOME.
8. Um processo antigo pode continuar respondendo depois do "restart"; confirmar o PID.

## 12. Números

| | |
|---|---|
| Commits desde 27/08 | 100+ (74 nesta semana) |
| Decisões | 24 |
| Problemas | 13 (3 resolvidos, 1 aguardando terceiro) |
| Testes automatizados | 44 (Command Center) + 9 (renderizador) |
| Envelopes DocuSign visíveis | 50+ |
| Rotinas no VPS | 4 timers + Command Center com sincronia a cada 15 min |

Índices: [[Decisoes]] · [[Problemas]] · [[Processos]] · [[Sistemas]] · [[Clientes]] · [[Equipe]]
