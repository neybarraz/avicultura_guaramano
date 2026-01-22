# =============================================================================
# tabs/alimentacao.py
# MÓDULO 100% INDEPENDENTE
#
# Objetivo:
# - Ler dados/alimetacao.csv (ou alimentacao.csv)
# - Exibir gráficos de Mistura (%) e Consumo (g/ave/dia)
# - Layout: Vertical (um abaixo do outro)
#
# Mudanças (2026-01-06):
# - Domínio do eixo Y controlável por série (Y_DOMAIN_POR_SERIE)
# - Altura do gráfico configurável (ALTURA_GRAFICO)
# - _calculate_scales respeita y_domain explícito (não calcula automático nesse caso)
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st


# =============================================================================
# 1. CONFIGURAÇÕES LOCAIS (Autônomas)
# =============================================================================
MODULE_VERSION = "tabs/alimentacao.py VERTICAL + Y-DOMAINS v2026-01-06"
PASTA_DADOS_LOCAL = "dados"

# Configuração de Janela de Tempo (Zoom inicial)
JANELA_INICIAL_DIAS: int = 7

# Faixas de Referência para Consumo
CONSUMO_MIN_LOCAL: float = 105.0
CONSUMO_MAX_LOCAL: float = 115.0

# Configuração visual (Padding dos eixos Y quando modo automático)
Y_PAD_LOW: float = 0.90
Y_PAD_HIGH: float = 1.10

# Altura padrão dos gráficos
ALTURA_GRAFICO: int = 350

# Domínio do eixo Y por série (controle independente)
# - Use (min, max) para domínio FIXO
# - Use None para domínio AUTOMÁTICO (baseado nos dados + padding)
Y_DOMAIN_POR_SERIE = {
    "%_milho": (50.0, 75.0),
    "%_soja": (10.0, 35.0),
    "%_calcario": (5.0, 15.0),
    "%_nucleo": (0.0, 10.0),
    # Consumo: ajuste como preferir (fixo) ou deixe None (automático)
    "consumo_g_ave_dia": (70.0, 140.0),
}


# =============================================================================
# 2. HELPERS DE VISUALIZAÇÃO (Eixos e Escalas)
# =============================================================================
def _pt_month_abbr_expr() -> str:
    """Retorna expressão Vega para traduzir meses para PT-BR."""
    return (
        "replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("
        "replace(datum.label,"
        "'Jan','JAN'),"
        "'Feb','FEV'),"
        "'Mar','MAR'),"
        "'Apr','ABR'),"
        "'May','MAI'),"
        "'Jun','JUN'),"
        "'Jul','JUL'),"
        "'Aug','AGO'),"
        "'Sep','SET'),"
        "'Oct','OUT'),"
        "'Nov','NOV'),"
        "'Dec','DEZ')"
    )


def _make_x_axis_dia_pt(title: str = "Dia") -> alt.Axis:
    """Cria eixo X formatado."""
    return alt.Axis(title=title, format="%d/%b", labelExpr=_pt_month_abbr_expr())


@dataclass(frozen=True)
class GlobalScales:
    """Armazena configurações de escala para consistência visual."""
    x_axis: alt.Axis
    x_scale: alt.Scale
    y_scale: alt.Scale


def _calculate_scales(
    df: pd.DataFrame,
    date_col: str,
    y_col: str,
    clamp_y: Optional[Tuple[float, float]] = None,
    y_domain: Optional[Tuple[float, float]] = None,
) -> GlobalScales:
    """
    Calcula escalas X e Y baseadas apenas no DataFrame fornecido.

    Prioridade do eixo Y:
    1) y_domain explícito -> usa exatamente (min, max)
    2) caso contrário -> calcula automático a partir dos dados + padding
       e aplica clamp_y se fornecido
    """
    # Eixo X
    x_axis = _make_x_axis_dia_pt("Dia")

    if df.empty or date_col not in df.columns:
        now = pd.Timestamp.today().normalize()
        return GlobalScales(
            x_axis=x_axis,
            x_scale=alt.Scale(domain=[now, now]),
            y_scale=alt.Scale(domain=[0, 1]),
        )

    # Escala de Tempo (Zoom nos últimos dias)
    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        now = pd.Timestamp.today().normalize()
        x_scale = alt.Scale(domain=[now, now])
    else:
        max_dt = dates.max()
        min_dt = dates.min()
        start_dt = max(min_dt, max_dt - pd.Timedelta(days=JANELA_INICIAL_DIAS))
        x_scale = alt.Scale(domain=[start_dt, max_dt])

    # Eixo Y: domínio explícito (controle por série)
    if y_domain is not None:
        y_min, y_max = float(y_domain[0]), float(y_domain[1])
        if y_max <= y_min:
            y_max = y_min + 1.0
        y_scale = alt.Scale(domain=[y_min, y_max])
        return GlobalScales(x_axis=x_axis, x_scale=x_scale, y_scale=y_scale)

    # Eixo Y: automático
    if y_col not in df.columns:
        y_min, y_max = 0.0, 1.0
    else:
        vals = pd.to_numeric(df[y_col], errors="coerce").dropna()
        if vals.empty:
            y_min, y_max = 0.0, 1.0
        else:
            v_min, v_max = float(vals.min()), float(vals.max())

            if v_min == v_max:
                y_min, y_max = v_min - 1.0, v_max + 1.0
            else:
                y_min = v_min * Y_PAD_LOW if v_min >= 0 else v_min * (2 - Y_PAD_LOW)
                y_max = v_max * Y_PAD_HIGH if v_max >= 0 else v_max * (2 - Y_PAD_HIGH)

            # Clamp opcional (ex.: 0-100)
            if clamp_y is not None:
                c_min, c_max = float(clamp_y[0]), float(clamp_y[1])
                y_min = max(y_min, c_min)
                y_max = min(y_max, c_max)
                if y_max <= y_min:
                    y_max = y_min + 1.0

    y_scale = alt.Scale(domain=[y_min, y_max])
    return GlobalScales(x_axis=x_axis, x_scale=x_scale, y_scale=y_scale)


# =============================================================================
# 3. LEITURA E TRATAMENTO DE DADOS
# =============================================================================
def _get_csv_path() -> Optional[str]:
    """Busca o arquivo CSV com tolerância a nomes."""
    candidates = ["alimetacao.csv", "alimentacao.csv"]
    if not os.path.exists(PASTA_DADOS_LOCAL):
        return None

    for filename in candidates:
        full_path = os.path.join(PASTA_DADOS_LOCAL, filename)
        if os.path.exists(full_path):
            return full_path
    return None


def _load_data() -> pd.DataFrame:
    """Lê, limpa e tipa os dados do CSV."""
    path = _get_csv_path()
    if not path:
        st.error(f"Arquivo de alimentação não encontrado na pasta '{PASTA_DADOS_LOCAL}'.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, sep=";", dtype=str, engine="python")
        df.columns = [c.strip() for c in df.columns]

        cols_req = ["data", "consumo_g_ave_dia"]
        if not all(c in df.columns for c in cols_req):
            st.error(f"Colunas obrigatórias faltando no CSV: {cols_req}")
            return pd.DataFrame()

        df["data"] = pd.to_datetime(df["data"].astype(str).str.strip(), dayfirst=True, errors="coerce")
        df = df.dropna(subset=["data"]).sort_values("data")

        cols_num = ["consumo_g_ave_dia", "%_milho", "%_calcario", "%_soja", "%_nucleo"]
        for c in cols_num:
            if c in df.columns:
                s = df[c].astype(str).str.strip().str.replace(",", ".", regex=False)
                df[c] = pd.to_numeric(s, errors="coerce")

        return df

    except Exception as e:
        st.error(f"Erro ao ler CSV de alimentação: {e}")
        return pd.DataFrame()


# =============================================================================
# 4. COMPONENTES DE PLOTAGEM
# =============================================================================
def _plot_timeseries(
    df: pd.DataFrame,
    y_col: str,
    title: str,
    y_title: str,
    ref_band: Optional[Tuple[float, float]] = None,
    clamp_y: Optional[Tuple[float, float]] = None,
    y_domain: Optional[Tuple[float, float]] = None,
    height: int = ALTURA_GRAFICO,
) -> None:
    """Gera um gráfico de linha temporal padrão."""
    if df.empty or y_col not in df.columns:
        st.info(f"Sem dados para gerar gráfico de {title}.")
        return

    df_plot = df.dropna(subset=["data", y_col]).copy()
    if df_plot.empty:
        st.info(f"Sem dados válidos para gerar gráfico de {title}.")
        return

    scales = _calculate_scales(df_plot, "data", y_col, clamp_y=clamp_y, y_domain=y_domain)

    base = alt.Chart(df_plot).encode(
        x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
    )

    layers = []

    # Faixa de referência
    if ref_band is not None:
        r_min, r_max = float(ref_band[0]), float(ref_band[1])
        df_band = df_plot[["data"]].copy()
        df_band["ref_min"] = r_min
        df_band["ref_max"] = r_max

        band = alt.Chart(df_band).mark_area(opacity=0.15, color="#2ecc71").encode(
            x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
            y=alt.Y("ref_min:Q", title=y_title, scale=scales.y_scale),
            y2=alt.Y2("ref_max:Q"),
        )
        layers.append(band)

    # Linha
    line = base.mark_line().encode(
        y=alt.Y(f"{y_col}:Q", title=y_title, scale=scales.y_scale),
        tooltip=[
            alt.Tooltip("data:T", title="Dia", format="%d/%m"),
            alt.Tooltip(f"{y_col}:Q", title=y_title, format=".1f"),
        ],
    )
    layers.append(line)

    # Pontos
    points = base.mark_point(size=60, filled=True).encode(
        y=alt.Y(f"{y_col}:Q", scale=scales.y_scale),
        tooltip=[
            alt.Tooltip("data:T", title="Dia", format="%d/%m"),
            alt.Tooltip(f"{y_col}:Q", title=y_title, format=".1f"),
        ],
    )
    layers.append(points)

    # Labels
    text = base.mark_text(dy=-15, color="white").encode(
        y=alt.Y(f"{y_col}:Q", scale=scales.y_scale),
        text=alt.Text(f"{y_col}:Q", format=".1f"),
    )
    layers.append(text)

    chart = alt.layer(*layers).properties(height=height, title=title)
    st.altair_chart(chart.interactive(bind_y=False), use_container_width=True)


def _diagnostico_texto(df: pd.DataFrame, col: str, ref_min: float, ref_max: float) -> str:
    """Retorna string de diagnóstico simples."""
    valid = df.dropna(subset=[col]).copy()
    if valid.empty:
        return "Sem dados."

    valid = valid.sort_values("data")
    last = float(valid.iloc[-1][col])
    mean = float(valid.tail(7)[col].mean())

    if last < ref_min:
        status = "ABAIXO"
    elif last > ref_max:
        status = "ACIMA"
    else:
        status = "DENTRO"

    return f"**{status}** do ideal ({ref_min}-{ref_max}). Último: {last:.1f} | Média (7d): {mean:.1f}"


# =============================================================================
# 5. ENTRYPOINT PRINCIPAL
# =============================================================================
def render_tab(*args, **kwargs) -> None:
    """
    Função Principal da Aba.
    Aceita *args e **kwargs para compatibilidade com qualquer chamada do app.py,
    mas IGNORA tudo para garantir total independência.
    """
    st.caption(MODULE_VERSION)
    st.title("Alimentação")
    st.markdown("Monitoramento independente da mistura da ração e consumo diário.")

    df = _load_data()
    if df.empty:
        return

    st.markdown("---")

    # 1) Mistura (%)
    st.subheader("Mistura da Ração (%)")

    series_mistura = [
        ("%_milho", "Milho (%)", (55.0, 70.0)),
        ("%_soja", "Soja (%)", (15.0, 30.0)),
        ("%_calcario", "Calcário (%)", (9.5, 10.5)),
        ("%_nucleo", "Núcleo (%)", (3.0, 5.0)),
    ]

    for col_name, titulo, faixa in series_mistura:
        if col_name in df.columns:
            _plot_timeseries(
                df=df,
                y_col=col_name,
                title=titulo,
                y_title="%",
                ref_band=faixa,
                # Se você quiser clamp (além do domínio), use clamp_y=(0,100).
                # Aqui, usamos domínio por série para controle total.
                clamp_y=None,
                y_domain=Y_DOMAIN_POR_SERIE.get(col_name),
                height=ALTURA_GRAFICO,
            )

    st.markdown("---")

    # 2) Consumo (g/ave/dia)
    st.subheader("Consumo Diário")

    if "consumo_g_ave_dia" in df.columns:
        _plot_timeseries(
            df=df,
            y_col="consumo_g_ave_dia",
            title="Consumo (g/ave/dia)",
            y_title="g/ave/dia",
            ref_band=(CONSUMO_MIN_LOCAL, CONSUMO_MAX_LOCAL),
            clamp_y=None,
            y_domain=Y_DOMAIN_POR_SERIE.get("consumo_g_ave_dia"),
            height=ALTURA_GRAFICO,
        )

        diag = _diagnostico_texto(df, "consumo_g_ave_dia", CONSUMO_MIN_LOCAL, CONSUMO_MAX_LOCAL)
        st.info(f"Diagnóstico de Consumo: {diag}")
