import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

# --- Configuração Inicial ---
st.set_page_config(page_title="Sistema de Gestão de Empréstimos", layout="wide")

# Conexão com Supabase (Pegando de st.secrets para segurança em prod)
# Em desenvolvimento local, crie um arquivo .streamlit/secrets.toml
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# --- Funções Auxiliares ---
def init_session():
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'role' not in st.session_state:
        st.session_state.role = None

def login(email, password):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = response.user
        
        # Buscar Role do usuário
        data = supabase.table("profiles").select("role").eq("id", response.user.id).execute()
        if data.data:
            st.session_state.role = data.data[0]['role']
        st.success("Login realizado com sucesso!")
        st.rerun()
    except Exception as e:
        st.error(f"Erro no login: {e}")

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.role = None
    st.rerun()

def upload_document(file, client_name):
    try:
        # Cria um nome único para o arquivo
        file_ext = file.name.split('.')[-1]
        file_name = f"{client_name}_{datetime.now().timestamp()}.{file_ext}".replace(" ", "_")
        
        # Upload para o bucket 'documents'
        res = supabase.storage.from_("documents").upload(file_name, file.getvalue(), {"content-type": file.type})
        
        # Pegar URL Pública
        public_url = supabase.storage.from_("documents").get_public_url(file_name)
        return public_url
    except Exception as e:
        st.error(f"Erro no upload: {e}")
        return None

# --- Interface Principal ---
init_session()

if not st.session_state.user:
    # Tela de Login
    st.title("🔐 Acesso ao Sistema")
    email = st.text_input("Email")
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        login(email, password)
else:
    # Área Logada
    st.sidebar.title(f"Olá, {st.session_state.role}")
    if st.sidebar.button("Sair"):
        logout()
    
    menu = st.sidebar.radio("Navegação", ["Dashboard", "Cadastrar Cliente", "Novo Empréstimo", "Meus Clientes"])

    # 1. Dashboard
    if menu == "Dashboard":
        st.title("📊 Resumo Financeiro")
        
        # Admin vê tudo, Employee vê só os seus (Graças ao RLS do Supabase, a query é a mesma)
        loans_query = supabase.table("loans").select("*").execute()
        df_loans = pd.DataFrame(loans_query.data)

        if not df_loans.empty:
            total_emprestado = df_loans['amount'].sum()
            # Cálculo simples de juros previstos (Montante = Capital * (1 + taxa/100))
            # Ajuste a fórmula conforme seu modelo de negócio (juros simples vs compostos)
            df_loans['previsto'] = df_loans['amount'] * (1 + df_loans['interest_rate'] / 100)
            total_previsto = df_loans['previsto'].sum()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Emprestado", f"R$ {total_emprestado:,.2f}")
            col2.metric("Retorno Previsto", f"R$ {total_previsto:,.2f}")
            col3.metric("Contratos Ativos", len(df_loans))
            
            st.subheader("Empréstimos Recentes")
            st.dataframe(df_loans[['amount', 'due_date', 'status']])
        else:
            st.info("Nenhum empréstimo registrado.")

    # 2. Cadastro de Cliente
    elif menu == "Cadastrar Cliente":
        st.title("👤 Novo Cliente")
        with st.form("client_form"):
            name = st.text_input("Nome Completo")
            phone = st.text_input("Telefone (com DDD e DDI, ex: +5511...)", help="Essencial para automação")
            doc_file = st.file_uploader("Documento (PDF/IMG)", type=['pdf', 'png', 'jpg'])
            
            submitted = st.form_submit_button("Cadastrar")
            if submitted and name and phone:
                doc_url = None
                if doc_file:
                    with st.spinner("Enviando documento..."):
                        doc_url = upload_document(doc_file, name)
                
                data = {
                    "name": name, 
                    "phone": phone, 
                    "doc_url": doc_url,
                    "owner_id": st.session_state.user.id
                }
                supabase.table("clients").insert(data).execute()
                st.success("Cliente cadastrado!")

    # 3. Novo Empréstimo
    elif menu == "Novo Empréstimo":
        st.title("💰 Conceder Empréstimo")
        
        # Buscar clientes para o selectbox
        clients = supabase.table("clients").select("id, name").execute()
        client_options = {c['name']: c['id'] for c in clients.data}
        
        if not client_options:
            st.warning("Cadastre clientes antes de criar empréstimos.")
        else:
            with st.form("loan_form"):
                selected_client = st.selectbox("Cliente", list(client_options.keys()))
                amount = st.number_input("Valor (R$)", min_value=0.0, step=100.0)
                interest = st.number_input("Juros (%)", min_value=0.0, step=0.5)
                due_date = st.date_input("Data de Vencimento")
                
                if st.form_submit_button("Salvar Empréstimo"):
                    loan_data = {
                        "client_id": client_options[selected_client],
                        "amount": amount,
                        "interest_rate": interest,
                        "due_date": str(due_date),
                        "owner_id": st.session_state.user.id
                    }
                    supabase.table("loans").insert(loan_data).execute()
                    st.success("Empréstimo registrado!")

    # 4. Listagem
    elif menu == "Meus Clientes":
        st.title("📂 Base de Clientes")
        clients = supabase.table("clients").select("*").execute()
        if clients.data:
            for c in clients.data:
                with st.expander(f"{c['name']} - {c['phone']}"):
                    st.write(f"ID: {c['id']}")
                    if c.get('doc_url'):
                        st.markdown(f"[Ver Documento]({c['doc_url']})")
        else:
            st.info("Sem clientes cadastrados.")