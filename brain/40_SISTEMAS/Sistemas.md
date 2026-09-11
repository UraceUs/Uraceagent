---
tipo: indice
tipo_info: CONTEXT
data: 2026-08-31
fonte: interno
responsavel: Italo Silveira
status: ativo
---

# 🧭 Sistemas

[[URACE]]

As ferramentas da operação — **e as armadilhas de cada uma**, que é o
que realmente evita erro.

| Sistema | Papel | A armadilha principal |
|---|---|---|
| [[Asana]] | tarefas, serviços, corridas, envios | a busca **atrasa** — conferir por leitura direta |
| [[QuickBooks]] | dinheiro | o cliente é o **responsável**, não o piloto |
| [[Conector do QuickBooks]] | a mecânica da ferramenta | `amount` é **unitário**, não total |
| [[Rate Card]] | **preço** | manda **acima** do catálogo do QuickBooks |
| [[DocuSign]] | waivers | `delivered` **não é** assinado |
| [[Gmail]] | entrada de tudo | ver [[Taxonomia do Gmail]] |
| [[Google Calendar]] | corridas | depende do Asana |
| [[VPS e OpenClaw]] | **onde a IA roda** | segredos ficam fora do repositório |


## Fontes de contexto da IA (09/09)

Em **Integrações → Planilhas e links / Arquivos** do Command Center o dono
cadastra planilhas (lidas ao vivo por `sheets_ler`), links e arquivos
(PDF, TXT, MD, CSV, DOCX, XLSX, imagem; até 25 MB). Cada item tem um
"para que serve"; tudo que está ativo entra em **todo comando da IA** com
o caminho de leitura. Arquivos ficam em `~/.urace/context/` e são copiados
para `contexto/` no workspace do agente; PDF vira `.txt` ao lado. A
[[Rate Card]] é a primeira fonte, com status próprio na aba Sistemas.
