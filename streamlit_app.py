# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(
    page_title="Enter - Contratos",
    page_icon="📄",
    layout="wide",
)

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_data(ttl=60)
def load_table(table: str):
    client = get_supabase()
    try:
        res = client.table(table).select("*").execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar '{table}': {e}")
        return pd.DataFrame()

# Titulo
st.title("📄 Enter — Painel de Contratos")

# Metricas resumo
docs     = load_table("documents")
analyses = load_table("document_analysis")
clients  = load_table("clients")
links    = load_table("document_client_links")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Documentos",  len(docs))
col2.metric("Analisados",  len(analyses))
col3.metric("Clientes",    len(clients))
col4.metric("Vínculos",    len(links))

st.divider()

# Abas
tab1, tab2, tab3, tab4 = st.tabs(["📁 Documentos", "🔍 Análises", "🏢 Clientes", "🔗 Vínculos"])

# Tab 1 - Documentos
with tab1:
    st.subheader("Documentos")

    if docs.empty:
        st.info("Nenhum documento encontrado.")
    else:
        statuses = ["Todos"] + sorted(docs["status"].dropna().unique().tolist()) if "status" in docs.columns else ["Todos"]
        sel = st.selectbox("Filtrar por status", statuses, key="docs_status")
        df = docs if sel == "Todos" else docs[docs["status"] == sel]

        cols = [c for c in ["id", "original_filename", "status", "size_bytes", "mime_type", "created_at", "updated_at"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

        if "status" in docs.columns:
            st.subheader("Distribuição por status")
            status_counts = docs["status"].value_counts().reset_index()
            status_counts.columns = ["status", "qtd"]
            st.bar_chart(status_counts.set_index("status"))

# Tab 2 - Análises
with tab2:
    st.subheader("Análises de documentos")

    if analyses.empty:
        st.info("Nenhuma análise encontrada.")
    else:
        tipos = ["Todos"] + sorted(analyses["instrument_type"].dropna().unique().tolist()) if "instrument_type" in analyses.columns else ["Todos"]
        sel_tipo = st.selectbox("Filtrar por tipo", tipos, key="analysis_tipo")
        df_a = analyses if sel_tipo == "Todos" else analyses[analyses["instrument_type"] == sel_tipo]

        priority_cols = [
            "id", "document_id", "instrument_type", "title_or_heading",
            "is_signed", "signature_date", "effective_date", "end_date",
            "contract_value", "payment_terms", "signing_city",
            "signing_platform", "object_summary", "prompt_version", "model",
        ]
        cols_a = [c for c in priority_cols if c in df_a.columns]
        st.dataframe(df_a[cols_a], use_container_width=True, hide_index=True)

        if "contract_value" in analyses.columns and "instrument_type" in analyses.columns:
            st.subheader("Valor total por tipo de instrumento (R$)")
            val = (
                analyses.dropna(subset=["contract_value"])
                .groupby("instrument_type")["contract_value"]
                .sum()
                .reset_index()
                .sort_values("contract_value", ascending=False)
            )
            if not val.empty:
                st.bar_chart(val.set_index("instrument_type"))

# Tab 3 - Clientes
with tab3:
    st.subheader("Clientes")

    if clients.empty:
        st.info("Nenhum cliente encontrado.")
    else:
        search = st.text_input("Buscar por nome", key="client_search")
        df_c = clients
        if search:
            mask = df_c.apply(lambda col: col.astype(str).str.contains(search, case=False, na=False)).any(axis=1)
            df_c = df_c[mask]

        priority_cols_c = [
            "id", "legal_name", "client_type", "cpf_cnpj",
            "address_city", "address_state", "email", "phone",
            "representative_name", "created_at",
        ]
        cols_c = [c for c in priority_cols_c if c in df_c.columns]
        st.dataframe(df_c[cols_c], use_container_width=True, hide_index=True)

        col_a, col_b = st.columns(2)
        if "client_type" in clients.columns:
            tipo_counts = clients["client_type"].value_counts().reset_index()
            tipo_counts.columns = ["tipo", "qtd"]
            col_a.subheader("PF vs PJ")
            col_a.bar_chart(tipo_counts.set_index("tipo"))

        if "address_state" in clients.columns:
            state_counts = clients["address_state"].value_counts().head(10).reset_index()
            state_counts.columns = ["UF", "qtd"]
            col_b.subheader("Top estados")
            col_b.bar_chart(state_counts.set_index("UF"))

# Tab 4 - Vínculos
with tab4:
    st.subheader("Vínculos documento - cliente")

    if links.empty:
        st.info("Nenhum vínculo encontrado.")
    else:
        if not clients.empty and "id" in clients.columns and "legal_name" in clients.columns:
            client_map = clients.set_index("id")["legal_name"].to_dict()
            links_view = links.copy()
            links_view["client_name"] = links_view["client_id"].map(client_map)
        else:
            links_view = links.copy()

        cols_l = [c for c in ["id", "document_id", "client_id", "client_name", "role_in_document", "source", "created_at"] if c in links_view.columns]
        st.dataframe(links_view[cols_l], use_container_width=True, hide_index=True)

        if "role_in_document" in links.columns:
            st.subheader("Papéis nos documentos")
            role_counts = links["role_in_document"].value_counts().reset_index()
            role_counts.columns = ["papel", "qtd"]
            st.bar_chart(role_counts.set_index("papel"))
