# Padrão de engenharia — vale em toda sessão, em todo projeto deste repositório

Dono, 30/09 (issue #14): *"preciso que faça também nos nossos projetos de agora pra frente"*.

## Fluxo: issue → branch → PR → merge → VPS
- Toda frente de trabalho é uma **issue** no GitHub (`UraceUs/Uraceagent`), com o pedido nas
  palavras do dono e o critério de "feito".
- Cada issue tem o seu **branch** (`claude/issue-<n>-<assunto>`) saindo do branch do VPS,
  `claude/commandcenter-vps`, e o seu **PR** para ele, com `Closes #<n>` e o
  template de `.github/pull_request_template.md`.
- **Quem faz o merge é o Claude** (dono, 30/09: *"vc faz e garante que tudo vá para a vps"*),
  e só com teste, lint e build verdes. Desde 14/10 o branch do VPS é o padrão do GitHub
  (renomeado de `claude/configurar-open-claw-ooqo8x`), então o `Closes` fecha a issue no merge.
- Depois do merge, o dono recebe **um bloco único** de deploy para o VPS.

## Entrega por blocos — teste fora da VPS (dono, 15/10, #277)
Dono: *"a partir de agora você rode os testes ... no seu ambiente virtual, porque os testes estão
demorando de 15 a 20 minutos ... comita, empurra para o GitHub e testa por lá, antes da gente jogar ali
na VPS ... separa por blocos, de acordo com as issues, para jogar mais coisas de uma vez"*.
- **Bloco** = um conjunto de issues que vai junto para a VPS. O Claude propõe o bloco ao dono com a
  lista de issues e o que muda no ar; as perguntas que só o dono responde vão **todas juntas**, no começo.
- Cada issue continua com o seu branch e o seu PR. Tudo é testado **no ambiente do Claude** (pytest,
  lint, build, end-to-end e a **prova com fotos**, `CC_E2E=1 CC_FOTOS=… pytest
  command_center/tests/e2e/test_pacote_de_provas.py`) e no **CI do GitHub**, que também gera o pacote de
  fotos como artefato.
- O dono recebe **um deploy por bloco**, e só depois que o CI do **commit do branch da VPS** estiver
  verde. Com os três jobs verdes no push ao branch da VPS, o CI grava a tag `ci-verde/<sha>`; o
  `servir_command_center.sh` procura essa tag pelo git (a chave do `git pull` — o repositório é privado e a
  VPS não lê a API do GitHub, #286) e, achando, **não roda a bateria na VPS**; na dúvida, roda. Por isso o
  bloco só vai ao dono **depois** que a tag do commit do merge existir. A prova com fotos na VPS (`testar_tudo.sh`) vira opcional.
- Junto do bloco de deploy vai o resumo do que mudou e as fotos da prova, para o dono ver antes de subir.

## Qualidade (não entra PR sem isto)
- `ruff check .` limpo (`ruff.toml`) · `python -m pytest -q` verde
- Frontend: `npm run build` (tsc + vite) e `npx oxlint src` sem erro
- Teste novo **falha sem a mudança** (confira com `git stash` só do código)
- Tela mexida: end-to-end `CC_E2E=1 python -m pytest -q command_center/tests/e2e`
- CI em `.github/workflows/ci.yml` roda tudo isso em cada PR
- **Playbook junto** (dono, 13/10, #199): mudou tela, rota ou processo, o playbook do assunto em
  `docs/playbooks/` (geral, vendas, mecânicos e coaches) e o guia de Suits mudam no mesmo PR

## Interface (toda tela)
- **Um `h1` por página**; seções `h2`, subitens e modais `h3`, sem pular nível
- Título da aba por tela; `meta description`
- **Mobile primeiro**: nada rola para o lado em 360 px e 390 px; alvo de toque ≥ 40 px
- **Motion**: durações e curvas dos tokens do CSS, só `transform`/`opacity`, e
  `prefers-reduced-motion` desliga o que não é essencial
- Imagem comprimida (WebP, ≤ 1600 px, sem EXIF), `loading="lazy"` nas listas
- Código dividido por rota (`React.lazy`); o bundle inicial não cresce à toa
- URL limpa: caminho, não parâmetro (`/compras/12`); endereço antigo redireciona
- **Inserção manual sempre com "Vincular ao cliente"** (dono, 08/10, #158): todo formulário que
  cria registro à mão tem o seletor de cliente (`Picker` de `components/Unir.tsx`), grava o
  `client_id` e puxa do cadastro o que já existe (nome, e-mail, telefone, piloto, endereço, medidas)

## Backend
- Lista que cresce é **paginada no backend** (`limit`/`offset` + `total`)
- GET da API com **ETag** (304 quando nada mudou); dado privado nunca em cache compartilhado
- **Observabilidade**: `X-Request-ID`, log estruturado por requisição (rota, status, tempo),
  métricas por rota; erro do navegador e Web Vitals chegam ao servidor. Nunca logar corpo,
  cookie ou token.

## Páginas públicas (o painel é privado: `noindex` e fora do `robots.txt`)
- `robots.txt`, `sitemap.xml`, `<link rel="canonical">`, título e descrição únicos,
  um `h1`, **schema markup** (JSON-LD), imagem comprimida

## Regras do dono que continuam valendo
- Não destruir dados, não apagar bancos, não regenerar credencial crítica sem necessidade;
  risco real de perda ou indisponibilidade → pedir autorização antes
- Secret nunca no código nem no repositório; nunca pedir token/senha/PIN no chat
- Nunca pôr serviço de um cliente no card de outro · **NO FAKE DATA** · não usar Turo nem Hostaway
- **Repositório público** (dono, 14/10, #244): nunca dado real de cliente no repositório (nome,
  e-mail, telefone, nascimento, endereço, medidas, valor ou ID ligado a pessoa, conversa). Teste e
  documento usam fictício marcado (`@example.com`, 555-01xx, nome inventado); `brain/` e `relatorios/`
  citam cliente pelo número do card; `test_sem_dado_de_cliente.py` trava. NO FAKE DATA continua valendo para o que o sistema mostra
- Tudo no fuso da Flórida (America/New_York)
- Commit termina com as linhas de atribuição do Claude; nenhum identificador de modelo
  em commit, PR ou arquivo
