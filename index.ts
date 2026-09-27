// supabase/functions/add-tasks/index.ts
//
// Webhook para o n8n (ou qualquer automação) injetar tarefas na Agenda DevOps.
//
// Autenticação: NÃO usa JWT do Supabase (deploy com verify_jwt=false).
// Em vez disso, exige o header "x-webhook-secret" batendo com o secret
// WEBHOOK_SECRET configurado nas Function Secrets do projeto.
//
// Body aceito (um dos dois formatos):
//
// 1) Tarefa única:
// {
//   "date": "2026-08-29",
//   "title": "Revisar túneis Cloudflare",
//   "stage": "Validation",
//   "status": "Pending",              // opcional, default "Pending"
//   "estimated_hours": 1.5,           // opcional (default 1h) OU use start_time/finish_time
//   "start_time": "2026-08-29T14:00:00", // opcional, ISO local
//   "finish_time": "2026-08-29T15:00:00", // opcional, ISO local
//   "is_top_priority": true,          // opcional, default false
//   "project_name": "Certificação X"  // opcional — cria/vincula a um projeto multi-dia
// }
//
// 2) Lote (várias tarefas, ex.: fases de um projeto novo em dias diferentes):
// {
//   "project_name": "Certificação X",   // opcional, aplicado a todas as tasks do lote
//   "tasks": [
//     {"date": "2026-09-01", "title": "Fase 1: Estudo teórico", "stage": "Provisioning", "estimated_hours": 2},
//     {"date": "2026-09-03", "title": "Fase 2: Lab prático", "stage": "Build", "estimated_hours": 3}
//   ]
// }

import { createClient } from "jsr:@supabase/supabase-js@2";

const VALID_STAGES = ["Provisioning", "Build", "Validation", "Execution", "Education"];
const VALID_STATUSES = ["Done", "In Progress", "Pending", "Planned", "Blocked"];

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const webhookSecret = Deno.env.get("WEBHOOK_SECRET");

const supabase = createClient(supabaseUrl, serviceRoleKey);

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function getOrCreateDailyPlan(planDate: string) {
  const { data: existing } = await supabase
    .from("daily_plans")
    .select("*")
    .eq("plan_date", planDate)
    .maybeSingle();
  if (existing) return existing;

  const { data: created, error } = await supabase
    .from("daily_plans")
    .insert({ plan_date: planDate })
    .select()
    .single();
  if (error) throw error;
  return created;
}

async function getOrCreateProject(name: string) {
  const { data: existing } = await supabase
    .from("projects")
    .select("*")
    .eq("name", name)
    .maybeSingle();
  if (existing) return existing;

  const { data: created, error } = await supabase
    .from("projects")
    .insert({ name })
    .select()
    .single();
  if (error) throw error;
  return created;
}

async function nextFreeSlot(dailyPlanId: string, planDate: string): Promise<Date> {
  const { data } = await supabase
    .from("tasks")
    .select("finish_time")
    .eq("daily_plan_id", dailyPlanId)
    .order("finish_time", { ascending: false })
    .limit(1);

  if (data && data.length > 0 && data[0].finish_time) {
    return new Date(data[0].finish_time);
  }
  // Sem tarefas ainda hoje: começa às 09:00 do dia planejado
  return new Date(`${planDate}T09:00:00`);
}

interface IncomingTask {
  date: string;
  title: string;
  stage: string;
  status?: string;
  estimated_hours?: number;
  start_time?: string;
  finish_time?: string;
  is_top_priority?: boolean;
  project_name?: string;
  phase_order?: number;
}

async function insertOneTask(t: IncomingTask, fallbackProjectName?: string) {
  if (!t.date || !t.title || !t.stage) {
    throw new Error(`Campos obrigatórios ausentes (date, title, stage): ${JSON.stringify(t)}`);
  }
  if (!VALID_STAGES.includes(t.stage)) {
    throw new Error(`Stage inválido "${t.stage}". Use um de: ${VALID_STAGES.join(", ")}`);
  }
  const status = t.status ?? "Pending";
  if (!VALID_STATUSES.includes(status)) {
    throw new Error(`Status inválido "${status}". Use um de: ${VALID_STATUSES.join(", ")}`);
  }

  const plan = await getOrCreateDailyPlan(t.date);

  let startTime: Date;
  let finishTime: Date;
  if (t.start_time && t.finish_time) {
    startTime = new Date(t.start_time);
    finishTime = new Date(t.finish_time);
  } else {
    startTime = await nextFreeSlot(plan.id, t.date);
    const hours = t.estimated_hours ?? 1;
    finishTime = new Date(startTime.getTime() + hours * 60 * 60 * 1000);
  }

  let projectId: string | null = null;
  const projectName = t.project_name ?? fallbackProjectName;
  if (projectName) {
    const project = await getOrCreateProject(projectName);
    projectId = project.id;
  }

  const { data, error } = await supabase
    .from("tasks")
    .insert({
      daily_plan_id: plan.id,
      title: t.title,
      stage: t.stage,
      status,
      start_time: startTime.toISOString(),
      finish_time: finishTime.toISOString(),
      is_top_priority: t.is_top_priority ?? false,
      project_id: projectId,
      phase_order: t.phase_order ?? null,
      source: "n8n_webhook",
    })
    .select()
    .single();

  if (error) throw error;
  return data;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "Use POST." }, 405);
  }

  if (!webhookSecret) {
    return jsonResponse({ error: "WEBHOOK_SECRET não configurado no servidor." }, 500);
  }
  const providedSecret = req.headers.get("x-webhook-secret");
  if (providedSecret !== webhookSecret) {
    return jsonResponse({ error: "Não autorizado." }, 401);
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "Body precisa ser JSON válido." }, 400);
  }

  const tasksInput: IncomingTask[] = Array.isArray(body.tasks) ? body.tasks : [body];
  const fallbackProjectName: string | undefined = body.project_name;

  const results = [];
  const errors = [];

  for (const t of tasksInput) {
    try {
      const inserted = await insertOneTask(t, fallbackProjectName);
      results.push(inserted);
    } catch (e) {
      errors.push({ input: t, error: (e as Error).message });
    }
  }

  return jsonResponse(
    {
      inserted_count: results.length,
      error_count: errors.length,
      inserted: results,
      errors,
    },
    errors.length > 0 && results.length === 0 ? 400 : 200,
  );
});
