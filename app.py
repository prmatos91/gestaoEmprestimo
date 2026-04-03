import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, timedelta
import re
import altair as alt
import requests

# --- 1. CONFIGURAÇÃO INICIAL E VALIDADORES ---
st.set_page_config(page_title="Gestão de Empréstimos", layout="wide", page_icon="🏦")

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
    if 'name' not in st.session_state: st.session_state.name = None
    if 'edit_client_id' not in st.session_state: st.session_state.edit_client_id = None
    if st.session_state.session:
        try:
            token = st.session_state.session.access_token
            refresh = st.session_state.session.refresh_token
            supabase.auth.set_session(token, refresh)
            # auth() atualiza os headers da sessão httpx do client PostgREST já inicializado
            supabase.postgrest.auth(token)
        except Exception:
            logout()

def login(email, password, nome):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.session = res.session
        st.session_state.user = res.user
        st.session_state.name = nome.strip() if nome and nome.strip() else None
        st.session_state.role = fetch_role(res.user.id, res.session.access_token)
    except Exception:
        st.error("Credenciais inválidas.")
        return
    st.rerun()

def logout():
    supabase.auth.sign_out()
    st.session_state.session = None; st.session_state.user = None
    st.session_state.role = None; st.session_state.name = None
    st.rerun()

# --- 3. UPLOAD ---
def upload_file(file, folder="docs"):
    try:
        name = f"{folder}/{datetime.now().timestamp()}_{file.name.replace(' ', '_')}"
        supabase.storage.from_("documents").upload(name, file.getvalue(), {"content-type": file.type})
        pub_url = supabase.storage.from_("documents").get_public_url(name)
        if isinstance(pub_url, dict):
            pub_url = pub_url.get('publicUrl') or pub_url.get('publicURL', '')
        return pub_url, file.name
    except: return None, None

def fetch_role(user_id, access_token):
    """Busca role via REST direto com Bearer token — independente do estado interno do client."""
    try:
        resp = requests.get(
            f"{url}/rest/v1/profiles",
            params={"select": "role", "id": f"eq.{user_id}"},
            headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get('role', 'employee')
    except:
        pass
    return 'employee'

# --- 4. ATUALIZAR STATUS ATRASADO ---
def update_atrasados():
    try:
        supabase.table("loans").update({"status": "atrasado"}).eq("status", "pendente").lt("due_date", str(date.today())).execute()
    except: pass

# --- 5. APP PRINCIPAL ---
init_session()

if not st.session_state.user:
    st.markdown("""
    <div style='text-align:center; padding: 50px 0 30px 0;'>
        <div style='font-size: 3.5rem; margin-bottom: 8px;'>🏦</div>
        <h1 style='font-size: 2.2rem; margin: 0 0 8px 0;'>Gestão de Empréstimos</h1>
        <p style='color: #888; margin: 0; font-size: 1rem;'>Faça login para acessar o sistema</p>
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.form("login"):
            st.markdown("#### 🔐 Acesse sua conta")
            nome = st.text_input("Seu Nome", placeholder="Como quer ser chamado")
            email = st.text_input("E-mail", placeholder="seu@email.com")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            st.write("")
            if st.form_submit_button("Entrar", use_container_width=True, type="primary"):
                if not nome.strip():
                    st.error("Informe seu nome.")
                else:
                    with st.spinner("Verificando credenciais..."):
                        login(email, password, nome)
else:
    update_atrasados()
    display_name = st.session_state.name or (st.session_state.user.email if st.session_state.user else '')
    st.sidebar.title(f"Olá, {display_name}")
    _menu_items = ["Painel Financeiro", "Baixa de Pagamentos", "Novo Contrato", "Cadastrar Cliente", "Base de Clientes", "Calculadora de Atraso"]
    if st.session_state.role == 'admin':
        _menu_items.append("Gerenciar Usuários")
    menu = st.sidebar.radio("Menu", _menu_items)
    st.sidebar.divider()
    if st.sidebar.button("Sair"): logout()

    # --- 1. PAINEL FINANCEIRO ---
    if menu == "Painel Financeiro":
        st.title("📊 Painel Financeiro")

        # Alertas de vencimento
        with st.spinner("Carregando dados..."):
            alertas_raw = supabase.table("loans").select("*, clients(name)").neq("status", "pago").execute().data
        hoje = date.today()
        atrasados_lst = [l for l in alertas_raw if l['status'] == 'atrasado']
        vencem_hoje_lst = [l for l in alertas_raw if l['status'] == 'pendente' and datetime.strptime(l['due_date'], '%Y-%m-%d').date() == hoje]
        vencem_semana_lst = [l for l in alertas_raw if l['status'] == 'pendente' and hoje < datetime.strptime(l['due_date'], '%Y-%m-%d').date() <= hoje + timedelta(days=7)]

        al1, al2, al3 = st.columns(3)
        with al1:
            if atrasados_lst:
                st.error(f"🔴 **{len(atrasados_lst)} contrato(s) atrasado(s)**")
                for l in atrasados_lst[:3]: st.caption(f"↳ {l['clients']['name']}")
                if len(atrasados_lst) > 3: st.caption(f"↳ ... e mais {len(atrasados_lst)-3}")
            else:
                st.success("✅ Nenhum contrato atrasado")
        with al2:
            if vencem_hoje_lst:
                st.warning(f"🟡 **{len(vencem_hoje_lst)} vence(m) hoje**")
                for l in vencem_hoje_lst[:3]: st.caption(f"↳ {l['clients']['name']}")
            else:
                st.success("✅ Nenhum vence hoje")
        with al3:
            if vencem_semana_lst:
                st.warning(f"🟠 **{len(vencem_semana_lst)} vence(m) essa semana**")
                for l in vencem_semana_lst[:3]: st.caption(f"↳ {l['clients']['name']}")
            else:
                st.success("✅ Nenhum vence essa semana")

        st.divider()
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

                # Gráficos de distribuição
                st.divider()
                st.subheader("📊 Distribuição por Status")
                gc1, gc2 = st.columns(2)
                status_count = df.groupby('status').size().reset_index(name='Contratos')
                status_saldo = df.groupby('status')['remaining_amount'].sum().reset_index()
                status_saldo.columns = ['status', 'Saldo']
                label_map = {'pago': 'Pago', 'pendente': 'Pendente', 'atrasado': 'Atrasado'}
                status_count['Status'] = status_count['status'].map(label_map)
                status_saldo['Status'] = status_saldo['status'].map(label_map)
                cor_scale = alt.Scale(domain=['pago','pendente','atrasado'], range=['#2ecc71','#f39c12','#e74c3c'])
                with gc1:
                    c_count = alt.Chart(status_count).mark_arc(innerRadius=55, outerRadius=95).encode(
                        theta=alt.Theta('Contratos:Q'),
                        color=alt.Color('status:N', scale=cor_scale, legend=alt.Legend(title='Status')),
                        tooltip=[alt.Tooltip('Status:N', title='Status'), alt.Tooltip('Contratos:Q', title='Contratos')]
                    ).properties(
                        title=alt.TitleParams('Contratos por Status', anchor='middle', fontSize=14, dy=-5),
                        height=260,
                        padding={'top': 30}
                    )
                    st.altair_chart(c_count, use_container_width=True)
                with gc2:
                    c_saldo = alt.Chart(status_saldo).mark_bar(
                        cornerRadiusTopLeft=6, cornerRadiusTopRight=6
                    ).encode(
                        x=alt.X('Status:N', title=None, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
                        y=alt.Y('Saldo:Q', title='Saldo Devedor (R$)', axis=alt.Axis(format=',.0f')),
                        color=alt.Color('status:N', scale=cor_scale, legend=None),
                        tooltip=[alt.Tooltip('Status:N', title='Status'), alt.Tooltip('Saldo:Q', title='Saldo (R$)', format=',.2f')]
                    ).properties(
                        title=alt.TitleParams('Saldo Devedor por Status', anchor='middle', fontSize=14),
                        height=260,
                        padding={'top': 30}
                    )
                    st.altair_chart(c_saldo, use_container_width=True)
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
        with st.spinner("Carregando contratos..."):
            loans = q.execute().data
        loans = sorted(loans, key=lambda x: x['due_date'])

        if loans:
            def make_label(l):
                due = datetime.strptime(l['due_date'], '%Y-%m-%d').date()
                delta = (date.today() - due).days
                icon = "🔴" if l['status'] == 'atrasado' else ("🟡" if delta == 0 else "⚪")
                atraso = f"  ⚠️ {delta}d em atraso" if delta > 0 else ""
                return f"{icon} {l['clients']['name']} | Vence: {due.strftime('%d/%m/%Y')}{atraso}"
            opts = {make_label(l): l for l in loans}
            sel = st.selectbox("Selecione o Contrato", list(opts.keys()))
            d = opts[sel]

            # Cálculos (juros sempre sobre o valor original emprestado)
            saldo = float(d['remaining_amount'])
            juros = float(d['original_amount']) * (float(d['interest_rate'])/100)
            total_quit = saldo + juros

            # Card Informativo
            st.info(f"""
            **Resumo do Contrato:**
            - 💰 Saldo Devedor (Principal): **R\\$ {saldo:,.2f}**
            - 📈 Juros da Parcela ({d['interest_rate']}% sobre R\\$ {float(d['original_amount']):,.2f}): **R\\$ {juros:,.2f}**
            - 🏁 Total para Quitação Hoje: **R\\$ {total_quit:,.2f}**
            """)

            # Modo fora do form para atualizar val_sug em tempo real
            mode = st.radio("Tipo de Pagamento", ["Somente Juros", "Juros + Amortização", "Quitação Total"], horizontal=True)

            with st.form("pay"):
                # Definição de valor sugerido
                val_sug = juros if mode == "Somente Juros" else (juros + 100) if mode == "Juros + Amortização" else total_quit
                
                c1, c2 = st.columns(2)
                dt = c1.date_input("Data Pagamento", date.today(), format="DD/MM/YYYY")
                val = c2.number_input("Valor Recebido (R$)", min_value=0.0, value=val_sug, step=10.0)
                
                # Upload Comprovante
                proof = st.file_uploader("Anexar Comprovante (Opcional)", type=['jpg','png','pdf'])

                confirm_quit = True
                if mode == "Quitação Total":
                    confirm_quit = st.checkbox(f"✅ Confirmo a quitação total de **R$ {total_quit:,.2f}**. Esta ação não pode ser desfeita.")

                if st.form_submit_button("Confirmar Baixa", type="primary"):
                    if mode == "Quitação Total" and not confirm_quit:
                        st.error("⚠️ Marque a confirmação acima para prosseguir com a quitação.")
                    else:
                        err = None
                        if mode == "Somente Juros":
                            if val < (juros - 0.1): err = f"Valor insuficiente. Mínimo para juros: R$ {juros:,.2f}"
                        elif mode == "Juros + Amortização":
                            if val <= juros:
                                err = f"O valor (R$ {val:.2f}) não cobre os juros. Para amortizar, precisa ser MAIOR que R$ {juros:,.2f}."
                        elif mode == "Quitação Total":
                            if val < (total_quit - 1.0): err = f"Para quitar, o valor deve ser R$ {total_quit:,.2f}"

                        if err: st.error(err)
                        else:
                            try:
                                proof_url = None
                                if proof:
                                    proof_url, _ = upload_file(proof, f"proofs/{d['id']}")

                                due_dt = datetime.strptime(d['due_date'], '%Y-%m-%d').date()
                                rep = 'BOM' if dt <= due_dt else 'RUIM'
                                supabase.table("clients").update({"reputation": rep}).eq("id", d['client_id']).execute()

                                type_db = "JUROS" if mode == "Somente Juros" else "AMORTIZACAO" if mode == "Juros + Amortização" else "QUITACAO"
                                supabase.table("payments").insert({
                                    "loan_id": d['id'], "amount": val, "payment_type": type_db,
                                    "paid_at": str(dt), "owner_id": st.session_state.user.id,
                                    "proof_url": proof_url
                                }).execute()

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
        if st.session_state.pop('loan_created', False):
            st.success("✅ Contrato criado com sucesso!")
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
                        st.session_state['loan_created'] = True
                        st.rerun()

    # --- 4. CADASTRAR CLIENTE ---
    elif menu == "Cadastrar Cliente":
        st.title("👤 Novo Cliente")

        # --- IMPORTAÇÃO EM MASSA VIA CSV ---
        with st.expander("📥 Importar clientes via CSV"):
            st.markdown("""
**Formato esperado do CSV** (com cabeçalho):
- Colunas obrigatórias: `nome`, `cpf`, `celular`, `endereco`, `referencia`
- Colunas opcionais: `rg`, `email`
- CPF: apenas números ou formatado (000.000.000-00)
- Celular: DDD + 9 dígitos (apenas números ou só dígitos)
            """)
            csv_template = "nome,cpf,celular,endereco,referencia,rg,email\nJoão Silva,123.456.789-09,11987654321,Rua das Flores 10 Apto 2 São Paulo SP,Maria Silva (esposa),12345678,joao@email.com\nMaria Oliveira,987.654.321-00,21976543210,Av. Brasil 500 Rio de Janeiro RJ,Carlos Oliveira (irmão),,"
            st.download_button(
                label="💾 Baixar modelo CSV",
                data=csv_template.encode('utf-8-sig'),
                file_name="modelo_importacao_clientes.csv",
                mime="text/csv"
            )
            csv_file = st.file_uploader("Selecione o arquivo CSV preenchido", type=["csv"], key="csv_import")
            if csv_file:
                try:
                    df_csv = pd.read_csv(csv_file, dtype=str).fillna("")
                    df_csv.columns = [c.strip().lower() for c in df_csv.columns]
                    required_cols = {"nome", "cpf", "celular", "endereco", "referencia"}
                    missing = required_cols - set(df_csv.columns)
                    if missing:
                        st.error(f"Colunas faltando no CSV: {', '.join(missing)}")
                    else:
                        st.dataframe(df_csv.head(5), use_container_width=True)
                        st.caption(f"{len(df_csv)} clientes encontrados no arquivo.")
                        if st.button("✅ Confirmar Importação", type="primary"):
                            ok, erros = 0, []
                            for _, row in df_csv.iterrows():
                                cpf_clean = re.sub(r'\D', '', row['cpf'])
                                phone_clean = re.sub(r'\D', '', row['celular'])
                                if not validate_cpf(cpf_clean):
                                    erros.append(f"{row['nome']}: CPF inválido ({row['cpf']})")
                                    continue
                                if not (len(phone_clean) == 11 and phone_clean[2] == '9'):
                                    erros.append(f"{row['nome']}: Celular inválido ({row['celular']})")
                                    continue
                                try:
                                    supabase.table("clients").insert({
                                        "name": row['nome'].strip(),
                                        "cpf": cpf_clean,
                                        "phone": phone_clean,
                                        "address": row['endereco'].strip(),
                                        "reference_contact": row['referencia'].strip(),
                                        "rg": row.get('rg', '').strip(),
                                        "email": row.get('email', '').strip(),
                                        "reputation": "NEUTRO",
                                        "owner_id": st.session_state.user.id
                                    }).execute()
                                    ok += 1
                                except Exception as e:
                                    erros.append(f"{row['nome']}: {e}")
                            if ok: st.success(f"✅ {ok} cliente(s) importado(s) com sucesso!")
                            if erros:
                                st.error(f"⚠️ {len(erros)} erro(s):")
                                for e in erros: st.write(f"- {e}")
                except Exception as e:
                    st.error(f"Erro ao ler CSV: {e}")

        st.divider()
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
        is_admin = st.session_state.role == 'admin'
        search = st.text_input("Buscar (Nome/CPF)")
        q = supabase.table("clients").select("*")
        if search: q = q.or_(f"name.ilike.%{search}%,cpf.ilike.%{search}%")
        with st.spinner("Carregando clientes..."):
            clients = q.execute().data

        if clients:
            for c in clients:
                icon = "🟢" if c['reputation']=='BOM' else "🔴" if c['reputation']=='RUIM' else "⚪"
                with st.expander(f"{icon} {c['name']} ({c['cpf']})"):
                    hcols = st.columns([4, 1, 1]) if is_admin else st.columns([5, 1])
                    hcols[0].write(f"📱 {c['phone']} | 📍 {c['address']}")
                    if hcols[1].button("✏️ Editar", key=f"editbtn_{c['id']}"):
                        st.session_state.edit_client_id = None if st.session_state.get('edit_client_id') == c['id'] else c['id']
                        st.rerun()
                    if is_admin and hcols[2].button("🗑️ Excluir", key=f"delbtn_{c['id']}", type="secondary"):
                        st.session_state[f'confirm_del_{c["id"]}'] = True

                    if is_admin and st.session_state.get(f'confirm_del_{c["id"]}'):
                        st.warning("⚠️ Tem certeza que deseja excluir este cliente? Esta ação não pode ser desfeita.")
                        cc1, cc2 = st.columns(2)
                        if cc1.button("✅ Sim, excluir", key=f"yes_del_{c['id']}", type="primary"):
                            active = supabase.table("loans").select("id").eq("client_id", c['id']).neq("status","pago").execute().data
                            if active:
                                st.error("❌ Cliente possui contratos ativos. Quite todos os contratos antes de excluir.")
                                st.session_state.pop(f'confirm_del_{c["id"]}', None)
                            else:
                                try:
                                    supabase.table("client_documents").delete().eq("client_id", c['id']).execute()
                                    supabase.table("loans").delete().eq("client_id", c['id']).execute()
                                    supabase.table("clients").delete().eq("id", c['id']).execute()
                                    st.session_state.pop(f'confirm_del_{c["id"]}', None)
                                    st.rerun()
                                except Exception as e: st.error(f"Erro ao excluir: {e}")
                        if cc2.button("❌ Cancelar", key=f"cancel_del_{c['id']}"):
                            st.session_state.pop(f'confirm_del_{c["id"]}', None)
                            st.rerun()

                    if st.session_state.get('edit_client_id') == c['id']:
                        with st.form(f"edit_cli_{c['id']}"):
                            ec1, ec2 = st.columns(2)
                            e_nm = ec1.text_input("Nome", value=c.get('name',''))
                            e_tel = ec1.text_input("Celular", value=c.get('phone',''))
                            e_ref = ec1.text_input("Referência", value=c.get('reference_contact',''))
                            e_rg = ec2.text_input("RG", value=c.get('rg',''))
                            e_em = ec2.text_input("Email", value=c.get('email',''))
                            e_end = ec2.text_area("Endereço", value=c.get('address',''))
                            if st.form_submit_button("💾 Salvar alterações", type="primary"):
                                try:
                                    supabase.table("clients").update({
                                        "name": e_nm, "phone": re.sub(r'\D','',e_tel),
                                        "rg": e_rg, "email": e_em,
                                        "address": e_end, "reference_contact": e_ref
                                    }).eq("id", c['id']).execute()
                                    st.session_state.edit_client_id = None
                                    st.success("✅ Cliente atualizado!")
                                    st.rerun()
                                except Exception as e: st.error(f"Erro: {e}")
                        st.divider()

                    tab_docs, tab_loans, tab_pag = st.tabs(["📎 Documentos", "💰 Contratos", "💸 Pagamentos"])

                    with tab_docs:
                        docs = supabase.table("client_documents").select("*").eq("client_id", c['id']).execute().data
                        if docs:
                            for doc in docs:
                                dc1, dc2, dc3 = st.columns([4, 2, 1])
                                dc1.write(f"📄 {doc.get('file_name') or 'Documento'}")
                                if doc.get('file_url'):
                                    dc2.markdown(f"[🔗 Abrir]({doc['file_url']})")
                                if is_admin and dc3.button("🗑️", key=f"del_doc_{doc['id']}", help="Excluir documento"):
                                    supabase.table("client_documents").delete().eq("id", doc['id']).execute()
                                    st.rerun()
                        else:
                            st.info("Nenhum documento cadastrado.")
                        st.divider()
                        with st.form(f"upload_doc_{c['id']}"):
                            new_docs = st.file_uploader("Adicionar documentos", accept_multiple_files=True, type=['jpg','png','pdf'])
                            if st.form_submit_button("📤 Enviar"):
                                if new_docs:
                                    for f in new_docs:
                                        u, n = upload_file(f, c['id'])
                                        if u:
                                            supabase.table("client_documents").insert({"client_id": c['id'], "file_name": n, "file_url": u}).execute()
                                    st.success("Documento(s) enviado(s)!")
                                    st.rerun()
                                else:
                                    st.warning("Selecione ao menos um arquivo.")

                    with tab_loans:
                        loans = supabase.table("loans").select("*").eq("client_id", c['id']).execute().data
                        if loans:
                            df_l = pd.DataFrame(loans)
                            df_l['Vencimento'] = pd.to_datetime(df_l['due_date']).dt.strftime('%d/%m/%Y')
                            df_l = df_l[['Vencimento', 'original_amount', 'remaining_amount', 'interest_rate', 'status']].rename(columns={
                                'original_amount': 'Valor', 'remaining_amount': 'Saldo', 'interest_rate': 'Juros (%)', 'status': 'Status'
                            })
                            st.dataframe(df_l, use_container_width=True)
                            if is_admin:
                                st.markdown("**✏️ Editar juros de um contrato:**")
                                loan_opts = {f"Vence {l['due_date']} | Saldo R$ {float(l['remaining_amount']):.2f}": l for l in loans}
                                sel_loan_lbl = st.selectbox("Selecione o contrato", list(loan_opts.keys()), key=f"sel_loan_{c['id']}")
                                sel_loan = loan_opts[sel_loan_lbl]
                                with st.form(f"edit_loan_{c['id']}"):
                                    new_rate = st.number_input("Nova Taxa de Juros (%)", value=float(sel_loan['interest_rate']), step=0.5)
                                    if st.form_submit_button("💾 Salvar Juros"):
                                        try:
                                            supabase.table("loans").update({"interest_rate": new_rate}).eq("id", sel_loan['id']).execute()
                                            st.success("✅ Juros atualizado!")
                                            st.rerun()
                                        except Exception as e: st.error(f"Erro: {e}")
                        else:
                            st.info("Nenhum contrato.")

                    with tab_pag:
                        loans_ids = supabase.table("loans").select("id").eq("client_id", c['id']).execute().data
                        if loans_ids:
                            ids = [l['id'] for l in loans_ids]
                            with st.spinner("Carregando histórico..."):
                                logs = supabase.table("payments").select("*, profiles!owner_id(email)").in_("loan_id", ids).order("paid_at", desc=True).execute().data
                            if logs:
                                data_logs = []
                                for l in logs:
                                    dt_br = datetime.strptime(l['paid_at'], '%Y-%m-%d').strftime('%d/%m/%Y')
                                    prof = l.get('profiles')
                                    resp = prof['email'] if isinstance(prof, dict) else l.get('owner_id', '-')
                                    data_logs.append({
                                        "Data": dt_br,
                                        "Valor (R$)": float(l['amount']),
                                        "Tipo": l['payment_type'],
                                        "Responsável": resp,
                                        "Comprovante": l.get('proof_url') or "",
                                    })
                                st.dataframe(
                                    pd.DataFrame(data_logs),
                                    column_config={
                                        "Valor (R$)": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                                        "Comprovante": st.column_config.LinkColumn("Comprovante", display_text="Ver"),
                                    },
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            else:
                                st.info("Sem pagamentos registrados.")
                        else:
                            st.info("Sem contratos.")
        else:
            st.info("Nenhum cliente encontrado.")

    # --- 6. CALCULADORA DE ATRASO ---
    elif menu == "Calculadora de Atraso":
        st.title("🧮 Calculadora de Multa e Juros por Atraso")
        st.caption("Use esta calculadora para saber o total a cobrar de um cliente em atraso.")

        c1, c2 = st.columns(2)
        saldo_calc = c1.number_input("💰 Saldo Devedor (R$)", min_value=0.0, step=50.0, format="%.2f")
        multa = c1.number_input("⚠️ Multa Fixa (R$)", min_value=0.0, step=5.0, format="%.2f",
                                help="Valor fixo de multa cobrado uma única vez pelo atraso")
        juros_dia = c2.number_input("📅 Juros por Dia (R$)", min_value=0.0, step=1.0, format="%.2f",
                                    help="Valor fixo cobrado por cada dia de atraso")
        dias = c2.number_input("📆 Dias em Atraso", min_value=0, step=1,
                               help="Quantos dias se passaram desde o vencimento")

        if saldo_calc > 0 or multa > 0 or juros_dia > 0:
            st.divider()
            total_juros_atraso = juros_dia * dias
            total_cobrar = saldo_calc + multa + total_juros_atraso

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Saldo Devedor", f"R$ {saldo_calc:,.2f}")
            col2.metric("Multa", f"R$ {multa:,.2f}")
            col3.metric(f"Juros ({dias} dias)", f"R$ {total_juros_atraso:,.2f}",
                        delta=f"R$ {juros_dia:,.2f}/dia", delta_color="off")
            col4.metric("💥 Total a Cobrar", f"R$ {total_cobrar:,.2f}")

            st.info(f"""
**Memória de cálculo:**
- Saldo devedor: **R\\$ {saldo_calc:,.2f}**
- Multa fixa: **R\\$ {multa:,.2f}**
- Juros por atraso: R\\$ {juros_dia:,.2f}/dia × {dias} dias = **R\\$ {total_juros_atraso:,.2f}**
- **Total: R\\$ {saldo_calc:,.2f} + R\\$ {multa:,.2f} + R\\$ {total_juros_atraso:,.2f} = R\\$ {total_cobrar:,.2f}**
            """)

    # --- 7. GERENCIAR USUÁRIOS (somente admin) ---
    elif menu == "Gerenciar Usuários":
        if st.session_state.role != 'admin':
            st.error("Acesso negado.")
            st.stop()
        st.title("👥 Gerenciar Usuários")
        tab_criar, tab_senha, tab_lista = st.tabs(["➕ Criar Funcionário", "🔑 Alterar Minha Senha", "📋 Funcionários"])

        with tab_criar:
            st.subheader("Criar conta de funcionário")
            with st.form("new_employee"):
                n_name = st.text_input("Nome do Funcionário")
                n_email = st.text_input("E-mail")
                n_pass = st.text_input("Senha Temporária", type="password")
                n_pass2 = st.text_input("Confirmar Senha", type="password")
                if st.form_submit_button("✅ Criar Conta", type="primary"):
                    errs = []
                    if not (n_name and n_email and n_pass): errs.append("Preencha todos os campos.")
                    if n_pass != n_pass2: errs.append("Senhas não conferem.")
                    if n_email and not validate_email(n_email): errs.append("E-mail inválido.")
                    if len(n_pass) < 6: errs.append("Senha deve ter ao menos 6 caracteres.")
                    for er in errs: st.error(er)
                    if not errs:
                        try:
                            temp = create_client(url, key)
                            res_new = temp.auth.sign_up({"email": n_email, "password": n_pass})
                            if res_new.user:
                                try:
                                    supabase.table("profiles").update({"name": n_name}).eq("id", res_new.user.id).execute()
                                except: pass
                                st.success(f"✅ Funcionário **{n_name}** cadastrado com e-mail `{n_email}`. Informe a senha `{n_pass}` para o acesso inicial.")
                                st.info("ℹ️ Se o Supabase exigir confirmação de e-mail, o funcionário precisa confirmar antes de logar. Você pode desativar isso em Authentication → Settings no painel Supabase.")
                            else:
                                st.error("Não foi possível criar o usuário. O e-mail já pode estar cadastrado.")
                        except Exception as e:
                            st.error(f"Erro: {e}")

        with tab_senha:
            st.subheader("Alterar sua senha")
            with st.form("change_pass"):
                new_p = st.text_input("Nova Senha", type="password")
                new_p2 = st.text_input("Confirmar Nova Senha", type="password")
                if st.form_submit_button("🔑 Alterar Senha", type="primary"):
                    if not new_p: st.error("Informe a nova senha.")
                    elif new_p != new_p2: st.error("Senhas não conferem.")
                    elif len(new_p) < 6: st.error("Senha deve ter ao menos 6 caracteres.")
                    else:
                        try:
                            supabase.auth.update_user({"password": new_p})
                            st.success("✅ Senha alterada com sucesso!")
                        except Exception as e:
                            st.error(f"Erro: {e}")

        with tab_lista:
            st.subheader("Usuários cadastrados")
            try:
                profs = supabase.table("profiles").select("name, email, role").execute().data
                if profs:
                    df_pr = pd.DataFrame(profs)
                    df_pr.columns = ['Nome', 'E-mail', 'Função']
                    df_pr['Função'] = df_pr['Função'].map({'admin': '👑 Admin', 'employee': '👤 Funcionário'}).fillna('—')
                    st.dataframe(df_pr, use_container_width=True, hide_index=True)
                else:
                    st.info("Nenhum usuário encontrado.")
            except Exception as e:
                st.info("Sem permissão para listar usuários ou nenhum encontrado.")