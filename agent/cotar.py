#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cotar.py — a régua da U-RACE. Devolve o número, não confia na cabeça.

Porta do cotar.py da AZ (ver PROMPT_MAC_COTAR.md, seção 8: "a conta é do
script, nunca da cabeça"). Fonte da tabela: prompts/PLAYBOOK_COMERCIAL.md,
seção "Tabela de preço (Rate Card Oficial 2026)". Se o preço mudar lá,
muda aqui também no mesmo commit.

USO
  python agent/cotar.py <produto> <dias> [--fds]        # Arrive and Drive
  python agent/cotar.py academy <plano> [meses] [--contrato 6|12] [--extra N]
  python agent/cotar.py --tabela [dias]                  # tudo, N dias

⛔ NÃO inventa imposto, NÃO inventa desconto avulso, NÃO soma a track fee
   no preço do produto — ela é SEMPRE linha separada, paga direto ao OKC.
⛔ Last-minute deals (US$ 245–395): só o operador na pista libera. Este
   script recusa a cotar isso por SMS/e-mail — não existe atalho aqui.
"""
from __future__ import annotations

import sys

# produto -> (rótulo, preço/dia, exigência)
ARRIVE = {
    'proprio':  ('Kart próprio (Arrive and Drive)', 500, '4+ anos'),
    'baby':     ('Baby Kart',                        719, '4-7 anos'),
    'arrive4t': ('Arrive and Drive 4-stroke',        719, '7+ anos'),
    'arrive2t': ('Arrive and Drive 2-stroke',        819, '7+ anos'),
    'shifter':  ('Adult Shifter',                    899, '14+, SÓ com experiência'),
}

# plano -> (rótulo, mensal (4 sessões/mês), sessão extra, exigência)
ACADEMY = {
    'proprio_mecanico': ('Academy — kart próprio + leva mecânico', 1200.00, 300.00, '4+ anos'),
    'proprio':          ('Academy — kart próprio',                 1800.00, 450.00, '4+ anos'),
    'baby4t':           ('Academy — Baby Kart / 4-stroke',        2756.90, 689.23, '4-7 ou 7+ anos'),
    '2stroke':          ('Academy — 2-stroke',                    3156.90, 789.23, '7+ anos'),
}

TRACK_FEE = {'util': 90, 'fds': 65, 'spectator': 5}
CONTRATO_DESCONTO = {6: 0.04, 12: 0.08}  # só parcelado, só se o Lucas oferecer

SOB_CONSULTA = {
    'last_minute': 'Last-minute deal (US$ 245-395) - SO o operador na pista libera. Nunca cotar por SMS/e-mail.',
    'coaching':    'Professional Coaching / Lead and Follow - fechado com antecedencia, NAO tem preco de tabela.',
    'support':     'Race Support - sob consulta.',
}


def fmt(v: float) -> str:
    return format(v, ',.2f') if v != int(v) else format(int(v), ',d')


def linha_arrive(k: str, dias: int) -> float:
    rot, preco, exig = ARRIVE[k]
    total = preco * dias
    print('%-32s %2d dia%s x US$ %s  =  US$ %s' % (
        rot, dias, '' if dias == 1 else 's', fmt(preco), fmt(total)))
    print('   exigência: %s' % exig)
    return total


def linha_academy(k: str, meses: int = 1, contrato: int | None = None, extra: int = 0) -> float:
    rot, mensal, sessao_extra, exig = ACADEMY[k]
    bruto = mensal * meses
    total = bruto
    desconto = 0.0
    if contrato in CONTRATO_DESCONTO:
        desconto = bruto * CONTRATO_DESCONTO[contrato]
        total -= desconto
    print('%-32s %2d mês%s x US$ %s  =  US$ %s' % (
        rot, meses, '' if meses == 1 else 'es', fmt(mensal), fmt(bruto)))
    if contrato:
        print('   contrato %d meses: -%d%% (parcelado) = -US$ %s  ->  US$ %s' % (
            contrato, int(CONTRATO_DESCONTO[contrato] * 100), fmt(desconto), fmt(total)))
    if extra:
        extra_total = sessao_extra * extra
        total += extra_total
        print('   + %d sessão(ões) extra x US$ %s  =  US$ %s' % (extra, fmt(sessao_extra), fmt(extra_total)))
    print('   exigência: %s' % exig)
    print('   SEM CONTRATO por padrão. 6 meses = 4% off, 12 meses = 8% off (só se o Lucas oferecer).')
    return total


def rodape_track_fee(dias: int = 1, fds: bool = False) -> None:
    fee = TRACK_FEE['fds'] if fds else TRACK_FEE['util']
    print()
    print('  + TRACK FEE DO OKC: US$ %d/dia (%s), NÃO INCLUSA, paga direto à pista.'
          % (fee, 'sáb-dom' if fds else 'seg-sex'))
    print('    total estimado: ~US$ %s (%d dia%s). + US$ %d por acompanhante/dia.'
          % (fmt(fee * dias), dias, '' if dias == 1 else 's', TRACK_FEE['spectator']))
    print('  ? IMPOSTO: não confirmado se já está dentro do preço. Não somar. Perguntar ao Lucas.')
    print('  ? DESCONTO fora do contrato Academy: não existe régua. Só o Lucas dá. Nunca oferecer.')
    print('  >> quem fecha, marca sessão, manda waiver e fala de dinheiro é o Lucas/Italo.')


def _parse_academy_args(rest: list[str]) -> tuple[int, int | None, int]:
    meses, contrato, extra = 1, None, 0
    i = 0
    while i < len(rest):
        if rest[i] == '--contrato':
            contrato = int(rest[i + 1]); i += 2
        elif rest[i] == '--extra':
            extra = int(rest[i + 1]); i += 2
        else:
            meses = int(rest[i]); i += 1
    return meses, contrato, extra


def main(a: list[str]) -> None:
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return

    if a[0] == '--tabela':
        dias = int(a[1]) if len(a) > 1 else 1
        for k in ARRIVE:
            linha_arrive(k, dias)
        print()
        for k in ACADEMY:
            linha_academy(k)
        rodape_track_fee(dias)
        return

    if a[0] == 'academy':
        if len(a) < 2 or a[1] not in ACADEMY:
            print('plano de academy inválido. válidos: ' + ', '.join(ACADEMY)); return
        plano = a[1]
        meses, contrato, extra = _parse_academy_args(a[2:])
        linha_academy(plano, meses, contrato, extra)
        rodape_track_fee(1)
        return

    k = a[0].lower()
    if k in SOB_CONSULTA:
        print('SEM PREÇO DE TABELA: ' + SOB_CONSULTA[k])
        print('  >> não cotar. Passar pro Lucas.'); return
    if k not in ARRIVE:
        print('produto desconhecido: %s' % k)
        print('válidos: ' + ', '.join(list(ARRIVE) + ['academy'] + list(SOB_CONSULTA))); return
    dias = int(a[1]) if len(a) > 1 and not a[1].startswith('--') else 1
    fds = '--fds' in a
    total = linha_arrive(k, dias)
    rodape_track_fee(dias, fds)


def _self_test() -> None:
    """No I/O de rede — só confere que a régua não mudou por engano."""
    checks = 0

    assert ARRIVE['arrive4t'][1] == 719 and ARRIVE['arrive2t'][1] == 819
    assert ARRIVE['baby'][1] == 719 and ARRIVE['shifter'][1] == 899
    assert ARRIVE['proprio'][1] == 500
    checks += 1

    assert ACADEMY['baby4t'][1] == 2756.90 and round(ACADEMY['baby4t'][2], 2) == 689.23
    assert ACADEMY['2stroke'][1] == 3156.90 and round(ACADEMY['2stroke'][2], 2) == 789.23
    checks += 1

    assert TRACK_FEE == {'util': 90, 'fds': 65, 'spectator': 5}
    checks += 1

    assert 'last_minute' in SOB_CONSULTA
    checks += 1

    print(f"cotar --self-test: {checks}/4 OK")


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        _self_test()
    else:
        main(sys.argv[1:])
