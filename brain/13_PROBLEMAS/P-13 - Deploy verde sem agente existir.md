---
tipo: problema
tipo_info: FACT
data: 2026-09-02
fonte: log do VPS
responsavel: Italo Silveira
status: resolvido
---

# P-13 — O deploy passou verde sem o agente existir

## O que aconteceu

Entre 01/09 e 02/09/2026, as quatro rotinas do [[VPS e OpenClaw]]
subiram no horário certo e **falharam na primeira linha**, todos os dias:

```
Error: Unknown agent id "urace-admin".
```

`OPENCLAW_AGENT=urace-admin` estava no env desde o começo, mas o agente
**nunca foi criado** no OpenClaw. Existiam só o `main` e o
`urace-sales` — este último é o agente de vendas da era Chase, que está
em `90_ARQUIVO/` e ainda estava marcado como **default**.

## Por que passou despercebido

A prova de instalação verificava duas coisas: **credencial presente** e
**timer ativo**. Nenhuma das duas toca no agente. Um sistema sem
executor nenhum passava nos dois testes.

⚠️ **A lição:** verificação que não chega a executar não prova execução.
Timer ativo prova que o systemd vai chamar; não prova que existe alguém
para atender. Ver [[Preferencias do dono]].

## O que foi feito

1. Agente `urace-admin` criado com workspace próprio, sem `--bind` — ele
   é chamado pelos timers, não recebe conversa de canal. O isolamento
   importa porque as tarefas do [[Asana]] que ele lê são marcações de
   cliente.
2. O instalador passou a **conferir se o agente existe**, e a listar o
   comando de criação quando não existe.
3. Cada timer passou a declarar a credencial que usa; sem ela o timer é
   desligado em vez de acumular falha.

## Fica em aberto

O **default do OpenClaw ainda é o `urace-sales`**, arquivado. Chamada
sem `--agent` cai nele. Mover o default mexe em roteamento de canal —
decisão do dono, ainda não tomada.

## Relacionado

[[VPS e OpenClaw]] · [[Administrative AI]] · [[Problemas]] ·
[[Etapa de conexão]] · [[2026-09-02]]
