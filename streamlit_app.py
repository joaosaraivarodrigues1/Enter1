# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import requests as http
import plotly.graph_objects as go

from supabase import create_client
from postgrest.exceptions import APIError

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

col_home, col_clientes, col_ativos, col_indices, *_ = st.columns([1, 1, 1, 1, 5])

if col_home.button("Home", use_container_width=True):
    st.session_state.page = "home"
if col_clientes.button("Clientes", use_container_width=True):
    st.session_state.page = "clientes"
if col_ativos.button("Ativos Disponíveis", use_container_width=True):
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

elif st.session_state.page == "clientes":
    st.subheader("Clientes")

    # ── Carregar todos os dados uma vez ───────────────────────────────────────
    df_clientes      = load_table("clientes")
    df_pos_acoes     = load_table("posicoes_acoes")
    df_pos_fundos    = load_table("posicoes_fundos")
    df_pos_rf        = load_table("posicoes_renda_fixa")
    df_ativos_acoes  = load_table("ativos_acoes")
    df_precos        = load_table("precos_acoes")
    df_cotas         = load_table("cotas_fundos")
    df_mercado       = load_table("dados_mercado")

    nomes = df_clientes["nome"].tolist() if not df_clientes.empty else []
    ids   = df_clientes["id"].tolist()   if not df_clientes.empty else []

    # Último e penúltimo mês disponíveis
    meses_ord = sorted(df_mercado["mes"].unique()) if not df_mercado.empty else []
    mes_atual = meses_ord[-1] if len(meses_ord) >= 1 else None
    mes_ant   = meses_ord[-2] if len(meses_ord) >= 2 else None
    row_merc  = df_mercado[df_mercado["mes"] == mes_atual].iloc[0] if mes_atual else None

    tabs_clientes = st.tabs(nomes + ["＋"])
    *tabs_pessoas, tab_add = tabs_clientes

    for tab, nome_cliente, cliente_id in zip(tabs_pessoas, nomes, ids):
        with tab:
            key = f"subpage_{cliente_id}"
            if key not in st.session_state:
                st.session_state[key] = "carteira"

            col_b1, col_b2, _ = st.columns([3, 3, 4])
            if col_b1.button("Carteira", key=f"btn_carteira_{cliente_id}", use_container_width=True,
                             type="primary" if st.session_state[key] == "carteira" else "secondary"):
                st.session_state[key] = "carteira"
            if col_b2.button("Resultados", key=f"btn_resultados_{cliente_id}", use_container_width=True,
                             type="primary" if st.session_state[key] == "resultados" else "secondary"):
                st.session_state[key] = "resultados"

            st.divider()

            # Posições filtradas por cliente
            acoes_c  = df_pos_acoes[df_pos_acoes["cliente_id"]   == cliente_id] if not df_pos_acoes.empty  else pd.DataFrame()
            fundos_c = df_pos_fundos[df_pos_fundos["cliente_id"] == cliente_id] if not df_pos_fundos.empty else pd.DataFrame()
            rf_c     = df_pos_rf[df_pos_rf["cliente_id"]         == cliente_id] if not df_pos_rf.empty     else pd.DataFrame()

            # ── Carteira ──────────────────────────────────────────────────────
            if st.session_state[key] == "carteira":
                rows = []
                for _, p in acoes_c.iterrows():
                    nome_at = "—"
                    if not df_ativos_acoes.empty:
                        m = df_ativos_acoes[df_ativos_acoes["ticker"] == p["ticker"]]
                        if not m.empty:
                            nome_at = m.iloc[0]["nome"]
                    rows.append({
                        "Tipo":            "Ação / FII",
                        "Ativo":           f"{p['ticker']} — {nome_at}",
                        "Qtd / Cotas":     float(p["quantidade"]),
                        "Preço médio":     float(p["preco_medio_compra"]),
                        "Valor investido": float(p["quantidade"]) * float(p["preco_medio_compra"]),
                        "Data entrada":    p["data_compra"],
                    })
                for _, p in fundos_c.iterrows():
                    rows.append({
                        "Tipo":            "Fundo",
                        "Ativo":           p.get("nome", "—"),
                        "Qtd / Cotas":     float(p["numero_cotas"]),
                        "Preço médio":     None,
                        "Valor investido": float(p["valor_aplicado"]),
                        "Data entrada":    p["data_investimento"],
                    })
                for _, p in rf_c.iterrows():
                    rows.append({
                        "Tipo":            "Renda Fixa",
                        "Ativo":           p.get("descricao", "—"),
                        "Qtd / Cotas":     None,
                        "Preço médio":     None,
                        "Valor investido": float(p["valor_aplicado"]),
                        "Data entrada":    p["data_inicio"],
                    })

                if rows:
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Preço médio":     st.column_config.NumberColumn(format="R$ %.2f"),
                            "Valor investido": st.column_config.NumberColumn(format="R$ %.2f"),
                        },
                    )
                else:
                    st.info("Nenhuma posição cadastrada para este cliente.")

            # ── Resultados ────────────────────────────────────────────────────
            else:
                st.caption(f"Mês de referência: **{mes_atual}**" if mes_atual else "Sem dados de mercado.")

                # Tabela de rendimento do portfólio
                rows_ret = []
                for _, p in acoes_c.iterrows():
                    ticker = p["ticker"]
                    pa_row  = df_precos[(df_precos["ticker"] == ticker) & (df_precos["mes"] == mes_atual)]
                    pant_row = df_precos[(df_precos["ticker"] == ticker) & (df_precos["mes"] == mes_ant)]
                    if not pa_row.empty and not pant_row.empty:
                        pa   = float(pa_row.iloc[0]["preco_fechamento"])
                        pant = float(pant_row.iloc[0]["preco_fechamento"])
                        div  = float(pa_row.iloc[0].get("dividendos_pagos", 0) or 0)
                        ret  = (pa - pant + div) / pant * 100
                        qtd  = float(p["quantidade"])
                        rows_ret.append({
                            "Ativo": ticker, "Tipo": "Ação / FII",
                            "Retorno mês (%)": ret,
                            "Variação R$":     (pa - pant + div) * qtd,
                            "Valor atual":     pa * qtd,
                        })
                    else:
                        rows_ret.append({"Ativo": ticker, "Tipo": "Ação / FII",
                                         "Retorno mês (%)": None, "Variação R$": None, "Valor atual": None})

                for _, p in fundos_c.iterrows():
                    cnpj = p["cnpj"]
                    ca_row   = df_cotas[(df_cotas["cnpj"] == cnpj) & (df_cotas["mes"] == mes_atual)]
                    cant_row = df_cotas[(df_cotas["cnpj"] == cnpj) & (df_cotas["mes"] == mes_ant)]
                    if not ca_row.empty and not cant_row.empty:
                        ca   = float(ca_row.iloc[0]["cota_fechamento"])
                        cant = float(cant_row.iloc[0]["cota_fechamento"])
                        ret  = (ca - cant) / cant * 100
                        cotas = float(p["numero_cotas"])
                        rows_ret.append({
                            "Ativo": p.get("nome", cnpj), "Tipo": "Fundo",
                            "Retorno mês (%)": ret,
                            "Variação R$":     cotas * (ca - cant),
                            "Valor atual":     cotas * ca,
                        })
                    else:
                        rows_ret.append({"Ativo": p.get("nome", cnpj), "Tipo": "Fundo",
                                         "Retorno mês (%)": None, "Variação R$": None, "Valor atual": None})

                for _, p in rf_c.iterrows():
                    ret, val = None, float(p.get("valor_aplicado", 0) or 0)
                    if row_merc is not None:
                        idx  = p.get("indexacao", "")
                        taxa = float(p.get("taxa_contratada", 0) or 0)
                        if idx == "pos_fixado_cdi":
                            ret = float(row_merc.get("cdi_mensal", 0) or 0) * (taxa / 100)
                        elif idx == "pos_fixado_selic":
                            ret = float(row_merc.get("selic_mensal", 0) or 0) * (taxa / 100)
                        elif idx == "prefixado":
                            ret = ((1 + taxa / 100) ** (1 / 12) - 1) * 100
                        elif idx == "ipca_mais":
                            ipca = float(row_merc.get("ipca_mensal", 0) or 0) / 100
                            spread_m = (1 + taxa / 100) ** (1 / 12) - 1
                            ret = ((1 + ipca) * (1 + spread_m) - 1) * 100
                    rows_ret.append({
                        "Ativo": p.get("descricao", "—"), "Tipo": "Renda Fixa",
                        "Retorno mês (%)": ret,
                        "Variação R$":     val * ret / 100 if ret is not None else None,
                        "Valor atual":     val * (1 + ret / 100) if ret is not None else val,
                    })

                if rows_ret:
                    st.dataframe(
                        pd.DataFrame(rows_ret),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Retorno mês (%)": st.column_config.NumberColumn(format="%.2f%%"),
                            "Variação R$":     st.column_config.NumberColumn(format="R$ %.2f"),
                            "Valor atual":     st.column_config.NumberColumn(format="R$ %.2f"),
                        },
                    )
                else:
                    st.info("Nenhuma posição cadastrada para este cliente.")

                # Benchmarks
                st.subheader("Benchmarks")
                if row_merc is not None:
                    st.dataframe(pd.DataFrame({
                        "Indicador":       ["CDI", "IPCA", "Selic", "Ibovespa", "IMA-B"],
                        "Retorno mês (%)": [
                            row_merc.get("cdi_mensal"),
                            row_merc.get("ipca_mensal"),
                            row_merc.get("selic_mensal"),
                            row_merc.get("ibovespa_retorno_mensal"),
                            row_merc.get("ima_b_retorno_mensal"),
                        ],
                    }), use_container_width=True, hide_index=True,
                    column_config={"Retorno mês (%)": st.column_config.NumberColumn(format="%.4f%%")})
                else:
                    st.info("Sem dados de benchmarks.")

                # Análise — API Revit
                st.subheader("Análise")
                with st.container(border=True):
                    st.caption("Conteúdo gerado pela API Revit")
                    st.markdown("*Aguardando integração com a API Revit...*")

    with tab_add:
        st.subheader("Novo cliente")
        with st.form("form_add_cliente"):
            novo_nome = st.text_input("Nome")
            submit = st.form_submit_button("Criar cliente", type="primary")
            if submit:
                if not novo_nome.strip():
                    st.error("Preencha o nome.")
                else:
                    try:
                        get_supabase().table("clientes").insert({"nome": novo_nome.strip()}).execute()
                        st.cache_data.clear()
                        st.success(f"Cliente **{novo_nome.strip()}** criado.")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Erro: {e}")

elif st.session_state.page == "ativos":
    st.subheader("Ativos Disponíveis")

    df_acoes  = load_table("ativos_acoes")
    df_fundos = load_table("ativos_fundos")
    df_rf     = load_table("ativos_renda_fixa")
    df_precos = load_table("precos_acoes")
    df_cotas  = load_table("cotas_fundos")

    # ── Métricas ──────────────────────────────────────────────────────────────
    cm1, cm2, cm3, cm4 = st.columns(4)
    cm1.metric("Total de ativos", len(df_acoes) + len(df_fundos) + len(df_rf))
    cm2.metric("Ações / FII", len(df_acoes), f"{len(df_precos)} preços históricos")
    cm3.metric("Fundos", len(df_fundos), f"{len(df_cotas)} cotas históricas")
    cm4.metric("Renda Fixa", len(df_rf))

    st.divider()

    # ── Layout: tabelas + formulário ──────────────────────────────────────────
    col_form, col_tabs = st.columns([4, 16])

    with col_tabs:
        max_meses_a = df_precos["mes"].nunique() if not df_precos.empty else 1
        max_meses_f = df_cotas["mes"].nunique()  if not df_cotas.empty else 1

        tab_a, tab_f, tab_rf_view = st.tabs(["Ações / FII", "Fundos", "Renda Fixa"])

        with tab_a:
            rows_a = []
            for _, a in df_acoes.iterrows():
                hist = df_precos[df_precos["ticker"] == a["ticker"]] if not df_precos.empty else pd.DataFrame()
                ultimo = hist.sort_values("mes").iloc[-1] if not hist.empty else None
                rows_a.append({
                    "Ticker":       a["ticker"],
                    "Nome":         a.get("nome", "—"),
                    "Meses":        len(hist),
                    "Último mês":   ultimo["mes"] if ultimo is not None else "—",
                    "Último preço": float(ultimo["preco_fechamento"]) if ultimo is not None else None,
                })
            st.dataframe(
                pd.DataFrame(rows_a),
                use_container_width=True, hide_index=True,
                column_config={
                    "Meses": st.column_config.ProgressColumn(
                        "Cobertura", min_value=0, max_value=max_meses_a, format="%d meses",
                    ),
                    "Último preço": st.column_config.NumberColumn("Último preço", format="R$ %.2f"),
                },
            )

        with tab_f:
            rows_f = []
            for _, f in df_fundos.iterrows():
                hist = df_cotas[df_cotas["cnpj"] == f["cnpj"]] if not df_cotas.empty else pd.DataFrame()
                ultimo = hist.sort_values("mes").iloc[-1] if not hist.empty else None
                rows_f.append({
                    "Nome":         f.get("nome", "—"),
                    "CNPJ":         f["cnpj"],
                    "Meses":        len(hist),
                    "Último mês":   ultimo["mes"] if ultimo is not None else "—",
                    "Última cota":  float(ultimo["cota_fechamento"]) if ultimo is not None else None,
                })
            st.dataframe(
                pd.DataFrame(rows_f),
                use_container_width=True, hide_index=True,
                column_config={
                    "Meses": st.column_config.ProgressColumn(
                        "Cobertura", min_value=0, max_value=max_meses_f, format="%d meses",
                    ),
                    "Última cota": st.column_config.NumberColumn("Última cota", format="R$ %.4f"),
                },
            )

        with tab_rf_view:
            if df_rf.empty:
                st.info("Nenhum instrumento de renda fixa cadastrado.")
            else:
                st.dataframe(
                    df_rf[["nome", "instrumento", "indexacao", "isento_ir", "emissor"]],
                    use_container_width=True, hide_index=True,
                    column_config={
                        "nome":        st.column_config.TextColumn("Nome"),
                        "instrumento": st.column_config.TextColumn("Instrumento"),
                        "indexacao":   st.column_config.TextColumn("Indexação"),
                        "isento_ir":   st.column_config.CheckboxColumn("IR Isento"),
                        "emissor":     st.column_config.TextColumn("Emissor"),
                    },
                )

    with col_form:
        st.caption("Adicionar ativo")
        tipo = st.radio("tipo", ["Ação / FII", "Fundo", "Renda Fixa"],
                        horizontal=True, label_visibility="collapsed")

        with st.form("form_add_ativo"):
            if tipo == "Ação / FII":
                tipo_ativo = st.selectbox("Tipo", ["Ação", "FII"])
                ticker = st.text_input("Ticker", placeholder="ex: PETR4").upper().strip()
                nome   = st.text_input("Nome", placeholder="ex: Petrobras")
                submit = st.form_submit_button("Adicionar", type="primary", use_container_width=True)

                if submit:
                    if not ticker or not nome:
                        st.error("Preencha ticker e nome.")
                    else:
                        try:
                            get_supabase().table("ativos_acoes").insert({"ticker": ticker, "nome": nome, "tipo": tipo_ativo}).execute()
                        except APIError as e:
                            if "23505" in str(e):
                                st.error(f"**{ticker}** já cadastrado.")
                            else:
                                st.error(f"Erro: {e}")
                            st.stop()
                        st.cache_data.clear()
                        with st.status("Adicionando ativo...", expanded=True) as s:
                            st.write("✅ Ativo registrado no banco de dados")
                            bar = st.progress(0, text="Importando preços históricos...")
                            try:
                                bar.progress(15, text="Conectando ao brapi.dev...")
                                resp = http.post(
                                    f"{functions_url()}/fetch-acoes",
                                    headers={**auth_header(), "Content-Type": "application/json"},
                                    json={"ticker": ticker},
                                    timeout=120,
                                )
                                bar.progress(85, text="Salvando no banco de dados...")
                                data = resp.json()
                                bar.progress(100, text="Concluído!")
                                if resp.status_code == 200:
                                    st.write(f"✅ {data.get('meses_inseridos', 0)} meses importados")
                                    s.update(label=f"{ticker} adicionado!", state="complete")
                                else:
                                    st.write(f"⚠️ Preços não importados: {data.get('error', resp.text)}")
                                    s.update(label=f"{ticker} cadastrado (preços pendentes)", state="error")
                            except Exception as e:
                                bar.progress(100, text="Falhou")
                                st.write(f"⚠️ Erro de conexão: {e}")
                                s.update(label=f"{ticker} cadastrado (preços pendentes)", state="error")

            elif tipo == "Fundo":
                cnpj      = st.text_input("CNPJ", placeholder="ex: 12.345.678/0001-90").strip()
                nome      = st.text_input("Nome", placeholder="ex: Riza Lotus Plus")
                categoria = st.selectbox("Categoria", ["RF DI", "RF Simples", "Multimercado RF", "Multimercado", "Long Biased", "FIA"])
                submit    = st.form_submit_button("Adicionar", type="primary", use_container_width=True)

                if submit:
                    if not cnpj or not nome:
                        st.error("Preencha CNPJ e nome.")
                    else:
                        res = get_supabase().table("ativos_fundos").insert({"cnpj": cnpj, "nome": nome, "categoria": categoria}).execute()
                        if res.data:
                            st.success(f"{nome} adicionado.")
                            st.cache_data.clear()
                            st.info("Para importar histórico de cotas:")
                            st.code(f'python extract_fundos.py "{cnpj}"', language="bash")
                        else:
                            st.error(f"Erro: {res}")

            elif tipo == "Renda Fixa":
                nome        = st.text_input("Nome", placeholder="ex: CDB BTG 110% CDI")
                instrumento = st.selectbox("Instrumento", ["CDB", "LCI", "LCA", "Tesouro Direto", "Debênture"])
                indexacao   = st.selectbox("Indexação", ["pos_fixado_cdi", "pos_fixado_selic", "prefixado", "ipca_mais"])
                isento_ir   = st.checkbox("Isento de IR")
                emissor     = st.text_input("Emissor", placeholder="ex: BTG Pactual (opcional)")
                submit      = st.form_submit_button("Adicionar", type="primary", use_container_width=True)

                if submit:
                    if not nome:
                        st.error("Preencha o nome.")
                    else:
                        try:
                            get_supabase().table("ativos_renda_fixa").insert({
                                "nome": nome, "instrumento": instrumento,
                                "indexacao": indexacao, "isento_ir": isento_ir,
                                "emissor": emissor or None,
                            }).execute()
                            st.success(f"**{nome}** adicionado.")
                            st.cache_data.clear()
                        except APIError as e:
                            if "23505" in str(e):
                                st.error(f"**{nome}** já cadastrado.")
                            else:
                                st.error(f"Erro: {e}")

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
        INDICES = {
            "cdi_mensal":              "CDI",
            "ipca_mensal":             "IPCA",
            "selic_mensal":            "Selic",
            "ibovespa_retorno_mensal": "IBOVESPA",
        }

        df_sorted = df.sort_values("mes").reset_index(drop=True)

        col_esq, col_dir = st.columns([1, 2])

        # ── Esquerda: valor mais recente de cada índice ──────────────────────
        with col_esq:
            ultimo = df_sorted.iloc[-1]
            mes_label = pd.to_datetime(ultimo["mes"] + "-01").strftime("%b/%Y")
            st.caption(f"Último mês disponível: **{mes_label}**")

            for campo, label in INDICES.items():
                val = ultimo.get(campo)
                texto = f"{val:.2f}%" if pd.notna(val) else "—"
                st.markdown(
                    f"""
                    <div style="padding:22px 0 14px 0; border-bottom:1px solid #333;">
                        <div style="font-size:22px; color:#aaa; font-weight:500; margin-bottom:4px;">{label}</div>
                        <div style="font-size:84px; font-weight:700; line-height:1.0;">{texto}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # ── Direita: gráfico histórico 5 anos ────────────────────────────────
        with col_dir:
            df_chart = df_sorted[["mes"] + list(INDICES.keys())].copy()
            df_chart["mes"] = pd.to_datetime(df_chart["mes"] + "-01")

            CORES = ["#ffffff", "#7dd3fc", "#86efac", "#fda4af"]

            fig = go.Figure()
            for (campo, label), cor in zip(INDICES.items(), CORES):
                serie = df_chart[["mes", campo]].dropna()
                fig.add_trace(go.Scatter(
                    x=serie["mes"],
                    y=serie[campo],
                    name=label,
                    mode="lines",
                    line=dict(width=2.5, color=cor),
                ))

            BG = "#0e1117"
            fig.update_layout(
                height=720,
                margin=dict(t=20, b=20, l=0, r=10),
                plot_bgcolor=BG,
                paper_bgcolor=BG,
                font=dict(color="#ffffff", size=14),
                legend=dict(
                    orientation="h", y=-0.06,
                    font=dict(size=14, color="#ffffff"),
                ),
                xaxis=dict(
                    showgrid=False,
                    tickfont=dict(size=13, color="#aaaaaa"),
                    linecolor="#333",
                ),
                yaxis=dict(
                    ticksuffix="%",
                    autorange=True,
                    showgrid=True,
                    gridcolor="#1f2937",
                    tickfont=dict(size=13, color="#aaaaaa"),
                    linecolor="#333",
                ),
                hovermode="x unified",
                hoverlabel=dict(bgcolor="#1f2937", font_color="#ffffff"),
            )

            st.plotly_chart(fig, use_container_width=True)
