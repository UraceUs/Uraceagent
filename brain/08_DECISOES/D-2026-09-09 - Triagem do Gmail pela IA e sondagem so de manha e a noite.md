---
tipo: decisao
data: 2026-09-09
fonte: dono (chat)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-09 — Triagem do Gmail pela IA (marcador principal) e sondagem só de manhã e à noite

**Dono, 09/09/2026:** *"quero ver o e-mail como vejo no Gmail"* (corpo com
imagens, não texto com links); *"a IA leia cada e-mail, adicione
marcadores e mova pro marcador principal"*, usando a hierarquia dos
marcadores — compra na Amazon leva a etiqueta **Amazon**, mas o
principal é **Receipts**; rodar **de manhã, à tarde e à noite**. Na aba
Gmail o marcador é escolhido **por busca ao digitar**; dá para adicionar
vários; **clicar num marcador adicionado move o e-mail** para ele. E a
**checagem das integrações é só de manhã e à noite**, não a cada hora;
*"se cair enquanto a IA usa, aí a IA checa"*.

**Como ficou:**
- Corpo da mensagem vem em HTML com as imagens inline embutidas, limpo
  de script/handler/iframe, servido com CSP própria e mostrado num
  iframe com sandbox. Link "ver só o texto" para o modo antigo.
- **Triagem automática** às **07:00, 13:00 e 21:00** (hora de Orlando),
  regra `gmail_triagem` em Automação (dá para desligar). A IA recebe o
  corpo de cada thread, responde `principal` + `marcadores` +
  `precisa_humano`, tudo validado contra a lista real da caixa; o painel
  aplica pela porta `triar_ia` (todos os marcadores + sai da inbox). O
  que ela não decide fica na inbox; o que pede resposta continua em
  **Precisa de atenção** mesmo fora da inbox. Botão "Triar com a IA
  agora" na aba.
- Esta porta **substitui, só para a triagem, a regra "só wNews sai da
  inbox"** de [[D-2026-09-04 - Clique humano move e-mail para o marcador]];
  a ferramenta `gmail_rotular` do agente continua com a regra antiga.
- Marcadores na thread: chips clicáveis (clicar = mover); campo de busca
  por digitação para adicionar (`/emails/{id}/labels`, não tira da
  inbox). A IA continua sem criar marcador.
- **Sondagem das integrações** às **07:00 e 22:00** (regra
  `sondagem_integracoes`); fora disso só re-sonda o sistema que falhar
  numa sincronia ou numa ação da IA, no máximo uma vez a cada 10 min.
  "Verificar agora" continua manual.
- O timer antigo `urace-triagem-email` (07:00, agente solto) sai do
  instalador: rodaria junto com a triagem nova e o VPS não aguenta dois
  agentes ([[2026-09-09]]).

Relacionado: [[Taxonomia do Gmail]], [[Triagem de e-mail]], [[Gmail]].
