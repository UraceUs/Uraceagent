"""Agenda de sessões (#41): o que está aberto, o que está bloqueado, quem marcou.

Dono, 30/09: *"o próprio cliente consiga ver os dias que tem disponível e agendar a sua
sessão; a gente consiga parametrizar: bloquear esse dia toda semana, bloquear datas
específicas, bloquear período; alguns dias são só pela manhã, outros só pela tarde, tem
dias que é o dia todo"*.

O modelo é pequeno de propósito:
- a **semana** diz, para cada dia e cada período (manhã, tarde), se abre e quantas vagas
  tem. "Bloquear esse dia toda semana" é fechar os dois períodos daquele dia;
- **bloqueios** tiram de uma data ou de um intervalo de datas a manhã, a tarde ou o dia
  todo, com motivo. Desbloquear não apaga: o bloqueio fica inativo, com quem e quando.
  O bloqueio **recorrente** (#52) vale só num dia da semana ("toda segunda");
- **dia todo** é manhã + tarde: só abre se as duas estão abertas e com vaga, e ocupa as duas;
- a **antecedência mínima** conta até o início do período; o **horizonte** é até quantos
  dias à frente o cliente enxerga. Tudo no relógio da Flórida.

Nada abre sozinho: sem regra da equipe, a agenda aparece fechada (NO FAKE DATA).
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import servicos_site

FUSO = ZoneInfo("America/New_York")
PERIODOS = ("manha", "tarde")
ATIVAS = ("pendente", "confirmada")
DIAS_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


class ErroAgenda(ValueError):
    pass


def _agora_fl():
    return datetime.now(FUSO)


def _hora(h):
    try:
        hh, mm = [int(x) for x in str(h).split(":")[:2]]
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    except ValueError:
        pass
    raise ErroAgenda(f"horário inválido: {h}")


# ------------------------------------------------------------------ configuração
def config(con):
    c = um(con, "SELECT * FROM booking_config WHERE id=1")
    if not c:
        con.execute("INSERT OR IGNORE INTO booking_config (id) VALUES (1)")
        c = um(con, "SELECT * FROM booking_config WHERE id=1")
    return dict(c)


def mudar_config(con, por, **d):
    config(con)
    mud = {}
    for k in ("morning_start", "morning_end", "afternoon_start", "afternoon_end"):
        if k in d and d[k] is not None:
            mud[k] = _hora(d[k])
    if "auto_confirm" in d and d["auto_confirm"] is not None:
        mud["auto_confirm"] = 1 if d["auto_confirm"] else 0
    for k, (mi, ma) in (("horizon_days", (1, 365)), ("min_notice_hours", (0, 24 * 30))):
        if k in d and d[k] is not None:
            v = int(d[k])
            if not mi <= v <= ma:
                raise ErroAgenda(f"{k} fora do limite ({mi}–{ma})")
            mud[k] = v
    novo = {**config(con), **mud}
    if not (novo["morning_start"] < novo["morning_end"] <= novo["afternoon_start"] < novo["afternoon_end"]):
        raise ErroAgenda("os horários não fecham: a manhã tem de terminar antes (ou quando) a tarde começa")
    if mud:
        atualizar(con, "booking_config", 1, **mud, updated_by=por, updated_at=agora())
    return config(con)


def semana(con):
    regras = {(r["weekday"], r["period"]): r for r in todos(con, "SELECT * FROM booking_weekly")}
    return [{"weekday": d, "dia": DIAS_PT[d], "period": p, "open": bool(regras.get((d, p), {}).get("open")),
             "capacity": regras.get((d, p), {}).get("capacity") or 1} for d in range(7) for p in PERIODOS]


def mudar_semana(con, regras):
    for r in regras:
        d, p = int(r["weekday"]), r["period"]
        if not 0 <= d <= 6 or p not in PERIODOS:
            raise ErroAgenda("dia ou período inválido")
        cap = int(r.get("capacity") or 1)
        if not 1 <= cap <= 50:
            raise ErroAgenda("capacidade entre 1 e 50")
        con.execute("""INSERT INTO booking_weekly (weekday, period, open, capacity) VALUES (?,?,?,?)
                       ON CONFLICT(weekday, period) DO UPDATE SET open=excluded.open, capacity=excluded.capacity""",
                    (d, p, 1 if r.get("open") else 0, cap))
    return semana(con)


# ------------------------------------------------------------------ bloqueios
def bloqueios(con, ativos=True):
    sql = "SELECT * FROM booking_blocks" + (" WHERE active=1" if ativos else "") + " ORDER BY date_from DESC, id DESC"
    return [dict(b) for b in todos(con, sql)]


SEM_FIM = "9999-12-31"


def bloquear(con, por, date_from=None, date_to=None, period="dia", reason=None, weekday=None):
    """Bloqueio de uma data, de um intervalo, ou **recorrente** (#52): `weekday` (0=segunda)
    bloqueia só aquele dia da semana, de `date_from` (padrão: hoje) até `date_to` (padrão:
    sem fim)."""
    if weekday is not None:
        if not 0 <= int(weekday) <= 6:
            raise ErroAgenda("dia da semana inválido")
        date_from = date_from or _agora_fl().date().isoformat()
        date_to = date_to or SEM_FIM
    try:
        a, b = date.fromisoformat(date_from), date.fromisoformat(date_to or date_from)
    except (TypeError, ValueError):
        raise ErroAgenda("data inválida (AAAA-MM-DD)")
    if b < a:
        raise ErroAgenda("o fim do bloqueio vem antes do começo")
    if weekday is None and (b - a).days > 366:
        raise ErroAgenda("bloqueio de mais de um ano: use o bloqueio recorrente (toda semana) em vez disso")
    if period not in ("dia", "manha", "tarde"):
        raise ErroAgenda("período inválido")
    return inserir(con, "booking_blocks", date_from=a.isoformat(), date_to=b.isoformat(), period=period,
                   reason=(reason or "").strip()[:200] or None, created_by=por,
                   weekday=int(weekday) if weekday is not None else None)


def _bloqueia(b, iso, dia_semana, periodo):
    return (b["date_from"] <= iso <= b["date_to"] and b["period"] in ("dia", periodo)
            and (b["weekday"] is None or b["weekday"] == dia_semana))


def desbloquear(con, por, bid):
    b = um(con, "SELECT active FROM booking_blocks WHERE id=?", (bid,))
    if not b:
        raise ErroAgenda("bloqueio não existe")
    if b["active"]:
        atualizar(con, "booking_blocks", bid, active=0, removed_by=por, removed_at=agora())


# ------------------------------------------------------------------ disponibilidade
def _ocupacao(con, de, ate):
    """{(data, período): vagas usadas}; o dia todo ocupa as duas."""
    uso = {}
    for b in todos(con, "SELECT date, period FROM bookings WHERE date BETWEEN ? AND ? AND status IN ('pendente','confirmada')",
                   (de.isoformat(), ate.isoformat())):
        for p in (PERIODOS if b["period"] == "dia" else (b["period"],)):
            uso[(b["date"], p)] = uso.get((b["date"], p), 0) + 1
    return uso


def _inicio(cfg, dia, periodo):
    h = cfg["morning_start"] if periodo in ("manha", "dia") else cfg["afternoon_start"]
    hh, mm = [int(x) for x in h.split(":")]
    return datetime(dia.year, dia.month, dia.day, hh, mm, tzinfo=FUSO)


def disponibilidade(con, de=None, ate=None, visao="cliente"):
    """Dia a dia: para cada período, se abre, quantas vagas sobram e por que não.
    `visao="cliente"` corta no horizonte e na antecedência; a equipe vê tudo."""
    cfg = config(con)
    agora_ = _agora_fl()
    hoje = agora_.date()
    de = de or hoje
    ate = ate or (hoje + timedelta(days=cfg["horizon_days"]))
    if visao == "cliente":
        de, ate = max(de, hoje), min(ate, hoje + timedelta(days=cfg["horizon_days"]))
    if ate < de:
        return {"config": _publica(cfg), "dias": []}
    if (ate - de).days > 400:
        raise ErroAgenda("intervalo grande demais")
    regras = {(r["weekday"], r["period"]): r for r in todos(con, "SELECT * FROM booking_weekly")}
    blocos = todos(con, "SELECT * FROM booking_blocks WHERE active=1 AND date_to>=? AND date_from<=?", (de.isoformat(), ate.isoformat()))
    uso = _ocupacao(con, de, ate)
    dias = []
    d = de
    while d <= ate:
        iso = d.isoformat()
        periodos = {}
        for p in PERIODOS:
            r = regras.get((d.weekday(), p))
            motivo, livres = None, 0
            if not r or not r["open"]:
                motivo = "fechado"
            else:
                bl = next((b for b in blocos if _bloqueia(b, iso, d.weekday(), p)), None)
                if bl:
                    motivo = "bloqueado" + (f": {bl['reason']}" if bl["reason"] and visao != "cliente" else "")
                elif visao == "cliente" and _inicio(cfg, d, p) - agora_ < timedelta(hours=cfg["min_notice_hours"]):
                    motivo = "antecedência"
                else:
                    livres = max(0, r["capacity"] - uso.get((iso, p), 0))
                    if not livres:
                        motivo = "lotado"
            periodos[p] = {"open": motivo is None, "spots": livres, "reason": motivo,
                           "capacity": r["capacity"] if r else 0, "used": uso.get((iso, p), 0)}
        periodos["dia"] = {"open": periodos["manha"]["open"] and periodos["tarde"]["open"],
                           "spots": min(periodos["manha"]["spots"], periodos["tarde"]["spots"])}
        dias.append({"date": iso, "weekday": d.weekday(), "periods": periodos,
                     "any_open": any(periodos[p]["open"] for p in PERIODOS)})
        d += timedelta(days=1)
    return {"config": _publica(cfg), "dias": dias}


def _publica(cfg):
    return {k: cfg[k] for k in ("morning_start", "morning_end", "afternoon_start", "afternoon_end",
                                "horizon_days", "min_notice_hours", "auto_confirm")}


# ------------------------------------------------------------------ agendamentos
def agendar(con, conta_id, data_iso, periodo, piloto_id=None, notes=None, servico_id=None):
    """O cliente marca um serviço, para um piloto da conta, num período aberto. O preço
    do serviço fica gravado no agendamento (#50): mudar a tabela depois não muda isso."""
    try:
        servico = servicos_site.do_agendamento(con, servico_id)
    except servicos_site.ErroServico as e:
        raise ErroAgenda(str(e))
    if piloto_id is None:
        raise ErroAgenda("Choose the driver for this session.")
    if periodo not in ("dia", "manha", "tarde"):
        raise ErroAgenda("Choose morning, afternoon or full day.")
    try:
        dia = date.fromisoformat(data_iso)
    except (TypeError, ValueError):
        raise ErroAgenda("Choose a valid date.")
    if not um(con, "SELECT 1 AS x FROM portal_pilots WHERE id=? AND account_id=? AND active=1", (piloto_id, conta_id)):
        raise ErroAgenda("Driver not found on your account.")
    from command_center.providers import portal            # import aqui: portal não depende da agenda
    falta = portal.pode_marcar(con, conta_id, piloto_id)
    if falta:
        raise ErroAgenda(falta)
    disp = disponibilidade(con, dia, dia)["dias"]
    if not disp or not disp[0]["periods"][periodo]["open"]:
        raise ErroAgenda("This time is no longer available. Please pick another one.")
    ja = um(con, """SELECT 1 AS x FROM bookings WHERE account_id=? AND date=? AND status IN ('pendente','confirmada')
                     AND COALESCE(pilot_id,0)=COALESCE(?,0) AND (period=? OR period='dia' OR ?='dia')""",
            (conta_id, data_iso, piloto_id, periodo, periodo))
    if ja:
        raise ErroAgenda("This driver already has a session at this time.")
    status = "confirmada" if config(con)["auto_confirm"] else "pendente"
    return inserir(con, "bookings", account_id=conta_id, pilot_id=piloto_id, date=data_iso, period=periodo,
                   status=status, notes=(notes or "").strip()[:500] or None,
                   service_id=servico["id"], service_name=servico["name"], price=servico["price"],
                   decided_at=agora() if status == "confirmada" else None)


def _booking(con, bid):
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b:
        raise ErroAgenda("agendamento não existe")
    return b


def decidir(con, por, bid, decisao, nota=None):
    b = _booking(con, bid)
    novo = {"confirmar": "confirmada", "recusar": "recusada", "cancelar": "cancelada"}.get(decisao)
    if not novo:
        raise ErroAgenda("decisão inválida")
    permitido = {"confirmada": ("pendente",), "recusada": ("pendente",), "cancelada": ("pendente", "confirmada")}
    if b["status"] not in permitido[novo]:
        raise ErroAgenda(f"o agendamento está {b['status']}")
    atualizar(con, "bookings", bid, status=novo, decided_by=por, decided_at=agora(),
              decision_note=(nota or "").strip()[:300] or None, updated_at=agora(),
              **({"cancelled_by": "equipe"} if novo == "cancelada" else {}))
    return novo


def cancelar_pelo_cliente(con, conta_id, bid):
    b = um(con, "SELECT * FROM bookings WHERE id=? AND account_id=?", (bid, conta_id))
    if not b:
        raise ErroAgenda("Session not found.")
    if b["status"] not in ATIVAS:
        raise ErroAgenda("This session is already closed.")
    if _inicio(config(con), date.fromisoformat(b["date"]), b["period"]) <= _agora_fl():
        raise ErroAgenda("This session has already started. Please call us.")
    atualizar(con, "bookings", bid, status="cancelada", cancelled_by="cliente", updated_at=agora())


def do_cliente(con, conta_id):
    return [dict(b) for b in todos(con, """SELECT b.id, b.date, b.period, b.status, b.notes, b.decision_note, b.created_at,
                                                 b.service_name AS service, b.price, p.name AS driver FROM bookings b LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                                            WHERE b.account_id=? ORDER BY b.date DESC, b.id DESC LIMIT 100""", (conta_id,))]


def lista(con, status=None, de=None, ate=None):
    from command_center.providers.contrato import CARD_DO_AGENDAMENTO
    sql = f"""SELECT b.*, a.name AS account_name, a.email AS account_email, a.phone AS account_phone,
                    {CARD_DO_AGENDAMENTO} AS client_id, p.name AS driver, p.birth_date AS driver_birth
               FROM bookings b JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
              WHERE 1=1"""
    par = []
    if status:
        sql += " AND b.status=?"; par.append(status)
    if de:
        sql += " AND b.date>=?"; par.append(de)
    if ate:
        sql += " AND b.date<=?"; par.append(ate)
    return [dict(b) for b in todos(con, sql + " ORDER BY b.date, CASE b.period WHEN 'manha' THEN 0 WHEN 'dia' THEN 0 ELSE 1 END, b.id LIMIT 500", par)]
