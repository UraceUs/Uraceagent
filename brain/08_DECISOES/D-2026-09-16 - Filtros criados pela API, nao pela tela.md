---
tipo: decisao
data: 2026-09-16
fonte: dono
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-16 — Os filtros do Gmail passam a ser criados pela API

[[Taxonomia do Gmail]] · [[Gmail]] · [[D-2026-09-14 - A IA sugere marcador novo, mas nao cria]]

## Por que mudou

A importação pela tela do Gmail falhou por dois motivos independentes, os dois no
mesmo dia:

1. **Conta delegada não muda configuração.** A `urace@` estava sendo operada por
   delegação (login do Eduardo). Ao clicar em "Criar filtros", o Google pediu
   reautenticação da dona da caixa — e delegado não pode responder por ela.
2. **Um clique a mais criou duas importações.** A aba estava em segundo plano, o
   primeiro clique pareceu não responder, e nasceram duas janelas de 89 filtros.
   Se as duas tivessem rodado, eram 178 filtros — cada um em dobro.

Resultado: **0 de 89 criados**, e um susto.

## A decisão

Criar os filtros **pela API**, do painel: botão *Criar no Gmail* no card de
filtros. Sem arquivo, sem janela de escolher arquivo, sem delegação, e com trava
de duplicata — o filtro que já existe **igual** (mesmo critério, mesmos
marcadores) é pulado.

## O custo, dito na hora

Exige o escopo **`gmail.settings.basic`**, que **não existe só para filtros**: ele
também abre encaminhamento, resposta automática e endereços de envio. O dono
autorizou sabendo disso. As travas ficam no código, não no escopo — como já é o
caso do envio de e-mail desde 04/09:

- marcador tem de existir (a IA não cria marcador);
- arquivar só com a família `wNews`;
- `TRASH` e `SPAM` nunca;
- **só cria**: nunca apaga nem edita filtro, inclusive os 41 que já existiam.

O XML continua sendo gerado e continua baixável — quem quiser importar à mão,
importa. A API é o caminho principal porque é o que não trava.

## Como terminou (mesmo dia)

A `support@` foi inteira pela API: painel respondeu **"2 criado(s), 22 já
existiam"** — a trava de duplicata funcionou (as 22 derivadas de remetente já
estavam lá) e os 2 criados são as duas regras que o dono ditou, `Softwares|Apps/Docusign`
e `Waivers`, que sustentam o fluxo da waiver.

Essas duas custaram duas tentativas com **HTTP 400 "Filter doesn't have any
criteria"**: o critério ia como `hasTheWord`, que é o nome **na tela** do Gmail —
na API o campo é `query`. A API descarta campo que não conhece **sem reclamar do
nome** e depois diz que o filtro está vazio, o que manda o diagnóstico para o lado
errado. `criar_filtro_humano` passou a traduzir o nome e a **recusar campo
desconhecido** na entrada (`063099a`), para o erro aparecer onde ele nasce.

A `urace@` ficou com as 89 novas sobre as 41 antigas, importadas pela tela antes
desta decisão valer. Da próxima vez que precisar de filtro lá, é pela API também.
Falta uma contagem real das duas caixas para fechar o número — comando no diário
de 16/09.
