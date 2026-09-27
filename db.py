"""
db.py — camada de acesso ao Supabase para o Agenda DevOps.

Todas as funções aqui assumem que st.secrets (ou variáveis de ambiente)
já contêm SUPABASE_URL e SUPABASE_KEY. Ver README.md para configuração.
"""
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo

from supabase import create_client, Client


def get_client(url: str, key: str) -> Client:
    return create_client(url, key)


# ---------- daily_plans ----------

def get_or_create_daily_plan(client: Client, plan_date: date) -> dict:
    """Busca o plano do dia informado; cria um novo (vazio) se não existir."""
    resp = (
        client.table("daily_plans")
        .select("*")
        .eq("plan_date", plan_date.isoformat())
        .execute()
    )
    if resp.data:
        return resp.data[0]

    insert_resp = (
        client.table("daily_plans")
        .insert({"plan_date": plan_date.isoformat()})
        .execute()
    )
    return insert_resp.data[0]


def update_daily_plan_metrics(
    client: Client,
    plan_id: str,
    cognitive_load: int | None,
    lead_time_avg_hours: float | None,
    bottleneck_notes: str | None,
) -> None:
    client.table("daily_plans").update(
        {
            "cognitive_load": cognitive_load,
            "lead_time_avg_hours": lead_time_avg_hours,
            "bottleneck_notes": bottleneck_notes,
        }
    ).eq("id", plan_id).execute()


# ---------- tasks ----------

def get_week_meetings(client: Client, reference_date) -> list[dict]:
    """Reuniões de calendário aceitas e com outros participantes (exclui
    blocos pessoais tipo "Lunch") dentro da semana (segunda a domingo) que
    contém reference_date."""
    start_of_week = reference_date - timedelta(days=reference_date.weekday())
    end_of_week = start_of_week + timedelta(days=7)
    resp = (
        client.table("tasks")
        .select("title, start_time")
        .eq("source", "google_calendar")
        .eq("rsvp_status", "accepted")
        .eq("has_attendees", True)
        .gte("start_time", start_of_week.isoformat())
        .lt("start_time", end_of_week.isoformat())
        .execute()
    )
    return resp.data


def get_tasks_for_plan(client: Client, plan_id: str) -> list[dict]:
    resp = (
        client.table("tasks")
        .select("*")
        .eq("daily_plan_id", plan_id)
        .order("start_time", desc=False)
        .execute()
    )
    return resp.data


def add_task(
    client: Client,
    plan_id: str,
    title: str,
    stage: str,
    status: str = "Planned",
    start_time: datetime | None = None,
    finish_time: datetime | None = None,
    is_top_priority: bool = False,
    goal_id: str | None = None,
    long_term_goal_id: str | None = None,
    source: str = "manual",
    is_emergency: bool = False,
    recurring_task_id: str | None = None,
) -> dict:
    payload = {
        "daily_plan_id": plan_id,
        "title": title,
        "stage": stage,
        "status": status,
        "is_top_priority": is_top_priority,
        "goal_id": goal_id,
        "long_term_goal_id": long_term_goal_id,
        "source": source,
        "is_emergency": is_emergency,
        "recurring_task_id": recurring_task_id,
    }
    if start_time:
        payload["start_time"] = start_time.isoformat()
    if finish_time:
        payload["finish_time"] = finish_time.isoformat()

    resp = client.table("tasks").insert(payload).execute()
    return resp.data[0]


def update_task_status(client: Client, task_id: str, status: str) -> None:
    client.table("tasks").update(
        {"status": status, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", task_id).execute()


# ---------- goals ----------

def save_goal(client: Client, raw_input: str, ai_decomposition: dict) -> dict:
    resp = (
        client.table("goals")
        .insert({"raw_input": raw_input, "ai_decomposition": ai_decomposition})
        .execute()
    )
    return resp.data[0]


# ---------- long_term_goals ----------

def get_long_term_goals(client: Client) -> list[dict]:
    resp = (
        client.table("long_term_goals")
        .select("*")
        .order("created_at", desc=False)
        .execute()
    )
    return resp.data


def create_long_term_goal(
    client: Client,
    title: str,
    total_hours: float,
    total_levels: int | None,
    current_level: int,
) -> dict:
    resp = (
        client.table("long_term_goals")
        .insert(
            {
                "title": title,
                "total_hours": total_hours,
                "total_levels": total_levels,
                "current_level": current_level,
            }
        )
        .execute()
    )
    return resp.data[0]


def update_long_term_goal_level(client: Client, goal_id: str, current_level: int) -> None:
    client.table("long_term_goals").update(
        {"current_level": current_level}
    ).eq("id", goal_id).execute()


def get_logged_hours_by_goal(client: Client) -> dict[str, float]:
    """Soma a duração (finish_time - start_time) das tarefas concluídas
    (status Done) por meta de longo prazo. Retorna {long_term_goal_id: horas}."""
    resp = (
        client.table("tasks")
        .select("long_term_goal_id, start_time, finish_time")
        .eq("status", "Done")
        .not_.is_("long_term_goal_id", "null")
        .execute()
    )
    totals: dict[str, float] = {}
    for t in resp.data:
        if not t["start_time"] or not t["finish_time"]:
            continue
        start = datetime.fromisoformat(t["start_time"])
        finish = datetime.fromisoformat(t["finish_time"])
        hours = (finish - start).total_seconds() / 3600
        gid = t["long_term_goal_id"]
        totals[gid] = totals.get(gid, 0.0) + hours
    return totals


# ---------- motor de agendamento ----------

WORK_START_HOUR = 9
WORK_END_HOUR = 18
APP_TZ = ZoneInfo("America/Sao_Paulo")


def _agora_local() -> datetime:
    """Agora no horário de parede do app (Brasília), sem tzinfo — mesma
    convenção dos horários gravados. datetime.now()/date.today() puros usariam
    o fuso do servidor (UTC no container), e das 21h à meia-noite já
    devolveriam o dia seguinte."""
    return datetime.now(APP_TZ).replace(tzinfo=None, second=0, microsecond=0)


def _parse_ts(value: str) -> datetime:
    """Converte o timestamptz do Supabase ("...+00:00") em datetime naive.

    O app grava o horário de parede sem fuso (9h digitado vira 09:00 UTC no
    banco), então o horário em UTC, sem o tzinfo, é o próprio horário de
    parede. Sem isso a comparação com os limites do dia (naive) quebra com
    "can't compare offset-naive and offset-aware datetimes"."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _busy_intervals(tasks, exclude_ids=None):
    """Lista (start, finish) de tudo que já tem horário marcado."""
    exclude_ids = exclude_ids or set()
    intervals = []
    for t in tasks:
        if t["id"] in exclude_ids:
            continue
        if not t["start_time"] or not t["finish_time"]:
            continue
        intervals.append((_parse_ts(t["start_time"]), _parse_ts(t["finish_time"])))
    return sorted(intervals)


def find_free_slots(tasks, plan_date, durations_hours, work_start=WORK_START_HOUR,
                    work_end=WORK_END_HOUR, exclude_ids=None):
    """Encaixa uma lista de durações (horas) nos buracos livres do dia,
    na ordem dada, dentro da janela [work_start, work_end). Nunca força
    fora da janela. Retorna lista de (start, finish) na mesma ordem, ou
    None se alguma duração não couber em lugar nenhum."""
    busy = _busy_intervals(tasks, exclude_ids)
    day_start = datetime.combine(plan_date, dtime(hour=work_start))
    agora = _agora_local()
    if plan_date == agora.date():
        day_start = max(day_start, agora)
    day_end = datetime.combine(plan_date, dtime(hour=work_end))

    gaps = []
    cursor = day_start
    for busy_start, busy_finish in busy:
        if busy_start > cursor:
            gaps.append((cursor, min(busy_start, day_end)))
        cursor = max(cursor, busy_finish)
        if cursor >= day_end:
            break
    if cursor < day_end:
        gaps.append((cursor, day_end))
    gaps = [(s, e) for s, e in gaps if e > s]

    results = []
    gap_idx = 0
    for hours in durations_hours:
        duration = timedelta(hours=float(hours))
        placed = False
        while gap_idx < len(gaps):
            gap_start, gap_end = gaps[gap_idx]
            if gap_end - gap_start >= duration:
                start = gap_start
                finish = gap_start + duration
                results.append((start, finish))
                gaps[gap_idx] = (finish, gap_end)
                placed = True
                break
            gap_idx += 1
        if not placed:
            return None
    return results


def update_task_schedule(client, task_id, start_time, finish_time):
    client.table("tasks").update(
        {
            "start_time": start_time.isoformat(),
            "finish_time": finish_time.isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", task_id).execute()


def resolve_conflicts(client, plan_id):
    """Eventos de calendário (source='google_calendar'), tarefas
    is_emergency=True e tarefas já concluídas (Done) nunca se movem. Qualquer outra tarefa com horário
    que colidir com uma dessas (ou, em cascata, com outra já remarcada)
    é empurrada pro próximo horário livre do MESMO dia, podendo passar
    das 18h."""
    tasks = get_tasks_for_plan(client, plan_id)
    timed = [t for t in tasks if t["start_time"] and t["finish_time"]]
    if not timed:
        return

    def overlaps(a_start, a_finish, b_start, b_finish):
        return a_start < b_finish and b_start < a_finish

    def is_fixed(t):
        return (
            t["source"] == "google_calendar"
            or t.get("is_emergency")
            or t["status"] == "Done"
        )

    fixed = sorted([t for t in timed if is_fixed(t)], key=lambda t: t["start_time"])
    movable = sorted([t for t in timed if not is_fixed(t)], key=lambda t: t["start_time"])

    blocking = [(_parse_ts(t["start_time"]), _parse_ts(t["finish_time"])) for t in fixed]

    for t in movable:
        start = _parse_ts(t["start_time"])
        finish = _parse_ts(t["finish_time"])
        duration = finish - start
        moved = False

        while True:
            hit = next(
                ((bs, bf) for bs, bf in blocking if overlaps(start, finish, bs, bf)),
                None,
            )
            if hit is None:
                break
            start = hit[1]
            finish = start + duration
            moved = True

        if moved:
            update_task_schedule(client, t["id"], start, finish)
        blocking.append((start, finish))


def generate_recurring_tasks_for_day(client, plan_id, plan_date):
    """Gera a instância do dia de cada tarefa recorrente ativa, se ainda
    não existir pra esse plano e se sobrar horário livre. Não força.

    Recorrentes com preferred_hour usam sempre esse horário fixo; se ele já
    estiver ocupado, a recorrente é pulada (não sobrepõe) e o título volta
    na lista de retorno pra quem chamou poder avisar."""
    skipped = []
    if plan_date < _agora_local().date():
        return skipped

    is_weekday = plan_date.weekday() < 5

    recurring = (
        client.table("recurring_tasks").select("*").eq("active", True).execute().data
    )
    if not recurring:
        return skipped

    existing = get_tasks_for_plan(client, plan_id)
    existing_recurring_ids = {
        t["recurring_task_id"] for t in existing if t.get("recurring_task_id")
    }

    for r in recurring:
        if r["weekdays_only"] and not is_weekday:
            continue
        if r["id"] in existing_recurring_ids:
            continue
        if r.get("preferred_hour") is not None:
            start = datetime.combine(plan_date, dtime(hour=r["preferred_hour"]))
            finish = start + timedelta(hours=float(r["duration_hours"]))
            if any(bs < finish and start < bf for bs, bf in _busy_intervals(existing)):
                skipped.append(r["title"])
                continue
        else:
            slot = find_free_slots(existing, plan_date, [r["duration_hours"]])
            if not slot:
                continue
            start, finish = slot[0]
        # recurring_task_id vai no mesmo insert: um update separado depois
        # deixaria a tarefa sem vínculo se falhasse, e ela duplicaria no
        # próximo carregamento.
        new_task = add_task(
            client,
            plan_id=plan_id,
            title=r["title"],
            stage=r["stage"],
            status="Planned",
            start_time=start,
            finish_time=finish,
            long_term_goal_id=r["long_term_goal_id"],
            source="recurring",
            recurring_task_id=r["id"],
        )
        existing.append(new_task)
    return skipped
