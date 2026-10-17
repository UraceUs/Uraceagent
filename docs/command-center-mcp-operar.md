# Operar o Command Center pelo Claude (MCP)

Dono, 02/10 (#73): *"os nossos vendedores... usam o Claude nas máquinas deles, nos terminais...
conectar por um MCP... de acordo com o nível de hierarquia ali do operador ou gerente... consiga
fazer tudo, não só a leitura."*

## Conectar

O passo a passo também está no painel: **Equipe › Conectar o Claude**, com o endereço pronto para copiar.

### No app do Claude (celular, computador ou claude.ai)

1. Configurações › **Conectores** › **Adicionar conector personalizado**.
2. Nome: **URACE Command Center**. URL: **só** o endereço `https://ops.urace.us/ops/mcp`.
   O campo não aceita o comando do terminal.
3. **Conectar**: entre com o **seu** usuário do painel, deixe marcado **"Também operar o painel como
   você"** e clique em **Autorizar**.

Se a conta do Claude for **Team ou Enterprise**, o dono pode adicionar o conector nas configurações
da **organização** (Conectores): ele aparece para todos os membros, e cada um ainda entra com o
próprio usuário. Em conta individual, cada pessoa adiciona o seu.

### No terminal (Claude Code), uma vez por computador

```
claude mcp add --transport http urace https://ops.urace.us/ops/mcp
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
| aceitar ou recusar pedido do site | `POST /ops/api/site/agendamentos/{id}/aceitar` · `…/{id}/recusar` (confirmar sem pagamento e waiver, `…/{id}/confirmar`, é do gerente) |
| abrir a oportunidade | `POST /ops/api/sales` |
| registrar a ligação | `POST /ops/api/sales/{id}/call` |
| fechar a venda (cliente, invoice, waiver, Asana, Kommo) | `POST /ops/api/sales/{id}/close` |
| reenviar só a invoice ou só a waiver | `POST /ops/api/sales/{id}/step/{passo}` (a invoice que espera o gerente não sai por aqui) |
| cobrar só o depósito que faltou | `POST /ops/api/sales/{id}/deposit` |
| liberar invoice fora da tabela (gerente) | `POST /ops/api/sales/{id}/invoice/liberar` |
| card de irmão | `POST /ops/api/clients` com `irmao_de` |
| responder no chat do Kommo | `POST /ops/api/crm/leads/{id}/reply` |
| enviar waiver avulsa | `POST /ops/api/waivers/send` |

### Confirmação antes de mandar para fora

O que vai para o cliente ou cobra (invoice, depósito, waiver, e-mail, QuickBooks, DocuSign, Asana,
Kommo — inclusive o chat do Kommo, `/ops/api/crm/…`: responder, anotar, etapa, tags)
**não acontece na primeira chamada**. O Claude recebe o que vai ser feito, mostra para você, e só
repete com `confirmar: true` depois do seu "pode mandar".

### Uma cobrança por vez (#310)

As travas da venda valem igual pelo MCP, pelo botão e pela IA, ao mesmo tempo: a invoice que já saiu
(ou a venda paga no site, no Stripe) não sai de novo; nenhum passo roda antes de fechar; e quem chega
enquanto outra saída cobra a mesma venda recebe 409 ("… está mandando a invoice agora"). Se uma
tentativa caiu depois do QuickBooks responder, a resposta é 409 "A tentativa de … não terminou:
confira no QuickBooks se a invoice saiu". Só o gerente (ou o dono), depois de conferir, resolve. Não
saiu: repete com a confirmação da rota, `"confirmar": true` no `corpo` do `close` e do
`invoice/liberar`, ou `{"confirmar": true}` na `consulta` de `step/qbo` e `deposit` (é outro
`confirmar`, além do do MCP). Saiu: `POST /ops/api/sales/{id}/invoice/registrar` com `{"numero": "…"}`,
que confere no QuickBooks antes de gravar. A invoice criada cujo envio falhou sai de novo só por
`POST /ops/api/sales/{id}/invoice/reenviar` (a mesma invoice).

## Para a TI

- O servidor de login é o próprio painel (OAuth 2.1 com PKCE). O escopo `mcp:write` só sai quando
  a pessoa marca a caixa **e** é OPERATOR ou acima; rebaixada a pessoa, o token volta a ler.
- Chave de API (`urk_…`) sem "só leitura" também opera, pelo papel da chave. A chave já criada passa de
  "só leitura" para operação (e volta) em **Usuários › Chaves de API › Liberar para operar**, sem
  trocar o valor; só o administrador muda, e fica na auditoria (`apikey.mode`, #209).
- Ficam fora do MCP: login, senha e chaves (`/ops/api/auth/*`) e a área do cliente (`/ops/api/portal/*`).
- Código: `command_center/api/mcp_operar.py`; testes: `command_center/tests/test_mcp_operar.py`.
