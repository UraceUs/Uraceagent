# Postman — provando os portões

Esta collection testa a camada de segurança contra o Postgres real. Ela **não
precisa** de servidor Python, de saldo de API nem do agente no ar: as funções
SQL do `db/006` são a camada de tools, e o Supabase as expõe como REST.

## Setup

1. Aplique `db/001` a `db/006` no SQL Editor do Supabase.
2. Rode o catalog sync (ou insira ao menos o programa `one_day`).
3. Importe `urace-postman-collection.json`.
4. Crie um Environment com:

| Variável | Onde achar |
|---|---|
| `supabase_url` | `https://<ref>.supabase.co` |
| `service_key` | Supabase > Project Settings > API > `service_role` |

A `service_role` tem privilégio total. Guarde no Environment do Postman, marcada
como secret, e nunca no repositório.

## Rode na ordem

As pastas constroem estado umas para as outras. A ordem **é** o teste:

| Pasta | O que prova |
|---|---|
| 0 | conectividade e catálogo populado |
| 1 | preço ausente sem pergunta, e ausente sem qualificação |
| 2 | qualificação sendo completada campo a campo |
| 3 | o mesmo pedido agora devolve o número |
| 4 | idade abaixo do mínimo bloqueia reserva, direto na tabela |
| 5 | escalonamento marca takeover e cancela follow-ups |

O par mais importante é **1B vs 3C**: mesma função, mesmo programa, mesmo
parâmetro `p_price_requested: true`. A única diferença é a qualificação, e o
número só existe no segundo. Se o 1B devolver preço, o portão está aberto.

A requisição **"Reserva é bloqueada pelo trigger"** insere direto em
`appointments`, contornando toda a lógica de aplicação. O banco recusa mesmo
assim — é a camada que sobrevive a qualquer erro de prompt ou de código.

## Limpeza

O lead de teste fica no banco. Para remover:

```sql
DELETE FROM leads WHERE name = 'Postman Test';
```

Os dependentes caem por cascade.
