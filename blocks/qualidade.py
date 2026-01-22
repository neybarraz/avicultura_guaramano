# =============================================================================
# blocks/qualidade.py
# =============================================================================
from __future__ import annotations

from typing import Callable, Optional, List

import numpy as np
import pandas as pd
import streamlit as st


def render_qualidade(
    *,
    dados_filtrados: pd.DataFrame,
    chart_serie_altair: Callable,
    mostrar_tabela: bool = True,
    colunas_tabela: Optional[List[str]] = None,
):
    """
    Renderiza a SEÇÃO: QUALIDADE & SANIDADE (VERTICAL)

    Parâmetros (injeção de dependências):
    - dados_filtrados: DataFrame já filtrado pelo período (do app principal).
    - chart_serie_altair: função do app principal para gráfico padronizado.
    - mostrar_tabela: se True, exibe a tabela detalhada no final.
    - colunas_tabela: lista opcional para controlar quais colunas aparecem na tabela.
      Se None, usa o mesmo conjunto padrão do seu código original (com fallback).
    """

    # =============================================================================
    # ÂNCORA + TÍTULO DA SEÇÃO
    # =============================================================================
    st.markdown("<div id='qualidade' style='position: relative; top: -40px;'></div>", unsafe_allow_html=True)
    st.subheader("Qualidade dos ovos & sanidade · linha do tempo")

    if dados_filtrados is None or dados_filtrados.empty:
        st.info("Sem dados no período selecionado para avaliar qualidade & sanidade.")
        return

    # =============================================================================
    # 1) GRÁFICO: % defeituosos
    # =============================================================================
    if "pct_defeituosos" in dados_filtrados.columns:
        df_qual = dados_filtrados[["data", "pct_defeituosos"]].dropna(subset=["pct_defeituosos"]).copy()

        chart_qual = chart_serie_altair(
            df=df_qual,
            col="pct_defeituosos",
            titulo="Percentual de ovos não conformes (%)",
            ref_min=0,
            ref_max=5,
            ylim=None,
            y_label="% de ovos não conformes",
            value_format=".1f",
            tooltip_label="% não conformes",
        )

        if chart_qual is not None:
            st.altair_chart(chart_qual, use_container_width=True)

        st.markdown(
            """
            **Referência prática:**  
            - Idealmente, o percentual de ovos não conformes deve ser mantido **o mais baixo possível**,  
              tipicamente abaixo de **3–5%**, dependendo do sistema de produção.  
            - Picos de defeitos podem estar associados a problemas de nutrição, sanidade ou manejo.
            """
        )
    else:
        st.info("Coluna `pct_defeituosos` não encontrada nos dados filtrados. Gráfico não exibido.")

    # =============================================================================
    # 2) CARDS: total defeituosos e aves doentes
    # =============================================================================
    col_q1, col_q2 = st.columns(2)

    with col_q1:
        if "ovos_defeituosos" in dados_filtrados.columns:
            total_def = pd.to_numeric(dados_filtrados["ovos_defeituosos"], errors="coerce").sum()
            if not np.isnan(total_def):
                st.metric("Total de ovos não conformes (período)", f"{total_def:.0f}")
            else:
                st.metric("Total de ovos não conformes (período)", "N/A")
        else:
            st.metric("Total de ovos não conformes (período)", "N/A")

    with col_q2:
        if "aves_doentes" in dados_filtrados.columns:
            total_doentes = pd.to_numeric(dados_filtrados["aves_doentes"], errors="coerce").sum()
            if not np.isnan(total_doentes):
                st.metric("Soma de aves doentes observadas", f"{total_doentes:.0f}")
            else:
                st.metric("Soma de aves doentes observadas", "N/A")
        else:
            st.metric("Soma de aves doentes observadas", "N/A")

    # =============================================================================
    # 3) TABELA DETALHADA
    # =============================================================================
    if not mostrar_tabela:
        return

    st.markdown("### Tabela detalhada (dados filtrados)")

    if colunas_tabela is None:
        # Mesmo padrão do seu trecho original:
        colunas_padrao = [
            "data",
            "milho_pct",
            "farelo_soja_pct",
            "calcario_pct",
            "nucleo_pct",
            "consumo_g_ave_dia",
            "ovos_granja",
            "ovos_escola",
            "perda_ovos",
            "ovos_quebrados",
            "ovos_sem_casca",
            "ovos_deformados",
            "ovos_defeituosos",
            "pct_defeituosos",
            "aves_doentes",
            "__arquivo_origem",
        ]

        # Se __arquivo_origem não existir, mostra só o que existir
        colunas_existentes = [c for c in colunas_padrao if c in dados_filtrados.columns]
        # Se estiver vazio por algum motivo, cai para todas
        if not colunas_existentes:
            colunas_existentes = list(dados_filtrados.columns)

        df_show = dados_filtrados[colunas_existentes].copy()
    else:
        # Usuário passou colunas específicas → filtra apenas as que existirem
        colunas_existentes = [c for c in colunas_tabela if c in dados_filtrados.columns]
        df_show = dados_filtrados[colunas_existentes].copy() if colunas_existentes else dados_filtrados.copy()

    st.dataframe(df_show, use_container_width=True)
