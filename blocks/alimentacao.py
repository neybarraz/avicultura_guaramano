# =============================================================================
# blocks/alimentacao.py
# BLOCO INDEPENDENTE (chamado por tabs/alimentacao.py)
#
# Objetivo:
# - Ler dados/alimetacao.csv (ou alimentacao.csv) dentro de PASTA_DADOS
# - Exibir gráficos de Mistura (%) e Consumo (g/ave/dia)
# - Abaixo de cada gráfico: diagnóstico zootécnico (se domain/alimentacao_diagnostico.py existir)
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st


# -----------------------------------------------------------------------------
# Diagnóstico (módulo separado; sem Streamlit)
# -----------------------------------------------------------------------------
try:
    from domain.alimentacao_diagnostico import diagnosticar_serie
except Exception as err:
    diagnosticar_serie = None
    _DIAG_IMPORT_ERROR = err
else:
    _DIAG_IMPORT_ERROR = None


# =============================================================================
# 1) CONFIG LOCAL
# =============================================================================

# Zoom inicial
JANELA_INICIAL_DIAS: int = 7

# Faixas de referência para Consumo
CONSUMO_MIN_LOCAL: float = 105.0
CONSUMO_MAX_LOCAL: float = 115.0

# Padding automático (quando y_domain não for dado)
Y_PAD_LOW: float = 0.90
Y_PAD_HIGH: float = 1.10

ALTURA_GRAFICO: int = 350

Y_DOMAIN_POR_SERIE = {
    "%_milho": (50.0, 75.0),
    "%_soja": (10.0, 35.0),
    "%_calcario": (5.0, 15.0),
    "%_nucleo": (0.0, 10.0),
    "consumo_g_ave_dia": (70.0, 140.0),
}

REF_BAND_COLOR = "#2ecc71"
REF_BAND_OPACITY = 0.18


# =============================================================================
# 2) HELPERS (Eixo PT + Scales)
# =============================================================================
def _pt_month_abbr_expr() -> str:
    return (
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "replace("
        "datum.label,"
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
    return alt.Axis(title=title, format="%d/%b", labelExpr=_pt_month_abbr_expr())


@dataclass(frozen=True)
class GlobalScales:
    x_axis: alt.Axis
    x_scale: alt.Scale
    y_scale: alt.Scale


def _calculate_scales(
    df: pd.DataFrame,
    date_col: str,
    y_col: str,
    *,
    y_domain: Optional[Tuple[float, float]] = None,
) -> GlobalScales:
    x_axis = _make_x_axis_dia_pt("Dia")

    today = pd.Timestamp.today().normalize()

    if df.empty or date_col not in df.columns:
        return GlobalScales(
            x_axis=x_axis,
            x_scale=alt.Scale(domain=[today, today]),
            y_scale=alt.Scale(domain=[0, 1]),
        )

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        end_dt = today
        start_dt = today - pd.Timedelta(days=JANELA_INICIAL_DIAS)
        x_scale = alt.Scale(domain=[start_dt, end_dt])
    else:
        max_dt = dates.max()
        min_dt = dates.min()

        max_dt_norm = max_dt.normalize() if hasattr(max_dt, "normalize") else max_dt
        end_dt = max(today, max_dt_norm)

        start_dt = max(min_dt, end_dt - pd.Timedelta(days=JANELA_INICIAL_DIAS))
        x_scale = alt.Scale(domain=[start_dt, end_dt])

    if y_domain is not None:
        y_min, y_max = float(y_domain[0]), float(y_domain[1])
        if y_max <= y_min:
            y_max = y_min + 1.0
        return GlobalScales(x_axis=x_axis, x_scale=x_scale, y_scale=alt.Scale(domain=[y_min, y_max]))

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

    return GlobalScales(x_axis=x_axis, x_scale=x_scale, y_scale=alt.Scale(domain=[y_min, y_max]))


# =============================================================================
# 3) LEITURA
# =============================================================================
def _get_csv_path(PASTA_DADOS: str) -> Optional[str]:
    candidates = ["alimentacao.csv"]
    if not os.path.exists(PASTA_DADOS):
        return None
    for filename in candidates:
        full_path = os.path.join(PASTA_DADOS, filename)
        if os.path.exists(full_path):
            return full_path
    return None


def _load_data(PASTA_DADOS: str) -> pd.DataFrame:
    """
    Leitura robusta para o formato atual do arquivo:
      data;consumo_g_ave_dia;pct_milho;pct_calcario;pct_soja;pct_nucleo
    - sep=';'
    - aceita vírgula/ponto em números
    - renomeia pct_* -> %_* (para compatibilizar com o restante do bloco)
    """
    path = _get_csv_path(PASTA_DADOS)
    if not path:
        st.error(f"Arquivo de alimentação não encontrado em `{PASTA_DADOS}/` (alimetacao.csv ou alimentacao.csv).")
        return pd.DataFrame()

    try:
        # Formato principal do seu arquivo: separador ';'
        df = pd.read_csv(path, sep=";", engine="python")
        df.columns = [c.strip() for c in df.columns]

        # aceita ambos: pct_* (pipeline) e %_* (padrão antigo do bloco)
        rename_map = {
            "pct_milho": "%_milho",
            "pct_calcario": "%_calcario",
            "pct_soja": "%_soja",
            "pct_nucleo": "%_nucleo",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # obrigatórias
        cols_req = ["data", "consumo_g_ave_dia"]
        if not all(c in df.columns for c in cols_req):
            st.error(
                f"Colunas obrigatórias faltando no CSV: {cols_req}. "
                f"Colunas encontradas: {list(df.columns)}"
            )
            return pd.DataFrame()

        # data dd/mm/yyyy (tolerante)
        df["data"] = pd.to_datetime(df["data"].astype(str).str.strip(), dayfirst=True, errors="coerce")
        df = df.dropna(subset=["data"]).sort_values("data")

        # numéricos (tolerante a ',' ou '.')
        cols_num = ["consumo_g_ave_dia", "%_milho", "%_calcario", "%_soja", "%_nucleo"]
        for c in cols_num:
            if c in df.columns:
                s = df[c].astype(str).str.strip().str.replace(",", ".", regex=False)
                df[c] = pd.to_numeric(s, errors="coerce")

        return df
    except Exception as err:
        st.error(f"Erro ao ler CSV de alimentação: {err}")
        return pd.DataFrame()


# =============================================================================
# 4) PLOT
# =============================================================================
def _plot_timeseries(
    df: pd.DataFrame,
    y_col: str,
    title: str,
    y_title: str,
    *,
    ref_band: Optional[Tuple[float, float]] = None,
    y_domain: Optional[Tuple[float, float]] = None,
    height: int = ALTURA_GRAFICO,
) -> None:
    if df.empty or y_col not in df.columns:
        st.info(f"Sem dados para gerar gráfico de {title}.")
        return

    df_plot = df.dropna(subset=["data", y_col]).copy()
    if df_plot.empty:
        st.info(f"Sem dados válidos para gerar gráfico de {title}.")
        return

    # >>> CORREÇÃO ROBUSTA: força "hoje" a existir no eixo X adicionando linha fantasma
    today = pd.Timestamp.today().normalize()
    df_ghost = pd.DataFrame({"data": [today], y_col: [pd.NA]})
    df_plot = pd.concat([df_plot, df_ghost], ignore_index=True)
    df_plot = df_plot.sort_values("data")
    # <<< fim correção

    scales = _calculate_scales(df_plot, "data", y_col, y_domain=y_domain)

    base = alt.Chart(df_plot).encode(
        x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
    )

    layers = []

    if ref_band is not None:
        r_min, r_max = float(ref_band[0]), float(ref_band[1])
        df_band = df_plot[["data"]].copy()
        df_band["ref_min"] = r_min
        df_band["ref_max"] = r_max

        band = alt.Chart(df_band).mark_area(
            color=REF_BAND_COLOR,
            opacity=REF_BAND_OPACITY,
        ).encode(
            x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
            y=alt.Y("ref_min:Q", title=y_title, scale=scales.y_scale),
            y2=alt.Y2("ref_max:Q"),
        )
        layers.append(band)

    line = base.mark_line().encode(
        y=alt.Y(f"{y_col}:Q", title=y_title, scale=scales.y_scale),
        tooltip=[
            alt.Tooltip("data:T", title="Dia", format="%d/%m"),
            alt.Tooltip(f"{y_col}:Q", title=y_title, format=".1f"),
        ],
    )
    layers.append(line)

    points = base.mark_point(size=60, filled=True).encode(
        y=alt.Y(f"{y_col}:Q", scale=scales.y_scale),
        tooltip=[
            alt.Tooltip("data:T", title="Dia", format="%d/%m"),
            alt.Tooltip(f"{y_col}:Q", title=y_title, format=".1f"),
        ],
    )
    layers.append(points)

    text = base.mark_text(dy=-15, color="white").encode(
        y=alt.Y(f"{y_col}:Q", scale=scales.y_scale),
        text=alt.Text(f"{y_col}:Q", format=".1f"),
    )
    layers.append(text)

    chart = alt.layer(*layers).properties(height=height, title=title)
    st.altair_chart(chart.interactive(bind_y=False), use_container_width=True)


# =============================================================================
# 5) DIAGNÓSTICO (HTML/CSS)
# =============================================================================
def _escape_html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _list_html(items) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_escape_html(x)}</li>" for x in items)
    return f"<ul>{lis}</ul>"


def _render_css_diagnostico() -> None:
    st.markdown(
        """
        <style>
          .diag-box {
            padding: 0.60rem 0.90rem;
            border-radius: 10px;
            margin-top: 0.35rem;
            margin-bottom: 0.90rem;
            background: rgba(255,255,255,0.00);
            border: 1px solid rgba(255,255,255,0.12);
          }
          .diag-ok  { color: #ffffff; }
          .diag-bad { color: #e57373; }
          .diag-box h4 {
            margin: 0 0 0.35rem 0;
            font-size: 1.0rem;
            font-weight: 700;
          }
          .diag-box p { margin: 0.15rem 0; }
          .diag-box ul { margin: 0.25rem 0 0.15rem 1.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_diagnostico_abaixo_do_grafico(
    df: pd.DataFrame,
    *,
    col: str,
    ref_min: float,
    ref_max: float,
    janela_dias: int = 7,
) -> None:
    if diagnosticar_serie is None:
        st.warning("Diagnóstico indisponível: não foi possível importar `domain/alimentacao_diagnostico.py`.")
        if _DIAG_IMPORT_ERROR is not None:
            with st.expander("Detalhes técnicos (import)"):
                st.code(str(_DIAG_IMPORT_ERROR))
        return

    diag = diagnosticar_serie(df, col, ref_min=ref_min, ref_max=ref_max, janela_dias=janela_dias)

    status = str(diag.get("status", "")).upper()
    css_class = "diag-ok" if status == "DENTRO" else "diag-bad"

    resumo = _escape_html(diag.get("resumo_curto", ""))

    aves = _list_html(diag.get("impacts_aves", []))
    prod = _list_html(diag.get("impacts_producao", []))
    qual = _list_html(diag.get("impacts_qualidade", []))
    obs = _list_html(diag.get("observar", []))
    aco = _list_html(diag.get("acoes", []))

    html = f"""
    <div class="diag-box {css_class}">
      <h4>Diagnóstico</h4>
      <p>{resumo}</p>
      {"<p><b>Impacto nas aves</b></p>" + aves if aves else ""}
      {"<p><b>Impacto na produção</b></p>" + prod if prod else ""}
      {"<p><b>Impacto na qualidade do ovo</b></p>" + qual if qual else ""}
      {"<p><b>O que observar</b></p>" + obs if obs else ""}
      {"<p><b>Ações sugeridas</b></p>" + aco if aco else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# 6) FUNÇÃO PÚBLICA DO BLOCO
# =============================================================================
def render_alimentacao(
    *,
    PASTA_DADOS: str,
    ini: Optional[pd.Timestamp] = None,
    fim: Optional[pd.Timestamp] = None,
) -> None:
    _ = (ini, fim)  # compatibilidade (não usado no bloco independente)

    # CSS do diagnóstico (uma vez)
    _render_css_diagnostico()

    df = _load_data(PASTA_DADOS)
    if df.empty:
        return
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
                y_domain=Y_DOMAIN_POR_SERIE.get(col_name),
                height=ALTURA_GRAFICO,
            )
            _render_diagnostico_abaixo_do_grafico(
                df=df,
                col=col_name,
                ref_min=float(faixa[0]),
                ref_max=float(faixa[1]),
                janela_dias=7,
            )
            st.markdown("---")

    st.subheader("Consumo Diário")

    if "consumo_g_ave_dia" in df.columns:
        _plot_timeseries(
            df=df,
            y_col="consumo_g_ave_dia",
            title="Consumo (g/ave/dia)",
            y_title="g/ave/dia",
            ref_band=(CONSUMO_MIN_LOCAL, CONSUMO_MAX_LOCAL),
            y_domain=Y_DOMAIN_POR_SERIE.get("consumo_g_ave_dia"),
            height=ALTURA_GRAFICO,
        )
        _render_diagnostico_abaixo_do_grafico(
            df=df,
            col="consumo_g_ave_dia",
            ref_min=float(CONSUMO_MIN_LOCAL),
            ref_max=float(CONSUMO_MAX_LOCAL),
            janela_dias=7,
        )
