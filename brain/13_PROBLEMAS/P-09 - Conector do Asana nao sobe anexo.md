---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: verificação do conector, 31/08/2026
responsavel: Italo Silveira
status: ativo
---

# P-09 — O conector do Asana não sobe arquivo

> **Resolvido em 02/09/2026** (conferido em 18/09): o problema era do conector pronto do
> Asana. O **servidor MCP próprio** que entrou naquele dia tem `asana_anexar_arquivo` —
> sobe o PDF da waiver assinada na tarefa, recusa em ADM URACE e em `Matt tasks`, e com
> `APLICAR=0` só simula. O passo da waiver assinada deixou de estar travado.

[[Asana]] · [[Waiver de responsabilidade]] · [[Etapa de conexão]] · [[Problemas]]

## O problema
O conector do [[Asana]] tem `get_attachments` (ler) e **nenhuma ferramenta de escrita de anexo**.

## Evidência
Verificado na lista de ferramentas do conector, 31/08/2026.

## Impacto
Trava o passo central do fluxo da waiver assinada: anexar o PDF na tarefa da criança. A marcação da subtarefa funciona; o upload não.

## O que fazer
Precisa do **Personal Access Token** do Asana + REST `POST /attachments` — já está em [[Etapa de conexão]]. Enquanto isso, a IA **marca a subtarefa e comenta com o link**, e não deixa de marcar por causa do anexo.

## Fonte
verificação do conector, 31/08/2026
