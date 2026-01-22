# blocks/racao.py
# =============================================================================
# BLOCO – MISTURA DA RAÇÃO (SEÇÃO 1)
# =============================================================================

import os
import pandas as pd
import streamlit as st


def render_racao(
    PASTA_DADOS: str,
    bloco_instagram_mistura,
    *,
    arquivo_mistura: str = "mistura_racao.csv",
    tail_n: int = 10,
):
    """
    Renderiza a SEÇÃO 1: Mistura da ração · linha do tempo

    Parâmetros
    ----------
    PASTA_DADOS : str
        Pasta onde ficam os CSV (ex.: "dados")
    bloco_instagram_mistura : callable
        Função já existente no app principal que desenha o card/linha do tempo
        (usa chart_serie_altair + diagnostico_serie internamente).
    arquivo_mistura : str
        Nome do CSV da mistura (default: "mistura_racao.csv")
    tail_n : int
        Quantos registros finais usar (default: 10)
    """

    # Âncora da seção (mantém navegação do app)
    st.markdown("<div id='mistura' style='position: relative; top: -40px;'></div>", unsafe_allow_html=True)
    st.subheader("Mistura da ração · linha do tempo")

    caminho_mistura = os.path.join(PASTA_DADOS, arquivo_mistura)

    if not os.path.exists(caminho_mistura):
        st.warning(
            f"Arquivo `{arquivo_mistura}` não encontrado na pasta de dados. "
            "Crie-o com as colunas: data,%_milho,%_calcario,%_soja,%_nucleo."
        )
        return

    # -------------------------------------------------------------------------
    # 1) Leitura e normalização de colunas (aceita sinônimos)
    #    (leitura robusta: aceita sep=',' ou ';')
    # -------------------------------------------------------------------------
    df_mist = pd.read_csv(caminho_mistura, sep=None, engine="python")
    df_mist.columns = [c.strip() for c in df_mist.columns]

    colunas_alvo_mist = {
        "data": ["data", "Data", "DATA"],
        "milho_pct": [
            "milho_pct", "pct_milho", "%_milho", "Milho", "Milho (%)", "milho (%)"
        ],
        "calcario_pct": [
            "calcario_pct", "pct_calcario", "%_calcario", "Calcário", "Calcario", "Calcário (%)"
        ],
        "farelo_soja_pct": [
            "farelo_soja_pct", "pct_soja", "%_soja", "Farelo de soja", "Farelo de Soja (%)"
        ],
        "nucleo_pct": [
            "nucleo_pct", "pct_nucleo", "%_nucleo", "Núcleo", "Nucleo", "Núcleo (%)"
        ],
    }

    df_norm = pd.DataFrame()
    for destino, candidatos in colunas_alvo_mist.items():
        encontrado = None
        for nome in candidatos:
            if nome in df_mist.columns:
                encontrado = nome
                break

        if encontrado is None:
            st.error(
                f"Não encontrei coluna correspondente a '{destino}'. "
                f"Colunas atuais em {arquivo_mistura}: {list(df_mist.columns)}"
            )
            st.stop()

        df_norm[destino] = df_mist[encontrado]

    df_mist = df_norm

    # -------------------------------------------------------------------------
    # 2) Tipos: números (aceita vírgula) e data
    # -------------------------------------------------------------------------
    for c in ["milho_pct", "farelo_soja_pct", "calcario_pct", "nucleo_pct"]:
        df_mist[c] = (
            df_mist[c]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .astype(float)
        )

    # parse tolerante de data (aceita dd/mm/aaaa e também ISO, se aparecer)
    df_mist["data"] = pd.to_datetime(
        df_mist["data"],
        dayfirst=True,
        errors="coerce",
    )

    if df_mist["data"].isna().any():
        st.error("Existem datas inválidas em mistura_racao.csv.")
        st.stop()

    df_mist = df_mist.sort_values("data")
    df_mist = df_mist.tail(tail_n).copy()

    # -------------------------------------------------------------------------
    # 3) Cards “Instagram”
    # -------------------------------------------------------------------------
    bloco_instagram_mistura(
        df=df_mist,
        col="milho_pct",
        titulo="Milho (%)",
        ref_min=59,
        ref_max=67,
        texto_ref="""
        **Referência teórica:** 62 % (faixa alvo: 59% – 67 %).  
        **Função:** principal fonte de energia da dieta.
        """,
        nome_curto="Milho",
        ylim=(40, 90),
    )

    bloco_instagram_mistura(
        df=df_mist,
        col="farelo_soja_pct",
        titulo="Farelo de soja (%)",
        ref_min=22,
        ref_max=26,
        texto_ref="""
        **Referência teórica:** 24 % (faixa alvo: 22.8% – 25.2%)  
        **Função:** principal fonte de proteína da formulação.
        """,
        nome_curto="Farelo de soja",
        ylim=(0, 40),
    )

    bloco_instagram_mistura(
        df=df_mist,
        col="calcario_pct",
        titulo="Calcário (%)",
        ref_min=9,
        ref_max=11,
        texto_ref="""
        **Referência teórica:** 10 % (faixa alvo: 9.5% – 10.5%)  
        **Função:** oferta de cálcio para qualidade de casca.
        """,
        nome_curto="Calcário",
        ylim=(0, 20),
    )

    bloco_instagram_mistura(
        df=df_mist,
        col="nucleo_pct",
        titulo="Núcleo (%)",
        ref_min=3,
        ref_max=5,
        texto_ref="""
        **Referência teórica:** 4 % (faixa alvo: 3–5 %)  
        **Função:** vitaminas, minerais e aditivos concentrados.
        """,
        nome_curto="Núcleo",
        ylim=None,
    )
