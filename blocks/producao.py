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
import streamlit.components.v1 as components



# =============================================================================
# CONFIG LOCAL — mantém este block autocontido (sem depender de escala global)
# =============================================================================
JANELA_INICIAL_DIAS: int = 7  # mesma ideia do CFG.janela_inicial_dias no bloco temperatura
ALTURA_GRAFICOS: int = 380


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


def _build_x_axis_and_time_scale_like_temperatura(
    df: pd.DataFrame,
    date_col: str,
    *,
    title: str = "Dia",
    janela_dias: int = JANELA_INICIAL_DIAS,
    end_dt_override: Optional[pd.Timestamp] = None,
) -> Tuple[alt.Axis, alt.Scale]:
    """
    Eixo X igual aos outros blocos, mas com opção de "navegação" no celular via end_dt_override.

    Regras:
      - max_end = max(hoje, max_dt_dados)
      - min_end = min_dt_dados (ou hoje se dataset vazio)
      - end_dt:
          * se end_dt_override informado -> clamp entre [min_end, max_end]
          * senão -> max_end
      - start_dt = max(min_dt, end_dt - janela)
      - domain = [start_dt, end_dt]
      - axis %d/%b + meses PT via labelExpr
    """
    axis = _make_x_axis_dia_pt(title)
    today = pd.Timestamp.today().normalize()

    if df.empty or date_col not in df.columns:
        end_dt = today
        start_dt = today
        return axis, alt.Scale(domain=[start_dt, end_dt])

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        max_end = today
        end_dt = end_dt_override.normalize() if isinstance(end_dt_override, pd.Timestamp) else today
        end_dt = min(max_end, max(today - pd.Timedelta(days=3650), end_dt))  # clamp leve
        start_dt = end_dt - pd.Timedelta(days=janela_dias)
        return axis, alt.Scale(domain=[start_dt, end_dt])

    min_dt = dates.min()
    max_dt = dates.max()

    min_dt_norm = min_dt.normalize() if hasattr(min_dt, "normalize") else min_dt
    max_dt_norm = max_dt.normalize() if hasattr(max_dt, "normalize") else max_dt

    max_end = max(today, max_dt_norm)
    min_end = min_dt_norm

    if isinstance(end_dt_override, pd.Timestamp):
        end_dt = end_dt_override.normalize()
        # clamp para não "sumir" fora do histórico
        end_dt = min(max_end, max(min_end, end_dt))
    else:
        end_dt = max_end

    start_dt = max(min_dt_norm, end_dt - pd.Timedelta(days=janela_dias))
    return axis, alt.Scale(domain=[start_dt, end_dt])


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


def render_producao(
    *,
    PASTA_DADOS: str,
    ini,
    fim,
    _build_x_axis_and_scale: Callable,  # mantido por compatibilidade (não usado aqui)
    chart_serie_altair: Callable,       # mantido por compatibilidade (não usado aqui)
):
    """
    Renderiza a SEÇÃO: PRODUÇÃO E PERDAS (USANDO producao_ovos.csv)

    Ajustes desta versão:
      - Controle simples e discreto para "navegar" o eixo X (Data final da janela).
      - Aumenta a altura dos gráficos para 380.
      - Mantém o padrão de meses PT e janela fixa (JANELA_INICIAL_DIAS).
    """
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
    # Força a data de HOJE existir no dataset para permitir domínio até hoje
    # (mas agora a navegação do eixo X fica por conta do slider de data final)
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
    # CONTROLE DISCRETO FIXO NO RODAPÉ (MOBILE-FRIENDLY)
    # =============================================================================
    datas_validas = pd.to_datetime(df_producao_filtrado["data"], errors="coerce").dropna()
    min_dt_global = datas_validas.min().normalize() if not datas_validas.empty else today
    max_dt_global = max(today, datas_validas.max().normalize() if not datas_validas.empty else today)

    key_end = "producao_x_end_dt"
    if key_end not in st.session_state:
        st.session_state[key_end] = max_dt_global

    st.session_state[key_end] = min(max_dt_global, max(min_dt_global, st.session_state[key_end]))

    # 1) Criar “slot” fixo no rodapé
    st.markdown(
        """
        <style>
          /* Barra fixa no rodapé */
          #producao-nav-footer {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 9999;
            padding: 8px 12px;
            background: rgba(15, 15, 15, 0.92);
            border-top: 1px solid rgba(255, 255, 255, 0.12);
            backdrop-filter: blur(6px);
          }

          /* Título discreto */
          #producao-nav-footer .title {
            font-size: 12px;
            opacity: 0.85;
            margin: 0 0 6px 0;
            line-height: 1;
          }

          /* Espaço extra no fim da página para não cobrir o último gráfico */
          .producao-bottom-spacer {
            height: 78px; /* ajuste fino se quiser mais/menos */
          }

          /* Deixa o slider mais “baixo” visualmente */
          #producao-nav-footer [data-baseweb="slider"] {
            margin-top: -6px;
          }
        </style>

        <div id="producao-nav-footer">
          <div class="title">Navegação do eixo X (data final da janela)</div>
          <div id="producao-nav-slot"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2) Renderizar o slider no fluxo normal, mas com um wrapper identificável
    st.markdown('<div id="producao-slider-wrapper"></div>', unsafe_allow_html=True)
    end_date = st.slider(
        "Data final",  # label curto (vai ficar “escondido” pela barra fixa)
        min_value=min_dt_global.date(),
        max_value=max_dt_global.date(),
        value=st.session_state[key_end].date(),
        key="producao_x_end_dt_slider",
        label_visibility="collapsed",
    )
    end_dt_override = pd.Timestamp(end_date).normalize()
    st.session_state[key_end] = end_dt_override

    # 3) Mover o slider para dentro do rodapé fixo via JS
    components.html(
        """
        <script>
          (function() {
            // Procura o slider recém-renderizado (o container do widget)
            // Streamlit usa estrutura interna, então buscamos o primeiro slider do bloco atual.
            const footerSlot = parent.document.querySelector("#producao-nav-slot");
            if (!footerSlot) return;

            // Pega o último slider da página (normalmente é o nosso, por estar logo acima deste script)
            const sliders = parent.document.querySelectorAll('[data-baseweb="slider"]');
            if (!sliders || sliders.length === 0) return;

            const sliderEl = sliders[sliders.length - 1];
            // Sobe para um container “seguro” do widget (evita quebrar o layout)
            const widgetContainer = sliderEl.closest('div[data-testid="stSlider"]') || sliderEl.parentElement;

            // Evita duplicar ao rerun
            if (widgetContainer && !footerSlot.contains(widgetContainer)) {
              footerSlot.appendChild(widgetContainer);
            }
          })();
        </script>
        """,
        height=0,
    )

    # 4) Espaçador no final da seção para o rodapé não cobrir conteúdo
    st.markdown('<div class="producao-bottom-spacer"></div>', unsafe_allow_html=True)


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
    # ESCALA Y GLOBAL (±20%) — considera também a faixa teórica
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
    # 5) GRÁFICO 1: ovos_granja x tempo + FAIXA TEÓRICA 85–95% (dinâmica e verde)
    # =============================================================================
    x_axis_ovos, x_scale_ovos = _build_x_axis_and_time_scale_like_temperatura(
        df_ovos,
        "data",
        title="Dia",
        janela_dias=JANELA_INICIAL_DIAS,
        end_dt_override=end_dt_override,
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
        height=ALTURA_GRAFICOS,
        title="Produção diária de ovos na granja (faixa teórica 85–95% de postura)",
    )

    st.markdown("### Produção diária de ovos – granja")
    st.altair_chart(chart_ovos_granja.interactive(bind_y=False), use_container_width=True)

    # =============================================================================
    # 6) GRÁFICO 2: granja vs escola
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

        x_axis_2, x_scale_2 = _build_x_axis_and_time_scale_like_temperatura(
            df_long,
            "data",
            title="Dia",
            janela_dias=JANELA_INICIAL_DIAS,
            end_dt_override=end_dt_override,
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
        st.altair_chart(
            (chart_prod + pontos_prod).properties(height=ALTURA_GRAFICOS).interactive(bind_y=False),
            use_container_width=True,
        )

    # =============================================================================
    # 7) GRÁFICO 3: perdas (granja → escola)
    # =============================================================================
    df_perdas = df_producao_filtrado[["data", "perda_ovos"]].dropna(subset=["perda_ovos"]).copy()

    if not df_perdas.empty:
        df_perdas = df_perdas.sort_values("data").copy()
        x_axis_3, x_scale_3 = _build_x_axis_and_time_scale_like_temperatura(
            df_perdas,
            "data",
            title="Dia",
            janela_dias=JANELA_INICIAL_DIAS,
            end_dt_override=end_dt_override,
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

        chart_perdas = (barras + rotulos).properties(height=ALTURA_GRAFICOS).interactive(bind_y=False)

        st.markdown("### Perdas no trajeto (granja → escola)")
        st.altair_chart(chart_perdas, use_container_width=True)

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

            x_axis_p, x_scale_p = _build_x_axis_and_time_scale_like_temperatura(
                df_postura,
                "data",
                title="Dia",
                janela_dias=JANELA_INICIAL_DIAS,
                end_dt_override=end_dt_override,
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
                height=ALTURA_GRAFICOS,
                title="Taxa de postura diária (%) — referência teórica 85–95%",
            )

            st.altair_chart(chart_postura.interactive(bind_y=False), use_container_width=True)

    # =============================================================================
    # 8) DIAGNÓSTICO AGREGADO
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
