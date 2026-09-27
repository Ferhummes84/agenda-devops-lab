"""
ai_orchestrator.py — chama a API da Anthropic para decompor uma meta macro
em tarefas com estágio (Provisioning/Build/Validation/Execution/Education)
e duração estimada em horas.
"""
import json

import anthropic

VALID_STAGES = ["Provisioning", "Build", "Validation", "Execution", "Education"]
MAX_TASKS = 6


def _build_system_prompt(total_hours: float | None) -> str:
    if total_hours:
        budget_rule = (
            f"- A SOMA de estimated_hours de TODAS as tarefas deve ficar entre "
            f"{total_hours * 0.8:.1f}h e {total_hours * 1.2:.1f}h (o usuário estimou "
            f"{total_hours:.1f}h no total para essa meta inteira). Ajuste o NÚMERO de "
            f"tarefas e a duração de cada uma pra caber nesse total — não gere mais "
            f"tarefas do que cabem nesse orçamento de tempo."
        )
    else:
        budget_rule = (
            "- O usuário não informou uma duração total. Assuma que a meta cabe numa "
            "sessão de trabalho focada e realista — tipicamente entre 2 e 6 horas no "
            "total somando todas as tarefas — a menos que o texto da meta descreva "
            "claramente um projeto de múltiplos dias."
        )

    return f"""Você é um engenheiro de DevSecOps que decompõe metas macro em
tarefas técnicas executáveis, no estilo de um pipeline de CI/CD.

Responda SOMENTE com um JSON válido (sem markdown, sem texto antes ou depois),
no formato exato:

{{
  "tasks": [
    {{"title": "string curta e acionável", "stage": "um de {VALID_STAGES}", "estimated_hours": number}}
  ]
}}

Regras:
- Gere entre 3 e {MAX_TASKS} tarefas. NUNCA mais que {MAX_TASKS}.
- Estágios devem seguir a ordem lógica de dependência (Provisioning -> Build -> Validation -> Execution -> Education quando fizer sentido).
- estimated_hours por tarefa deve ser realista (mínimo 0.25h).
{budget_rule}
- Não inclua nenhum campo além de title, stage e estimated_hours.
"""


def decompose_goal(
    api_key: str,
    goal_text: str,
    total_hours: float | None = None,
    model: str = "claude-sonnet-5",
) -> dict:
    """Chama a Anthropic API e retorna o dict já parseado {"tasks": [...]}.

    total_hours, se informado, ancora o modelo a um orçamento de tempo total
    pra evitar que a meta seja fatiada em tarefas demais espalhadas o dia
    inteiro quando na prática cabe numa janela curta.
    """
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_build_system_prompt(total_hours),
        messages=[{"role": "user", "content": goal_text}],
    )

    raw_text = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json\n", "", 1)

    parsed = json.loads(raw_text)

    tasks = [t for t in parsed.get("tasks", []) if t.get("stage") in VALID_STAGES]

    if len(tasks) > MAX_TASKS:
        tasks = tasks[:MAX_TASKS]

    if total_hours and tasks:
        total_generated = sum(float(t.get("estimated_hours", 1)) for t in tasks)
        if total_generated > 0 and abs(total_generated - total_hours) / total_hours > 0.25:
            scale = total_hours / total_generated
            for t in tasks:
                t["estimated_hours"] = round(float(t.get("estimated_hours", 1)) * scale, 2)

    parsed["tasks"] = tasks
    return parsed

