# =============================================================================
# blocks/iluminacao.py
# Iluminação (lux) — Série diária + Perfil horário (últimos 3 dias) + Diagnóstico
# Padrão: MQ135 (bloco independente)
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st


# -----------------------------------------------------------------------------
# Diagnóstico (módulo separado; sem Streamlit) — padrão MQ135
# -----------------------------------------------------------------------------
try:
    from domain.iluminacao_diagnostico import diagnosticar_iluminacao_perfil_horario
except Exception as _err:
    diagnosticar_iluminacao_perfil_horario = None
    _DIAG_IMPORT_ERROR = _err
else:
    _DIAG_IMPORT_ERROR = None


# =============================================================================
# 1) CONFIG — PONTO ÚNICO PARA AJUSTES RÁPIDOS (ILUMINAÇÃO)
# =============================================================================
@dataclass(frozen=True)
class IluminacaoConfig:
    janela_inicial_dias: int = 7

    # Aparência
    cor_faixa_ref: str = "#2ecc71"

    # Referências (lux)
    illum_dark_max: float = 5.0      # acima disso já não é “escuro efetivo”
    illum_prod_min: float = 10.0     # faixa de produção (mín)
    illum_prod_max: float = 20.0     # faixa de produção (máx)
    illum_target: float = 15.0       # alvo central

    # Horas padrão
    # - Escuro: madrugada + fim de noite (ajuste conforme seu programa)
    dark_hours: Tuple[int, ...] = (1, 2, 3, 4, 5, 22, 23, 24)
    # - Produção: “janela produtiva”
    prod_hours: Tuple[int, ...] = (7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)


CFG = IluminacaoConfig()
ALTURA_GRAFICO: int = 300


# =============================================================================
# 2) HELPERS — EIXO PT + SCALES
# =============================================================================
def pt_month_abbr_expr() -> str:
    return (
        "replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("
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


def make_x_axis_dia_pt(title: str = "Dia") -> alt.Axis:
    return alt.Axis(title=title, format="%d/%b", labelExpr=pt_month_abbr_expr())


@dataclass(frozen=True)
class GlobalScales:
    x_axis: alt.Axis
    x_scale: alt.Scale


def _calculate_x_zoom(df: pd.DataFrame, date_col: str, janela_dias: int) -> GlobalScales:
    """
    Ajustado para ficar igual aos outros blocos:
    - O eixo X SEMPRE termina em HOJE (ou em uma data futura se existir dado futuro)
    - start = max(min_dt, end_dt - janela)
    - domain = [start, end]
    """
    x_axis = make_x_axis_dia_pt("Dia")
    today = pd.Timestamp.today().normalize()

    if df.empty or date_col not in df.columns:
        return GlobalScales(x_axis=x_axis, x_scale=alt.Scale(domain=[today, today]))

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        return GlobalScales(x_axis=x_axis, x_scale=alt.Scale(domain=[today, today]))

    max_dt = dates.max()
    min_dt = dates.min()

    max_dt_norm = max_dt.normalize() if hasattr(max_dt, "normalize") else max_dt
    end_dt = max(today, max_dt_norm)

    start_dt = max(min_dt, end_dt - pd.Timedelta(days=int(janela_dias)))
    return GlobalScales(x_axis=x_axis, x_scale=alt.Scale(domain=[start_dt, end_dt]))


def _auto_domain(series: pd.Series, pad_ratio: float = 0.10) -> Tuple[float, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return 0.0, 1.0
    vmin = float(s.min())
    vmax = float(s.max())
    if vmin == vmax:
        pad = abs(vmin) * pad_ratio if vmin != 0 else 1.0
        return vmin - pad, vmax + pad
    pad = (vmax - vmin) * pad_ratio
    return vmin - pad, vmax + pad


# =============================================================================
# 3) DIAGNÓSTICO — HTML/CSS (padrão MQ135)
# =============================================================================
def _escape_html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _list_html(items) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_escape_html(x)}</li>" for x in items)
    return f"<ul>{lis}</ul>"


def _render_css_diagnostico() -> None:
    st.markdown(
        """
        <style>
          .diag-box {
            padding: 0.60rem 0.90rem;
            border-radius: 10px;
            margin-top: 0.35rem;
            margin-bottom: 0.90rem;
            background: rgba(255,255,255,0.00);
            border: 1px solid rgba(255,255,255,0.12);
          }
          .diag-ok  { color: #ffffff; }
          .diag-bad { color: #e57373; }
          .diag-box h4 {
            margin: 0 0 0.35rem 0;
            font-size: 1.0rem;
            font-weight: 700;
          }
          .diag-box p { margin: 0.15rem 0; }
          .diag-box ul { margin: 0.25rem 0 0.15rem 1.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_diagnostico_box(diag: Dict) -> None:
    status = str(diag.get("status", "")).upper()
    css_class = "diag-ok" if status == "DENTRO" else "diag-bad"

    resumo = _escape_html(diag.get("resumo_curto", ""))

    aves = _list_html(diag.get("impacts_aves", []))
    prod = _list_html(diag.get("impacts_producao", []))
    qual = _list_html(diag.get("impacts_qualidade", []))
    obs = _list_html(diag.get("observar", []))
    aco = _list_html(diag.get("acoes", []))

    html = f"""
    <div class="diag-box {css_class}">
      <h4>Diagnóstico</h4>
      <p>{resumo}</p>
      {"<p><b>Impacto nas aves</b></p>" + aves if aves else ""}
      {"<p><b>Impacto na produção</b></p>" + prod if prod else ""}
      {"<p><b>Impacto na qualidade do ovo</b></p>" + qual if qual else ""}
      {"<p><b>O que observar</b></p>" + obs if obs else ""}
      {"<p><b>Ações sugeridas</b></p>" + aco if aco else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_diagnostico_iluminacao(df_profile: pd.DataFrame, cfg: IluminacaoConfig) -> None:
    if diagnosticar_iluminacao_perfil_horario is None:
        st.warning("Diagnóstico indisponível: não foi possível importar `domain/iluminacao_diagnostico.py`.")
        if _DIAG_IMPORT_ERROR is not None:
            with st.expander("Detalhes técnicos (import)"):
                st.code(str(_DIAG_IMPORT_ERROR))
        return

    diag = diagnosticar_iluminacao_perfil_horario(
        df_profile=df_profile,
        dark_max=float(cfg.illum_dark_max),
        prod_min=float(cfg.illum_prod_min),
        prod_max=float(cfg.illum_prod_max),
        target=float(cfg.illum_target),
        dark_hours=tuple(cfg.dark_hours),
        prod_hours=tuple(cfg.prod_hours),
    )
    _render_diagnostico_box(diag)


# =============================================================================
# 4) IO + NORMALIZAÇÃO (ILUMINAÇÃO)
# =============================================================================
def _pick_first_existing(candidates: List[str], cols: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in cols}
    for cand in candidates:
        key = cand.lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def _read_and_normalize_illum_csv(csv_path: str) -> pd.DataFrame:
    """
    Normaliza para:
      - dt    : datetime
      - illum : float (lux)
    """
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    datetime_candidates = [
        "datetime_local",
        "timestamp",
        "datetime",
        "datahora",
        "data_hora",
        "data_horario",
        "date_time",
        "time",
    ]
    illum_candidates = [
        "illuminance_lx",
        "iluminancia_lx",
        "iluminacao_lx",
        "illum_lx",
        "lux",
        "illuminance",
        "iluminancia",
        "iluminacao",
    ]

    col_dt = _pick_first_existing(datetime_candidates, df.columns.tolist())
    col_illum = _pick_first_existing(illum_candidates, df.columns.tolist())

    if col_dt is None or col_illum is None:
        st.error(
            "Formato inesperado do arquivo `estacao_meteorologica.csv` para ILUMINAÇÃO.\n\n"
            f"Colunas encontradas: {list(df.columns)}\n\n"
            "Preciso de:\n"
            f"- Data/hora (uma de): {datetime_candidates}\n"
            f"- Iluminação (uma de): {illum_candidates}"
        )
        st.stop()

    out = pd.DataFrame()
    out["dt"] = pd.to_datetime(df[col_dt].astype(str).str.strip(), errors="coerce")

    illum = df[col_illum].astype(str).str.strip().str.replace(",", ".", regex=False)
    out["illum"] = pd.to_numeric(illum, errors="coerce")

    out = out.dropna(subset=["dt", "illum"]).sort_values("dt")
    return out


def _project_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# =============================================================================
# 5) TRANSFORMAÇÕES (ILUMINAÇÃO)
# =============================================================================
def compute_daily_means_illum(df_raw: pd.DataFrame) -> pd.DataFrame:
    df_d = (
        df_raw.set_index("dt")
        .resample("1D")["illum"]
        .mean()
        .dropna()
        .reset_index()
        .rename(columns={"illum": "illum_media_d"})
    )
    return df_d


def _last_3_days_window_from_dt(df: pd.DataFrame, dt_col: str = "dt") -> Tuple[pd.Timestamp, pd.Timestamp]:
    if df.empty or dt_col not in df.columns:
        today = pd.Timestamp.today().normalize()
        return today, today + pd.Timedelta(days=1)

    dts = pd.to_datetime(df[dt_col], errors="coerce").dropna()
    if dts.empty:
        today = pd.Timestamp.today().normalize()
        return today, today + pd.Timedelta(days=1)

    ultimo_dia = dts.max().normalize()
    inicio = ultimo_dia - pd.Timedelta(days=2)
    fim_exclusivo = ultimo_dia + pd.Timedelta(days=1)
    return inicio, fim_exclusivo


def compute_hourly_profile_last3days(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Perfil horário (1..24h): média do lux por hora, considerando somente os últimos 3 dias.
    """
    if df_raw.empty or "dt" not in df_raw.columns or "illum" not in df_raw.columns:
        return pd.DataFrame(columns=["hora", "media"])

    ini, fim = _last_3_days_window_from_dt(df_raw, "dt")

    tmp = df_raw.copy()
    tmp["dt"] = pd.to_datetime(tmp["dt"], errors="coerce")
    tmp = tmp[(tmp["dt"] >= ini) & (tmp["dt"] < fim)].copy()

    tmp["illum"] = pd.to_numeric(tmp["illum"], errors="coerce")
    tmp = tmp.dropna(subset=["illum", "dt"])
    if tmp.empty:
        return pd.DataFrame(columns=["hora", "media"])

    tmp["hora"] = tmp["dt"].dt.hour.astype(int) + 1  # 1..24

    out = tmp.groupby("hora", as_index=False)["illum"].mean().rename(columns={"illum": "media"})
    full = pd.DataFrame({"hora": list(range(1, 25))})
    out = full.merge(out, on="hora", how="left")
    return out


# =============================================================================
# 6) GRÁFICOS (ILUMINAÇÃO)
# =============================================================================
def build_chart_daily_illum(df_plot: pd.DataFrame, cfg: IluminacaoConfig) -> alt.Chart:
    # >>> ADIÇÃO (igual aos outros blocos):
    # garante que "HOJE" exista no dataset para o eixo X ir até hoje
    df_p = df_plot.copy()
    today = pd.Timestamp.today().normalize()
    if "dt" in df_p.columns:
        dt_norm = pd.to_datetime(df_p["dt"], errors="coerce").dt.normalize()
        if not (dt_norm == today).any():
            ghost = pd.DataFrame(
                {
                    "dt": [today],
                    "illum_media_d": [pd.NA],
                }
            )
            df_p = pd.concat([df_p, ghost], ignore_index=True).sort_values("dt")
    # <<<

    x = _calculate_x_zoom(df_p, "dt", cfg.janela_inicial_dias)

    y0, y1 = _auto_domain(df_p["illum_media_d"], pad_ratio=0.10)
    y_scale = alt.Scale(domain=[y0, y1])
    y_axis = alt.Axis(title="Iluminação média diária (lux)")

    base = alt.Chart(df_p).encode(
        x=alt.X("dt:T", axis=x.x_axis, scale=x.x_scale),
    )

    linha = base.mark_line().encode(
        y=alt.Y("illum_media_d:Q", scale=y_scale, axis=y_axis),
        tooltip=[
            alt.Tooltip("dt:T", title="Dia", format="%d/%m"),
            alt.Tooltip("illum_media_d:Q", title="Média (lux)", format=".1f"),
        ],
    )

    pontos = base.mark_point(size=60).encode(
        y=alt.Y("illum_media_d:Q", scale=y_scale),
        tooltip=[
            alt.Tooltip("dt:T", title="Dia", format="%d/%m"),
            alt.Tooltip("illum_media_d:Q", title="Média (lux)", format=".1f"),
        ],
    )

    return alt.layer(linha, pontos).properties(height=ALTURA_GRAFICO).interactive(bind_y=False)


def build_chart_hourly_profile_illum(df_profile: pd.DataFrame, cfg: IluminacaoConfig) -> alt.Chart:
    y0, y1 = _auto_domain(df_profile["media"], pad_ratio=0.10)

    x_axis = alt.Axis(title="Hora", values=list(range(1, 25)), labelAngle=0)
    x_scale = alt.Scale(domain=[1, 24], clamp=True)

    base = alt.Chart(df_profile).encode(
        x=alt.X("hora:Q", axis=x_axis, scale=x_scale),
    )

    y_scale_main = alt.Scale(domain=[y0, y1])
    y_axis_main = alt.Axis(title="Iluminação média (lux)")

    linha = base.mark_line().encode(
        y=alt.Y("media:Q", axis=y_axis_main, scale=y_scale_main),
        tooltip=[
            alt.Tooltip("hora:Q", title="Hora", format=".0f"),
            alt.Tooltip("media:Q", title="Média (lux)", format=".1f"),
        ],
    )

    pontos = base.mark_point(size=60).encode(
        y=alt.Y("media:Q", scale=y_scale_main),
        tooltip=[
            alt.Tooltip("hora:Q", title="Hora", format=".0f"),
            alt.Tooltip("media:Q", title="Média (lux)", format=".1f"),
        ],
    )

    layers = [linha, pontos]

    # Bandas de referência: Escuro (0–dark_max) e Produção (prod_min–prod_max)
    ref_bands = pd.DataFrame(
        {
            "ymin": [0.0, float(cfg.illum_prod_min)],
            "ymax": [float(cfg.illum_dark_max), float(cfg.illum_prod_max)],
            "opacity": [0.08, 0.14],
            "label": [
                f"Escuro (0–{cfg.illum_dark_max:g})",
                f"Produção ({cfg.illum_prod_min:g}–{cfg.illum_prod_max:g})",
            ],
        }
    )

    band = (
        alt.Chart(ref_bands)
        .mark_rect(color=cfg.cor_faixa_ref)
        .encode(
            y=alt.Y("ymin:Q", scale=y_scale_main),
            y2="ymax:Q",
            opacity=alt.Opacity("opacity:Q", legend=None),
        )
    )

    # Linhas: limite escuro e alvo
    ref_lines = pd.DataFrame(
        {
            "y": [float(cfg.illum_dark_max), float(cfg.illum_target)],
            "label": [f"Limite escuro ({cfg.illum_dark_max:g})", f"Alvo ({cfg.illum_target:g})"],
        }
    )

    rule = (
        alt.Chart(ref_lines)
        .mark_rule(opacity=0.35, strokeWidth=2, color=cfg.cor_faixa_ref)
        .encode(y=alt.Y("y:Q", scale=y_scale_main))
    )

    text = (
        alt.Chart(ref_lines.assign(hora=24))
        .mark_text(
            align="right",
            dx=-8,
            baseline="middle",
            fontSize=14,
            fontWeight="bold",
            color="white",
            strokeWidth=1.2,
        )
        .encode(
            x=alt.X("hora:Q", scale=x_scale),
            y=alt.Y("y:Q", scale=y_scale_main),
            text="label:N",
        )
    )

    layers = [band, rule, text] + layers

    return alt.layer(*layers).properties(height=ALTURA_GRAFICO).interactive(bind_y=False)


# =============================================================================
# 7) EXPORTS AUXILIARES (ILUMINAÇÃO)
# =============================================================================
def export_daily_illum_aux(df_d: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "iluminacao_media_diaria.csv")
    out = df_d.copy()
    out["dt"] = pd.to_datetime(out["dt"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    return path


def export_hourly_illum_aux(df_h: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "iluminacao_media_por_hora_ultimos_3_dias.csv")
    df_h.to_csv(path, index=False)
    return path


# =============================================================================
# 8) FUNÇÃO PÚBLICA (render) — BLOCO ILUMINAÇÃO (independente)
# =============================================================================
def render_iluminacao(
    PASTA_DADOS: str,
    arquivo_csv: str = "estacao_meteorologica.csv",
    ini: Optional[pd.Timestamp] = None,  # compatibilidade
    fim: Optional[pd.Timestamp] = None,  # compatibilidade
    pasta_aux: str = "auxs",
) -> None:
    _ = (ini, fim)

    cfg = IluminacaoConfig(
        janela_inicial_dias=int(CFG.janela_inicial_dias),
        cor_faixa_ref=str(CFG.cor_faixa_ref),
        illum_dark_max=float(CFG.illum_dark_max),
        illum_prod_min=float(CFG.illum_prod_min),
        illum_prod_max=float(CFG.illum_prod_max),
        illum_target=float(CFG.illum_target),
        dark_hours=tuple(CFG.dark_hours),
        prod_hours=tuple(CFG.prod_hours),
    )

    st.markdown("<div id='iluminacao' style='position: relative; top: -40px;'></div>", unsafe_allow_html=True)
    _render_css_diagnostico()

    csv_path = os.path.join(PASTA_DADOS, arquivo_csv)
    if not os.path.exists(csv_path):
        st.warning(f"Arquivo `{arquivo_csv}` não encontrado em `{PASTA_DADOS}/`.")
        return

    df_raw = _read_and_normalize_illum_csv(csv_path)
    if df_raw.empty:
        st.info("Arquivo sem dados válidos de iluminação.")
        return

    root = _project_root()
    aux_dir = os.path.join(root, pasta_aux)
    _ensure_dir(aux_dir)

    st.subheader("Iluminação (lux)")

    # A) Série diária (remember: eixo X deve ir até HOJE)
    df_d = compute_daily_means_illum(df_raw)
    if df_d.empty:
        st.info("Não há dados suficientes para calcular média diária de iluminação.")
    else:
        export_daily_illum_aux(df_d, aux_dir)
        st.altair_chart(build_chart_daily_illum(df_d, cfg), use_container_width=True)

    # B) Perfil por hora (últimos 3 dias) + diagnóstico
    st.subheader("Iluminação — Média por Hora (últimos 3 dias)")

    df_h = compute_hourly_profile_last3days(df_raw)
    if not df_h["media"].notna().any():
        st.info("Não há dados suficientes de iluminação nos últimos 3 dias para calcular média por hora.")
        return

    export_hourly_illum_aux(df_h, aux_dir)
    st.altair_chart(build_chart_hourly_profile_illum(df_h, cfg), use_container_width=True)

    _render_diagnostico_iluminacao(df_h, cfg)
