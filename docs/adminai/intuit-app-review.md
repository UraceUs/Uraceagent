# Destravar as chaves de produção do QuickBooks

O app da URACE está `IN DEVELOPMENT` e as chaves de produção estão atrás
de cadeado. Este documento tem **as respostas prontas** de cada campo,
para o preenchimento virar trabalho mecânico.

Contexto e por que isso importa: `brain/13_PROBLEMAS/P-11 - Producao do
app QuickBooks travada.md`. Em resumo: **o agente roda no VPS**, e sem
chave de produção ele não fala com o QuickBooks real — só com sandbox.

---

## Passo 0 — publicar as duas páginas (é o único pré-requisito real)

A Intuit exige URLs de **política de privacidade** e **EULA** que
resolvam de verdade. As duas já estão escritas:

- `adminai/deploy/legal/privacy.html`
- `adminai/deploy/legal/eula.html`

Dois caminhos para publicá-las:

**a) No site da URACE** (preferível — é o domínio da empresa)
Suba os dois arquivos e anote as URLs finais.

**b) No próprio VPS**, pelo Caddy que já está instalado:

```bash
cd ~/Uraceagent && git pull
bash adminai/deploy/legal/servir_legal.sh
```

O script termina fazendo `curl` nas duas URLs e mostrando o código HTTP.
**As duas precisam devolver 200** — a Intuit vai buscar de fato.

> ⚠️ Leia as duas páginas antes de publicar. São rascunhos escritos a
> partir do que o app realmente faz, mas quem assume o texto é a empresa.
> Confira principalmente a cláusula 5 do EULA (revisão humana da saída
> automatizada) — ela descreve a regra que já vale no cérebro: **a IA
> prepara, humano envia**.

---

## Passo 1 — App details

| Campo | Resposta |
|---|---|
| **App name** | `URACE Administrative AI` — vale renomear; hoje está "ia app", que não diz nada a um revisor |
| **Description** | Internal operations tool for URACE.US INC. Prepares invoices and estimates from the company's own service records, tracks outstanding balances, and keeps accounting data consistent with the company's project management and document signing systems. Not distributed to third parties. |
| **App category** | `Accounting` (segunda opção, se pedir: `Invoicing`) |
| **Host domain** | o domínio onde as páginas do passo 0 ficaram |
| **Launch URL** | `https://<domínio>/legal/privacy.html` — o app é headless, não tem tela pública; aponte para uma página que exista |
| **Disconnect URL** | `https://<domínio>/legal/privacy.html` |
| **Connect / Reconnect URL** | `https://<domínio>/legal/privacy.html` |
| **EULA URL** | `https://<domínio>/legal/eula.html` |
| **Privacy policy URL** | `https://<domínio>/legal/privacy.html` |
| **Where is the app hosted?** | Amazon Web Services (AWS), United States |
| **Regulated industries** | **Não.** O app não atende saúde, finanças reguladas, governo nem crédito. É uma escola e equipe de kart. |
| **Terms of service** | mesma URL do EULA, se pedir separado |

**Perfil da conta** (o Playground reclamou): endereço, estado e telefone
são os da empresa — 6149 Cyril Ave, Orlando, FL 32809 · (407) 250-2291.

---

## Passo 2 — Compliance

O questionário pergunta o que o app faz com os dados. As respostas
verdadeiras, na ordem em que costumam aparecer:

| Pergunta | Resposta |
|---|---|
| Quais escopos usa? | Apenas `com.intuit.quickbooks.accounting` |
| Acessa dados de pagamento, cartão ou conta bancária? | **Não** |
| Processa pagamentos? | **Não** |
| Armazena dados do QuickBooks? | Apenas temporariamente, para completar a tarefa, mais logs operacionais por até 90 dias |
| Compartilha dados com terceiros? | Apenas provedores de infraestrutura: AWS (hospedagem) e Anthropic (modelo de linguagem) |
| Vende ou aluga dados? | **Não** |
| Usa os dados para treinar modelos? | **Não** |
| Quantas empresas se conectam? | **Uma** — a própria URACE.US INC. Não há clientes terceiros |
| Onde ficam os tokens? | Variáveis de ambiente no servidor, permissão 600, fora de controle de versão |
| Transporte é criptografado? | Sim, HTTPS/TLS |
| Há autenticação multifator no acesso ao servidor? | Acesso por SSH com chave |
| O app é público na App Store da Intuit? | **Não** — uso interno |

Se aparecer pergunta que não estiver aqui, **não invente**: anote e
pergunte. Resposta errada em questionário de conformidade é pior que
resposta em branco.

---

## Passo 3 — pegar as credenciais

Só depois que Production destravar:

1. **Keys & credentials → Production** → `Client ID` e `Client Secret`
2. Confirmar que a lista de **Redirect URIs** inclui
   `https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl`
3. **OAuth Playground** → o app → escopo `com.intuit.quickbooks.accounting`
   → *Get authorization code* → autorizar a **URACE.US INC** →
   *Get tokens* → copiar o **Refresh Token**
4. Conferir que o **Realm ID** que aparece é `9341453113046421`.
   Se for outro, autorizou a empresa errada.

Depois, no VPS, num bloco só:

```bash
cd ~/Uraceagent
sed -i 's|^QBO_CLIENT_ID=.*|QBO_CLIENT_ID=COLE_AQUI|' ~/.urace/adminai.env
sed -i 's|^QBO_CLIENT_SECRET=.*|QBO_CLIENT_SECRET=COLE_AQUI|' ~/.urace/adminai.env
sed -i 's|^QBO_REFRESH_TOKEN=.*|QBO_REFRESH_TOKEN=COLE_AQUI|' ~/.urace/adminai.env
grep -c '^QBO_REFRESH_TOKEN=.\+' ~/.urace/adminai.env
bash adminai/deploy/install_adminai.sh
```

---

## O prazo que ninguém lembra

⚠️ **O refresh token do QuickBooks vale 100 dias e rotaciona a cada
uso.** Diferente do token do Asana, que é permanente.

Se o agente ficar mais de 100 dias sem chamar o QuickBooks, o token
morre e este fluxo tem que ser refeito. O painel vai avisar quando
estiver perto — mas vale saber antes de descobrir num sábado.
