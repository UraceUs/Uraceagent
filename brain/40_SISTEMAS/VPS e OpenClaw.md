---
tipo: sistema
tipo_info: FACT
fonte: adminai/deploy + docs/openclaw-setup.md
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# VPS e OpenClaw

[[Sistemas]] · [[Administrative AI]] · [[Etapa de conexão]]

Onde o [[Administrative AI]] realmente mora. O Claude Code é backup e
ambiente de desenvolvimento — **o destino é aqui**.

## O que roda sozinho

| Rotina | Quando | Processo |
|---|---|---|
| Triagem de e-mail | todo dia **07:00** | [[Triagem de e-mail]] |
| Varredura de waiver | todo dia **07:30** | [[Waiver de responsabilidade]] |
| Sincronia status ↔ quadro | seg–sex **06:40** | [[Compra e envio]] |
| Saúde do grafo | segunda **06:00** | [[Como o cérebro cresce]] |

Todas com `Persistent=true`: VPS desligado na hora não perde a execução.

## Como está montado

- **Segredos** em `~/.urace/adminai.env`, permissão 600, **fora do
  repositório**. Nunca no cérebro, nunca no git.
- **Skills** ligadas por link simbólico de `skills/` para o diretório do
  OpenClaw — `git pull` atualiza a skill sem reinstalar nada.
- **Logs** em `~/.urace/logs/`.
- **`APLICAR=0` é o padrão**: tudo em simulação até o dono ler os
  relatórios e liberar.

## O que o token do [[Asana]] destrava

Além das rotinas: **anexar arquivo na tarefa**, via REST
`POST /attachments`. O conector do Claude não faz isso — é o
[[P-09 - Conector do Asana nao sobe anexo]], e é o que trava o passo do
anexo da waiver assinada.

## Runbook

`adminai/deploy/README.md` — instalação, verificação real (não `rc=0`),
comandos do dia a dia e o que fazer quando der errado.
