# Administrative AI — Descobertas (FASE 2/5, 27/08/2026)

> Levantamento READ-ONLY feito pelos MCPs conectados à sessão Claude.
> Nada foi criado/alterado nas plataformas.

## Conexões vivas (MCPs da sessão)

| Plataforma | Status | Identidade |
|---|---|---|
| Asana | ✅ autenticado | urace@urace.us (Italo Silveira), 2 workspaces (`1205117893189112`, `1205450084498489`) |
| Google Calendar | ✅ autenticado | 16 calendários visíveis |
| QuickBooks | ✅ autenticado | Company **URACE**, industry NAICS **711212** (Racetracks) |
| Gmail | ✅ conectado (conteúdo ainda não sondado) | — |
| Google Drive | ✅ conectado (não sondado) | — |

## Asana — projetos (workspace padrão)

| Projeto | GID | Tarefas (abertas/total) | Papel provável no Admin AI |
|---|---|---|---|
| **U-RACE** | 1205450093098920 | 37/1170 | operação/corridas — candidato a fonte do Workflow 1 |
| **ADM URACE** | 1205530439507169 | 87/1242 | administrativo geral |
| **ADM URace Workflow** | 1213585023616738 | 23/556 | provável casa dos TEMPLATES de processo |
| **Financeiro** | 1209321678013085 | 25/217 | invoices/pagamentos — Workflow 3 |
| CUSTOMERS SERVICE | 1205631592011879 | 41/52 | clientes |
| URace Drivers | 1212344952664712 | 17/19 | pilotos/clientes |
| Shipping Orders | 1215968721507536 | 37/40 | logística |
| Dealer overview | 1215642956993435 | 43/145 | dealers |
| SUITS | 1205661933760052 | 29/179 | equipamentos |
| Marketing / Social Media / Loja / Sponsorships / Business development / Canotops / Alphaline / Silveira Logistics (x2) / URACE AUTO | — | — | fora do MVP |

## Google Calendar — os que importam

| Calendário | ID | Uso no Admin AI |
|---|---|---|
| **Urace Race Calendar** | `c_739bbc...eafe4@group.calendar.google.com` | ALVO do Workflow 1 (corrida→evento) |
| URACE (principal) | `urace@urace.us` | practices and events |
| Urace Team | `c_classroomab7edc43@...` | equipe |
| CALENDÁRIO PESSOAL URACE-GETAVAN | `81b378...@group...` | compromissos das empresas |

(+8 calendários "Transferred from <ex-funcionário>" — legado; fora do MVP.)

## Implicações imediatas para os workflows

- **Workflow 1 (corrida)**: fonte provável = projeto U-RACE; destino = Urace
  Race Calendar. Chave de dedupe natural: GID da task Asana gravado no
  evento (extendedProperties) e vice-versa.
- **Workflow 3 (invoice)**: QuickBooks autenticado e respondendo; projeto
  Financeiro como espelho de estado no Asana.
- **Templates**: brief manda reutilizar — provável em "ADM URace
  Workflow"; PRÓXIMA SONDAGEM: listar tasks-modelo desse projeto.

## Sondagens pendentes (próxima rodada)

1. Estrutura real de uma "corrida" no U-RACE (campos, seções, naming).
2. Templates no ADM URace Workflow (nomes + GIDs).
3. Segundo workspace Asana (o que é?).
4. Gmail: labels e volume (sem ler conteúdo ainda).
5. QuickBooks: clientes/serviços existentes (qbo_contact_search, catalog).
