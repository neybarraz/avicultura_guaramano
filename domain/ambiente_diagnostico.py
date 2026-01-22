# =============================================================================
# domain/ambiente_diagnostico.py
# Diagnósticos automáticos (padrão alimentacao_diagnostico)
# - Temperatura (média diária; por turno; heatmap dia×turno)
# - THI (por turno)
# - Iluminação (perfil horário últimos 3 dias)
# - MQ135 (perfil horário últimos 3 dias)
# =============================================================================

from __future__ import annotations

from typing import Dict, List, Tuple

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
    if df_profile is None or df_profile.empty or "hora" not in df_profile.columns or "media" not in df_profile.columns:
        return {}
    tmp = df_profile.copy()
    tmp["hora"] = pd.to_numeric(tmp["hora"], errors="coerce")
    tmp["media"] = pd.to_numeric(tmp["media"], errors="coerce")
    tmp = tmp.dropna(subset=["hora", "media"])
    out: Dict[int, float] = {}
    for _, r in tmp.iterrows():
        h = int(r["hora"])
        out[h] = float(r["media"])
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


def _window_last_days(df: pd.DataFrame, date_col: str, days: int) -> pd.DataFrame:
    if df is None or df.empty or date_col not in df.columns:
        return pd.DataFrame()
    tmp = df.copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp = tmp.dropna(subset=[date_col])
    if tmp.empty:
        return pd.DataFrame()
    last = tmp[date_col].max().normalize()
    start = last - pd.Timedelta(days=int(max(days - 1, 0)))
    end = last + pd.Timedelta(days=1)
    tmp = tmp[(tmp[date_col] >= start) & (tmp[date_col] < end)].copy()
    return tmp


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
# 1) ILUMINAÇÃO — perfil por hora (últimos 3 dias)
# =============================================================================
def diagnosticar_iluminacao_perfil_horario(
    *,
    df_profile: pd.DataFrame,
    dark_max: float,
    prod_min: float,
    prod_max: float,
    target: float,
    dark_hours: Tuple[int, ...] = (1, 2, 3, 4, 5, 22, 23, 24),
    prod_hours: Tuple[int, ...] = (7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18),
) -> Dict:
    """
    Diagnóstico operacional:
    - "Noite escura": horas em dark_hours devem estar <= dark_max
    - "Janela produtiva": horas em prod_hours idealmente dentro de [prod_min, prod_max]
      (isto é referência visual/consistência; não é regra universal de manejo)
    """
    hv = _get_hour_value_map(df_profile)

    dark_viol = []
    for h in dark_hours:
        if h in hv and hv[h] > dark_max:
            dark_viol.append((h, hv[h]))

    prod_low = []
    prod_high = []
    for h in prod_hours:
        if h in hv:
            if hv[h] < prod_min:
                prod_low.append((h, hv[h]))
            elif hv[h] > prod_max:
                prod_high.append((h, hv[h]))

    problemas: List[str] = []
    if dark_viol:
        problemas.append("vazamento de luz no período escuro")
    if len(prod_low) >= 4:
        problemas.append("luz de produção abaixo da faixa por várias horas")
    if len(prod_high) >= 4:
        problemas.append("luz de produção acima da faixa por várias horas")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = (
            f"Fotoperíodo parece coerente: período escuro ≤ {dark_max:g} lux e janela produtiva está próxima da faixa "
            f"{prod_min:g}–{prod_max:g} lux."
        )
    else:
        parts = []
        if dark_viol:
            horas = ", ".join(str(h) for h, _ in dark_viol[:8])
            parts.append(f"Há luz no período escuro (horas: {horas}).")
        if prod_low:
            horas = ", ".join(str(h) for h, _ in prod_low[:8])
            parts.append(f"Luz baixa na janela produtiva (horas: {horas}).")
        if prod_high:
            horas = ", ".join(str(h) for h, _ in prod_high[:8])
            parts.append(f"Luz alta na janela produtiva (horas: {horas}).")
        resumo = " ".join(parts).strip()

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if dark_viol:
        impacts_aves += [
            "Repouso comprometido (noite não escura) e maior estresse comportamental.",
            "Maior atividade em horários que deveriam ser de descanso.",
        ]
        impacts_producao += [
            "Pior persistência e maior variabilidade da postura ao longo das semanas.",
            "Consumo pode ficar desorganizado (pico de alimentação fora do padrão).",
        ]
        impacts_qualidade += [
            "Risco de piora indireta de qualidade de casca por mudança de rotina alimentar/descanso.",
        ]
        observar += [
            "Luz acendendo fora do horário programado (timer/relé).",
            "Vazamento de luz em cortinas, portas, frestas, iluminação externa.",
            "Sensor recebendo luz de fora (posicionamento/reflexo).",
        ]
        acoes += [
            "Vistoriar vazamento de luz com o galpão em 'noite' (andar com luxímetro/telefone em pontos diferentes).",
            "Revisar temporizadores, relés, luz de serviço e refletores externos.",
            "Garantir 'escuro efetivo' no período de descanso (meta: ≤ limite definido).",
        ]

    if len(prod_low) >= 4:
        impacts_producao += [
            "Pode reduzir estímulo luminoso e afetar uniformidade do lote (dependendo do manejo/linhagem).",
        ]
        observar += [
            "Distribuição de luminárias e sombreamento (uniformidade de luz no piso/altura das aves).",
        ]
        acoes += [
            "Checar uniformidade de lux (vários pontos) e não apenas um sensor fixo.",
            "Se a faixa for realmente o objetivo do seu aviário, ajustar intensidade/dimmers na janela produtiva.",
        ]

    if len(prod_high) >= 4:
        impacts_aves += [
            "Ambiente mais excitável e maior risco de agitação (dependendo de densidade e manejo).",
        ]
        impacts_producao += [
            "Pode aumentar estresse e piorar estabilidade do consumo/rotina.",
        ]
        observar += [
            "Picos fortes por posicionamento do sensor (sensor sob luminária).",
        ]
        acoes += [
            "Rever posicionamento do sensor (altura e distância de luminárias).",
            "Se a faixa for objetivo, reduzir intensidade/picos e estabilizar a curva de luz.",
        ]

    if status == "DENTRO":
        observar += [
            "Confirmar que o sensor mede lux na altura das aves (ou com correção/consistência).",
            "Comparar 2–3 pontos do galpão para validar uniformidade.",
        ]
        acoes += [
            "Manter o mesmo programa de luz e monitorar tendência semanal (evitar mudanças bruscas).",
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
            "dark_viol": dark_viol,
            "prod_low": prod_low,
            "prod_high": prod_high,
            "refs": {"dark_max": dark_max, "prod_min": prod_min, "prod_max": prod_max, "target": target},
        },
    }


# =============================================================================
# 2) MQ135 — perfil por hora (últimos 3 dias)
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
            "Potencial desconforto respiratório/irritação (dependendo do que está contribuindo: amônia/poeira/CO₂).",
            "Maior estresse em períodos de ar pior, com pior repouso/atividade.",
        ]
        impacts_producao += [
            "Pode reduzir consumo em horários críticos e afetar desempenho se virar padrão recorrente.",
            "Maior variabilidade de produção quando o ar pior coincide com horários de maior atividade.",
        ]
        impacts_qualidade += [
            "Impacto indireto possível (via consumo/estresse) na qualidade de casca e uniformidade.",
        ]
        observar += [
            "Rotina de ventilação/inlets no fim da tarde/noite (setpoints e operação real).",
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


# =============================================================================
# 3) TEMPERATURA — média diária (janela)
# =============================================================================
def diagnosticar_temperatura_media_diaria(
    *,
    df_d: pd.DataFrame,
    col: str = "temp_media_d",
    ref_min: float = 18.0,
    ref_max: float = 24.0,
    janela_dias: int = 7,
) -> Dict:
    tmp = df_d.copy() if df_d is not None else pd.DataFrame()
    if tmp.empty or "dt" not in tmp.columns or col not in tmp.columns:
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes para avaliar temperatura média diária.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    tmp = _window_last_days(tmp, "dt", max(int(janela_dias), 1))
    tmp["dt"] = pd.to_datetime(tmp["dt"], errors="coerce")
    tmp[col] = pd.to_numeric(tmp[col], errors="coerce")
    tmp = tmp.dropna(subset=["dt", col]).sort_values("dt")
    if tmp.empty:
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes na janela para avaliar temperatura média diária.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    vals = tmp[col].tolist()
    dates = tmp["dt"].dt.strftime("%d/%m").tolist()

    out_high = [(d, float(v)) for d, v in zip(dates, vals) if v > float(ref_max)]
    out_low = [(d, float(v)) for d, v in zip(dates, vals) if v < float(ref_min)]

    n = len(tmp)
    n_out = len(out_high) + len(out_low)
    mean_v = float(tmp[col].mean())
    max_v = float(tmp[col].max())
    min_v = float(tmp[col].min())

    # streak de fora (dias consecutivos fora)
    tmp["fora"] = (tmp[col] < float(ref_min)) | (tmp[col] > float(ref_max))
    tmp["dia"] = tmp["dt"].dt.normalize()
    tmp = tmp.sort_values("dia")
    streak = 0
    best_streak = 0
    for flag in tmp["fora"].tolist():
        if bool(flag):
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    problemas: List[str] = []
    if n_out > 0:
        problemas.append("dias fora da faixa")
    if best_streak >= 2:
        problemas.append("persistência (≥2 dias consecutivos fora)")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = (
            f"Temperatura média diária está coerente: {n} dia(s) na janela, média {mean_v:.1f} °C, "
            f"dentro da faixa {ref_min:.1f}–{ref_max:.1f} °C."
        )
    else:
        parts = [
            f"{n_out}/{n} dia(s) fora da faixa {ref_min:.1f}–{ref_max:.1f} °C.",
        ]
        if out_high:
            parts.append(f"Acima do máximo em: {', '.join(d for d, _ in out_high[:8])}.")
        if out_low:
            parts.append(f"Abaixo do mínimo em: {', '.join(d for d, _ in out_low[:8])}.")
        if best_streak >= 2:
            parts.append(f"Persistência: {best_streak} dia(s) consecutivos fora.")
        resumo = " ".join(parts).strip()

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if out_high:
        impacts_aves += [
            "Maior carga térmica e risco de estresse térmico, especialmente no período mais quente do dia.",
        ]
        impacts_producao += [
            "Redução de consumo e possível queda de postura quando o padrão se repete por vários dias.",
        ]
        impacts_qualidade += [
            "Risco de piora de casca (indireto via consumo/estresse), com mais variação de peso e qualidade.",
        ]
        observar += [
            "Ventilação real no pico da tarde (setpoint vs entrega).",
            "Uniformidade térmica no galpão (pontos quentes).",
            "Temperatura e disponibilidade de água.",
        ]
        acoes += [
            "Priorizar mitigação no pico do dia: ventilação/velocidade do ar/sombreamento/rotina de manejo.",
            "Validar sensor e posição (altura e ponto do galpão).",
        ]

    if out_low:
        impacts_aves += [
            "Desconforto por frio e maior gasto energético para manutenção.",
        ]
        impacts_producao += [
            "Possível piora de conversão e queda de desempenho se persistente.",
        ]
        observar += [
            "Correntes de ar frio e vedação/cortinas.",
        ]
        acoes += [
            "Revisar vedação e manejo de cortinas/inlets para evitar frio direto nas aves.",
        ]

    if status == "DENTRO":
        observar += [
            "Manter monitoramento para captar tendências (deriva) e dias extremos.",
        ]
        acoes += [
            "Usar esta janela como referência e comparar com a próxima semana.",
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
            "ref_min": float(ref_min),
            "ref_max": float(ref_max),
            "janela_dias": int(janela_dias),
            "n": n,
            "n_out": n_out,
            "mean": mean_v,
            "min": min_v,
            "max": max_v,
            "out_high": out_high,
            "out_low": out_low,
            "best_streak_out": best_streak,
        },
    }


# =============================================================================
# 4) TEMPERATURA — por turno (últimos 3 dias)
# =============================================================================
def diagnosticar_temperatura_por_turno(
    *,
    df_summary: pd.DataFrame,
    ref_min: float = 18.0,
    ref_max: float = 24.0,
) -> Dict:
    if df_summary is None or df_summary.empty or "turno" not in df_summary.columns or "temp_media_turno" not in df_summary.columns:
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes para avaliar temperatura por turno.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    tmp = df_summary.copy()
    tmp["temp_media_turno"] = pd.to_numeric(tmp["temp_media_turno"], errors="coerce")
    tmp = tmp.dropna(subset=["turno", "temp_media_turno"])
    if tmp.empty:
        return {
            "status": "FORA",
            "resumo_curto": "Sem valores válidos para avaliar temperatura por turno.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    too_high = tmp[tmp["temp_media_turno"] > float(ref_max)].sort_values("temp_media_turno", ascending=False)
    too_low = tmp[tmp["temp_media_turno"] < float(ref_min)].sort_values("temp_media_turno", ascending=True)

    worst_row = tmp.sort_values("temp_media_turno", ascending=False).iloc[0]
    worst_turno = str(worst_row["turno"])
    worst_temp = float(worst_row["temp_media_turno"])
    worst_desc = max(0.0, worst_temp - float(ref_max)) if worst_temp > float(ref_max) else max(0.0, float(ref_min) - worst_temp)

    problemas: List[str] = []
    if not too_high.empty or not too_low.empty:
        problemas.append("turnos fora da faixa")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = f"Temperatura por turno está coerente e dentro da faixa {ref_min:.1f}–{ref_max:.1f} °C."
    else:
        parts = [f"Pior turno: {worst_turno} — {worst_temp:.1f} °C."]
        if not too_high.empty:
            parts.append("Acima do máximo em: " + ", ".join(too_high["turno"].astype(str).tolist()) + ".")
        if not too_low.empty:
            parts.append("Abaixo do mínimo em: " + ", ".join(too_low["turno"].astype(str).tolist()) + ".")
        resumo = " ".join(parts).strip()

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if status == "FORA":
        if not too_high.empty:
            impacts_aves += [
                "Maior ofegação e carga térmica nos turnos quentes.",
            ]
            impacts_producao += [
                "Queda de consumo nos turnos quentes e maior risco de queda de postura quando o padrão se repete.",
            ]
            impacts_qualidade += [
                "Risco de piora de casca e variação de peso do ovo (efeito indireto via consumo/estresse).",
            ]
            observar += [
                "Se o pior turno for a Tarde: verificar ventilação/velocidade do ar e sombreamento no pico.",
                "Se o pior turno for a Noite: checar recuperação noturna (calor residual).",
            ]
            acoes += [
                "Ajustar estratégia do turno crítico (normalmente pico da tarde): aumentar troca de ar e velocidade do ar.",
                "Validar uniformidade térmica por pontos do galpão (pontos quentes).",
            기억 ]
        if not too_low.empty:
            observar += [
                "Correntes de ar frio e ajuste de cortinas/inlets.",
            ]
            acoes += [
                "Reduzir corrente de ar direta nas aves e revisar vedação.",
            ]
    else:
        observar += [
            "Manter vigilância em ondas de calor; turno crítico costuma antecipar problemas.",
        ]
        acoes += [
            "Usar este perfil por turno como baseline e comparar semanalmente.",
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
            "ref_min": float(ref_min),
            "ref_max": float(ref_max),
            "worst_turno": worst_turno,
            "worst_temp": worst_temp,
            "worst_desc": worst_desc,
            "turnos_high": too_high[["turno", "temp_media_turno"]].to_dict(orient="records") if not too_high.empty else [],
            "turnos_low": too_low[["turno", "temp_media_turno"]].to_dict(orient="records") if not too_low.empty else [],
        },
    }


# =============================================================================
# 5) THI — por turno (últimos 3 dias)
# =============================================================================
def diagnosticar_thi_por_turno(
    *,
    df_summary_thi: pd.DataFrame,
    thi_min: float = 70.0,
    thi_max: float = 75.0,
) -> Dict:
    if (
        df_summary_thi is None
        or df_summary_thi.empty
        or "turno" not in df_summary_thi.columns
        or "thi_media_turno" not in df_summary_thi.columns
    ):
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes para avaliar THI por turno.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    tmp = df_summary_thi.copy()
    tmp["thi_media_turno"] = pd.to_numeric(tmp["thi_media_turno"], errors="coerce")
    tmp = tmp.dropna(subset=["turno", "thi_media_turno"])
    if tmp.empty:
        return {
            "status": "FORA",
            "resumo_curto": "Sem valores válidos para avaliar THI por turno.",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    too_high = tmp[tmp["thi_media_turno"] > float(thi_max)].sort_values("thi_media_turno", ascending=False)
    too_low = tmp[tmp["thi_media_turno"] < float(thi_min)].sort_values("thi_media_turno", ascending=True)

    worst_row = tmp.sort_values("thi_media_turno", ascending=False).iloc[0]
    worst_turno = str(worst_row["turno"])
    worst_thi = float(worst_row["thi_media_turno"])

    problemas: List[str] = []
    if not too_high.empty or not too_low.empty:
        problemas.append("turnos fora da faixa THI")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = f"THI por turno está coerente e dentro da faixa {thi_min:.1f}–{thi_max:.1f}."
    else:
        parts = [f"Turno mais crítico: {worst_turno} — THI {worst_thi:.1f}."]
        if not too_high.empty:
            parts.append("Acima do máximo em: " + ", ".join(too_high["turno"].astype(str).tolist()) + ".")
        if not too_low.empty:
            parts.append("Abaixo do mínimo em: " + ", ".join(too_low["turno"].astype(str).tolist()) + ".")
        resumo = " ".join(parts).strip()

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if not too_high.empty:
        impacts_aves += [
            "Indício de estresse térmico (THI alto), com maior dificuldade de dissipar calor.",
        ]
        impacts_producao += [
            "Maior risco de queda de consumo e queda de postura se o padrão persistir.",
        ]
        impacts_qualidade += [
            "Risco indireto de piora de casca (via consumo/estresse e alcalose respiratória).",
        ]
        observar += [
            "Umidade no turno crítico (THI sobe muito com umidade).",
            "Velocidade do ar na altura das aves (efeito direto no conforto).",
            "Recuperação noturna (se noite ainda alta, há acúmulo de estresse).",
        ]
        acoes += [
            "Aumentar capacidade de resfriamento efetivo no turno crítico: ventilação, velocidade do ar, estratégia de inlets.",
            "Mitigar fontes de umidade (cama úmida, vazamentos, excesso de nebulização se houver).",
        ]

    if status == "DENTRO":
        observar += [
            "Manter THI como indicador líder para ondas de calor (tende a antecipar queda de desempenho).",
        ]
        acoes += [
            "Guardar este perfil como baseline e comparar semanalmente.",
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
            "thi_min": float(thi_min),
            "thi_max": float(thi_max),
            "worst_turno": worst_turno,
            "worst_thi": worst_thi,
            "turnos_high": too_high[["turno", "thi_media_turno"]].to_dict(orient="records") if not too_high.empty else [],
            "turnos_low": too_low[["turno", "thi_media_turno"]].to_dict(orient="records") if not too_low.empty else [],
        },
    }


# =============================================================================
# 6) HEATMAP dia×turno (temperatura) — diagnóstico simples
# =============================================================================
def diagnosticar_heatmap_temperatura_dia_turno(
    *,
    df_turnos: pd.DataFrame,
    ref_min: float = 18.0,
    ref_max: float = 24.0,
) -> Dict:
    """
    Heurística:
    - conta células (dia×turno) fora da faixa
    - destaca quais turnos mais frequentemente fora
    """
    if (
        df_turnos is None
        or df_turnos.empty
        or "dia" not in df_turnos.columns
        or "turno" not in df_turnos.columns
        or "temp_media_turno" not in df_turnos.columns
    ):
        return {
            "status": "FORA",
            "resumo_curto": "Sem dados suficientes para avaliar heatmap (dia×turno).",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    tmp = df_turnos.copy()
    tmp["dia"] = pd.to_datetime(tmp["dia"], errors="coerce")
    tmp["temp_media_turno"] = pd.to_numeric(tmp["temp_media_turno"], errors="coerce")
    tmp = tmp.dropna(subset=["dia", "turno", "temp_media_turno"])
    if tmp.empty:
        return {
            "status": "FORA",
            "resumo_curto": "Sem valores válidos para avaliar heatmap (dia×turno).",
            "impacts_aves": [],
            "impacts_producao": [],
            "impacts_qualidade": [],
            "observar": [],
            "acoes": [],
            "debug": {},
        }

    tmp["fora"] = (tmp["temp_media_turno"] < float(ref_min)) | (tmp["temp_media_turno"] > float(ref_max))

    total = int(len(tmp))
    out = int(tmp["fora"].sum())

    by_turno = (
        tmp.groupby("turno", as_index=False)["fora"]
        .mean()
        .rename(columns={"fora": "frac_fora"})
        .sort_values("frac_fora", ascending=False)
    )

    turnos_criticos = by_turno[by_turno["frac_fora"] > 0].head(2)["turno"].astype(str).tolist()

    problemas: List[str] = []
    if out > 0:
        problemas.append("células fora da faixa")

    status = "DENTRO" if not problemas else "FORA"

    if status == "DENTRO":
        resumo = f"Heatmap coerente: 0/{total} célula(s) fora da faixa {ref_min:.1f}–{ref_max:.1f} °C."
    else:
        resumo = f"Heatmap indica {out}/{total} célula(s) fora da faixa {ref_min:.1f}–{ref_max:.1f} °C."
        if turnos_criticos:
            resumo += f" Turno(s) mais frequentemente fora: {', '.join(turnos_criticos)}."

    impacts_aves: List[str] = []
    impacts_producao: List[str] = []
    impacts_qualidade: List[str] = []
    observar: List[str] = []
    acoes: List[str] = []

    if status == "FORA":
        impacts_aves += [
            "Confirma padrão de desconforto por turno (sinal de problema sistêmico no ciclo diário).",
        ]
        impacts_producao += [
            "Maior risco de queda de desempenho se o turno crítico se repetir por vários dias.",
        ]
        impacts_qualidade += [
            "Risco indireto de piora de casca e variabilidade (via estresse/consumo).",
        ]
        observar += [
            "Se o turno crítico for a Tarde: capacidade no pico (troca de ar/velocidade do ar/sombreamento).",
            "Se o turno crítico for a Noite: calor residual e recuperação insuficiente.",
        ]
        acoes += [
            "Atacar o turno crítico: ajustar ventilação e estratégia de manejo para reduzir picos.",
            "Validar com medições em múltiplos pontos (uniformidade térmica).",
        ]
    else:
        observar += [
            "Manter heatmap para detectar mudança de padrão (ex.: início de onda de calor).",
        ]
        acoes += [
            "Comparar semanalmente para detectar deriva gradual.",
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
            "ref_min": float(ref_min),
            "ref_max": float(ref_max),
            "total_cells": total,
            "out_cells": out,
            "by_turno": by_turno.to_dict(orient="records"),
        },
    }
