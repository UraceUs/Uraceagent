---
tipo: projeto
tipo_info: CONTEXT
status: ativo
owner: Italo Silveira
data: 2026-08-27
fonte: conversas com o dono, 27–31/08/2026
responsavel: Italo Silveira
---

# Administrative AI

[[URACE]] · [[Projetos]] · [[PARAMETROS]]

## Objetivo

Uma camada de inteligência operacional sobre as ferramentas que a URACE
já usa — [[Asana]], [[Gmail]], [[QuickBooks]], [[DocuSign]],
[[Google Calendar]] — com **tudo alimentando o segundo cérebro** no
Obsidian, em tempo real.

## Contexto

Sucede o [[Projeto Chase]], encerrado em 27/08/2026. O gargalo real não
era vender: era administrar. Construído **por partes e por aplicação**,
com **uma skill por aplicação**
([[D-2026-08-28 - Construir por partes e por aplicacao]]).

Roda no **[[VPS e OpenClaw]]**; o Claude Code é backup e ambiente de
desenvolvimento, não o destino final.

## Pessoas envolvidas

[[Italo Silveira]] (dono, decide tudo) · [[Eduardo Resende]] (logística
e compras) · [[Lara Carvalho]] · [[Luis Barros]] · [[Anabelly]]

## Ferramentas

[[Asana]] · [[Gmail]] · [[QuickBooks]] · [[Rate Card]] · [[DocuSign]] ·
[[Google Calendar]]

## Processos

[[Invoice e estimate no QuickBooks]] · [[Waiver de responsabilidade]] ·
[[Pedido de macacão]] · [[Pagamento e security deposit]] ·
[[Compra e envio]] · [[Triagem de e-mail]]

## Decisões

Todas em `08_DECISOES`. As que mais moldam o projeto:
[[D-2026-08-28 - Construir por partes e por aplicacao]] ·
[[D-2026-08-28 - PARAMETROS e o ponto unico de alteracao]] ·
[[D-2026-08-31 - Rate Card acima do catalogo do QuickBooks]] ·
[[D-2026-08-31 - IA envia a waiver]]

## Estado por aplicação

| Aplicação | Estado |
|---|---|
| [[Asana]] | mapeado e validado · escrita liberada · **falta PAT para anexo** |
| [[Gmail]] | taxonomia lida · triagem especificada · **falta `support@`** |
| [[QuickBooks]] | processo completo · pode criar, não envia |
| [[DocuSign]] | conectado e sondado · **pode enviar waiver** |
| [[Google Calendar]] | mínimo, depende do Asana |

## Pendências

**Deploy marcado para 01/09/2026** — runbook em
`adminai/deploy/README.md`, lista do que levar em [[Etapa de conexão]].

[[Etapa de conexão]] — credenciais do VPS, acesso ao `support@` e os
cliques que só o dono pode dar.

## Problemas

Ver [[Problemas]]. O que mais afeta este projeto:
[[P-09 - Conector do Asana nao sobe anexo]].

## Próximos passos

Ver [[Painel do Brain]] — é lá que fica o estado de hoje.
