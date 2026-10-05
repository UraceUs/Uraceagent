---
tipo: decisao
tipo_info: DECISION
data: 2026-10-05
fonte: [[Administrative AI]]
responsavel: O que o mecânico e o coach alcançam no Command Center, e como os checklists funcionam.
status: ativo
---

# D-2026-10-05 — Cargos Mecânico e Coach, e checklists nativos com foto

issue #92, 05/10/2026

## O que foi decidido
- **Cargos Mecânico e Coach.** O papel é OPERATOR (é o que deixa lançar peça e contar estoque) e
  o **cargo restringe**. O coach tem o mesmo acesso do mecânico, por enquanto. Quem muda é o
  administrador, em Usuários.
- **O que eles alcançam** (aprovado como proposto):
  - **Meu dia**, que é a tela inicial e o calendário: serviços, corridas e sessões do site, sem
    valores nem contato do cliente.
  - **Checklists:** preenchem os do seu cargo, com foto.
  - **Balcão:** cobrar, guardar no estoque do cliente, código novo. Não enviam a invoice.
  - **Estoque** (sem custo nem margem) e **Pedidos/Compras** (pedir e receber).
  - **Card do cliente** sem e-mail, invoice, mensalidade e IA. Ver, não editar.
  - **Chat da equipe.**
  - Todo o resto fica fechado: a trava é no servidor e é uma **lista do que pode**, então rota
    nova nasce fechada para o cargo.
- **Checklists nativos**, vindos da planilha **Master Checklist** (importada sem redigitar).
  - Gerente para cima vê e edita: itens, quando aparece (treino, corrida, trimestral, avulso),
    de quem é e "um por kart".
  - **Foto opcional em todo item.** O gerente torna obrigatória num item ou no checklist inteiro
    (aí ele pede pelo menos uma foto).
  - O preenchimento é uma **cópia** do modelo: editar o modelo não muda o que já foi feito.
  - Checklist começado e não concluído num dia que passou vai para **Precisa de atenção**.
- **Ícone do app:** opção C, o U laranja como traçado de pista com a chegada quadriculada.

## Por quê
Dono, 05/10: *"cria um novo cargo que vai ser para os mecânicos"*; *"o checklist pronto… gerente
para cima consegue ver e editar… o mecânico completa… abrir a câmera, tirar fotos ou subir"*.

## Fonte
issue #92 · `command_center/providers/checklists.py` · `auth.ROTAS_DO_CARGO`
