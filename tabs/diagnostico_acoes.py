import streamlit as st

def render_tab():
    st.header("Diagnóstico & Ações")
    st.caption("Interpretação e ações recomendadas.")

    st.warning("🚧 Esta seção está em construção.")
    st.markdown(
        """
        Ideias para evoluir aqui:
        - Regras automáticas (if/then) para alertas
        - Lista de ações sugeridas
        - Registro do que foi feito e por quê
        """
    )
