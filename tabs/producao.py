import importlib
import streamlit as st

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

render_producao = _load_block("blocks.producao", "render_producao")

def render_tab(PASTA_DADOS, ini, fim, _build_x_axis_and_scale, chart_serie_altair):
    st.header("Produção")


    _safe(
        "Produção e perdas",
        render_producao,
        PASTA_DADOS=PASTA_DADOS,
        ini=ini,
        fim=fim,
        _build_x_axis_and_scale=_build_x_axis_and_scale,
        chart_serie_altair=chart_serie_altair,
    )
