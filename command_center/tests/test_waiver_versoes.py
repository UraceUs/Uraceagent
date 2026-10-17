"""Versões do modelo da waiver nativa e a conferência do aviso §744.301(3) (#116, lacunas D-4 e F-2).

O que estes testes trancam: reimportar o modelo não perde a versão anterior (ela continua consultável, com o
PDF, e a assinatura antiga acha o modelo pelo hash); a tabela de versões é append-only no próprio SQLite, com a
trava criada a cada subida; e o aviso do parental é conferido (texto inteiro, maiúsculas, +5 pt) num modelo de
exemplo. O texto do aviso NÃO está no código: aqui é um aviso de EXEMPLO, fictício, marcado como tal. Sem o
texto aprovado configurado a conferência só informa; com ele, o parental que não passa não entra, não liga e
não se assina online."""
import hashlib
import io
import json
import os
import sqlite3

import pytest

import command_center.providers as prov
from command_center import db
from command_center.db import aplicar_schema, conectar, inserir, todos, um
from command_center.providers import waiver_nativa as wn
from command_center.tests.test_waiver_nativa import (ADULT, CONTA, PARENTAL, S, _pdf, assina, cli, cliente,  # noqa: F401
                                                     equipe, liga)

# Um aviso de EXEMPLO, só para o teste: não é o texto da lei. O de verdade é o que o advogado aprovar.
AVISO_EXEMPLO = ("EXAMPLE NOTICE FOR AUTOMATED TESTS ONLY. THIS IS NOT THE TEXT OF THE FLORIDA STATUTE. "
                 "THE REAL NOTICE IS THE TEXT THAT THE LAWYER APPROVES FOR THE PARENTAL WAIVER.")
CORPO = ["Fictitious parental consent document used only by the test suite.",
         "Participant: Test Kid (fictitious). Parent: Test Parent (fictitious).",
         "This paragraph stands for the body text of the waiver, in the normal size.",
         "Nothing in this document is a real waiver or a real legal text."]


def _parental(aviso=AVISO_EXEMPLO, pt_aviso=15, pt_corpo=10, maiusculas=True, paginas=1):
    """Um PDF parental de exemplo (reportlab): o corpo em `pt_corpo` e o aviso em `pt_aviso`, quebrado em linhas."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=letter)
    for n in range(paginas):
        y = 740
        c.setFont("Helvetica", pt_corpo)
        for linha in CORPO:
            c.drawString(54, y, linha)
            y -= pt_corpo + 4
        if aviso and n == paginas - 1:
            y -= 10
            c.setFont("Helvetica-Bold", pt_aviso)
            texto = aviso if maiusculas else aviso.capitalize()
            palavras, atual = texto.split(), ""
            for p in palavras:
                if len(atual) + len(p) > 48:
                    c.drawString(54, y, atual); y -= pt_aviso + 4; atual = p
                else:
                    atual = f"{atual} {p}".strip()
            c.drawString(54, y, atual); y -= pt_aviso + 10
            c.setFont("Helvetica", pt_corpo)
            for linha in CORPO:
                c.drawString(54, y, linha)
                y -= pt_corpo + 4
        c.showPage()
    c.save()
    return b.getvalue()


CFG = {"text": AVISO_EXEMPLO, "sha256": hashlib.sha256(AVISO_EXEMPLO.encode()).hexdigest(), "error": None}


# ------------------------------------------------------------------ a conferência do aviso (modelo de exemplo, no CI)
def test_o_aviso_grande_e_em_maiusculas_passa():
    from command_center.providers import aviso_744
    r = aviso_744.conferir(_parental(), CFG)
    assert r["configured"] and r["ok"] is True, r
    assert r["found"] and r["uppercase"] and r["notice_pt"] == 15 and r["body_pt"] == 10 and r["difference_pt"] == 5
    assert "em maiúsculas" in r["reason"]


@pytest.mark.parametrize("pdf,trecho", [
    (lambda: _parental(aviso=None), "não está inteiro no modelo"),
    (lambda: _parental(aviso=AVISO_EXEMPLO.replace("LAWYER APPROVES", "LAWYER WROTE")), "falta a partir de “APPROVES"),
    (lambda: _parental(pt_aviso=10), "não tem 5 pt a mais"),
    (lambda: _parental(pt_aviso=14), "não tem 5 pt a mais"),
    (lambda: _parental(maiusculas=False), "em minúscula"),
    (lambda: _pdf("PARENTAL CONSENT - test document"), "não está inteiro no modelo"),
])
def test_sem_o_aviso_do_tamanho_certo_e_em_maiusculas_falha(pdf, trecho):
    from command_center.providers import aviso_744
    r = aviso_744.conferir(pdf(), CFG)
    assert r["configured"] and r["ok"] is False and trecho in r["reason"], r


def test_espaco_pontuacao_e_quebra_de_linha_do_texto_aprovado_nao_contam():
    """O advogado manda o texto com outra quebra de linha e aspas curvas: o que conta são as letras, na ordem."""
    from command_center.providers import aviso_744
    outro = AVISO_EXEMPLO.replace(". ", ".\n\n").replace("NOT THE TEXT", "NOT  THE “TEXT”")
    r = aviso_744.conferir(_parental(), {**CFG, "text": outro, "sha256": "x" * 64})
    assert r["ok"] is True, r


def test_o_aviso_em_outra_pagina_e_o_corpo_maior_que_o_titulo_ainda_sao_medidos():
    from command_center.providers import aviso_744
    r = aviso_744.conferir(_parental(paginas=3, pt_aviso=17, pt_corpo=12), CFG)
    assert r["ok"] is True and r["body_pt"] == 12 and r["notice_pt"] == 17, r


def test_sem_texto_aprovado_so_informa(tmp_path, monkeypatch):
    from command_center.providers import aviso_744
    monkeypatch.setenv("CC_WAIVERS_DIR", str(tmp_path / "w"))
    monkeypatch.delenv("CC_WAIVER_AVISO_744", raising=False)
    assert aviso_744.aprovado() is None
    r = aviso_744.conferir(_pdf("PARENTAL CONSENT - test document"))
    assert r == {"configured": False, "ok": None, "rule": r["rule"], "reason": r["reason"]} and "advogado" in r["reason"]


def test_o_texto_aprovado_vem_do_arquivo_e_o_arquivo_que_nao_abre_barra(tmp_path, monkeypatch):
    from command_center.providers import aviso_744
    monkeypatch.setenv("CC_WAIVERS_DIR", str(tmp_path / "w"))
    monkeypatch.delenv("CC_WAIVER_AVISO_744", raising=False)
    os.makedirs(tmp_path / "w" / "modelos", exist_ok=True)
    (tmp_path / "w" / "aviso-744.txt").write_text(AVISO_EXEMPLO + "\n", encoding="utf-8")
    a = aviso_744.aprovado()
    assert a["text"] == AVISO_EXEMPLO and a["sha256"] == CFG["sha256"] and a["path"].endswith("aviso-744.txt")
    assert aviso_744.conferir(_parental())["ok"] is True
    # a variável aponta para um arquivo que não existe: alguém quis configurar, então barra
    monkeypatch.setenv("CC_WAIVER_AVISO_744", str(tmp_path / "nao-existe.txt"))
    r = aviso_744.conferir(_parental())
    assert r["configured"] and r["ok"] is False and "não abre" in r["reason"]
    vazio = tmp_path / "vazio.txt"
    vazio.write_text("  \n", encoding="utf-8")
    monkeypatch.setenv("CC_WAIVER_AVISO_744", str(vazio))
    assert "vazio" in aviso_744.conferir(_parental())["reason"]


# ------------------------------------------------------------------ a tabela de versões
@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DB_PATH", str(tmp_path / "cc.sqlite"))
    c = conectar(); aplicar_schema(c)
    yield c
    c.close()


def _versao(con, **mais):
    return inserir(con, "waiver_template_versions", **{**dict(kind="parental", sha256="a" * 64, name="Parental (teste)",
                                                             pdf_path="/nao/existe.pdf", pages=1, imported_at="2026-01-01T00:00:00Z"),
                                                        **mais})


def test_a_versao_do_modelo_e_append_only(con):
    vid = _versao(con)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE waiver_template_versions SET text='outro' WHERE id=?", (vid,))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM waiver_template_versions WHERE id=?", (vid,))
    with pytest.raises(sqlite3.IntegrityError):
        _versao(con)                                              # o mesmo texto do mesmo tipo é a mesma versão
    _versao(con, kind="adult")
    assert um(con, "SELECT COUNT(*) AS n FROM waiver_template_versions")["n"] == 2


def test_a_trava_das_versoes_entra_a_cada_subida_e_se_atualiza(con):
    con.execute("DROP TRIGGER waiver_template_versions_no_delete")
    con.execute("DROP TRIGGER waiver_template_versions_no_update")
    con.execute("""CREATE TRIGGER waiver_template_versions_no_update BEFORE UPDATE OF text ON waiver_template_versions
                   BEGIN SELECT RAISE(ABORT, 'velha'); END""")
    aplicar_schema(con)
    aplicar_schema(con)
    for nome, sql in db._so_insert("waiver_template_versions").items():
        assert con.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (nome,)).fetchone()[0] == sql
    vid = _versao(con)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE waiver_template_versions SET name='x' WHERE id=?", (vid,))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM waiver_template_versions WHERE id=?", (vid,))


def test_o_modelo_importado_antes_das_versoes_vira_a_versao_dele(con, tmp_path):
    """Banco que já tinha o modelo no ponteiro (antes do #116): a subida cria a versão e aponta, uma vez."""
    pdf = tmp_path / "parental-antigo.pdf"
    pdf.write_bytes(PARENTAL)
    sha = hashlib.sha256(PARENTAL).hexdigest()
    con.execute("""INSERT INTO waiver_templates (kind, name, pdf_path, sha256, pages, text, source, imported_at, imported_by)
                   VALUES ('parental', 'Parental antigo', ?, ?, 1, 'PARENTAL CONSENT', 'docusign', '2026-01-02T00:00:00Z', NULL)""",
                (str(pdf), sha))
    aplicar_schema(con)
    aplicar_schema(con)
    vs = todos(con, "SELECT * FROM waiver_template_versions")
    assert len(vs) == 1 and vs[0]["sha256"] == sha and vs[0]["pdf_path"] == str(pdf) and vs[0]["imported_at"] == "2026-01-02T00:00:00Z"
    assert um(con, "SELECT version_id FROM waiver_templates WHERE kind='parental'")["version_id"] == vs[0]["id"]


# ------------------------------------------------------------------ reimportar não perde a anterior
class Docusign:
    """Só LEITURA de modelo, com o PDF de cada tipo trocável no meio do teste."""
    def __init__(self):
        self.pdf = {"adult": ADULT, "parental": PARENTAL}

    def modelo_humano(self, tid):
        tipo = next(k for k, v in wn.MODELOS.items() if v == tid)
        return {"nome": f"{tipo.title()} Waiver (teste)", "documentos": [{"documentId": "1"}]}

    def baixar_documento_do_modelo_humano(self, tid, did):
        return self.pdf[next(k for k, v in wn.MODELOS.items() if v == tid)]

    def __getattr__(self, nome):
        raise AssertionError(f"tocou no DocuSign além de ler o modelo: {nome}")


@pytest.fixture()
def ds(cli, monkeypatch):  # noqa: F811
    d = Docusign()
    monkeypatch.setattr(prov, "modulo", lambda nome: d if nome == "docusign" else None)
    monkeypatch.delenv("CC_WAIVER_AVISO_744", raising=False)
    return d


def _importa(cli, status=200):  # noqa: F811
    h = equipe(cli)
    r = cli.post(f"{S}/waiver-nativa/importar", headers=h)
    assert r.status_code == status, r.text
    return r


def test_reimportar_guarda_a_anterior_e_a_assinatura_antiga_acha_o_modelo_pelo_hash(cli, ds):  # noqa: F811
    liga(cli)
    hc, (pid,) = cliente(cli)
    w1 = um(conectar(), "SELECT * FROM waivers WHERE id=?", (assina(cli, hc, pid).json()["waiver_id"],))
    t1 = json.loads(w1["audit"])
    v1 = um(conectar(), "SELECT * FROM waiver_template_versions WHERE kind='parental'")
    assert t1["template_sha256"] == hashlib.sha256(PARENTAL).hexdigest() == v1["sha256"]
    assert t1["template_version_id"] == v1["id"]
    from command_center.tests.test_waiver_nativa import certificado
    assert f"Template version ID: {v1['id']}" in certificado(w1["pdf_path"])
    # o DocuSign mudou o texto do parental: reimportar acrescenta a versão 2 e aponta para ela
    ds.pdf["parental"] = _pdf("PARENTAL CONSENT, RELEASE AND WAIVER - second text (test)")
    _importa(cli)
    _importa(cli)                                                # o mesmo PDF de novo não cria outra versão
    equipe(cli, "ger@urace.us")
    vs = cli.get(f"{S}/waiver-nativa/versoes?kind=parental").json()
    assert vs["total"] == 2 and [v["number"] for v in vs["itens"]] == [2, 1]
    atual, antiga = vs["itens"]
    assert atual["current"] and not antiga["current"] and antiga["id"] == v1["id"] and antiga["signatures"] == 1
    assert cli.get(f"{S}/waiver-nativa/versoes").json()["total"] == 3, "adult 1 + parental 2"
    assert cli.get(f"{S}/waiver-nativa/versoes?limit=1&offset=1").json()["itens"][0]["number"] == 1
    # a versão 1 continua consultável: o PDF como foi importado, e a assinatura antiga acha pelo hash
    r = cli.get(f"{S}/waiver-nativa/versoes/{v1['id']}/pdf")
    assert r.status_code == 200 and r.content == PARENTAL and r.headers["x-content-sha256"] == v1["sha256"]
    achada = wn.versao_por_hash(conectar(), "parental", t1["template_sha256"])
    assert achada["id"] == v1["id"] and "PARENTAL CONSENT" in achada["text"]
    m = {x["kind"]: x for x in cli.get(f"{S}/waiver-nativa").json()["modelos"]}
    assert m["parental"]["version"] == 2 and m["parental"]["sha256"] == atual["sha256"]
    # a próxima assinatura usa a versão 2; a 1 continua com a dela
    hc2, (pid2,) = cliente(cli, conta={**CONTA, "email": "segunda@example.com"})
    w2 = um(conectar(), "SELECT audit FROM waivers WHERE id=?", (assina(cli, hc2, pid2).json()["waiver_id"],))
    assert json.loads(w2["audit"])["template_version_id"] == atual["id"]
    assert os.stat(achada["pdf_path"]).st_mode & 0o777 == 0o400, "o PDF da versão fica só leitura"


def test_o_pdf_da_versao_que_mudou_no_disco_nao_sai_e_reimportar_devolve_o_original(cli, ds):  # noqa: F811
    _importa(cli)
    equipe(cli, "ger@urace.us")
    v = cli.get(f"{S}/waiver-nativa/versoes?kind=parental").json()["itens"][0]
    caminho = wn.versao(conectar(), v["id"])["pdf_path"]
    os.chmod(caminho, 0o600)
    open(caminho, "ab").write(b"% mexido")
    assert cli.get(f"{S}/waiver-nativa/versoes/{v['id']}/pdf").status_code == 409
    feitos = {x["kind"]: x for x in _importa(cli).json()["modelos"]}
    assert feitos["parental"]["version"] == 1
    assert cli.get(f"{S}/waiver-nativa/versoes/{v['id']}/pdf").content == PARENTAL
    assert cli.get(f"{S}/waiver-nativa/versoes/999999/pdf").status_code == 404


def test_versoes_so_para_gerente(cli, ds):  # noqa: F811
    from command_center.api import auth
    from command_center.tests.test_waiver_nativa import SENHA
    _importa(cli)
    c = conectar()
    auth.criar_usuario(c, "op@urace.us", "Operador", "OPERATOR", SENHA)
    c.commit(); c.close()
    equipe(cli, "op@urace.us")
    assert cli.get(f"{S}/waiver-nativa/versoes").status_code == 403
    assert cli.get(f"{S}/waiver-nativa/versoes/1/pdf").status_code == 403


# ------------------------------------------------------------------ o aviso, de ponta a ponta
def _aprova(tmp_texto=AVISO_EXEMPLO):
    """Põe o texto aprovado no lugar padrão (a pasta das waivers do teste)."""
    with open(os.path.join(wn.pasta(), "aviso-744.txt"), "w", encoding="utf-8") as f:
        f.write(tmp_texto)


def test_sem_texto_aprovado_a_conferencia_so_informa_e_nada_e_barrado(cli, ds):  # noqa: F811
    liga(cli)                                                    # o parental de teste não tem aviso nenhum
    hc, (pid,) = cliente(cli)
    assert assina(cli, hc, pid).status_code == 201
    equipe(cli, "ger@urace.us")
    d = cli.get(f"{S}/waiver-nativa").json()["aviso_744"]
    assert d["configured"] is False and d["ok"] is None and d["path"].endswith("aviso-744.txt") and d["approved_text"] is None
    v = cli.get(f"{S}/waiver-nativa/versoes?kind=parental").json()["itens"][0]
    assert v["notice_744"]["configured"] is False
    assert cli.get(f"{S}/waiver-nativa/versoes?kind=adult").json()["itens"][0]["notice_744"] is None, "o aviso é só do parental"


def test_com_texto_aprovado_o_parental_sem_aviso_nao_entra_nao_liga_e_nao_assina(cli, ds):  # noqa: F811
    liga(cli)                                                    # ligada antes do texto aprovado, com o parental sem aviso
    _aprova()
    h = equipe(cli)
    d = cli.get(f"{S}/waiver-nativa").json()["aviso_744"]
    assert d["configured"] and d["ok"] is False and d["approved_text"] == AVISO_EXEMPLO
    # assinar a parental pela área do cliente: recusa antes de gastar o código; a adult continua
    hc, (pid,) = cliente(cli)
    r = assina(cli, hc, pid)
    assert r.status_code == 400 and "not available right now" in r.json()["detail"], r.text
    hc, _ = cliente(cli, conta={**CONTA, "email": "adulto@example.com", "i_am_driver": True}, pilotos=())
    pid = next(x["id"] for x in cli.get("/ops/api/portal/me").json()["drivers"] if x["is_self"])
    assert assina(cli, hc, pid).status_code == 201
    # religar: recusa com o motivo
    h = equipe(cli)
    assert cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": False}, headers=h).status_code == 200
    r = cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=h)
    assert r.status_code == 409 and "§744.301(3)" in r.json()["detail"]
    # reimportar um parental sem o aviso: nada entra, nem o adult novo
    ds.pdf = {"adult": _pdf("ADULT - second text (test)"), "parental": _parental(pt_aviso=10)}
    antes = cli.get(f"{S}/waiver-nativa/versoes").json()["total"]
    r = _importa(cli, 409)
    assert "não tem 5 pt a mais" in r.json()["detail"] and "continuam valendo" in r.json()["detail"]
    assert cli.get(f"{S}/waiver-nativa/versoes").json()["total"] == antes
    # o parental com o aviso certo entra, liga e assina; a trilha guarda a conferência
    ds.pdf["parental"] = _parental()
    feitos = {x["kind"]: x for x in _importa(cli).json()["modelos"]}
    assert feitos["parental"]["version"] == 2
    v = cli.get(f"{S}/waiver-nativa/versoes?kind=parental").json()["itens"][0]
    assert v["current"] and v["notice_744"]["ok"] is True and v["notice_744"]["approved_sha256"] == CFG["sha256"]
    h = equipe(cli)
    assert cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=h).status_code == 200
    hc, (pid,) = cliente(cli, conta={**CONTA, "email": "mae@example.com"})
    r = assina(cli, hc, pid)
    assert r.status_code == 201, r.text
    t = json.loads(um(conectar(), "SELECT audit FROM waivers WHERE id=?", (r.json()["waiver_id"],))["audit"])
    assert t["notice_744_check"] == {"configured": True, "ok": True, "approved_sha256": CFG["sha256"], "notice_pt": 15, "body_pt": 10}


def test_pelo_convite_a_parental_sem_aviso_tambem_nao_se_assina(cli, ds):  # noqa: F811
    from command_center.tests import test_convite_waiver as tc
    liga(cli)
    _aprova()
    cid = tc.card()                                              # piloto menor: o responsável assina a parental
    h = equipe(cli)
    assert tc.manda(cli, h, cid, "maria@example.com").status_code == 201
    r = tc.assina(cli, tc.token_do_email("maria@example.com"), relationship="mother", guardian_declaration=True)
    assert r.status_code == 400 and "not available right now" in r.json()["detail"], r.text
    assert not um(conectar(), "SELECT 1 AS x FROM waivers WHERE source='urace'")


# ------------------------------------------------------------------ revisão do PR #328
@pytest.mark.parametrize("importado", [False, True])
def test_arquivo_vazio_o_quadro_diz_que_esta_vazio_com_ou_sem_o_parental_importado(cli, ds, importado):  # noqa: F811
    """Produção hoje: 0 modelos. Se alguém criar o arquivo do aviso vazio, o quadro diz isso (e não só que falta o
    modelo), e importar e ligar continuam barrados."""
    if importado:
        _importa(cli)
    _aprova("")
    equipe(cli, "ger@urace.us")
    a = cli.get(f"{S}/waiver-nativa").json()["aviso_744"]
    assert a["configured"] is True and a["ok"] is False and "está vazio" in a["reason"], a
    assert "está vazio" in _importa(cli, 409).json()["detail"]
    r = cli.post(f"{S}/waiver-nativa/ligar", json={"ligada": True}, headers=equipe(cli))
    assert r.status_code == 409


@pytest.mark.parametrize("tabela,linha", [
    ("waiver_template_versions", dict(kind="parental", sha256="a" * 64, name="Parental (teste)", pdf_path="/nao/existe.pdf",
                                      imported_at="2026-01-01T00:00:00Z")),
    ("waiver_voids", dict(waiver_id=None, by_name="Gerente", reason="assinada por engano no teste")),
    ("audit_logs", dict(actor="system", event="teste")),
])
def test_insert_or_replace_nao_passa_pela_trava_append_only(con, tabela, linha):
    """Com `recursive_triggers` desligado, o REPLACE apagava a linha em conflito sem disparar o trigger de DELETE e
    trocava o registro. Agora o banco recusa; o INSERT OR IGNORE continua só não fazendo nada."""
    if tabela == "waiver_voids":
        from command_center.tests.test_waiver_imutavel import nativa
        linha = {**linha, "waiver_id": nativa(con)}
    lid = inserir(con, tabela, **linha)
    antes = um(con, f"SELECT * FROM {tabela} WHERE id=?", (lid,))
    campos = {**linha, "id": lid}
    sql = f"({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})"
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute(f"INSERT OR REPLACE INTO {tabela} {sql}", tuple(campos.values()))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute(f"REPLACE INTO {tabela} {sql}", tuple(campos.values()))
    con.execute(f"INSERT OR IGNORE INTO {tabela} {sql}", tuple(campos.values()))
    assert um(con, f"SELECT * FROM {tabela} WHERE id=?", (lid,)) == antes
    assert con.execute("PRAGMA recursive_triggers").fetchone()[0] == 1


def test_o_replace_das_tabelas_sem_trava_continua_igual(con):
    """As tabelas onde o código usa INSERT OR REPLACE não têm trigger de DELETE: nada muda para elas."""
    gatilhos = {r[0] for r in con.execute("SELECT tbl_name FROM sqlite_master WHERE type='trigger' AND sql LIKE '%BEFORE DELETE%'")}
    assert not gatilhos & {"vault_unlocks", "qbo_items", "action_policies"}
    for _ in range(2):
        con.execute("INSERT OR REPLACE INTO qbo_items (id, name, full_name, price, type, active) VALUES ('t1','X','X',1,'Service',1)")
    assert um(con, "SELECT COUNT(*) AS n FROM qbo_items WHERE id='t1'")["n"] == 1


def test_com_recursive_triggers_ligado_todo_trigger_so_recusa(con):
    """`recursive_triggers` é global: todo trigger do schema só faz RAISE (nenhum escreve, então não há recursão) e
    nenhuma FK tem ação (CASCADE/SET NULL). Trigger novo que escreva, ou FK com ação, tem de ser pensado de novo."""
    import re
    for nome, sql in con.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'"):
        corpo = sql.split("BEGIN", 1)[1]
        assert re.fullmatch(r"\s*SELECT RAISE\(ABORT, '[^']*'\);\s*END\s*", corpo), (nome, sql)
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for fk in con.execute(f"PRAGMA foreign_key_list({t})").fetchall():
            assert (fk[5], fk[6]) == ("NO ACTION", "NO ACTION"), (t, tuple(fk))
