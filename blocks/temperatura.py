# =============================================================================
# blocks/temperatura.py
# Temperatura — Série diária + Turnos (últimos 3 dias) + THI + Heatmap + Diagnóstico
# (sem MQ135 e sem Iluminação)
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st


# -----------------------------------------------------------------------------
# Diagnóstico (módulo separado; sem Streamlit)
# -----------------------------------------------------------------------------
try:
    from domain.temperatura_diagnostico import diagnosticar_temperatura_ambiente
except Exception as _err:
    diagnosticar_temperatura_ambiente = None
    _DIAG_IMPORT_ERROR = _err
else:
    _DIAG_IMPORT_ERROR = None


# =============================================================================
# 1) CONFIG — PONTO ÚNICO PARA AJUSTES RÁPIDOS
# =============================================================================
@dataclass(frozen=True)
class TemperaturaConfig:
    # Janela inicial (em dias) para gráficos com eixo temporal (ZOOM no X)
    janela_inicial_dias: int = 7

    # Faixa de conforto (>= 18 semanas)
    conforto_min: float = 18.0
    conforto_max: float = 24.0

    # THI (faixa alvo "clássica" — ajuste conforme sua referência)
    thi_min: float = 70.0
    thi_max: float = 75.0

    # Aparência (cores)
    cor_faixa_conforto: str = "#2ecc71"
    cor_barra_padrao: str = "#4c78a8"
    cor_barra_destaque: str = "#e74c3c"

    # Heatmap — domínio fixo (temperatura)
    heatmap_domain_min: float = 10.0
    heatmap_domain_max: float = 40.0

    # Heatmap — paleta contínua
    heatmap_palette: Tuple[str, ...] = (
        "#1b3b8b",
        "#2355c8",
        "#2e7bf7",
        "#49b5ff",
        "#7be3ff",
        "#bdf7d7",
        "#f3f7a1",
        "#ffd35a",
        "#ff9b3d",
        "#f04b2d",
        "#b3001b",
    )

    heatmap_interpolate: str = "lab"
    heatmap_rule_opacity: float = 0.25
    heatmap_label_fontsize: int = 10

    # Eixo X
    x_label_angle: int = 0

    # Domínio Y fixo para temperatura média diária
    y_min: float = 10.0
    y_max: float = 35.0


CFG = TemperaturaConfig()
ALTURA_GRAFICO_DIARIO: int = 300


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


def _calculate_x_zoom_like_alimentacao(df: pd.DataFrame, date_col: str, janela_dias: int) -> GlobalScales:
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


def _safe_float(x: float, default: float) -> float:
    try:
        v = float(x)
        if pd.isna(v):
            return default
        return v
    except Exception:
        return default


# =============================================================================
# 2b) DIAGNÓSTICO — HTML/CSS
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


def _render_diagnostico_box(diag: dict) -> None:
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


def _render_diagnostico_temperatura(
    df_turnos_3d: pd.DataFrame,
    df_summary: pd.DataFrame,
    df_summary_thi: Optional[pd.DataFrame],
    cfg: TemperaturaConfig,
) -> None:
    if diagnosticar_temperatura_ambiente is None:
        st.warning("Diagnóstico indisponível: não foi possível importar `domain/temperatura_diagnostico.py`.")
        if _DIAG_IMPORT_ERROR is not None:
            with st.expander("Detalhes técnicos (import)"):
                st.code(str(_DIAG_IMPORT_ERROR))
        return

    diag = diagnosticar_temperatura_ambiente(
        df_turnos_3d=df_turnos_3d,
        df_summary=df_summary,
        df_summary_thi=df_summary_thi,
        conforto_min=float(cfg.conforto_min),
        conforto_max=float(cfg.conforto_max),
        thi_min=float(cfg.thi_min),
        thi_max=float(cfg.thi_max),
    )
    _render_diagnostico_box(diag)


# =============================================================================
# 3) IO + NORMALIZAÇÃO (somente temperatura + umidade opcional)
# =============================================================================
def _pick_first_existing(candidates: List[str], cols: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in cols}
    for cand in candidates:
        key = cand.lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def _read_and_normalize_estacao_csv(csv_path: str) -> pd.DataFrame:
    """
    Normaliza para:
      - dt   : datetime
      - temp : float (°C)
      - rh   : float (%), opcional
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
    temp_candidates = [
        "temperature_c",
        "temperatura",
        "temp",
        "temperature",
        "temp_c",
        "temperatura_c",
    ]
    rh_candidates = [
        "humidity_pct",
        "umidade",
        "humidity",
        "rh",
        "umidade_pct",
        "humid",
    ]

    col_dt = _pick_first_existing(datetime_candidates, df.columns.tolist())
    col_temp = _pick_first_existing(temp_candidates, df.columns.tolist())
    col_rh = _pick_first_existing(rh_candidates, df.columns.tolist())

    if col_dt is None or col_temp is None:
        st.error(
            "Formato inesperado do arquivo `estacao_meteorologica.csv`.\n\n"
            f"Colunas encontradas: {list(df.columns)}\n\n"
            "Preciso de:\n"
            f"- Data/hora (uma de): {datetime_candidates}\n"
            f"- Temperatura (uma de): {temp_candidates}\n"
            f"- Umidade (opcional, uma de): {rh_candidates}"
        )
        st.stop()

    out = pd.DataFrame()
    out["dt"] = pd.to_datetime(df[col_dt].astype(str).str.strip(), errors="coerce")

    temp = df[col_temp].astype(str).str.strip().str.replace(",", ".", regex=False)
    out["temp"] = pd.to_numeric(temp, errors="coerce")

    if col_rh is not None:
        rh = df[col_rh].astype(str).str.strip().str.replace(",", ".", regex=False)
        out["rh"] = pd.to_numeric(rh, errors="coerce")
    else:
        out["rh"] = pd.NA

    out = out.dropna(subset=["dt", "temp"]).sort_values("dt")
    return out


def _project_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# =============================================================================
# 4) TRANSFORMAÇÕES (temperatura + THI)
# =============================================================================
def compute_daily_means(df_raw: pd.DataFrame) -> pd.DataFrame:
    df_d = (
        df_raw.set_index("dt")
        .resample("1D")["temp"]
        .mean()
        .dropna()
        .reset_index()
        .rename(columns={"temp": "temp_media_d"})
    )
    return df_d


def _assign_turno(hour: int) -> str:
    if 0 <= hour <= 5:
        return "Madrugada"
    if 6 <= hour <= 11:
        return "Manhã"
    if 12 <= hour <= 17:
        return "Tarde"
    return "Noite"


def thi_simple(temp_c: float, rh_pct: float) -> float:
    """
    THI em escala "clássica" (T em Fahrenheit), compatível com faixas 70–75.
    THI = T_F - (0.55 - 0.0055*RH) * (T_F - 58)
    """
    if pd.isna(rh_pct) or pd.isna(temp_c):
        return float("nan")

    RH = float(rh_pct)
    T_F = float(temp_c) * 9.0 / 5.0 + 32.0
    return T_F - (0.55 - 0.0055 * RH) * (T_F - 58.0)


def compute_turno_means_with_thi(df_raw: pd.DataFrame) -> pd.DataFrame:
    tmp = df_raw.copy()
    tmp["dia"] = tmp["dt"].dt.date
    tmp["hora"] = tmp["dt"].dt.hour
    tmp["turno"] = tmp["hora"].apply(_assign_turno)

    tmp["thi"] = tmp.apply(
        lambda r: thi_simple(r["temp"], r["rh"]) if pd.notna(r.get("rh", pd.NA)) else float("nan"),
        axis=1,
    )

    df_t = (
        tmp.groupby(["dia", "turno"], as_index=False)
        .agg(
            temp_media_turno=("temp", "mean"),
            rh_media_turno=("rh", "mean"),
            thi_media_turno=("thi", "mean"),
        )
    )

    ordem = ["Madrugada", "Manhã", "Tarde", "Noite"]
    df_t["turno"] = pd.Categorical(df_t["turno"], categories=ordem, ordered=True)
    df_t = df_t.sort_values(["dia", "turno"]).reset_index(drop=True)
    return df_t


def discomfort_score(temp: float, conforto_min: float, conforto_max: float) -> float:
    if temp < conforto_min:
        return float(conforto_min - temp)
    if temp > conforto_max:
        return float(temp - conforto_max)
    return 0.0


def compute_turno_summary(df_turnos: pd.DataFrame, conforto_min: float, conforto_max: float) -> pd.DataFrame:
    df_s = df_turnos.groupby("turno", as_index=False)["temp_media_turno"].mean().copy()
    df_s["desconforto"] = df_s["temp_media_turno"].apply(
        lambda t: discomfort_score(float(t), conforto_min, conforto_max)
    )
    ordem = ["Madrugada", "Manhã", "Tarde", "Noite"]
    df_s["turno"] = pd.Categorical(df_s["turno"], categories=ordem, ordered=True)
    df_s = df_s.sort_values("turno").reset_index(drop=True)
    return df_s


def pick_worst_turno(df_summary: pd.DataFrame) -> Tuple[str, float, float]:
    if (df_summary["desconforto"] > 0).any():
        row = df_summary.sort_values(["desconforto", "temp_media_turno"], ascending=[False, False]).iloc[0]
    else:
        row = df_summary.sort_values(["temp_media_turno"], ascending=[False]).iloc[0]
    return str(row["turno"]), float(row["temp_media_turno"]), float(row["desconforto"])


def discomfort_score_range(valor: float, vmin: float, vmax: float) -> float:
    if pd.isna(valor):
        return 0.0
    if valor < vmin:
        return float(vmin - valor)
    if valor > vmax:
        return float(valor - vmax)
    return 0.0


def compute_turno_summary_thi(df_turnos: pd.DataFrame, thi_min: float, thi_max: float) -> pd.DataFrame:
    df_s = df_turnos.groupby("turno", as_index=False)["thi_media_turno"].mean().copy()
    df_s["desconforto_thi"] = df_s["thi_media_turno"].apply(
        lambda v: discomfort_score_range(float(v), thi_min, thi_max) if pd.notna(v) else 0.0
    )
    ordem = ["Madrugada", "Manhã", "Tarde", "Noite"]
    df_s["turno"] = pd.Categorical(df_s["turno"], categories=ordem, ordered=True)
    df_s = df_s.sort_values("turno").reset_index(drop=True)
    return df_s


def pick_worst_turno_thi(df_summary_thi: pd.DataFrame) -> str:
    if (df_summary_thi["desconforto_thi"] > 0).any():
        row = df_summary_thi.sort_values(["desconforto_thi", "thi_media_turno"], ascending=[False, False]).iloc[0]
    else:
        row = df_summary_thi.sort_values(["thi_media_turno"], ascending=[False]).iloc[0]
    return str(row["turno"])


# =============================================================================
# 5) GRÁFICOS (somente temperatura)
# =============================================================================
def build_chart_media_diaria(df_d_plot: pd.DataFrame, cfg: TemperaturaConfig) -> alt.Chart:
    # >>> ADIÇÃO (igual aos outros blocos):
    # garante que "HOJE" exista no dataset para o eixo X ir até hoje
    df_plot = df_d_plot.copy()
    today = pd.Timestamp.today().normalize()
    if "dt" in df_plot.columns:
        dt_norm = pd.to_datetime(df_plot["dt"], errors="coerce").dt.normalize()
        if not (dt_norm == today).any():
            ghost = pd.DataFrame(
                {
                    "dt": [today],
                    "temp_media_d": [pd.NA],
                    "ref_min": [cfg.conforto_min],
                    "ref_max": [cfg.conforto_max],
                }
            )
            df_plot = pd.concat([df_plot, ghost], ignore_index=True).sort_values("dt")
    # <<<

    x = _calculate_x_zoom_like_alimentacao(df_plot, "dt", cfg.janela_inicial_dias)

    y_min = _safe_float(cfg.y_min, 10.0)
    y_max = _safe_float(cfg.y_max, 35.0)
    if y_min >= y_max:
        y_min, y_max = 10.0, 35.0

    y_scale = alt.Scale(domain=[y_min, y_max])
    y_axis = alt.Axis(title="Temperatura média diária (°C)")

    base = alt.Chart(df_plot).encode(
        x=alt.X("dt:T", axis=x.x_axis, scale=x.x_scale),
    )

    faixa = base.mark_area(opacity=0.18, color=cfg.cor_faixa_conforto).encode(
        y=alt.Y("ref_min:Q", scale=y_scale, axis=y_axis),
        y2="ref_max:Q",
    )

    linha = base.mark_line().encode(
        y=alt.Y("temp_media_d:Q", scale=y_scale, axis=y_axis),
        tooltip=[
            alt.Tooltip("dt:T", title="Dia", format="%d/%m"),
            alt.Tooltip("temp_media_d:Q", title="Média (°C)", format=".1f"),
        ],
    )

    pontos = base.mark_point(size=60).encode(
        y=alt.Y("temp_media_d:Q", scale=y_scale),
        tooltip=[
            alt.Tooltip("dt:T", title="Dia", format="%d/%m"),
            alt.Tooltip("temp_media_d:Q", title="Média (°C)", format=".1f"),
        ],
    )

    return alt.layer(faixa, linha, pontos).properties(height=ALTURA_GRAFICO_DIARIO).interactive(bind_y=False)


def build_chart_turnos_barras(df_summary: pd.DataFrame, worst_turno: str, cfg: TemperaturaConfig) -> alt.Chart:
    y_min = _safe_float(cfg.y_min, 10.0)
    y_max = _safe_float(cfg.y_max, 35.0)
    if y_min >= y_max:
        y_min, y_max = 10.0, 35.0

    base = alt.Chart(df_summary).encode(
        y=alt.Y("turno:N", title="Turno", sort=None),
        x=alt.X(
            "temp_media_turno:Q",
            title="Temperatura média (°C)",
            scale=alt.Scale(domain=[y_min, y_max]),
        ),
        tooltip=[
            alt.Tooltip("turno:N", title="Turno"),
            alt.Tooltip("temp_media_turno:Q", title="Média (°C)", format=".1f"),
            alt.Tooltip("desconforto:Q", title="Desconforto (°C)", format=".1f"),
        ],
    )

    faixa = alt.Chart(pd.DataFrame({"xmin": [cfg.conforto_min], "xmax": [cfg.conforto_max]})).mark_rect(
        opacity=0.18,
        color=cfg.cor_faixa_conforto,
    ).encode(x="xmin:Q", x2="xmax:Q")

    bars = base.mark_bar().encode(
        color=alt.condition(
            alt.datum.turno == worst_turno,
            alt.value(cfg.cor_barra_destaque),
            alt.value(cfg.cor_barra_padrao),
        )
    )

    labels = base.mark_text(dx=6, align="left", baseline="middle", color="white").encode(
        text=alt.Text("temp_media_turno:Q", format=".1f")
    )

    return (faixa + bars + labels).properties(height=260)


def build_chart_turnos_barras_thi(
    df_summary_thi: pd.DataFrame,
    worst_turno_thi: str,
    thi_min: float,
    thi_max: float,
    cfg: TemperaturaConfig,
) -> alt.Chart:
    base = alt.Chart(df_summary_thi).encode(
        y=alt.Y("turno:N", title="Turno", sort=None),
        x=alt.X("thi_media_turno:Q", title="Estresse Térmico médio (THI)", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("turno:N", title="Turno"),
            alt.Tooltip("thi_media_turno:Q", title="THI médio (escala clássica)", format=".1f"),
            alt.Tooltip("desconforto_thi:Q", title="Desconforto THI", format=".1f"),
        ],
    )

    faixa = alt.Chart(pd.DataFrame({"xmin": [thi_min], "xmax": [thi_max]})).mark_rect(
        opacity=0.18,
        color=cfg.cor_faixa_conforto,
    ).encode(x="xmin:Q", x2="xmax:Q")

    bars = base.mark_bar().encode(
        color=alt.condition(
            alt.datum.turno == worst_turno_thi,
            alt.value(cfg.cor_barra_destaque),
            alt.value(cfg.cor_barra_padrao),
        )
    )

    labels = base.mark_text(dx=6, align="left", baseline="middle", color="white").encode(
        text=alt.Text("thi_media_turno:Q", format=".2f")
    )

    return (faixa + bars + labels).properties(height=260)


def build_chart_turnos_heatmap(df_turnos: pd.DataFrame, cfg: TemperaturaConfig) -> alt.Chart:
    df_h = df_turnos.copy()

    df_h["dia_ini"] = pd.to_datetime(df_h["dia"]).dt.normalize()
    df_h["dia_fim"] = df_h["dia_ini"] + pd.Timedelta(days=1)
    df_h["dia_mid"] = df_h["dia_ini"] + pd.Timedelta(hours=12)

    ordem = ["Madrugada", "Manhã", "Tarde", "Noite"]
    df_h["turno"] = pd.Categorical(df_h["turno"], categories=ordem, ordered=True)

    df_h["temp_media_turno"] = pd.to_numeric(df_h["temp_media_turno"], errors="coerce")
    df_h = df_h.dropna(subset=["temp_media_turno"])

    min_d = df_h["dia_ini"].min()
    max_d = df_h["dia_ini"].max()
    today = pd.Timestamp.today().normalize()

    if pd.isna(min_d) or pd.isna(max_d):
        min_d, max_d = today, today

    # >>> AJUSTE: fim do heatmap acompanha HOJE (como nos outros)
    max_d = max(max_d, today)

    start_d = max(min_d, max_d - pd.Timedelta(days=int(cfg.janela_inicial_dias)))
    end_d = max_d + pd.Timedelta(days=1)  # mantém a célula do dia completo
    # <<<

    domain_min = float(cfg.heatmap_domain_min)
    domain_max = float(cfg.heatmap_domain_max)
    if domain_min >= domain_max:
        domain_min, domain_max = 10.0, 40.0

    color_scale = alt.Scale(
        domain=[domain_min, domain_max],
        range=list(cfg.heatmap_palette),
        clamp=True,
        nice=False,
        interpolate=cfg.heatmap_interpolate,
    )

    x_axis = make_x_axis_dia_pt("Dia")

    rects = (
        alt.Chart(df_h)
        .mark_rect()
        .encode(
            x=alt.X(
                "dia_ini:T",
                title="Dia",
                axis=x_axis,
                scale=alt.Scale(domain=[start_d, end_d]),
            ),
            x2="dia_fim:T",
            y=alt.Y("turno:N", title="Turno", sort=ordem),
            color=alt.Color(
                "temp_media_turno:Q",
                title="Temp. média (°C)",
                scale=color_scale,
                legend=alt.Legend(format=".1f"),
            ),
            tooltip=[
                alt.Tooltip("dia_ini:T", title="Dia", format="%d/%m"),
                alt.Tooltip("turno:N", title="Turno"),
                alt.Tooltip("temp_media_turno:Q", title="Média (°C)", format=".1f"),
            ],
        )
        .properties(height=220)
    )

    df_days = df_h[["dia_ini"]].drop_duplicates().sort_values("dia_ini").reset_index(drop=True)
    rules = alt.Chart(df_days).mark_rule(opacity=cfg.heatmap_rule_opacity).encode(x="dia_ini:T")

    labels = (
        alt.Chart(df_h)
        .mark_text(fontSize=cfg.heatmap_label_fontsize)
        .encode(
            x="dia_mid:T",
            y=alt.Y("turno:N", sort=ordem),
            text=alt.Text("temp_media_turno:Q", format=".1f"),
        )
    )

    return (rects + rules + labels).interactive()


# =============================================================================
# 6) EXPORTS AUXILIARES (somente temperatura)
# =============================================================================
def export_daily_aux(df_d: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "temperatura_media_diaria.csv")
    out = df_d.copy()
    out["dt"] = pd.to_datetime(out["dt"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    return path


def export_turnos_aux(df_turnos: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "temperatura_media_por_turno.csv")
    out = df_turnos.copy()
    out["dia"] = pd.to_datetime(out["dia"]).dt.strftime("%Y-%m-%d")
    out["turno"] = out["turno"].astype(str)
    out.to_csv(path, index=False)
    return path


def export_turnos_resumo_aux(df_summary: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "temperatura_media_por_turno_resumo.csv")
    out = df_summary.copy()
    out["turno"] = out["turno"].astype(str)
    out.to_csv(path, index=False)
    return path


def export_heatmap_aux(df_turnos: pd.DataFrame, aux_dir: str) -> str:
    path = os.path.join(aux_dir, "temperatura_heatmap_dia_turno.csv")
    out = df_turnos.copy()
    out["dia"] = pd.to_datetime(out["dia"]).dt.strftime("%Y-%m-%d")
    out["turno"] = out["turno"].astype(str)
    cols = [c for c in ["dia", "turno", "temp_media_turno"] if c in out.columns]
    out[cols].to_csv(path, index=False)
    return path


# =============================================================================
# 7) FUNÇÃO PÚBLICA (render)
# =============================================================================
def render_temperatura(
    PASTA_DADOS: str,
    arquivo_csv: str = "estacao_meteorologica.csv",
    ini: Optional[pd.Timestamp] = None,  # compatibilidade
    fim: Optional[pd.Timestamp] = None,  # compatibilidade
    conforto_min: float = CFG.conforto_min,
    conforto_max: float = CFG.conforto_max,
    pasta_aux: str = "auxs",
) -> None:
    _ = (ini, fim)

    cfg = TemperaturaConfig(
        janela_inicial_dias=int(CFG.janela_inicial_dias),
        conforto_min=float(conforto_min),
        conforto_max=float(conforto_max),
        thi_min=float(CFG.thi_min),
        thi_max=float(CFG.thi_max),
        cor_faixa_conforto=str(CFG.cor_faixa_conforto),
        cor_barra_padrao=str(CFG.cor_barra_padrao),
        cor_barra_destaque=str(CFG.cor_barra_destaque),
        heatmap_domain_min=float(CFG.heatmap_domain_min),
        heatmap_domain_max=float(CFG.heatmap_domain_max),
        heatmap_palette=tuple(CFG.heatmap_palette),
        heatmap_interpolate=str(CFG.heatmap_interpolate),
        heatmap_rule_opacity=float(CFG.heatmap_rule_opacity),
        heatmap_label_fontsize=int(CFG.heatmap_label_fontsize),
        x_label_angle=int(CFG.x_label_angle),
        y_min=float(CFG.y_min),
        y_max=float(CFG.y_max),
    )

    st.markdown("<div id='temperatura' style='position: relative; top: -40px;'></div>", unsafe_allow_html=True)
    _render_css_diagnostico()

    csv_path = os.path.join(PASTA_DADOS, arquivo_csv)
    if not os.path.exists(csv_path):
        st.warning(f"Arquivo `{arquivo_csv}` não encontrado em `{PASTA_DADOS}/`.")
        return

    df_raw = _read_and_normalize_estacao_csv(csv_path)
    if df_raw.empty:
        st.info("Arquivo sem dados válidos.")
        return

    root = _project_root()
    aux_dir = os.path.join(root, pasta_aux)
    _ensure_dir(aux_dir)

    # 1) Temperatura — média diária
    st.subheader("Temperatura Média Diária")

    df_d = compute_daily_means(df_raw)
    if df_d.empty:
        st.info("Não há dados suficientes para calcular média diária de temperatura.")
        return

    export_daily_aux(df_d, aux_dir)

    df_d_plot = df_d.copy()
    df_d_plot["ref_min"] = cfg.conforto_min
    df_d_plot["ref_max"] = cfg.conforto_max

    st.altair_chart(build_chart_media_diaria(df_d_plot, cfg), use_container_width=True)

    # 2) Turnos (com THI)
    df_turnos = compute_turno_means_with_thi(df_raw)
    if df_turnos.empty:
        st.info("Não há dados suficientes para calcular médias por turno.")
        return

    # Usar somente os 3 últimos dias disponíveis
    df_turnos["dia_dt"] = pd.to_datetime(df_turnos["dia"]).dt.normalize()
    ultimo_dia = df_turnos["dia_dt"].max()
    inicio_janela = ultimo_dia - pd.Timedelta(days=2)

    df_turnos_3d = df_turnos[df_turnos["dia_dt"] >= inicio_janela].copy()
    df_turnos_3d = df_turnos_3d.drop(columns=["dia_dt"])

    st.subheader("Temperatura média por turno (últimos 3 dias)")

    export_turnos_aux(df_turnos_3d, aux_dir)

    df_summary = compute_turno_summary(df_turnos_3d, cfg.conforto_min, cfg.conforto_max)
    export_turnos_resumo_aux(df_summary, aux_dir)

    worst_turno, worst_temp, worst_desc = pick_worst_turno(df_summary)

    st.altair_chart(
        build_chart_turnos_barras(df_summary, worst_turno=worst_turno, cfg=cfg),
        use_container_width=True,
    )

    if worst_desc > 0:
        st.warning(
            f"Pior turno (temperatura): **{worst_turno}** — média **{worst_temp:.1f} °C** "
            f"(desconforto de **{worst_desc:.1f} °C** em relação à faixa "
            f"{cfg.conforto_min:.1f}–{cfg.conforto_max:.1f} °C)."
        )
    else:
        st.success(
            f"Todos os turnos estão, em média, dentro da faixa de conforto. "
            f"Maior média (desempate): **{worst_turno}** — **{worst_temp:.1f} °C**."
        )

    # THI por turno (últimos 3 dias)
    st.subheader("Estresse Térmico (THI) médio por turno (últimos 3 dias)")

    df_summary_thi: Optional[pd.DataFrame] = None
    if df_turnos_3d["thi_media_turno"].notna().any():
        df_summary_thi = compute_turno_summary_thi(df_turnos_3d, thi_min=cfg.thi_min, thi_max=cfg.thi_max)
        worst_turno_thi = pick_worst_turno_thi(df_summary_thi)

        st.altair_chart(
            build_chart_turnos_barras_thi(
                df_summary_thi=df_summary_thi,
                worst_turno_thi=worst_turno_thi,
                thi_min=cfg.thi_min,
                thi_max=cfg.thi_max,
                cfg=cfg,
            ),
            use_container_width=True,
        )

        if (df_summary_thi["desconforto_thi"] > 0).any():
            st.warning(f"Estresse térmico detectado: o turno mais crítico é o da **{worst_turno_thi}**.")
        else:
            st.success("THI médio por turno está dentro da faixa definida.")
    else:
        st.info("Não há umidade (RH) no arquivo; THI não pôde ser calculado.")

    # Diagnóstico consolidado (temperatura + THI)
    _render_diagnostico_temperatura(df_turnos_3d, df_summary, df_summary_thi, cfg)

    # 3) Heatmap
    st.subheader("Mapa de calor: dia × turno (temperatura)")

    _ = export_heatmap_aux(df_turnos, aux_dir)
    st.altair_chart(build_chart_turnos_heatmap(df_turnos, cfg), use_container_width=True)
