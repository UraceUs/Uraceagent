# Checklist da troca do urace.us (#173)

Dono, 09/10: troca do DNS *"quando eu decidir que esta pronto"*. Esta lista é para o dia da troca;
nada aqui roda sozinho. O passo a passo técnico está em `site-inteiro-2026-10-09.md`, seção
"Trocar o urace.us".

## Antes (pode fazer já)

- [ ] Na VPS, `~/.urace/adminai.env` tem `SITE_GTM_ID`, `SITE_META_PIXEL_ID`, `SITE_KOMMO_ID` e
      `SITE_KOMMO_HASH` (os mesmos do `urace.us` de hoje).
- [ ] No `novo.urace.us`: o banner de cookies aparece na primeira visita; **Accept** liga a medição,
      **Decline** não; **Cookie settings** no rodapé reabre o banner.
- [ ] O balão do chat aparece e uma mensagem de teste cai no Kommo (apague o lead de teste depois).
- [ ] No Tag Manager (`GTM-59CCNDC`), conferir que o pixel do Meta **não** está também dentro do
      container — senão o Meta conta tudo duas vezes. (Dono.)
- [ ] Reserva de ponta a ponta no `novo.urace.us`: data, kart, Lead and Follow, carrinho, conta,
      Stripe, página do pedido, e-mail.

## No dia (dono)

- [ ] Registro A de `urace.us` e `www.urace.us` → IP da VPS (como foi feito com `novo.urace.us`).
- [ ] Avisar o Claude: ele manda **um bloco** com as variáveis `CC_SITE_HOSTS`, `CC_SITE_PREVIEW=0`,
      `CC_DOMINIOS_EXTRAS` e o deploy.

## Depois (Claude confere e manda as fotos)

- [ ] `https://urace.us` abre o site novo com cadeado; `www.` e `novo.` levam a `urace.us` (301).
- [ ] `my.urace.us/...` leva a `https://urace.us/ops/portal/...` mantendo o caminho.
- [ ] As 10 páginas principais abrindo (início, Arrive and Drive, Academy, Pro Team, iniciantes,
      carreira, sobre, loja, blog, contato), sem rolar para o lado em 360 px e 390 px.
- [ ] Contato pelo site cai em Vendas com a campanha; chat cai no Kommo.
- [ ] `robots.txt` libera o site; `sitemap.xml` enviado no Search Console. (Dono, com o acesso dele.)
- [ ] WordPress na Hostinger fica guardado como está (decisão de 06/10: não mexer).
