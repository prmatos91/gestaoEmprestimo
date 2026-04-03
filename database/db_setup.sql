-- 1. Tabela de Perfis (Vinculada ao Auth do Supabase)
create table public.profiles (
  id uuid references auth.users not null primary key,
  email text,
  role text check (role in ('admin', 'employee')) default 'employee'
);

-- Trigger para criar profile automaticamente ao cadastrar usuário
create or replace function public.handle_new_user() 
returns trigger as $$
begin
  insert into public.profiles (id, email, role)
  values (new.id, new.email, 'employee');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- 2. Tabela de Clientes
create table public.clients (
  id uuid default gen_random_uuid() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  name text not null,
  cpf text not null,
  phone text not null,
  rg text,
  email text,
  address text not null,
  reference_contact text,
  reputation text check (reputation in ('BOM', 'RUIM', 'NEUTRO')) default 'NEUTRO',
  owner_id uuid references public.profiles(id) not null
);

-- 3. Tabela de Documentos do Cliente
create table public.client_documents (
  id uuid default gen_random_uuid() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  client_id uuid references public.clients(id) not null,
  file_name text,
  file_url text
);

-- 4. Tabela de Empréstimos
create table public.loans (
  id uuid default gen_random_uuid() primary key,
  client_id uuid references public.clients(id) not null,
  original_amount numeric not null,
  remaining_amount numeric not null,
  interest_rate numeric not null, -- Em porcentagem (ex: 10.0 para 10%)
  due_date date not null,
  status text check (status in ('pendente', 'pago', 'atrasado')) default 'pendente',
  owner_id uuid references public.profiles(id) not null
);

-- 5. Tabela de Pagamentos
create table public.payments (
  id uuid default gen_random_uuid() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  loan_id uuid references public.loans(id) not null,
  amount numeric not null,
  payment_type text check (payment_type in ('JUROS', 'AMORTIZACAO', 'QUITACAO')) not null,
  paid_at date not null,
  owner_id uuid references public.profiles(id) not null,
  proof_url text
);

-- 6. Logs de Notificação (Para evitar spam de cobrança)
create table public.notification_logs (
  id uuid default gen_random_uuid() primary key,
  loan_id uuid references public.loans(id) not null,
  sent_at timestamp with time zone default timezone('utc'::text, now()) not null,
  status text default 'success'
);

-- 7. Configuração do Storage (Bucket 'documents')
insert into storage.buckets (id, name, public) values ('documents', 'documents', true);

-- =============================================================
-- POLÍTICAS DE SEGURANÇA (RLS)
-- Regra: Admin vê tudo, Employee vê apenas seus próprios registros
-- =============================================================

alter table public.profiles enable row level security;
alter table public.clients enable row level security;
alter table public.client_documents enable row level security;
alter table public.loans enable row level security;
alter table public.payments enable row level security;

-- Profiles
create policy "Users can view own profile" on public.profiles
  for select using (auth.uid() = id);

-- Clients
create policy "Admins can view all clients" on public.clients
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can manage own clients" on public.clients
  for all using (owner_id = auth.uid());

-- Client Documents
create policy "Admins can view all client documents" on public.client_documents
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can manage own client documents" on public.client_documents
  for all using (exists (select 1 from public.clients where id = client_id and owner_id = auth.uid()));

-- Loans
create policy "Admins can view all loans" on public.loans
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can manage own loans" on public.loans
  for all using (owner_id = auth.uid());

-- Payments
create policy "Admins can view all payments" on public.payments
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can manage own payments" on public.payments
  for all using (owner_id = auth.uid());