"""O gerador de filtros nativos do Gmail (adminai/gerar_filtros_gmail.py).

Dono, 14/09: *"identifique as keywords de cada e-mail e coloque nativamente neles
os marcadores"*. A parte que decide — quais remetentes viram regra — é pura e
testável sem tocar no Gmail. É ela que impede o erro que importa: dar a um
marcador um remetente que na verdade pertence a outro.
"""
import importlib.util
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "adminai", "mcp"))
_spec = importlib.util.spec_from_file_location("gerar_filtros_gmail",
                                               os.path.join(RAIZ, "adminai", "gerar_filtros_gmail.py"))
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


@pytest.mark.parametrize("bruto,esperado", [
    ("Amazon.com <shipment-tracking@amazon.com>", "shipment-tracking@amazon.com"),
    ("MCINFO@UPS.COM", "mcinfo@ups.com"),
    ("sem endereço nenhum", ""),
    ("", ""),
])
def test_endereco(bruto, esperado):
    assert g._endereco(bruto) == esperado


def _conta(d):
    import collections
    return {k: collections.Counter(v) for k, v in d.items()}


def test_remetente_dominante_vira_regra_e_o_fraco_nao():
    por_remetente = _conta({
        "mcinfo@ups.com": {"Shipping Status": 9},
        "service@paypal.com": {"Finances/Receipt": 7, "Banks/PayPal": 1},
        "contato@aleatorio.com": {"Suppliers": 1},
        "ebay@alias.com": {"Finances/Anderson_EB3": 2},       # 2 de 3: fraco demais
    })
    mensagens = {"mcinfo@ups.com": 9, "service@paypal.com": 8, "contato@aleatorio.com": 1, "ebay@alias.com": 3}
    r = g.regras(por_remetente, mensagens, share=0.6, minimo=3)
    assert [e for e, _n, _t in r["Shipping Status"]] == ["mcinfo@ups.com"]
    assert [e for e, _n, _t in r["Finances/Receipt"]] == ["service@paypal.com"]
    assert "Banks/PayPal" not in r          # 1 de 8 nao sustenta
    assert "Suppliers" not in r             # uma mensagem so
    assert "Finances/Anderson_EB3" not in r, "2 mensagens nao viram regra"


def test_mensagem_com_dois_marcadores_nao_derruba_os_dois():
    """O bug que esvaziou o primeiro relatório: somando os marcadores como
    denominador, a UPS ficava com 50% em cada um e nenhum passava — e foi assim que
    `Shipping Status`, `wNews` e `Finances/Shopping`, os maiores da caixa, saíram
    sem regra nenhuma."""
    por_remetente = _conta({"mcinfo@ups.com": {"Shipping Status": 9, "Finances/Shopping": 9}})
    r = g.regras(por_remetente, {"mcinfo@ups.com": 9}, share=0.6, minimo=3)
    assert ("mcinfo@ups.com", 9, 9) in r["Shipping Status"]
    assert ("mcinfo@ups.com", 9, 9) in r["Finances/Shopping"]


def test_arquivo_morto_por_ano_nunca_vira_filtro():
    """`Years 2019-2023` é arquivo; o manual diz que a triagem não usa. Mandar
    e-mail NOVO para a pasta de 2019 seria enterrá-lo."""
    r = g.regras(_conta({"darrin@amrmotorplex.com": {"Years 2019-2023/y.2019": 8}}),
                 {"darrin@amrmotorplex.com": 8}, share=0.6, minimo=3)
    assert r == {}


def test_xml_agrupa_por_marcador_e_so_arquiva_wnews():
    r = {"wNews": [("promo@loja.com", 9, 9)],
         "Shipping Status": [("mcinfo@ups.com", 9, 9), ("tracking@shipstation.com", 4, 4)]}
    x = g.xml(r, "urace")
    assert x.startswith("<?xml version='1.0' encoding='UTF-8'?>")
    assert x.count("<entry>") == 2                                   # um filtro por marcador
    assert 'value="mcinfo@ups.com OR tracking@shipstation.com"' in x  # remetentes no mesmo filtro
    assert x.count("shouldArchive") == 1                             # so a propaganda sai da inbox
    assert "shouldArchive" in x.split("wNews")[1].split("</entry>")[0] or \
           "shouldArchive" in x.split("<entry>")[1]


def test_relatorio_marca_o_que_ficou_sem_regra_e_o_que_nao_e_do_manual():
    r = {"wNews": [("promo@loja.com", 9, 9)]}
    md = g.relatorio(r, ["wNews", "Suppliers"], ["wNews", "Suppliers", "Intruso/Novo"],
                     "urace", 0.6, 3)
    assert "marcadores com filtro: **1**" in md
    assert "Sem remetente estável" in md and "`Suppliers`" in md
    assert "NÃO estão no manual" in md and "`Intruso/Novo`" in md


def test_nao_usa_dominio_pessoal_como_regra():
    """gmail.com/hotmail e afins pegariam a caixa inteira — ficam de fora na amostra."""
    assert "gmail.com" in g.DOMINIOS_PROIBIDOS and "outlook.com" in g.DOMINIOS_PROIBIDOS


def test_abre_a_caixa_carregando_env_E_tokens(monkeypatch):
    """O bug de 14/09: o script carregava o env e esquecia os tokens. O Gmail
    respondia "conta não configurada. Disponíveis: []", que parece falta de
    credencial e não é — o token estava lá, ninguém tinha lido."""
    chamadas = []
    falso = type("M", (), {
        "_carregar_env": staticmethod(lambda: chamadas.append("env")),
        "_carregar_contas": staticmethod(lambda: chamadas.append("contas")),
        "_contas": {"urace": {}},
        "_sem_token": {"support": "/home/ubuntu/.urace/google-token-support.json"},
        "_mapa_labels": staticmethod(lambda c: {"wNews": "Label_1"}),
    })
    monkeypatch.setattr(g, "gmail_mcp", falso)
    assert g.marcadores_da_caixa("urace") == {"wNews": "Label_1"}
    assert chamadas == ["env", "contas"]
    # caixa sem token: erro que diz o que fazer, não stack trace
    with pytest.raises(SystemExit) as ex:
        g.marcadores_da_caixa("support")
    assert "google_auth.py --conta support" in str(ex.value)


def test_relatorio_nao_confunde_marcador_do_sistema_com_intruso():
    """O primeiro relatório listou INBOX, SENT, TRASH e CATEGORY_* como "não estão no
    manual". Ruído que escondia o que importava: `Action Required` e `Finance`, que
    apareceram sozinhos na caixa depois de 11/09."""
    na_caixa = ["INBOX", "SENT", "TRASH", "UNREAD", "CATEGORY_PROMOTIONS", "CHAT", "DRAFT",
                "wNews", "Finances/Receipt", "Customer Service/Leads", "Finance", "Receipts"]
    # `Customer Service/Leads` é da support@: entrou no manual em 14/09 e deixou de ser intruso
    assert g.desconhecidos(na_caixa) == ["Finance", "Receipts"]
    # marcador que o dono deixou de FORA voltando à caixa é intruso de novo: tem de aparecer
    assert g.desconhecidos(["Email Review/Finance", "wNews"]) == ["Email Review/Finance"]


def test_dominio_inteiro_vira_uma_regra_so():
    """Dono, 14/09: "deixe essas lógicas nativas o máximo que der". Regra por endereço
    só pega quem já apareceu; por domínio pega o endereço que a transportadora criar
    amanhã."""
    por_remetente = _conta({"mcinfo@ups.com": {"Shipping Status": 9},
                            "tracking@ups.com": {"Shipping Status": 5},
                            "quantum@ups.com": {"Shipping Status": 4}})
    mensagens = {"mcinfo@ups.com": 9, "tracking@ups.com": 5, "quantum@ups.com": 4}
    r = g.regras(por_remetente, mensagens, share=0.6, minimo=3)
    assert [e for e, _n, _t in r["Shipping Status"]] == ["@ups.com"], "um filtro, não três"
    assert ("@ups.com", 18, 18) in r["Shipping Status"]


def test_dominio_misturado_nao_vira_regra_mas_o_endereco_forte_sobrevive():
    """google.com manda de tudo: o domínio não pode virar regra. Mas o endereço que
    tem cara própria continua valendo."""
    por_remetente = _conta({
        "payments-noreply@google.com": {"Finances/Receipt": 8},
        "businessprofile-noreply@google.com": {"Platforms & Subscriptions/Google": 7},
        "no-reply@accounts.google.com": {"Platforms & Subscriptions/Google": 6},
    })
    mensagens = {"payments-noreply@google.com": 8, "businessprofile-noreply@google.com": 7,
                 "no-reply@accounts.google.com": 6}
    r = g.regras(por_remetente, mensagens, share=0.6, minimo=3)
    assert [e for e, _n, _t in r["Finances/Receipt"]] == ["payments-noreply@google.com"]
    alvos = [e for e, _n, _t in r["Platforms & Subscriptions/Google"]]
    assert "@google.com" not in alvos          # 7 de 15 no dominio: nao sustenta
    assert "businessprofile-noreply@google.com" in alvos


def test_um_endereco_so_no_dominio_nao_vira_regra_de_dominio():
    """Generalizar a partir de um endereço é chute: `noreply@x.com` não autoriza
    dizer que o domínio inteiro vai naquele marcador."""
    r = g.regras(_conta({"noreply@robinhood.com": {"Banks/Robinhood": 30}}),
                 {"noreply@robinhood.com": 30}, share=0.6, minimo=3)
    assert [e for e, _n, _t in r["Banks/Robinhood"]] == ["noreply@robinhood.com"]


def test_amostra_busca_por_id_e_nao_por_nome(monkeypatch):
    """O `|` no nome quebra a consulta do Gmail: `label:"Softwares|Apps/Docusign"`
    devolve ZERO, e `LOC | Practice/Practice Orlando` tem 370 conversas. Por isso a
    amostra vai por labelIds, que não passa por interpretação de texto."""
    urls = []
    falso = type("M", (), {
        "GMAIL": "https://x/users/me",
        "_mapa_labels": staticmethod(lambda c: {}),
        "_cabecalho": staticmethod(lambda d, h: "Alguém <a@b.com>"),
    })
    monkeypatch.setattr(g, "gmail_mcp", falso)
    monkeypatch.setattr(g, "_req", lambda conta, url, tentativas=4: urls.append(url) or {"messages": []})
    g.amostrar("urace", ["LOC | Practice"], 30, mapa={"LOC | Practice": "Label_392"}, verboso=False)
    assert "labelIds=Label_392" in urls[0]
    assert "label%3A" not in urls[0] and "%7C" not in urls[0], "nome com | não pode ir na consulta"


def test_regras_recusadas_pelo_dono_nao_voltam():
    """Revisão do dono em 14/09. O gerador não tem como saber que a Hilton não é
    corrida nem que o DOL não é banco: a recusa fica registrada."""
    casos = [("flag@dol.gov", "Banks/Idea Financial"),
             ("noreply@h6.hilton.com", "RACES/F4/JFC"),
             ("greenlane@dwolla.com", "RACES"),
             ("info@tkart.it", "Team/Samira")]
    for remetente, alvo in casos:
        r = g.regras(_conta({remetente: {alvo: 9}}), {remetente: 9}, share=0.6, minimo=3)
        assert r == {}, f"{remetente} -> {alvo} devia estar recusado"
    # o destino certo do mesmo remetente continua valendo
    r = g.regras(_conta({"flag@dol.gov": {"Finances/Anderson_EB3": 4}}), {"flag@dol.gov": 4}, 0.6, 3)
    assert [e for e, _n, _t in r["Finances/Anderson_EB3"]] == ["flag@dol.gov"]


def test_pasta_de_ex_funcionario_nunca_vira_filtro():
    """Mesmo erro do arquivo por ano: e-mail NOVO da Delta na pasta de quem saiu da
    empresa é e-mail enterrado."""
    for alvo in ("Team/Ex-Employees/MANU", "Ex-Funcionários/Lara"):
        r = g.regras(_conta({"deltaairlines@t.delta.com": {alvo: 8}}),
                     {"deltaairlines@t.delta.com": 8}, share=0.6, minimo=3)
        assert r == {}, alvo


def test_segunda_revisao_do_dono_15_09():
    """A que mais importava: `@orlandokartcenter.com` estava indo para
    `Finances/Pending Invoices ❗`, que é a fila de CONTAS A PAGAR do dono — todo
    e-mail do OKC viraria dívida fantasma no painel."""
    recusadas = [("@orlandokartcenter.com", "Finances/Pending Invoices ❗"),
                 ("mailer-daemon@googlemail.com", "Marketing & Sales/Colina | Site e ADS"),
                 ("@flybreeze.com", "RACES/F4/JFC"),
                 ("payments-noreply@google.com", "Marketing & Sales/Comercial/Canais | Social Media")]
    for remetente, alvo in recusadas:
        assert g.regras(_conta({remetente: {alvo: 9}}), {remetente: 9}, 0.6, 3) == {}, f"{remetente} -> {alvo}"
    # o OKC continua indo para a pasta de compra, que é o certo
    r = g.regras(_conta({"@orlandokartcenter.com": {"Finances/Shopping/Orlando Kart Center": 5}}),
                 {"@orlandokartcenter.com": 6}, 0.6, 3)
    assert [e for e, _n, _t in r["Finances/Shopping/Orlando Kart Center"]] == ["@orlandokartcenter.com"]
    # e o relatório do Kommo arquiva em wNews: decisão do dono em 15/09
    r = g.regras(_conta({"samuel.rulli@itcygnus.com": {"wNews/George | Atendente": 31}}),
                 {"samuel.rulli@itcygnus.com": 31}, 0.6, 3)
    assert r["wNews/George | Atendente"]


def test_familia_wnews_inteira_arquiva():
    """Decisão do dono (15/09): o relatório diário do Kommo, em
    `wNews/George | Atendente`, pode sair da inbox. A taxonomia dele já dizia que a
    família wNews inteira é propaganda — só o código tratava o nome exato."""
    r = {"wNews": [("promo@loja.com", 9, 9)],
         "wNews/George | Atendente": [("samuel.rulli@itcygnus.com", 31, 31)],
         "Finances/Receipt": [("service@paypal.com", 7, 8)]}
    x = g.xml(r, "urace")
    assert x.count("shouldArchive") == 2, "wNews e a sub-pasta arquivam; recibo não"
    assert "shouldArchive" not in x.split("Finances/Receipt")[1].split("</entry>")[0]


def test_recusar_o_dominio_recusa_os_enderecos_dele():
    """Tirar `@orlandokartcenter.com` da fila de contas a pagar não pode deixar
    `arielle@orlandokartcenter.com` entrar lá pela porta do endereço individual."""
    r = g.regras(_conta({"arielle@orlandokartcenter.com": {"Finances/Pending Invoices ❗": 4}}),
                 {"arielle@orlandokartcenter.com": 4}, 0.6, 3)
    assert r == {}


def test_regras_ditadas_pelo_dono_docusign_e_waiver():
    """Dono, 16/09: todo e-mail do DocuSign leva `Softwares|Apps/Docusign`; só a waiver
    enviada ou assinada leva TAMBÉM `Waivers`. É a única regra com assunto — remetente
    fixo mais o nome do modelo — e só entra onde o marcador existe."""
    d = g.regras_do_dono(["Softwares|Apps/Docusign", "Waivers", "wNews"])
    alvos = [alvo for _q, alvo, _a in d]
    assert alvos == ["Softwares|Apps/Docusign", "Waivers"]
    busca_waiver = next(q for q, alvo, _a in d if alvo == "Waivers")
    assert "Waiver of Liability" in busca_waiver and "Completed:" in busca_waiver and "Please Complete" in busca_waiver
    assert "Voided" not in busca_waiver
    # a urace@ não tem esses marcadores: nada entra
    assert g.regras_do_dono(["wNews", "Finances/Receipt"]) == []
    x = g.xml({}, "support", d)
    assert x.count("<entry>") == 2 and "hasTheWord" in x and "shouldArchive" not in x
    md = g.relatorio({}, ["Waivers"], ["Waivers"], "support", 0.6, 3, d)
    assert "Regras ditadas pelo dono" in md and "Sem remetente estável" not in md.split("## Regras ditadas")[0]


def test_dominio_de_plataforma_de_envio_nunca_vira_regra_de_dominio():
    """Revisão da extensão (16/09): `@g.shopifyemail.com` é TODA loja Shopify, não a do
    Orlando Kart Center. O endereço da loja continua valendo; o domínio, nunca."""
    por = _conta({"store+57444597856@t.shopifyemail.com": {"Finances/Shopping/Orlando Kart Center": 20},
                  "store+83901055190@g.shopifyemail.com": {"Finances/Shopping/Orlando Kart Center": 3}})
    msgs = {"store+57444597856@t.shopifyemail.com": 23, "store+83901055190@g.shopifyemail.com": 3}
    r = g.regras(por, msgs, share=0.6, minimo=3)
    alvos = [e for e, _n, _t in r["Finances/Shopping/Orlando Kart Center"]]
    assert "store+57444597856@t.shopifyemail.com" in alvos
    assert not any(a.startswith("@") for a in alvos), "nada de @shopifyemail.com"


def test_intruso_que_o_dono_deixou_de_fora_continua_sendo_listado():
    """`Action Required` está no manual da support@ como FORA. Se aparecer na urace@, não
    pode ser tratado como conhecido — é intruso e tem de aparecer no relatório."""
    assert g.desconhecidos(["wNews", "Action Required", "Email Review/Finance"]) == ["Action Required", "Email Review/Finance"]


def test_gerador_le_o_manual_confirmado_no_painel(monkeypatch, tmp_path):
    """A support@ gerou 4 filtros em vez de 61: o gerador procurava nela os marcadores
    da urace@, porque só olhava a lista estática do código. Quem manda depois da
    confirmação do dono é a tabela gmail_labels, por caixa."""
    import os as _os
    from command_center.db import conectar, aplicar_schema
    _os.environ["CC_DB_PATH"] = str(tmp_path / "cc.sqlite")
    con = conectar()
    try:
        aplicar_schema(con)
        con.execute("UPDATE gmail_labels SET status='confirmado' WHERE name IN ('Customer Service/Leads','Waivers')")
        con.commit()
        assert sorted(g.confirmados_no_painel("support")) == ["Customer Service/Leads", "Waivers"]
        assert "Customer Service/Leads" not in g.confirmados_no_painel("urace")
        assert "Finances/Receipt" in g.confirmados_no_painel("urace")
    finally:
        con.close()
        _os.environ.pop("CC_DB_PATH", None)


def test_regra_ditada_manda_sozinha_no_marcador_dela():
    """Dono, 16/09: só waiver ENVIADA ou ASSINADA leva `Waivers`. A amostra somou
    `dse_na4@docusign.net`, que é o remetente de TODO e-mail do DocuSign — juntas, as
    duas mandariam 'visualizou' e 'anulado' para lá. Onde ele falou, a amostra cala."""
    ditadas = g.regras_do_dono(["Softwares|Apps/Docusign", "Waivers"])
    por_marcador = {"Waivers": [("dse_na4@docusign.net", 9, 10)],
                    "Softwares|Apps/Docusign": [("@docusign.net", 13, 14)],
                    "Fornecedores": [("info@palaceracewear.com", 5, 5)]}
    r = g.sem_conflito_com_o_dono(por_marcador, ditadas)
    assert "Waivers" not in r and "Softwares|Apps/Docusign" not in r
    assert r["Fornecedores"], "o resto da amostra continua valendo"
    # e o XML final fica com a regra dele, não com a da amostra
    x = g.xml(r, "support", ditadas)
    assert "Waiver of Liability" in x and "dse_na4@docusign.net" not in x


def test_quarta_revisao_support_16_09():
    """O domínio falso da RD Station não pode virar filtro: arquivar phishing numa pasta
    normal o faz parecer legítimo."""
    for remetente, alvo in [("receiv@rdstation-fin.com", "Marketing/RD Station /MailMarketing"),
                            ("no-reply@accounts.google.com", "Eduardo/n8n"),
                            ("support@kommo.com", "Marketing"),
                            ("@united.com", "Events & National Races")]:
        assert g.regras(_conta({remetente: {alvo: 9}}), {remetente: 9}, 0.6, 3) == {}, f"{remetente} -> {alvo}"
    # o domínio verdadeiro da RD Station continua valendo
    r = g.regras(_conta({"info@rdstation.com.br": {"Marketing/RD Station /MailMarketing": 5}}),
                 {"info@rdstation.com.br": 5}, 0.6, 3)
    assert r["Marketing/RD Station /MailMarketing"]
