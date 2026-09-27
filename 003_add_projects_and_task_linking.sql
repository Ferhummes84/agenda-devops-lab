-- 003_add_projects_and_task_linking.sql
-- Suporte a projetos multi-dia com fases (tarefas vinculadas a um projeto,
-- cada uma podendo cair num dia diferente) e rastreio de origem da tarefa.

create table projects (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    description text,
    created_at timestamptz not null default now()
);

alter table projects enable row level security;
create policy "authenticated_full_access_projects" on projects
    for all using (auth.uid() is not null) with check (auth.uid() is not null);

alter table tasks add column project_id uuid references projects(id) on delete set null;
alter table tasks add column phase_order smallint;
alter table tasks add column source text not null default 'manual' check (source in ('manual', 'ai_orchestrator', 'n8n_webhook'));

create index idx_tasks_project on tasks(project_id);
