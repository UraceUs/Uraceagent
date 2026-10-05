---
tipo: decisao
tipo_info: DECISION
data: 2026-10-05
fonte: [[Administrative AI]]
responsavel: Onde ficam os documentos de cada cliente e o backup fora da VPS.
status: ativo
---

# D-2026-10-05 — Biblioteca no Command Center e backup no Drive, por cliente

issue #88, 05/10/2026

## O que foi decidido
- **Aba Biblioteca** (gerente para cima), com as abas Invoices, Recibos, Contratos, Waivers e
  Histórico de serviço. Cada documento tem o PDF.
  - Operador e mecânico continuam vendo a waiver e a invoice no card do cliente.
- **Todas as invoices** do QuickBooks, no PDF que o próprio QuickBooks imprime. A invoice que
  muda é baixada de novo.
- **Recibo** é o comprovante do pagamento recebido no QuickBooks. Quando o QuickBooks não
  entrega o PDF do pagamento, o sistema gera um comprovante com os dados dele, e o
  comprovante diz que foi gerado a partir do registro do QuickBooks.
- **Rotina diária sem IA**: timer `urace-biblioteca` às 03:40 (Flórida). Só lê QuickBooks e
  DocuSign; não gasta token.
- **Drive (urace@)**:
  - Documentos em `Command Center/Clientes/<Piloto #card>/<Invoices|Recibos|Contratos|Waivers|Histórico de serviço>`.
  - Backup do banco em `Command Center/Backup do banco`.
  - **Só "Clientes" é compartilhada com eduardo@urace.us**, como leitor. A raiz e o backup do
    banco ficam privados, como já valia desde a decisão de 23/09 (backup semanal): o backup é a base inteira.
- **Nunca no card errado.** O documento só entra num card quando o vínculo é certo. Família
  com dois pilotos no mesmo cliente do QuickBooks vai para **"Sem cliente"**, e uma pessoa
  resolve.
- **Nada é apagado.** O documento que muda substitui o arquivo no Drive, e o Drive guarda
  a versão anterior.

## Por quê
Dono, 05/10: *"todos os tipos de contrato, waivers, recibos de pagamento, invoices, históricos
de serviço — a gente precisa de um backup no nosso Google Drive"*; *"não quero que fique
gastando token… que seja programado mesmo, com rotina"*.

## Fonte
issue #88 · `command_center/providers/biblioteca.py` · `adminai/biblioteca_diaria.py`
