# D-2026-09-04 — Senha do Command Center com mínimo de 5 caracteres

**Decisão do dono, 04/09/2026**, durante o primeiro deploy: *"essa senha
precisa ter no mínimo somente 5 caracteres"*. O código pedia 10 e o
cadastro do primeiro ADMIN parou nisso.

**Aplicado:** `SENHA_MIN = 5` em `command_center/api/auth.py`; o
frontend e o `manage.py` seguem a mesma constante.

**O que segura a porta no lugar da senha longa:** bloqueio de 5 erros em
15 minutos por IP *e* por e-mail, sessão revogável, cookie HttpOnly.
Se um dia esse bloqueio for afrouxado, esta decisão precisa ser revista
junto — os dois não podem cair ao mesmo tempo.

**Registro da ressalva:** o painel fica na internet com nome de cliente
e situação de waiver. Foi dito ao dono; ele manteve o mínimo de 5.

Relacionado: [[VPS e OpenClaw]], [[Painel do Brain]].
