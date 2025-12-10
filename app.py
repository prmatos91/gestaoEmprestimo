import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date
import re

# --- 1. CONFIGURAÇÃO INICIAL E VALIDADORES ---
st.set_page_config(page_title="Sistema de Gestão de Empréstimos", layout="wide", page_icon="🏦")

# Validadores (Regex e Algoritmos)
def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    # Aceita formatos limpos: 11999999999
    # Remove tudo que não é dígito
    nums = re.sub(r'\D', '', phone)
    # Verifica se tem 11 dígitos e se o terceiro dígito é 9
    return len(nums) == 11 and nums[2] == '9'

def validate_cpf(cpf):
    # Remove caracteres não numéricos
    cpf = re.sub(r'\D', '', cpf)
    
    if len(cpf) != 11 or cpf == cpf[0] * 11: return False
    
    # Validação do 1º Dígito
    sum_ = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digit1 = (sum_ * 10 % 11)
    if digit1 == 10: digit1 = 0
    if digit1 != int(cpf[9]): return False
    
    # Validação do 2º Dígito
    sum_ = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digit2 = (sum_ * 10 % 11)
    if digit2 == 10: digit2 = 0
    if digit2 != int(cpf[10]): return False
    
    return True

# Conexão Supabase
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Erro Crítico: Configure as chaves no .streamlit/secrets.toml")
    st.stop()

# --- 2. SESSÃO E AUTH ---
def init_session():
    if 'session' not in st.session_state: st.session_state.session = None
    if 'user' not in st.session_state: st.session_state.user = None
    if 'role' not in st.session_state: st.session_state.role = None
    
    if st.session_state.session:
        try:
            supabase.auth.set_session(
                access_token=st.session_state.session.access_token,
                refresh_token=st.session_state.session.refresh_token
            )
        except: logout()

def login(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.session = res.session
        st.session_state.user = res.user
        try:
            data = supabase.table("profiles").select("role").eq("id", res.user.id).execute()
            st.session_state.role = data.data[0]['role'] if data.data else 'employee'
        except: st.session_state.role = 'employee'
        st.rerun()
    except: st.error("Email ou senha incorretos.")

def logout():
    supabase.auth.sign_out()
    st.session_state.session = None; st.session_state.user = None; st.session_state.role = None
    st.rerun()

# --- 3. HELPER FUNCTIONS ---
def upload_document(file, client_id):
    try:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', file.name)
        path = f"{client_id}/{datetime.now().timestamp()}_{clean_name}"
        supabase.storage.from_("documents").upload(path, file.getvalue(), {"content-type": file.type})
        return supabase.storage.from_("documents").get_public_url(path), file.name
    except: return None, None

def get_reputation_badge(status):
    if status == 'BOM': return "🟢 Bom Pagador"
    elif status == 'RUIM': return "🔴 Inadimplente"
    return "⚪ Neutro"

# --- 4. APLICAÇÃO ---
init_session()

if not st.session_state.user:
    # TELA DE LOGIN
    st.markdown("<h1 style='text-align: center;'>🏦 LoanManager System</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            if st.form_submit_button("Acessar Sistema", use_container_width=True):
                login(email, password)
else:
    # LAYOUT LOGADO
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.sidebar.title(f"Olá, {st.session_state.role}")
    
    menu = st.sidebar.radio("Navegação", 
        ["Painel Financeiro", "Baixa de Pagamentos", "Novo Contrato", "Cadastrar Cliente", "Base de Clientes"]
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"): logout()

    # ---------------------------------------------------------
    # ABA 1: PAINEL FINANCEIRO (COM FILTROS)
    # ---------------------------------------------------------
    if menu == "Painel Financeiro":
        st.title("📊 Painel Financeiro")
        
        # --- FILTROS ---
        with st.expander("🔍 Filtros de Visualização", expanded=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                # Filtro de Data (Padrão: Últimos 30 dias até hoje)
                date_range = st.date_input("Período de Vencimento", 
                                         value=(date(date.today().year, 1, 1), date.today()),
                                         format="DD/MM/YYYY")
            with col_f2:
                # Busca clientes para o multiselect
                all_clients = supabase.table("clients").select("id, name").execute().data
                client_options = {c['name']: c['id'] for c in all_clients} if all_clients else {}
                selected_clients = st.multiselect("Filtrar por Clientes", list(client_options.keys()))

        # --- BUSCA DADOS ---
        # Query base
        query = supabase.table("loans").select("*")
        
        # Aplica Filtros no Banco (Server-side) ou Pandas (Client-side)
        # Vamos trazer tudo e filtrar no Pandas para facilitar a flexibilidade de datas
        loans_data = query.execute().data
        
        if loans_data:
            df = pd.DataFrame(loans_data)
            df['due_date'] = pd.to_datetime(df['due_date']).dt.date

            # Aplica Filtro de Data
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
                df = df[(df['due_date'] >= start_date) & (df['due_date'] <= end_date)]

            # Aplica Filtro de Cliente
            if selected_clients:
                selected_ids = [client_options[name] for name in selected_clients]
                df = df[df['client_id'].isin(selected_ids)]

            if df.empty:
                st.warning("Nenhum dado encontrado para os filtros selecionados.")
            else:
                # Cálculos KPI
                total_orig = df['original_amount'].sum()
                total_dev = df['remaining_amount'].sum()
                df['juros_valor'] = df['original_amount'] * (df['interest_rate'] / 100)
                receita_prevista = df['juros_valor'].sum()
                recebido = total_orig - total_dev # Simplificação

                # Visual KPI
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Carteira (Período)", f"R$ {total_orig:,.2f}")
                k2.metric("A Receber", f"R$ {total_dev:,.2f}")
                k3.metric("Juros Previstos", f"R$ {receita_prevista:,.2f}", delta="Lucro Bruto")
                k4.metric("Contratos", len(df))

                st.divider()
                st.subheader("Detalhamento")
                
                # Tabela estilizada
                grid = df[['due_date', 'original_amount', 'remaining_amount', 'status']].copy()
                grid.columns = ['Vencimento', 'Valor Original', 'Saldo Devedor', 'Status']
                
                # Colorir status
                def color_status(val):
                    color = '#d4edda' if val == 'pago' else '#f8d7da' if val == 'atrasado' else '#fff3cd'
                    return f'background-color: {color}; color: black'
                
                st.dataframe(grid.style.applymap(color_status, subset=['Status']).format({
                    'Valor Original': 'R$ {:.2f}',
                    'Saldo Devedor': 'R$ {:.2f}'
                }), use_container_width=True)
        else:
            st.info("Nenhum empréstimo registrado no sistema.")

    # ---------------------------------------------------------
    # ABA 2: BAIXA DE PAGAMENTOS (INTUITIVA & VALIDADA)
    # ---------------------------------------------------------
    elif menu == "Baixa de Pagamentos":
        st.title("💸 Registrar Pagamento")
        
        # 1. Busca
        search = st.text_input("Buscar Cliente (Nome ou CPF)", placeholder="Digite para pesquisar...")
        
        target_ids = []
        if search:
            # Busca Clientes
            cli_resp = supabase.table("clients").select("id").or_(f"name.ilike.%{search}%,cpf.ilike.%{search}%").execute()
            target_ids = [c['id'] for c in cli_resp.data]
            if not target_ids: st.warning("Cliente não encontrado."); st.stop()

        # 2. Query Empréstimos
        q = supabase.table("loans").select("*, clients(name, cpf)").neq("status", "pago")
        if target_ids: q = q.in_("client_id", target_ids)
        loans = q.execute().data

        if not loans:
            st.info("Nenhum contrato pendente encontrado.")
        else:
            # Mapeia para seleção amigável
            loan_opts = {f"{l['clients']['name']} - Vence: {l['due_date']} (Saldo: R$ {l['remaining_amount']})": l for l in loans}
            sel_key = st.selectbox("Selecione o Contrato", list(loan_opts.keys()))
            data = loan_opts[sel_key]

            # 3. CARD DE INFORMAÇÕES (Visual Intuitivo)
            juros_calc = float(data['original_amount']) * (float(data['interest_rate']) / 100)
            saldo_atual = float(data['remaining_amount'])
            quitacao_total = saldo_atual + juros_calc

            st.markdown(f"""
            <div style="background-color: #262730; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #444;">
                <h3 style="margin:0; color: #fff">{data['clients']['name']}</h3>
                <p style="color: #aaa; margin:0">CPF: {data['clients']['cpf']}</p>
                <hr style="border-color: #555;">
                <div style="display: flex; justify-content: space-between;">
                    <div><span style="color:#aaa">Saldo Principal:</span> <br><strong style="font-size:1.2em">R$ {saldo_atual:,.2f}</strong></div>
                    <div><span style="color:#aaa">Juros Mensal:</span> <br><strong style="font-size:1.2em; color: #ffbd45">R$ {juros_calc:,.2f}</strong></div>
                    <div><span style="color:#aaa">Total p/ Quitar:</span> <br><strong style="font-size:1.2em; color: #4CAF50">R$ {quitacao_total:,.2f}</strong></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 4. FORMULÁRIO INTELIGENTE
            # Usamos radio para definir a lógica de preenchimento
            pay_mode = st.radio("O que o cliente vai pagar?", 
                              ["Somente Juros", "Juros + Amortização", "Quitação Total"], 
                              horizontal=True)
            
            # Lógica de Valores Sugeridos
            val_sugerido = 0.0
            msg_ajuda = ""
            
            if pay_mode == "Somente Juros":
                val_sugerido = juros_calc
                msg_ajuda = "Cliente paga apenas o aluguel do dinheiro. Saldo não diminui."
            elif pay_mode == "Juros + Amortização":
                val_sugerido = juros_calc + 50.0 # Sugere juros + um pouco
                msg_ajuda = "O valor deve cobrir o Juros e o restante abate do Principal."
            else:
                val_sugerido = quitacao_total
                msg_ajuda = "Encerra o contrato."

            # Inputs
            c1, c2 = st.columns(2)
            with c1:
                dt_pay = st.date_input("Data do Pagamento", value=date.today(), format="DD/MM/YYYY")
            with c2:
                # number_input não atualiza value dinamicamente bem dentro de forms complexos,
                # mas como o layout recarrega ao mudar o radio (st.radio sem form), funciona.
                val_input = st.number_input("Valor Recebido (R$)", 
                                          min_value=0.0, 
                                          value=val_sugerido, 
                                          step=10.0,
                                          help=msg_ajuda)

            # Botão de Ação Fora do Form para controle total
            if st.button("Confirmar Baixa do Pagamento", type="primary"):
                erro = None
                
                # --- VALIDAÇÕES DE REGRA DE NEGÓCIO ---
                if pay_mode == "Somente Juros":
                    # Aceitamos valor maior ou igual ao juros (as vezes paga adiantado, mas vamos travar no juros exato ou maior)
                    if val_input < (juros_calc - 0.1): # Margem de erro float
                        erro = f"Para pagar juros, o valor deve ser no mínimo R$ {juros_calc:.2f}"
                
                elif pay_mode == "Juros + Amortização":
                    if val_input <= juros_calc:
                        erro = f"Para amortizar, o valor deve ser MAIOR que o juros (R$ {juros_calc:.2f})."
                
                elif pay_mode == "Quitação Total":
                    if val_input < (quitacao_total - 1.0):
                        erro = f"Para quitar, o valor deve ser R$ {quitacao_total:.2f}"

                if erro:
                    st.error(erro)
                else:
                    try:
                        # 1. Atualizar Reputação
                        due = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
                        new_rep = 'BOM' if dt_pay <= due else 'RUIM'
                        supabase.table("clients").update({"reputation": new_rep}).eq("id", data['clients']['id']).execute()

                        # 2. Salvar Pagamento
                        tipo_db = "JUROS" if pay_mode == "Somente Juros" else "AMORTIZACAO" if pay_mode == "Juros + Amortização" else "QUITACAO"
                        
                        supabase.table("payments").insert({
                            "loan_id": data['id'], "amount": val_input, "payment_type": tipo_db,
                            "paid_at": str(dt_pay), "owner_id": st.session_state.user.id
                        }).execute()

                        # 3. Abater Saldo
                        novo_saldo = saldo_atual
                        novo_status = 'pendente'

                        if pay_mode == "Somente Juros":
                            pass # Não mexe no saldo
                        elif pay_mode == "Juros + Amortização":
                            amortizacao = val_input - juros_calc
                            novo_saldo -= amortizacao
                        elif pay_mode == "Quitação Total":
                            novo_saldo = 0

                        if novo_saldo <= 0.5: # Margem de segurança
                            novo_saldo = 0
                            novo_status = 'pago'

                        supabase.table("loans").update({"remaining_amount": novo_saldo, "status": novo_status}).eq("id", data['id']).execute()
                        
                        st.balloons()
                        st.success("Pagamento registrado com sucesso!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro técnico: {e}")

    # ---------------------------------------------------------
    # ABA 3: NOVO CONTRATO
    # ---------------------------------------------------------
    elif menu == "Novo Contrato":
        st.title("💰 Novo Contrato")
        try:
            # Busca clientes
            resp = supabase.table("clients").select("id, name, cpf, reputation").execute()
            # Ordena por nome
            clients_list = sorted(resp.data, key=lambda x: x['name'])
            cli_map = {f"{c['name']} (CPF: {c['cpf']})": c['id'] for c in clients_list}
        except: cli_map = {}

        if not cli_map:
            st.warning("Cadastre clientes antes.")
        else:
            with st.form("new_loan"):
                sel_cli = st.selectbox("Cliente", list(cli_map.keys()))
                c1, c2 = st.columns(2)
                with c1:
                    val = st.number_input("Valor Principal (R$)", min_value=50.0, step=50.0)
                    rate = st.number_input("Taxa de Juros (%)", value=10.0, step=0.5)
                with c2:
                    due = st.date_input("Data 1º Vencimento", value=date.today(), format="DD/MM/YYYY")
                
                if st.form_submit_button("Criar Contrato"):
                    supabase.table("loans").insert({
                        "client_id": cli_map[sel_cli],
                        "original_amount": val,
                        "remaining_amount": val,
                        "interest_rate": rate,
                        "due_date": str(due),
                        "owner_id": st.session_state.user.id
                    }).execute()
                    st.success("Contrato Gerado!")

    # ---------------------------------------------------------
    # ABA 4: CADASTRAR CLIENTE (COM VALIDAÇÃO)
    # ---------------------------------------------------------
    elif menu == "Cadastrar Cliente":
        st.title("👤 Novo Cliente")
        st.info("Todos os campos com * são obrigatórios.")

        with st.form("new_client"):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Nome Completo *")
                cpf = st.text_input("CPF *", placeholder="Apenas números", max_chars=14)
                phone = st.text_input("Celular *", placeholder="11999999999", help="DDD + 9 Dígitos")
                ref = st.text_input("Referência Pessoal *")
            with c2:
                rg = st.text_input("RG")
                email = st.text_input("E-mail")
                addr = st.text_area("Endereço Completo *")
            
            files = st.file_uploader("Documentos", accept_multiple_files=True)
            
            if st.form_submit_button("Salvar Cadastro"):
                # --- VALIDAÇÃO ---
                errors = []
                if not (name and cpf and phone and addr and ref):
                    errors.append("Preencha todos os campos obrigatórios (*).")
                
                if cpf and not validate_cpf(cpf):
                    errors.append("CPF inválido. Verifique os dígitos.")
                
                if phone and not validate_phone(phone):
                    errors.append("Telefone inválido. Formato esperado: 11999999999 (DDD + 9 na frente + 8 números).")
                
                if email and not validate_email(email):
                    errors.append("E-mail inválido.")

                if errors:
                    for e in errors: st.error(e)
                else:
                    # Sucesso
                    try:
                        clean_cpf = re.sub(r'\D', '', cpf) # Salva limpo
                        clean_phone = re.sub(r'\D', '', phone) # Salva limpo
                        
                        res = supabase.table("clients").insert({
                            "name": name, "cpf": clean_cpf, "rg": rg, 
                            "phone": clean_phone, "email": email,
                            "address": addr, "reference_contact": ref, 
                            "reputation": "NEUTRO",
                            "owner_id": st.session_state.user.id
                        }).execute()
                        
                        if res.data:
                            cid = res.data[0]['id']
                            if files:
                                for f in files:
                                    u, n = upload_document(f, cid)
                                    if u: supabase.table("client_documents").insert({"client_id":cid,"file_name":n,"file_url":u}).execute()
                            st.success(f"Cliente {name} cadastrado com sucesso!")
                    except Exception as e:
                        # Tratamento para erro de CPF duplicado (Constraint do banco se houver)
                        if "duplicate key" in str(e):
                            st.error("Erro: Este CPF já está cadastrado no sistema.")
                        else:
                            st.error(f"Erro ao salvar: {e}")

    # ---------------------------------------------------------
    # ABA 5: BASE DE CLIENTES
    # ---------------------------------------------------------
    elif menu == "Base de Clientes":
        st.title("📂 Carteira de Clientes")
        
        search = st.text_input("🔍 Buscar (Nome ou CPF)", placeholder="Digite...")
        
        q = supabase.table("clients").select("*")
        if search: q = q.or_(f"name.ilike.%{search}%,cpf.ilike.%{search}%")
        clients = q.execute().data

        if clients:
            for c in clients:
                rep = c.get('reputation', 'NEUTRO')
                icon = "🟢" if rep == 'BOM' else "🔴" if rep == 'RUIM' else "⚪"
                
                with st.expander(f"{icon} {c['name']} (CPF: {c['cpf']})"):
                    # Formata CPF e Fone para visualização
                    fmt_cpf = f"{c['cpf'][:3]}.{c['cpf'][3:6]}.{c['cpf'][6:9]}-{c['cpf'][9:]}" if len(c['cpf'])==11 else c['cpf']
                    
                    c1, c2 = st.columns(2)
                    c1.write(f"**📱 Cel:** {c['phone']}")
                    c2.write(f"**📍 End:** {c['address']}")
                    st.write(f"**📧 Email:** {c.get('email','-')}")

                    loans = supabase.table("loans").select("*").eq("client_id", c['id']).execute().data
                    if loans:
                        st.subheader("Histórico")
                        df_h = pd.DataFrame(loans)
                        # Tradução
                        df_h = df_h[['due_date', 'original_amount', 'remaining_amount', 'status']].rename(columns={
                            'due_date': 'Vencimento', 'original_amount': 'Tomado', 'remaining_amount': 'Devendo', 'status': 'Status'
                        })
                        st.dataframe(df_h, use_container_width=True)
                        
                        # Botão de Log
                        if st.button("Ver Extrato de Pagamentos", key=f"btn_{c['id']}"):
                            ids = [l['id'] for l in loans]
                            logs = supabase.table("payments").select("*, profiles(email)").in_("loan_id", ids).order("paid_at", desc=True).execute().data
                            if logs:
                                data_log = [{"Data": p['paid_at'], "Valor": p['amount'], "Tipo": p['payment_type'], "Resp": p['profiles']['email']} for p in logs]
                                st.table(data_log)
                            else:
                                st.info("Sem pagamentos registrados.")
                    else:
                        st.info("Sem contratos.")
                    
                    docs = supabase.table("client_documents").select("*").eq("client_id", c['id']).execute().data
                    if docs:
                        st.markdown("**Documentos:**")
                        for d in docs: st.markdown(f"[{d['file_name']}]({d['file_url']})")
        else:
            st.info("Nenhum cliente encontrado.")