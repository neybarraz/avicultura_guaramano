# =============================================================================
# domain/iluminacao_diagnostico.py
# Diagnóstico operacional de iluminação por hora (perfil dos últimos 3 dias)
# Convenção de retorno: igual demais diagnósticos do projeto
# =============================================================================

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd


# -----------------------------------------------------------------------------
# Convenção de retorno:
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
        h = int(r["hora"])
        out[h] = float(r["media"])
    return out


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
      (referência visual/consistência; ajuste conforme seu programa de luz)
    """
    hv = _get_hour_value_map(df_profile)

    dark_viol: List[Tuple[int, float]] = []
    for h in dark_hours:
        if h in hv and hv[h] > float(dark_max):
            dark_viol.append((h, float(hv[h])))

    prod_low: List[Tuple[int, float]] = []
    prod_high: List[Tuple[int, float]] = []
    for h in prod_hours:
        if h in hv:
            v = float(hv[h])
            if v < float(prod_min):
                prod_low.append((h, v))
            elif v > float(prod_max):
                prod_high.append((h, v))

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
            f"Fotoperíodo parece coerente: período escuro ≤ {float(dark_max):g} lux e janela produtiva próxima da faixa "
            f"{float(prod_min):g}–{float(prod_max):g} lux."
        )
    else:
        parts: List[str] = []
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
            "Risco indireto de piora de qualidade de casca por mudança de rotina alimentar/descanso.",
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
            "Confirmar que o sensor mede lux na altura das aves (ou usar correção/consistência).",
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
            "refs": {
                "dark_max": float(dark_max),
                "prod_min": float(prod_min),
                "prod_max": float(prod_max),
                "target": float(target),
                "dark_hours": list(dark_hours),
                "prod_hours": list(prod_hours),
            },
        },
    }
