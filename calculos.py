"""
Cálculo de rendimento de portfólio.

Cada função corresponde a um módulo de Plano/RendimentoPortfolio.md:

  calcular_retorno_acoes     → Módulo 1 (Ações e FIIs)
  calcular_retorno_fundos    → Módulo 2 (Fundos de Investimento)
  calcular_retorno_rf        → Módulo 3 (Renda Fixa: 3A pós-CDI, 3B pós-Selic, 3C prefixado, 3D IPCA+)
  calcular_retorno_portfolio → Módulo 4 (Retorno total ponderado)
  calcular_alfas             → Módulo 5 (Performance vs. benchmarks)

Convenções:
  - Todos os retornos percentuais estão em % (ex: 8.94 para 8,94%).
  - Nenhuma função importa ou depende do Streamlit.
  - Cada função recebe DataFrames do banco e retorna lista de dicts ou um dict de métricas.
"""

from __future__ import annotations
import pandas as pd


# ── Módulo 1 — Ações e FIIs ───────────────────────────────────────────────────

def calcular_retorno_acoes(
    posicoes: pd.DataFrame,
    precos: pd.DataFrame,
    ativos: pd.DataFrame,
    mes_ref: str,
    mes_ant: str,
) -> list[dict]:
    """
    Módulo 1 — Ações e FIIs (RendimentoPortfolio.md § Módulo 1).

    retorno_mes       = (preco_atual - preco_ant + dividendos) / preco_ant × 100
    valor_posicao     = quantidade × preco_atual
    variacao_rs       = (preco_atual - preco_ant + dividendos) × quantidade
    retorno_acumulado = (preco_atual - preco_medio_compra) / preco_medio_compra × 100

    Retorna uma linha por posição com os campos:
      ativo, tipo, ticker, retorno_mes, variacao_rs, valor_posicao, retorno_acumulado
    """
    resultado: list[dict] = []

    for _, pos in posicoes.iterrows():
        ticker = pos["ticker"]

        info  = ativos[ativos["ticker"] == ticker]
        tipo  = info.iloc[0].get("tipo", "Ação") if not info.empty else "Ação"

        row_atual = precos[(precos["ticker"] == ticker) & (precos["mes"] == mes_ref)]
        row_ant   = precos[(precos["ticker"] == ticker) & (precos["mes"] == mes_ant)]

        if row_atual.empty or row_ant.empty:
            resultado.append({
                "ativo": ticker, "tipo": tipo, "ticker": ticker,
                "retorno_mes": None, "variacao_rs": None,
                "valor_posicao": None, "retorno_acumulado": None,
            })
            continue

        preco_atual  = float(row_atual.iloc[0]["preco_fechamento"])
        preco_ant    = float(row_ant.iloc[0]["preco_fechamento"])
        dividendos   = float(row_atual.iloc[0].get("dividendos_pagos", 0) or 0)
        quantidade   = float(pos["quantidade"])
        preco_medio  = float(pos.get("preco_medio_compra", 0) or 0)

        retorno_mes       = (preco_atual - preco_ant + dividendos) / preco_ant * 100
        variacao_rs       = (preco_atual - preco_ant + dividendos) * quantidade
        valor_posicao     = preco_atual * quantidade
        retorno_acumulado = (
            (preco_atual - preco_medio) / preco_medio * 100
            if preco_medio else None
        )

        resultado.append({
            "ativo": ticker,
            "tipo": tipo,
            "ticker": ticker,
            "retorno_mes": retorno_mes,
            "variacao_rs": variacao_rs,
            "valor_posicao": valor_posicao,
            "retorno_acumulado": retorno_acumulado,
        })

    return resultado


# ── Módulo 2 — Fundos de Investimento ────────────────────────────────────────

def calcular_retorno_fundos(
    posicoes: pd.DataFrame,
    cotas: pd.DataFrame,
    ativos: pd.DataFrame,
    mes_ref: str,
    mes_ant: str,
) -> list[dict]:
    """
    Módulo 2 — Fundos de Investimento (RendimentoPortfolio.md § Módulo 2).

    retorno_mes       = (cota_atual / cota_ant - 1) × 100
    valor_posicao     = numero_cotas × cota_atual   ← não usa valor_liquido externo
    variacao_rs       = numero_cotas × (cota_atual - cota_ant)
    retorno_acumulado = (valor_posicao / valor_aplicado - 1) × 100

    Retorna uma linha por posição com os campos:
      ativo, tipo, cnpj, retorno_mes, variacao_rs, valor_posicao, retorno_acumulado
    """
    resultado: list[dict] = []

    for _, pos in posicoes.iterrows():
        cnpj = pos["cnpj"]

        info = ativos[ativos["cnpj"] == cnpj]
        nome = info.iloc[0]["nome"] if not info.empty else cnpj

        row_atual = cotas[(cotas["cnpj"] == cnpj) & (cotas["mes"] == mes_ref)]
        row_ant   = cotas[(cotas["cnpj"] == cnpj) & (cotas["mes"] == mes_ant)]

        if row_atual.empty or row_ant.empty:
            resultado.append({
                "ativo": nome, "tipo": "Fundo", "cnpj": cnpj,
                "retorno_mes": None, "variacao_rs": None,
                "valor_posicao": None, "retorno_acumulado": None,
            })
            continue

        cota_atual  = float(row_atual.iloc[0]["cota_fechamento"])
        cota_ant    = float(row_ant.iloc[0]["cota_fechamento"])
        num_cotas   = float(pos["numero_cotas"])
        valor_aplic = float(pos.get("valor_aplicado", 0) or 0)

        retorno_mes       = (cota_atual / cota_ant - 1) * 100
        variacao_rs       = num_cotas * (cota_atual - cota_ant)
        valor_posicao     = num_cotas * cota_atual
        retorno_acumulado = (
            (valor_posicao / valor_aplic - 1) * 100
            if valor_aplic else None
        )

        resultado.append({
            "ativo": nome,
            "tipo": "Fundo",
            "cnpj": cnpj,
            "retorno_mes": retorno_mes,
            "variacao_rs": variacao_rs,
            "valor_posicao": valor_posicao,
            "retorno_acumulado": retorno_acumulado,
        })

    return resultado


# ── Módulo 3 — Renda Fixa ─────────────────────────────────────────────────────

def calcular_retorno_rf(
    posicoes: pd.DataFrame,
    ativos: pd.DataFrame,
    mercado: dict,
) -> list[dict]:
    """
    Módulo 3 — Renda Fixa (RendimentoPortfolio.md §§ 3A, 3B, 3C, 3D).

    3A pos_fixado_cdi:   retorno_mes = cdi_mensal   × (taxa / 100)
    3B pos_fixado_selic: retorno_mes = selic_mensal  × (taxa / 100)
    3C prefixado:        retorno_mes = ((1 + taxa/100)^(1/12) - 1) × 100
    3D ipca_mais:        spread_mes  = (1 + taxa/100)^(1/12) - 1
                         retorno_mes = ((1 + ipca_mensal/100) × (1 + spread_mes) - 1) × 100

    valor_posicao = valor_aplicado  (proxy; ver RendimentoPortfolio.md § Módulo 3 nota)
    variacao_rs   = valor_aplicado × retorno_mes / 100

    Retorna uma linha por posição com os campos:
      ativo, tipo, indexacao, isento_ir, retorno_mes, variacao_rs, valor_posicao
    """
    cdi_mensal   = float(mercado.get("cdi_mensal",   0) or 0)
    selic_mensal = float(mercado.get("selic_mensal", 0) or 0)
    ipca_mensal  = float(mercado.get("ipca_mensal",  0) or 0)

    resultado: list[dict] = []

    for _, pos in posicoes.iterrows():
        info      = ativos[ativos["id"] == pos["ativo_id"]]
        nome      = info.iloc[0]["nome"]      if not info.empty else "—"
        indexacao = info.iloc[0]["indexacao"] if not info.empty else ""
        isento_ir = bool(info.iloc[0].get("isento_ir", False)) if not info.empty else False

        taxa        = float(pos.get("taxa_contratada", 0) or 0)
        valor_aplic = float(pos.get("valor_aplicado",  0) or 0)

        retorno_mes: float | None = None

        if not mercado:
            pass
        elif indexacao == "pos_fixado_cdi":
            # 3A — pós-fixado CDI: taxa em %CDI (ex: 110 para 110% CDI)
            retorno_mes = cdi_mensal * (taxa / 100)
        elif indexacao == "pos_fixado_selic":
            # 3B — pós-fixado Selic: taxa em %Selic (ex: 100 para 100% Selic)
            retorno_mes = selic_mensal * (taxa / 100)
        elif indexacao == "prefixado":
            # 3C — prefixado: taxa em % a.a. (ex: 12.5 para 12,5% a.a.)
            retorno_mes = ((1 + taxa / 100) ** (1 / 12) - 1) * 100
        elif indexacao == "ipca_mais":
            # 3D — IPCA+: taxa é o spread anual em % a.a. (ex: 5.45 para 5,45% a.a.)
            spread_mes  = (1 + taxa / 100) ** (1 / 12) - 1
            retorno_mes = ((1 + ipca_mensal / 100) * (1 + spread_mes) - 1) * 100

        variacao_rs   = valor_aplic * retorno_mes / 100 if retorno_mes is not None else None
        valor_posicao = valor_aplic

        resultado.append({
            "ativo": nome,
            "tipo": "Renda Fixa",
            "indexacao": indexacao,
            "isento_ir": isento_ir,
            "retorno_mes": retorno_mes,
            "variacao_rs": variacao_rs,
            "valor_posicao": valor_posicao,
            "retorno_acumulado": None,
        })

    return resultado


# ── Módulo 4 — Retorno total ponderado ───────────────────────────────────────

def calcular_retorno_portfolio(linhas: list[dict]) -> dict:
    """
    Módulo 4 — Retorno total ponderado (RendimentoPortfolio.md § Módulo 4).

    peso_i         = valor_posicao_i / valor_total
    contribuicao_i = peso_i × retorno_mes_i
    retorno_portfolio = Σ contribuicao_i

    Modifica cada dict em `linhas` adicionando os campos:
      peso (0 a 1), contribuicao (em %)

    Retorna um dict com métricas consolidadas:
      valor_total, retorno_portfolio, variacao_total_rs,
      top_contributors (até 3), top_detractors (até 3)
    """
    linhas_com_valor = [l for l in linhas if l.get("valor_posicao") is not None]
    valor_total = sum(l["valor_posicao"] for l in linhas_com_valor)

    retorno_portfolio = 0.0
    variacao_total_rs = 0.0

    for linha in linhas:
        if linha.get("valor_posicao") is not None and valor_total > 0:
            peso         = linha["valor_posicao"] / valor_total
            contribuicao = peso * (linha["retorno_mes"] or 0)
        else:
            peso         = None
            contribuicao = None

        linha["peso"]         = peso
        linha["contribuicao"] = contribuicao

        if contribuicao is not None:
            retorno_portfolio += contribuicao
        if linha.get("variacao_rs") is not None:
            variacao_total_rs += linha["variacao_rs"]

    # Ordenar por contribuição para extrair destaques
    com_contribuicao = sorted(
        [l for l in linhas if l.get("contribuicao") is not None],
        key=lambda l: l["contribuicao"],
        reverse=True,
    )

    top_contributors = com_contribuicao[:3]
    top_detractors   = [l for l in reversed(com_contribuicao) if l["contribuicao"] < 0][:3]

    return {
        "valor_total":        valor_total,
        "retorno_portfolio":  retorno_portfolio,
        "variacao_total_rs":  variacao_total_rs,
        "top_contributors":   top_contributors,
        "top_detractors":     top_detractors,
    }


# ── Módulo 5 — Performance vs. benchmarks ────────────────────────────────────

def calcular_alfas(
    retorno_portfolio: float,
    linhas_acoes: list[dict],
    mercado: dict,
) -> dict:
    """
    Módulo 5 — Performance vs. benchmarks (RendimentoPortfolio.md § Módulo 5).

    alfa_cdi               = retorno_portfolio - cdi_mensal
    retorno_real_vs_ipca   = ((1 + rp/100) / (1 + ipca/100) - 1) × 100
    retorno_classe_acoes   = Σ (peso_na_classe_i × retorno_mes_i)
    alfa_acoes_vs_ibovespa = retorno_classe_acoes - ibovespa_retorno_mensal

    Retorna um dict com:
      alfa_cdi, retorno_real_vs_ipca,
      retorno_classe_acoes, alfa_acoes_vs_ibovespa,
      cdi, ipca, ibov, ima_b  (benchmarks brutos para exibição)
    """
    cdi   = float(mercado.get("cdi_mensal",              0) or 0)
    ipca  = float(mercado.get("ipca_mensal",             0) or 0)
    ibov  = float(mercado.get("ibovespa_retorno_mensal", 0) or 0)
    ima_b = float(mercado.get("ima_b_retorno_mensal",    0) or 0)
    selic = float(mercado.get("selic_mensal",            0) or 0)

    alfa_cdi     = retorno_portfolio - cdi
    retorno_real = ((1 + retorno_portfolio / 100) / (1 + ipca / 100) - 1) * 100

    # Retorno ponderado da classe de ações (§ 5.3)
    acoes_validas = [
        l for l in linhas_acoes
        if l.get("valor_posicao") and l.get("retorno_mes") is not None
    ]
    retorno_classe_acoes   = None
    alfa_acoes_vs_ibovespa = None

    if acoes_validas:
        total_acoes = sum(l["valor_posicao"] for l in acoes_validas)
        retorno_classe_acoes = sum(
            (l["valor_posicao"] / total_acoes) * l["retorno_mes"]
            for l in acoes_validas
        )
        alfa_acoes_vs_ibovespa = retorno_classe_acoes - ibov if ibov else None

    return {
        "alfa_cdi":               alfa_cdi,
        "retorno_real_vs_ipca":   retorno_real,
        "retorno_classe_acoes":   retorno_classe_acoes,
        "alfa_acoes_vs_ibovespa": alfa_acoes_vs_ibovespa,
        "cdi":   cdi,
        "ipca":  ipca,
        "ibov":  ibov,
        "ima_b": ima_b,
        "selic": selic,
    }
