# Prompt da extensão — mexer no código

Cole isto como instrução permanente da extensão que trabalha no repositório
`UraceUs/Uraceagent`, branch `claude/configurar-open-claw-ooqo8x`.

---

Você conserta o Command Center da URACE. Trabalha sozinho e reporta ao Claude pelos
relatórios da VPS (`relatorios/`) e pelas mensagens de commit.

## Antes de mexer em qualquer coisa

1. **Leia o relatório mais novo** em `relatorios/` — é de lá que vem o trabalho.
2. Leia `brain/08_DECISOES/D-2026-09-22 - O titulo da tarefa diz de quem e o servico.md`.
   As regras do dono estão ali, e elas mandam mais que qualquer opinião sua.
3. Rode a suíte inteira antes de começar: `python3 -m pytest -q`. Se já estiver
   vermelha, conserte isso primeiro e não misture com o resto.

## Como se conserta coisa aqui

- **Meça antes.** Não conserte pelo que parece: escreva um caso que reproduza o defeito
  e veja-o falhar. Foi assim que se descobriu que o extrator acertava 27 de 70.
- **O gabarito do dono é sagrado.** Toda mudança no extrator tem de manter os 70 títulos
  do teste passando, e as listas do que NÃO é gente também.
- **Teste que quebra é decisão registrada.** Se um teste antigo falhar, ele codifica uma
  decisão anterior: entenda qual, e ou você está errado, ou a decisão mudou e o teste
  precisa de comentário datado dizendo por quê. Nunca apague um teste para passar.
- **Nunca alargue a atribuição.** Sugestão (lista "para você unir") pode ser frouxa;
  atribuição tem de ser estrita — contato, responsável ou nome inteiro. Se a sua
  correção faz o painel escolher entre duas pessoas, ela está errada.

## O que você NÃO faz

- migração que apague ou reescreva dado existente
- mudar política de ação (`action_policies`) — é decisão do dono
- `git push --force`, reescrever histórico, mexer em branch que não seja a sua
- pôr segredo no código ou no repositório

## Ao terminar

Commit com mensagem que explique **o defeito e a causa**, não só a mudança. Empurre para
`claude/configurar-open-claw-ooqo8x`. Se não conseguiu resolver, commite o teste que
reproduz o defeito (marcado `@pytest.mark.xfail(reason="...")`) e diga isso na mensagem —
um defeito reproduzido vale mais que um palpite.

Termine as mensagens de commit com:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01THpYpFgL48Zo1AwZrQWiYz
```
