import os
import requests
from supabase import create_client, Client
from datetime import datetime, date

# Carrega variáveis de ambiente (útil para teste local, no GitHub Actions elas são injetadas)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# CONFIGURAÇÕES
SUPABASE_URL = os.getenv("SUPABASE_URL")
# IMPORTANTE: Use a SERVICE_ROLE_KEY aqui para ignorar RLS e ler todos os dados
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") 

API_WHATSAPP_URL = os.getenv("WHATSAPP_API_URL")
API_WHATSAPP_KEY = os.getenv("WHATSAPP_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Variáveis de ambiente do Supabase não configuradas.")

# Inicializa Cliente
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def send_whatsapp_message(phone, message):
    """
    Função genérica para envio de mensagem.
    Adapte o payload conforme a API que você contratar (Twilio, Z-API, WppConnect, etc).
    """
    if not API_WHATSAPP_URL:
        print(f"[SIMULAÇÃO] Enviando para {phone}: {message}")
        return True

    headers = {
        "Authorization": f"Bearer {API_WHATSAPP_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "phone": phone,
        "message": message
    }
    
    try:
        response = requests.post(API_WHATSAPP_URL, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Erro ao enviar mensagem para {phone}: {e}")
        return False

def main():
    print("--- Iniciando Job de Cobrança ---")
    today = date.today().isoformat()
    
    # 1. Buscar empréstimos pendentes vencidos ou vencendo hoje
    # Precisamos fazer um join manual ou buscar dados relacionados.
    # O Supabase permite selecionar tabelas relacionadas se houver Foreign Key.
    response = supabase.table("loans") \
        .select("*, clients(name, phone)") \
        .eq("status", "pendente") \
        .lte("due_date", today) \
        .execute()
    
    loans = response.data
    print(f"Encontrados {len(loans)} empréstimos com vencimento <= {today}")

    for loan in loans:
        loan_id = loan['id']
        client = loan['clients']
        
        if not client:
            print(f"Erro: Empréstimo {loan_id} sem cliente associado.")
            continue

        # 2. Verificar se já enviamos mensagem HOJE para este empréstimo
        log_check = supabase.table("notification_logs") \
            .select("sent_at") \
            .eq("loan_id", loan_id) \
            .gte("sent_at", f"{today}T00:00:00") \
            .execute()
            
        if log_check.data:
            print(f"Log: Cliente {client['name']} já notificado hoje. Pulando.")
            continue

        # 3. Preparar Mensagem
        valor = float(loan['amount'])
        msg_text = (
            f"Olá {client['name']}, notamos que seu empréstimo de R$ {valor:.2f} "
            f"vence em {loan['due_date']}. Por favor, regularize sua situação."
        )

        # 4. Enviar e Logar
        print(f"Processando: {client['name']}...")
        success = send_whatsapp_message(client['phone'], msg_text)
        
        if success:
            supabase.table("notification_logs").insert({
                "loan_id": loan_id,
                "status": "success"
            }).execute()
            print(f"Sucesso: Mensagem enviada e logada para {client['name']}")
        else:
            print(f"Falha: Não foi possível notificar {client['name']}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Erro fatal no script: {e}")
        exit(1)