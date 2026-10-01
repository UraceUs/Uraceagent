# Prompt da extensão — trocar o link dos botões de reservar que dão 404 (issue #47)

Cole isto na extensão do navegador, com o wp-admin do urace.us aberto. **Esta é uma
mudança no site público**: quem cola o prompt é o dono, e isso é a autorização. As
decisões estão em `docs/site-publico/decisoes-2026-10-01.md`.

---

Você vai trocar **só o link (URL) de botões** em 6 páginas do urace.us. Siga estas regras:

- **Não** mude texto, cor, imagem, preço, produto, página, menu, tema ou plugin.
- **Não** publique nem despublique produto.
- **Não** apague nada.
- **Não** atualize plugin.
- Se o Elementor pedir para atualizar, converter ou ativar a licença, **cancele**.
- Se um botão estiver num **template global**, como "Página de serviço V2" (id 1212),
  **pare e anote**: mudar o template muda todas as páginas que o usam. Nesse caso troque
  o link só na página.
- Alguém da equipe está editando o site ao mesmo tempo. Se a página estiver bloqueada
  ("X está editando"), **não assuma o controle**: anote e passe para a próxima.

## Antes de começar

Abra cada página abaixo no site (sem login) e anote quantos links apontam para o endereço
antigo. A contagem de 01/10 está na tabela.

## O que trocar

| Página (Páginas › editar com Elementor) | Endereço antigo do botão | Endereço novo | Botões em 01/10 |
|---|---|---|---|
| `/services/kart-school/` | `https://urace.us/product/urace-kart-school/` | `https://urace.us/product/urace-academy-1-month-4-sessions/` | 5 |
| `/services/professional-coaching/` | `https://urace.us/product/professional-coaching/` | `https://urace.us/product/arrive-and-drive/` | 5 |
| `/services/intensive-training-camp/` | `https://urace.us/product/urace-intensive-training-camp/` | `https://urace.us/contact/` | 6 |
| `/services/birthday-party/` | `https://urace.us/product/corporate-karting-events/` | `https://urace.us/contact/` | 1 |
| `/services/corporate-events/` | `https://urace.us/product/corporate-karting-events/` | `https://urace.us/contact/` | 3 |
| `/services/group-events-social-gatherings/` | `https://urace.us/product/corporate-karting-events/` | `https://urace.us/contact/` | 5 |

Em cada página:

1. Abra a página no Elementor.
2. Em cada botão cujo link seja o endereço antigo, troque só o campo **Link** pelo
   endereço novo.
3. Clique em **Atualizar** (é o salvar do Elementor) uma vez, no fim da página.

## Depois

1. Abra cada página **sem login**, numa aba anônima.
2. Confirme que nenhum link aponta mais para o endereço antigo.
3. Confirme que o endereço novo abre (não dá 404).

## Como entregar

Uma tabela por página, com:

- os botões trocados;
- os que não conseguiu trocar, e por quê;
- se o botão era de template global.

No fim, uma linha: **"Só links foram trocados."**
