# Webhook de Tarefas — integração com n8n

Endpoint para o n8n (ou qualquer automação) injetar tarefas direto na
Agenda DevOps, sem passar pela tela do app. Sempre que você abrir o
dashboard, as tarefas já geradas pela automação estarão lá.

**URL do endpoint:**
```
https://xzblsddegiwckaxkyowg.supabase.co/functions/v1/add-tasks
```

## 1. Configurar o secret (uma vez só)

O endpoint exige um header `x-webhook-secret` — sem ele, ou com o valor
errado, a chamada é rejeitada com 401. Esse secret ainda não está
configurado no servidor; faça isso agora.

**Gere o seu próprio secret** (nunca deixe o valor real neste arquivo —
ele é versionado no git):
```bash
openssl rand -hex 32
```

Guarde o valor gerado num local seguro (ex: seu cofre de credenciais do
n8n, ou um gerenciador de senhas) — **não cole em nenhum arquivo do
repositório**. Configure-o no projeto Supabase por uma destas duas formas:

**Opção A — pelo Dashboard (mais simples):**
1. Acesse https://supabase.com/dashboard/project/xzblsddegiwckaxkyowg/functions
2. Clique em "add-tasks" → aba "Secrets" (ou "Manage secrets", dependendo da versão da UI)
3. Adicione: chave `WEBHOOK_SECRET`, valor o hex que você gerou
4. Salve

**Opção B — via Supabase CLI:**
```bash
supabase login
supabase link --project-ref xzblsddegiwckaxkyowg
supabase secrets set WEBHOOK_SECRET=<cole aqui o hex que você gerou> --project-ref xzblsddegiwckaxkyowg
```

## 2. Testar com curl

Depois de configurar o secret, teste do seu terminal:

```bash
curl -X POST https://xzblsddegiwckaxkyowg.supabase.co/functions/v1/add-tasks \
  -H "Content-Type: application/json" \
  -H "x-webhook-secret: <cole aqui o hex que você gerou>" \
  -d '{
    "date": "2026-08-29",
    "title": "Testar webhook do n8n",
    "stage": "Validation",
    "estimated_hours": 0.5
  }'
```

Resposta esperada (HTTP 200):
```json
{"inserted_count":1,"error_count":0,"inserted":[{...}],"errors":[]}
```

Abra o app na data `2026-08-29` e confirme que a tarefa apareceu no Pipeline.

## 3. Formato do body

**Tarefa única** (ex: um email de suporte classificado como acionável vira
uma tarefa de hoje):
```json
{
  "date": "2026-08-29",
  "title": "Revisar túneis Cloudflare",
  "stage": "Validation",
  "status": "Pending",
  "estimated_hours": 1.5,
  "is_top_priority": true
}
```

**Lote — projeto com fases em dias diferentes** (ex: você cria um projeto
novo e a IA no n8n já quebra em fases distribuídas ao longo da semana):
```json
{
  "project_name": "Certificação AWS SAA",
  "tasks": [
    {"date": "2026-09-01", "title": "Fase 1: Estudo teórico - IAM/VPC", "stage": "Provisioning", "estimated_hours": 2},
    {"date": "2026-09-03", "title": "Fase 2: Lab prático - VPC peering", "stage": "Build", "estimated_hours": 3},
    {"date": "2026-09-05", "title": "Fase 3: Simulado", "stage": "Validation", "estimated_hours": 2}
  ]
}
```

Campos:

| Campo              | Obrigatório | Valores aceitos |
|---------------------|:---:|---|
| `date`              | sim | `YYYY-MM-DD` |
| `title`             | sim | texto livre |
| `stage`             | sim | `Provisioning`, `Build`, `Validation`, `Execution`, `Education` |
| `status`            | não | `Done`, `In Progress`, `Pending`, `Planned`, `Blocked` (default `Pending`) |
| `estimated_hours`   | não | número (default 1h) — ignorado se `start_time`/`finish_time` forem enviados |
| `start_time` / `finish_time` | não | ISO 8601, ex `2026-08-29T14:00:00` |
| `is_top_priority`   | não | `true`/`false` (default `false`) |
| `project_name`      | não | texto — cria o projeto se não existir, ou reaproveita se já existir com esse nome |
| `phase_order`       | não | número — ordem da fase dentro do projeto |

Se não informar `start_time`/`finish_time`, a tarefa é agendada
automaticamente após a última tarefa já existente naquele dia (ou às 09:00
se for a primeira do dia).

## 4. Configurar no n8n

No node **HTTP Request**:
- Method: `POST`
- URL: `https://xzblsddegiwckaxkyowg.supabase.co/functions/v1/add-tasks`
- Headers: `x-webhook-secret` = (o secret configurado no passo 1) — salve
  como uma credencial/variável no n8n, não deixe hardcoded no node.
- Body: JSON, no formato acima, montado a partir da saída do seu fluxo
  (ex: classificação de email, decomposição de meta por IA, etc.)

## Segurança

- Nunca compartilhe o valor de `WEBHOOK_SECRET` fora do n8n/seus scripts.
- Se ele vazar, gere um novo (`openssl rand -hex 32`) e repita o passo 1 —
  o antigo para de funcionar assim que o novo for salvo.
- O endpoint usa a service role key internamente (bypassa RLS), por isso o
  secret é a única barreira de acesso — trate-o como senha de banco.
