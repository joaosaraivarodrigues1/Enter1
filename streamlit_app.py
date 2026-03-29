# -*- coding: utf-8 -*-
import time

import streamlit as st
import pandas as pd
import requests as http
import plotly.graph_objects as go

from supabase import create_client
from postgrest.exceptions import APIError

from calculos import (
    calcular_retorno_acoes,
    calcular_retorno_fundos,
    calcular_retorno_rf,
    calcular_retorno_portfolio,
    calcular_alfas,
)

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

def gerar_recomendacao(cliente_id: str, mes: str) -> str:
    """Dispara a Edge Function, recebe job_id e faz polling até status=done."""
    # 1. Disparar
    resp = http.post(
        functions_url() + "/gerar-recomendacao",
        headers={
            **auth_header(),
            "apikey": st.secrets["SUPABASE_KEY"].strip(),
            "Content-Type": "application/json",
        },
        json={"cliente_id": cliente_id, "mes": mes},
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json()["job_id"]

    # 2. Polling na tabela recomendacoes (até 5 minutos)
    sb = get_supabase()
    for _ in range(100):
        time.sleep(3)
        row = (
            sb.table("recomendacoes")
            .select("status, resultado, erro")
            .eq("job_id", job_id)
            .single()
            .execute()
            .data
        )
        if row["status"] == "done":
            return row["resultado"]
        if row["status"] == "error":
            raise RuntimeError(row.get("erro") or "Erro no processamento Rivet")

    raise TimeoutError("Timeout: recomendação não foi gerada em 5 minutos")

# ── Navegação ─────────────────────────────────────────────────────────────────

if "page" not in st.session_state:
    st.session_state.page = "home"
if "mes_selecionado" not in st.session_state:
    st.session_state.mes_selecionado = None

@st.dialog("Período de referência")
def modal_selecionar_data():
    df_p = load_table("precos_acoes")
    df_c = load_table("cotas_fundos")
    df_m = load_table("dados_mercado")

    meses = set()
    if not df_p.empty: meses.update(df_p["mes"].dropna().unique())
    if not df_c.empty: meses.update(df_c["mes"].dropna().unique())
    if not df_m.empty: meses.update(df_m["mes"].dropna().unique())

    meses_sorted = sorted(meses)
    if not meses_sorted:
        st.info("Nenhum dado histórico encontrado.")
        return

    atual = st.session_state.mes_selecionado
    idx = meses_sorted.index(atual) if atual in meses_sorted else len(meses_sorted) - 1

    mes_escolhido = st.selectbox(
        "Mês de referência",
        options=meses_sorted,
        index=idx,
        format_func=lambda m: pd.to_datetime(m + "-01").strftime("%b/%Y"),
    )
    st.caption(f"{len(meses_sorted)} meses disponíveis · {meses_sorted[0]} → {meses_sorted[-1]}")

    if st.button("Confirmar", type="primary", use_container_width=True):
        st.session_state.mes_selecionado = mes_escolhido
        st.rerun()

st.title("Xp - Análise de portfólio e rendimentos")

col_home, col_clientes, col_ativos, col_indices, col_data, *_ = st.columns([1, 1, 1, 1, 1, 3])

if col_home.button("Home", use_container_width=True):
    st.session_state.page = "home"
if col_clientes.button("Clientes", use_container_width=True):
    st.session_state.page = "clientes"
if col_ativos.button("Ativos Disponíveis", use_container_width=True):
    st.session_state.page = "ativos"
if col_indices.button("Índice Mercado", use_container_width=True):
    st.session_state.page = "indice_mercado"

_mes_sel = st.session_state.mes_selecionado
_data_label = pd.to_datetime(_mes_sel + "-01").strftime("%b/%Y") if _mes_sel else "Data"
if col_data.button(_data_label, use_container_width=True):
    modal_selecionar_data()

st.divider()

# ── Páginas ───────────────────────────────────────────────────────────────────

if st.session_state.page == "home":
    st.markdown("## Plataforma de Gestão de Portfólios")
    st.markdown(
        "Solução integrada para **calcular rendimentos**, comparar performance com benchmarks de mercado "
        "e gerar **recomendações personalizadas** para cada cliente, com base no perfil de risco e na composição atual da carteira."
    )

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Cálculo de Rendimentos")
        st.markdown("""
Consolida automaticamente todas as posições do cliente — **ações, FIIs, fundos e renda fixa** —
e calcula o retorno mensal e acumulado de cada ativo.

Os resultados são comparados com os principais benchmarks:

| Benchmark | Descrição |
|-----------|-----------|
| CDI | Referência de renda fixa |
| IPCA | Inflação oficial |
| Selic | Taxa básica de juros |
| IBOVESPA | Referência de renda variável |

Assim é possível identificar quais ativos superam o mercado e quais estão abaixo do esperado para o perfil do cliente.
""")

    with col2:
        st.markdown("#### Recomendações por Cliente")
        st.markdown("""
Com base no **perfil de risco** (conservador, moderado ou agressivo) e na distribuição atual da carteira,
o sistema identifica oportunidades de rebalanceamento.

O fluxo de análise segue três etapas:

1. **Diagnóstico** — leitura da carteira atual e cálculo de exposição por classe de ativo
2. **Comparação** — performance vs. benchmarks no mês selecionado
3. **Recomendação** — sugestão de ativos disponíveis no catálogo alinhados ao perfil

As recomendações são geradas por uma Edge Function que combina os dados de mercado com as posições do cliente.
""")

    with col3:
        st.markdown("#### Estrutura de Dados")
        st.markdown("""
Os dados são coletados de fontes públicas e armazenados no **Supabase** com atualização mensal.

**Catálogo de ativos**
- `ativos_acoes` / `ativos_fundos` / `ativos_renda_fixa`

**Posições por cliente**
- `posicoes_acoes` / `posicoes_fundos` / `posicoes_renda_fixa`

**Série histórica**
- `precos_acoes` — preços mensais via brapi.dev
- `cotas_fundos` — cotas mensais via CVM (Informe Diário)
- `dados_mercado` — CDI, IPCA, Selic, IBOVESPA via BCB API e brapi.dev

**Clientes**
- `clientes` — perfil de risco e dados cadastrais
""")

    st.divider()

    st.markdown("#### Como usar")
    c1, c2, c3, c4 = st.columns(4)
    c1.info("**1. Selecione o período**\n\nUse o botão de data no menu para escolher o mês de referência da análise.")
    c2.info("**2. Acesse Clientes**\n\nEscolha um cliente para ver a carteira consolidada, os rendimentos mensais e as recomendações geradas.")
    c3.info("**3. Explore Ativos**\n\nConsulte o catálogo completo de ações, FIIs e fundos disponíveis para alocação.")
    c4.info("**4. Acompanhe o Mercado**\n\nVeja a evolução dos benchmarks no tempo e entenda o contexto macro de cada período.")

elif st.session_state.page == "clientes":
    st.subheader("Clientes")

    # ── Carregar todos os dados uma vez ───────────────────────────────────────
    df_clientes      = load_table("clientes")
    df_pos_acoes     = load_table("posicoes_acoes")
    df_pos_fundos    = load_table("posicoes_fundos")
    df_pos_rf        = load_table("posicoes_renda_fixa")
    df_ativos_acoes  = load_table("ativos_acoes")
    df_ativos_fundos = load_table("ativos_fundos")
    df_ativos_rf     = load_table("ativos_renda_fixa")
    df_precos        = load_table("precos_acoes")
    df_cotas         = load_table("cotas_fundos")
    df_mercado       = load_table("dados_mercado")

    nomes = df_clientes["nome"].tolist() if not df_clientes.empty else []
    ids   = df_clientes["id"].tolist()   if not df_clientes.empty else []

    # Mês de referência — usa seleção do usuário ou último disponível
    meses_ord = sorted(df_mercado["mes"].unique()) if not df_mercado.empty else []
    mes_sel   = st.session_state.mes_selecionado
    if mes_sel and mes_sel in meses_ord:
        mes_atual = mes_sel
        idx_sel   = meses_ord.index(mes_sel)
        mes_ant   = meses_ord[idx_sel - 1] if idx_sel > 0 else None
    else:
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

            col_b0, col_b1, col_b2, _ = st.columns([3, 3, 3, 1])
            if col_b0.button("Dados Pessoais", key=f"btn_dados_{cliente_id}", use_container_width=True,
                             type="primary" if st.session_state[key] == "dados" else "secondary"):
                st.session_state[key] = "dados"
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

            # ── Dados Pessoais ────────────────────────────────────────────────
            if st.session_state[key] == "dados":
                row_cli = df_clientes[df_clientes["id"] == cliente_id].iloc[0]
                perfil_texto = row_cli.get("perfil_de_risco", "") or ""
                nome_cli = row_cli.get("nome", "—")

                CORES_PERFIL = {
                    "Conservador": ("#22c55e", "#052e16"),
                    "Moderado":    ("#3b82f6", "#0c1a3a"),
                    "Arrojado":    ("#f97316", "#3a1a00"),
                    "Agressivo":   ("#ef4444", "#3a0c0c"),
                }

                if perfil_texto:
                    linhas = perfil_texto.splitlines()
                    classificacao = next(
                        (l.replace("Classificação do Perfil de Investimento:", "").strip()
                         for l in linhas if "Classificação" in l), "—"
                    )
                    cor_badge, cor_bg = CORES_PERFIL.get(classificacao, ("#6b7280", "#1a1f2e"))

                    # ── Cabeçalho ──────────────────────────────────────────────
                    _, card_col, _ = st.columns([3, 4, 3])
                    with card_col:
                        st.markdown(f"""
<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
border-radius:20px;padding:44px 52px 36px 52px;text-align:center;margin-bottom:8px;">
  <h1 style="font-size:3rem;font-weight:700;margin:0 0 18px 0;
  letter-spacing:-1px;line-height:1.1;">{nome_cli}</h1>
  <span style="background:{cor_badge};color:#fff;padding:6px 22px;border-radius:24px;
  font-size:1rem;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;">
  {classificacao}</span>
  <p style="font-size:1.2rem;color:#9ca3af;margin:22px 0 0 0;font-weight:400;
  letter-spacing:0.1px;">Perfil de Investimento · XP Assessoria</p>
</div>""", unsafe_allow_html=True)

                    st.write("")

                    # ── Corpo do perfil ────────────────────────────────────────
                    # Parseia seções numeradas e sub-itens
                    secoes = []   # lista de (titulo, [(sub_titulo, texto)])
                    sec_titulo = None; sub_titulo = None; buf = []

                    for linha in linhas[2:]:
                        l = linha.strip()
                        if not l:
                            if buf and sub_titulo is not None:
                                if secoes: secoes[-1][1].append((sub_titulo, " ".join(buf)))
                                sub_titulo = None; buf = []
                            elif buf and sec_titulo:
                                if secoes: secoes[-1][1].append((None, " ".join(buf)))
                                buf = []
                            continue
                        if l[0].isdigit() and l[1] == ".":
                            if buf and secoes:
                                secoes[-1][1].append((sub_titulo, " ".join(buf)))
                                buf = []; sub_titulo = None
                            sec_titulo = l[2:].strip() if len(l) > 2 else l
                            secoes.append((sec_titulo, []))
                        elif len(l) >= 2 and l[0].isalpha() and l[1] == "." and l[0].islower():
                            if buf and secoes:
                                secoes[-1][1].append((sub_titulo, " ".join(buf)))
                                buf = []
                            sub_titulo = l[2:].strip() if len(l) > 2 else l
                        else:
                            buf.append(l)
                    if buf and secoes:
                        secoes[-1][1].append((sub_titulo, " ".join(buf)))

                    _, body_col, _ = st.columns([3, 4, 3])
                    with body_col:
                        for sec_t, items in secoes:
                            st.markdown(f"""
<div style="margin-bottom:28px;">
  <p style="font-size:1.05rem;font-weight:700;color:{cor_badge};
  text-transform:uppercase;letter-spacing:0.8px;margin:0 0 12px 0;
  border-left:3px solid {cor_badge};padding-left:10px;">{sec_t}</p>""",
                                unsafe_allow_html=True)
                            for sub_t, texto in items:
                                if sub_t:
                                    st.markdown(f"""
  <p style="font-size:1rem;font-weight:600;color:#e5e7eb;margin:14px 0 4px 0;">{sub_t}</p>
  <p style="font-size:0.95rem;color:#9ca3af;line-height:1.7;margin:0;">{texto}</p>""",
                                        unsafe_allow_html=True)
                                else:
                                    st.markdown(f"""
  <p style="font-size:0.95rem;color:#9ca3af;line-height:1.7;margin:0;">{texto}</p>""",
                                        unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.info("Perfil de risco não cadastrado para este cliente.")

            # ── Carteira ──────────────────────────────────────────────────────
            elif st.session_state[key] == "carteira":
                # Totais por categoria
                total_acoes_c = 0.0
                for _, p in acoes_c.iterrows():
                    pa_r = df_precos[(df_precos["ticker"] == p["ticker"]) & (df_precos["mes"] == mes_atual)] if mes_atual else pd.DataFrame()
                    total_acoes_c += float(pa_r.iloc[0]["preco_fechamento"]) * float(p["quantidade"]) if not pa_r.empty else float(p["quantidade"]) * float(p["preco_medio_compra"])

                total_fundos_c = 0.0
                for _, p in fundos_c.iterrows():
                    ca_r = df_cotas[(df_cotas["cnpj"] == p["cnpj"]) & (df_cotas["mes"] == mes_atual)] if mes_atual else pd.DataFrame()
                    total_fundos_c += float(ca_r.iloc[0]["cota_fechamento"]) * float(p["numero_cotas"]) if not ca_r.empty else float(p["valor_aplicado"])

                total_rf_c = rf_c["valor_aplicado"].astype(float).sum() if not rf_c.empty else 0.0
                total_g = total_acoes_c + total_fundos_c + total_rf_c or 1.0

                def _pct(v): return v / total_g * 100

                COLS_A = [0.9, 1.8, 0.8, 1.1, 1.1, 1.1, 1.1, 0.8, 1.1, 0.5]
                HDRS_A = ["Ticker", "Nome", "Qtd", "P. Médio", "V. Invest.", "P. Atual", "V. Atual", "Var %", "Data compra", ""]
                COLS_F = [2.2, 1.8, 0.9, 1.1, 1.1, 1.1, 0.8, 1.1, 0.5]
                HDRS_F = ["Fundo", "CNPJ", "Cotas", "V. Aplicado", "Cota Atual", "V. Atual", "Var %", "Data invest.", ""]
                COLS_R = [2.2, 1.3, 0.8, 0.9, 1.1, 1.1, 1.1, 0.5]
                HDRS_R = ["Instrumento", "Indexação", "Taxa", "Unidade", "V. Aplicado", "Início", "Vencimento", ""]

                def _sec_header(label, n_pos, total, pct, tkey):
                    if tkey not in st.session_state:
                        st.session_state[tkey] = False
                    _ha, _hb, _hc = st.columns([0.35, 7, 3])
                    with _ha:
                        if st.button("▼" if st.session_state[tkey] else "▶", key=f"tog_{tkey}"):
                            st.session_state[tkey] = not st.session_state[tkey]; st.rerun()
                    _hb.markdown(
                        f'<p style="font-size:1.2rem;font-weight:400;margin:0;padding:4px 0">'
                        f'{label}<span style="font-size:1.0rem;color:#9ca3af;margin-left:2.5rem">'
                        f'{n_pos} posições</span></p>',
                        unsafe_allow_html=True,
                    )
                    _hc.markdown(
                        f'<p style="text-align:right;font-size:1.05rem;font-weight:400;margin:0;padding:4px 0">'
                        f'R$ {total:,.2f}&ensp;&ensp;{pct:.1f}%</p>',
                        unsafe_allow_html=True,
                    )
                    st.divider()
                    return st.session_state[tkey]

                # ── Ações ──────────────────────────────────────────────────────
                n_a = len(acoes_c)
                if _sec_header("Ações", n_a, total_acoes_c, _pct(total_acoes_c), f"exp_a_{cliente_id}"):
                    hc = st.columns(COLS_A)
                    for c, h in zip(hc, HDRS_A):
                        c.markdown(f"**{h}**")
                    st.divider()

                    for _, p in acoes_c.iterrows():
                        qtd = float(p["quantidade"]); pm = float(p["preco_medio_compra"]); vi = qtd * pm
                        nome_at = "—"
                        if not df_ativos_acoes.empty:
                            m = df_ativos_acoes[df_ativos_acoes["ticker"] == p["ticker"]]
                            if not m.empty: nome_at = m.iloc[0]["nome"]
                        pa_r = df_precos[(df_precos["ticker"] == p["ticker"]) & (df_precos["mes"] == mes_atual)] if mes_atual else pd.DataFrame()
                        pa  = float(pa_r.iloc[0]["preco_fechamento"]) if not pa_r.empty else None
                        va  = pa * qtd if pa else None
                        var = (pa - pm) / pm * 100 if pa else None

                        rc = st.columns(COLS_A)
                        rc[0].write(p["ticker"])
                        rc[1].write(nome_at)
                        rc[2].write(f"{qtd:,.0f}")
                        rc[3].write(f"R$ {pm:,.2f}")
                        rc[4].markdown(f"**R$ {vi:,.0f}**")
                        rc[5].write(f"R$ {pa:,.2f}" if pa else "—")
                        rc[6].write(f"R$ {va:,.0f}" if va else "—")
                        if var is not None:
                            sg = "+" if var >= 0 else ""; cor = "green" if var >= 0 else "red"
                            rc[7].markdown(f":{cor}[**{sg}{var:.1f}%**]")
                        else:
                            rc[7].write("—")
                        rc[8].write(str(p.get("data_compra", "—")))
                        with rc[9]:
                            with st.popover("🗑"):
                                st.caption(f"Remover **{p['ticker']}**?")
                                if st.button("Confirmar", key=f"del_a_{p['id']}", type="primary"):
                                    get_supabase().table("posicoes_acoes").delete().eq("id", str(p["id"])).execute()
                                    st.cache_data.clear(); st.rerun()

                    st.divider()
                    add_a = f"add_acao_{cliente_id}"
                    if not st.session_state.get(add_a):
                        if st.button("＋ Adicionar ação", key=f"btn_add_a_{cliente_id}"):
                            st.session_state[add_a] = True; st.rerun()
                    else:
                        if df_ativos_acoes.empty:
                            st.warning("Nenhuma ação cadastrada em Ativos Disponíveis.")
                        else:
                            opcoes_a = {row["ticker"]: row.get("nome", row["ticker"])
                                        for _, row in df_ativos_acoes.iterrows()}
                            ac = st.columns(COLS_A)
                            with ac[0]:
                                tk_sel = st.selectbox("Ticker", options=list(opcoes_a.keys()),
                                    key=f"na_tk_{cliente_id}", label_visibility="collapsed")
                            ac[1].markdown(opcoes_a.get(tk_sel, "—"))
                            with ac[2]:
                                qtd_str = st.text_input("Qtd", key=f"na_qtd_{cliente_id}",
                                    label_visibility="collapsed", placeholder="Qtd")
                            try:
                                qtd_v = float(qtd_str.replace(",", ".")) if qtd_str.strip() else 0.0
                            except ValueError:
                                qtd_v = 0.0
                            pa_r = df_precos[(df_precos["ticker"] == tk_sel) & (df_precos["mes"] == mes_atual)] if mes_atual and tk_sel else pd.DataFrame()
                            preco_at = float(pa_r.iloc[0]["preco_fechamento"]) if not pa_r.empty else None
                            total_ac = preco_at * qtd_v if (preco_at and qtd_v > 0) else None
                            ac[3].markdown(f"R$ {preco_at:,.2f}" if preco_at else "—")
                            ac[4].markdown(f"**R$ {total_ac:,.0f}**" if total_ac else "—")
                            all_a = bool(tk_sel) and qtd_v > 0 and preco_at is not None
                            with ac[9]:
                                if st.button("Salvar", key=f"save_a_{cliente_id}", type="primary", disabled=not all_a, use_container_width=True):
                                    data_compra = (mes_atual + "-01") if mes_atual else pd.Timestamp.today().strftime("%Y-%m-%d")
                                    get_supabase().table("posicoes_acoes").insert({
                                        "cliente_id": cliente_id, "ticker": tk_sel,
                                        "quantidade": qtd_v, "preco_medio_compra": preco_at,
                                        "data_compra": data_compra,
                                    }).execute()
                                    st.session_state[add_a] = False; st.cache_data.clear(); st.rerun()
                        if st.button("✕ Cancelar", key=f"cancel_a_{cliente_id}"):
                            st.session_state[add_a] = False; st.rerun()

                # ── Fundos ─────────────────────────────────────────────────────
                n_f = len(fundos_c)
                if _sec_header("Fundos", n_f, total_fundos_c, _pct(total_fundos_c), f"exp_f_{cliente_id}"):
                    hc = st.columns(COLS_F)
                    for c, h in zip(hc, HDRS_F):
                        c.markdown(f"**{h}**")
                    st.divider()

                    for _, p in fundos_c.iterrows():
                        nome_f = "—"
                        if not df_ativos_fundos.empty:
                            m = df_ativos_fundos[df_ativos_fundos["cnpj"] == p["cnpj"]]
                            if not m.empty: nome_f = m.iloc[0]["nome"]
                        ca_r  = df_cotas[(df_cotas["cnpj"] == p["cnpj"]) & (df_cotas["mes"] == mes_atual)] if mes_atual else pd.DataFrame()
                        ca    = float(ca_r.iloc[0]["cota_fechamento"]) if not ca_r.empty else None
                        cotas = float(p["numero_cotas"]); vaplic = float(p["valor_aplicado"])
                        va    = ca * cotas if ca else None
                        var   = (va - vaplic) / vaplic * 100 if va else None

                        rc = st.columns(COLS_F)
                        rc[0].write(nome_f)
                        rc[1].write(p["cnpj"])
                        rc[2].write(f"{cotas:,.0f}")
                        rc[3].markdown(f"**R$ {vaplic:,.0f}**")
                        rc[4].write(f"R$ {ca:,.4f}" if ca else "—")
                        rc[5].write(f"R$ {va:,.0f}" if va else "—")
                        if var is not None:
                            sg = "+" if var >= 0 else ""; cor = "green" if var >= 0 else "red"
                            rc[6].markdown(f":{cor}[**{sg}{var:.1f}%**]")
                        else:
                            rc[6].write("—")
                        rc[7].write(str(p.get("data_investimento", "—")))
                        with rc[8]:
                            with st.popover("🗑"):
                                st.caption(f"Remover **{nome_f}**?")
                                if st.button("Confirmar", key=f"del_f_{p['id']}", type="primary"):
                                    get_supabase().table("posicoes_fundos").delete().eq("id", str(p["id"])).execute()
                                    st.cache_data.clear(); st.rerun()

                    st.divider()
                    add_f = f"add_fundo_{cliente_id}"
                    if not st.session_state.get(add_f):
                        if st.button("＋ Adicionar fundo", key=f"btn_add_f_{cliente_id}"):
                            st.session_state[add_f] = True; st.rerun()
                    else:
                        if df_ativos_fundos.empty:
                            st.warning("Nenhum fundo cadastrado em Ativos Disponíveis.")
                        else:
                            opcoes_f = {row["cnpj"]: row["nome"] for _, row in df_ativos_fundos.iterrows()}
                            fc = st.columns(COLS_F)
                            with fc[0]:
                                cnpj_sel = st.selectbox("Fundo", options=list(opcoes_f.keys()),
                                    format_func=lambda x: opcoes_f[x],
                                    key=f"nf_cnpj_{cliente_id}", label_visibility="collapsed")
                            fc[1].markdown(cnpj_sel or "—")
                            with fc[2]:
                                cotas_str = st.text_input("Cotas", key=f"nf_cotas_{cliente_id}",
                                    label_visibility="collapsed", placeholder="Nº cotas")
                            try:
                                cotas_v = float(cotas_str.replace(",", ".")) if cotas_str.strip() else 0.0
                            except ValueError:
                                cotas_v = 0.0
                            ca_r = df_cotas[(df_cotas["cnpj"] == cnpj_sel) & (df_cotas["mes"] == mes_atual)] if mes_atual and cnpj_sel else pd.DataFrame()
                            cota_at = float(ca_r.iloc[0]["cota_fechamento"]) if not ca_r.empty else None
                            vaplic_calc = cotas_v * cota_at if (cota_at and cotas_v > 0) else None
                            fc[3].markdown(f"**R$ {vaplic_calc:,.0f}**" if vaplic_calc else "—")
                            fc[4].markdown(f"R$ {cota_at:,.4f}" if cota_at else "—")
                            all_f = cotas_v > 0 and cota_at is not None
                            with fc[8]:
                                if st.button("Salvar", key=f"save_f_{cliente_id}", type="primary", disabled=not all_f, use_container_width=True):
                                    data_inv = (mes_atual + "-01") if mes_atual else pd.Timestamp.today().strftime("%Y-%m-%d")
                                    get_supabase().table("posicoes_fundos").insert({
                                        "cliente_id": cliente_id, "cnpj": cnpj_sel,
                                        "numero_cotas": cotas_v, "valor_aplicado": vaplic_calc,
                                        "data_investimento": data_inv,
                                    }).execute()
                                    st.session_state[add_f] = False; st.cache_data.clear(); st.rerun()
                        if st.button("✕ Cancelar", key=f"cancel_f_{cliente_id}"):
                            st.session_state[add_f] = False; st.rerun()

                # ── Renda Fixa ─────────────────────────────────────────────────
                n_r = len(rf_c)
                if _sec_header("Renda Fixa", n_r, total_rf_c, _pct(total_rf_c), f"exp_r_{cliente_id}"):
                    hc = st.columns(COLS_R)
                    for c, h in zip(hc, HDRS_R):
                        c.markdown(f"**{h}**")
                    st.divider()

                    for _, p in rf_c.iterrows():
                        nome_rf = "—"; idx_rf = "—"
                        if not df_ativos_rf.empty:
                            m = df_ativos_rf[df_ativos_rf["id"] == p["ativo_id"]]
                            if not m.empty:
                                nome_rf = m.iloc[0]["nome"]
                                idx_rf  = m.iloc[0].get("indexacao", "—")

                        rc = st.columns(COLS_R)
                        rc[0].write(nome_rf)
                        rc[1].write(idx_rf)
                        rc[2].write(str(p.get("taxa_contratada", "—")))
                        rc[3].write(str(p.get("unidade_taxa", "—")))
                        rc[4].markdown(f"**R$ {float(p['valor_aplicado']):,.0f}**")
                        rc[5].write(str(p.get("data_inicio", "—")))
                        rc[6].write(str(p.get("data_vencimento", "—")))
                        with rc[7]:
                            with st.popover("🗑"):
                                st.caption(f"Remover **{nome_rf}**?")
                                if st.button("Confirmar", key=f"del_r_{p['id']}", type="primary"):
                                    get_supabase().table("posicoes_renda_fixa").delete().eq("id", str(p["id"])).execute()
                                    st.cache_data.clear(); st.rerun()

                    st.divider()
                    add_r = f"add_rf_{cliente_id}"
                    if not st.session_state.get(add_r):
                        if st.button("＋ Adicionar renda fixa", key=f"btn_add_r_{cliente_id}"):
                            st.session_state[add_r] = True; st.rerun()
                    else:
                        if df_ativos_rf.empty:
                            st.warning("Nenhum instrumento cadastrado em Ativos Disponíveis.")
                        else:
                            opcoes_r = {row["id"]: row["nome"] for _, row in df_ativos_rf.iterrows()}
                            rc2 = st.columns(COLS_R)
                            with rc2[0]:
                                ativo_sel = st.selectbox("Instrumento", options=list(opcoes_r.keys()),
                                    format_func=lambda x: opcoes_r[x],
                                    key=f"nr_ativo_{cliente_id}", label_visibility="collapsed")
                            with rc2[2]:
                                taxa_str = st.text_input("Taxa", key=f"nr_taxa_{cliente_id}",
                                    label_visibility="collapsed", placeholder="ex: 110")
                            try:
                                taxa_v = float(taxa_str.replace(",", ".")) if taxa_str.strip() else 0.0
                            except ValueError:
                                taxa_v = 0.0
                            with rc2[3]: unid_v = st.selectbox("Unidade", ["% CDI", "% Selic", "% a.a."], key=f"nr_unid_{cliente_id}", label_visibility="collapsed")
                            with rc2[4]:
                                vaplic_str = st.text_input("V.Aplic", key=f"nr_vaplic_{cliente_id}",
                                    label_visibility="collapsed", placeholder="ex: 10000")
                            try:
                                vaplic_r = float(vaplic_str.replace(",", ".")) if vaplic_str.strip() else 0.0
                            except ValueError:
                                vaplic_r = 0.0
                            with rc2[5]: dt_ini_v  = st.date_input("Início", key=f"nr_ini_{cliente_id}",  label_visibility="collapsed")
                            with rc2[6]: dt_venc_v = st.date_input("Venc.",  key=f"nr_venc_{cliente_id}", label_visibility="collapsed")
                            all_r = taxa_v > 0 and vaplic_r > 0
                            with rc2[7]:
                                if st.button("Salvar", key=f"save_r_{cliente_id}", type="primary", disabled=not all_r):
                                    get_supabase().table("posicoes_renda_fixa").insert({
                                        "cliente_id": cliente_id, "ativo_id": ativo_sel,
                                        "taxa_contratada": taxa_v, "unidade_taxa": unid_v,
                                        "valor_aplicado": vaplic_r,
                                        "data_inicio": str(dt_ini_v),
                                        "data_vencimento": str(dt_venc_v),
                                    }).execute()
                                    st.session_state[add_r] = False; st.cache_data.clear(); st.rerun()
                        if st.button("✕ Cancelar", key=f"cancel_r_{cliente_id}"):
                            st.session_state[add_r] = False; st.rerun()

            # ── Resultados ────────────────────────────────────────────────────
            elif st.session_state[key] == "resultados":
                if not mes_atual or not mes_ant:
                    st.info("Selecione um mês com pelo menos dois períodos disponíveis.")
                else:
                    mes_label = pd.to_datetime(mes_atual + "-01").strftime("%b/%Y")
                    st.caption(f"Mês de referência: **{mes_label}**")

                    mercado = row_merc.to_dict() if row_merc is not None else {}

                    # ── Módulos 1, 2, 3 — Retorno individual por ativo ────────
                    linhas_acoes  = calcular_retorno_acoes(acoes_c, df_precos, df_ativos_acoes, mes_atual, mes_ant)
                    linhas_fundos = calcular_retorno_fundos(fundos_c, df_cotas, df_ativos_fundos, mes_atual, mes_ant)
                    linhas_rf     = calcular_retorno_rf(rf_c, df_ativos_rf, mercado)

                    todas_linhas = linhas_acoes + linhas_fundos + linhas_rf

                    # ── Módulo 4 — Retorno total ponderado ────────────────────
                    portfolio = calcular_retorno_portfolio(todas_linhas)

                    # ── Módulo 5 — Alfas vs. benchmarks ──────────────────────
                    alfas = calcular_alfas(portfolio["retorno_portfolio"], linhas_acoes, mercado)

                    # ── Métricas de topo ──────────────────────────────────────
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric(
                        "Retorno do portfólio",
                        f"{portfolio['retorno_portfolio']:.2f}%",
                    )
                    m2.metric(
                        "Variação no mês",
                        f"R$ {portfolio['variacao_total_rs']:+,.2f}",
                    )
                    m3.metric(
                        "Valor total",
                        f"R$ {portfolio['valor_total']:,.2f}",
                    )
                    m4.metric(
                        "Alfa vs CDI",
                        f"{alfas['alfa_cdi']:+.2f} p.p.",
                        help="Retorno do portfólio menos CDI do mês",
                    )

                    st.divider()

                    # ── Tabela de ativos ──────────────────────────────────────
                    st.subheader("Ativos")
                    if todas_linhas:
                        df_ret = pd.DataFrame([{
                            "Ativo":            l["ativo"],
                            "Tipo":             l["tipo"],
                            "Retorno mês (%)":  l["retorno_mes"],
                            "Peso (%)":         l["peso"] * 100 if l.get("peso") is not None else None,
                            "Contribuição (%)": l["contribuicao"],
                            "Variação R$":      l["variacao_rs"],
                            "Valor atual":      l["valor_posicao"],
                        } for l in todas_linhas])

                        st.dataframe(
                            df_ret,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Retorno mês (%)":  st.column_config.NumberColumn(format="%.2f%%"),
                                "Peso (%)":         st.column_config.NumberColumn(format="%.2f%%"),
                                "Contribuição (%)": st.column_config.NumberColumn(format="%.3f%%"),
                                "Variação R$":      st.column_config.NumberColumn(format="R$ %.2f"),
                                "Valor atual":      st.column_config.NumberColumn(format="R$ %.2f"),
                            },
                        )
                    else:
                        st.info("Nenhuma posição cadastrada para este cliente.")

                    # ── Destaques do mês ──────────────────────────────────────
                    contributors = portfolio["top_contributors"]
                    detractors   = portfolio["top_detractors"]

                    if contributors or detractors:
                        st.divider()
                        col_pos, col_neg = st.columns(2)

                        with col_pos:
                            st.markdown("**Maiores contribuidores**")
                            for item in contributors:
                                st.metric(
                                    item["ativo"],
                                    f"{item['contribuicao']:+.3f}%",
                                    f"Retorno: {item['retorno_mes']:+.2f}%",
                                )

                        with col_neg:
                            st.markdown("**Maiores detratores**")
                            if detractors:
                                for item in detractors:
                                    st.metric(
                                        item["ativo"],
                                        f"{item['contribuicao']:+.3f}%",
                                        f"Retorno: {item['retorno_mes']:+.2f}%",
                                        delta_color="inverse",
                                    )
                            else:
                                st.caption("Nenhum detrator no período.")

                    # ── Performance vs. benchmarks ────────────────────────────
                    st.divider()
                    st.subheader("Performance vs. benchmarks")

                    col_bench, col_alfa = st.columns(2)

                    with col_bench:
                        st.markdown("**Benchmarks do mês**")
                        if mercado:
                            st.dataframe(
                                pd.DataFrame({
                                    "Indicador": ["CDI", "IPCA", "Selic", "IBOVESPA", "IMA-B"],
                                    "Retorno mês (%)": [
                                        alfas["cdi"],
                                        alfas["ipca"],
                                        alfas["selic"],
                                        alfas["ibov"],
                                        alfas["ima_b"],
                                    ],
                                }),
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "Retorno mês (%)": st.column_config.NumberColumn(format="%.4f%%"),
                                },
                            )
                        else:
                            st.info("Sem dados de benchmarks.")

                    with col_alfa:
                        st.markdown("**Alfas do portfólio**")
                        linhas_alfa = [
                            {"Indicador": "Alfa vs CDI",        "Valor (p.p.)": alfas["alfa_cdi"]},
                            {"Indicador": "Retorno real (IPCA)", "Valor (p.p.)": alfas["retorno_real_vs_ipca"]},
                        ]
                        if alfas["alfa_acoes_vs_ibovespa"] is not None:
                            linhas_alfa.append({
                                "Indicador": "Ações vs IBOVESPA",
                                "Valor (p.p.)": alfas["alfa_acoes_vs_ibovespa"],
                            })
                        st.dataframe(
                            pd.DataFrame(linhas_alfa),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Valor (p.p.)": st.column_config.NumberColumn(format="%+.2f p.p."),
                            },
                        )

                    # ── Recomendação — Rivet ─────────────────────────────────
                    st.divider()
                    st.subheader("Recomendação")

                    rec_key = f"recomendacao_{cliente_id}_{mes_atual}"

                    col_btn_rec, _ = st.columns([2, 8])
                    if col_btn_rec.button(
                        "Gerar recomendação",
                        key=f"btn_rec_{cliente_id}",
                        type="primary",
                        use_container_width=True,
                        disabled=not mes_atual,
                    ):
                        st.session_state[rec_key] = None
                        with st.spinner("Analisando carteira e gerando recomendação..."):
                            try:
                                st.session_state[rec_key] = gerar_recomendacao(cliente_id, mes_atual)
                            except Exception as e:
                                st.session_state[rec_key] = f"__erro__: {e}"

                    recomendacao = st.session_state.get(rec_key)
                    if recomendacao:
                        if recomendacao.startswith("__erro__"):
                            st.error(recomendacao.replace("__erro__: ", ""))
                        else:
                            with st.container(border=True):
                                st.markdown(recomendacao)

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
        INDICES_PCT = {
            "cdi_mensal":              "CDI",
            "ipca_mensal":             "IPCA",
            "selic_mensal":            "Selic",
            "ibovespa_retorno_mensal": "IBOVESPA",
            "ima_b_retorno_mensal":    "IMA-B",
            "pib_crescimento_anual":   "PIB (YoY)",
        }
        INDICES_FX = {
            "usd_brl_fechamento": "USD/BRL",
        }

        df_sorted = df.sort_values("mes").reset_index(drop=True)

        col_esq, col_dir = st.columns([1, 2])

        # ── Esquerda: valor mais recente de cada índice ──────────────────────
        with col_esq:
            ultimo = df_sorted.iloc[-1]
            mes_label = pd.to_datetime(ultimo["mes"] + "-01").strftime("%b/%Y")
            st.caption(f"Último mês disponível: **{mes_label}**")

            for campo, label in INDICES_PCT.items():
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
            for campo, label in INDICES_FX.items():
                val = ultimo.get(campo)
                texto = f"R$ {val:.4f}" if pd.notna(val) else "—"
                st.markdown(
                    f"""
                    <div style="padding:22px 0 14px 0; border-bottom:1px solid #333;">
                        <div style="font-size:22px; color:#aaa; font-weight:500; margin-bottom:4px;">{label}</div>
                        <div style="font-size:84px; font-weight:700; line-height:1.0;">{texto}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # ── Direita: gráficos históricos ──────────────────────────────────────
        with col_dir:
            BG = "#0e1117"

            # Gráfico 1 — Índices em % (CDI, IPCA, Selic, IBOV, IMA-B, PIB)
            df_chart = df_sorted[["mes"] + list(INDICES_PCT.keys())].copy()
            df_chart["mes"] = pd.to_datetime(df_chart["mes"] + "-01")

            CORES_PCT = ["#ffffff", "#7dd3fc", "#86efac", "#fda4af", "#fbbf24", "#c084fc"]

            fig = go.Figure()
            for (campo, label), cor in zip(INDICES_PCT.items(), CORES_PCT):
                serie = df_chart[["mes", campo]].dropna()
                fig.add_trace(go.Scatter(
                    x=serie["mes"], y=serie[campo],
                    name=label, mode="lines",
                    line=dict(width=2.5, color=cor),
                ))

            fig.update_layout(
                height=420,
                margin=dict(t=20, b=20, l=0, r=10),
                plot_bgcolor=BG, paper_bgcolor=BG,
                font=dict(color="#ffffff", size=14),
                legend=dict(orientation="h", y=-0.12, font=dict(size=13, color="#ffffff")),
                xaxis=dict(showgrid=False, tickfont=dict(size=12, color="#aaaaaa"), linecolor="#333"),
                yaxis=dict(ticksuffix="%", autorange=True, showgrid=True,
                           gridcolor="#1f2937", tickfont=dict(size=12, color="#aaaaaa"), linecolor="#333"),
                hovermode="x unified",
                hoverlabel=dict(bgcolor="#1f2937", font_color="#ffffff"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Gráfico 2 — USD/BRL
            df_fx = df_sorted[["mes", "usd_brl_fechamento"]].copy()
            df_fx["mes"] = pd.to_datetime(df_fx["mes"] + "-01")
            df_fx = df_fx.dropna()

            fig_fx = go.Figure()
            fig_fx.add_trace(go.Scatter(
                x=df_fx["mes"], y=df_fx["usd_brl_fechamento"],
                name="USD/BRL", mode="lines",
                line=dict(width=2.5, color="#34d399"),
                fill="tozeroy", fillcolor="rgba(52,211,153,0.08)",
            ))
            fig_fx.update_layout(
                height=280,
                margin=dict(t=10, b=20, l=0, r=10),
                plot_bgcolor=BG, paper_bgcolor=BG,
                font=dict(color="#ffffff", size=14),
                legend=dict(orientation="h", y=-0.18, font=dict(size=13, color="#ffffff")),
                xaxis=dict(showgrid=False, tickfont=dict(size=12, color="#aaaaaa"), linecolor="#333"),
                yaxis=dict(tickprefix="R$ ", autorange=True, showgrid=True,
                           gridcolor="#1f2937", tickfont=dict(size=12, color="#aaaaaa"), linecolor="#333"),
                hovermode="x unified",
                hoverlabel=dict(bgcolor="#1f2937", font_color="#ffffff"),
            )
            st.plotly_chart(fig_fx, use_container_width=True)
