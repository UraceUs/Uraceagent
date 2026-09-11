# Ambiente de teste da operação

Um Command Center com dados que imitam a operação real, sem tocar em
Asana, DocuSign, Gmail ou QuickBooks. Serve para provar a interface
inteira antes de subir para a VPS.

```bash
# 1. semear e subir (porta 8800, banco descartável)
export SC=/tmp/cc-teste && mkdir -p $SC
CC_DB_PATH=$SC/e2e.sqlite python3 command_center/tests/e2e/semear.py
CC_AUTOSYNC=0 URACE_ENV=/nao/existe CC_DB_PATH=$SC/e2e.sqlite \
  python3 -m uvicorn command_center.api.main:app --port 8800 &

# 2. provar (92 verificações, imprime OK/FALHA)
S=$SC node command_center/tests/e2e/operacao.mjs

# 3. rolagem lateral no celular, tela por tela
node command_center/tests/e2e/celular.mjs
```

Usuários semeados (senha `senha-de-teste-123`): `italo@urace.us` (admin),
`eduardo@urace.us` (gerente), `op@urace.us` (operador), `leitor@urace.us`
(leitura). As telas de teste ficam em `$SC/t01…t10.png`.

O que o cenário cobre: piloto Pro mensal com equipamento e corrida,
piloto de diária com serviço no domingo, VIP, piloto inativo com invoice
vencida, duplicado Alonso/Alonzo, waivers assinada/aberta/devolvida,
e-mails na inbox e triados pela IA, invoices paga/aberta/vencida,
corridas com convite confirmado, e uma conversa da IA com ação feita,
ação esperando aprovação e proposta incompleta.
