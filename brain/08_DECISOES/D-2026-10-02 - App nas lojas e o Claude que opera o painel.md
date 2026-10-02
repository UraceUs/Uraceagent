---
tipo: decisao
tipo_info: DECISION
status: ativo
owner: Italo Silveira
data: 2026-10-02
fonte: dono, 02/10/2026
---

# D-2026-10-02 — App nas lojas e o Claude que opera o painel

[[URACE]] · [[Command Center - Proximos passos]] · substitui em parte
[[D-2026-09-21 - Celular e PWA, sem app nativo]]

## 1. O Command Center operável pelo Claude de cada vendedor (#73)

Dono: *"eu preciso que toda, todas as funcionalidades sejam operáveis pela API, não só como
visualização, mas como operação mesmo... os nossos vendedores, que é quem agenda as pessoas,
fecha as vendas, envia as invoices... usam o Claude nas máquinas deles... de acordo com o nível
de hierarquia ali do operador ou gerente"*.

**O que mudou:** o conector deixou de ser só leitura (decisão de 23/09) **para quem autoriza
operar**. As regras que ficam:

- **O Claude age como a pessoa, nunca acima dela.** O operador faz o que um operador faz no
  painel; o que é do gerente continua do gerente. A pessoa rebaixada perde a escrita sozinha.
- **Não existe um caminho paralelo.** O Claude chama as mesmas rotas dos botões do painel. Valem
  as mesmas travas: não cobrar duas vezes, card do cliente certo, e o que é "nunca" continua nunca.
- **O que vai para o cliente ou cobra pede confirmação.** Invoice, waiver, e-mail, QuickBooks,
  DocuSign, Asana, Kommo e fechar venda: o Claude mostra antes o que vai fazer, e só executa
  depois do "pode" da pessoa.
- **Tudo na auditoria com o nome de quem fez** (`mcp.call` mais o evento da própria rota).
- **Login, senha, chaves de API e a área do cliente ficam fora do conector.**

## 2. App nas lojas, um só, com o Command Center escondido (#74)

Dono: *"preciso que realmente seja um aplicativo... nas bancas de aplicativos... versionado
tanto para iOS quanto para Android. E que cada atualização nossa atualize esses aplicativos
também... a gente sobe um aplicativo só... área do cliente... quanto o Command Center...
clicar no ícone U"*.

**Por que muda a decisão de 21/09:** em 21/09 o app era só para a equipe (cerca de 10 pessoas),
e a loja não trazia nada. Agora o app é **dos clientes**: a área do cliente precisa estar onde o
cliente procura, na App Store e no Google Play.

**Como, sem perder o que a decisão de 21/09 protegia:**

- **Capacitor em volta do mesmo site, sem código duplicado.** As telas vêm do servidor, então
  um conserto chega ao celular no deploy (os mesmos 3 minutos), sem fila de revisão. A loja só
  revisa quando muda a parte nativa.
- **Um app só, "URACE".** Abre na área do cliente; **5 toques no "U"** do login abrem o
  Command Center. O toque não dá acesso a nada sozinho: lá dentro vale o login e o papel.
- **Versão e build automáticos:** cada merge gera o build e o manda para o TestFlight e para o
  teste interno do Google Play. Publicar para todos é um clique do dono.
- **A conta e a assinatura são do dono:** Apple Developer como organização (US$ 99/ano, com
  D-U-N-S) e Google Play (US$ 25). Nenhuma chave passa pelo chat; tudo vai para os secrets
  do GitHub.

## O que ainda é decisão do dono

- Excluir a conta pelo app (a Apple exige): proposta de **pedido de exclusão** que desliga o
  login e chega à equipe, sem apagar dado sem a decisão dele.
- Notificação push no app (precisa de Firebase e de chave APNs) e Face ID / digital.
