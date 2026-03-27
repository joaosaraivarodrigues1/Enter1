# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as http

from supabase import create_client

st.set_page_config(
    page_title="Enter",
    layout="wide",
)

# ── Conexões ─────────────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"].strip()
    key = st.secrets["SUPABASE_KEY"].strip()
    return create_client(url, key)

@st.cache_data(ttl=60)
def load_table(table: str):
    client = get_supabase()
    try:
        res = client.table(table).select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar '{table}': {e}")
        return pd.DataFrame()

def functions_url():
    return st.secrets["SUPABASE_URL"].strip() + "/functions/v1"

def auth_header():
    return {"Authorization": f"Bearer {st.secrets['SUPABASE_KEY'].strip()}"}

# ── Navegação ─────────────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state.page = "home"

st.title("Xp - Análise de portfólio e rendimentos")

col_home, col_db, col_ativos, col_indices, *_ = st.columns([1, 1, 1, 1, 5])

if col_home.button("Home", use_container_width=True):
    st.session_state.page = "home"
if col_db.button("Banco de dados", use_container_width=True):
    st.session_state.page = "banco_de_dados"
if col_ativos.button("Ativos", use_container_width=True):
    st.session_state.page = "ativos"
if col_indices.button("Índice Mercado", use_container_width=True):
    st.session_state.page = "indice_mercado"

st.divider()

# ── Páginas ───────────────────────────────────────────────────────────────────

if st.session_state.page == "home":
    st.subheader("Sobre o projeto")
    st.markdown("""
    **Enter** é uma plataforma de análise de portfólio e rendimentos para carteiras de investimento.

    O sistema consolida dados de ações, fundos de investimento e renda fixa, cruza com índices de
    mercado (CDI, IPCA, Selic, IBOVESPA) e produz análises de performance e recomendações.

    **Fontes de dados**
    - Ações e FIIs: brapi.dev (preços mensais e dividendos)
    - Fundos: CVM — Informe Diário (arquivos locais)
    - Índices: BCB API (CDI, IPCA, Selic) e brapi.dev (IBOVESPA)

    **Banco de dados**
    - `ativos_acoes` / `ativos_fundos` — catálogo de ativos disponíveis
    - `posicoes_acoes` / `posicoes_fundos` / `posicoes_renda_fixa` — carteira por cliente
    - `precos_acoes` / `cotas_fundos` / `dados_mercado` — série histórica mensal
    """)

elif st.session_state.page == "banco_de_dados":
    st.subheader("Banco de dados")

    tabelas = [
        "ativos_acoes",
        "ativos_fundos",
        "clientes",
        "posicoes_acoes",
        "posicoes_fundos",
        "posicoes_renda_fixa",
        "precos_acoes",
        "cotas_fundos",
        "dados_mercado",
    ]

    sel = st.selectbox("Tabela", tabelas)
    df = load_table(sel)

    if df.empty:
        st.info("Tabela vazia.")
    else:
        st.caption(f"{len(df)} registros")
        st.dataframe(df, use_container_width=True, hide_index=True)

elif st.session_state.page == "ativos":
    st.subheader("Adicionar ativo")
    st.caption("Cadastra um novo ativo no catálogo. Após o cadastro, o ativo estará disponível para posições e coleta de dados.")

    tipo = st.radio("Tipo de ativo", ["Ação / FII", "Fundo", "Renda Fixa"], horizontal=True)

    with st.form("form_add_ativo"):
        if tipo == "Ação / FII":
            ticker = st.text_input("Ticker", placeholder="ex: PETR4").upper().strip()
            nome   = st.text_input("Nome da empresa", placeholder="ex: Petrobras")
            submit = st.form_submit_button("Adicionar", type="primary")

            if submit:
                if not ticker or not nome:
                    st.error("Preencha ticker e nome.")
                else:
                    res = get_supabase().table("ativos_acoes").insert({"ticker": ticker, "nome": nome}).execute()
                    if res.data:
                        st.success(f"{ticker} adicionado com sucesso.")
                        st.cache_data.clear()
                    else:
                        st.error(f"Erro: {res}")

        elif tipo == "Fundo":
            cnpj = st.text_input("CNPJ", placeholder="ex: 12.345.678/0001-90").strip()
            nome = st.text_input("Nome do fundo", placeholder="ex: Riza Lotus Plus")
            submit = st.form_submit_button("Adicionar", type="primary")

            if submit:
                if not cnpj or not nome:
                    st.error("Preencha CNPJ e nome.")
                else:
                    res = get_supabase().table("ativos_fundos").insert({"cnpj": cnpj, "nome": nome}).execute()
                    if res.data:
                        st.success(f"{nome} adicionado com sucesso.")
                        st.cache_data.clear()
                    else:
                        st.error(f"Erro: {res}")

        elif tipo == "Renda Fixa":
            descricao     = st.text_input("Descrição", placeholder="ex: CDB C6")
            instrumento   = st.selectbox("Instrumento", ["CDB", "LCI", "LCA", "tesouro_direto", "debenture"])
            indexacao     = st.selectbox("Indexação", ["pos_fixado", "prefixado", "ipca_mais"])
            taxa          = st.number_input("Taxa contratada", min_value=0.0, format="%.4f")
            unidade_taxa  = st.selectbox("Unidade da taxa", ["percentual_cdi", "percentual_selic", "percentual_ao_ano", "spread_ao_ano"])
            valor         = st.number_input("Valor aplicado (R$)", min_value=0.0, format="%.2f")
            cliente_id    = st.text_input("ID do cliente (uuid)")
            data_inicio   = st.date_input("Data de início")
            data_venc     = st.date_input("Data de vencimento")
            isento_ir     = st.checkbox("Isento de IR")
            emissor       = st.text_input("Emissor (somente debêntures)", placeholder="opcional")
            submit        = st.form_submit_button("Adicionar", type="primary")

            if submit:
                if not descricao or not cliente_id:
                    st.error("Preencha ao menos descrição e ID do cliente.")
                else:
                    payload = {
                        "cliente_id":     cliente_id.strip(),
                        "descricao":      descricao,
                        "instrumento":    instrumento,
                        "indexacao":      indexacao,
                        "taxa_contratada": taxa,
                        "unidade_taxa":   unidade_taxa,
                        "valor_aplicado": valor,
                        "data_inicio":    str(data_inicio),
                        "data_vencimento": str(data_venc),
                        "isento_ir":      isento_ir,
                        "emissor":        emissor or None,
                    }
                    res = get_supabase().table("posicoes_renda_fixa").insert(payload).execute()
                    if res.data:
                        st.success(f"{descricao} adicionado com sucesso.")
                        st.cache_data.clear()
                    else:
                        st.error(f"Erro: {res}")

elif st.session_state.page == "indice_mercado":
    col_title, col_btn = st.columns([5, 1])
    col_title.subheader("Índices de mercado")

    with col_btn:
        st.write("")
        if st.button("Atualizar", type="primary", use_container_width=True):
            with st.spinner("Buscando índices..."):
                try:
                    resp = http.post(
                        f"{functions_url()}/fetch-indices",
                        headers={**auth_header(), "Content-Type": "application/json"},
                        json={},
                        timeout=60,
                    )
                    data = resp.json()
                except Exception as e:
                    st.error(f"Erro de conexão: {e}")
                    data = None

            if data and resp.status_code == 200:
                st.success(f"{data.get('meses_inseridos', 0)} meses atualizados.")
                st.cache_data.clear()
                st.rerun()
            elif data:
                st.error(f"Erro: {data.get('error', resp.text)}")

    df = load_table("dados_mercado")

    if df.empty:
        st.info("Nenhum dado encontrado. Clique em Atualizar para buscar os índices.")
    else:
        df = df.sort_values("mes", ascending=False).head(5).reset_index(drop=True)

        COLUNAS = {
            "cdi_mensal":              "CDI",
            "ipca_mensal":             "IPCA",
            "selic_mensal":            "Selic",
            "ibovespa_retorno_mensal": "IBOVESPA",
        }

        for _, row in df.iterrows():
            mes_label = pd.to_datetime(row["mes"] + "-01").strftime("%B/%Y").capitalize()

            with st.container(border=True):
                st.markdown(f"**{mes_label}**")
                cols = st.columns(4)
                for col, (campo, label) in zip(cols, COLUNAS.items()):
                    val = row.get(campo)
                    if val is not None:
                        cols[list(COLUNAS.keys()).index(campo)].metric(label, f"{val:.2f}%")
                    else:
                        cols[list(COLUNAS.keys()).index(campo)].metric(label, "—")
