-- =============================================================
-- MIGRATION V3 — Rodar no SQL Editor do Supabase
-- Adiciona: coluna due_day em loans para guardar o dia âncora
-- do vencimento (1-31), permitindo recalcular o próximo vencimento
-- corretamente mesmo em meses com menos dias (ex: fevereiro).
-- =============================================================

-- 1. Adicionar coluna due_day (dia do mês original do contrato)
ALTER TABLE public.loans ADD COLUMN IF NOT EXISTS due_day integer;

-- 2. Preencher contratos existentes com o dia extraído do due_date atual
UPDATE public.loans SET due_day = EXTRACT(DAY FROM due_date)::int WHERE due_day IS NULL;

-- 3. Reconciliar contratos atrasados que já tiveram pagamento de juros registrado
--    mas cujo due_date não foi avançado (código antigo não fazia o avanço).
--    Regra: se há pagamento JUROS ou AMORTIZACAO com paid_at >= due_date do contrato,
--    avança o due_date em 1 mês (respeitando o dia âncora / último dia do mês) e
--    define status = 'pendente'.
WITH ultimo_pagamento AS (
    SELECT DISTINCT ON (loan_id)
        loan_id,
        paid_at
    FROM public.payments
    WHERE payment_type IN ('JUROS', 'AMORTIZACAO')
    ORDER BY loan_id, paid_at DESC
)
UPDATE public.loans l
SET
    due_day  = COALESCE(l.due_day, EXTRACT(DAY FROM l.due_date)::int),
    due_date = (
        -- Próximo vencimento = 1º dia do mês seguinte + (dia âncora - 1) dias,
        -- clamped ao último dia real do mês destino
        date_trunc('month', l.due_date)::date
        + interval '1 month'
        + (
            LEAST(
                COALESCE(l.due_day, EXTRACT(DAY FROM l.due_date)::int),
                DATE_PART('day',
                    date_trunc('month', l.due_date)::date
                    + interval '2 months'
                    - interval '1 day'
                )::int
            ) - 1
          ) * interval '1 day'
    ),
    status   = 'pendente'
FROM ultimo_pagamento up
WHERE l.id = up.loan_id
  AND l.status = 'atrasado'
  AND l.remaining_amount > 0.5
  AND up.paid_at >= l.due_date;
