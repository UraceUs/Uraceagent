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

**Nome igual ganha de nome parecido.** `Martin` (26 serviços) é o Martin Jaramillo, não
o Bruno Martins nem o Ethan Martins.

## A regra que manda em tudo

> *"Nunca colocar serviço de outro cliente em card de outro cliente."* — dono, 22/09

Foi a resposta dele quando a varredura devolveu 20 nomes ambíguos. Sobre o `Mike`
(Fattuta? Davies?): *"crie o mike, mike fattuta e o davies separados"*. Sobre o `Sean`
(Haling? Murphy? Portnov?): *"siga a mesma lógica"*. Sobre o `G.J`, 19 serviços e sem
nome completo: *"não tenho o nome do G.J mas pode colocar como G.J"*.

Então **na dúvida não se escolhe: abre-se um card com o nome exatamente como está no
título.** A lógica é dele e está certa — um card "Mike" com um serviço é ruído que se
une num clique; o serviço do Mike Davies dentro do card do Mike Fattuta é dado errado
que ninguém vê. Isso vale para ambíguo e para nome de uma palavra só sem card.

O card novo nasce com uma nota dizendo de onde veio, e a varredura devolve a lista
**"para você unir"**, marcando com `=` quem parece ser a mesma pessoa de um card que já
existe. Unir continua sendo decisão humana — foi justamente uma união no escuro que
levou 112 serviços para o card do David Pera.

## O princípio para confirmar (dono, 22/09)

> *"O princípio para cruzar e confirmar é usar o nome do responsável e informações
> de contato."*

Foi a resposta dele às três dúvidas que sobraram depois da distribuição — e a que
explica o erro do `Alex`: o #238 Edward Donnell (piloto Alex) **é o Alex Donnell**, não
o Alex Xikis; primeiro nome igual não diz nada. Ele decidiu também: o balde `Charlie`
é o Charlie Marron; `Savage`, `Savege`, #15 e #465 são um só, e o nome certo é
**Alexander Savage**.

No código: `identidade.mesmo_contato` (e-mail, telefone ou responsável igual) é o que
CONFIRMA; `candidatos_duplicados` lista esses pares primeiro, marcados `forte`; a
lista "para você unir" marca `=` só com contato/responsável e `~` quando é só o nome.

## À noite: as três instruções finais

1. *"Pode só separar"* — card que é corrida/tarefa não é mais apagado por
   `limpar_nao_clientes`: ganha `kind='separado'`, sai da lista e de toda busca de
   identidade, e aparece no filtro **Separados** da tela de clientes.
2. *"Aplique o princípio como base de agora para frente"* — a sincronia passou a
   guardar na tarefa o que a descrição diz (`resp_name`, `resp_email`, `resp_phone`).
   A atribuição decide por **contato antes do título** (`por_contato`): o título diz
   "Alex", a descrição diz Edward Donnell, ed@… — é o Alex do Edward. Contato que bate
   em dois cards não decide (é problema de cadastro, não licença para chutar).
   `--ler-descricoes` busca no Asana só o que o título deixou em dúvida, uma vez.
3. *"Nesse caso o nome é Erik Mendoza"* — tag na frente (`[Canceled]`) sai; `Jr` no
   fim é marca de criança, não nome. `Sr` fica: é o pai.

## O cadastro também está sujo

A varredura expôs uma segunda camada do problema: boa parte dos "ambíguos" eram **cards
duplicados do próprio cadastro**, não dúvidas de verdade.

| Aparece como | Cards | O que é |
|---|---|---|
| `Charlie M`, `Charlie` (31 serviços) | #162 Charlie Marron, #296 Charlie **Marrom** | mesma criança, erro de digitação |
| `Liam Bourghol`, `Liam B` (7) | #332 Liam **Burghol**, #486 Liam **Bourgnhol** | mesma criança, dois erros |
| `Savage`, `Savege` (20) | #15 Alexander Savage, #465 Alex savage | mesma pessoa, apelido |

`parecem_a_mesma_pessoa` marca esses pares na lista — mais larga que a regra de união
de propósito, porque aqui não se une nada, só se aponta.

E há cards que são tarefa virada cliente: `Buscar as coisas no Mauricio`,
`Lucca_Professional Coach Mini ou Junior ???`, `TRAINING SESSION Javi Sanghera`,
`Aaron KA`, `Alex_Mini/Micro (driving experience 3sessões)`.

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
