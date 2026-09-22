---
tipo: decisao
tipo_info: DECISION
status: ativo
owner: Italo Silveira
data: 2026-09-22
fonte: dono, 22/09/2026 — card do David Pera
---

# D-2026-09-22 — O título da tarefa diz de quem é o serviço

[[URACE]] · [[Asana]] · [[Command Center - Proximos passos]]

## O que ele viu

Foi marcar uma sessão nova para o **David Pera**, abriu o card e encontrou **113
serviços** — 112 de outras pessoas: Jude Cook, Harley Keeble, Alexander Jacoby,
Brody Robbin, Alex Xikis, Charlie Marron, Liam Bourghol, Branson, Mariano, G.J…

> *"Está errado da forma que está. A gente precisa identificar e distribuir esses
> serviços dentro do card de cada pessoa."*

E completou: *"isso já foi algo que eu já tinha passado e não foi aplicado"* — a regra
de 16/09 ([[D-2026-09-16 - Piloto nao e servico, documento interno e a IA dentro da tarefa]])
existia, mas só reconhecia nome com duas palavras ou mais.

## Onde estava o erro

O extrator acertava **27 de 70** títulos reais do quadro. Tudo que ele errava tinha a
mesma causa: **nome de uma palavra só era descartado** — e metade do quadro escreve só o
primeiro nome (`Branson_Practice KA100`, `Charlie_Orlando Cup`, `Savage_RWC RD2`). Sem
nome no título, a tarefa caía na descrição; quando a descrição não ajudava, ia para um
card genérico. Um desses cards genéricos se chamava **"Date of birth"**, e foi ele que o
dono uniu ao David Pera — trazendo 112 serviços junto.

Agora acerta **70 de 70**. O gabarito é a lista que ele mandou, com o nome do cliente
marcado por ele entre parênteses em cada formato.

## A gramática do título (seis formas)

| No título | Cliente | O que separa |
|---|---|---|
| `Aaron Benoit_Trackside Support` | Aaron Benoit | `_` |
| `Harley Keeble - Rotax [3/3]` | Harley Keeble | hífen com espaço |
| `Alexander Jacoby \| KA100` | Alexander Jacoby | `\|` |
| `David Pera Using his own Kart` | David Pera | só o espaço, antes da palavra de serviço |
| `Jude cook/Harley client - Kart proprio` | Jude cook | `/`, nunca entre números (`3/6`) |
| `Alex Xikis KA100_Professional Coaching` | Alex Xikis | categoria colada sai fora |

Mais: primeiro nome sozinho vale (`Branson`), inicial abreviada vale (`Charlie M`),
`G.J` vale. `Sr` e `Jr` no fim são do nome, não categoria.

## O que NÃO pode virar cliente

"Lead and Follow", "Urace Daily", "Trackside Support", "Professional Coaching",
"Karting School", "Orlando Cup", "Prep", "Practice", "Date of Birth", "Age: 13".
A trava é a primeira palavra do título: se ela já abre serviço, não sobrou pessoa.

## Como o serviço acha o card

Em camadas, da mais forte para a mais fraca, e **só a primeira camada que tiver alguém**:

1. nome igual (cliente ou piloto)
2. nome quase igual (Alonso/Alonzo)
3. apelido com sobrenome igual — `Alex Savage` → Alexander Savage
4. inicial abreviada — `Charlie M` → Charlie Marron
5. uma palavra só batendo o primeiro **ou** o último nome — `Savage` → Alexander Savage,
   `Brason` → Branson (1 letra trocada)

**Duas regras que não se negociam:**

- **Ambíguo não se chuta.** `Alexander` com um Savage e um Jacoby no quadro volta para
  decisão humana. Unir no escuro é criar o mesmo problema do outro lado.
- **Nome de uma palavra só não abre card.** Serve para achar um card que existe, nunca
  para criar um — senão nasce "Charlie" ao lado de "Charlie Marron". Card novo só a
  partir de duas palavras, e o nome mais completo é processado primeiro justamente para
  ganhar o card antes do apelido procurar.

## O que a primeira varredura real achou (22/09, na VPS)

Rodar contra o quadro inteiro pagou na hora: apareceram quatro formas que nem a lista
do dono tinha, e todas viraram teste.

| Título | Estava dando | Por quê |
|---|---|---|
| `Bella M Wagner - Professional Coach` | nada | inicial **no meio** do nome era recusada |
| `Alex Savage– Old Chassis \| Adjustments` | nada | travessão colado no nome |
| `Branson KA100 01/09` | nada | data colada era lida como sobrenome |
| `MauricioPardomo_Coach` | `MauricioPardomo` | nome grudado, sem espaço |

E do outro lado: `Savege` e `Brason` não achavam ninguém porque o parecido só era
comparado com o **primeiro** nome — agora também com o último (`Savege` → Alexander
Savage, `Brason` → Branson). Mais 12 palavras soltas que apareciam como "cliente"
(`Trackhouse`, `Endurance`, `Florida`, `Closed`, `Photos`, `Goals`, `To-Do`, `AMR`,
`JFC`, `RMC`, `Mycron`, `Skapa`) entraram no vocabulário do que não é gente.

## Como rodar

```
python3 adminai/atribuir_servicos.py              # varredura, não escreve nada
python3 adminai/atribuir_servicos.py --aplicar    # move cada serviço para o card certo
```

No painel: `GET /ops/api/service-attribution` (MANAGER) varre,
`POST` (ADMIN) aplica e fica em `audit_logs`.

## Onde está no código

- `command_center/providers/identidade.py` — `pessoa_do_titulo` e os cortes
- `command_center/providers/atribuicao.py` — de quem é cada serviço, e a varredura
- `command_center/api/rotas.py` — `/service-attribution`
- `adminai/atribuir_servicos.py` — a linha de comando
- `command_center/tests/test_atribuicao.py` — 46 testes, com o gabarito do dono
