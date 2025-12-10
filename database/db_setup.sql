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
  values (new.id, new.email, 'employee'); -- Default é employee
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
  phone text not null, -- Formato E.164 recomendado (+5511999999999)
  doc_url text,
  owner_id uuid references public.profiles(id) not null
);

-- 3. Tabela de Empréstimos
create table public.loans (
  id uuid default gen_random_uuid() primary key,
  client_id uuid references public.clients(id) not null,
  amount numeric not null,
  interest_rate numeric not null, -- Em porcentagem (ex: 5.0 para 5%)
  due_date date not null,
  status text check (status in ('pendente', 'pago', 'atrasado')) default 'pendente',
  owner_id uuid references public.profiles(id) not null
);

-- 4. Logs de Notificação (Para evitar spam)
create table public.notification_logs (
  id uuid default gen_random_uuid() primary key,
  loan_id uuid references public.loans(id) not null,
  sent_at timestamp with time zone default timezone('utc'::text, now()) not null,
  status text default 'success'
);

-- 5. Configuração do Storage (Bucket 'documents')
insert into storage.buckets (id, name, public) values ('documents', 'documents', true);

-- POLÍTICAS DE SEGURANÇA (RLS)

alter table public.profiles enable row level security;
alter table public.clients enable row level security;
alter table public.loans enable row level security;

-- Política: Admin vê tudo, Employee vê apenas o seu.

-- Clients
create policy "Admins can view all clients" on public.clients
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can view own clients" on public.clients
  for all using (owner_id = auth.uid());

-- Loans
create policy "Admins can view all loans" on public.loans
  for select using (exists (select 1 from public.profiles where id = auth.uid() and role = 'admin'));

create policy "Employees can view own loans" on public.loans
  for all using (owner_id = auth.uid());