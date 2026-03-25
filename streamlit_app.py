# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as http

from supabase import create_client

st.set_page_config(
    page_title="Enter - Contratos",
    page_icon="📄",
    layout="wide",
)

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

def fetch_failed_documents():
    client = get_supabase()
    try:
        res = (
            client.table("documents")
            .select("id, original_filename, error_message, updated_at")
            .eq("status", "failed")
            .order("updated_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar documentos com falha: {e}")
        return []

def reanalyze_document(doc_id: str):
    try:
        resp = http.post(
            f"{functions_url()}/extract-pdf",
            headers={**auth_header(), "Content-Type": "application/json"},
            json={"document_id": doc_id},
            timeout=180,
        )
        if resp.ok:
            return True, "Reanálise concluída com sucesso."
        return False, f"Erro {resp.status_code}: {resp.text[:200]}"
    except http.exceptions.Timeout:
        return False, "Timeout: a reanálise demorou mais de 3 minutos."
    except Exception as e:
        return False, str(e)

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
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "📤 Upload", "📁 Documentos", "🔍 Análises", "🏢 Clientes", "🔗 Vínculos"
])

# Tab 0 - Upload
with tab0:
    st.subheader("Enviar novo contrato")
    st.caption("O arquivo será enviado ao Supabase e analisado automaticamente pelo Claude.")

    uploaded = st.file_uploader("Selecione um PDF", type=["pdf"], label_visibility="collapsed")

    if uploaded is not None:
        st.info(f"Arquivo: **{uploaded.name}** ({uploaded.size / 1024:.0f} KB)")

        if st.button("Enviar e analisar", type="primary"):
            with st.spinner("Fazendo upload..."):
                try:
                    resp = http.post(
                        f"{functions_url()}/ingest",
                        headers=auth_header(),
                        files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                        timeout=30,
                    )
                    data = resp.json()
                except Exception as e:
                    st.error(f"Erro de conexão: {e}")
                    data = None

            if data and resp.status_code == 200:
                st.success(f"Upload concluído! ID: `{data['id']}`")
                st.caption("A análise pelo Claude começa automaticamente via Database Webhook. Aguarde alguns instantes e atualize a aba Documentos.")
                st.cache_data.clear()
            elif data:
                st.error(f"Erro no upload: {data.get('error', resp.text)}")

    st.divider()
    st.subheader("Reanalisar documento existente")
    st.caption("Use o ID de um documento com status 'analyzed' ou 'failed' para rodar a análise novamente.")

    reanalyze_id = st.text_input("ID do documento", placeholder="uuid do documento")
    if st.button("Reanalisar", disabled=not reanalyze_id):
        with st.spinner("Reenviando para análise..."):
            try:
                resp = http.post(
                    f"{functions_url()}/extract-pdf",
                    headers={**auth_header(), "Content-Type": "application/json"},
                    json={"document_id": reanalyze_id.strip()},
                    timeout=180,
                )
                data = resp.json()
            except Exception as e:
                st.error(f"Erro: {e}")
                data = None

        if data and resp.status_code == 200:
            st.success(f"Reanálise concluída! Status: `{data.get('status')}`")
            st.cache_data.clear()
        elif data:
            st.error(f"Erro: {data.get('error', resp.text)}")

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

    # Documentos com erro
    st.divider()
    col_err_title, col_err_refresh = st.columns([8, 1])
    col_err_title.subheader("⚠️ Documentos com erro")
    if col_err_refresh.button("Atualizar", key="refresh_failed"):
        st.cache_data.clear()
        st.rerun()

    failed_docs = fetch_failed_documents()

    if not failed_docs:
        st.success("Nenhum documento com erro.")
    else:
        st.caption(f"{len(failed_docs)} documento(s) com status **failed**")
        for doc in failed_docs:
            doc_id = doc["id"]
            filename = doc.get("original_filename") or doc_id
            error_msg = doc.get("error_message") or "Erro desconhecido"
            updated = doc.get("updated_at", "")[:19].replace("T", " ") if doc.get("updated_at") else ""

            with st.container(border=True):
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**{filename}**")
                    st.caption(f"ID: `{doc_id}`  •  Atualizado: {updated}")
                    st.error(error_msg, icon="🔴")
                with col_btn:
                    st.write("")
                    if st.button("Reanalisar", key=f"reanalyze_{doc_id}", use_container_width=True):
                        with st.spinner(f"Reanalysando {filename}..."):
                            ok, msg = reanalyze_document(doc_id)
                        if ok:
                            st.success(msg)
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(msg)

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
