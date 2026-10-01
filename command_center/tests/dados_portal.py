"""Dados completos da área do cliente (#54), para os testes que não são sobre validação:
o responsável com telefone e endereço, e o piloto com as medidas e a experiência."""
ENDERECO = {"phone": "(407) 555-0142", "address_line1": "100 Main St", "city": "Orlando", "state": "FL", "zip": "32809"}
MEDIDAS = {"height_in": 60, "weight_lb": 110, "chest_in": 30, "waist_in": 26, "hips_in": 30}
PILOTO = {"birth_date": "2014-05-01", "measures": MEDIDAS, "notes": "Two seasons in Mini kart."}


def piloto(nome, **mais):
    """Corpo do POST /drivers com tudo o que é obrigatório."""
    return {"name": nome, **PILOTO, **mais}


def completa(con, conta_id, piloto_id=None):
    """Completa no banco uma conta (e um piloto) criados direto, sem passar pela API."""
    import json

    from command_center.db import agora
    con.execute("UPDATE portal_accounts SET phone=?, address_line1=?, city=?, state=?, zip=? WHERE id=?",
                (ENDERECO["phone"], ENDERECO["address_line1"], ENDERECO["city"], ENDERECO["state"], ENDERECO["zip"], conta_id))
    if piloto_id:
        con.execute("""UPDATE portal_pilots SET birth_date=COALESCE(birth_date, ?), measures=?, measures_updated_at=?,
                       notes=COALESCE(notes, ?) WHERE id=?""",
                    (PILOTO["birth_date"], json.dumps(MEDIDAS), agora(), PILOTO["notes"], piloto_id))
