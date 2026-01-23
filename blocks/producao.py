# =============================================================================
# blocks/producao.py
# =============================================================================
from __future__ import annotations

import os
from typing import Optional, Callable, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt


# =============================================================================
# CONFIG LOCAL — mantém este block autocontido (sem depender de escala global)
# =============================================================================
JANELA_INICIAL_DIAS: int = 7   # exibir 7 dias
PASSO_NAVEGACAO_DIAS: int = 7  # andar 7 dias por clique


# =============================================================================
# EIXO X (PT) — mesmo padrão do gráfico de Temperatura Média Diária
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
    return alt.Axis(title=title, format="%d/%b", labelExpr=_pt_month_abbr_expr())


def _safe_num_max(series_list) -> float:
    vals = []
    for s in series_list:
        if s is None:
            continue
        v = pd.to_numeric(s, errors="coerce")
        if v.notna().any():
            vals.append(float(v.max()))
    return float(max(vals)) if vals else 0.0


def _safe_num_min(series_list) -> float:
    vals = []
    for s in series_list:
        if s is None:
            continue
        v = pd.to_numeric(s, errors="coerce")
        if v.notna().any():
            vals.append(float(v.min()))
    return float(min(vals)) if vals else 0.0


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _get_nav_offset_days(state_key: str) -> int:
    k = f"{state_key}__offset_days"
    if k not in st.session_state:
        st.session_state[k] = 0
    return int(st.session_state[k])


def _set_nav_offset_days(state_key: str, value: int) -> None:
    st.session_state[f"{state_key}__offset_days"] = int(value)


def _compute_offset_bounds(
    df: pd.DataFrame,
    date_col: str,
    *,
    window_days: int,
    base_end_dt: pd.Timestamp,
) -> tuple[int, int]:
    if df.empty or date_col not in df.columns:
        return (0, 0)

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        return (0, 0)

    min_dt = dates.min().normalize()
    end_dt_min = min_dt + pd.Timedelta(days=max(0, window_days - 1))

    min_offset = int((end_dt_min - base_end_dt).days)
    max_offset = 0

    if min_offset > 0:
        min_offset = 0

    return (min_offset, max_offset)


def _build_x_axis_and_time_scale_navegavel(
    df: pd.DataFrame,
    date_col: str,
    *,
    title: str = "Dia",
    janela_dias: int = JANELA_INICIAL_DIAS,
    passo_dias: int = PASSO_NAVEGACAO_DIAS,
    state_key: str,
) -> Tuple[alt.Axis, alt.Scale]:
    axis = _make_x_axis_dia_pt(title)
    today = pd.Timestamp.today().normalize()

    if df.empty or date_col not in df.columns:
        return axis, alt.Scale(domain=[today, today])

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    end_base = max(today, dates.max().normalize()) if not dates.empty else today

    min_off, max_off = _compute_offset_bounds(df, date_col, window_days=janela_dias, base_end_dt=end_base)

    off = _get_nav_offset_days(state_key)
    off = _clamp(off, min_off, max_off)
    _set_nav_offset_days(state_key, off)

    end_dt = end_base + pd.Timedelta(days=off)
    start_dt = end_dt - pd.Timedelta(days=max(0, janela_dias - 1))

    return axis, alt.Scale(domain=[start_dt, end_dt])


def _enable_pinch_zoom_x(chart: alt.Chart) -> alt.Chart:
    zoom_x = alt.selection_interval(bind="scales", encodings=["x"])
    add_params = getattr(chart, "add_params", None)
    if callable(add_params):
        return chart.add_params(zoom_x)
    return chart.add_selection(zoom_x)


def _render_chart_com_navegacao_lateral(
    chart: alt.Chart,
    *,
    state_key: str,
    df_ref: pd.DataFrame,
    date_col: str,
    janela_dias: int = JANELA_INICIAL_DIAS,
    passo_dias: int = PASSO_NAVEGACAO_DIAS,
    limitar_largura_px: int | None = 720,
):
    today = pd.Timestamp.today().normalize()

    # CSS: limita largura do bloco + botões pequenos + data SEM QUEBRAR LINHA
    if limitar_largura_px is not None:
        st.markdown(
            f"""
            <style>
              .producao-nav-wrap {{
                max-width: {int(limitar_largura_px)}px;
                margin-left: auto;
                margin-right: auto;
              }}
              .producao-nav-wrap div.stButton > button {{
                padding: 0.25rem 0.6rem;
                min-width: 2.6rem;
              }}
              .producao-nav-date {{
                white-space: nowrap;          /* não quebra linha */
                overflow: hidden;             /* corta o excesso */
                text-overflow: ellipsis;      /* "..." se faltar espaço */
                width: 12.5rem;               /* largura fixa do texto da data */
                margin: 0 auto;               /* centraliza */
                text-align: center;
                opacity: 0.85;
                font-size: 0.9rem;
              }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    # Base do fim do eixo X (max entre hoje e último dado)
    if df_ref.empty or date_col not in df_ref.columns:
        end_base = today
        min_off, max_off = (0, 0)
    else:
        dates = pd.to_datetime(df_ref[date_col], errors="coerce").dropna()
        end_base = max(today, dates.max().normalize()) if not dates.empty else today
        min_off, max_off = _compute_offset_bounds(
            df_ref,
            date_col,
            window_days=janela_dias,
            base_end_dt=end_base,
        )

    # Offset atual (limitado)
    off = _get_nav_offset_days(state_key)
    off = _clamp(off, min_off, max_off)
    _set_nav_offset_days(state_key, off)

    end_dt = end_base + pd.Timedelta(days=off)
    start_dt = end_dt - pd.Timedelta(days=max(0, janela_dias - 1))

    def _fmt_pt(dt: pd.Timestamp) -> str:
        s = dt.strftime("%d/%b")
        return (
            s.replace("Jan", "JAN")
            .replace("Feb", "FEV")
            .replace("Mar", "MAR")
            .replace("Apr", "ABR")
            .replace("May", "MAI")
            .replace("Jun", "JUN")
            .replace("Jul", "JUL")
            .replace("Aug", "AGO")
            .replace("Sep", "SET")
            .replace("Oct", "OUT")
            .replace("Nov", "NOV")
            .replace("Dec", "DEZ")
        )

    if limitar_largura_px is not None:
        st.markdown("<div class='producao-nav-wrap'>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 10, 1], vertical_alignment="center")

    with c1:
        clicked_left = st.button(
            "◀",
            key=f"{state_key}__btn_left",
            help=f"Voltar {passo_dias} dias",
        )

    with c2:
        st.markdown(
            f"<div class='producao-nav-date'>{_fmt_pt(start_dt)} — {_fmt_pt(end_dt)}</div>",
            unsafe_allow_html=True,
        )

    with c3:
        clicked_right = st.button(
            "▶",
            key=f"{state_key}__btn_right",
            help=f"Avançar {passo_dias} dias",
        )

    if clicked_left:
        _set_nav_offset_days(state_key, _clamp(off - passo_dias, min_off, max_off))
        st.rerun()

    if clicked_right:
        _set_nav_offset_days(state_key, _clamp(off + passo_dias, min_off, max_off))
        st.rerun()

    st.altair_chart(_enable_pinch_zoom_x(chart), use_container_width=True)

    if limitar_largura_px is not None:
        st.markdown("</div>", unsafe_allow_html=True)


def render_producao(
    *,
    PASTA_DADOS: str,
    ini,
    fim,
    _build_x_axis_and_scale: Callable,
    chart_serie_altair: Callable,
):
    st.markdown("<div id='producao' style='position: relative; top: -40px;'></div>", unsafe_allow_html=True)

    # =============================================================================
    # 1) LEITURA DO CSV PRINCIPAL
    # =============================================================================
    caminho_producao = os.path.join(PASTA_DADOS, "producao_ovos.csv")

    if not os.path.exists(caminho_producao):
        st.warning(
            "Arquivo `producao_ovos.csv` não encontrado na pasta de dados. "
            "Crie-o com as colunas: data,ovos_granja,ovos_escola."
        )
        return

    try:
        df_producao = pd.read_csv(caminho_producao)
    except Exception as e:
        st.error(f"Erro ao ler `producao_ovos.csv`: {e}")
        return

    df_producao.columns = [c.strip() for c in df_producao.columns]

    colunas_necessarias = {"data", "ovos_granja", "ovos_escola"}
    if not colunas_necessarias.issubset(df_producao.columns):
        st.error(
            "O arquivo `producao_ovos.csv` deve conter as colunas "
            "`data`, `ovos_granja` e `ovos_escola`."
        )
        return

    # =============================================================================
    # 2) PRÉ-PROCESSAMENTO
    # =============================================================================
    df_producao["data"] = pd.to_datetime(
        df_producao["data"].astype(str).str.strip(),
        dayfirst=True,
        errors="coerce",
    )
    df_producao = df_producao.dropna(subset=["data"]).copy()

    for col in ["ovos_granja", "ovos_escola"]:
        df_producao[col] = (
            df_producao[col]
            .astype(str)
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        df_producao[col] = pd.to_numeric(df_producao[col], errors="coerce")

    df_producao["perda_ovos"] = df_producao["ovos_granja"] - df_producao["ovos_escola"]

    # =============================================================================
    # 3) (OPCIONAL) DADOS GERAIS PARA FAIXA TEÓRICA 85–95% (VARIÁVEL COM AVES_ATUAL)
    # =============================================================================
    df_gerais: Optional[pd.DataFrame] = None
    caminho_dados_gerais = os.path.join(PASTA_DADOS, "dados_gerais.csv")

    if os.path.exists(caminho_dados_gerais):
        try:
            df_tmp = pd.read_csv(caminho_dados_gerais)
            df_tmp.columns = [c.strip() for c in df_tmp.columns]

            if "data_ref" in df_tmp.columns:
                df_tmp["data_ref"] = pd.to_datetime(
                    df_tmp["data_ref"].astype(str).str.strip(),
                    format="%d/%m/%Y",
                    dayfirst=True,
                    errors="coerce",
                )
                df_tmp = df_tmp.dropna(subset=["data_ref"]).copy()
            else:
                df_tmp = None

            if df_tmp is not None:
                if "aves_atual" in df_tmp.columns:
                    df_tmp["aves_atual"] = (
                        df_tmp["aves_atual"]
                        .astype(str)
                        .str.strip()
                        .str.replace(",", ".", regex=False)
                    )
                    df_tmp["aves_atual"] = pd.to_numeric(df_tmp["aves_atual"], errors="coerce")
                    df_tmp = df_tmp.dropna(subset=["aves_atual"]).copy()
                else:
                    df_tmp = None

            df_gerais = df_tmp
        except Exception as e:
            st.warning(f"Não foi possível usar `dados_gerais.csv` para estimar a faixa de postura: {e}")
            df_gerais = None

    # =============================================================================
    # 4) SEM FILTRO — usa TODO o histórico do CSV
    # =============================================================================
    df_producao_filtrado = df_producao.copy()

    if df_producao_filtrado.empty:
        st.info("Não há dados em `producao_ovos.csv`.")
        return

    # =============================================================================
    # Força a data de HOJE existir no dataset para o eixo X ir até hoje
    # =============================================================================
    today = pd.Timestamp.today().normalize()
    if not (df_producao_filtrado["data"].dt.normalize() == today).any():
        df_producao_filtrado = pd.concat(
            [
                df_producao_filtrado,
                pd.DataFrame(
                    {
                        "data": [today],
                        "ovos_granja": [np.nan],
                        "ovos_escola": [np.nan],
                        "perda_ovos": [np.nan],
                    }
                ),
            ],
            ignore_index=True,
        ).sort_values("data")

    # =============================================================================
    # 5) Preparação do dataset do Gráfico 1 (com merge e faixa teórica variável)
    # =============================================================================
    df_ovos = df_producao_filtrado[["data", "ovos_granja"]].copy().sort_values("data")

    if df_gerais is not None and {"data_ref", "aves_atual"}.issubset(df_gerais.columns):
        df_ovos = df_ovos.sort_values("data").copy()
        df_ovos["data"] = pd.to_datetime(df_ovos["data"], errors="coerce")

        df_gerais_sorted = df_gerais.sort_values("data_ref")[["data_ref", "aves_atual"]].copy()
        df_gerais_sorted["data_ref"] = pd.to_datetime(df_gerais_sorted["data_ref"], errors="coerce")

        df_gerais_sorted = df_gerais_sorted.dropna(subset=["data_ref"]).drop_duplicates(subset=["data_ref"])

        df_ovos = pd.merge_asof(
            df_ovos,
            df_gerais_sorted,
            left_on="data",
            right_on="data_ref",
            direction="backward",
        )

        df_ovos["ovos_min_teor"] = df_ovos["aves_atual"] * 0.85
        df_ovos["ovos_max_teor"] = df_ovos["aves_atual"] * 0.95
    else:
        df_ovos["data_ref"] = pd.NaT
        df_ovos["aves_atual"] = np.nan
        df_ovos["ovos_min_teor"] = np.nan
        df_ovos["ovos_max_teor"] = np.nan

    # =============================================================================
    # ESCALA Y GLOBAL (±20%) — CONSIDERA TAMBÉM A FAIXA TEÓRICA
    # =============================================================================
    max_prod = _safe_num_max(
        [
            df_producao_filtrado.get("ovos_granja"),
            df_producao_filtrado.get("ovos_escola"),
            df_ovos.get("ovos_max_teor"),
        ]
    )
    min_prod = _safe_num_min(
        [
            df_producao_filtrado.get("ovos_granja"),
            df_producao_filtrado.get("ovos_escola"),
            df_ovos.get("ovos_min_teor"),
        ]
    )

    y_max_global = max_prod * 1.2 if max_prod > 0 else 1.0
    y_min_global = max(0.0, min_prod * 0.8) if min_prod > 0 else 0.0
    if y_max_global == y_min_global:
        y_max_global = y_min_global + 1.0

    y_scale_global = alt.Scale(domain=[y_min_global, y_max_global])

    # =============================================================================
    # 6) GRÁFICO 1: ovos_granja x tempo + FAIXA TEÓRICA 85–95% (dinâmica)
    # =============================================================================
    x_axis_ovos, x_scale_ovos = _build_x_axis_and_time_scale_navegavel(
        df_ovos,
        "data",
        title="Dia",
        janela_dias=JANELA_INICIAL_DIAS,
        passo_dias=PASSO_NAVEGACAO_DIAS,
        state_key="producao__ovos_granja_x",
    )

    base_ovos = alt.Chart(df_ovos).encode(
        x=alt.X("data:T", axis=x_axis_ovos, scale=x_scale_ovos)
    )

    camadas_ovos = []

    if df_ovos["ovos_min_teor"].notna().any() and df_ovos["ovos_max_teor"].notna().any():
        faixa_ovos = base_ovos.mark_area(opacity=0.18, color="#2ecc71").encode(
            y=alt.Y("ovos_min_teor:Q", title="Ovos/dia (granja)", scale=y_scale_global),
            y2=alt.Y2("ovos_max_teor:Q"),
        )
        camadas_ovos.append(faixa_ovos)

    linha_ovos = base_ovos.mark_line().encode(
        y=alt.Y("ovos_granja:Q", title="Ovos/dia (granja)", scale=y_scale_global),
    )
    camadas_ovos.append(linha_ovos)

    pontos_ovos = base_ovos.mark_point(size=60).encode(
        y=alt.Y("ovos_granja:Q", scale=y_scale_global),
        tooltip=[
            alt.Tooltip("data:T", title="Dia"),
            alt.Tooltip("ovos_granja:Q", title="Ovos (granja)", format=".0f"),
            alt.Tooltip("aves_atual:Q", title="Aves atuais", format=".0f"),
            alt.Tooltip("ovos_min_teor:Q", title="Faixa mínima teórica", format=".0f"),
            alt.Tooltip("ovos_max_teor:Q", title="Faixa máxima teórica", format=".0f"),
        ],
    )
    camadas_ovos.append(pontos_ovos)

    textos_ovos = base_ovos.mark_text(dy=-20, fontSize=10, color="white").encode(
        y=alt.Y("ovos_granja:Q", scale=y_scale_global),
        text=alt.Text("ovos_granja:Q", format=".0f"),
    )
    camadas_ovos.append(textos_ovos)

    chart_ovos_granja = alt.layer(*camadas_ovos).properties(
        height=250,
        title="Produção diária de ovos na granja (faixa teórica 85–95% de postura)",
    )

    st.markdown("### Produção diária de ovos – granja")
    _render_chart_com_navegacao_lateral(
        chart_ovos_granja,
        state_key="producao__ovos_granja_x",
        df_ref=df_ovos,
        date_col="data",
    )

    # =============================================================================
    # 7) GRÁFICO 2: granja vs escola
    # =============================================================================
    df_prod = df_producao_filtrado[["data", "ovos_granja", "ovos_escola"]].dropna(
        subset=["ovos_granja", "ovos_escola"]
    ).copy()

    if not df_prod.empty:
        df_long = df_prod.melt(
            id_vars="data",
            value_vars=["ovos_granja", "ovos_escola"],
            var_name="origem",
            value_name="ovos",
        )

        x_axis_2, x_scale_2 = _build_x_axis_and_time_scale_navegavel(
            df_long,
            "data",
            title="Dia",
            janela_dias=JANELA_INICIAL_DIAS,
            passo_dias=PASSO_NAVEGACAO_DIAS,
            state_key="producao__granja_vs_escola_x",
        )

        color_def = alt.Color(
            "origem:N",
            title="Origem",
            scale=alt.Scale(
                domain=["ovos_granja", "ovos_escola"],
                range=["#1f77b4", "#ff7f0e"],
            ),
            legend=alt.Legend(
                title=None,
                orient="top",
                direction="horizontal",
                offset=-10,
                padding=0,
                symbolSize=120,
                labelFontSize=12,
                labelExpr=(
                    "replace(replace(datum.label,"
                    "'ovos_granja','Granja'),"
                    "'ovos_escola','Escola')"
                ),
            ),
        )

        chart_prod = (
            alt.Chart(df_long)
            .mark_line()
            .encode(
                x=alt.X("data:T", axis=x_axis_2, scale=x_scale_2),
                y=alt.Y("ovos:Q", title="Produção de ovos (unid./dia)", scale=y_scale_global),
                color=color_def,
                tooltip=[
                    alt.Tooltip("data:T", title="Dia"),
                    alt.Tooltip("origem:N", title="Origem"),
                    alt.Tooltip("ovos:Q", title="Ovos", format=".0f"),
                ],
            )
        )

        pontos_prod = (
            alt.Chart(df_long)
            .mark_point(size=50)
            .encode(
                x=alt.X("data:T", axis=x_axis_2, scale=x_scale_2),
                y=alt.Y("ovos:Q", title="Produção de ovos (unid./dia)", scale=y_scale_global),
                color=color_def,
                tooltip=[
                    alt.Tooltip("data:T", title="Dia"),
                    alt.Tooltip("origem:N", title="Origem"),
                    alt.Tooltip("ovos:Q", title="Ovos", format=".0f"),
                ],
            )
        )

        st.markdown("### Produção diária de ovos (granja vs. escola)")
        _render_chart_com_navegacao_lateral(
            (chart_prod + pontos_prod).properties(height=300),
            state_key="producao__granja_vs_escola_x",
            df_ref=df_long,
            date_col="data",
        )

    # =============================================================================
    # 8) GRÁFICO 3: perdas (granja → escola)
    # =============================================================================
    df_perdas = df_producao_filtrado[["data", "perda_ovos"]].dropna(subset=["perda_ovos"]).copy()

    if not df_perdas.empty:
        df_perdas = df_perdas.sort_values("data").copy()

        x_axis_3, x_scale_3 = _build_x_axis_and_time_scale_navegavel(
            df_perdas,
            "data",
            title="Dia",
            janela_dias=JANELA_INICIAL_DIAS,
            passo_dias=PASSO_NAVEGACAO_DIAS,
            state_key="producao__perdas_x",
        )

        max_perdas = pd.to_numeric(df_perdas["perda_ovos"], errors="coerce").max()
        min_perdas = pd.to_numeric(df_perdas["perda_ovos"], errors="coerce").min()
        max_perdas = 0.0 if pd.isna(max_perdas) else float(max_perdas)
        min_perdas = 0.0 if pd.isna(min_perdas) else float(min_perdas)

        y_max_perdas = max_perdas * 1.2
        y_min_perdas = max(0.0, min_perdas * 0.8)
        if y_max_perdas == y_min_perdas:
            y_max_perdas = y_min_perdas + 1.0

        y_scale_perdas = alt.Scale(domain=[y_min_perdas, y_max_perdas])

        base_perdas = alt.Chart(df_perdas).encode(
            x=alt.X("data:T", axis=x_axis_3, scale=x_scale_3),
            tooltip=[
                alt.Tooltip("data:T", title="Dia"),
                alt.Tooltip("perda_ovos:Q", title="Perdas (ovos)", format=".0f"),
            ],
        )

        barras = base_perdas.mark_bar(color="#d62728").encode(
            y=alt.Y("perda_ovos:Q", title="Perdas (ovos)", scale=y_scale_perdas),
        )

        rotulos = base_perdas.mark_text(dy=-10, fontSize=10, color="white").encode(
            y=alt.Y("perda_ovos:Q", scale=y_scale_perdas),
            text=alt.Text("perda_ovos:Q", format=".0f"),
        )

        chart_perdas = (barras + rotulos).properties(height=260)

        st.markdown("### Perdas no trajeto (granja → escola)")
        _render_chart_com_navegacao_lateral(
            chart_perdas,
            state_key="producao__perdas_x",
            df_ref=df_perdas,
            date_col="data",
        )

    # =============================================================================
    # 9) GRÁFICO: TAXA DE POSTURA (%)
    # =============================================================================
    st.markdown("### Taxa de postura diária (%)")

    if df_gerais is None or "aves_atual" not in df_ovos.columns:
        st.info(
            "Taxa de postura não calculada: é necessário `dados_gerais.csv` "
            "com a coluna `aves_atual` para cada data."
        )
    else:
        df_postura = df_ovos.dropna(subset=["ovos_granja", "aves_atual"]).copy()

        if df_postura.empty:
            st.info("Não há dados suficientes para calcular a taxa de postura.")
        else:
            df_postura = df_postura.sort_values("data").copy()
            df_postura["postura_pct"] = 100.0 * df_postura["ovos_granja"] / df_postura["aves_atual"]

            max_postura = float(pd.to_numeric(df_postura["postura_pct"], errors="coerce").max())
            min_postura = float(pd.to_numeric(df_postura["postura_pct"], errors="coerce").min())
            max_postura = 0.0 if pd.isna(max_postura) else max_postura
            min_postura = 0.0 if pd.isna(min_postura) else min_postura

            y_max_postura = max_postura * 1.2
            y_min_postura = max(0.0, min_postura * 0.8)
            if y_max_postura == y_min_postura:
                y_max_postura = y_min_postura + 1.0

            y_scale_postura = alt.Scale(domain=[y_min_postura, y_max_postura])

            x_axis_p, x_scale_p = _build_x_axis_and_time_scale_navegavel(
                df_postura,
                "data",
                title="Dia",
                janela_dias=JANELA_INICIAL_DIAS,
                passo_dias=PASSO_NAVEGACAO_DIAS,
                state_key="producao__postura_x",
            )

            base_postura = alt.Chart(df_postura).encode(
                x=alt.X("data:T", axis=x_axis_p, scale=x_scale_p)
            )

            camadas_postura = []

            df_faixa = pd.DataFrame(
                {"data": df_postura["data"], "postura_min": 85.0, "postura_max": 95.0}
            )

            faixa_postura = alt.Chart(df_faixa).mark_area(opacity=0.18, color="#2ecc71").encode(
                x=alt.X("data:T", axis=x_axis_p, scale=x_scale_p),
                y=alt.Y("postura_min:Q", title="Postura (%)", scale=y_scale_postura),
                y2=alt.Y2("postura_max:Q"),
            )
            camadas_postura.append(faixa_postura)

            linha_postura = base_postura.mark_line().encode(
                y=alt.Y("postura_pct:Q", title="Postura (%)", scale=y_scale_postura),
            )
            camadas_postura.append(linha_postura)

            pontos_postura = base_postura.mark_point(size=60).encode(
                y=alt.Y("postura_pct:Q", scale=y_scale_postura),
                tooltip=[
                    alt.Tooltip("data:T", title="Dia"),
                    alt.Tooltip("ovos_granja:Q", title="Ovos (granja)", format=".0f"),
                    alt.Tooltip("aves_atual:Q", title="Aves atuais", format=".0f"),
                    alt.Tooltip("postura_pct:Q", title="Postura (%)", format=".1f"),
                ],
            )
            camadas_postura.append(pontos_postura)

            textos_postura = base_postura.mark_text(dy=-20, fontSize=10, color="white").encode(
                y=alt.Y("postura_pct:Q", scale=y_scale_postura),
                text=alt.Text("postura_pct:Q", format=".1f"),
            )
            camadas_postura.append(textos_postura)

            chart_postura = alt.layer(*camadas_postura).properties(
                height=260,
                title="Taxa de postura diária (%) — referência teórica 85–95%",
            )

            _render_chart_com_navegacao_lateral(
                chart_postura,
                state_key="producao__postura_x",
                df_ref=df_postura,
                date_col="data",
            )

    # =============================================================================
    # 10) DIAGNÓSTICO AGREGADO
    # =============================================================================
    total_granja = float(pd.to_numeric(df_producao_filtrado["ovos_granja"], errors="coerce").sum())
    total_escola = float(pd.to_numeric(df_producao_filtrado["ovos_escola"], errors="coerce").sum())
    total_perdas = float(pd.to_numeric(df_producao_filtrado["perda_ovos"], errors="coerce").sum())

    st.markdown(
        f"""
        **Diagnóstico de produção e perdas (período filtrado):**  

        - Total produzido na granja: **{total_granja:.0f} ovos**  
        - Total registrado na escola: **{total_escola:.0f} ovos**  
        - Diferença absoluta (perdas acumuladas): **{total_perdas:.0f} ovos**  

        Se a diferença for recorrente e significativa, vale investigar:  
        - acondicionamento das bandejas e proteção durante o transporte;  
        - conferência de contagem na saída da granja e na chegada à escola;  
        - registro diário em planilhas para rastrear dias mais críticos.
        """
    )
