"""O e-mail com a identidade da URACE (#305).

Dono, 16/10: *"a pessoa recebe o um e-mail com a nossa identidade, da Erase"*. Um desenho só para os e-mails ao
cliente: faixa preta com a marca, cartão branco, botão vermelho e o rodapé com endereço e telefone. Estilo inline
(é o que os programas de e-mail respeitam), sem imagem de fora (a marca é texto: abre igual com imagem bloqueada).
Todo texto passa por escape: nada que a pessoa digitou vira HTML.
"""
from html import escape as e

PRETO, VERMELHO, PAPEL, TINTA, CINZA = "#0b0b0f", "#d91617", "#f4f4f6", "#121217", "#5b5c6e"
FONTE = "Helvetica, Arial, sans-serif"


def _rodape():
    from command_center.vitrine import conteudo as C
    end = C.SITE["endereco"]
    return (f'{e(end["rua"])}, {e(end["cidade"])}, {e(end["estado"])} {e(end["cep"])}<br>'
            f'{e(C.SITE["telefone"])} · <a href="https://urace.us" style="color:{CINZA}">urace.us</a>')


def html(titulo, paragrafos=(), linhas=(), botao=None, depois=(), lang="en"):
    """`linhas`: [(rótulo, valor)] num quadro (login, senha, número de cliente). `botao`: (texto, link)."""
    ps = "".join(f'<p style="margin:0 0 14px;font:16px/1.55 {FONTE};color:{TINTA}">{e(p)}</p>' for p in paragrafos)
    quadro = ""
    if linhas:
        tr = "".join(f'<tr><td style="padding:8px 12px;font:14px {FONTE};color:{CINZA};white-space:nowrap">{e(r)}</td>'
                     f'<td style="padding:8px 12px;font:bold 15px {FONTE};color:{TINTA};word-break:break-all">{e(v)}</td></tr>'
                     for r, v in linhas)
        quadro = (f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
                  f'style="background:{PAPEL};border-radius:10px;margin:4px 0 18px">{tr}</table>')
    bt = ""
    if botao:
        bt = (f'<p style="margin:6px 0 20px"><a href="{e(botao[1])}" style="display:inline-block;background:{VERMELHO};color:#fff;'
              f'text-decoration:none;font:bold 16px {FONTE};padding:14px 26px;border-radius:8px">{e(botao[0])}</a></p>')
    fim = "".join(f'<p style="margin:0 0 10px;font:14px/1.5 {FONTE};color:{CINZA}">{e(p)}</p>' for p in depois)
    return f"""<!doctype html>
<html lang="{"pt-BR" if lang == "pt" else "en"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titulo)}</title></head>
<body style="margin:0;padding:0;background:{PAPEL}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPEL}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="background:{PRETO};border-radius:12px 12px 0 0;padding:20px 24px">
  <span style="font:900 26px {FONTE};letter-spacing:1px;color:{VERMELHO}">U</span><span style="font:900 26px {FONTE};letter-spacing:1px;color:#fff">RACE</span>
  <span style="font:12px {FONTE};color:#a6a7b8;padding-left:8px">the Champion's Factory</span></td></tr>
<tr><td style="background:#fff;border-radius:0 0 12px 12px;padding:28px 24px">
  <h1 style="margin:0 0 16px;font:bold 22px/1.25 {FONTE};color:{TINTA}">{e(titulo)}</h1>
  {ps}{quadro}{bt}{fim}
</td></tr>
<tr><td style="padding:16px 8px;text-align:center;font:12px/1.6 {FONTE};color:{CINZA}">{_rodape()}</td></tr>
</table></td></tr></table></body></html>"""
