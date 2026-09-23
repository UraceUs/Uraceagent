# Playbook comercial — lições da operação irmã (AZ Car Rental)

Extraído de `COMECE_AQUI.md` e `COPY_RESPOSTAS_URACE.md` (base de trabalho
real, 21-23/09/2026). Não é teoria — cada regra aqui custou um erro real
medido na operação. Ler antes de rodar qualquer loop de resposta/follow-up.

## As duas regras que fazem tudo funcionar

1. **Ler antes de perguntar.** Se a resposta está na base (`CLAUDE.md`,
   `data/leads_master.xlsx`, notas do Kommo/Asana), usar — não perguntar
   de novo ao dono.
2. **Confirmou? Escrever na hora.** O dado no lugar certo, o que mudou
   registrado com data e fonte. Nunca apagar o que outro agente escreveu.

## Regras de loop (custaram horas de CRM parado até serem aprendidas)

- **Rearmar é a última ação de todo turno, sem exceção** — inclusive turno
  que foi só conversa com o dono, ou com fila vazia.
- **Não filtrar a fila por tempo recente.** Filtrar "mexeu nos últimos 45
  min" esconde quem está parado há dias. Nas etapas que significam "é a
  sua vez": pegar tudo, ordenar do mais antigo. Filtro de tempo serve só
  pra achar quem respondeu agora, nunca pra achar a fila.
- **GUARD antes de escrever** — checar se já falaram com essa pessoa hoje
  antes de mandar de novo. Evita mandar 2x pro mesmo cliente.
- **Se a última fala for do cliente, é a sua vez** — mesmo que hoje já
  tenha rolado alguma coisa no card (evento de sistema não conta).
- **Bot atropelando vendedor**: se o robô repete pergunta já respondida,
  assumir a conversa na hora, não deixar o robô insistir.

## Fronteira entre agentes (o que resolveu a sobreposição)

> **O cliente respondeu nas últimas 48h?**
> SIM → quem fecha/negocia · NÃO → follow-up só reaquece
> Já é cliente ativo → operação/pós-venda · Organizar card → organizer,
> nunca fala com cliente

Handoff: follow-up reaquece, cliente responde, vira pra quem fecha — entrega
a bola e sai.

## Venda

- **Preço só de tabela, uma fórmula única, nunca dizer a porcentagem de
  desconto ao cliente** — falar o número convida a negociar percentual.
- **Foto/mídia junto com a cotação, uma mensagem só** — nunca antes do
  cliente responder à primeira mensagem.
- **O fecho pede o pagamento.** Não abrir dizendo "não precisa pagar nada
  agora" — isso entrega a saída antes de pedir a venda.
- **"Obrigado" não encerra conversa** — é recusa educada sem motivo.
  Perguntar o que faltou (preço, produto, atendimento).
- **Honestidade vende mais que desconto** — assumir erro próprio, não
  empurrar pro cliente; recusar dar desconto por custo de terceiro.

## Estrutura de toda resposta (COPY_RESPOSTAS_URACE.md)

```
[GANCHO]     o que ELE disse ou fez, nas palavras dele
[RESPOSTA]   o que ele perguntou, direto, sem rodeio
[UMA PERGUNTA] o dado que falta — quase sempre a idade do piloto
```

Sem gancho, mensagem fria vira STOP. Com gancho pra quem já conversou,
zero STOP — medido, não teoria.

## As seis regras que não se quebram

1. Uma ideia por mensagem.
2. Termina pedindo UM dado — de preferência a idade do piloto.
3. Primeira mensagem sem link e sem foto — entram na segunda, depois que
   a pessoa responde.
4. Nunca prometer data — pode citar a janela da pista, quem trava o dia
   é o Lucas/Italo.
5. Preço só o de tabela. Desconto e promoção: só com o dono.
6. Não inventar nada — cidade, idade, o que a pessoa pediu, origem do
   contato. Sem dado, pergunta.

## Reativação (quem falou e sumiu)

- Só com gancho, e só dentro da janela.
- **Janela de 24h do Meta**: fora dela a plataforma recusa a mensagem.
  Reativar gente antiga não é mensagem — é anúncio de reengajamento, pra
  a pessoa escrever de novo e reabrir a janela.
- Teto: máximo 2 tentativas por pessoa, formato diferente na segunda
  (texto → link/imagem). Não existe terceira.

## Quando parar e chamar o dono

Pediu data firme · pediu desconto ou preço fora da tabela · falou de
pagamento/waiver/caução · reclamação ou assunto sensível · um humano já
respondeu na thread (o bot cala a boca e sai na hora).
