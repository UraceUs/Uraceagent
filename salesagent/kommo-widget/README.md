# Chase Bridge — widget do Kommo (Salesbot ⇄ ponte)

O `widget_request` do Salesbot **exige um widget carregado na conta** (docs
oficiais: "you can use this handler only from the Widget step of Salesbot").
Este diretório é o widget mínimo: registra o bloco **"Chase — responder ao
lead"** no designer do Salesbot; ao salvar o bot, o bloco gera o
`widget_request` para a ponte com a mensagem do lead e o contexto.

Requisitos: plano **Advanced** ou superior (upload de widget custom) — a
conta URACE já é Advanced.

## Montar o zip (no VPS ou em qualquer máquina)

```bash
cd ~/Uraceagent/salesagent/kommo-widget
zip -r chase-bridge-widget.zip manifest.json script.js i18n images
```

## Subir no Kommo

1. Kommo → **Settings → Integrations → Create integration** (integração
   privada) — pode reaproveitar a integração privada existente da URACE se
   ela permitir anexar widget.
2. Na integração, seção de **widget**: enviar o `chase-bridge-widget.zip`.
3. Instalar/ativar a integração na conta.
4. (Opcional, defesa extra) Copiar o **client secret** da aba *Keys and
   scopes* e gravar no VPS em `~/.urace/kommo.env` como
   `KOMMO_BOT_SECRET=...` — a ponte passa a validar a assinatura HS512 do
   token que o Salesbot envia. Sem essa variável, a autenticação continua
   sendo só o `?key=` da URL (que já é obrigatório).

## Usar no bot

No designer do Salesbot, o bloco aparece como **"Chase — responder ao
lead"** (grupo de widgets). Único campo: a **URL da ponte**, já preenchida
por padrão — só trocar `COLE_A_AGENT_API_KEY_AQUI` pela chave real
(`grep AGENT_API_KEY ~/.urace/bridge.env` no VPS).

Fluxo completo do bot e teste ponta a ponta: `../docs/kommo-circuit-setup.md`.
