# Padrão de engenharia — vale em toda sessão, em todo projeto deste repositório

Dono, 30/09 (issue #14): *"preciso que faça também nos nossos projetos de agora pra frente"*.

## Fluxo: issue → branch → PR → merge → VPS
- Toda frente de trabalho é uma **issue** no GitHub (`UraceUs/Uraceagent`), com o pedido nas
  palavras do dono e o critério de "feito".
- Cada issue tem o seu **branch** (`claude/issue-<n>-<assunto>`) saindo do branch do VPS,
  `claude/configurar-open-claw-ooqo8x`, e o seu **PR** para ele, com `Closes #<n>` e o
  template de `.github/pull_request_template.md`.
- **Quem faz o merge é o Claude** (dono, 30/09: *"vc faz e garante que tudo vá para a vps"*),
  e só com teste, lint e build verdes. Como o branch do VPS não é o padrão do GitHub, o
  `Closes` não fecha a issue sozinho: feche à mão depois do merge.
- Depois do merge, o dono recebe **um bloco único** de deploy para o VPS.

## Qualidade (não entra PR sem isto)
- `ruff check .` limpo (`ruff.toml`) · `python -m pytest -q` verde
- Frontend: `npm run build` (tsc + vite) e `npx oxlint src` sem erro
- Teste novo **falha sem a mudança** (confira com `git stash` só do código)
- Tela mexida: end-to-end `CC_E2E=1 python -m pytest -q command_center/tests/e2e`
- CI em `.github/workflows/ci.yml` roda tudo isso em cada PR

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
- Tudo no fuso da Flórida (America/New_York)
- Commit termina com as linhas de atribuição do Claude; nenhum identificador de modelo
  em commit, PR ou arquivo
