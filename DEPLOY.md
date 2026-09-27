# Deploy — GitHub → VPS Ubuntu (systemd + Nginx + HTTPS)

Pré-requisito: troque `seudominio.com` (nginx.conf) e `SEU_USUARIO` /
`seu-usuario` (systemd, comandos abaixo) pelos valores reais antes de copiar
os comandos.

## Parte 1 — Subir no GitHub

Rode estes comandos **na sua máquina local**, dentro da pasta `agenda-devops/`
(a mesma onde estão `app.py`, `db.py`, etc.):

```bash
git init
git add .
git commit -m "Agenda DevOps - versão inicial com auth"
```

Crie o repositório vazio no GitHub (via navegador, em github.com/new — não
marque "Initialize with README"). Depois:

```bash
git remote add origin https://github.com/SEU_USUARIO_GITHUB/agenda-devops.git
git branch -M main
git push -u origin main
```

Confirme que o `.env` **não** subiu (o `.gitignore` já bloqueia isso). Rode
`git status` antes do commit se quiser ter certeza.

## Parte 2 — Configurar o Supabase Auth

Antes do deploy, no painel do Supabase (https://supabase.com/dashboard),
projeto **Agenda DevOps**:

1. **Criar seu usuário de login:**
   Authentication → Users → "Add user" → preencha seu email e uma senha
   inicial → marque "Auto Confirm User" (assim não precisa confirmar por
   email na primeira vez).

2. **Configurar as URLs de redirecionamento** (necessário para o link de
   reset de senha funcionar):
   Authentication → URL Configuration →
   - **Site URL:** `https://seudominio.com`
   - **Redirect URLs:** adicione `https://seudominio.com` e, se quiser
     testar localmente também, `http://localhost:8501`

## Parte 3 — Provisionar a VPS

Conecte na VPS via SSH e rode:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx certbot python3-certbot-nginx
```

Clone o projeto:

```bash
cd ~
git clone https://github.com/SEU_USUARIO_GITHUB/agenda-devops.git
cd agenda-devops
```

Crie o venv e instale as dependências (igual ao setup local):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Crie o `.env` na VPS (ele não veio do GitHub, de propósito):

```bash
cp .env.example .env
nano .env
```

Preencha `ANTHROPIC_API_KEY` e ajuste `PUBLIC_APP_URL` para
`https://seudominio.com`. Salve com `Ctrl+O`, `Enter`, `Ctrl+X`.

## Parte 4 — Rodar como serviço systemd

Edite `deploy/agenda-devops.service` substituindo `SEU_USUARIO` pelo seu
usuário Linux real (rode `whoami` se não souber), depois instale o serviço:

```bash
sudo cp deploy/agenda-devops.service /etc/systemd/system/agenda-devops.service
sudo systemctl daemon-reload
sudo systemctl enable agenda-devops
sudo systemctl start agenda-devops
```

Verifique se subiu sem erro:

```bash
sudo systemctl status agenda-devops
```

Deve aparecer `active (running)`. Se der erro, veja os logs com:

```bash
sudo journalctl -u agenda-devops -f
```

## Parte 5 — Nginx como reverse proxy + HTTPS

Copie o template e edite o domínio:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agenda-devops
sudo nano /etc/nginx/sites-available/agenda-devops
```

Troque `seudominio.com` pelo seu domínio real, salve, e ative o site:

```bash
sudo ln -s /etc/nginx/sites-available/agenda-devops /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

`sudo nginx -t` deve retornar "syntax is ok" / "test is successful" antes de
recarregar. Agora gere o certificado HTTPS gratuito (Let's Encrypt):

```bash
sudo certbot --nginx -d seudominio.com
```

O certbot pergunta seu email (pra avisos de renovação) e se quer redirecionar
HTTP para HTTPS automaticamente — escolha **sim** (redirecionar). A renovação
é automática (o certbot já instala um cron/timer).

## Parte 6 — Testar

Acesse `https://seudominio.com` no navegador. Deve aparecer a tela de login.
Entre com o email/senha criados na Parte 2. Teste também "Esqueci minha
senha" — o email deve chegar com um link que volta pro app já pedindo pra
definir a nova senha.

## Atualizando o app depois de mudanças

Sempre que você alterar o código localmente e der `git push`, na VPS rode:

```bash
cd ~/agenda-devops
git pull
source venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart agenda-devops
```
