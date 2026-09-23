# Ligar o Command Center como conector (MCP por HTTP)

Dono, 23/09: expor o painel como conector, para um Claude de fora usar ferramentas em
vez de ele virar o terminal de ninguém.

O servidor MCP do painel já existia desde 21/09 (`adminai/mcp/command_center_mcp.py`),
mas falava **stdio** — serve para quem roda na mesma máquina. Conector remoto precisa de
HTTP. É só isso que foi acrescentado: `POST /ops/mcp`, com as mesmas ferramentas.

## O que ele dá

Nove ferramentas, **todas de leitura**:

| ferramenta | o que responde |
|---|---|
| `urace_resumo` | panorama em números — a melhor primeira pergunta |
| `urace_atencao` | o que precisa de gente hoje, já priorizado |
| `urace_estoque` | saldo de cada item, o que é nosso, o que falta repor |
| `urace_estoque_item` | uma peça com o razão que explica o saldo |
| `urace_clientes` | busca de clientes |
| `urace_cliente` | ficha completa: serviços, invoices, waivers, peças dele |
| `urace_invoices` | quem deve, quanto, desde quando |
| `urace_corridas` | calendário da equipe |
| `urace_auditoria` | quem fez o quê e quando |

## Por que não há nenhuma que escreve

Três travas, e elas valem juntas:

1. **O catálogo.** A ferramenta que não deve existir simplesmente não é registrada. Não
   é confiança no modelo: não há como desobedecer o que não existe.
2. **A conexão.** A rota abre o banco em `mode=ro`. O SQLite **recusa** escrita por ela.
   Se um dia alguém acrescentar por engano uma ferramenta que grava, ela falha em vez de
   gravar — promessa virou impedimento.
3. **A chave.** Criada como `read_only` no painel.

Se um dia um Claude de fora precisar **agir**, o caminho certo não é uma chave que
escreve: é propor a ação no painel, com política e aprovação humana, como a IA de dentro
já faz.

## Ligar

**1. Crie a chave** no painel: Usuários → Chaves de API → nova, papel **VIEWER**,
**só leitura** marcado. Ela aparece **uma vez** — copie na hora, porque depois só o hash
existe no banco.

**2. Confirme que a rota responde** (na VPS):

```bash
curl -s -H "Authorization: Bearer urk_..." https://urace-bridge.duckdns.org/ops/mcp | head -3
```

Tem de vir `{"ok": true, ... "somente_leitura": true}`. O Caddy já manda `/ops*` para o
serviço, então **não há nada novo para configurar no servidor web**.

**3. Conecte** em https://claude.ai/customize/connectors, apontando para
`https://urace-bridge.duckdns.org/ops/mcp`. Depois **abra uma sessão nova**: conector é
lido quando a sessão começa.

## O que ainda não sabemos

Como o claude.ai apresenta a autenticação de um conector remoto pode pedir **OAuth** em
vez de aceitar uma chave fixa no cabeçalho. Este servidor fala Bearer, que é o que a
especificação do MCP usa. Se a tela pedir OAuth, é outro trabalho — um servidor de
autorização — e não adianta eu afirmar que funciona antes de você tentar.

## Revogar

Some do conector na hora: Usuários → Chaves de API → revogar. A chave revogada volta a
dar 401 na requisição seguinte, e a revogação fica na auditoria.
