# =============================================================================
# tabs/alimentacao.py
# ORQUESTRADOR DA ABA "Alimentação" (tolerante / não quebra se app.py não passar args)
#
# Requisito:
# - blocks/alimentacao.py
# - def render_alimentacao(PASTA_DADOS: str, ini: Optional[pd.Timestamp], fim: Optional[pd.Timestamp], ...)
# =============================================================================

from __future__ import annotations

import importlib
from typing import Optional

import pandas as pd
import streamlit as st


def _load_block(module_path: str, func_name: str):
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)
    except Exception as err:
        # "Congela" a mensagem aqui para não depender do closure do except
        msg = f"Falha ao importar {module_path}.{func_name}: {err}"

        def _broken(*args, **kwargs):
            raise ImportError(msg)

        return _broken


def _safe(nome: str, fn, **kwargs):
    try:
        fn(**kwargs)
    except ImportError as err:
        st.warning(f"🚧 **{nome}** está em construção (módulo ausente ou quebrado).")
        with st.expander("Detalhes técnicos"):
            st.code(str(err))
    except Exception as err:
        st.warning(f"🚧 **{nome}** está em construção (erro interno).")
        with st.expander("Detalhes técnicos"):
            st.exception(err)


# Ajuste aqui se o nome da função no bloco for outro
render_alimentacao = _load_block("blocks.alimentacao", "render_alimentacao")


def _to_ts(x) -> Optional[pd.Timestamp]:
    if x is None:
        return None
    try:
        return pd.Timestamp(x)
    except Exception:
        return None


def render_tab(*args, **kwargs) -> None:
    """
    Tolerante: funciona tanto se o app.py chamar:
      - render_tab()
      - render_tab(PASTA_DADOS=..., ini=..., fim=...)
      - render_tab(PASTA_DADOS, ini, fim)  (por posição)
    """
    # 1) tenta por posição (se vier)
    PASTA_DADOS = None
    ini = None
    fim = None

    if len(args) >= 1:
        PASTA_DADOS = args[0]
    if len(args) >= 2:
        ini = args[1]
    if len(args) >= 3:
        fim = args[2]

    # 2) sobrescreve por kwargs (se vier)
    PASTA_DADOS = kwargs.get("PASTA_DADOS", PASTA_DADOS) or "dados"
    ini = kwargs.get("ini", ini)
    fim = kwargs.get("fim", fim)

    ini_ts = _to_ts(ini)
    fim_ts = _to_ts(fim)

    st.header("Alimentação")

    _safe(
        "Bloco Alimentação",
        render_alimentacao,
        PASTA_DADOS=PASTA_DADOS,
        ini=ini_ts,
        fim=fim_ts,
    )
