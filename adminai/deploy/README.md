# Subir o Administrative AI no VPS — runbook

Tudo que roda no VPS está nesta pasta. O passo a passo abaixo é para ser
seguido de cima para baixo, uma vez.

> ⚠️ **Nada aqui foi testado no VPS.** Sintaxe validada, caminhos de erro
> testados localmente, mas a máquina de verdade só existe amanhã. O
> instalador foi escrito para ser **idempotente** justamente por isso:
> se algo falhar no meio, corrige e roda de novo.

---

## O que você precisa ter em mãos

Sem isto, não começa. Cada linha diz **onde tirar**.

| Sistema | O que | Onde tirar |
|---|---|---|
| **Asana** | Personal Access Token | Asana → perfil → Settings → Apps → Manage Developer Apps → Personal access tokens |
| **Google** | credencial das **duas** caixas | Workspace → Configurações → Contas → **conceder acesso da `support@` para a `urace@`** (um acesso resolve as duas) |
| **QuickBooks** | Client ID, Secret, Refresh Token | https://developer.intuit.com → seu app → Keys |
| **DocuSign** | Integration Key + chave privada RSA | https://apps.docusign.com/admin/apps-and-keys, **na conta `support@urace.us`** |
| **Anthropic** | API key | https://console.anthropic.com (dispensável se o OpenClaw já autentica por assinatura) |

O `DOCUSIGN_USER_ID`, o `DOCUSIGN_ACCOUNT_ID` e o `QBO_REALM_ID` **já
vêm preenchidos** no exemplo — foram lidos das contas em 31/08.

---

## Os 5 passos

### 1. Trazer o repositório

```bash
cd ~ && git clone <url-do-repo> Uraceagent
cd Uraceagent && git checkout claude/commandcenter-vps
```

Se já existe: `git pull`.

### 2. Rodar o instalador (a primeira vez cria o arquivo de segredos)

```bash
bash adminai/deploy/install_adminai.sh
```

Ele cria `~/.urace/adminai.env` a partir do exemplo e **para**, pedindo
que você preencha. É esperado.

### 3. Preencher as credenciais

```bash
nano ~/.urace/adminai.env
```

Deixe vazio o que ainda não tem — o instalador **pula o timer** daquele
sistema e avisa. Não trava o resto.

> 🔒 O arquivo nasce com permissão **600** e mora fora do repositório. O
> `.gitignore` bloqueia `*.env`. **Credencial nunca entra no cérebro nem
> no git.**

### 4. Rodar o instalador de novo

```bash
bash adminai/deploy/install_adminai.sh
```

Agora ele liga as skills, instala os timers e **prova o que ficou de
pé** — lista os timers ativos, roda a saúde do cérebro e mostra as
skills que o agente enxerga.

### 5. Deixar rodar um dia em simulação

`APLICAR=0` é o padrão: **nada é escrito** em Asana, Gmail, QuickBooks
ou DocuSign. Os relatórios caem em `~/.urace/logs/`.

No dia seguinte, leia os logs. Se o que a IA *teria feito* está certo:

```bash
sed -i 's/^APLICAR=0/APLICAR=1/' ~/.urace/adminai.env
bash adminai/deploy/install_adminai.sh
```

---

## O que fica rodando

| Timer | Quando | O que faz |
|---|---|---|
| `urace-triagem-email` | todo dia **07:00** | triagem da caixa — só rascunho |
| `urace-waivers` | todo dia **07:30** | varredura de waiver pendente e prazo |
| `urace-asana-sync` | seg–sex **06:40** | status ↔ quadro no Shipping Orders |
| `urace-brain-health` | segunda **06:00** | mede a forma do grafo |

Todos com `Persistent=true`: se o VPS estiver desligado na hora, rodam
assim que subir.

---

## Comandos do dia a dia

```bash
systemctl list-timers 'urace-*'          # o que está agendado
journalctl -u urace-waivers -n 50        # o que aconteceu
tail -f ~/.urace/logs/triagem-email.log  # acompanhar ao vivo
sudo systemctl start urace-waivers       # rodar agora, sem esperar
sudo systemctl disable --now urace-triagem-email.timer   # desligar um
```

Para **parar tudo** sem desinstalar:

```bash
sudo systemctl disable --now 'urace-*.timer'
```

---

## Como saber se está funcionando de verdade

`rc=0` não é prova. O que é:

```bash
# 1. os timers têm próxima execução marcada?
systemctl list-timers 'urace-*' --all

# 2. o agente enxerga as skills?
ls -l ~/.openclaw/skills/

# 3. o cérebro está íntegro?
python3 adminai/brain_health.py --strict; echo "rc=$?"

# 4. o Asana responde com o token que você pôs?
set -a; . ~/.urace/adminai.env; set +a
python3 adminai/asana_status_sync.py | head -20
```

O passo 4 roda em **simulação** e mostra o que ele mudaria. É o teste
mais honesto: se ele lista as tarefas, o token funciona.

---

## Provar o site e o processo de vendas (pacote de fotos)

Dono, 15/10 (#253): *"me de um bloco para a extensão testar todo o site e processo de vendas criando
uma conta fictícia para testar de ponta a ponta"* e *"de o comando para a extensão capturar tela a
cada passo para poder te passar e testar todas as funcionalidades"*.

**Uma linha, no VPS:**

```bash
bash adminai/deploy/command_center/testar_tudo.sh
```

O que ele faz: confere o ambiente (**para na hora** se achar chave real, ou `CC_DB_PATH` apontado
para o banco de produção), acha o Python do Command Center e o Chromium do Playwright, constrói o
frontend se faltar **ou se o código for mais novo que ele** (#275: senão a prova testaria o código novo com a tela velha), e roda a **suíte end-to-end inteira** num **banco descartável** e numa porta
livre própria (`CC_DB_PATH` temporário, `CC_AUTOSYNC=0`, `URACE_ENV=/nao/existe`, Stripe e Google
falsos locais). Depois percorre a **venda de ponta a ponta com conta fictícia** — site → kart, dia e
turno → carrinho → checkout no Stripe falso → pago → pedido, sessão em Agendamentos do site, venda
GANHO e card do piloto — fotografando **cada passo** em **390 px** e **1280 px**, e passa por
**todas as telas do painel**, com uma foto de cada.

No fim imprime, em destaque na última linha, o caminho e o tamanho de **um pacote só**:

```
>> MANDE ESTE ARQUIVO PARA O CLAUDE: /root/.urace/teste-20261015-093000.tar.gz  (31M)
```

Dentro dele: `RESUMO.md` em português (uma linha por passo: o que foi feito, o que o sistema
respondeu, qual foto, PASSOU/FALHOU; o total; e as telas com rolagem lateral ou alvo de toque
pequeno), as pastas `390/` e `1280/` com as fotos numeradas, o log inteiro e o `COMO-FOI-GERADO.md`.
Sai com código ≠ 0 se algo falhar — e **mesmo falhando entrega o pacote**, com a foto do estado do
erro, para dar para ver o que aconteceu. O banco temporário e o servidor do teste saem no fim,
inclusive se der erro (`trap`).

- **O que o pacote prova**: o site no ar, a reserva com o serviço e o preço do painel, a conta criada
  no próprio site, o carrinho (sessão + depósito + produto) num pagamento só, a volta do pagamento, e
  o registro no painel (venda, agenda e card). Mais: toda tela do painel abrindo sem erro de
  JavaScript nem de API, em celular e em computador.
- **O que ele NÃO prova**: cobrança de verdade no Stripe (chave real), e-mail de verdade saindo, e
  Asana, QuickBooks, DocuSign ou Google de verdade — tudo isso é **falso** ali, de propósito. Para o
  teste da IA com dado de verdade (em ensaio), é o `testar_ia.sh`.
- **Na primeira vez, o venv do teste** (#264): o teste **nunca** instala nada no venv da produção
  (`~/.urace/cc-venv`, o do serviço no ar — instalar ali resolveria as versões de novo e pode
  derrubar o Command Center). Ele usa um venv só dele:

  ```bash
  python3 -m venv ~/.urace/teste-venv
  ~/.urace/teste-venv/bin/python -m pip install -q -r ~/Uraceagent/command_center/requirements.txt pytest httpx playwright
  ~/.urace/teste-venv/bin/python -m playwright install chromium
  # se o Chromium reclamar de biblioteca do sistema:
  # sudo ~/.urace/teste-venv/bin/python -m playwright install-deps chromium
  ```

  Depois é sempre a linha única de cima. Para usar outro Python: `CC_TEST_PY=/caminho/do/python`
  (ou `CC_TEST_VENV=/caminho/do/venv`).
- Chromium fora do lugar padrão: `PW_CHROMIUM=/caminho/do/chrome bash adminai/deploy/command_center/testar_tudo.sh`.
- Ambiente com credencial carregada (`. ~/.urace/adminai.env`): o script diz exatamente o comando
  `env -u …` para rodar limpo. Isso é de propósito: teste nunca roda com chave real.

---

## Se der errado

| Sintoma | Causa provável |
|---|---|
| `falta ASANA_TOKEN no ambiente` | o `EnvironmentFile` não achou o env — confira o caminho no `.service` |
| timer aparece mas nunca dispara | `systemctl daemon-reload` e `systemctl enable --now <nome>.timer` |
| `openclaw: command not found` no log | o `PATH` do systemd não tem o binário; o `bash -lc` do `ExecStart` existe para isso — confirme que o login shell do usuário enxerga `openclaw` |
| agente não acha a skill | `ls ~/.openclaw/skills` — o instalador cria **link simbólico**, então o repo precisa continuar no lugar |

---

## O que este deploy **não** resolve

Coisas que continuam dependendo de você, na interface — estão em
`brain/10_PROCESSOS/Etapa de conexão.md`:

- **Acesso à caixa `support@`** (a waiver já não depende dela, mas a
  triagem sim)
- Remover o campo `Order number` do SUITS no Asana (a API dá
  `Access denied`)
- Criar as 14 regras de status ↔ quadro no Asana (não há endpoint)
- Corrigir as 4 células de preço na Rate Card

E uma limitação técnica conhecida: **o conector do Asana não sobe
arquivo**. Com o `ASANA_TOKEN` desta instalação isso passa a ser possível
via REST `POST /attachments` — é o que destrava anexar a waiver assinada
na tarefa (ver `P-09` no cérebro).
