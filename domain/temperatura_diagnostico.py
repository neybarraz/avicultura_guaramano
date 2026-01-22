# =============================================================================
# domain/temperatura_diagnostico.py
# Diagnóstico automático — Temperatura/THI (sem Streamlit)
# Retorno padrão:
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
# =============================================================================

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd


def _to_float(x, default: float = float("nan")) -> float:
    try:
        v = float(x)
        if pd.isna(v):
            return float(default)
        return v
    except Exception:
        return float(default)


def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:
        return ""


def diagnosticar_temperatura_ambiente(
    df_turnos_3d: pd.DataFrame,
    df_summary: pd.DataFrame,
    df_summary_thi: Optional[pd.DataFrame],
    conforto_min: float,
    conforto_max: float,
    thi_min: float,
    thi_max: float,
) -> Dict:
    # Defaults
    out = {
        "status": "DENTRO",
        "resumo_curto": "Sem anomalias detectadas na janela analisada.",
        "impacts_aves": [],
        "impacts_producao": [],
        "impacts_qualidade": [],
        "observar": [],
        "acoes": [],
        "debug": {},
    }

    if df_turnos_3d is None or df_turnos_3d.empty or df_summary is None or df_summary.empty:
        out["status"] = "FORA"
        out["resumo_curto"] = "Diagnóstico indisponível: dados insuficientes para avaliar temperatura por turno."
        out["acoes"] = [
            "Verifique se o arquivo possui registros de temperatura ao longo do dia (mínimo: alguns pontos por turno).",
            "Confirme se a coluna de data/hora está sendo lida corretamente.",
        ]
        return out

    # Pior turno por temperatura
    df_s = df_summary.copy()
    df_s["temp_media_turno"] = pd.to_numeric(df_s.get("temp_media_turno"), errors="coerce")
    df_s["desconforto"] = pd.to_numeric(df_s.get("desconforto"), errors="coerce").fillna(0.0)

    if df_s["desconforto"].gt(0).any():
        worst_row = df_s.sort_values(["desconforto", "temp_media_turno"], ascending=[False, False]).iloc[0]
    else:
        worst_row = df_s.sort_values(["temp_media_turno"], ascending=[False]).iloc[0]

    worst_turno = _safe_str(worst_row.get("turno"))
    worst_temp = _to_float(worst_row.get("temp_media_turno"))
    worst_desc = _to_float(worst_row.get("desconforto"), default=0.0)

    # THI (se disponível)
    thi_available = df_summary_thi is not None and not df_summary_thi.empty and df_summary_thi["thi_media_turno"].notna().any()
    worst_turno_thi = None
    worst_thi = None
    worst_desc_thi = 0.0

    if thi_available:
        df_t = df_summary_thi.copy()
        df_t["thi_media_turno"] = pd.to_numeric(df_t.get("thi_media_turno"), errors="coerce")
        df_t["desconforto_thi"] = pd.to_numeric(df_t.get("desconforto_thi"), errors="coerce").fillna(0.0)

        if df_t["desconforto_thi"].gt(0).any():
            r = df_t.sort_values(["desconforto_thi", "thi_media_turno"], ascending=[False, False]).iloc[0]
        else:
            r = df_t.sort_values(["thi_media_turno"], ascending=[False]).iloc[0]

        worst_turno_thi = _safe_str(r.get("turno"))
        worst_thi = _to_float(r.get("thi_media_turno"))
        worst_desc_thi = _to_float(r.get("desconforto_thi"), default=0.0)

    # Regras de status
    fora_temp = bool(worst_desc > 0)
    fora_thi = bool(thi_available and worst_desc_thi > 0)

    if fora_temp or fora_thi:
        out["status"] = "FORA"

    # Resumo curto
    parts = []
    if fora_temp:
        side = "abaixo" if worst_temp < conforto_min else "acima"
        parts.append(
            f"Temperatura fora da faixa em média no turno da {worst_turno} ({worst_temp:.1f} °C, {side} de {conforto_min:.1f}–{conforto_max:.1f} °C)."
        )
    else:
        parts.append(
            f"Temperatura média por turno dentro da faixa {conforto_min:.1f}–{conforto_max:.1f} °C (pior turno: {worst_turno}, {worst_temp:.1f} °C)."
        )

    if thi_available:
        if fora_thi:
            parts.append(
                f"THI fora da faixa no turno da {worst_turno_thi} (THI {worst_thi:.1f} vs alvo {thi_min:.1f}–{thi_max:.1f})."
            )
        else:
            parts.append("THI médio por turno dentro da faixa definida.")
    else:
        parts.append("THI não avaliado (umidade/RH ausente).")

    out["resumo_curto"] = " ".join(parts)

    # Impactos / observações / ações (heurísticas práticas)
    if fora_temp:
        if worst_temp > conforto_max:
            out["impacts_aves"] += [
                "Maior estresse térmico, aumento de ofegação e consumo de água.",
                "Redução de conforto e piora de bem-estar no turno crítico.",
            ]
            out["impacts_producao"] += [
                "Risco de queda de consumo de ração e redução de produção.",
            ]
            out["impacts_qualidade"] += [
                "Potencial piora de qualidade de casca em condições de calor persistente.",
            ]
            out["acoes"] += [
                "Reforçar ventilação/exaustão e checar velocidade do ar no turno crítico.",
                "Avaliar resfriamento evaporativo/nebulização (se aplicável) e pontos de sombreamento.",
                "Conferir disponibilidade de água (vazão e temperatura).",
            ]
        else:
            out["impacts_aves"] += [
                "Possível desconforto por frio (amontoamento, menor atividade).",
            ]
            out["impacts_producao"] += [
                "Aumento de gasto energético para termorregulação; possível piora de conversão.",
            ]
            out["acoes"] += [
                "Revisar vedação/cortinas e correntes de ar no turno crítico.",
                "Verificar aquecimento (se existir) e ajustes de manejo para reduzir perda térmica.",
            ]

        out["observar"] += [
            "Distribuição das aves (amontoamento ou dispersão excessiva).",
            "Comportamento respiratório (ofegação) e consumo de água.",
            "Oscilação diária: diferenças abruptas entre turnos.",
        ]
    else:
        out["observar"] += [
            "Manter monitoramento do turno de maior média (desempate) para antecipar tendência.",
        ]

    if fora_thi:
        out["impacts_aves"] += [
            "THI elevado aumenta risco de estresse por calor mesmo com temperatura moderada (efeito da umidade).",
        ]
        out["acoes"] += [
            "Se THI alto: priorizar redução de umidade e aumento de troca de ar no turno crítico.",
            "Inspecionar cama/umidade interna e fontes de vapor (vazamentos, bebedouros).",
        ]

    out["debug"] = {
        "conforto_min": float(conforto_min),
        "conforto_max": float(conforto_max),
        "worst_turno_temp": worst_turno,
        "worst_temp_media": float(worst_temp) if not pd.isna(worst_temp) else None,
        "worst_temp_desconforto": float(worst_desc),
        "thi_avaliado": bool(thi_available),
        "thi_min": float(thi_min),
        "thi_max": float(thi_max),
        "worst_turno_thi": worst_turno_thi,
        "worst_thi_media": float(worst_thi) if worst_thi is not None and not pd.isna(worst_thi) else None,
        "worst_thi_desconforto": float(worst_desc_thi),
    }

    return out
