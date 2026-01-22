# =============================================================================
# APP.PY — Avicultura (ABAS em módulos: tabs/* + blocks tolerantes a erro)
# - Abas com índices robustos (tabs_map)
# - safe_render: não quebra o app em erro de aba/bloco
#
# LIMPEZA (Alimentação):
# - Aba Alimentação NÃO recebe mais helpers (chart_serie_altair/diagnostico_consumo/bloco_instagram_mistura).
# - Aba Alimentação deve ser AUTÔNOMA (tabs/alimentacao.py lê seu próprio CSV).
#
# ALTERAÇÃO (2026-01-09):
# - Removido o "Filtro de período" da barra lateral.
# - Mantido ini/fim internos como range completo (data_min → data_max),
#   para não quebrar abas que ainda recebem ini/fim.
# =============================================================================

from __future__ import annotations

import os
from glob import glob
from datetime import timedelta
import importlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

# -------------------------------------------------------------------------
# Configuração da página
# -------------------------------------------------------------------------
st.set_page_config(
    page_title="Avicultura - Dashboard automático",
    layout="wide",
)

# =============================================================================
# CONFIG — escalas globais (mesmo padrão do consumo.py)
# =============================================================================
MODULE_VERSION = "app.py GLOBAL-SCALES v2026-01-06"

JANELA_INICIAL_DIAS: int = 7

PCT_CLAMP_MIN: float = 0.0
PCT_CLAMP_MAX: float = 100.0

Y_PAD_LOW: float = 0.80
Y_PAD_HIGH: float = 1.20


# =============================================================================
# Funções de carregamento seguro
# =============================================================================
def load_func(module_path: str, func_name: str):
    try:
        mod = importlib.import_module(module_path)
        fn = getattr(mod, func_name)
        return fn
    except Exception as e:
        def _missing_or_broken(*args, **kwargs):
            raise ImportError(f"Falha ao importar {module_path}.{func_name}: {e}")
        return _missing_or_broken


def safe_render(nome_secao: str, func, **kwargs):
    try:
        func(**kwargs)
    except ImportError as e:
        st.warning(f"🚧 **{nome_secao}** está em construção (módulo ausente ou quebrado).")
        with st.expander("Detalhes técnicos"):
            st.code(str(e))
    except Exception as e:
        st.warning(f"🚧 **{nome_secao}** está em construção (erro interno).")
        with st.expander("Detalhes técnicos"):
            st.exception(e)


# =============================================================================
# Utilitários: Eixo X em PT
# =============================================================================
def _pt_month_abbr_expr() -> str:
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
    return alt.Axis(
        title=title,
        format="%d/%b",
        labelExpr=_pt_month_abbr_expr(),
    )


# =============================================================================
# ESCALAS GLOBAIS — FUNÇÃO ÚNICA
# =============================================================================
@dataclass(frozen=True)
class GlobalScales:
    x_axis: alt.Axis
    x_scale: alt.Scale
    y_scale: alt.Scale


def _global_scales(
    dfs: List[pd.DataFrame],
    date_col: str,
    *,
    y_cols: List[str],
    x_title: str = "Dia",
    janela_dias: int = JANELA_INICIAL_DIAS,
    clamp_y: Optional[Tuple[float, float]] = None,
    pad_low: float = Y_PAD_LOW,
    pad_high: float = Y_PAD_HIGH,
) -> GlobalScales:
    x_axis = _make_x_axis_dia_pt(x_title)

    # X global
    all_dates = []
    for df in dfs:
        if df is None or df.empty or date_col not in df.columns:
            continue
        s = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if not s.empty:
            all_dates.append(s)

    if not all_dates:
        now = pd.Timestamp.today().normalize()
        return GlobalScales(
            x_axis=x_axis,
            x_scale=alt.Scale(domain=[now, now]),
            y_scale=alt.Scale(domain=[0, 1]),
        )

    dates = pd.concat(all_dates)
    min_dt = dates.min()
    max_dt = dates.max()
    start_dt = max(min_dt, max_dt - pd.Timedelta(days=janela_dias))
    x_scale = alt.Scale(domain=[start_dt, max_dt])

    # Y global
    values = []
    for df in dfs:
        if df is None or df.empty:
            continue
        for col in y_cols:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if not s.empty:
                    values.append(s)

    if not values:
        y_min, y_max = 0.0, 1.0
    else:
        v = pd.concat(values)
        y_min = float(v.min())
        y_max = float(v.max())

        if y_max == y_min:
            y_max = y_min + 1.0
        else:
            y_min = y_min * pad_low if y_min >= 0 else y_min * (2 - pad_low)
            y_max = y_max * pad_high if y_max >= 0 else y_max * (2 - pad_high)

        if clamp_y is not None:
            c0, c1 = clamp_y
            y_min = max(y_min, c0)
            y_max = min(y_max, c1)
            if y_max <= y_min:
                y_max = y_min + 1.0

    return GlobalScales(
        x_axis=x_axis,
        x_scale=x_scale,
        y_scale=alt.Scale(domain=[y_min, y_max]),
    )


# -------------------------------------------------------------------------
# Carregamento seguro das ABAS (tabs/*)
# Cada módulo de aba precisa expor: render_tab(...)
# -------------------------------------------------------------------------
tab_visao_geral = load_func("tabs.visao_geral", "render_tab")
tab_ambiente = load_func("tabs.ambiente", "render_tab")
tab_alimentacao = load_func("tabs.alimentacao", "render_tab")  # <- alimentacao.py (autônomo)
tab_producao = load_func("tabs.producao", "render_tab")
tab_qualidade_sanidade = load_func("tabs.qualidade_sanidade", "render_tab")
tab_diagnostico_acoes = load_func("tabs.diagnostico_acoes", "render_tab")
tab_historico_aprendizado = load_func("tabs.historico_aprendizado", "render_tab")

# -------------------------------------------------------------------------
# Título
# -------------------------------------------------------------------------
st.markdown(
    """
    <div style="text-align: center; margin-top: 1rem;">
        <h1 style="margin: 0; line-height: 1.05;">
            Análise Inteligente da Produção de Ovos na Avicultura de Postura
        </h1>
        <p style="font-size: 1rem; opacity: 0.8; margin: 0.35rem 0 0 0; line-height: 1.2;">
            Sistema de monitoramento e apoio à decisão · Escola Estadual Técnica Guaramano
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# PARTE A — LEITURA GLOBAL DOS CSVs (para abas que usam dados_filtrados)
# =============================================================================
PASTA_DADOS = "dados"

if not os.path.isdir(PASTA_DADOS):
    st.error(f"Pasta '{PASTA_DADOS}' não encontrada. Crie a pasta e coloque seus arquivos .csv nela.")
    st.stop()

arquivos_csv = sorted(glob(os.path.join(PASTA_DADOS, "*.csv")))

with st.sidebar:
    st.header("Configurações")
    st.write(f"📂 Pasta de dados: `{PASTA_DADOS}/`")
    st.write(f"📄 Arquivos CSV encontrados: **{len(arquivos_csv)}**")
    if arquivos_csv:
        st.write("Arquivos:")
        for arq in arquivos_csv:
            st.text(f"- {os.path.basename(arq)}")
    else:
        st.warning("Nenhum arquivo CSV encontrado. Adicione pelo menos um arquivo na pasta.")
        st.stop()


def _read_csv_tolerante(path: str) -> Optional[pd.DataFrame]:
    """
    Leitura tolerante: tenta ';' (decimal ',') e depois default.
    Isso reduz erros quando existem CSVs mistos na pasta.
    """
    try:
        # 1) tenta padrão comum BR: sep=';' decimal=','
        df = pd.read_csv(path, sep=";", decimal=",")
        return df
    except Exception:
        pass

    try:
        # 2) tenta default (vírgula)
        df = pd.read_csv(path)
        return df
    except Exception as e:
        st.warning(f"CSV ignorado (erro de leitura): `{os.path.basename(path)}`")
        with st.expander("Detalhes técnicos"):
            st.code(str(e))
        return None


dfs = []
for caminho in arquivos_csv:
    df_tmp = _read_csv_tolerante(caminho)
    if df_tmp is None:
        continue
    df_tmp["__arquivo_origem"] = os.path.basename(caminho)
    dfs.append(df_tmp)

if not dfs:
    st.error("Não foi possível carregar nenhum CSV.")
    st.stop()

dados = pd.concat(dfs, ignore_index=True)

# -------------------------------------------------------------------------
# Pré-processamento global
# -------------------------------------------------------------------------
if "data" not in dados.columns:
    st.error("Coluna obrigatória 'data' não encontrada nos CSV.")
    st.stop()

dados["data"] = pd.to_datetime(
    dados["data"].astype(str).str.strip(),
    format="%d/%m/%Y",
    dayfirst=True,
    errors="coerce",
)
dados = dados.dropna(subset=["data"]).sort_values("data")

colunas_num = [
    "milho_pct",
    "farelo_soja_pct",
    "calcario_pct",
    "nucleo_pct",
    "consumo_g_ave_dia",
    "ovos_granja",
    "ovos_escola",
    "ovos_quebrados",
    "ovos_sem_casca",
    "ovos_deformados",
    "aves_doentes",
]
for col in colunas_num:
    if col in dados.columns:
        dados[col] = pd.to_numeric(dados[col], errors="coerce")

if {"ovos_granja", "ovos_escola"}.issubset(dados.columns):
    dados["perda_ovos"] = dados["ovos_granja"] - dados["ovos_escola"]
else:
    dados["perda_ovos"] = np.nan

if {"ovos_quebrados", "ovos_sem_casca", "ovos_deformados", "ovos_granja"}.issubset(dados.columns):
    dados["ovos_defeituosos"] = (
        dados["ovos_quebrados"] + dados["ovos_sem_casca"] + dados["ovos_deformados"]
    )
    dados["pct_defeituosos"] = 100 * dados["ovos_defeituosos"] / dados["ovos_granja"]
else:
    dados["ovos_defeituosos"] = np.nan
    dados["pct_defeituosos"] = np.nan

# =============================================================================
# PARTE B — (REMOVIDO) FILTRO DE PERÍODO NA BARRA LATERAL
# - Mantém ini/fim internos como range total para não quebrar abas existentes.
# =============================================================================
CONSUMO_MIN = 105.0
CONSUMO_MAX = 115.0

data_min = dados["data"].min().date()
data_max = dados["data"].max().date()

ini = data_min
fim = data_max

dados_filtrados = dados.copy()  # Mantido por compatibilidade futura, caso alguma aba use.

# =============================================================================
# PARTE C — HELPERS GLOBAIS (mantidos para Produção e outras abas)
# =============================================================================
def _build_x_axis_and_scale(df_plot: pd.DataFrame, date_col: str = "data"):
    scales = _global_scales(
        dfs=[df_plot],
        date_col=date_col,
        y_cols=[],
        x_title="Dia",
        janela_dias=JANELA_INICIAL_DIAS,
        clamp_y=None,
    )
    return scales.x_axis, scales.x_scale


def chart_serie_altair(
    df,
    col,
    titulo,
    ref_min=None,
    ref_max=None,
    ylim=None,
    y_label=None,
    value_format=".1f",
    tooltip_label=None,
):
    if df.empty or col not in df.columns or "data" not in df.columns:
        return None

    df_plot = df.copy()

    if y_label is None:
        y_label = ""
    if tooltip_label is None:
        tooltip_label = "Valor"

    is_pct = (y_label.strip() == "%") or col.lower().endswith("_pct") or col.lower().startswith("pct_")
    clamp = (PCT_CLAMP_MIN, PCT_CLAMP_MAX) if is_pct else None

    scales = _global_scales(
        dfs=[df_plot],
        date_col="data",
        y_cols=[col],
        x_title="Dia",
        janela_dias=JANELA_INICIAL_DIAS,
        clamp_y=clamp,
        pad_low=Y_PAD_LOW,
        pad_high=Y_PAD_HIGH,
    )

    scale_y = alt.Scale(domain=ylim) if ylim else scales.y_scale

    base = alt.Chart(df_plot).encode(
        x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
    )

    camadas = []

    if (ref_min is not None) and (ref_max is not None):
        df_plot["ref_min"] = ref_min
        df_plot["ref_max"] = ref_max
        faixa = alt.Chart(df_plot).mark_area(opacity=0.15, color="#54A24B").encode(
            x=alt.X("data:T", axis=scales.x_axis, scale=scales.x_scale),
            y=alt.Y("ref_min:Q", scale=scale_y),
            y2=alt.Y2("ref_max:Q"),
        )
        camadas.append(faixa)

    linha = base.mark_line().encode(
        y=alt.Y(f"{col}:Q", title=y_label, scale=scale_y),
    )
    camadas.append(linha)

    pontos = base.mark_point(size=60).encode(
        y=alt.Y(f"{col}:Q", scale=scale_y),
        tooltip=[
            alt.Tooltip("data:T", title="Dia"),
            alt.Tooltip(f"{col}:Q", title=tooltip_label, format=value_format),
        ],
    )
    camadas.append(pontos)

    textos = base.mark_text(dy=-20, fontSize=10, color="white").encode(
        y=alt.Y(f"{col}:Q", scale=scale_y),
        text=alt.Text(f"{col}:Q", format=value_format),
    )
    camadas.append(textos)

    chart = alt.layer(*camadas).properties(height=250, title=titulo)
    return chart.interactive(bind_y=False)


# =============================================================================
# PARTE D — ABAS (ROBUSTAS)
# =============================================================================
TABS_ENABLED = {
    "Ambiente": True,
    "Alimentação": True,
    "Produção": True,
}

tabs_labels = [nome for nome, on in TABS_ENABLED.items() if on]
tabs_objs = st.tabs(tabs_labels)
tabs_map = dict(zip(tabs_labels, tabs_objs))

if "Ambiente" in tabs_map:
    with tabs_map["Ambiente"]:
        safe_render(
            "Aba Ambiente",
            tab_ambiente,
            PASTA_DADOS=PASTA_DADOS,
            ini=ini,
            fim=fim,
        )

if "Alimentação" in tabs_map:
    with tabs_map["Alimentação"]:
        safe_render("Aba Alimentação", tab_alimentacao, PASTA_DADOS=PASTA_DADOS, ini=ini, fim=fim)


if "Produção" in tabs_map:
    with tabs_map["Produção"]:
        safe_render(
            "Aba Produção",
            tab_producao,
            PASTA_DADOS=PASTA_DADOS,
            ini=ini,
            fim=fim,
            _build_x_axis_and_scale=_build_x_axis_and_scale,
            chart_serie_altair=chart_serie_altair,
        )

st.markdown("---")
