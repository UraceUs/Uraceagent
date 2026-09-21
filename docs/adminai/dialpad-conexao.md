# Dialpad no Command Center — como conectar

Situação em 18/09/2026, dita pelo dono: **o plano já tem API e Dialpad Ai**, o **aviso de
consentimento já toca** na chamada (a Flórida exige consentimento de todas as partes para
gravar), e existe **um número de empresa** que recebe todas as ligações. Então gravação e
transcrição entram desde o começo.

O que o painel faz com isso: espelha cada ligação em `calls`, casa pelo telefone com
cliente, oportunidade ou lead, escreve a ligação na linha do tempo da venda, e ligação
perdida vira item em **Precisa de atenção**. Discar é sempre gesto humano
(`dialpad_ligar` = confirmação obrigatória).

> **Segredo nunca no repositório.** Tudo vive em `~/.urace/dialpad.env` no VPS.

---

## 1. Na conta do Dialpad (uma vez)

Como **admin da empresa**, em <https://dialpad.com> → Admin Settings → Company Settings →
Authentication (ou `/developers`): crie uma **API key** com os escopos
`recordings_export` (para a URL da gravação vir no evento) e o de eventos de ligação.
Guarde a chave — ela não aparece de novo.

Pegue também o **seu `user_id`** (o da pessoa que vai usar o botão Ligar): aparece na URL
do seu perfil no admin, ou em `GET https://dialpad.com/api/v2/users/me`.

## 2. No VPS: o arquivo de segredos

```bash
install -d -m 700 ~/.urace && umask 077 && cat > ~/.urace/dialpad.env <<'EOF'
DIALPAD_API_KEY=cole_a_chave_aqui
DIALPAD_HOOK_KEY=gere_uma_chave_aleatoria
DIALPAD_HOOK_SECRET=gere_outra_chave_aleatoria
DIALPAD_USER_ID=seu_user_id_no_dialpad
EOF
chmod 600 ~/.urace/dialpad.env && echo "pronto: $(ls -l ~/.urace/dialpad.env)"
```

Para gerar as duas chaves aleatórias: `openssl rand -hex 24` (uma para cada).

- `DIALPAD_HOOK_KEY` é **nossa**: vai na URL do webhook, para ninguém de fora postar evento.
- `DIALPAD_HOOK_SECRET` é o **combinado com o Dialpad**: com ele o evento chega assinado em
  JWT (HS256) e o painel confere a assinatura antes de gravar.
- `DIALPAD_USER_<id>` (ex.: `DIALPAD_USER_3=…`) mapeia cada pessoa do painel ao usuário dela
  no Dialpad; sem isso, todos discam pelo `DIALPAD_USER_ID`.

Depois de criar o arquivo, reinicie o serviço: `sudo systemctl restart urace-command-center`.

## 3. Registrar o webhook no Dialpad

A URL sai pronta no painel, em **Integrações → Dialpad** (ou em
`GET /ops/api/dialpad/status`). É esta forma:

```
https://urace-bridge.duckdns.org/ops/api/dialpad/webhook?key=<DIALPAD_HOOK_KEY>
```

Webhook no Dialpad se cria pela API (não tem tela). No VPS, com as variáveis já no arquivo:

```bash
set -a && . ~/.urace/dialpad.env && set +a && \
WH=$(curl -sS -X POST https://dialpad.com/api/v2/webhooks \
  -H "Authorization: Bearer $DIALPAD_API_KEY" -H "Content-Type: application/json" \
  -d "{\"hook_url\":\"https://urace-bridge.duckdns.org/ops/api/dialpad/webhook?key=$DIALPAD_HOOK_KEY\",\"secret\":\"$DIALPAD_HOOK_SECRET\"}") && \
echo "$WH" && ID=$(printf '%s' "$WH" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("id",""))') && \
curl -sS -X POST https://dialpad.com/api/v2/subscriptions/call \
  -H "Authorization: Bearer $DIALPAD_API_KEY" -H "Content-Type: application/json" \
  -d "{\"webhook_id\":\"$ID\",\"enabled\":true,\"call_states\":[\"ringing\",\"connected\",\"hangup\",\"missed\",\"voicemail\",\"recording\"]}" && echo
```

Se alguma dessas duas chamadas responder **404 ou 400**, o caminho da API mudou: a
referência é [Webhook — Create](https://developers.dialpad.com/reference/webhookscreate) e
[Call Event — Create](https://developers.dialpad.com/reference/webhook_call_event_subscriptioncreate).
Cole a resposta de erro no painel (AI Command) ou aqui e eu ajusto o comando.

## 4. Provar que chegou

1. Ligue para o número da empresa e desligue.
2. No painel: **Integrações → Dialpad** mostra `último evento` com a hora.
3. No VPS, o evento como chegou fica em
   `~/.urace/dialpad-webhook-ultimo.json` — é ele que confirma o nome exato
   de cada campo.

```bash
sudo cat /root/.urace/dialpad-webhook-ultimo.json | head -40   # mesma pasta do kommo-webhook-ultimo.json
sudo journalctl -u urace-command-center -n 50 --no-pager | grep -i dialpad
```

> **Por que esse arquivo importa.** O site de desenvolvedores do Dialpad não é alcançável de
> dentro do ambiente onde o painel é escrito, então o parser (`_normaliza`, em
> `command_center/api/dialpad.py`) aceita as variações conhecidas de nome
> (`call_id`/`id`, `external_number`/`from_number`, `duration`/`duration_seconds`,
> `transcription_text`/`transcript`…) e guarda o evento inteiro em `calls.raw`. Com o
> primeiro evento real na mão, os nomes ficam exatos. **Nada se perde no meio.**

## 5. O que o painel faz com cada ligação

| Chega | O painel faz |
|---|---|
| Ligação atendida de um número conhecido | espelha em `calls`, liga ao cliente/oportunidade/lead e escreve na linha do tempo da venda quando termina |
| Ligação perdida ou caixa postal | item em **Precisa de atenção** (alto se for gente conhecida), com botão de tratar |
| Transcrição no evento | guardada em `calls.transcript` e mostrada no corpo do evento da venda |
| Botão **Ligar** no painel | `POST /ops/api/dialpad/call` faz o Dialpad tocar no aparelho de quem clicou |

## 6. O que ainda depende de decisão

- **Onde a ligação aparece**: só dentro da ficha e da oportunidade, ou também numa tela
  "Ligações" no menu. As opções estão num canvas para o dono escolher.
- **A IA lendo a transcrição** e propondo ação (marcar retorno, mover etapa, montar
  invoice): vale a pena, e entra com a política de sempre — ela propõe, a pessoa aprova.

## Endpoints do painel

| Rota | Quem | O que faz |
|---|---|---|
| `POST /ops/api/dialpad/webhook?key=` | Dialpad | evento de ligação (JSON ou JWT HS256) |
| `GET /ops/api/dialpad/status` | operador | conectado, o que falta, URL do webhook, último evento |
| `GET /ops/api/dialpad/calls?dias=14&so_perdidas=0` | operador | espelho das ligações |
| `POST /ops/api/dialpad/calls/{id}/handled` | operador | perdida já resolvida |
| `POST /ops/api/dialpad/call` | operador | discar (confirmação obrigatória) |
