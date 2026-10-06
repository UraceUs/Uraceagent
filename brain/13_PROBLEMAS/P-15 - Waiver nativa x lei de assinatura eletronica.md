---
tipo: problema
tipo_info: FACT
data: 2026-10-06
fonte: revisão do código da waiver nativa (#85) contra ESIGN, UETA da Flórida, §744.301(3) e regras de prova
responsavel: Italo Silveira
status: aberto
---

# P-15 — Waiver nativa × lei de assinatura eletrônica

[[Waiver de responsabilidade]] · [[D-2026-10-05 - Waiver assinada na area do cliente]] · issue #103 (tasks #104–#120)

URACE.US · Orlando, FL · revisão de 06/10/2026 (America/New_York) · issue #85 (fase 1)

> **Isto é uma revisão técnica de conformidade, não aconselhamento jurídico.** O que está na
> seção 6 precisa da palavra de um advogado licenciado na Flórida antes de ligar a waiver nativa.
>
> **Limite da pesquisa:** nesta sessão o proxy bloqueou a leitura direta de flsenate.gov,
> leg.state.fl.us, law.cornell.edu, justia e afins. As leis e os casos foram conferidos por busca
> (trechos das fontes listadas) e pelo texto conhecido das leis; o que não pude conferir palavra
> por palavra está marcado **[conferir]**. O texto dos dois modelos do DocuSign **não** está no
> repositório nem no servidor de desenvolvimento: não consegui lê-lo (ver lacuna F-2).

---

## 1. Resumo em 5 linhas

1. A **forma** da assinatura (caixa de concordância + nome digitado + assinatura desenhada, conta logada, IP, aparelho, hora e hash) atende ao mínimo do ESIGN e da UETA da Flórida: uma assinatura eletrônica simples assim **vale** em tribunal americano.
2. O que mais arrisca a defesa **não é a forma, é quem assina e por quem**: hoje o titular da conta assina a waiver **adulta de outro adulto** e a **parental de qualquer menor** sem declarar que é pai/mãe. Em nenhum desses dois casos a Flórida deixa o waiver valer.
3. A **atribuição** é fraca diante de um "não fui eu": o e-mail da conta nunca é verificado e ninguém pede senha ou código na hora de assinar. É o tipo de prova que caiu em *Ruiz v. Moss Bros.*
4. O **registro** não é à prova de alteração: a linha em `waivers` aceita UPDATE, o PDF não leva selo criptográfico nem carimbo de tempo, a lixeira tira a waiver do backup, e não existe um "pacote de prova" pronto para entregar no tribunal.
5. Antes de ligar, falta confirmar com o advogado: (a) se o texto parental tem o aviso do **§744.301(3)** em maiúsculas, 5 pontos maior que o resto; (b) que a tela mostra esse aviso com a mesma formatação. Hoje a tela mostra só texto extraído, sem formatação.

---

## 2. O que a lei exige

| # | Requisito | Fonte | O que significa para nós |
|---|---|---|---|
| L1 | Assinatura/contrato não perde validade só por ser eletrônico | ESIGN 15 U.S.C. §7001(a) — [uscode.house.gov](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section7001); Fla. Stat. §668.50(7) — [flsenate.gov](https://www.flsenate.gov/Laws/Statutes/2025/668.50); §668.004 ("same force and effect as a written signature") — [flsenate.gov](https://www.flsenate.gov/Laws/Statutes/2024/668.004) | A base legal existe. O que se disputa em tribunal é **quem** assinou, **o quê** e **se ainda é o mesmo documento**. |
| L2 | Definição: "electronic sound, symbol, or process, attached to or logically associated with a contract or other record and executed or adopted by a person **with the intent to sign** the record" | 15 U.S.C. §7006(5) — [govinfo](https://www.govinfo.gov/content/pkg/USCODE-2024-title15/html/USCODE-2024-title15-chap96.htm); igual em §668.50(2)(h) | É preciso provar a **intenção** (botão, caixa e texto inequívocos) e a **ligação lógica** entre a assinatura e a versão exata do documento (hash). |
| L3 | Consentimento do consumidor (§7001(c)): só é **obrigatório** quando uma lei exige que uma informação seja dada **por escrito** ao consumidor. Inclui aviso claro de: direito a papel, direito de retirar o consentimento, alcance, como atualizar o contato, como pedir cópia em papel e se há taxa, hardware e software necessários, e consentimento dado de um jeito que "reasonably demonstrates" que a pessoa consegue acessar o formato | 15 U.S.C. §7001(c)(1) — [NCLC](https://www.nclc.org/wp-content/uploads/2024/09/Quick-E-Sign-slides2.pdf), [uscode](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section7001) | A waiver em si não é uma "informação exigida por lei por escrito". Então §7001(c) **provavelmente não se aplica** [conferir com advogado]. Ainda assim, é a **boa prática** que os tribunais e o DocuSign seguem ("ERSD"), e custa pouco. |
| L4 | UETA: só vale entre partes que **concordaram em transacionar eletronicamente** (contexto e circunstâncias) | Fla. Stat. §668.50(5)(b) [conferir] | A caixa "I agree to sign electronically" cumpre isso. Tem que ficar **guardada com o texto exato** que a pessoa viu. |
| L5 | **Atribuição**: o registro é da pessoa se foi "the act of the person"; isso se prova "in any manner, including a showing of the efficacy of any security procedure" | Fla. Stat. §668.50(9)(a) — [flsenate.gov](https://www.flsenate.gov/Laws/Statutes/2025/668.50) | Quanto melhor o procedimento de segurança (e-mail verificado, senha ou código na hora, ID no balcão), mais fácil provar que foi ela. |
| L6 | **Erro**: numa transação automatizada, o indivíduo pode desfazer o efeito de um erro se o sistema **não deu chance de evitar ou corrigir** | Fla. Stat. §668.50(10) (UETA §10) [conferir o texto da FL] | Precisa de uma etapa de **revisão e confirmação** antes do clique final (ex.: assinou pelo piloto errado). |
| L7 | **Retenção e exatidão**: o registro tem que refletir com exatidão a informação, continuar acessível e poder ser reproduzido depois **por todas as partes**; se não puder, pode perder o efeito | 15 U.S.C. §7001(d), (e); Fla. Stat. §668.50(12) — [busca](https://www.flsenate.gov/Laws/Statutes/2025/668.50) | Guardar o PDF + trilha **sem alteração**, com backup, e dar ao cliente uma cópia que ele **possa guardar** (download/e-mail). |
| L8 | Cláusula exculpatória adulta: só vale se for **clara e inequívoca**. Não precisa da palavra "negligence" | *Sanislo v. Give Kids the World, Inc.*, 157 So. 3d 256 (Fla. 2015) — [White and Williams](https://whiteandwilliams.com/resources-alerts-In-Florida-Exculpatory-Clauses-Do-Not-Need-Express-Language-Referring-to-the-Exculpated-Partys-Negligence) | O texto precisa dizer, sem ambiguidade, que libera a URACE **inclusive pela culpa dela e de funcionários**. |
| L9 | Caso de **kart** na própria região: o waiver de uma pista de kart **caiu** porque o texto só cobria culpa do próprio piloto ou de outros pilotos, não a de um funcionário | *Gillette v. All Pro Sports, LLC*, 5th DCA 2014 (135 So. 3d 369 [conferir cit.]) — [FindLaw](https://caselaw.findlaw.com/court/fl-district-court-of-appeal/1655588.html), [Recreation Law](https://recreation-law.com/2016/07/03/release-fails-under-floridas-law-because-it-is-only-an-assumption-of-risk-form-not-a-release-in-a-go-kart-case/) | O advogado tem que ler o texto Adult procurando exatamente essa falha. Um release de motocross **foi** mantido em *Cain v. Banka*, 932 So. 2d 575 (Fla. 5th DCA 2006) — [FindLaw](https://caselaw.findlaw.com/court/fl-district-court-of-appeal/1004174.html). |
| L10 | **Menor**: release pré-dano assinado pelo pai para atividade comercial era **nulo** (o caso foi de motocross/ATV em pista) | *Kirton v. Fields*, 997 So. 2d 349 (Fla. 2008) — [FindLaw](https://caselaw.findlaw.com/fl-supreme-court/1195345.html) | Sem o §744.301(3), a waiver parental não vale nada. |
| L11 | **§744.301(3)**: os *natural guardians* podem renunciar, pelo filho menor, **só** aos riscos **inerentes** de uma atividade comercial. Para valer, o texto precisa trazer o aviso abaixo **em maiúsculas, pelo menos 5 pontos maior** que o resto do texto e claramente destacado. Se cumprir e não renunciar a mais do que a lei deixa, há **presunção refutável** de validade e de que o dano veio de risco inerente; para derrubar, o autor precisa de "clear and convincing evidence" | Fla. Stat. §744.301(3) (lei de 2010, resposta a *Kirton*) — [leg.state.fl.us](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0700-0799/0744/Sections/0744.301.html), [Recreation Law](https://recreation-law.com/2010/09/13/new-florida-law-allows-a-parent-to-sign-away-a-childs-right-to-sue-for-injuries/) | (a) Quem assina tem que ser **pai ou mãe** (*natural guardian*). (b) O aviso tem que estar no PDF **e** na tela com o tamanho exigido. (c) A **negligência** da URACE **não** pode ser renunciada pelo menor. Ver o texto abaixo. |
| L12 | "Inherent risk" = "those dangers or conditions, known or unknown, which are characteristic of, intrinsic to, or an integral part of the activity and which are not eliminated even if the activity provider acts with due care in a reasonably prudent manner" | §744.301(3) | Vale descrever no texto os riscos inerentes **do kart** (capotamento, colisão, falha mecânica, roupa ou cabelo preso no eixo etc.). |
| L13 | Autenticação no tribunal federal: FRE 901(a) (prova suficiente de que é o que se diz); 901(b)(4) (características distintivas); 901(b)(9) (processo ou sistema que produz resultado exato); **902(13)** (registro gerado por processo eletrônico, com **certificação** de pessoa qualificada) e **902(14)** (dado copiado e identificado por hash), com aviso prévio da 902(11); 803(6) (registro de negócio); 1001–1004 (o impresso exato de dado eletrônico é "original") | FRE — [Foley sobre 902(13)/(14)](https://www.foley.com/insights/publications/2017/12/new-federal-rules-of-evidence-90213-and-90214/) | Precisamos de: (1) uma **descrição escrita do sistema**; (2) um **custodiante** nomeado; (3) um **modelo de declaração** 902(11)/(13); (4) a verificação de **hash** do arquivo. |
| L14 | Florida Evidence Code: §90.901 (autenticação), §90.803(6) (registro de negócio), §90.902(11) (registro de negócio **certificado**, com aviso à outra parte) | [floridajustice §90.902](https://floridajustice.com/rule/90-902-self-authentication/), [§90.803(6)](https://floridajustice.com/rule/90-803-6-business-records/) | É o mesmo pacote, usado no tribunal estadual de Orange County. |
| L15 | O que os tribunais olham num "não fui eu": **como** a assinatura e a hora foram parar no documento; por que **só aquela pessoa** podia ter assinado (credencial única, e-mail com link, login seguro); data, hora e IP. Uma declaração genérica do processo **não basta** | *Ruiz v. Moss Bros. Auto Group*, 232 Cal.App.4th 836 (2014) — [NatLawReview](https://natlawreview.com/article/fact-intensive-inquiry-how-california-courts-are-resolving-authenticity-disputes); *Espejo v. So. Cal. Permanente*, 246 Cal.App.4th 1047 (2016), assinatura mantida porque o processo foi detalhado — [Ogletree](https://ogletree.com/insights-resources/blog-posts/california-appeals-court-provides-guidance-on-the-use-of-electronic-signatures-by-employees/) | Casos da Califórnia, mas a mesma regra da UETA (§9). **Não achei** precedente de tribunal de apelação da Flórida sobre atribuição de assinatura eletrônica que eu pudesse conferir. Para aceite por clique na Flórida: *Airbnb, Inc. v. Doe*, 336 So. 3d 698 (Fla. 2022) — [CPR](https://blog.cpradr.org/2022/03/31/airbnbs-clickwrap-agreement-prevails-in-floridas-top-court-sending-hidden-camera-dispute-to-an-arbitrator/). |
| L16 | Prescrição por negligência na FL: **2 anos** (antes 4) para fatos depois de 24/03/2023 | Fla. Stat. §95.11(4)(a), HB 837 — [King & Spalding](https://www.kslaw.com/news-and-insights/florida-enacts-transformative-tort-reform-legislation) | Define a **retenção mínima**. Para menor pode haver suspensão do prazo (§95.051) [conferir]: guardar **pelo menos** até o menor fazer 18 + o prazo, ou mais (seção 6). |
| L17 | Privacidade: o *Florida Digital Bill of Rights* só alcança empresa com **US$ 1 bilhão** de receita global **e** um dos três modelos de negócio (anúncios, alto-falante inteligente, loja de apps) | Fla. Stat. §501.702 — [Burr & Forman](https://www.burr.com/burr-cybersecurity-data-privacy-law-legal-partners-for-digital/article/floridas-digital-bill-of-rights-a-summary-of-key-points-for-large-online-platforms) | **Não se aplica** à URACE. Guardar IP e aparelho para prova é interesse legítimo. **Não** coletar geolocalização precisa (não acrescenta e exige permissão). |

**Aviso exigido pelo §744.301(3)** (de memória e de trechos da busca; **conferir palavra por palavra** na lei vigente [leg.state.fl.us](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&URL=0700-0799/0744/Sections/0744.301.html)):

```
NOTICE TO THE MINOR CHILD'S NATURAL GUARDIAN
READ THIS FORM COMPLETELY AND CAREFULLY. YOU ARE AGREEING TO LET YOUR MINOR CHILD ENGAGE IN A
POTENTIALLY DANGEROUS ACTIVITY. YOU ARE AGREEING THAT, EVEN IF (name of released party or parties)
USES REASONABLE CARE IN PROVIDING THIS ACTIVITY, THERE IS A CHANCE YOUR CHILD MAY BE SERIOUSLY
INJURED OR KILLED BY PARTICIPATING IN THIS ACTIVITY BECAUSE THERE ARE CERTAIN DANGERS INHERENT IN
THE ACTIVITY WHICH CANNOT BE AVOIDED OR ELIMINATED. BY SIGNING THIS FORM YOU ARE GIVING UP YOUR
CHILD'S RIGHT AND YOUR RIGHT TO RECOVER FROM (name of released party or parties) IN A LAWSUIT FOR
ANY PERSONAL INJURY, INCLUDING DEATH, TO YOUR CHILD OR ANY PROPERTY DAMAGE THAT RESULTS FROM THE
RISKS THAT ARE A NATURAL PART OF THE ACTIVITY. YOU HAVE THE RIGHT TO REFUSE TO SIGN THIS FORM, AND
(name of released party or parties) HAS THE RIGHT TO REFUSE TO LET YOUR CHILD PARTICIPATE IF YOU DO
NOT SIGN THIS FORM.
```
Forma exigida: **maiúsculas**, pelo menos **5 pontos maior** que o resto do texto e **claramente destacado**.

---

## 3. O que o sistema faz hoje (fatos, com arquivo:linha)

**Liga/desliga.** Nasce desligada (`booking_config.waiver_native = 0`, `command_center/db/__init__.py:133`). Só um ADMIN liga, e só depois de importar os dois modelos (`providers/waiver_nativa.py:65-70`; `api/site_publico.py:316-326`). A decisão D-2026-10-05 manda ouvir o advogado antes de ligar. **Não conferi** se está ligada em produção.

**Texto.** Os dois modelos (Adult `c51aede4…` e Parental `6dbf2094…`) vêm **do DocuSign, byte a byte**. Cada um é guardado com SHA-256, número de páginas e o texto extraído por `pypdf` (`waiver_nativa.py:35-38, 85-120`). Uma nova importação **sobrescreve** a linha de `waiver_templates` (`:100-101`); o PDF antigo fica no disco (nome com o hash). Se o arquivo mudar no disco, o sistema recusa assinar (`:197-198`). Se o texto é o mesmo do DocuSign: **sim, por construção** (mesmo PDF). O conteúdo em si não pude ler (lacuna F-2).

**Quem assina e como se identifica.**
- Conta da área do cliente com e-mail e senha (scrypt), limite de tentativas e CSRF (`api/portal.py:1-14, 57-70, 120-140`).
- O titular declara ter 18 anos ou mais **pela data de nascimento que ele mesmo digita** (`providers/portal.py:202-210`).
- O **e-mail nunca é verificado**: não há confirmação nem "esqueci a senha" (busca sem resultado no código).
- A sessão dura **30 dias** (`api/portal.py:33, 46-55`). Na hora de assinar não se pede senha nem código de novo.
- O tipo de waiver sai da idade do piloto (`waiver_nativa.py:124-127`): menor de 18 → parental, maior → adult.
- Quem assina é **sempre o titular da conta**, inclusive para um piloto **adulto que não é ele** ("You sign as the account holder for {piloto}", `web/src/portal/Waiver.tsx:96-98`). O servidor não confere `is_self` (`waiver_nativa.py:183-192`).
- Na parental, a tela diz "You sign as the parent or legal guardian" (`Waiver.tsx:97`), mas **não pede** que a pessoa declare o parentesco, e o parentesco não é guardado.

**Consentimento.** Duas caixas obrigatórias (`Waiver.tsx:107-110`; servidor `waiver_nativa.py:181-182`):
1. "I have read this waiver, I understand it gives up legal rights, and I agree to it [on behalf of X]."
2. "I agree to sign electronically. My electronic signature is legally binding, the same as a handwritten one."

O que fica guardado é **só `true/true`**, não o texto que a pessoa viu (`:208`). **Não há** aviso ESIGN (papel, como retirar, hardware/software, como pedir cópia). No cadastro há um `accept_terms` com data, mas sem versão do texto (`portal.py:203, 218`).

**Intenção e cerimônia.** A pessoa lê o texto extraído numa caixa com rolagem, ou abre o PDF original num link (`Waiver.tsx:100-104`). Marca as duas caixas, digita o nome completo (pelo menos 2 palavras, `waiver_nativa.py:170-174`), desenha a assinatura (PNG, com mínimo de tinta, `:154-167`) e clica "Sign the waiver" (`Waiver.tsx:114`). **Não** é preciso rolar até o fim. **Não** há tela de revisão e confirmação. O nome digitado **não** é comparado com o nome da conta.

**O que é guardado** (`waiver_nativa.py:203-227`), no JSON `waivers.audit`:
- id da assinatura (uuid), modelo, nome e SHA-256 do modelo, páginas;
- conta (id, e-mail, nome), nome digitado, piloto (id, nome, nascimento);
- hora em UTC e na Flórida; IP (o primeiro `X-Forwarded-For`, `api/auth.py:214-216`); user-agent (300 caracteres);
- as duas caixas; o método de autenticação (texto fixo); SHA-256 do PNG; validade; SHA-256 do PDF final.

Também ficam `pdf_path` e `doc_sha256` na linha, e um evento `portal.waiver.sign` (com o sha256) no `audit_logs`, que é **append-only por trigger** (`api/portal.py:376-377`; `db/schema.sql:581-584`). **Não** se guarda geolocalização, nem eventos intermediários (abriu, leu, abriu o PDF), nem o IP e a hora do login daquela sessão.

**PDF final** (`waiver_nativa.py:251-313`): o PDF do modelo **intacto**, mais uma página "Electronic signature and certificate of completion" com o signatário, o menor e a data de nascimento, uma frase de concordância, a imagem da assinatura, o nome digitado, a hora (Flórida e UTC), a validade, a autenticação, o IP, o aparelho e os hashes do modelo e da imagem. **Não** tem assinatura digital (PAdES/certificado) nem carimbo de tempo (RFC 3161). Os campos de assinatura que existirem **dentro** do corpo do modelo continuam em branco (não verificado: depende do PDF).

**Integridade.** `doc_sha256` fica na mesma linha, que aceita UPDATE: a tabela `waivers` não tem trigger, e o painel faz UPDATE de `hidden`, `status`, `signer_email` e `client_id` (`api/rotas.py:946, 958, 990, 1008`). Uma cópia do hash fica no `audit_logs` imutável. O arquivo fica em `~/.urace/waivers/urace-<uuid>.pdf` com permissão 0600 (`waiver_nativa.py:213-216`).

**Entrega ao cliente.** Só o botão "Download the signed PDF" logo depois de assinar, ou enquanto a waiver estiver válida (`Waiver.tsx:77-89`; rota `api/portal.py:382-391`, só da própria conta). **Nenhum e-mail com cópia.** Depois que vence, a tela não lista a waiver antiga (`situacao` só mostra a vigente, `waiver_nativa.py:130-150`).

**Retenção e backup.** A rotina diária da Biblioteca sobe para o Google Drive as waivers `completed` **e não ocultas** (`providers/biblioteca.py:197-198`). A **lixeira** do painel (OPERATOR) aceita waiver nativa assinada: põe `hidden=1`, que a tira de "vigente" e do backup. A mensagem de retorno diz "Assinada fica no DocuSign (registro legal)", o que **é falso** para `source='urace'` (`api/rotas.py:930-950`). Não há política escrita de retenção.

**Validade e nova assinatura.** Vale 365 dias a partir da data na Flórida (`waiver_nativa.py:41, 199-201`). Não deixa assinar de novo enquanto valer (`:191-192`). Depois que vence, pode assinar de novo. Uma waiver **parental continua valendo depois que o piloto faz 18 anos**, até completar o ano.

**Prova para o tribunal.** A equipe baixa o PDF pelo card, e isso fica auditado (`api/rotas.py:887-903`). **Não** há exportação de um pacote de prova (PDF + JSON + `audit_logs` + verificação de hash), descrição do sistema, custodiante nem modelo de declaração.

**Testes.** `tests/test_waiver_nativa.py` cobre: nasce desligada, importação só pelo ADMIN, parental e adult, recusa sem as caixas ou sem assinatura, outra conta, download da própria, modelo alterado e lista paginada. `tests/test_assinatura.py` **não** é sobre a waiver: trata da marca "by Urace Ai agent" no Asana e no Kommo.

---

## 4. Lacunas

### A. Identidade e atribuição

**A-1 · crítica · Um adulto assina a waiver de outro adulto.** `Waiver.tsx:98` e `assinar()` deixam o titular assinar a "Adult Release" de um piloto adulto que não é ele (`is_self=0`).
- **Por que importa:** um adulto só abre mão dos próprios direitos. Fora de procuração, um terceiro não renuncia por ele. O release seria do titular, não do piloto, e não teria efeito (L8; *Sanislo* exige que **a parte** tenha consentido claramente).
- **Correção:** a waiver adult só pode ser assinada pelo **próprio piloto**. Para um piloto adulto que não é o titular: mandar um convite para o e-mail do piloto, com link de uso único e código, e o piloto assina numa tela própria (sem conta, ou com conta própria). Até isso existir, **bloquear** a assinatura adult quando `is_self=0` ("This driver is an adult and must sign their own waiver.").

**A-2 · alta · E-mail não verificado.**
- **Por que importa:** §668.50(9) aceita como prova "the efficacy of any security procedure". *Ruiz* derrubou uma assinatura porque a empresa não mostrou por que só aquela pessoa podia ter assinado. *Espejo* manteve outra porque houve e-mail com link e credencial única (L15).
- **Correção:** verificar o e-mail no cadastro (link ou código de 6 dígitos, válido por 15 minutos) e só liberar a assinatura com e-mail verificado. Guardar `email_verified_at` e incluir na trilha.

**A-3 · alta · Ninguém se autentica de novo na hora de assinar** (sessão de 30 dias; computador da família).
- **Por que importa:** é o mesmo argumento de *Ruiz* ("qualquer um no computador logado").
- **Correção:** antes de gravar, pedir um **código enviado ao e-mail** (opcional também por SMS) ou a senha. Guardar na trilha o método, a hora do código, o hash do id da sessão e o IP e a hora do login.

**A-4 · média · Nenhuma ligação com a pessoa física no balcão.**
- **Correção:** quando o piloto chega (o QR do balcão já existe, #87), a equipe confere um documento com foto do signatário e registra "ID verified in person by <staff> at <hora>" na waiver (append-only). Em tribunal, esse é o fato mais forte de atribuição.

**A-5 · baixa · Nome digitado ≠ nome da conta passa sem aviso.**
- **Correção:** comparar sem acento e sem diferença de maiúsculas. Se for diferente, pedir confirmação ("The name you typed is different from the account holder name") e guardar as duas versões.

**A-6 · baixa · O IP vem do primeiro `X-Forwarded-For`** (`auth.py:214-216`).
- **Por que importa:** se o proxy repassar um cabeçalho vindo do cliente, o IP pode ser forjado.
- **Correção:** confirmar no VPS que o Caddy substitui o XFF (é o padrão do Caddy 2 sem `trusted_proxies`) e documentar isso na descrição do sistema (G-2).

### B. Consentimento e aviso

**B-1 · média · Sem aviso de consentimento eletrônico (ERSD).**
- **Por que importa:** §7001(c) provavelmente não é obrigatório aqui (L3), mas é o padrão que um juiz espera ver e reforça a "intenção" e o acordo de transacionar eletronicamente (§668.50(5)).
- **Correção:** uma página curta "Consumer Disclosure and Consent to Electronic Records and Signatures", com: alcance (esta waiver e as renovações); direito a assinar em papel no balcão, sem custo; como retirar o consentimento (e-mail ou balcão) e o efeito (passa a assinar em papel); como pedir cópia em papel, sem custo; como atualizar o e-mail; requisitos (navegador atual, leitor de PDF, e-mail). A caixa de consentimento passa a apontar para ela, e abrir o PDF de exemplo serve de "demonstração" de acesso.

**B-2 · média · O texto das caixas e do botão não fica guardado.** Hoje só `true` (`waiver_nativa.py:208`) e o texto mora no frontend (`Waiver.tsx:107-110`).
- **Correção:** o backend passa a servir os textos com versão (`consent_texts`: id, versão, texto, sha256). A trilha guarda id, versão e hash de cada texto aceito, e a página de certificado imprime o texto exato.

**B-3 · baixa · O aceite dos termos no cadastro não tem versão** (`portal.py:203, 218`).
- **Correção:** guardar a versão e o hash dos termos aceitos.

### C. Intenção e cerimônia de assinatura

**C-1 · alta · A tela mostra o texto sem formatação.** `portal-waiver-texto` exibe o texto extraído do PDF. O aviso do §744.301(3) perde o tamanho e o destaque, e o próprio PDF só abre por um link opcional.
- **Por que importa:** a forma do aviso é **condição de validade** (L11). Quem assina na tela precisa ver o aviso como a lei pede.
- **Correção:** mostrar o **PDF de verdade** dentro da página (pdf.js, carregado só nessa rota). Se for HTML, renderizar o aviso em maiúsculas e pelo menos 5 pt maior. Só liberar as caixas depois de rolar até o fim ou de abrir todas as páginas, e guardar `viewed_all_pages_at`.

**C-2 · média · Não há etapa de revisão e confirmação** (§668.50(10), L6).
- **Correção:** depois de "Sign", mostrar um resumo (documento, piloto, quem assina, parentesco, a imagem da assinatura) com "Confirm and sign" ou "Go back". Guardar a hora das duas etapas.

**C-3 · média · Faltam os eventos intermediários.** O certificado do DocuSign traz enviado, visto e assinado; o nosso só traz assinado.
- **Correção:** criar uma tabela `waiver_events` append-only (trigger igual à do `audit_logs`) com: abriu a tela, abriu o PDF, rolou até o fim, marcou as caixas, pediu o código, código ok, assinou. Cada evento com hora, IP e user-agent, e todos impressos no certificado.

**C-4 · baixa · Texto do botão.** "Sign the waiver" é aceitável.
- **Correção:** trocar por "I agree — sign the waiver" ou "Adopt and sign" e mostrar, ao lado do botão, a frase de efeito legal (hoje ela só aparece no PDF, `waiver_nativa.py:280`).

### D. Integridade e prova de não alteração

**D-1 · alta · O registro assinado aceita alteração.** A tabela `waivers` aceita UPDATE em tudo, inclusive `audit`, `doc_sha256` e `pdf_path`, e o arquivo é comum no disco.
- **Por que importa:** §7001(d)/(e) e §668.50(12) exigem que o registro "accurately reflects" a informação. Para a FRE 902(13)/(14), o custodiante tem que certificar o processo e o hash (L7, L13).
- **Correção:**
  1. Trigger SQLite que recusa UPDATE de `audit`, `doc_sha256`, `pdf_path`, `completed_at`, `expires_at`, `signer_*`, `template` e `pilot_id` quando `source='urace'`. Ficam livres só `hidden` e `client_id`, que são do painel.
  2. Gravar uma cópia do JSON da trilha também no `audit_logs` (já imutável).
  3. Encadear os hashes (cada assinatura guarda o hash da anterior).

**D-2 · alta · O PDF não tem selo criptográfico nem carimbo de tempo confiável.**
- **Por que importa:** hoje a prova de que o PDF não mudou é só "o hash está no nosso banco". Um PDF selado (PAdES) com o certificado da URACE e um carimbo RFC 3161 de uma TSA externa prova a integridade e a hora sem depender do nosso servidor. É o que o DocuSign faz ("tamper-evident seal").
- **Correção:** depois de montar o PDF, aplicar uma assinatura PAdES-B-T com `pyHanko`: certificado de selo da URACE (chave fora do repositório, em `~/.urace/`) e TSA RFC 3161 (há gratuitas e pagas). Guardar o token de tempo, e verificar com `pyhanko sign validate` num teste.

**D-3 · média · A lixeira tira a waiver nativa do backup, com uma mensagem falsa** (`rotas.py:930-950`; `biblioteca.py:198`).
- **Correção:** a waiver nativa assinada **não** vai para a lixeira. Se for o caso, "anular" com motivo, o que gera um evento append-only, e o arquivo continua no backup. Corrigir a mensagem para `source='urace'`.

**D-4 · média · O histórico de versões do modelo se perde.** A reimportação sobrescreve `waiver_templates` (`waiver_nativa.py:100-101`).
- **Correção:** tabela `waiver_template_versions` (kind, sha256, caminho, texto, importado_em, por) que nunca é apagada. A assinatura aponta para a versão pelo hash. O PDF assinado já contém o modelo, mas o histórico mostra **o que estava em vigor** em cada data.

### E. Entrega e retenção

**E-1 · média · Nenhuma cópia por e-mail.**
- **Por que importa:** §7001(e) diz "capable of being retained and accurately reproduced… by all involved parties". O download cumpre em parte. O e-mail dá prova de **entrega** e uma cópia fora do nosso controle (em tribunal, "ele recebeu e não reclamou").
- **Correção:** depois de assinar, mandar e-mail ao signatário com o PDF anexado (ou link autenticado), da conta `support@`. Guardar o message-id e a hora de envio na trilha e em `waiver_events`.

**E-2 · média · O cliente não acha as waivers vencidas.**
- **Correção:** a área do cliente lista **todas** as waivers da conta (vigentes e vencidas) com download.

**E-3 · média · Não há política de retenção nem cópia fora do VPS garantida para todas.**
- **Correção:** escrever a política (seção 6 define o prazo; sugestão para o advogado: nunca apagar waiver de menor antes de 18 anos de idade + 5 anos; de adulto, vencimento + 5 anos). O backup diário passa a incluir as ocultas e as anuladas. Sugestão: um bucket com *object lock* (WORM) ou pelo menos as versões do Drive.

### F. Menores e texto da waiver (Flórida §744.301(3))

**F-1 · crítica · Ninguém declara ser pai ou mãe.**
- **Por que importa:** o §744.301(3) autoriza só o ***natural guardian*** (L11). Avô, tia, técnico ou padrasto **não** podem. Um tutor nomeado por juiz é outra situação [conferir com o advogado]. Sem essa declaração, a waiver parental assinada por quem não é pai ou mãe é nula (*Kirton*).
- **Correção:**
  1. Campo obrigatório "Your relationship to {minor}": Mother / Father / Court-appointed legal guardian / Other. Se "Other", **bloquear** com a mensagem "a parent must sign".
  2. Caixa "I am the parent (natural guardian) or legal guardian of {minor} and have authority to sign for them".
  3. Guardar na trilha e imprimir no certificado.
  4. Para tutor nomeado por juiz, pedir upload da ordem judicial ou fazer no balcão.

**F-2 · crítica (verificação) · Não sei se o texto parental tem o aviso do §744.301(3) no formato exigido.** O PDF do DocuSign não está no repositório nem no servidor de desenvolvimento.
- **Correção:** o advogado lê o PDF importado e confere: (a) o aviso **palavra por palavra**, com "URACE.US INC" (e afiliadas) no lugar de "(name of released party)"; (b) maiúsculas e +5 pt; (c) que a parte que renuncia pelo menor fica **limitada a riscos inerentes**, ou que o texto separa com clareza a renúncia do pai (que pode ser mais ampla) da do menor; (d) a lista de riscos inerentes do kart. Criar um teste automático que falha se o texto do modelo parental não contém o aviso.

**F-3 · alta · A waiver parental continua valendo depois que o piloto faz 18 anos.**
- **Por que importa:** quando o menor vira adulto, a participação dele já não é coberta pela renúncia do pai. Ele precisa assinar a própria (L8/L11).
- **Correção:** `expires_at` da parental = o **menor** entre 365 dias e a véspera do 18º aniversário. `vigente()` também confere a idade na data. Avisar 30 dias antes: "{driver} turns 18 on … and must sign the adult waiver".

**F-4 · média · A idade vem de uma data de nascimento declarada e editável.**
- **Correção:** guardar a data de nascimento do momento da assinatura (já se guarda) e proibir alterar essa data enquanto houver waiver vigente sem um novo fluxo. No balcão, conferir a idade do menor (certidão ou passaporte) junto com A-4.

**F-5 · média · O texto Adult precisa cobrir a culpa de funcionários** (*Gillette*, kart, 5th DCA; L9).
- **Correção:** revisão do advogado (seção 6). Nenhuma mudança de código. Lembrete: a decisão D-2026-08-31 manteve o **texto do e-mail** do DocuSign como está, não o texto da waiver.

**F-6 · baixa · Campos em branco no corpo do modelo.** Se o PDF do DocuSign tem linhas "Signature / Date / Participant name" no corpo, elas ficam vazias e a assinatura vai só na página anexa.
- **Correção:** o advogado confirma que a página anexa basta. Se não bastar, preencher esses campos por coordenadas (`pypdf`/`reportlab`) e guardar o mapa das coordenadas por versão do modelo.

### G. Pacote de prova para o tribunal

**G-1 · alta · Não há exportação de um "evidence package".**
- **Correção:** um botão na waiver (MANAGER+) que gera um ZIP com: o PDF assinado; `audit.json`; os `waiver_events`; as linhas do `audit_logs` daquela waiver e daquela conta (cadastro, login, assinatura); a verificação do hash (`sha256sum`); o token de tempo RFC 3161; a versão do modelo; e o **certificado de conclusão** em PDF (já existe como página, mas aqui sai sozinho e com os eventos). Cada exportação gera um evento `waiver.evidence_export`.

**G-2 · alta · Não há descrição escrita do sistema nem custodiante.** Faltam a descrição do processo de assinatura (as telas, a autenticação, como a hora é tirada e de qual relógio, como o hash é calculado, onde fica e quem acessa) e um **custodiante** nomeado.
- **Por que importa:** *Ruiz* exige uma explicação **específica** de como a assinatura foi parar no documento. A FRE 902(11)/(13) e a Fla. §90.902(11) exigem a certificação de "a qualified person" (L13–L15).
- **Correção:** um documento versionado no repositório ("Waiver e-signature system description") e um **modelo de declaração** (FRE 902(11)/(13) e §90.902(11)) que o pacote preenche com os dados da waiver, para o advogado revisar.

**G-3 · baixa · O relógio do servidor não está documentado.**
- **Correção:** confirmar o NTP (`timedatectl`) no VPS e registrar na descrição. O carimbo RFC 3161 (D-2) resolve a prova da hora.

### H. Internacional (secundário: o foro é a Flórida)

| Jurisdição | O que nossa assinatura simples ganha | Cuidado extra |
|---|---|---|
| **UE — eIDAS** (Reg. 910/2014, alterado pelo 2024/1183) | Art. 25(1): não pode ser recusada como prova **só** por ser eletrônica ou não qualificada. É uma **SES** (simples). A AES (Art. 26) exige vínculo único e controle exclusivo do signatário; a QES equivale à manuscrita (Art. 25(2)) — [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2014/910/oj), [firmaelectronica.gob.es](https://firmaelectronica.gob.es/en/empresas/cosas-deberias-saber/base-legal) | O selo PAdES com carimbo de tempo (D-2) aproxima a prova de integridade da AES. Não vale a pena buscar QES. Na UE, cláusula que exclui responsabilidade por morte ou lesão de consumidor tende a ser abusiva (Diretiva 93/13) [conferir]. |
| **Reino Unido** — ECA 2000 s.7; Law Commission 2019 | A assinatura eletrônica serve para executar um documento se houver **intenção de autenticar** — [HSF](https://www.hsfkramer.com/notes/corporate/2019-09/law-commission-report-on-electronic-signatures) | A **forma** vale, mas a **substância** não: o *Consumer Rights Act 2015* s.65 proíbe excluir responsabilidade por morte ou lesão causada por negligência — [legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2015/15/section/65). Se o caso fosse julgado lá, a waiver não protegeria contra negligência. |
| **Canadá** — PIPEDA Parte 2 (federal) e as *Electronic Commerce Acts* provinciais | A assinatura eletrônica é aceita em geral — [PIPEDA](https://laws-lois.justice.gc.ca/eng/acts/P-8.6/) | No **Quebec**, o Código Civil (art. 1474) não deixa excluir responsabilidade por dano corporal [conferir]. Nas províncias de *common law*, waivers claros costumam valer. |
| **Brasil** — MP 2.200-2/2001 art. 10 §2º; Lei 14.063/2020 | Uma assinatura fora da ICP-Brasil vale se for "admitida pelas partes como válida ou aceita pela pessoa a quem for oposto o documento". A Lei 14.063 classifica simples / avançada / qualificada (para atos com o poder público) — [Planalto MP](https://www.planalto.gov.br/ccivil_03/mpv/antigas_2001/2200-2.htm), [Dizer o Direito](https://www.dizerodireito.com.br/2020/09/lei-140632020-dispoe-sobre-as.html) | **Maior risco internacional:** o CDC art. 51, I torna **nula** a cláusula que exonera o fornecedor de responsabilidade — [Planalto CDC](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm). O art. 101, I deixa o consumidor processar no domicílio dele. Se um cliente brasileiro processar **no Brasil**, a waiver tende a não valer como exoneração, e a cláusula de foro e lei da Flórida pode ser afastada [conferir com advogado no Brasil]. Na Flórida, o caso segue a lei da Flórida. |
| **UNCITRAL** — Model Law on Electronic Signatures (2001) | Art. 6: assinatura "as reliable as appropriate" para o fim. É a base de muitas leis nacionais — [UNCITRAL](https://uncitral.un.org/en/texts/ecommerce/modellaw/electronic_signatures) | Nada extra além do que já foi dito. |

**H-1 · média · Cliente estrangeiro.**
- **Correção** (decidir com o advogado):
  1. Cláusula de **lei aplicável e foro** (Florida law; Orange County, FL) em destaque.
  2. Caixa "I read and understand English, or I had this document translated before signing", guardada na trilha.
  3. Opcional: uma tradução para o português **só de cortesia**, com "the English version controls" e o hash das duas.
  4. Guardar o **país do IP** no momento da assinatura (derivado do IP, sem geolocalização precisa) para saber depois quem assinou de fora.

---

## 5. Tasks em ordem (cada uma = 1 issue + 1 PR)

Ordem pelo risco jurídico. **Até T1–T5 entrarem e o advogado responder a seção 6, a waiver nativa continua desligada.**

**T1 — Bloquear a waiver adult assinada por outra pessoa** (A-1)
O servidor recusa `template='adult'` quando `piloto.is_self=0`. A tela explica que o piloto adulto assina a própria waiver. Teste que falha sem a mudança.
*Feito quando:* um POST de uma conta para um piloto adulto não-self volta 400 com a mensagem certa; o titular adulto que é piloto continua assinando; teste, lint e build verdes.

**T2 — Parentesco obrigatório na parental** (F-1)
Campo "relationship" (Mother / Father / Court-appointed legal guardian / Other → bloqueia) e a caixa de declaração de autoridade. Os dois vão para a trilha e para o certificado. Tutor nomeado por juiz só no balcão por enquanto.
*Feito quando:* a parental sem parentesco válido volta 400; a trilha e a página do certificado mostram o parentesco e o texto aceito; e2e da tela verde.

**T3 — A parental vence no 18º aniversário** (F-3)
`expires_at = min(+365, véspera dos 18)`, e `vigente()` confere a idade na data. Aviso na área do cliente 30 dias antes.
*Feito quando:* um teste com piloto de 17 anos e 9 meses dá validade até a véspera dos 18; no dia dos 18, `situacao` pede a adult.

**T4 — Mostrar o PDF de verdade e exigir a leitura** (C-1)
Visualizador pdf.js (com `React.lazy`) no lugar do texto extraído. As caixas só se liberam depois de passar por todas as páginas. Guardar `viewed_all_pages_at`.
*Feito quando:* em 360 px o PDF aparece legível e sem rolagem lateral; o aviso aparece com a formatação do PDF; a trilha tem a hora da leitura; o bundle inicial não cresce (o pdf.js vem só nessa rota).

**T5 — Verificar o e-mail e pedir código na hora de assinar** (A-2, A-3)
Verificação de e-mail no cadastro (código de 6 dígitos, 15 minutos, limite de tentativas). Na assinatura, código novo por e-mail. Trilha com `email_verified_at`, `otp_sent_at`, `otp_verified_at`, o hash da sessão e o IP e a hora do login.
*Feito quando:* uma conta sem e-mail verificado não assina; um código errado ou vencido não assina; o certificado mostra "Email verified · one-time code to <e-mail> verified at …".

**T6 — Registro assinado imutável** (D-1, D-3)
Trigger que bloqueia UPDATE dos campos de prova em `waivers` com `source='urace'`. A trilha também vai para o `audit_logs`. A lixeira recusa waiver nativa assinada (vira "anular com motivo", sem sair do backup). Corrigir a mensagem.
*Feito quando:* um teste mostra que o UPDATE de `doc_sha256` e `audit` levanta erro; a lixeira de uma nativa volta 409; a Biblioteca inclui as anuladas.

**T7 — Selo PAdES + carimbo de tempo RFC 3161** (D-2, G-3)
`pyHanko` assina o PDF final com o certificado de selo da URACE (chave em `~/.urace/`, nunca no repositório) e o carimbo de uma TSA. O token fica guardado.
*Feito quando:* `pyhanko sign validate` aceita o PDF num teste (com TSA falsa local); alterar 1 byte invalida; sem chave configurada, a assinatura **não** acontece.

**T8 — Trilha de eventos append-only** (C-3)
Tabela `waiver_events` com trigger anti-UPDATE/DELETE. Registra: abriu, abriu o PDF, leu tudo, pediu o código, código ok, revisou, assinou, e-mail enviado. Tudo vai para o certificado.
*Feito quando:* uma assinatura completa gera a sequência inteira; o certificado lista os eventos com hora na Flórida e em UTC.

**T9 — Revisão e confirmação antes do clique final** (C-2, C-4, A-5)
Passo 2 com o resumo, "Confirm and sign" e "Go back". Aviso quando o nome digitado difere do nome da conta. Botão com a frase de efeito legal.
*Feito quando:* não há como assinar sem passar pela revisão; a trilha tem as duas horas; e2e verde em 360/390 px.

**T10 — Textos de consentimento versionados + ERSD** (B-1, B-2, B-3)
O backend serve o "Consumer Disclosure" e os textos das caixas com versão e hash. A trilha guarda as versões, e o certificado imprime o texto. Os termos do cadastro também ganham versão.
*Feito quando:* trocar um texto cria uma versão nova sem alterar as assinaturas antigas; o certificado mostra o texto exato aceito.

**T11 — Cópia por e-mail + histórico na área do cliente** (E-1, E-2)
E-mail com o PDF ao signatário depois de assinar (message-id na trilha). A área do cliente lista todas as waivers, inclusive as vencidas.
*Feito quando:* o teste com Gmail falso confirma o envio e o message-id; a lista mostra as vencidas com download só da própria conta.

**T12 — Pacote de prova + descrição do sistema + modelo de declaração** (G-1, G-2)
Botão "Evidence package (ZIP)" para MANAGER+; `docs/waiver-esign-system.md` versionado; modelo de declaração FRE 902(11)/(13) e Fla. §90.902(11) preenchido com os dados da waiver.
*Feito quando:* o ZIP contém tudo da G-1 e o `sha256sum` confere; a exportação fica auditada; o advogado recebe o modelo para revisar.

**T13 — Histórico de versões do modelo + teste do aviso §744.301** (D-4, F-2)
Tabela de versões que nunca se apaga. Um teste falha se o texto parental importado não contém o aviso do §744.301(3) (texto que o advogado aprovar).
*Feito quando:* reimportar mantém a versão anterior consultável; o teste do aviso roda no CI com um modelo de exemplo.

**T14 — Conferência no balcão** (A-4, F-4)
No check-in pelo QR, a equipe marca "ID checked" (tipo de documento, sem guardar a imagem) para o signatário e, se for menor, a idade. Vira um evento append-only. A data de nascimento fica travada enquanto houver waiver vigente.
*Feito quando:* o evento aparece no certificado e no pacote; editar a data de nascimento com waiver vigente volta 409.

**T15 — Política de retenção e backup imutável** (E-3)
Documento com o prazo aprovado pelo advogado. O backup inclui as ocultas e as anuladas, com destino imutável ou versionado.
*Feito quando:* a política está no `brain/`; o backup diário cobre 100% das `source='urace'`; uma restauração de teste confere os hashes.

**T16 — Internacional** (H-1)
Caixa "I read and understand English…", cláusula de lei e foro destacada (texto do advogado), país do IP na trilha e tradução de cortesia opcional.
*Feito quando:* a trilha guarda o país e o aceite de idioma; a tradução (se houver) aparece marcada "for convenience — English controls".

**T17 — Confirmar o IP real atrás do Caddy** (A-6) — pequeno, pode ir junto com a T12.
*Feito quando:* um teste ou checagem no VPS mostra que um `X-Forwarded-For` enviado pelo cliente não é aceito como IP.

---

## 6. O que precisa de advogado (Flórida, licenciado)

1. **Texto Parental:** tem o aviso do §744.301(3) **palavra por palavra**, em maiúsculas e +5 pt, com o nome certo da parte liberada (URACE.US INC e quem mais)? A renúncia **pelo menor** se limita a riscos **inerentes**? A lista de riscos inerentes do kart está adequada? Ir além do permitido faz perder a presunção do §744.301(3)?
2. **Texto Adult:** depois de *Sanislo* e de *Gillette* (kart, 5th DCA), o texto libera **com clareza** a negligência da URACE e de funcionários e agentes? Tem a cláusula de assunção de risco, de indenização, a de *severability*, a de lei e foro da Flórida e a declaração de que leu e entendeu? (Orange County hoje recorre ao 6th DCA; as decisões do 5th DCA continuam valendo nos tribunais de primeira instância enquanto não houver conflito [conferir].)
3. **Quem pode assinar pelo menor:** só pai ou mãe (*natural guardian*)? E tutor nomeado por juiz, padrasto ou madrasta, avós com procuração? Se os pais forem divorciados, basta um?
4. **Um ano de validade** e a regra de vencer no 18º aniversário: estão corretas? A waiver deve dizer que cobre "all sessions within 12 months"?
5. **ESIGN §7001(c):** confirmar que não é obrigatório para a waiver, e aprovar o texto do "Consumer Disclosure" (T10) mesmo assim.
6. **Página de certificado anexada** em vez de preencher os campos do corpo: basta? (F-6)
7. **Retenção:** por quanto tempo guardar (prescrição de 2 anos do §95.11(4)(a), a suspensão para menores do §95.051, a ação contratual escrita), e a política de nunca apagar?
8. **Modelo de declaração** FRE 902(11)/(13) e §90.902(11), e quem será o **custodiante**.
9. **Clientes estrangeiros:** cláusula de lei e foro; o risco do CDC (Brasil), do *Consumer Rights Act* (Reino Unido) e do Quebec; vale ter tradução de cortesia? (Para o Brasil, ouvir também um advogado brasileiro.)
10. **Seguro:** se a seguradora da pista exige algum formato de waiver (algumas exigem um texto específico ou um fornecedor específico).

Até essas respostas, a recomendação técnica é **manter `waiver_native = 0`** e o DocuSign como fonte de verdade.
