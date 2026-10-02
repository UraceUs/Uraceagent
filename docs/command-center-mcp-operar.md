# Operar o Command Center pelo Claude (MCP)

Dono, 02/10 (#73): *"os nossos vendedores... usam o Claude nas máquinas deles, nos terminais...
conectar por um MCP... de acordo com o nível de hierarquia ali do operador ou gerente... consiga
fazer tudo, não só a leitura."*

## Conectar (uma vez por computador)

No terminal do vendedor, com o Claude Code instalado:

```
claude mcp add --transport http urace https://urace-bridge.duckdns.org/ops/mcp
```

Depois, dentro do Claude Code, digite `/mcp`, escolha **urace** e **Authenticate**. O navegador
abre o login do Command Center:

1. entre com o **seu** usuário do painel (o de sempre);
2. na tela de autorização, deixe marcado **"Também operar o painel como você"**;
3. clique em **Autorizar**.

Pronto. O Claude passa a agir **como você**, com o **seu** papel. Sem a caixa marcada, o acesso
só lê. Para desligar: revogue no painel ou rode `claude mcp remove urace`.

> Ninguém precisa copiar senha, token ou chave para o chat ou para arquivo nenhum: o login é pelo
> navegador, e o Claude Code guarda o acesso sozinho.

## O que dá para fazer

Tudo o que o seu papel faz no painel. O Claude descobre com a ferramenta **`urace_operacoes`**
(filtre com uma palavra: `agendamento`, `invoice`, `waiver`, `venda`) e executa com
**`urace_api`**. São as mesmas rotas dos botões do painel. Por isso:

- o **operador** não faz o que é do **gerente** (valor da mensalidade, mover serviço de card,
  bloquear agenda…): a resposta diz qual papel precisa;
- as travas de sempre valem: não cobrar duas vezes, não pôr serviço de um cliente no card de outro,
  o que é "nunca" continua nunca;
- tudo fica na **auditoria** com o seu nome (evento `mcp.call` mais o evento da própria rota).

### O dia a dia de vendas

| Para | Operação |
|---|---|
| achar o cliente | `GET /ops/api/clients?q=…` · `GET /ops/api/clients/{id}` |
| criar o cliente | `POST /ops/api/clients` |
| agendar (tarefa no Asana pelo modelo oficial) | `POST /ops/api/tasks` |
| confirmar ou recusar pedido do site | `POST /ops/api/site/agendamentos/{id}/confirmar` |
| abrir a oportunidade | `POST /ops/api/sales` |
| registrar a ligação | `POST /ops/api/sales/{id}/call` |
| fechar a venda (cliente, invoice, waiver, Asana, Kommo) | `POST /ops/api/sales/{id}/close` |
| reenviar só a invoice ou só a waiver | `POST /ops/api/sales/{id}/step/{passo}` |
| enviar waiver avulsa | `POST /ops/api/waivers/send` |

### Confirmação antes de mandar para fora

O que vai para o cliente ou cobra (invoice, waiver, e-mail, QuickBooks, DocuSign, Asana, Kommo)
**não acontece na primeira chamada**. O Claude recebe o que vai ser feito, mostra para você, e só
repete com `confirmar: true` depois do seu "pode mandar".

## Para a TI

- O servidor de login é o próprio painel (OAuth 2.1 com PKCE). O escopo `mcp:write` só sai quando
  a pessoa marca a caixa **e** é OPERATOR ou acima; rebaixada a pessoa, o token volta a ler.
- Chave de API (`urk_…`) sem "só leitura" também opera, pelo papel da chave.
- Ficam fora do MCP: login, senha e chaves (`/ops/api/auth/*`) e a área do cliente (`/ops/api/portal/*`).
- Código: `command_center/api/mcp_operar.py`; testes: `command_center/tests/test_mcp_operar.py`.
