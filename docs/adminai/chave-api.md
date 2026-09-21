# Chave de API do Command Center

Pedido do dono em 21/09: *"preciso montar uma chave api desse command center"*. Outro
sistema (n8n, um script, uma integração) precisa falar com o painel **sem navegador** — e
sem afrouxar nada do que já protege a porta.

## Criar

**Usuários → Chaves de API → Criar chave** (só ADMIN). Escolha:

| campo | o que decide |
|---|---|
| **Para que serve** | o nome que vai aparecer na lista e na auditoria |
| **Papel** | o que a chave **alcança**: Leitura, Operador, Gerente, Administrador |
| **Só leitura** | se ela pode **mexer**. Ligado por padrão |
| **Age como** | a pessoa que a chave representa — e o **teto** do que ela alcança |
| **Validade** | em dias; em branco, não expira |

A chave aparece **uma única vez**, na criação. Depois disso ela não existe em lugar nenhum:
o banco guarda só o hash (scrypt, como senha). Perdeu? Revogue e crie outra — ninguém,
nem o ADMIN, nem a IA, consegue ler uma chave já criada.

## Usar

```bash
curl -s https://urace-bridge.duckdns.org/ops/api/dashboard \
  -H "Authorization: Bearer urk_xxxxxxxxxx_SEGREDO"
```

Também vale `X-API-Key: urk_…`. Quem entra por chave **não recebe cookie e não passa por
CSRF** — não há cookie de sessão para um site de terceiro abusar. Em compensação, a chave
não abre sessão, não troca senha e não vira "acesso livre".

Qualquer rota do painel responde à chave, respeitando o papel dela. Exemplos úteis:

| rota | papel mínimo | o que devolve |
|---|---|---|
| `GET /ops/api/dashboard` | Leitura | números do dia |
| `GET /ops/api/needs-attention` | Leitura | o que precisa de ação |
| `GET /ops/api/crm/inbox` | Leitura | conversas do chat |
| `POST /ops/api/crm/leads/{id}/reply` | Operador | responder no chat do lead |
| `GET /ops/api/clients` | Leitura | clientes |

## Papel e escrita são coisas separadas

Em 21/09 a primeira chave de verdade foi para um **agente de IA fora do painel, com acesso
ao financeiro**. Ver o financeiro e mandar mensagem para cliente não podem vir no mesmo
pacote — então o papel diz o que a chave *alcança* e `read_only` diz se ela pode *mexer*.

Uma chave Gerente só-leitura lê QuickBooks, invoices, auditoria, conversas e clientes, e
qualquer `POST`/`PUT`/`PATCH`/`DELETE` dela volta 403. **Só leitura é o padrão**: escrever
é exceção, marcada na mão.

Se você tirar a marca, o aviso na tela é literal e vale repetir aqui: o que a chave fizer
**acontece de verdade** — a mensagem sai para o cliente, o preço muda no QuickBooks — sem
passar por aprovação nenhuma. O portão de APLICAR e as políticas da IA valem para o que a
IA propõe *dentro* do painel; uma chave que escreve é tratada como pessoa agindo.

## As três travas

1. **A chave age como uma pessoa, e nunca passa do que essa pessoa alcança.** Criar uma
   chave ADMIN "em nome de" um operador é recusado na hora. Chave não é como alguém
   consegue o que não tem.
2. **Rebaixou a pessoa, a chave desce junto.** O papel efetivo é o menor entre o papel da
   chave e o papel atual da pessoa, conferido a cada pedido — ninguém precisa lembrar de
   revogar. Desativou a pessoa, a chave morre.
3. **Acesso livre não se herda.** A conta sem cargo opera solta no navegador; a chave dela
   continua presa ao papel escolhido.

## Acompanhar e desligar

A lista mostra último uso, IP, quantas vezes e validade. `urk_<id>` é **público de
propósito** — aparece no log e na auditoria, e sozinho não abre nada; o que abre é o
segredo, que não é guardado.

**Revogar** corta na hora: o pedido seguinte recebe 401. Criação e revogação ficam em
`audit_logs` (`apikey.create`, `apikey.revoke`), sem o valor da chave.

## Se a chave vazar

Revogue no painel (efeito imediato) e crie outra. Não existe "trocar o segredo" de uma
chave: a identidade dela é o segredo.
