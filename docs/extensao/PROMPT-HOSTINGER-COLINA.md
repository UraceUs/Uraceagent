# Prompt da extensão — Box 3 e saída da Colina Tech (issue #49)

Cole isto na extensão do navegador, com o hPanel e o wp-admin do urace.us abertos. **Isto
muda o site público e o painel da Hostinger.** Quem cola o prompt é o dono, e isso é a
autorização. O que o dono decidiu em 01/10:

- *"box 3"*;
- sobre a Colina Tech: *"Eles estão saindo e não vão cuidar mais disso"*.

---

## Regras

- Faça **só** os passos abaixo, nesta ordem. Se uma tela pedir algo fora da lista, **cancele**.
- **Não** troque senha nem crie senha.
- **Não** apague usuário, página, produto, plugin ou arquivo.
- **Não** copie para o relatório nenhuma senha, token ou chave, nem dado de cliente.
- Se o Elementor pedir para atualizar, converter ou ativar a licença, **cancele**.
- Se outra pessoa estiver editando uma página ("X está editando"), **não assuma o
  controle**: anote e siga para o próximo passo.

## 1. Endereço: Box 5 → Box 3

1. Abra wp-admin › Modelos (Templates) › **"Página de serviço V2"** (id 1212) no Elementor.
2. Na seção "Location", no widget de título "Address", troque só o texto
   `10724 Cosmonaut Blvd, Box 5` por `10724 Cosmonaut Blvd, Box 3`.
3. Clique em **Atualizar** uma vez.
4. Se alguma página de serviço tiver o widget **copiado** (e não vindo do modelo), faça a
   mesma troca nela. As páginas são: arrive-and-drive, kart-school, intensive-training-camp,
   professional-coaching, birthday-party, corporate-events e group-events-social-gatherings.
5. **Não mexa** no `page-contact.php` do tema, mesmo que tenha "Box 5": é código PHP. Só
   anote que está lá.

Para conferir, abra as 7 páginas sem login, numa aba anônima, e veja se mostram "Box 3".

## 2. E-mails que hoje vão para a agência

1. **Configurações › Geral › Endereço de e-mail da administração**: troque
   `desenvolvimento@colinatech.com.br` por `urace@urace.us` e salve. O WordPress manda um
   link de confirmação para urace@urace.us. **O dono confirma** pelo Gmail. Até lá, a
   troca fica pendente; anote isso.
2. **Contato (Contact Form 7) › "[CT] Form Pop-up" (1839) › aba E-mail › Para**: troque
   `[_site_admin_email]` por `support@urace.us, urace@urace.us` (igual aos outros três
   formulários) e salve.
3. **Configurações › SXS LP / Kommo › E-mail de reserva**: troque o endereço
   @colinatech.com.br por `support@urace.us` e salve.
   - **Não preencha** subdomínio, token, funil nem etapa: o token do Kommo é credencial, e
     quem coloca é o dono.

## 3. Acesso da agência na Hostinger

1. Abra hPanel › Perfil › **Compartilhamento de conta** › Dar acesso.
2. **Remova o acesso** do colaborador da Colina Tech: o único da lista, com "Gerenciar
   serviços e faturamento". Remover só tira o acesso dele: nada da conta é apagado, e dá
   para convidar de novo.

## 4. Registro de quem mexe no site

1. Abra wp-admin › Plugins › **WP Activity Log**. Ele está inativo, na versão 5.6.5, que é
   vulnerável.
2. Clique em **atualizar agora**. Só depois de atualizado, clique em **Ativar**.
3. Confira se a home e uma página de produto continuam abrindo.
   - Se alguma der erro, **desative o WP Activity Log** na hora e anote.
4. Se o plugin abrir um assistente de configuração, escolha as opções padrão e **não**
   ligue nada que mande dados para fora (relatórios por e-mail, integrações).

## Como entregar

Uma lista com os passos 1 a 4. Para cada passo, diga:

- o que foi feito;
- o que ficou pendente, e por quê;
- onde viu cada coisa (menu › tela).

No passo 1, diga quantas páginas mostram "Box 3" no fim e se o `page-contact.php` tem
"Box 5".

Termine com a linha: **"Nenhuma senha foi trocada e nada foi apagado."**
