# Agenda DevOps

Dashboard de planejamento diário orientado a pipeline (Provisioning → Build →
Validation → Execution → Education), feito em Streamlit, com dados e login no
Supabase e decomposição de metas pela API da Anthropic.

**Em produção:** roda na VPS via EasyPanel (Docker), com deploy a partir da
branch `main` deste repositório. Veja [Deploy](#deploy).

Projeto Supabase:
- Nome: **Agenda DevOps** · Region `sa-east-1` · Project ref `xzblsddegiwckaxkyowg`
- Tabelas: `daily_plans`, `tasks`, `goals`, `long_term_goals`
- Storage: bucket público `audios` (resumos em áudio do Jarvis)

## Funcionalidades

- **Login** via Supabase Auth, com "esqueci minha senha" e troca de senha na
  sidebar. A sessão fica salva num cookie por 7 dias e sobrevive a um F5.
- **Seletor de dia** (abre no dia de hoje).
- **Coluna esquerda:** Metas de Longo Prazo (progresso em horas e níveis) e
  Observabilidade Pessoal (carga cognitiva, lead time, gargalos).
- **Coluna central — Pipeline do Dia:** tarefas retraídas (só o título),
  expansíveis para ver estágio e horário. O checkbox marca como concluída.
  Abaixo, o formulário de tarefa rápida (sem IA).
- **Coluna direita — Orquestrador IA:** descreve uma meta macro e, opcionalmente,
  a duração total estimada. A IA gera de 3 a 6 tarefas dentro desse orçamento
  de horas e as agenda em sequência a partir das 9h. Dá pra vincular o resultado
  a uma meta de longo prazo.
- **Jarvis (sidebar):** botões "🔊" que tocam o último resumo em áudio da manhã
  e do fim de tarde, gerados automaticamente pelo n8n.

## Variáveis de ambiente

| Nome | Uso |
|---|---|
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | anon key do Supabase |
| `ANTHROPIC_API_KEY` | chave da API da Anthropic (Orquestrador IA) |
| `PUBLIC_APP_URL` | URL pública do app: usada no link de reset de senha e para marcar o cookie de sessão como `Secure` quando é `https://` |

Localmente elas vêm do `.env` (modelo em `.env.example`). Em produção ficam na
aba **Environment** do App no EasyPanel. Nunca commite o `.env`.

## Rodar localmente

Requer Python 3.10+.

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env              # preencha SUPABASE_KEY e ANTHROPIC_API_KEY
streamlit run app.py
```

Abra `http://localhost:8501`. Para o link de "esqueci minha senha" funcionar
localmente, `http://localhost:8501` precisa estar em **Redirect URLs**
(Supabase → Authentication → URL Configuration).

### Criar um usuário

Não há cadastro pelo app. Crie o usuário no painel do Supabase:
Authentication → Users → **Add user**, marcando **Auto Confirm User**.

## Deploy

O app está publicado na VPS pelo EasyPanel, como um App do tipo Dockerfile
(porta interna `8501`, com healthcheck em `/_stcore/health`). Com o Auto Deploy
ativo, um push na `main` já gera um novo deploy; sem ele, clique em **Deploy**
no painel.

- Passo a passo da configuração no EasyPanel: [`DEPLOY_EASYPANEL.md`](./DEPLOY_EASYPANEL.md)
- Alternativa sem EasyPanel (systemd + Nginx + certbot), não usada hoje:
  [`DEPLOY.md`](./DEPLOY.md)

Ao mudar o domínio de produção, atualize `PUBLIC_APP_URL` no EasyPanel e a
**Site URL** / **Redirect URLs** no Supabase.

## Integração com n8n

- **Webhook de tarefas:** automações do n8n podem injetar tarefas direto na
  agenda, incluindo projetos de vários dias com fases. Veja
  [`N8N_WEBHOOK.md`](./N8N_WEBHOOK.md).
- **Jarvis:** fluxos com cron às 08:00 e às 16:00 geram `resumo-dia.mp3` e
  `resumo-fim-tarde.mp3` no bucket `audios`. O app baixa o arquivo pelo servidor
  e o serve pelo próprio domínio, porque o CSP do Cloudflare (`default-src
  'self'`, sem `media-src`) impede o navegador de tocar mídia direto do Supabase.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `app.py` | interface Streamlit, login e fluxo da página |
| `auth.py` | login, reset e troca de senha, restauração de sessão (Supabase Auth) |
| `db.py` | acesso às tabelas do Supabase |
| `ai_orchestrator.py` | prompt e chamada à Anthropic, agendamento das tarefas geradas |
| `ui.py` | ícones SVG e fundo animado "Matrix rain" |
| `.streamlit/config.toml` | configuração do Streamlit (toolbar mínima, sem botão Deploy) |
| `Dockerfile` | imagem usada pelo EasyPanel |
