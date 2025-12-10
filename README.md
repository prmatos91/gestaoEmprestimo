# 🏦 Sistema de Gestão de Empréstimos & Automação de Cobrança

Este projeto é uma solução Full-Stack para gestão de microcrédito e empréstimos pessoais. Ele combina um painel administrativo interativo para gestão de contratos e um sistema "headless" (sem interface) para automação de cobranças via WhatsApp.

---

## 🏗 Arquitetura e Tecnologias

O sistema foi projetado focando em baixo custo de manutenção, segurança e escalabilidade serverless.

* **Frontend:** [Streamlit](https://streamlit.io/) (Interface Python simples e reativa).
* **Backend & Database:** [Supabase](https://supabase.com/) (PostgreSQL + Auth + Storage + RLS).
* **Automação:** Python Script + [GitHub Actions](https://github.com/features/actions) (Cron Job Diário).
* **Notificações:** Integração via API HTTP (preparado para WhatsApp Gateway).

### Fluxo de Dados
1.  **Admin/Funcionario** cadastra clientes e empréstimos via Streamlit.
2.  **Supabase** armazena dados com segurança RLS (Row Level Security).
3.  **GitHub Actions** acorda todo dia às 09:00 AM (BRT).
4.  **Script Python** verifica vencimentos pendentes e dispara mensagens HTTP.

---

## 📂 Estrutura do Projeto

```text
├── .github/workflows/daily_cobranca.yml  # Agendamento do Cron Job
├── database/db_setup.sql                 # Schema do Banco e Políticas de Segurança
├── app.py                                # Aplicação Web (Streamlit)
├── automation_job.py                     # Robô de Cobrança (Backend Script)
├── requirements.txt                      # Dependências Python
└── README.md                             # Documentação