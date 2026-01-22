import numpy as np
import streamlit as st

def render_tab(
    dados_filtrados,
    PASTA_DADOS,
    ini,
    fim,
    CONSUMO_MIN,
    CONSUMO_MAX,
):
    st.header("Visão Geral")
    st.caption("Indicadores-chave do período selecionado.")
    st.markdown(
        "Esta aba é o painel de controle rápido. Sugestões de evolução: semáforos, alertas e um “status do dia”."
    )

    st.markdown("### Resumo do período")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if "consumo_g_ave_dia" in dados_filtrados.columns:
            v = dados_filtrados["consumo_g_ave_dia"].mean()
            if not np.isnan(v):
                st.metric(
                    "Consumo médio (g/ave/dia)",
                    f"{v:.1f}",
                    f"{(v - CONSUMO_MIN):+.1f} vs. mínimo {CONSUMO_MIN:.0f}",
                )
            else:
                st.metric("Consumo médio (g/ave/dia)", "N/A")
        else:
            st.metric("Consumo médio (g/ave/dia)", "N/A")

    with col2:
        if "ovos_granja" in dados_filtrados.columns:
            v = dados_filtrados["ovos_granja"].mean()
            st.metric("Ovos/dia (granja)", f"{v:.0f}" if not np.isnan(v) else "N/A")
        else:
            st.metric("Ovos/dia (granja)", "N/A")

    with col3:
        if "perda_ovos" in dados_filtrados.columns:
            v = dados_filtrados["perda_ovos"].mean()
            st.metric("Perda média (granja→escola)", f"{v:.1f}" if not np.isnan(v) else "N/A")
        else:
            st.metric("Perda média (granja→escola)", "N/A")

    with col4:
        if "pct_defeituosos" in dados_filtrados.columns:
            v = dados_filtrados["pct_defeituosos"].mean()
            st.metric("% defeituosos", f"{v:.1f}%" if not np.isnan(v) else "N/A")
        else:
            st.metric("% defeituosos", "N/A")
