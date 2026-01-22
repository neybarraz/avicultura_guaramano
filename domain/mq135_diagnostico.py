# =============================================================================
# domain/mq135_diagnostico.py
# Diagnóstico automático — MQ135 (perfil horário últimos 3 dias)
# - Diagnóstico relativo (sem ppm): usa a distribuição do próprio perfil
# =============================================================================

from __future__ import annotations

from typing import Dict, List

import pandas as pd


# -----------------------------------------------------------------------------
# Convenção de retorno (igual alimentacao_diagnostico):
# {
#   "status": "DENTRO" | "FORA",
#   "resumo_curto": str,
#   "impacts_aves": [..],
#   "impacts_producao": [..],
#   "impacts_qualidade": [..],
#   "observar": [..],
#   "acoes": [..],
#   "debug": {...}   # opcional
# }
# -----------------------------------------------------------------------------


def _to_series_media(df_profile: pd.DataFrame) -> pd.Series:
    if df_profile is None or df_profile.empty:
        return pd.Series(dtype="float64")
    if "media" not in df_profile.columns:
        return pd.Series(dtype="float64")
    s = pd.to_numeric(df_profile["media"], errors="coerce").dropna()
    return s


def _get_hour_value_map(df_profile: pd.DataFrame) -> Dict[int, float]:
    if df_profile is None or df_profile.empty:
        return {}
    if "hora" not in df_profile.columns or "media" not in df_profile.columns:
        return {}

    tmp = df_profile.copy()
    tmp["hora"] = pd.to_numeric(tmp["hora"], errors="coerce")
    tmp["media"] = pd.to_numeric(tmp["media"], errors="coerce")
    tmp = tmp.dropna(subset=["hora", "media"])

    out: Dict[int, float] = {}
    for _, r in tmp.iterrows():
        out[int(r["hora"])] = float(r["media"])
    return out


def _consecutive_runs(hours_sorted: List[int], min_len: int = 3) -> List[List[int]]:
    """
    Recebe lista de horas ordenadas e retorna blocos consecutivos com tamanho >= min_len.
    """
    if not hours_sorted:
        return []
    runs: List[List[int]] = []
    current = [hours_sorted[0]]
    for h in hours_sorted[1:]:
        if h == current[-1] + 1:
            current.append(h)
        else:
            if len(current) >= min_len:
                runs.append(current)
            current = [h]
    if len(current) >= min_len:
        runs.append(current)
    return runs


def _fmt_hours(hours: List[int], max_items: int = 12) -> str:
    if not hours:
        return ""
    h2 = hours[:max_items]
    s = ", ".join(map(str, h2))
    return s + (" ..." if len(hours) > max_items else "")


def _blocks_to_str(runs: List[List[int]]) -> str:
    if not runs:
        return ""
    blocks = []
    for r in runs:
        if len(r) == 1:
            blocks.append(str(r[0]))
        else:
            blocks.append(f"{r[0]}–{r[-1]}")
    return ", ".join(blocks)


# =============================================================================
# MQ135 — perfil por hora (últimos 3 dias)
# =============================================================================
def diagnosticar_mq135_perfil_horario(
    *,
    df_profile: pd.DataFrame,
    q_low: float = 0.25,
    q_high: float = 0.75,
    q2_low: float = 0.10,
    q2_high: float = 0.90,
) -> Dict:
    """
    Diagnóstico relativo (sem ppm): usa a distribuição do próprio perfil.

    Heurísticas:
    - Hora acima de P90: "pico"
    - Sustentação acima de P75 por >= 3 horas consecutivas: "janela ruim"
    - Amplitude muito alta (max-min): instabilidade (manejo ou sensor/posição)
    """
    s = _to_series_media(df_profile)
    if s.empty:
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes para avaliar MQ135 (perfil por hora).",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    p10 = float(s.quantile(q2_low))
    p25 = float(s.quantile(q_low))
    p50 = float(s.quantile(0.50))
    p75 = float(s.quantile(q_high))
    p90 = float(s.quantile(q2_high))

    vmin = float(s.min())
    vmax = float(s.max())
    iqr = max(p75 - p25, 1e-9)
    amp = vmax - vmin

    hv = _get_hour_value_map(df_profile)

    above_p90 = sorted([h for h, v in hv.items() if v > p90])
    above_p75 = sorted([h for h, v in hv.items() if v > p75])
    runs_above_p75 = _consecutive_runs(above_p75, min_len=3)

    problemas: List[str] = []
    if above_p90:
        problemas.append("picos acima do P90")
    if runs_above_p75:
        problemas.append("período sustentado acima do P75")
    if amp > 4.0 * iqr:
        problemas.append("instabilidade horária alta (amplitude grande)")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = "Perfil de MQ135 está estável dentro da faixa relativa (sem picos relevantes no período analisado)."
    else:
        parts = []
        if above_p90:
            parts.append(f"Picos acima do P90 nas horas: {_fmt_hours(above_p90)}.")
        if runs_above_p75:
            parts.append(f"Período sustentado acima do P75 em: {_blocks_to_str(runs_above_p75)}.")
        if amp > 4.0 * iqr:
            parts.append("Amplitude horária alta sugere instabilidade operacional ou efeito de sensor/posição.")
        resumo = " ".join(parts).strip()

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if above_p90 or runs_above_p75:
        impacts_aves += [
            "Possível desconforto respiratório/irritação (dependendo do que está contribuindo: amônia/poeira/CO₂).",
            "Maior estresse em períodos de ar pior, com pior repouso/atividade.",
        ]
        impacts_producao += [
            "Pode reduzir consumo em horários críticos e afetar desempenho se virar padrão recorrente.",
            "Maior variabilidade de produção quando o ar pior coincide com horários de maior atividade.",
        ]
        impacts_qualidade += [
            "Impacto indireto possível (via consumo/estresse) na uniformidade e qualidade.",
        ]
        observar += [
            "Rotina real de ventilação/inlets nos horários críticos (setpoint vs entrega).",
            "Manejo que gera poeira: arraçoamento, revolvimento de cama, movimentação intensa.",
            "Local do sensor (corrente de ar direta, exaustor, janela, porta).",
        ]
        acoes += [
            "Correlacionar picos por hora com eventos do dia (alimentação, limpeza, ajuste de cortinas, ventiladores).",
            "Verificar se a ventilação cai em horários de pico (se esse padrão aparecer).",
            "Se possível, medir amônia/CO₂ pontualmente para validar o que o MQ135 está capturando (referência).",
        ]

    if amp > 4.0 * iqr:
        observar += [
            "Possível interferência de fluxo de ar no sensor (picos e vales por posição).",
        ]
        acoes += [
            "Revisar posição do sensor: afastar de jatos de ventiladores e de exaustores.",
            "Fixar altura e local padrão para comparação histórica.",
        ]

    if status == "DENTRO":
        observar += [
            "Manter acompanhamento de tendência (semanal) para detectar deriva gradual.",
        ]
        acoes += [
            "Usar esta curva como baseline do seu aviário e comparar com 7/14 dias no futuro.",
        ]

    return {
        "status": status,
        "resumo_curto": resumo,
        "impacts_aves": impacts_aves,
        "impacts_producao": impacts_producao,
        "impacts_qualidade": impacts_qualidade,
        "observar": observar,
        "acoes": acoes,
        "debug": {
            "p10": p10,
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "p90": p90,
            "vmin": vmin,
            "vmax": vmax,
            "iqr": iqr,
            "amp": amp,
            "above_p90_hours": above_p90,
            "runs_above_p75": runs_above_p75,
        },
    }
