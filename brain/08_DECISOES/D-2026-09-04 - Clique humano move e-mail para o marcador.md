# D-2026-09-04 — Clique humano no Command Center move o e-mail para o marcador

**Dono, 04/09/2026:** *"quando eu clicar no botão ali, já vai mover pra
essa caixa de marcador. Porque as tags e as caixas estão sempre
conectadas uma na outra."*

**O que muda:** um botão por thread na aba Gmail aplica o marcador
sugerido **e tira da inbox**, para qualquer marcador — não só `wNews`.

**O que NÃO muda:** a regra da IA. `gmail_rotular` (ferramenta do agente)
continua arquivando só com `wNews`. A porta humana é outra função
(`mover_humano`), que não é ferramenta do MCP: o agente não a enxerga.
Auditada (`email.move`) com quem, quando, marcador.

**Sugestão de destino:** primeiro regras explicáveis (marcador que o
filtro do Gmail já pôs; remetente/assunto da [[Taxonomia do Gmail]]);
o resto vai em lote para o agente, que responde JSON validado contra os
marcadores reais — nunca cria marcador.

Relacionado: [[Triagem de e-mail]], [[Gmail]].
