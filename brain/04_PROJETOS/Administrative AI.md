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
| [[Asana]] | **MCP próprio no VPS**, quadro espelhado no Command Center; ADM URACE e Matt tasks só leitura |
| [[Gmail]] | **as duas caixas conectadas** (04/09); inbox por dentro no Command Center; sem envio |
| [[QuickBooks]] | **produção** (09/09, P-11 resolvido); invoice criada e enviada **depois de aprovada**; lembretes recorrentes |
| [[DocuSign]] | **produção** (04/09); envia waiver com aprovação; download, lixeira, reenvio pelo painel |
| [[Kommo]] | **chat do lead dentro do painel** (16–17/09): webhook da conta entrega a mensagem, a resposta sai pelo bot |
| [[Google Calendar]] | mínimo, depende do Asana |
| **Vendas** | área própria no painel (17/09): oportunidades, agenda de retornos e fechamento em uma tela |

## Pendências (18/09)

As quatro pendências de 17/09 foram **respondidas pelo dono em 18/09**
([[D-2026-09-18 - As travas respondidas, uma a uma]]): azul oficial `#0057B4` (já no
painel), Pit Wall **aposentado**, agente **com `APLICAR=1`** nas rotinas, e a venda de
ponta a ponta fica com **outra pessoa** (o Lucas, pelo papel comercial de U-06).

O que falta agora:

1. **URACE** — criar o usuário do Lucas (papel Operador) e rodar a venda de ponta a ponta.
2. **URACE** — reenviar as três waivers paradas (P-07); a do Hubbard pede correção do e-mail.
3. **Comigo** — a lista revisada de preços do catálogo antes de tocar nos 896 itens (P-06).
4. **Comigo** — o que o agente passa a escrever sozinho com `APLICAR=1`, antes de ligar.
5. **Comigo** — ler a Rate Card do Drive em vez de guardar cópia (decisão de C-01).

## Problemas

Ver [[Problemas]]. O que mais afeta este projeto hoje:
[[P-06 - Precos defasados no catalogo do QuickBooks]] (a invoice sai pela Rate Card, mas o
catálogo continua errado) e [[P-05 - Security deposit quase nao aparece]]. O
[[P-09 - Conector do Asana nao sobe anexo]] foi **resolvido em 02/09** pelo MCP próprio.

## Estado completo

**[[Administrative AI - Estado completo em 2026-09-17]]** — a fotografia de hoje:
o que está no ar, o que não está, como a operação funciona, as travas, os números e
todos os links. A anterior fica como histórico:
[[Administrative AI - Estado completo em 2026-09-04]].

**Manual de uso do painel**, para humanos e para IA:
`docs/manual-do-command-center.md`.

## Próximos passos

Ver [[Painel do Brain]] — é lá que fica o estado de hoje.
