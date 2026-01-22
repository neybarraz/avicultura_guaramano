import pandas as pd
import altair as alt
import streamlit as st
import streamlit.components.v1 as components

def scroll_to(anchor: str):
    """Rola até o elemento com o id fornecido."""
    components.html(
        f"""
        <script>
        const frameWin = window.parent;
        const frameDoc = frameWin.document;
        const el = frameDoc.getElementById('{anchor}');
        if (el) {{
            el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
        </script>
        """,
        height=0,
    )

def _build_x_axis_and_scale(df_plot):
    """Constrói eixo X padronizado (datas)."""
    hoje = pd.Timestamp.today().normalize()
    dmin = hoje - pd.Timedelta(days=30)
    dmax = hoje

    valores_ticks = []
    dia = hoje
    while dia >= dmin:
        valores_ticks.append(dia)
        dia -= pd.Timedelta(days=7)
    valores_ticks = list(reversed(valores_ticks))

    label_expr = (
        "replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("
        "datum.label,'Jan','Jan'),'Feb','Fev'),'Mar','Mar'),'Apr','Abr'),'May','Mai'),'Jun','Jun'),"
        "'Jul','Jul'),'Aug','Ago'),'Sep','Set'),'Oct','Out'),'Nov','Nov'),'Dec','Dez')"
    )

    x_axis = alt.Axis(title="", format="%d %b", values=valores_ticks, labelExpr=label_expr)
    x_scale = alt.Scale(domain=[dmin, dmax])
    return x_axis, x_scale

def chart_serie_altair(df, col, titulo, ref_min=None, ref_max=None, ylim=None, y_label=None, value_format=".1f", tooltip_label=None):
    if df.empty or col not in df.columns:
        return None
    
    df_plot = df.copy()
    if y_label is None: y_label = "%"
    if tooltip_label is None: tooltip_label = "Valor"

    x_axis, x_scale = _build_x_axis_and_scale(df_plot)
    scale_y = alt.Scale(domain=ylim, nice=False) if ylim else alt.Undefined

    base = alt.Chart(df_plot).encode(x=alt.X("data:T", axis=x_axis, scale=x_scale))
    camadas = []

    if (ref_min is not None) and (ref_max is not None):
        df_plot["ref_min"] = ref_min
        df_plot["ref_max"] = ref_max
        faixa = base.mark_area(opacity=0.15).encode(y=alt.Y("ref_min:Q", scale=scale_y), y2=alt.Y2("ref_max:Q"))
        camadas.append(faixa)

    linha = base.mark_line().encode(y=alt.Y(f"{col}:Q", title=y_label, scale=scale_y))
    camadas.append(linha)

    pontos = base.mark_point(size=60).encode(
        y=alt.Y(f"{col}:Q", scale=scale_y),
        tooltip=[alt.Tooltip("data:T", title="Data"), alt.Tooltip(f"{col}:Q", title=tooltip_label, format=value_format)],
    )
    camadas.append(pontos)

    textos = base.mark_text(dy=-20, fontSize=10, color="white").encode(
        y=alt.Y(f"{col}:Q", scale=scale_y),
        text=alt.Text(f"{col}:Q", format=value_format),
    )
    camadas.append(textos)

    return alt.layer(*camadas).properties(height=250, title=titulo).interactive()

def diagnostico_serie(df, col, ref_min, ref_max, nome):
    if df.empty or col not in df.columns: return f"Diagnóstico para {nome}: série sem dados."
    y = df[col].dropna()
    if y.empty: return f"Diagnóstico para {nome}: série vazia."

    dentro = ((y >= ref_min) & (y <= ref_max)).sum()
    acima = (y > ref_max).sum()
    abaixo = (y < ref_min).sum()
    total = len(y)
    
    media_ultimos = y.tail(2).mean() if len(y) >= 2 else y.mean()
    tendencia = "acima" if media_ultimos > ref_max else ("abaixo" if media_ultimos < ref_min else "dentro")
    
    # Resumo simplificado para o exemplo (pode expandir com o texto completo original)
    status = f"Média recente ({media_ultimos:.1f}) está {tendencia} da faixa."
    return f"Nos últimos {total} registros: {dentro} dentro, {acima} acima, {abaixo} abaixo. {status}"

def diagnostico_consumo(df, col, ref_min, ref_max, nome="Consumo"):
    if df.empty or col not in df.columns: return "Sem dados."
    y = df[col].dropna()
    media = y.tail(2).mean() if len(y) >= 2 else y.mean()
    if media < ref_min:
        return f"Tendência de BAIXO consumo ({media:.1f}). Verifique oferta de ração ou ambiência."
    elif media > ref_max:
        return f"Tendência de ALTO consumo ({media:.1f}). Risco de desperdício."
    return f"Consumo dentro da faixa ({media:.1f}). Manejo adequado."

def bloco_instagram_mistura(df, col, titulo, ref_min, ref_max, texto_ref, nome_curto, ylim=None):
    st.markdown(f"### {titulo}")
    st.markdown(texto_ref)
    chart = chart_serie_altair(df, col, titulo, ref_min, ref_max, ylim, "%", ".1f", f"{nome_curto} (%)")
    if chart: st.altair_chart(chart, use_container_width=True)
    diag = diagnostico_serie(df, col, ref_min, ref_max, nome_curto)
    st.markdown(f"**Diagnóstico ({nome_curto}):** {diag}")
    st.markdown("---")