---
tipo: sistema
tipo_info: RULE
fonte: Italo Silveira
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Como o cérebro cresce

[[URACE]] · [[Protocolo de aprendizado]] · [[Tipos de informação]] ·
[[README|Como o cérebro funciona]]

> **A forma que o dono quer ver crescer:** muitos **hubs**, cada um com
> um punhado de **notas atômicas** em volta, e os **hubs ligados entre
> si**. Não é estética — é o que faz a IA achar o que precisa em dois
> saltos, em vez de ler o vault inteiro.

## As três formas — e por que só uma serve

| Forma | Como se parece | O problema |
|---|---|---|
| **Ilhas** | pontos soltos, sem linha | a IA nunca chega lá. Conhecimento invisível |
| **Bolo** | 5 notas gigantes com tudo dentro | achar o parágrafo certo exige ler tudo; e editar um assunto arrisca outro |
| ✅ **Constelação** | hubs + satélites + pontes | é o que temos, e é o que se mantém |

## As cinco regras

### 1. Uma nota, uma coisa
Um cliente, uma corrida, um fornecedor, um processo, **uma decisão**, um
problema. Se o título precisa de "e", provavelmente são duas notas.

Contraexemplo do que **não** fazer: uma nota "Fornecedores" com o texto
de todos dentro. O certo é [[Fornecedores]] como índice, e
[[Usman]], [[KartSport]], [[AiM]], [[Alibaba]]… cada um na sua.

### 2. Toda nota nasce com pelo menos 2 links de saída
- **um para o hub da área** ([[Clientes]], [[Fornecedores]],
  [[Processos]], [[Sistemas]], [[Problemas]], [[Decisoes]]…) — é o raio
  que prende o satélite;
- **pelo menos um lateral** para algo relacionado de **outra** área — é
  a ponte que costura as constelações.

Só o link do hub faz estrela isolada. É o lateral que dá a forma.

### 3. Nota grande é nota que virou duas
Acima de **~1.800 palavras**, quase sempre há dois assuntos juntos.
Dividir e ligar as partes. *(Diário é exceção: é cronológico.)*

Aconteceu na primeira medição: o POP do [[QuickBooks]] tinha **2.333
palavras** e era quatro coisas. Virou
[[Invoice e estimate no QuickBooks]] (o processo),
[[Conector do QuickBooks]] (a mecânica da ferramenta),
[[Estimate de pre-corrida]] e [[Cobranca de invoice vencida]].
**A costura entre elas é o que mantém a forma** — cada uma linka as
outras.

### 4. Nada de órfã, nunca
Se ninguém linka a nota, ela não existe para a IA. Ao criar, **linkar
de algum lugar** — do hub da área, no mínimo.

### 5. O hub é índice, não depósito
Hub lista e aponta. O conteúdo mora nos satélites. Um hub que engorda
está virando bolo.

## Como medir

```
python3 adminai/brain_health.py
```

Relata: densidade, hubs, links quebrados, nomes duplicados, órfãs, notas
pouco ligadas e notas grandes. **Não altera nada.** Com `--strict`,
devolve erro — serve para rodar antes de publicar.

### Onde estamos (31/08/2026)

| Medida | Valor |
|---|---|
| Notas ativas | 118 |
| Ligações | 875 |
| **Densidade** | **7,4 por nota** |
| **Hubs** (≥8 entradas) | **34** |
| Órfãs · quebrados · duplicados | **0 · 0 · 0** |

Os maiores hubs: [[QuickBooks]] · [[PARAMETROS]] · [[Asana]] ·
[[Italo Silveira]] · [[Serviços]] · [[DocuSign]] ·
[[Pagamento e security deposit]] · [[URACE]].

## O que crescer significa, na prática

Quando entra assunto novo, o instinto errado é **escrever mais dentro do
que já existe**. O certo é **criar o satélite e ligá-lo**:

| Chegou | Vira |
|---|---|
| Cliente novo | nota em `20_ENTIDADES/clientes` → [[Clientes]] + a corrida ou serviço dele |
| Decisão do dono | nota `D-AAAA-MM-DD` → [[Decisoes]] + a nota que ela muda |
| Problema achado | nota `P-NN` → [[Problemas]] + o sistema onde ele mora |
| Ferramenta nova | nota em `40_SISTEMAS` → [[Sistemas]] + o processo que a usa |
| Fato sobre algo que já existe | **edita a nota existente**, não cria outra |

A última linha é a que evita duplicata — ver [[Protocolo de aprendizado]],
passo 1: **procurar antes de criar**.
