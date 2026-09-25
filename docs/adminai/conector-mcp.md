# Ligar o Command Center como conector (MCP por HTTP)

Dono, 23/09: expor o painel como conector, para um Claude de fora usar ferramentas em
vez de ele virar o terminal de ninguém.

O servidor MCP do painel já existia desde 21/09 (`adminai/mcp/command_center_mcp.py`),
mas falava **stdio** — serve para quem roda na mesma máquina. Conector remoto precisa de
HTTP. É só isso que foi acrescentado: `POST /ops/mcp`, com as mesmas ferramentas.

## O que ele dá

Quinze ferramentas, **todas de leitura** — nove do painel e seis do Kommo:

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
| `urace_kommo_conta` | a conta do Kommo ligada (nome, moeda, funis) |
| `urace_kommo_funis` | funis e etapas, com os ids para filtrar |
| `urace_kommo_leads` | leads recentes, por funil, etapa ou texto |
| `urace_kommo_lead` | um lead; com `completo=true`, tudo: contatos, perfis, eventos, conversa |
| `urace_kommo_conversa` | conversa e anotações de um lead, em ordem |
| `urace_kommo_chats` | movimento do chat por canal (até 30 dias) |

### O Kommo (25/09)

As `urace_kommo_*` chamam as funções de **leitura** do servidor MCP do Kommo
(`adminai/mcp/kommo_mcp.py`) pelo mesmo carregador que o painel já usa. O token continua
em `~/.urace/kommo.env` — o conector nunca o vê. As portas de escrita do módulo
(`*_humano`: mover etapa, tag, nota, responder, atribuir) **não são registradas**; um teste
roda cada ferramenta contra o módulo de verdade e confere, na ida à rede, que nenhum
pedido sai com outro verbo que não GET. Sem `kommo.env`, a ferramenta responde o motivo em
vez de cair. As chamadas rodam fora do laço de eventos, para uma consulta lenta ao Kommo
não travar o painel.

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

## Login: o painel virou servidor OAuth (24/09)

A dúvida acima foi respondida do jeito difícil. O conector recusou a chave fixa e falhou
com *"não foi possível registrar no serviço de login"* — ele tenta **registro dinâmico de
cliente** (RFC 7591). Então o painel passou a ser esse serviço de login.

O que existe agora:

| endereço | para quê |
|---|---|
| `/.well-known/oauth-authorization-server` | onde ficam os endereços de login (RFC 8414) |
| `/.well-known/oauth-protected-resource` | qual login vale para o `/ops/mcp` (RFC 9728) |
| `/ops/oauth/register` | o cliente se apresenta e ganha um `client_id` |
| `/ops/oauth/authorize` | **a tela onde uma pessoa aprova**, logada no painel |
| `/ops/oauth/token` | troca do código pelo token, com PKCE |
| `/ops/oauth/revoke` | derruba o acesso na hora |

E o 401 do `/ops/mcp` passou a trazer `WWW-Authenticate` apontando para a descoberta —
sem isso o cliente não tem como achar o login, que foi onde ele parou.

**As travas, e o que cada uma impede:**

- **PKCE obrigatório (S256).** Código interceptado na volta do navegador não vira token.
- **`redirect_uri` conferido byte a byte.** `startswith` aqui já foi ataque real:
  `https://meusite.com` casaria com `https://meusite.com.invasor.net`.
- **Código de uso único.** Reuso é sinal de interceptação: a segunda tentativa falha e
  **todos os tokens daquele cliente são revogados**, porque nesse ponto não dá para saber
  quem é o legítimo. Fica na auditoria.
- **Refresh rotativo.** O refresh usado morre; um roubado só vale até o dono renovar, e a
  renovação denuncia o roubo.
- **Nada em claro.** Código, token e segredo de cliente viram hash antes de tocar o banco.
- **Quem autoriza é gente.** O `/authorize` exige sessão do painel e mostra o que está
  sendo aprovado. Não existe caminho em que um programa se autorize sozinho.
- **O token não escreve.** Vale a mesma trava da chave só-leitura — conferida num lugar
  só para as duas credenciais, depois de um defeito meu em que o token OAuth escreveu.

O Caddy precisa entregar `/.well-known/oauth-*` ao painel. O script de deploy já cuida.

## Revogar

Some do conector na hora: Usuários → Chaves de API → revogar. A chave revogada volta a
dar 401 na requisição seguinte, e a revogação fica na auditoria.
