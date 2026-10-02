# App URACE nas lojas (iOS e Android) — #74

Dono, 02/10: *"preciso que realmente seja um aplicativo... nas bancas de aplicativos... versionado
tanto para iOS quanto para Android. E que cada atualização nossa atualize esses aplicativos
também... a gente sobe um aplicativo só, e que esse aplicativo... tenha tanto a área do cliente...
quanto o Command Center... clicar no ícone U."*

## Como o app funciona

- **Um app só, "URACE"** (`us.urace.app`), feito com Capacitor em volta do mesmo site.
  O projeto está em `command_center/app/`.
- **Abre na área do cliente** (`my.urace.us/ops/portal`). **5 toques seguidos no "U"** do login
  abrem o login do Command Center. Lá dentro vale o login e o papel de cada um; o toque não dá
  acesso a nada sozinho. Do login da equipe, o link "Área do cliente" volta.
- **Atualização:** as telas vêm do servidor, então **cada deploy chega ao app na hora**, sem
  passar pela loja. A loja só precisa de versão nova quando muda a parte nativa (ícone,
  permissão, plugin), e isso o workflow faz sozinho.
- **Versão:** o nome vem de `command_center/app/package.json` (`1.0.0`). O número do build é o da
  execução do GitHub Actions, que sempre sobe, como as lojas exigem.
- **Build automático** (`.github/workflows/app.yml`): a cada push no branch do VPS, o Android vai
  para a **faixa interna do Google Play** e o iOS vai para o **TestFlight**. Publicar para todo
  mundo continua sendo **um clique seu** na loja.

## O que é seu (uma vez)

Conta e assinatura são suas. **Nenhuma senha ou chave passa pelo chat:** tudo vai direto para os
*secrets* do GitHub (Settings › Secrets and variables › Actions do repositório).

### 1. Apple (iOS)

1. **Apple Developer Program** como **organização** (URACE.US INC): developer.apple.com/programs.
   Custa US$ 99 por ano e pede o número **D-U-N-S** da empresa (grátis, sai em alguns dias se a
   empresa ainda não tiver).
2. No **App Store Connect** › Apps › **+**: novo app iOS, nome "URACE", bundle ID `us.urace.app`,
   SKU `urace-app`.
3. Em **Users and Access › Integrations › App Store Connect API**, crie uma chave com acesso
   **App Manager** e baixe o arquivo `.p8`, que só pode ser baixado uma vez.
4. Crie estes secrets no GitHub:
   - `ASC_KEY_ID`: o Key ID da chave;
   - `ASC_ISSUER_ID`: o Issuer ID, que aparece na mesma tela;
   - `ASC_KEY_P8`: o conteúdo inteiro do arquivo `.p8`;
   - `APPLE_TEAM_ID`: o Team ID (Membership details).

### 2. Google (Android)

1. **Google Play Console** como organização: play.google.com/console. Custa US$ 25, uma vez só.
2. Crie o app "URACE", com o pacote `us.urace.app`.
3. **Chave de assinatura.** Crie uma vez, no seu computador. O comando pede uma senha: escolha
   uma e guarde num gerenciador de senhas.
   ```
   keytool -genkeypair -v -keystore urace.keystore -alias urace -keyalg RSA -keysize 2048 -validity 10000 && base64 -i urace.keystore | tr -d '\n' > urace.keystore.b64
   ```
   Crie estes secrets no GitHub:
   - `ANDROID_KEYSTORE_BASE64`: o conteúdo de `urace.keystore.b64`;
   - `ANDROID_KEYSTORE_PASSWORD` e `ANDROID_KEY_PASSWORD`: a senha que você escolheu;
   - `ANDROID_KEY_ALIAS`: `urace`.

   Guarde o `urace.keystore` num lugar seguro **fora do repositório**. O Play App Signing do Google
   guarda a chave final.
4. **Primeira versão à mão.** O Google exige que o primeiro `.aab` seja enviado pela tela do Play
   Console. Baixe o artefato `urace-android-N` da execução do workflow no GitHub Actions e suba
   em Testing › Internal testing.
5. **Conta de serviço para os envios automáticos:**
   - em Play Console › Setup › API access, crie a conta de serviço;
   - dê a ela a permissão "Release to testing tracks";
   - baixe o JSON e crie o secret `PLAY_SERVICE_ACCOUNT_JSON` com o conteúdo inteiro.

### 3. Ficha nas lojas

- Nome, descrição curta e longa, e e-mail de suporte (`support@urace.us`?).
- Política de privacidade: `https://urace-bridge.duckdns.org/legal/privacy.html` (já existe).
- Uma **conta de cliente de demonstração** para os revisores da Apple e do Google entrarem. É uma
  conta de teste no portal, sem dado de cliente real.
- Capturas de tela: eu tiro do app rodando quando as contas estiverem prontas.

## O que ainda falta no app (próximos PRs)

- [ ] **Excluir a conta pelo app.** A Apple exige isso para app com cadastro. Proposta: um pedido de
  exclusão na área do cliente, que desliga o login e chega para a equipe tratar. Nada é apagado
  sem a sua decisão.
- [ ] **Notificação push** (sessão confirmada, invoice, lembrete). Precisa de um projeto no
  Firebase (Android) e de uma chave APNs da Apple (iOS).
- [ ] **Entrar com Face ID / digital.**
