---
tipo: sistema
tipo_info: CONTEXT
fonte: sondas ao vivo + decisões do dono
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Conflitos e lacunas

[[URACE]] · [[Tipos de informação]] · [[Protocolo de aprendizado]] ·
[[Escalonamento]]

> **A lista do que a IA NÃO sabe, e do que ela sabe de dois jeitos
> diferentes.** É a nota que ela consulta antes de afirmar coisa em cima
> de assunto delicado. Registro vivo — entra e sai item.

Regra: quando duas fontes discordam, **as duas ficam registradas**. A IA
não escolhe lado. Ver [[Protocolo de aprendizado]], passo 6.

---

## ⚠️ Conflitos abertos — `needs_human_confirmation`

### C-01 · Preço do mensal Academy 4T e Baby Kart

| Fonte | Diz |
|---|---|
| **[[Rate Card]]** (planilha) | $2.756,00 mensal · $689,00 sessão extra |
| **[[QuickBooks]]** (invoice paga txnId 9391) + 3 checagens de consistência | **$2.756,90** · **$689,23** |

**Resolvido no cérebro em 31/08** por decisão do dono: vale
**$2.756,90 / $689,23**. O conflito **continua aberto na planilha** — 4
células esperando o clique dele. Enquanto isso, **a IA lê do cérebro**,
não da planilha, para esses quatro valores.
→ [[Rate Card]] · [[D-2026-08-31 - Sessao extra e mensal do Academy]]

---

## ❓ Lacunas — `UNKNOWN`

Coisas que a IA **não sabe** e que não dá para deduzir. Cada uma tem um
dono da resposta.

### U-01 · `sendReminder` do [[DocuSign]]
A IA pode cutucar quem recebeu a waiver e não assinou?
**Não decidido.** Hoje ela alerta [[Italo Silveira]], não o cliente.
→ [[Waiver de responsabilidade]]

### U-02 · Fornecedor do e-mail `whitesoldier205@gmail.com`
Recebeu um pedido "SUIT - Frankie Iadevaia". Não se sabe se é o Manzoor,
o WheelDeal ou outro. → [[PARAMETROS]] · [[Fornecedores]]

### U-03 · Devolução do security deposit
A IA executa a devolução ou só prepara? O *merchant view* do
[[QuickBooks]] é tela, não API. → [[Pagamento e security deposit]]

### U-04 · Política de desconto
Não existe regra definida na URACE. Se um pedido depender disso, **pedir
a definição** — não arbitrar. → [[Invoice e estimate no QuickBooks]]

### U-05 · Datas e duração do serviço a partir do pagamento
Como a IA descobre quando o serviço vai acontecer, a partir de uma
invoice paga? → [[QuickBooks]]

### U-06 · Papel de [[Lucas Azaro]]
Concluiu a subtarefa "Signed waiver?" do Enzo em 31/08 no [[Asana]]; o
dono pediu acesso ao [[QuickBooks]] para `lucas@urace.us` em 01/09. O
**papel formal não está registrado em lugar nenhum**. Dono da resposta:
[[Italo Silveira]]. → [[Equipe]]

---

## 🔒 Fechado — o que já foi resolvido

Fica aqui como memória: **estes assuntos não precisam ser reabertos.**

| # | Era | Resolvido em | Como ficou |
|---|---|---|---|
| F-01 | Waiver "vale por temporada"? | 31/08 | **1 ano da assinatura** — é o que o e-mail promete ao cliente |
| F-02 | Existe modelo de e-mail de invoice? | 31/08 | **Não existe porque não é preciso** — o [[QuickBooks]] envia |
| F-03 | Texto do Adult Waiver está errado | 31/08 | **Decisão: fica como está.** Não é bug esquecido |
| F-04 | Depósito é por pacote ou por cliente? | 28/08 | **Por cliente**, enquanto retido — conferir se foi devolvido |
| F-05 | Reminder de cobrança: autorização permanente? | 31/08 | **Não** — aprovação por lote |
| F-06 | Templates vazios do [[DocuSign]] | 31/08 | Não serão usados **nem apagados** → escolher template por ID |

---

## Como usar esta nota

- **Antes de afirmar** algo sobre um assunto listado aqui: ler primeiro.
- **Ao resolver** um item: mover para a tabela "Fechado", com a data e o
  como ficou. **Não apagar** — o histórico é o que impede reabrir.
- **Ao descobrir** conflito novo: registrar as duas versões com suas
  fontes, marcar as notas envolvidas `needs_human_confirmation` e
  escalar. Ver [[Escalonamento]].
