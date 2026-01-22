import importlib
import streamlit as st
import pandas as pd

def _load_block(module_path: str, func_name: str):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)
    except Exception as e:
        def _broken(*args, **kwargs):
            raise ImportError(f"Falha ao importar {module_path}.{func_name}: {e}")
        return _broken

def _safe(nome: str, fn, **kwargs):
    try:
        fn(**kwargs)
    except ImportError as e:
        st.warning(f"🚧 **{nome}** está em construção (módulo ausente ou quebrado).")
        with st.expander("Detalhes técnicos"):
            st.code(str(e))
    except Exception as e:
        st.warning(f"🚧 **{nome}** está em construção (erro interno).")
        with st.expander("Detalhes técnicos"):
            st.exception(e)

render_temperatura = _load_block("blocks.temperatura", "render_temperatura")

def render_tab(PASTA_DADOS, ini, fim):
    st.header("Ambiente")
    # st.caption("Condições ambientais (ex.: temperatura).")

    _safe(
        "Temperatura ambiente",
        render_temperatura,
        PASTA_DADOS=PASTA_DADOS,
        ini=pd.Timestamp(ini),
        fim=pd.Timestamp(fim),
    )
