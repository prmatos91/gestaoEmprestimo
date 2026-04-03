import os
import requests
from supabase import create_client, Client
from datetime import datetime, date, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- CONFIGURAÇÕES ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Service Role Key — ignora RLS

# WAHA: URL base do seu servidor (ex: http://SEU_IP_ORACLE:3000)
WAHA_URL = os.getenv("WAHA_URL")
# Opcional: se você configurou API Key no WAHA (recomendado)
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
# Nome da sessão do WAHA (padrão é "default")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY não configuradas.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def format_phone_waha(phone: str) -> str:
    """
    Converte número brasileiro para o formato do WAHA.
    Entrada: '11987654321' (11 dígitos, sem DDI)
    Saída:   '5511987654321@c.us'
    """
    digits = "".join(filter(str.isdigit, phone))
    if not digits.startswith("55"):
        digits = "55" + digits
    return f"{digits}@c.us"


def send_whatsapp(phone: str, message: str) -> bool:
    """Envia mensagem via WAHA. Retorna True em sucesso."""
    if not WAHA_URL:
        print(f"[SIMULAÇÃO — WAHA_URL não configurada] {phone}: {message}")
        return True

    chat_id = format_phone_waha(phone)
    url = f"{WAHA_URL.rstrip('/')}/api/sendText"
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY

    payload = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "text": message,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  [ERRO] Falha ao enviar para {phone}: {e}")
        return False


def build_message(client_name: str, loan: dict) -> str:
    """Monta o texto da mensagem de cobrança."""
    saldo = float(loan["remaining_amount"])
    due = datetime.strptime(loan["due_date"], "%Y-%m-%d").date()
    hoje = date.today()
    dias_atraso = (hoje - due).days

    if dias_atraso > 0:
        return (
            f"Olá {client_name}! 👋\n\n"
            f"Seu empréstimo está em atraso há *{dias_atraso} dia(s)*.\n"
            f"💰 Saldo devedor: *R$ {saldo:,.2f}*\n"
            f"📅 Vencimento: {due.strftime('%d/%m/%Y')}\n\n"
            f"Entre em contato para regularizar. Obrigado!"
        )
    else:
        return (
            f"Olá {client_name}! 👋\n\n"
            f"Seu empréstimo vence *hoje ({due.strftime('%d/%m/%Y')})*.\n"
            f"💰 Saldo devedor: *R$ {saldo:,.2f}*\n\n"
            f"Aguardamos seu pagamento. Obrigado!"
        )


def already_notified_today(loan_id: str, today: str) -> bool:
    """Verifica se já foi enviada notificação hoje para este empréstimo."""
    r = supabase.table("notification_logs") \
        .select("id") \
        .eq("loan_id", loan_id) \
        .gte("sent_at", f"{today}T00:00:00") \
        .execute()
    return bool(r.data)


def main():
    today = date.today().isoformat()
    print(f"--- Job de Cobrança: {today} ---")

    # Busca empréstimos atrasados + vencendo hoje (status pendente ou atrasado)
    response = supabase.table("loans") \
        .select("*, clients(name, phone)") \
        .in_("status", ["pendente", "atrasado"]) \
        .lte("due_date", today) \
        .execute()

    loans = response.data or []
    print(f"Contratos encontrados: {len(loans)}")

    enviados, pulados, erros = 0, 0, 0

    for loan in loans:
        loan_id = loan["id"]
        client = loan.get("clients")

        if not client or not client.get("phone"):
            print(f"  [AVISO] Empréstimo {loan_id} sem cliente/telefone. Pulando.")
            pulados += 1
            continue

        if already_notified_today(loan_id, today):
            print(f"  [PULADO] {client['name']} já notificado hoje.")
            pulados += 1
            continue

        message = build_message(client["name"], loan)
        print(f"  Enviando para {client['name']} ({client['phone']})...")

        success = send_whatsapp(client["phone"], message)

        log_status = "success" if success else "error"
        supabase.table("notification_logs").insert({
            "loan_id": loan_id,
            "status": log_status,
        }).execute()

        if success:
            enviados += 1
            print(f"  [OK] Mensagem enviada e logada.")
        else:
            erros += 1

    print(f"\n--- Resultado: {enviados} enviados | {pulados} pulados | {erros} erros ---")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erro fatal: {e}")
        exit(1)
