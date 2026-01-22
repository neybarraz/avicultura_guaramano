import importlib
import streamlit as st
import pandas as pd


# =============================================================================
# Loader genérico de blocos (detecta: módulo ausente / função ausente / erro import)
# =============================================================================
def _load_block(module_path: str, func_name: str):
    try:
        mod = importlib.import_module(module_path)

    except ModuleNotFoundError as err:
        # IMPORTANTE:
        # ModuleNotFoundError pode ocorrer porque:
        #   (a) o módulo pedido não existe (err.name == module_path)
        #   (b) o módulo existe, mas ele tentou importar uma dependência interna que não existe
        #       (err.name != module_path)
        missing_name = getattr(err, "name", None)

        if missing_name == module_path or missing_name == module_path.split(".")[0]:
            # Caso (a): módulo/pacote realmente não existe
            def _missing_module(*args, _err=err, **kwargs):
                raise ImportError(
                    f"MÓDULO NÃO ENCONTRADO: '{module_path}'.\n"
                    f"Verifique se o arquivo existe e se há __init__.py nos diretórios.\n\n"
                    f"Erro original: {_err}"
                )
            return _missing_module

        # Caso (b): dependência interna faltando (módulo existe mas import falhou)
        def _broken_import_dep(*args, _err=err, **kwargs):
            raise ImportError(
                f"FALHA AO IMPORTAR O MÓDULO: '{module_path}'.\n"
                f"O arquivo existe, mas um import interno falhou (dependência ausente).\n\n"
                f"Erro original: {_err}"
            )
        return _broken_import_dep

    except Exception as err:
        # Módulo existe mas falhou ao importar (erro de sintaxe, import interno, etc.)
        def _broken_import(*args, _err=err, **kwargs):
            raise ImportError(
                f"FALHA AO IMPORTAR O MÓDULO: '{module_path}'.\n"
                f"O arquivo existe, mas está com erro ao importar.\n\n"
                f"Erro original: {_err}"
            )
        return _broken_import

    # Importou o módulo. Agora checa se a função existe.
    try:
        fn = getattr(mod, func_name)
        return fn
    except AttributeError as err:
        def _missing_func(*args, _err=err, **kwargs):
            raise ImportError(
                f"FUNÇÃO NÃO ENCONTRADA: '{module_path}.{func_name}'.\n"
                f"O módulo existe, mas não possui a função esperada.\n\n"
                f"Erro original: {_err}"
            )
        return _missing_func


# =============================================================================
# Execução segura (não derruba a aba inteira)
# =============================================================================
def _safe(nome: str, fn, **kwargs):
    try:
        fn(**kwargs)
    except ImportError as err:
        st.error(f"❌ **{nome}** não pôde ser carregado.")
        with st.expander("Detalhes técnicos"):
            st.code(str(err))
    except Exception as err:
        st.error(f"❌ **{nome}** falhou durante a execução.")
        with st.expander("Detalhes técnicos"):
            st.exception(err)


# =============================================================================
# Carregamento dos blocos
# =============================================================================
render_temperatura = _load_block("blocks.temperatura", "render_temperatura")
render_iluminacao = _load_block("blocks.iluminacao", "render_iluminacao")
render_mq135 = _load_block("blocks.mq135", "render_mq135")


# =============================================================================
# Aba Ambiente — ORQUESTRADOR
# =============================================================================
def render_tab(PASTA_DADOS, ini, fim):
    st.header("Ambiente")

    ini = pd.Timestamp(ini)
    fim = pd.Timestamp(fim)

    # (Debug opcional)
    # import os, sys
    # st.write("CWD:", os.getcwd())
    # st.write("sys.path[0:3]:", sys.path[0:3])

    # BLOCO 1 — Temperatura
    _safe(
        "Temperatura",
        render_temperatura,
        PASTA_DADOS=PASTA_DADOS,
        ini=ini,
        fim=fim,
    )

    st.divider()

    # BLOCO 2 — Iluminação
    _safe(
        "Iluminação",
        render_iluminacao,
        PASTA_DADOS=PASTA_DADOS,
        ini=ini,
        fim=fim,
    )

    st.divider()

    # BLOCO 3 — MQ135
    _safe(
        "Qualidade do Ar (MQ135)",
        render_mq135,
        PASTA_DADOS=PASTA_DADOS,
        ini=ini,
        fim=fim,
    )
