---
tipo: sistema
tipo_info: PREFERENCE
fonte: Italo Silveira
data: 2026-09-01
responsavel: Italo Silveira
status: ativo
---

# Preferências do dono

[[URACE]] · [[Tipos de informação]] · [[Escalonamento]]

Como o [[Italo Silveira]] gosta de receber o trabalho. São
**preferências**, não regras: orientam o jeito, **não travam** a
execução — ver [[Tipos de informação]].

## Comando de terminal: um bloco só

**Sempre entregar os comandos em UM único bloco**, para copiar e colar de
uma vez. Nada de passo 1, rodar, passo 2, rodar.

Dito em 01/09/2026, durante o deploy no [[VPS e OpenClaw]], depois de a
instância cair no meio de uma sequência picada.

Como isso muda o que se escreve:

- **Não usar `read` dentro do bloco.** Numa colagem, as linhas seguintes
  viram a resposta do `read`. Se precisa de um valor, grave direto com
  `sed`, ou peça o valor antes e monte o bloco já com ele.
- **Não pôr verificação que devia impedir o passo seguinte.** Num bloco
  colado tudo executa em sequência: um `wc -c` antes de um `cp` não
  protege nada. Se a verificação precisa **gatilhar** a decisão, ela vira
  um `if`, ou o bloco se separa de propósito — e aí diga que é de propósito.
- **Terminar com a prova.** O último comando do bloco mostra se deu
  certo, para não precisar de uma segunda rodada só para conferir.

## Texto

Português, direto, sem enfeite. Ele corrige em uma frase; texto longo
atrapalha. E **não tirar dúvida sobre tudo** — quando perguntar, ser
conciso e certeiro. Ver [[Escalonamento]].
