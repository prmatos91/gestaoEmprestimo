-- =============================================================
-- MIGRATION V2 — Rodar no SQL Editor do Supabase
-- Adiciona: coluna name em profiles, policies admin para todas as 
-- tabelas (ALL em vez de só SELECT) e policies para gerenciar profiles.
-- =============================================================

-- 1. Adicionar coluna name em profiles (se ainda não existir)
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS name text;

-- ---------------------------------------------------------------
-- 2. CLIENTS — Admin precisa de ALL (inclui DELETE/UPDATE)
-- ---------------------------------------------------------------
DROP POLICY IF EXISTS "Admins can view all clients" ON public.clients;
CREATE POLICY "Admins can manage all clients" ON public.clients
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- ---------------------------------------------------------------
-- 3. LOANS — Admin precisa de ALL
-- ---------------------------------------------------------------
DROP POLICY IF EXISTS "Admins can view all loans" ON public.loans;
CREATE POLICY "Admins can manage all loans" ON public.loans
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- ---------------------------------------------------------------
-- 4. PAYMENTS — Admin precisa de ALL
-- ---------------------------------------------------------------
DROP POLICY IF EXISTS "Admins can view all payments" ON public.payments;
CREATE POLICY "Admins can manage all payments" ON public.payments
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- ---------------------------------------------------------------
-- 5. CLIENT_DOCUMENTS — Admin precisa de ALL
-- ---------------------------------------------------------------
DROP POLICY IF EXISTS "Admins can view all client documents" ON public.client_documents;
CREATE POLICY "Admins can manage all client documents" ON public.client_documents
  FOR ALL USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );

-- ---------------------------------------------------------------
-- 6. PROFILES — Admin pode ver todos e atualizar (para salvar nome do funcionário)
-- ---------------------------------------------------------------
DROP POLICY IF EXISTS "Users can view own profile" ON public.profiles;
CREATE POLICY "Users can view own profile" ON public.profiles
  FOR SELECT USING (
    auth.uid() = id
    OR EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );

CREATE POLICY "Admins can update profiles" ON public.profiles
  FOR UPDATE USING (
    EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
  );
