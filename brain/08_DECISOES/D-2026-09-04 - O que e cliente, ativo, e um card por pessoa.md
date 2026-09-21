# D-2026-09-04 — O que é cliente, quem está ativo, um card por pessoa

**Dono, 04/09/2026**, ao ver a aba Clientes cheia de corridas e nomes
repetidos:
- *"Nem tudo que está no Asana é cliente. Corrida não entra."*
- *"Serviço nos últimos seis meses = ativo; mais de seis meses = inativo."*
- *"Os mais recentes sempre no topo."*
- *"Alex Alonso com s e com z é a mesma pessoa. Um card por cliente, sem
  duplicação."*
- *"Buscar tudo daquele cliente: Gmail pelo e-mail, DocuSign, QuickBooks.
  Os acessos do DocuSign chegam no support@."*
- *"Uma aba com todas as parental e adult assinadas, para baixar, ligadas
  ao cliente."*

**Como ficou** (`command_center/providers/identidade.py`):
- **Pessoa no título**: `Session Setup | Aaron Benoit_Kart [..]` → *Aaron
  Benoit*. Título com ano, série, pista, "created by", "nothing is done"
  não vira cliente. O que já tinha virado e não tem nada humano ligado sai
  do espelho (`limpar_nao_clientes`).
- **Mesma pessoa**: e-mail igual, telefone igual (10 dígitos) ou nome
  normalizado igual → **une sozinho** (o duplicado fica inteiro em
  `client_merges`). Nome *quase* igual (Alonso/Alonzo) → **par para
  revisão** na tela, com botão "Unir" e parecer da IA; nunca une no escuro.
- **Status**: recalculado a cada sincronia; mudança feita à mão trava
  (`status_locked`).
- **Varredura por cliente**: botão no card e rotina para os ativos: Gmail
  (`from:`/`to:` do e-mail nas duas caixas, fora da inbox também),
  DocuSign (`docusign_waivers_de`). QuickBooks entra quando conectar.

Relacionado: [[Asana]], [[Gmail]], [[DocuSign]], [[Waiver de responsabilidade]].
