import html
import json as _json
import os
import time
from collections import Counter
from datetime import datetime, timedelta

import anthropic
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_cookies_controller import CookieController

import db
import ai_orchestrator as ai
import auth
import ui

load_dotenv()

st.set_page_config(layout="wide", page_title="Agenda DevOps", page_icon="🛠️")

# ---------- Estilo Dark Mode (mantido do mockup original) ----------
st.markdown(
    """
    <style>
    html, body { background-color: #0e1117; }
    .stApp { background-color: transparent; color: #c9d1d9; }
    .block-container { padding-top: 1.5rem; }
    h1, h2, h3 { color: #58a6ff; }
    .stButton>button { background-color: #238636; color: white; border: 1px solid #2ea043; }
    .stButton>button:hover { background-color: #2ea043; border-color: #3fb950; }
    .metric-box {
        background-color: #161b22; padding: 15px; border-radius: 8px;
        border-left: 4px solid #f0883e; margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Fundo animado "Matrix rain" (decorativo, atrás do dashboard) ----------
ui.render_matrix_background()

# ---------- Credenciais ----------
def get_config(key: str, default: str = "") -> str:
    """Lê de variável de ambiente (.env) primeiro; cai para st.secrets (Streamlit
    Cloud) só se necessário — evita crash quando não existe secrets.toml."""
    value = os.getenv(key)
    if value:
        return value
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_KEY = get_config("SUPABASE_KEY")
ANTHROPIC_API_KEY = get_config("ANTHROPIC_API_KEY")
PUBLIC_APP_URL = get_config("PUBLIC_APP_URL", "http://localhost:8501")
GITHUB_TOKEN = get_config("GITHUB_TOKEN")

# ---------- GitHub (cacheado; detalhes por repo só sob demanda) ----------
GITHUB_API = "https://api.github.com"


def _github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


@st.cache_data(ttl=600)
def fetch_github_repos():
    """Lista todos os repos do usuário (próprios, incluindo privados).
    Chamada leve — 1 request, cacheada por 10min."""
    repos = []
    page = 1
    while True:
        resp = requests.get(
            f"{GITHUB_API}/user/repos",
            headers=_github_headers(),
            params={"per_page": 100, "page": page, "sort": "pushed", "affiliation": "owner"},
            timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


@st.cache_data(ttl=300)
def fetch_repo_details(repo_full_name: str):
    """Busca commit mais recente, PRs abertas e última execução do
    GitHub Actions pra UM repo. Só é chamada quando o usuário pede
    (botão), não em todo carregamento de página."""
    headers = _github_headers()

    commits = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/commits",
        headers=headers, params={"per_page": 1}, timeout=15,
    )
    last_commit = None
    if commits.ok and commits.json():
        c = commits.json()[0]
        last_commit = {
            "message": c["commit"]["message"].split("\n")[0],
            "date": c["commit"]["author"]["date"],
            "author": c["commit"]["author"]["name"],
        }

    prs = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/pulls",
        headers=headers, params={"state": "open", "per_page": 10}, timeout=15,
    )
    open_prs = prs.json() if prs.ok else []

    runs = requests.get(
        f"{GITHUB_API}/repos/{repo_full_name}/actions/runs",
        headers=headers, params={"per_page": 1}, timeout=15,
    )
    latest_run = None
    if runs.ok and runs.json().get("workflow_runs"):
        r = runs.json()["workflow_runs"][0]
        latest_run = {
            "name": r["name"],
            "status": r["status"],
            "conclusion": r["conclusion"],
            "branch": r["head_branch"],
            "updated_at": r["updated_at"],
        }

    return {"last_commit": last_commit, "open_prs": open_prs, "latest_run": latest_run}


@st.cache_data(ttl=None)
def _categorize_meeting_title_cached(title: str) -> str:
    """Usa o Claude pra resumir o título da reunião num rótulo curto de
    assunto (2-3 palavras, em português), tipo 'Entra ID', 'DAST',
    'IA Pentest', 'Product Review'. Cacheado por título — só chama a
    API uma vez por título distinto. Exceções não são cacheadas."""
    client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client_ai.messages.create(
        model="claude-sonnet-5",
        max_tokens=20,
        system=(
            "Você recebe o título de uma reunião e devolve SÓ um "
            "rótulo curto de assunto (2-3 palavras, em português, "
            "sem pontuação final). Ex: 'Daily support' -> 'Suporte "
            "diário'; 'Sync DAST cliente X' -> 'DAST'; 'Revisão "
            "produto Q4' -> 'Product Review'. Responda APENAS o "
            "rótulo, nada mais."
        ),
        messages=[{"role": "user", "content": title}],
    )
    return "".join(
        b.text for b in msg.content if b.type == "text"
    ).strip() or title


def categorize_meeting_title(title: str) -> str:
    """Rótulo da reunião; se a IA falhar, usa o título cru sem cachear a
    falha, pra tentar de novo no próximo carregamento."""
    if not ANTHROPIC_API_KEY:
        return title
    try:
        return _categorize_meeting_title_cached(title)
    except Exception:
        return title


if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "SUPABASE_URL / SUPABASE_KEY não configurados. Veja o README.md para "
        "criar o arquivo .env com essas variáveis."
    )
    st.stop()

client = db.get_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- Cookies do navegador (mantém o login depois de um F5) ----------
# O componente só entrega os cookies depois de montar no navegador: no primeiro
# run da sessão ele devolve {} e, assim que carrega, dispara sozinho um rerun com
# os valores reais. Paramos esse primeiro run pra não piscar a tela de login.
SESSION_COOKIE = "sb_session"
cookies_ready = "cookies" in st.session_state
cookies = CookieController()
if not cookies_ready:
    st.caption("Carregando sessão...")
    st.stop()

if st.session_state.get("_clear_ai_form"):
    st.session_state["meta_input"] = ""
    st.session_state["ai_goal_link"] = "Nenhuma"
    st.session_state["ai_total_hours"] = 0.0
    del st.session_state["_clear_ai_form"]

# =========================================================================
# AUTENTICAÇÃO
# =========================================================================

# 1) Se o usuário voltou de um link de reset de senha, a URL traz "?code=..."
recovery_code = st.query_params.get("code")
if recovery_code and "recovery_session" not in st.session_state:
    session, err = auth.exchange_recovery_code(client, recovery_code)
    if session:
        st.session_state["recovery_session"] = {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
        st.query_params.clear()
    else:
        st.error(f"Link de reset inválido ou expirado: {err}")

# 2) Tela de "definir nova senha" (veio de um link de reset válido)
if "recovery_session" in st.session_state and "session" not in st.session_state:
    ui.heading("Definir nova senha", "key", level=1, size=28)
    auth.restore_session(
        client,
        st.session_state["recovery_session"]["access_token"],
        st.session_state["recovery_session"]["refresh_token"],
    )
    with st.form("set_new_password"):
        new_pw = st.text_input("Nova senha", type="password")
        new_pw_confirm = st.text_input("Confirme a nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha")
        if submitted:
            if len(new_pw) < 8:
                st.error("A senha deve ter pelo menos 8 caracteres.")
            elif new_pw != new_pw_confirm:
                st.error("As senhas não coincidem.")
            else:
                ok, err = auth.update_password(client, new_pw)
                if ok:
                    st.session_state["session"] = st.session_state.pop("recovery_session")
                    st.success("Senha atualizada! Redirecionando...")
                    st.rerun()
                else:
                    st.error(f"Erro ao atualizar senha: {err}")
    st.stop()

# 3a) Logout pendente apaga o cookie; sem sessão em memória (ex.: depois de um
#     F5), tenta recuperá-la do cookie. O componente devolve o valor já
#     convertido de JSON pra dict — a string só aparece em cookies antigos.
if st.session_state.pop("_logout", False):
    if cookies.get(SESSION_COOKIE) is not None:
        cookies.remove(SESSION_COOKIE)
elif "session" not in st.session_state:
    saved = cookies.get(SESSION_COOKIE)
    if saved:
        try:
            st.session_state["session"] = saved if isinstance(saved, dict) else _json.loads(saved)
        except Exception:
            pass

# 3) Restaura sessão já existente (necessário a cada rerun do Streamlit)
if "session" in st.session_state:
    restored = auth.restore_session(
        client,
        st.session_state["session"]["access_token"],
        st.session_state["session"]["refresh_token"],
    )
    if restored:
        # set_session renova o access token quando ele expira, e o refresh token
        # antigo deixa de valer — guarda sempre o par atual.
        st.session_state["session"] = {
            "access_token": restored.access_token,
            "refresh_token": restored.refresh_token,
        }
    else:
        # Tokens inválidos (ex.: cookie de uma sessão já encerrada): volta pro login.
        del st.session_state["session"]
        if cookies.get(SESSION_COOKIE) is not None:
            cookies.remove(SESSION_COOKIE)

# 4) Tela de login (se ainda não autenticado)
if "session" not in st.session_state:
    ui.heading("Agenda DevOps", "terminal", level=1, size=28)
    ui.heading("Login", "lock", level=2, size=20)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            session, err = auth.sign_in(client, email, password)
            if session:
                st.session_state["session"] = {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                }
                st.rerun()
            else:
                st.error(f"Falha no login: {err}")

    with st.expander("Esqueci minha senha"):
        reset_email = st.text_input("Seu email cadastrado", key="reset_email")
        if st.button("Enviar link de reset"):
            if reset_email:
                ok, err = auth.send_password_reset_email(client, reset_email, PUBLIC_APP_URL)
                if ok:
                    st.success("Se o email existir, um link de reset foi enviado.")
                else:
                    st.error(f"Erro ao enviar email: {err}")
            else:
                st.warning("Informe o email.")
    st.stop()

# ---------- A partir daqui o usuário já está autenticado ----------
# Espelha a sessão atual no cookie (vale pra login, reset de senha e token
# renovado). Fica aqui, e não junto dos st.rerun() do login, porque o cookie é
# gravado por um componente no navegador que precisa terminar de carregar — um
# rerun imediato o descarta antes disso.
if cookies.get(SESSION_COOKIE) != st.session_state["session"]:
    cookies.set(
        SESSION_COOKIE,
        st.session_state["session"],
        expires=datetime.now() + timedelta(days=7),
        max_age=60 * 60 * 24 * 7,
        secure=PUBLIC_APP_URL.startswith("https://") or None,
    )

ui.heading("Agenda DevOps", "terminal", level=1, size=28)

with st.sidebar:
    ui.heading("Conta", "user", level=3, size=18)
    if st.button("Sair", icon=":material/logout:"):
        auth.sign_out(client)
        st.session_state.clear()
        # O cookie é apagado no próximo run (bloco 3a), pelo mesmo motivo de ser
        # gravado fora dos st.rerun(): o componente precisa de um run inteiro.
        st.session_state["_logout"] = True
        st.rerun()

    with st.expander("Trocar senha", icon=":material/key:"):
        with st.form("change_password_form"):
            pw1 = st.text_input("Nova senha", type="password", key="pw1")
            pw2 = st.text_input("Confirme a nova senha", type="password", key="pw2")
            change_submitted = st.form_submit_button("Atualizar senha")
            if change_submitted:
                if len(pw1) < 8:
                    st.error("A senha deve ter pelo menos 8 caracteres.")
                elif pw1 != pw2:
                    st.error("As senhas não coincidem.")
                else:
                    ok, err = auth.update_password(client, pw1)
                    if ok:
                        st.success("Senha atualizada com sucesso.")
                    else:
                        st.error(f"Erro: {err}")

    st.markdown("---")
    ui.heading("Jarvis", "mic")
    # Os áudios são gerados pelos crons do n8n (08:00 e 16:00). O app baixa o
    # arquivo no servidor e entrega os bytes ao st.audio, que os serve pelo
    # próprio domínio: o CSP de produção (default-src 'self', sem media-src)
    # bloqueia o navegador de carregar mídia direto do Supabase.
    # As URLs vêm do ambiente, sem valor padrão: o lab nunca pode chamar a
    # produção (um scanner DAST clicaria nesses botões).
    JARVIS_AUDIO_URLS = {
        label: url
        for label, url in {
            "Resumo da manhã": get_config("JARVIS_AUDIO_MORNING_URL"),
            "Resumo do fim de tarde": get_config("JARVIS_AUDIO_EVENING_URL"),
        }.items()
        if url
    }
    if not JARVIS_AUDIO_URLS:
        st.caption("Jarvis desativado neste ambiente.")
    for label, url in JARVIS_AUDIO_URLS.items():
        if st.button(f"🔊 {label}", key=f"jarvis_play_{label}"):
            try:
                # ?t= fura o cache do CDN pra sempre pegar o áudio mais recente.
                resp = requests.get(url, params={"t": int(time.time())}, timeout=15)
                resp.raise_for_status()
                st.audio(resp.content, format="audio/mpeg", autoplay=True)
            except Exception as e:
                st.error(f"Não foi possível carregar o áudio: {e}")

    st.markdown("---")
    CALENDAR_SYNC_WEBHOOK_URL = get_config("CALENDAR_SYNC_WEBHOOK_URL")
    if not CALENDAR_SYNC_WEBHOOK_URL:
        st.caption("Sincronização desativada neste ambiente.")
    elif st.button("🔄 Atualizar calendário agora"):
        with st.spinner("Sincronizando..."):
            try:
                resp = requests.get(CALENDAR_SYNC_WEBHOOK_URL, timeout=15)
                resp.raise_for_status()
                time.sleep(3)  # dá um tempo pro n8n terminar de gravar antes do rerun
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao sincronizar: {e}")

# ---------- Seletor de dia de planejamento ----------
# Abre por padrão no dia de hoje.
default_plan_date = db._agora_local().date()
plan_date = st.date_input("Planejando para o dia:", value=default_plan_date)

plan = db.get_or_create_daily_plan(client, plan_date)
tasks = db.get_tasks_for_plan(client, plan["id"])
skipped_recurring = db.generate_recurring_tasks_for_day(client, plan["id"], plan_date)
db.resolve_conflicts(client, plan["id"])
tasks = db.get_tasks_for_plan(client, plan["id"])
long_term_goals = db.get_long_term_goals(client)
logged_hours_by_goal = db.get_logged_hours_by_goal(client)
goal_options = {"Nenhuma": None}
goal_options.update({g["title"]: g["id"] for g in long_term_goals})

STAGE_COLORS = {
    "Provisioning": "#58a6ff",
    "Build": "#d2a8ff",
    "Validation": "#3fb950",
    "Execution": "#f0883e",
    "Education": "#8b949e",
}

# =========================================================================
# PÁGINAS (cada seção tem rota própria; tudo acima roda antes da navegação,
# então sem sessão qualquer rota mostra apenas o login)
# =========================================================================

# ---------- Pipeline Timeline ----------
def page_pipeline():
    ui.heading("Pipeline do Dia", "git-branch")

    # Os balões disparam no run seguinte ao da marcação: chamados antes do
    # st.rerun() eles seriam descartados junto com o run interrompido.
    if st.session_state.pop("_celebrate_done", False):
        st.balloons()

    for title in skipped_recurring:
        st.warning(
            f"Recorrente \"{title}\" não foi criada: o horário fixo dela já "
            "está ocupado nesse dia."
        )

    if tasks:
        st.markdown("**Tarefas do dia:**")
        for t in tasks:
            was_done = t["status"] == "Done"
            check_col, exp_col = st.columns([1, 14])
            with check_col:
                checked = st.checkbox(
                    f"Concluir: {t['title']}", value=was_done, key=f"task_{t['id']}",
                    label_visibility="collapsed",
                )
            with exp_col:
                label = f"✅ ~~{t['title']}~~" if was_done else t["title"]
                with st.expander(label):
                    inicio = (
                        datetime.fromisoformat(t["start_time"]).strftime("%H:%M")
                        if t["start_time"] else "—"
                    )
                    fim = (
                        datetime.fromisoformat(t["finish_time"]).strftime("%H:%M")
                        if t["finish_time"] else "—"
                    )
                    st.caption(f"{t['stage']} · {inicio} – {fim}")
            if checked and not was_done:
                db.update_task_status(client, t["id"], "Done")
                st.session_state["_celebrate_done"] = True
                st.rerun()
            elif not checked and was_done:
                db.update_task_status(client, t["id"], "Pending")
                st.rerun()
    else:
        st.caption("Nenhuma tarefa cadastrada para este dia ainda.")

    st.markdown("---")
    ui.label("Adicionar tarefa rápida (sem IA)", "plus")
    with st.form("quick_add", clear_on_submit=True):
        qa_col1, qa_col2, qa_col3 = st.columns([2, 1, 1])
        title = qa_col1.text_input("Título da tarefa")
        stage = qa_col2.selectbox("Estágio", list(STAGE_COLORS.keys()))
        start_h = qa_col3.number_input(
            "Hora início", 0, 23, 9,
            help="Só é usado se marcar Emergência. Sem isso, o sistema escolhe "
                 "sozinho o próximo horário livre.",
        )
        duration_h = st.slider("Duração estimada (h)", 0.5, 8.0, 1.0, step=0.5)
        top_priority = st.checkbox("Marcar como Top 3 prioridade do dia")
        is_emergency = st.checkbox(
            "🚨 Emergência (fura fila, usa o horário de início escolhido)"
        )
        linked_goal_label = st.selectbox(
            "Vincular à meta de longo prazo (opcional)", list(goal_options.keys())
        )
        submitted = st.form_submit_button("Adicionar")
        if submitted and title:
            if is_emergency:
                start_dt = datetime.combine(plan_date, datetime.min.time()).replace(hour=start_h)
                finish_dt = start_dt + timedelta(hours=duration_h)
                slot = [(start_dt, finish_dt)]
            else:
                slot = db.find_free_slots(tasks, plan_date, [duration_h])
            # Sem st.stop() aqui: ele interromperia o script e o resto da
            # página não seria desenhado junto com o erro.
            if not slot:
                st.error(
                    "Não sobrou horário livre entre 9h e 18h hoje. Marque "
                    "como Emergência se precisar encaixar mesmo assim."
                )
            else:
                start_dt, finish_dt = slot[0]
                db.add_task(
                    client,
                    plan_id=plan["id"],
                    title=title,
                    stage=stage,
                    status="Planned",
                    start_time=start_dt,
                    finish_time=finish_dt,
                    is_top_priority=top_priority,
                    long_term_goal_id=goal_options[linked_goal_label],
                    source="manual",
                    is_emergency=is_emergency,
                )
                if is_emergency:
                    db.resolve_conflicts(client, plan["id"])
                st.rerun()


# ---------- Metas de Longo Prazo ----------
def page_metas():
    ui.heading("Metas de Longo Prazo", "flag")

    if not long_term_goals:
        st.caption("Nenhuma meta de longo prazo cadastrada ainda.")
    for g in long_term_goals:
        done_hours = logged_hours_by_goal.get(g["id"], 0.0)
        total_hours = float(g["total_hours"])
        pct = min(done_hours / total_hours, 1.0) if total_hours else 0.0
        level_info = (
            f" · Nível {g['current_level']}/{g['total_levels']}"
            if g.get("total_levels")
            else f" · Nível {g['current_level']}"
        )
        st.markdown(f"**{g['title']}**")
        st.progress(pct)
        st.caption(f"{done_hours:.1f}h / {total_hours:.0f}h ({pct * 100:.0f}%){level_info}")
        with st.expander("Atualizar nível", expanded=False):
            new_level = st.number_input(
                "Nível atual",
                min_value=1,
                max_value=int(g["total_levels"]) if g.get("total_levels") else 999,
                value=int(g["current_level"]),
                step=1,
                key=f"level_{g['id']}",
            )
            if st.button("Salvar nível", key=f"update_level_{g['id']}"):
                db.update_long_term_goal_level(client, g["id"], int(new_level))
                st.rerun()

    with st.expander("+ Nova meta de longo prazo"):
        with st.form("new_long_term_goal", clear_on_submit=True):
            lt_title = st.text_input("Título da meta")
            lt_hours = st.number_input("Carga horária total (h)", min_value=0.5, step=0.5, value=10.0)
            lt_levels = st.number_input("Total de níveis/etapas (0 = sem níveis)", min_value=0, step=1, value=0)
            lt_current_level = st.number_input("Nível atual", min_value=1, step=1, value=1)
            lt_submitted = st.form_submit_button("Criar meta")
            if lt_submitted and lt_title:
                db.create_long_term_goal(
                    client,
                    title=lt_title,
                    total_hours=lt_hours,
                    total_levels=int(lt_levels) if lt_levels > 0 else None,
                    current_level=int(lt_current_level),
                )
                st.rerun()


# ---------- Reuniões da Semana ----------
def page_reunioes():
    ui.heading("Reuniões da Semana", "activity")

    week_meetings = db.get_week_meetings(client, plan_date)
    st.markdown(f"**{len(week_meetings)} reuniões aceitas** nesta semana")

    if week_meetings:
        categories = Counter(
            categorize_meeting_title(m["title"]) for m in week_meetings
        )
        palette = list(STAGE_COLORS.values())
        max_count = max(categories.values())

        # Sem indentação no HTML: linhas com 4+ espaços viram bloco de
        # código no markdown do Streamlit em vez de serem renderizadas.
        rows_html = ""
        for i, (label, count) in enumerate(
            sorted(categories.items(), key=lambda x: -x[1])
        ):
            color = palette[i % len(palette)]
            width_pct = (count / max_count) * 100
            safe_label = html.escape(label)
            rows_html += (
                '<div style="margin-bottom: 10px;">'
                '<div style="display: flex; justify-content: space-between; '
                'font-size: 12px; color: #c9d1d9; margin-bottom: 3px;">'
                f'<span>{safe_label}</span><span style="color: #8b949e;">{count}</span>'
                '</div>'
                '<div style="background: #21262d; border-radius: 999px; height: 6px; overflow: hidden;">'
                f'<div style="background: {color}; width: {width_pct}%; height: 100%; border-radius: 999px;"></div>'
                '</div>'
                '</div>'
            )
        st.markdown(rows_html, unsafe_allow_html=True)
    else:
        st.caption("Nenhuma reunião aceita registrada nesta semana ainda.")


# ---------- Orquestrador IA ----------
def page_orquestrador():
    ui.heading("Orquestrador IA", "sparkles")
    meta_input = st.text_area(
        "Defina sua Meta (Macro):",
        placeholder="Ex: Criar agente IA no n8n usando Groq para triagem...",
        key="meta_input",
    )
    total_hours_input = st.number_input(
        "Duração total estimada (h)",
        min_value=0.0,
        step=0.5,
        key="ai_total_hours",
        help="Quanto tempo você acha que essa meta toda deveria tomar. "
             "Deixe em 0 se não souber — a IA assume uma sessão curta e realista.",
    )
    linked_goal_label_ai = st.selectbox(
        "Vincular à meta de longo prazo (opcional)",
        list(goal_options.keys()),
        key="ai_goal_link",
    )

    if st.button("Gerar Pipeline com IA"):
        if not meta_input:
            st.warning("Descreva uma meta primeiro.")
        elif not ANTHROPIC_API_KEY:
            st.error("ANTHROPIC_API_KEY não configurada. Veja o README.md.")
        else:
            with st.spinner("Decompondo meta em estágios..."):
                try:
                    result = ai.decompose_goal(
                        ANTHROPIC_API_KEY,
                        meta_input,
                        total_hours=total_hours_input if total_hours_input > 0 else None,
                    )
                    linked_goal_id = goal_options[linked_goal_label_ai]

                    durations = [t["estimated_hours"] for t in result["tasks"]]
                    slots = db.find_free_slots(tasks, plan_date, durations)
                    if not slots:
                        st.error(
                            "Não tem horário livre suficiente hoje pra essas tarefas. "
                            "Reduza a duração total ou libere espaço na agenda."
                        )
                    else:
                        # A meta só é salva quando as tarefas cabem, pra não
                        # deixar registros órfãos em goals a cada tentativa.
                        goal_row = db.save_goal(client, meta_input, result)
                        scheduled = []
                        for t, (start, finish) in zip(result["tasks"], slots):
                            db.add_task(
                                client,
                                plan_id=plan["id"],
                                title=t["title"],
                                stage=t["stage"],
                                status="Pending",
                                start_time=start,
                                finish_time=finish,
                                goal_id=goal_row["id"],
                                long_term_goal_id=linked_goal_id,
                                source="ai",
                            )
                            scheduled.append({"title": t["title"], "stage": t["stage"]})
                        st.success(f"{len(scheduled)} tarefas injetadas no pipeline!")
                        st.markdown("**Tarefas Injetadas:**")
                        for s in scheduled:
                            st.markdown(f"- [{s['stage']}] {s['title']}")
                        st.session_state["_clear_ai_form"] = True
                        st.rerun()
                except Exception as e:
                    st.error(f"Erro ao chamar a IA: {e}")


# ---------- GitHub ----------
def page_github():
    ui.heading("GitHub", "github")

    if not GITHUB_TOKEN:
        st.info("GITHUB_TOKEN não configurado — a seção do GitHub fica desativada.")
    else:
        try:
            repos = fetch_github_repos()
            repos = repos[:5]
        except Exception as e:
            repos = []
            st.error(f"Não foi possível carregar os repositórios: {e}")

        for i, repo in enumerate(repos):
            # pushed_at pode vir null na API; cai pro updated_at pra não quebrar a página.
            pushed_raw = repo.get("pushed_at") or repo["updated_at"]
            pushed = datetime.fromisoformat(pushed_raw.replace("Z", "+00:00"))
            repo_color = list(STAGE_COLORS.values())[i % len(STAGE_COLORS)]
            st.markdown(
                f'<div style="height: 3px; background: {repo_color}; '
                f'border-radius: 2px; margin-bottom: 2px;"></div>',
                unsafe_allow_html=True,
            )
            with st.expander(
                f"{repo['name']} · último push em {pushed.strftime('%d/%m/%Y')} · "
                f"{repo['open_issues_count']} issues abertas"
            ):
                st.caption(repo.get("description") or "Sem descrição.")
                if st.button("🔍 Ver detalhes (commits, PRs, CI)", key=f"gh_details_{repo['id']}"):
                    with st.spinner("Buscando..."):
                        details = fetch_repo_details(repo["full_name"])

                    if details["last_commit"]:
                        c = details["last_commit"]
                        st.markdown(f"**Último commit:** {c['message']} — {c['author']}")

                    prs = details["open_prs"]
                    if prs:
                        st.markdown(f"**{len(prs)} PR(s) aberta(s):**")
                        for pr in prs:
                            st.markdown(f"- [{pr['title']}]({pr['html_url']})")
                    else:
                        st.caption("Nenhuma PR aberta.")

                    run = details["latest_run"]
                    if run:
                        icon = "🟢" if run["conclusion"] == "success" else (
                            "🔴" if run["conclusion"] == "failure" else "🟡"
                        )
                        st.markdown(
                            f"**Última execução do CI:** {icon} {run['name']} "
                            f"({run['branch']}) — {run['status']}"
                        )
                    else:
                        st.caption("Nenhuma execução de CI encontrada.")


pages = [
    st.Page(page_pipeline, title="Pipeline do Dia", icon=":material/timeline:", default=True),
    st.Page(page_metas, title="Metas", icon=":material/flag:", url_path="metas"),
    st.Page(page_reunioes, title="Reuniões", icon=":material/groups:", url_path="reunioes"),
    st.Page(page_orquestrador, title="Orquestrador IA", icon=":material/auto_awesome:", url_path="orquestrador"),
    st.Page(page_github, title="GitHub", icon=":material/code:", url_path="github"),
]

st.navigation(pages).run()
