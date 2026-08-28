# Parâmetros operacionais — os valores que a IA usa

> **ESTE É O ÚNICO LUGAR ONDE SE ALTERA ESSES VALORES.**
> Mudou aqui, mudou em todo lugar. Não repita número nenhum destes
> dentro de código, script ou prompt — todos leem daqui.

## Security deposit

```
SECURITY_DEPOSIT_USD = 400
```

Valor fixo por serviço, cobrado via QuickBooks. **Para alterar: troque o
número acima e mais nada.** Quem mudar, anote quando e por quê:

| Data | Valor | Quem | Motivo |
|---|---|---|---|
| — (desde sempre até 28/08/2026) | US$ 400 | — | valor histórico, confirmado pelo dono em 28/08 |

## Cronograma padrão de corrida

```
DIAS_ANTES_CHEGADA_EQUIPE = 2   # equipe chega (à noite)
DIAS_ANTES_TREINO_URACE   = 1   # nosso treino com os pilotos
```

Contados a partir do **primeiro dia do evento**. Sequência completa:
chegada da equipe → treino URACE → treino oficial → classificação →
corrida. Exemplo do dono: evento nos dias 3, 4 e 5 → nosso treino no dia
2 → equipe chega no dia 1. Logo, `start_on` da tarefa = dia 1.

Exceção: evento nosso (não é corrida de campeonato), como a semana de
prática de 25–27/09 em Jacksonville — ali as datas são as do próprio
serviço.

## Devolução do security deposit

```
DIAS_APOS_SESSAO_PARA_DEVOLVER = 5
```

Sessão na segunda → devolução na sexta. O valor devolvido é o depósito
**menos** as peças usadas (que saem do Service Order do mecânico e viram
invoice do cliente). Devolução pelo *merchant view* do QuickBooks, na
mesma forma de pagamento.

## Identificador de local/categoria (campo `Race`, obrigatório)

| Valor | Quando usar |
|---|---|
| `Practice OKC` | prática em Orlando (Orlando Kart Center) — **o caso padrão** |
| `Practice Bushnell` | prática em Bushnell |
| `KART` | corrida de kart |
| `F4` | corrida de Fórmula 4 |

A maioria das práticas é em Orlando. Outro local só quando avisado.
Preencher é **imprescindível** — é por este campo que a automação separa
prática de corrida e kart de F4.
