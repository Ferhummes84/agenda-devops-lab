"""
auth.py — autenticação via Supabase Auth para o Agenda DevOps.

Fluxos cobertos:
- Login com email/senha
- "Esqueci minha senha" (tela inicial) -> envia email com link de reset
- Troca de senha dentro do app (usuário já logado)
- Conclusão do reset: quando o usuário clica no link do email, ele volta pro
  app com "?code=..." na URL; capturamos isso e trocamos por uma sessão
  válida, permitindo definir a nova senha na hora.
"""
from supabase import Client


def sign_in(client: Client, email: str, password: str):
    """Retorna (session, error_message). session é None se falhar."""
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        return resp.session, None
    except Exception as e:
        return None, str(e)


def send_password_reset_email(client: Client, email: str, redirect_to: str):
    """Dispara o email de reset. Retorna (ok: bool, error_message)."""
    try:
        client.auth.reset_password_for_email(email, {"redirect_to": redirect_to})
        return True, None
    except Exception as e:
        return False, str(e)


def exchange_recovery_code(client: Client, code: str):
    """Troca o ?code=... da URL (vindo do email de reset) por uma sessão válida.
    Retorna (session, error_message)."""
    try:
        resp = client.auth.exchange_code_for_session({"auth_code": code})
        return resp.session, None
    except Exception as e:
        return None, str(e)


def restore_session(client: Client, access_token: str, refresh_token: str):
    """Reaplica uma sessão já existente no client recém-criado (necessário
    porque o Streamlit recria o client a cada rerun do script).

    Retorna a sessão ativa — com tokens novos se o access token tinha expirado
    e foi renovado — ou None se os tokens não valem mais."""
    try:
        return client.auth.set_session(access_token, refresh_token).session
    except Exception:
        return None


def update_password(client: Client, new_password: str):
    """Requer que o client já tenha uma sessão ativa (via restore_session
    ou logo após sign_in / exchange_recovery_code)."""
    try:
        client.auth.update_user({"password": new_password})
        return True, None
    except Exception as e:
        return False, str(e)


def sign_out(client: Client):
    try:
        client.auth.sign_out()
    except Exception:
        pass
