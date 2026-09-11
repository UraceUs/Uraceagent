---
tipo: decisao
tipo_info: DECISION
data: 2026-09-01
fonte: Italo Silveira
responsavel: Italo Silveira
status: ativo
---

# Manter o par RSA do DocuSign demo

## O que foi decidido

O par de chaves RSA gerado em 01/09/2026 para o app
`URACE Administrative AI` **fica como está**. Não será descartado nem
regenerado agora.

## Contexto

A chave privada passou por uma janela de chat durante a instalação, em
vez de ir da tela do [[DocuSign]] direto para o [[VPS e OpenClaw]] como
o procedimento previa. Foi levantada a troca do par; o dono decidiu
seguir com o par atual.

## O que isso implica

O par nasce no ambiente **demo**, mas **acompanha a Integration Key no
go-live** — depois da aprovação, a mesma chave privada autentica em
produção. Quem tem essa chave assina envelope como `support@urace.us`
sem senha e sem login, por causa do escopo `impersonation`.

⚠️ **Ponto de reavaliação:** antes do go-live ser aprovado, vale decidir
de novo se esse par acompanha a produção ou se um novo é gerado no
momento da promoção. Gerar um par novo não invalida a Integration Key
nem o consentimento do JWT — só troca o segredo.

## Quem decidiu

Italo Silveira, 01/09/2026: *"desconsidere regenerar"*.

## Relacionado

[[DocuSign]] · [[P-12 - Integration Key do DocuSign so nasce em demo]] ·
[[Etapa de conexão]] · [[Decisoes]]
