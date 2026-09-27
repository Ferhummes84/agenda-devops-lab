# Deploy — GitHub → EasyPanel (Docker)

Este é o caminho recomendado agora (substitui o `DEPLOY.md` antigo, que
assumia systemd + Nginx manual numa VPS crua). Como você já roda EasyPanel
na VPS — e o openclaw já está nela — vamos usar a mesma abordagem.

## Parte 1 — GitHub

Igual ao que já foi feito antes: `Dockerfile` e `.dockerignore` já estão no
repo. Se ainda não subiu essas duas adições:

```bash
git add Dockerfile .dockerignore
git commit -m "Adiciona Dockerfile para deploy via EasyPanel"
git push
```

## Parte 2 — Criar o App no EasyPanel

No painel do EasyPanel (porta 3000 da sua VPS):

1. **Criar novo serviço:** botão de criar App → tipo **"App"** (não
   "Compose Project" — é importante ser App simples, pra ele entrar
   automaticamente na rede `easypanel` de ingress, igual ao openclaw).
2. **Source:** conecte o repositório GitHub `agenda-devops` (branch `main`).
3. **Build:** o EasyPanel detecta o `Dockerfile` automaticamente. Se
   perguntar o build method, escolha **Dockerfile** (não Nixpacks/Buildpacks).
4. **Porta interna:** `8501` (é a porta que o Streamlit expõe no Dockerfile).
5. **Variáveis de ambiente** (aba Environment): adicione

   | Nome | Valor |
   |---|---|
   | `SUPABASE_URL` | `https://xzblsddegiwckaxkyowg.supabase.co` |
   | `SUPABASE_KEY` | (a mesma anon key do `.env` local) |
   | `ANTHROPIC_API_KEY` | sua chave da Anthropic |
   | `PUBLIC_APP_URL` | por enquanto, deixe em branco ou use a URL temporária que o EasyPanel gerar (você edita isso na Parte 4, quando decidir o domínio) |

   **Não** copie o `.env` como arquivo pro container — use sempre os campos
   de Environment do EasyPanel. Isso evita segredo vazando na imagem/no Git.

6. Clique em **Deploy**. Acompanhe os logs de build na própria tela do
   EasyPanel — se o build falhar, o erro geralmente é dependência faltando
   no `requirements.txt` ou porta errada.

## Parte 3 — Testar

O EasyPanel te dá uma URL temporária (algo como
`https://agenda-devops-xxxx.easypanel.host` ou similar, dependendo da
versão). Abra essa URL — deve aparecer a tela de login. Se ainda não criou
seu usuário, volte na seção **5.5 do README.md** (criar usuário no Supabase
Dashboard) antes de testar o login.

## Parte 4 — Quando decidir o domínio

Quando escolher o domínio/subdomínio definitivo:

1. No EasyPanel, na aba **Domains** do serviço, adicione o domínio e aponte
   o DNS (registro A ou CNAME) pra VPS conforme o painel instruir. O
   EasyPanel provisiona o certificado HTTPS automaticamente via Traefik.
2. Edite a variável `PUBLIC_APP_URL` pro domínio final (ex:
   `https://agenda.seudominio.com`) e faça **Redeploy**.
3. No Supabase Dashboard → Authentication → URL Configuration, atualize
   **Site URL** e **Redirect URLs** pro mesmo domínio (senão o link de
   reset de senha por email quebra).

## Parte 5 — Redeploy em mudanças futuras

Depois de `git push` no repositório, no EasyPanel você tem duas opções:

- **Manual:** aba do serviço → botão **Deploy** (puxa o último commit e
  rebuilda).
- **Automático:** na aba de configuração do App, ative "Auto Deploy" /
  webhook do GitHub (nome exato varia por versão do EasyPanel) — cada push
  na branch configurada dispara o rebuild sozinho.

## Parte 6 — Confirmar que o openclaw enxerga o app internamente

Depois do deploy, do lado do openclaw (ou via SSH na VPS), confirme o nome
de serviço interno que o EasyPanel atribuiu ao container (aparece no painel,
ou rode `docker service ls` / `docker ps` na VPS procurando por algo como
`agenda-devops` ou `agenda-devops_app`). Teste a partir de dentro da rede:

```bash
# rodando de dentro do container do openclaw, ou de qualquer container
# anexado à rede "easypanel"
curl http://NOME_DO_SERVICO:8501/_stcore/health
```

Se retornar `ok`, a rede está funcionando e o openclaw pode alcançar o app
diretamente. **Importante:** isso serve pra acessar a *interface* do
Streamlit internamente, se você quiser isso no futuro. Para o openclaw
**adicionar tarefas**, ele não precisa disso — continua usando o mesmo
webhook `add-tasks` do Supabase (`https://xzblsddegiwckaxkyowg.supabase.co/
functions/v1/add-tasks` + header `x-webhook-secret`), que já funciona de
qualquer lugar com internet, testado e ativo. Rede Docker compartilhada não
muda nada nesse fluxo — é só um bônus de organização.

## Nota sobre o n8n

O webhook `add-tasks` não teve nenhuma mudança de código nesta etapa — ele é
agnóstico de quem chama. O n8n continua 100% funcional como fallback ou
para automações que façam mais sentido lá (ex: classificação de email,
que já é um fluxo n8n seu). O openclaw vira só mais um chamador possível do
mesmo endpoint.
