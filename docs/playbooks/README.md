# Playbooks do Command Center

Dono, 13/10 (#199): *"um playbook de como operar dentro do Command Center, que seja entendido
tanto por IA quanto por um humano, para eu poder estar passando isso para o time"*.

| Playbook | Para quem | Como usar |
|---|---|---|
| [Geral](playbook-geral.md) | todo mundo da equipe e o Claude de cada um | ler primeiro; a IA cola nas instruções do Projeto do Claude ou num `CLAUDE.md` |
| [Vendas](playbook-vendas.md) | quem vende e o Claude dessa pessoa | depois do geral; os roteiros da seção 9 são o dia a dia |
| [Mecânicos e coaches](playbook-mecanicos-e-coaches.md) · [PDF](playbook-mecanicos-e-coaches.pdf) | o box: mecânico e coach têm o mesmo acesso | foco no calendário (Meu dia) e no balcão de peças; o PDF sai de `gerar_pdf_mecanicos.py` |
| [Suits](../suits-guia-do-lucas.md) | quem opera os macacões e o Claude dessa pessoa | guia da aba Suits |

Os playbooks descrevem o que o código faz hoje. Mudou tela ou processo, o playbook do assunto
muda no mesmo PR (regra no `CLAUDE.md`).

No painel: **Administrativo › Como usar** (`/ops/como-usar`) mostra estes guias, baixa cada um em `.md` (e o dos
mecânicos em PDF) e gera o **MD para a sua IA** (`/ops/api/guia/para-ia.md`), que junta tudo (#223).
