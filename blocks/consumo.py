# =============================================================================
# blocks/consumo.py  (AUTÔNOMO + ESCALAS GLOBAIS)
# =============================================================================
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import altair as alt


# =============================================================================
# CONFIG
# =============================================================================
MODULE_VERSION = "consumo.py GLOBAL-SCALES v2026-01-06"

JANELA_INICIAL_DIAS: int = 7

# Clamp padrão para percentuais (evita eixo negativo e evita estourar acima de 100)
PCT_CLAMP_MIN: float = 0.0
PCT_CLAMP_MAX: float = 100.0

# Margem multiplicativa para o domínio Y (estilo producao.py: 0.8x–1.2x)
Y_PAD_LOW: float = 0.90
Y_PAD_HIGH: float = 1.10


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
    """
    FUNÇÃO ÚNICA que produz as escalas globais (X e Y).

    X:
      - considera TODAS as datas disponíveis (em todos os dfs)
      - define domínio inicial como [max(min_dt, max_dt - janela), max_dt]
      - zoom/pan será apenas em X (bind_y=False na chamada do chart)

    Y:
      - calcula min/max global considerando TODAS as colunas listadas em y_cols, em TODOS os dfs
      - aplica padding multiplicativo
      - aplica clamp (ex.: percentuais 0–100) quando fornecido
    """
    x_axis = _make_x_axis_dia_pt(x_title)

    # -------------------------
    # X global
    # -------------------------
    all_dates = []
    for df in dfs:
        if df is None or df.empty or date_col not in df.columns:
            continue
        s = pd.to_datetime(df[date_col], errors="coerce")
        s = s.dropna()
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

    # -------------------------
    # Y global
    # -------------------------
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
        # fallback seguro
        y_min, y_max = 0.0, 1.0
    else:
        v = pd.concat(values)
        y_min = float(v.min())
        y_max = float(v.max())

        # padding
        # se min/max podem ser negativos, padding multiplicativo pode inverter; então tratamos com robustez:
        if y_max == y_min:
            y_max = y_min + 1.0
        else:
            # padding multiplicativo em torno dos extremos
            y_min = y_min * pad_low if y_min >= 0 else y_min * (2 - pad_low)
            y_max = y_max * pad_high if y_max >= 0 else y_max * (2 - pad_high)

        # clamp opcional
        if clamp_y is not None:
            c0, c1 = clamp_y
            y_min = max(y_min, c0)
            y_max = min(y_max, c1)
            if y_max <= y_min:
                y_max = y_min + 1.0

    y_scale = alt.Scale(domain=[y_min, y_max])

    return GlobalScales(x_axis=x_axis, x_scale=x_scale, y_scale=y_scale)


# =============================================================================
# Leitura robusta de CSVs (autônomo)
# =============================================================================
def _read_csv_if_exists(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception:
        return None


def _parse_date(df: pd.DataFrame, date_col: str = "data") -> pd.DataFrame:
    df = df.copy()
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col].astype(str).str.strip(), dayfirst=True, errors="coerce")
    return df


def _coerce_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = (
                df[c]
                .astype(str)
                .str.strip()
                .str.replace(",", ".", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# =============================================================================
# Render genérico de série (linha + pontos + rótulo) usando escalas globais
# =============================================================================
def _render_timeseries(
    df: pd.DataFrame,
    *,
    date_col: str,
    value_col: str,
    title: str,
    y_title: str,
    scales: GlobalScales,
    ref_band: Optional[Tuple[float, float]] = None,
    height: int = 280,
    value_fmt: str = ".1f",
) -> None:
    base = alt.Chart(df).encode(
        x=alt.X(f"{date_col}:T", axis=scales.x_axis, scale=scales.x_scale),
    )

    layers = []

    # faixa de referência (opcional)
    if ref_band is not None:
        r0, r1 = map(float, ref_band)
        faixa = alt.Chart(
            pd.DataFrame({date_col: df[date_col], "ref_min": r0, "ref_max": r1})
        ).mark_area(opacity=0.15).encode(
            x=alt.X(f"{date_col}:T", axis=scales.x_axis, scale=scales.x_scale),
            y=alt.Y("ref_min:Q", title=y_title, scale=scales.y_scale),
            y2=alt.Y2("ref_max:Q"),
        )
        layers.append(faixa)

    linha = base.mark_line().encode(
        y=alt.Y(f"{value_col}:Q", title=y_title, scale=scales.y_scale),
        tooltip=[
            alt.Tooltip(f"{date_col}:T", title="Dia"),
            alt.Tooltip(f"{value_col}:Q", title=y_title, format=value_fmt),
        ],
    )
    pontos = base.mark_point(size=60).encode(
        y=alt.Y(f"{value_col}:Q", scale=scales.y_scale),
        tooltip=[
            alt.Tooltip(f"{date_col}:T", title="Dia"),
            alt.Tooltip(f"{value_col}:Q", title=y_title, format=value_fmt),
        ],
    )
    rotulos = base.mark_text(dy=-20, fontSize=10, color="white").encode(
        y=alt.Y(f"{value_col}:Q", scale=scales.y_scale),
        text=alt.Text(f"{value_col}:Q", format=value_fmt),
    )

    layers.extend([linha, pontos, rotulos])

    chart = alt.layer(*layers).properties(height=height, title=title)

    # CRÍTICO: exploração apenas no X
    st.altair_chart(chart.interactive(bind_y=False), use_container_width=True)


# =============================================================================
# Diagnóstico local (simples e robusto)
# =============================================================================
def _diagnostico_faixa(
    df: pd.DataFrame,
    col: str,
    ref_min: float,
    ref_max: float,
    *,
    label: str,
    janela_dias: int = 7,
) -> str:
    if df.empty or col not in df.columns or "data" not in df.columns:
        return f"{label}: sem dados suficientes."

    dff = df[["data", col]].dropna().copy()
    if dff.empty:
        return f"{label}: sem dados válidos."

    dff = dff.sort_values("data")
    ultimo = float(dff.iloc[-1][col])
    media = float(dff.tail(janela_dias)[col].mean())

    if ultimo < ref_min:
        status = "ABAIXO"
    elif ultimo > ref_max:
        status = "ACIMA"
    else:
        status = "DENTRO"

    return f"{label}: {status} da faixa (último={ultimo:.1f}; média{janela_dias}d={media:.1f}; ref={ref_min:.0f}–{ref_max:.0f})."


# =============================================================================
# ENTRYPOINT
# =============================================================================
def render_consumo(
    PASTA_DADOS: str,
    ini=None,  # compatibilidade — NÃO usado
    fim=None,  # compatibilidade — NÃO usado
    CONSUMO_MIN: float = 105.0,
    CONSUMO_MAX: float = 115.0,
    chart_serie_altair=None,     # compatibilidade — NÃO usado
    diagnostico_consumo=None,    # compatibilidade — NÃO usado
):
    st.caption(MODULE_VERSION)

    # -------------------------------------------------------------------------
    # 1) Ler dados de consumo
    # -------------------------------------------------------------------------
    consumo_path = os.path.join(PASTA_DADOS, "consumo_racao.csv")
    df_consumo = _read_csv_if_exists(consumo_path)

    if df_consumo is not None:
        if not {"data", "consumo_g_ave_dia"}.issubset(df_consumo.columns):
            df_consumo = None
        else:
            df_consumo = _parse_date(df_consumo, "data")
            df_consumo = _coerce_numeric(df_consumo, ["consumo_g_ave_dia"])
            df_consumo = df_consumo.dropna(subset=["data", "consumo_g_ave_dia"]).sort_values("data")

    # -------------------------------------------------------------------------
    # 2) Ler dados percentuais (Calcário/Núcleo etc.)
    #     - o módulo tenta achar um arquivo plausível; você pode padronizar 1 nome no seu projeto.
    # -------------------------------------------------------------------------
    candidatos_pct = [
        "formulacao_racao.csv",
        "composicao_racao.csv",
        "racao_composicao.csv",
        "racao_formula.csv",
    ]
    df_pct = None
    for nome in candidatos_pct:
        p = os.path.join(PASTA_DADOS, nome)
        df_try = _read_csv_if_exists(p)
        if df_try is not None and "data" in df_try.columns:
            df_pct = df_try
            break

    if df_pct is not None:
        df_pct = _parse_date(df_pct, "data")

        # detecta colunas % automaticamente (fallback) e trata vírgula decimal
        # você pode fixar as colunas se preferir.
        pct_cols = [c for c in df_pct.columns if c != "data"]
        df_pct = _coerce_numeric(df_pct, pct_cols)
        df_pct = df_pct.dropna(subset=["data"]).sort_values("data")

    # -------------------------------------------------------------------------
    # 3) Seções Percentuais (Calcário/Núcleo etc.) — TODOS com MESMO X e MESMO Y (%)
    # -------------------------------------------------------------------------
    if df_pct is not None and not df_pct.empty:
        st.markdown("## Formulação / Composição (%)")

        # Lista “prioritária” (se existir no CSV, renderiza)
        # (Mantém seu caso: Calcário e Núcleo)
        series_pct: List[Tuple[str, str, Tuple[float, float]]] = [
            ("calcario_pct", "Calcário (%)", (9.5, 10.5)),
            ("nucleo_pct", "Núcleo (%)", (3.0, 5.0)),
        ]

        # Se seus nomes de coluna forem diferentes, você pode ajustar aqui.
        # Ex.: "calcario" ou "calcario_%". O código abaixo tenta localizar.
        def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
            cols = {c.lower(): c for c in df.columns}
            for cand in candidates:
                if cand.lower() in cols:
                    return cols[cand.lower()]
            return None

        # Descobre colunas presentes para a escala Y global de percentuais
        # (Inclui todas as colunas numéricas do df_pct, exceto data)
        pct_numeric_cols = [c for c in df_pct.columns if c != "data"]

        # Escalas globais (%) — UMA vez só
        scales_pct = _global_scales(
            dfs=[df_pct, df_consumo] if df_consumo is not None else [df_pct],
            date_col="data",
            y_cols=pct_numeric_cols,
            x_title="Dia",
            janela_dias=JANELA_INICIAL_DIAS,
            clamp_y=(PCT_CLAMP_MIN, PCT_CLAMP_MAX),
        )

        # Renderiza apenas as séries relevantes (Calcário, Núcleo)
        for base_col, titulo, faixa in series_pct:
            col_real = _find_col(df_pct, [base_col, base_col.replace("_pct", ""), titulo.split()[0]])
            if col_real is None or col_real not in df_pct.columns:
                continue

            st.markdown(f"### {titulo}")
            st.markdown(
                f"**Referência teórica:** {((faixa[0]+faixa[1])/2):.1f}% (faixa alvo: {faixa[0]:.1f}–{faixa[1]:.1f}%)."
            )
            _render_timeseries(
                df=df_pct.dropna(subset=["data", col_real]),
                date_col="data",
                value_col=col_real,
                title=titulo,
                y_title="%",
                scales=scales_pct,
                ref_band=faixa,
                height=220,
                value_fmt=".1f",
            )


    # -------------------------------------------------------------------------
    # 4) Seção Consumo (g/ave/dia) — X global (mesma janela), Y global do consumo
    # -------------------------------------------------------------------------
    st.markdown("## Consumo de ração (g/ave/dia)")

    if df_consumo is None or df_consumo.empty:
        st.warning(
            "Arquivo `consumo_racao.csv` não encontrado ou inválido. "
            "Esperado: colunas `data,consumo_g_ave_dia`."
        )
        return

    # Escalas globais do consumo — usa a MESMA função
    scales_consumo = _global_scales(
        dfs=[df_consumo, df_pct] if df_pct is not None else [df_consumo],
        date_col="data",
        y_cols=["consumo_g_ave_dia"],
        x_title="Dia",
        janela_dias=JANELA_INICIAL_DIAS,
        clamp_y=None,
    )

    _render_timeseries(
        df=df_consumo,
        date_col="data",
        value_col="consumo_g_ave_dia",
        title=f"Consumo de ração (g/ave/dia) — referência {CONSUMO_MIN:.0f}–{CONSUMO_MAX:.0f}",
        y_title="Consumo (g/ave/dia)",
        scales=scales_consumo,
        ref_band=(float(CONSUMO_MIN), float(CONSUMO_MAX)),
        height=280,
        value_fmt=".1f",
    )

    st.markdown(
        f"**Diagnóstico (Consumo de ração):** "
        f"{_diagnostico_faixa(df_consumo, 'consumo_g_ave_dia', float(CONSUMO_MIN), float(CONSUMO_MAX), label='Consumo', janela_dias=7)}"
    )
 

 