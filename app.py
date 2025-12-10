import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date
import re

# --- 1. CONFIGURAÇÃO INICIAL E VALIDADORES ---
st.set_page_config(page_title="Sistema de Gestão de Empréstimos", layout="wide", page_icon="🏦")

# --- Validadores ---
def validate_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def validate_phone(phone):
    # Aceita apenas números, deve ter 11 dígitos e o 3º ser 9 (11 9xxxx-xxxx)
    nums = re.sub(r'\D', '', phone)
    return len(nums) == 11 and nums[2] == '9'

def validate_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11: return False
    sum_ = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = (sum_ * 10 % 11); d1 = 0 if d1 == 10 else d1
    if d1 != int(cpf[9]): return False
    sum_ = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = (sum_ * 10 % 11); d2 = 0 if d2 == 10 else d2
    return d2 == int(cpf[10])

# --- Conexão Supabase ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Erro: Configure .streamlit/secrets.toml")
    st.stop()

# --- 2. SESSÃO ---
def init_session():
    if 'session' not in st.session_state: st.session_state.session = None
    if 'user' not in st.session_state: st.session_state.user = None
    if 'role' not in st.session_state: st.session_state.role = None
    if st.session_state.session:
        try:
            supabase.auth.set_session(st.session_state.session.access_token, st.session_state.session.refresh_token)
        except: logout()

def login(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.session = res.session
        st.session_state.user = res.user
        try:
            d = supabase.table("profiles").select("role").eq("id", res.user.id).execute()
            st.session_state.role = d.data[0]['role'] if d.data else 'employee'
        except: st.session_state.role = 'employee'
        st.rerun()
    except: st.error("Credenciais inválidas.")

def logout():
    supabase.auth.sign_out()
    st.session_state.session = None; st.session_state.user = None; st.session_state.role = None
    st.rerun()

# --- 3. UPLOAD ---
def upload_file(file, folder="docs"):
    try:
        ext = file.name.split('.')[-1]
        name = f"{folder}/{datetime.now().timestamp()}_{file.name.replace(' ', '_')}"
        supabase.storage.from_("documents").upload(name, file.getvalue(), {"content-type": file.type})
        return supabase.storage.from_("documents").get_public_url(name), file.name
    except: return None, None

# --- 4. APP PRINCIPAL ---
init_session()

if not st.session_state.user:
    st.markdown("<h1 style='text-align: center;'>🏦 LoanManager System</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            email = st.text_input("E-mail"); password = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True): login(email, password)
else:
    st.sidebar.title(f"Olá, {st.session_state.role}")
    menu = st.sidebar.radio("Menu", ["Painel Financeiro", "Baixa de Pagamentos", "Novo Contrato", "Cadastrar Cliente", "Base de Clientes"])
    st.sidebar.divider()
    if st.sidebar.button("Sair"): logout()

    # --- 1. PAINEL FINANCEIRO ---
    if menu == "Painel Financeiro":
        st.title("📊 Painel Financeiro")
        with st.expander("🔍 Filtros", expanded=True):
            c1, c2 = st.columns(2)
            dr = c1.date_input("Período (Vencimento)", (date(date.today().year, 1, 1), date.today()), format="DD/MM/YYYY")
            clients = supabase.table("clients").select("id, name").execute().data
            cli_opts = {c['name']:c['id'] for c in clients} if clients else {}
            sel_cli = c2.multiselect("Clientes", list(cli_opts.keys()))

        data = supabase.table("loans").select("*").execute().data
        if data:
            df = pd.DataFrame(data)
            df['due_date_dt'] = pd.to_datetime(df['due_date']).dt.date
            
            # Filtros
            if len(dr) == 2: df = df[(df['due_date_dt'] >= dr[0]) & (df['due_date_dt'] <= dr[1])]
            if sel_cli: df = df[df['client_id'].isin([cli_opts[n] for n in sel_cli])]

            if not df.empty:
                # KPIs
                tot_orig = df['original_amount'].sum()
                tot_dev = df['remaining_amount'].sum()
                juros_prev = (df['original_amount'] * (df['interest_rate']/100)).sum()
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Total Emprestado", f"R$ {tot_orig:,.2f}")
                k2.metric("Saldo a Receber", f"R$ {tot_dev:,.2f}")
                k3.metric("Lucro Juros Previsto", f"R$ {juros_prev:,.2f}")
                
                # Tabela Formatada
                st.divider()
                grid = df[['due_date_dt', 'original_amount', 'remaining_amount', 'status']].copy()
                # Formata data para string BR
                grid['due_date_dt'] = grid['due_date_dt'].apply(lambda x: x.strftime('%d/%m/%Y'))
                grid.columns = ['Vencimento', 'Valor Original', 'Saldo Devedor', 'Status']
                
                def color(v): return f"background-color: {'#d4edda' if v=='pago' else '#f8d7da' if v=='atrasado' else '#fff3cd'}; color: black"
                st.dataframe(grid.style.map(color, subset=['Status']).format({'Valor Original': 'R$ {:.2f}', 'Saldo Devedor': 'R$ {:.2f}'}), use_container_width=True)
            else: st.warning("Sem dados para o filtro.")
        else: st.info("Sem empréstimos.")

    # --- 2. BAIXA DE PAGAMENTOS (AJUSTADA) ---
    elif menu == "Baixa de Pagamentos":
        st.title("💸 Registrar Pagamento")
        search = st.text_input("Buscar (Nome/CPF)")
        
        target_ids = []
        if search:
            r = supabase.table("clients").select("id").or_(f"name.ilike.%{search}%,cpf.ilike.%{search}%").execute()
            target_ids = [x['id'] for x in r.data]
            if not target_ids: st.warning("Não encontrado."); st.stop()

        q = supabase.table("loans").select("*, clients(name, cpf)").neq("status", "pago")
        if target_ids: q = q.in_("client_id", target_ids)
        loans = q.execute().data

        if loans:
            opts = {f"{l['clients']['name']} | Vence: {datetime.strptime(l['due_date'], '%Y-%m-%d').strftime('%d/%m/%Y')}": l for l in loans}
            sel = st.selectbox("Selecione o Contrato", list(opts.keys()))
            d = opts[sel]

            # Cálculos
            juros = float(d['original_amount']) * (float(d['interest_rate'])/100)
            saldo = float(d['remaining_amount'])
            total_quit = saldo + juros

            # Card Informativo
            st.info(f"""
            **Resumo do Contrato:**
            - 💰 Saldo Devedor (Principal): **R$ {saldo:,.2f}**
            - 📈 Juros da Parcela: **R$ {juros:,.2f}**
            - 🏁 Total para Quitação Hoje: **R$ {total_quit:,.2f}**
            """)

            with st.form("pay"):
                mode = st.radio("Tipo de Pagamento", ["Somente Juros", "Juros + Amortização", "Quitação Total"], horizontal=True)
                
                # Definição de valor sugerido
                val_sug = juros if mode == "Somente Juros" else (juros + 100) if mode == "Juros + Amortização" else total_quit
                
                c1, c2 = st.columns(2)
                dt = c1.date_input("Data Pagamento", date.today(), format="DD/MM/YYYY")
                val = c2.number_input("Valor Recebido (R$)", min_value=0.0, value=val_sug, step=10.0)
                
                # Upload Comprovante
                proof = st.file_uploader("Anexar Comprovante (Opcional)", type=['jpg','png','pdf'])

                if st.form_submit_button("Confirmar Baixa", type="primary"):
                    err = None
                    
                    # --- VALIDAÇÕES ESTRITAS ---
                    if mode == "Somente Juros":
                        if val < (juros - 0.1): err = f"Valor insuficiente. Mínimo para juros: R$ {juros:,.2f}"
                    
                    elif mode == "Juros + Amortização":
                        # AQUI ESTÁ A TRAVA: Deve pagar o juros E sobrar algo
                        if val <= juros:
                            err = f"ERRO: O valor (R$ {val}) cobre apenas o juros ou menos. Para amortizar, precisa ser MAIOR que R$ {juros:,.2f}."
                    
                    elif mode == "Quitação Total":
                        if val < (total_quit - 1.0): err = f"Para quitar, o valor deve ser R$ {total_quit:,.2f}"

                    if err: st.error(err)
                    else:
                        try:
                            # 1. Upload Comprovante
                            proof_url = None
                            if proof:
                                proof_url, _ = upload_file(proof, f"proofs/{d['id']}")

                            # 2. Reputação
                            due_dt = datetime.strptime(d['due_date'], '%Y-%m-%d').date()
                            rep = 'BOM' if dt <= due_dt else 'RUIM'
                            supabase.table("clients").update({"reputation": rep}).eq("id", d['client_id']).execute()

                            # 3. Insert Pagamento
                            type_db = "JUROS" if mode == "Somente Juros" else "AMORTIZACAO" if mode == "Juros + Amortização" else "QUITACAO"
                            supabase.table("payments").insert({
                                "loan_id": d['id'], "amount": val, "payment_type": type_db,
                                "paid_at": str(dt), "owner_id": st.session_state.user.id,
                                "proof_url": proof_url
                            }).execute()

                            # 4. Atualizar Saldo
                            new_bal = saldo
                            if mode == "Juros + Amortização": new_bal -= (val - juros)
                            elif mode == "Quitação Total": new_bal = 0
                            
                            stt = 'pago' if new_bal <= 0.5 else 'pendente'
                            supabase.table("loans").update({"remaining_amount": new_bal, "status": stt}).eq("id", d['id']).execute()
                            
                            st.balloons()
                            st.success("Pagamento registrado!")
                            st.rerun()
                        except Exception as e: st.error(f"Erro: {e}")
        else: st.info("Nada pendente.")

    # --- 3. NOVO CONTRATO ---
    elif menu == "Novo Contrato":
        st.title("💰 Novo Contrato")
        try:
            r = supabase.table("clients").select("*").execute()
            # Ordena e cria Label Visual
            cli_data = sorted(r.data, key=lambda x: x['name'])
            # Dicionário reverso para buscar objeto completo pelo Label
            opts = {}
            for c in cli_data:
                icon = "🟢" if c['reputation']=='BOM' else "🔴" if c['reputation']=='RUIM' else "⚪"
                lbl = f"{icon} {c['name']} | CPF: {c['cpf']}"
                opts[lbl] = c
        except: opts = {}

        if not opts: st.warning("Cadastre clientes.")
        else:
            st.write("Busque o cliente:")
            sel_lbl = st.selectbox("Cliente", list(opts.keys()), index=None, placeholder="Digite para buscar...")
            
            if sel_lbl:
                cli = opts[sel_lbl]
                # Contexto Visual
                loans = supabase.table("loans").select("remaining_amount").eq("client_id", cli['id']).neq("status","pago").execute().data
                divida = sum([x['remaining_amount'] for x in loans])
                
                alert_color = "#ff4b4b" if cli['reputation']=='RUIM' else "#4CAF50"
                st.markdown(f"""
                <div style="border-left: 5px solid {alert_color}; background-color:#262730; padding:15px; border-radius:5px; margin-bottom:15px">
                    <h4 style="margin:0">{cli['name']}</h4>
                    <span>📱 {cli['phone']} | 📍 {cli['address']}</span><br>
                    <span>💸 Dívida Atual: <b>R$ {divida:,.2f}</b></span>
                </div>
                """, unsafe_allow_html=True)
                
                if cli['reputation']=='RUIM': st.error("⚠️ Atenção: Cliente com histórico negativo.")

                with st.form("new_loan"):
                    c1, c2, c3 = st.columns(3)
                    val = c1.number_input("Valor (R$)", min_value=50.0, step=50.0)
                    rate = c2.number_input("Juros (%)", value=10.0, step=0.5)
                    due = c3.date_input("1º Vencimento", date.today(), format="DD/MM/YYYY")
                    
                    if st.form_submit_button("Gerar Contrato", type="primary"):
                        supabase.table("loans").insert({
                            "client_id": cli['id'], "original_amount": val, "remaining_amount": val,
                            "interest_rate": rate, "due_date": str(due), "owner_id": st.session_state.user.id
                        }).execute()
                        st.success("Criado!"); st.rerun()

    # --- 4. CADASTRAR CLIENTE ---
    elif menu == "Cadastrar Cliente":
        st.title("👤 Novo Cliente")
        with st.form("cli"):
            c1, c2 = st.columns(2)
            nm = c1.text_input("Nome *")
            cpf = c1.text_input("CPF *", max_chars=14)
            tel = c1.text_input("Celular *", help="DDD+9 dígitos")
            ref = c1.text_input("Referência *")
            
            rg = c2.text_input("RG")
            em = c2.text_input("Email")
            end = c2.text_area("Endereço *")
            files = st.file_uploader("Docs", accept_multiple_files=True)

            if st.form_submit_button("Salvar"):
                errs = []
                if not (nm and cpf and tel and end and ref): errs.append("Preencha obrigatórios *")
                if cpf and not validate_cpf(cpf): errs.append("CPF inválido")
                if tel and not validate_phone(tel): errs.append("Celular inválido")
                if em and not validate_email(em): errs.append("Email inválido")

                if errs: 
                    for e in errs: st.error(e)
                else:
                    try:
                        res = supabase.table("clients").insert({
                            "name": nm, "cpf": re.sub(r'\D','',cpf), "phone": re.sub(r'\D','',tel),
                            "rg": rg, "email": em, "address": end, "reference_contact": ref,
                            "reputation": "NEUTRO", "owner_id": st.session_state.user.id
                        }).execute()
                        if res.data:
                            cid = res.data[0]['id']
                            if files:
                                for f in files:
                                    u, n = upload_file(f, cid)
                                    if u: supabase.table("client_documents").insert({"client_id":cid,"file_name":n,"file_url":u}).execute()
                            st.success("Salvo!")
                    except Exception as e: st.error(f"Erro: {e}")

    # --- 5. BASE DE CLIENTES ---
    elif menu == "Base de Clientes":
        st.title("📂 Carteira")
        search = st.text_input("Buscar (Nome/CPF)")
        q = supabase.table("clients").select("*")
        if search: q = q.or_(f"name.ilike.%{search}%,cpf.ilike.%{search}%")
        clients = q.execute().data

        if clients:
            for c in clients:
                icon = "🟢" if c['reputation']=='BOM' else "🔴" if c['reputation']=='RUIM' else "⚪"
                with st.expander(f"{icon} {c['name']} ({c['cpf']})"):
                    st.write(f"📱 {c['phone']} | 📍 {c['address']}")
                    
                    loans = supabase.table("loans").select("*").eq("client_id", c['id']).execute().data
                    if loans:
                        st.subheader("Contratos")
                        df = pd.DataFrame(loans)
                        # Formata data para BR na tabela
                        df['Vencimento'] = pd.to_datetime(df['due_date']).dt.strftime('%d/%m/%Y')
                        df = df[['Vencimento', 'original_amount', 'remaining_amount', 'status']].rename(columns={
                            'original_amount': 'Valor', 'remaining_amount': 'Saldo', 'status': 'Status'
                        })
                        st.dataframe(df, use_container_width=True)

                        if st.button("Ver Histórico Pagamentos", key=c['id']):
                            ids = [l['id'] for l in loans]
                            logs = supabase.table("payments").select("*, profiles(email)").in_("loan_id", ids).order("paid_at", desc=True).execute().data
                            if logs:
                                # Prepara dados para tabela
                                data_logs = []
                                for l in logs:
                                    dt_br = datetime.strptime(l['paid_at'], '%Y-%m-%d').strftime('%d/%m/%Y')
                                    # Cria link se tiver comprovante
                                    comprovante = f"[Ver]({l['proof_url']})" if l.get('proof_url') else "-"
                                    data_logs.append({
                                        "Data": dt_br, 
                                        "Valor": f"R$ {l['amount']}", 
                                        "Tipo": l['payment_type'], 
                                        "Resp": l['profiles']['email'],
                                        "Comp": comprovante
                                    })
                                # Mostra tabela markdown para permitir links
                                st.markdown(pd.DataFrame(data_logs).to_markdown(index=False))
                            else: st.info("Sem pagamentos.")
                    else: st.info("Sem histórico.")