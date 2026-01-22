# =============================================================================
# domain/alimentacao_diagnostico.py
#
# Diagnóstico zootécnico para Alimentação (mistura + consumo)
# - NÃO depende de app.py
# - NÃO importa Streamlit
# - Trabalha com pandas DataFrame já tipado (colunas numéricas + "data" datetime)
#
# Uso típico (na aba tabs/alimentacao.py):
#   from domain.alimentacao_diagnostico import diagnosticar_serie
#   diag = diagnosticar_serie(df, "%_milho", ref_min=55, ref_max=70, janela_dias=7)
#   # diag é um dict com status, severidade, impactos, sinais e ações.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# =============================================================================
# Configuração e utilitários
# =============================================================================

@dataclass(frozen=True)
class SeverityThresholds:
    """
    Severidade baseada no quanto o valor está fora da faixa, em percentual da faixa.

    Exemplo:
      faixa 55–70 => largura 15
      valor 52 => 3 abaixo => 3/15 = 20% (alta, se > 10%).
    """
    leve: float = 0.05       # até 5% da largura da faixa
    moderada: float = 0.10   # 5–10% da largura da faixa
    # acima de moderada => alta


DEFAULT_THRESHOLDS = SeverityThresholds()


def _safe_float(x: Any) -> Optional[float]:
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _normalize_key(col: str) -> str:
    return str(col).strip().lower()


def _compute_status(value: float, ref_min: float, ref_max: float) -> str:
    if value < ref_min:
        return "ABAIXO"
    if value > ref_max:
        return "ACIMA"
    return "DENTRO"


def _out_of_range_distance(value: float, ref_min: float, ref_max: float) -> float:
    """
    Distância absoluta até a faixa. Se dentro, retorna 0.
    """
    if value < ref_min:
        return ref_min - value
    if value > ref_max:
        return value - ref_max
    return 0.0


def _severity_from_distance(distance: float, ref_min: float, ref_max: float, thr: SeverityThresholds) -> str:
    """
    Severidade baseada na distância fora da faixa, normalizada pela largura da faixa.
    """
    width = float(ref_max - ref_min)
    if width <= 0:
        # Faixa inválida -> não dá para graduar com confiança
        return "indefinida"

    ratio = distance / width  # fração da largura da faixa

    if ratio <= 0:
        return "ok"
    if ratio <= thr.leve:
        return "leve"
    if ratio <= thr.moderada:
        return "moderada"
    return "alta"


def _trend_label(last: float, mean_janela: float, tol: float = 1e-9) -> str:
    """
    Rótulo simples de tendência: acima / abaixo / estável vs média.
    """
    if abs(last - mean_janela) <= tol:
        return "estável"
    return "subindo" if last > mean_janela else "caindo"


def _get_window(df: pd.DataFrame, col: str, janela_dias: int) -> pd.DataFrame:
    """
    Retorna as últimas N linhas válidas (preferência por 'data' se existir).
    Não filtra por data corrido; usa "últimos registros" para robustez.
    """
    if df is None or df.empty or col not in df.columns:
        return pd.DataFrame()

    tmp = df.copy()
    if "data" in tmp.columns:
        tmp = tmp.sort_values("data")
    tmp = tmp.dropna(subset=[col])
    if tmp.empty:
        return tmp

    return tmp.tail(int(janela_dias))


# =============================================================================
# Regras zootécnicas (mensagens por variável)
# =============================================================================

def _rules_consumo() -> Dict[str, Dict[str, List[str]]]:
    return {
        "ABAIXO": {
            "aves": [
                "Maior risco de déficit energético/proteico e pior uniformidade do lote.",
                "Possível aumento de estresse/competição se houver restrição no comedouro.",
            ],
            "producao": [
                "Tendência de queda de postura e/ou redução de massa de ovo ao longo de dias.",
                "Maior variabilidade de desempenho e pior previsibilidade do lote.",
            ],
            "qualidade": [
                "Pode piorar casca indiretamente por menor ingestão total de cálcio e nutrientes.",
            ],
            "observar": [
                "Água (vazão/qualidade), falhas de fornecimento, sobra/ausência de ração no comedouro.",
                "Temperatura/estresse térmico e densidade/competição no acesso ao alimento.",
            ],
            "acoes": [
                "Verificar oferta de ração e rotina de trato; checar água e conforto térmico.",
                "Confirmar formulação e granulometria (palatabilidade).",
            ],
        },
        "DENTRO": {
            "aves": [
                "Ingestão adequada para manutenção e suporte à postura.",
                "Maior estabilidade metabólica e menor oscilação de desempenho.",
            ],
            "producao": [
                "Maior estabilidade de produção e melhor eficiência econômica esperada.",
            ],
            "qualidade": [
                "Condição favorável para manter padrão de casca e tamanho de ovo.",
            ],
            "observar": [
                "Manter rotina; monitorar tendências (média 7 dias) para antecipar desvios.",
            ],
            "acoes": [
                "Manter parâmetros; agir apenas se houver tendência consistente de desvio.",
            ],
        },
        "ACIMA": {
            "aves": [
                "Risco de ganho de peso e pior uniformidade se o excesso persistir.",
                "Possível aumento de excreta úmida se houver desequilíbrio nutricional.",
            ],
            "producao": [
                "Nem sempre melhora postura; pode reduzir eficiência e elevar custo por ovo.",
            ],
            "qualidade": [
                "Pode aumentar tamanho de ovo e, dependendo do cálcio, predispor casca relativamente mais frágil.",
            ],
            "observar": [
                "Condição corporal/peso, sobra de ração, comportamento e consistência de cama/excretas.",
            ],
            "acoes": [
                "Revisar densidade energética da dieta e rotina de trato.",
                "Checar se o consumo está alto por frio/condição ambiental (ajuste de manejo).",
            ],
        },
    }


def _rules_milho() -> Dict[str, Dict[str, List[str]]]:
    return {
        "ABAIXO": {
            "aves": [
                "Energia dietética possivelmente insuficiente; aves podem tentar compensar com maior consumo.",
            ],
            "producao": [
                "Risco de queda gradual de postura e/ou ovos menores se não houver compensação de energia.",
            ],
            "qualidade": [
                "Maior variabilidade de desempenho por instabilidade energética.",
            ],
            "observar": [
                "Consumo diário: sobe para compensar ou cai por palatabilidade/ambiente.",
            ],
            "acoes": [
                "Revisar formulação para energia metabolizável e consistência de mistura.",
            ],
        },
        "DENTRO": {
            "aves": [
                "Perfil energético mais consistente para a fase, favorecendo estabilidade.",
            ],
            "producao": [
                "Maior previsibilidade de postura e massa de ovo.",
            ],
            "qualidade": [
                "Base favorável para estabilidade de desempenho.",
            ],
            "observar": [
                "Manter controle de variação lote a lote (matéria-prima).",
            ],
            "acoes": [
                "Manter padrão; auditar matéria-prima e moagem periodicamente.",
            ],
        },
        "ACIMA": {
            "aves": [
                "Excesso de energia pode predispor a ganho de peso ao longo do tempo.",
            ],
            "producao": [
                "Pode reduzir eficiência alimentar; custo por ovo tende a subir se persistente.",
            ],
            "qualidade": [
                "Dependendo do balanço mineral, ovos maiores podem exigir maior atenção à casca.",
            ],
            "observar": [
                "Peso corporal, uniformidade e consumo (pode cair por densidade energética alta).",
            ],
            "acoes": [
                "Rebalancear energia vs proteína/aminoácidos e minerais para evitar 'diluição' de nutrientes.",
            ],
        },
    }


def _rules_soja() -> Dict[str, Dict[str, List[str]]]:
    return {
        "ABAIXO": {
            "aves": [
                "Possível déficit de proteína/aminoácidos essenciais (ex.: lisina, metionina).",
                "Piora de plumagem e condição geral pode ocorrer ao longo de semanas.",
            ],
            "producao": [
                "Risco de redução de massa de ovo e queda de postura.",
            ],
            "qualidade": [
                "Maior risco de ovos menores e variabilidade de lote.",
            ],
            "observar": [
                "Tamanho do ovo e persistência de postura; uniformidade do lote.",
            ],
            "acoes": [
                "Revisar níveis de proteína e aminoácidos (metionina/cistina, lisina).",
            ],
        },
        "DENTRO": {
            "aves": [
                "Suporte adequado para manutenção e produção.",
            ],
            "producao": [
                "Melhor estabilidade de massa de ovo e produção.",
            ],
            "qualidade": [
                "Menor risco de variações por deficiência proteica.",
            ],
            "observar": [
                "Manter monitoramento de peso e massa de ovo para ajustes finos.",
            ],
            "acoes": [
                "Manter padrão e ajustar apenas conforme fase/idade das aves.",
            ],
        },
        "ACIMA": {
            "aves": [
                "Excesso proteico pode aumentar excreção de nitrogênio e amônia ao longo do tempo.",
            ],
            "producao": [
                "Ganho de desempenho pode não compensar o custo adicional.",
            ],
            "qualidade": [
                "Ambiente pode piorar (cama mais úmida/amônia) dependendo do manejo.",
            ],
            "observar": [
                "Umidade de cama, odor/amônia e qualidade do ar.",
            ],
            "acoes": [
                "Otimizar proteína com foco em aminoácidos digestíveis (reduz desperdício).",
            ],
        },
    }


def _rules_calcario() -> Dict[str, Dict[str, List[str]]]:
    return {
        "ABAIXO": {
            "aves": [
                "Maior risco de déficit de cálcio disponível e maior mobilização óssea.",
            ],
            "producao": [
                "Pode aumentar perdas por quebra e reduzir aproveitamento de produção.",
            ],
            "qualidade": [
                "Piora de casca (ovos finos/quebradiços) tende a aparecer se persistente.",
            ],
            "observar": [
                "Aumento de ovos quebrados/trincados; efeito pode ser mais forte em aves mais velhas.",
            ],
            "acoes": [
                "Revisar teor e granulometria do calcário (partícula grossa ajuda oferta noturna).",
                "Checar vitamina D3 e balanço Ca:P conforme núcleo.",
            ],
        },
        "DENTRO": {
            "aves": [
                "Oferta adequada de cálcio para suporte à casca e manutenção.",
            ],
            "producao": [
                "Menor perda por quebra e melhor regularidade.",
            ],
            "qualidade": [
                "Casca tende a ser mais consistente.",
            ],
            "observar": [
                "Manter monitoramento de quebra e deformidades como indicadores precoces.",
            ],
            "acoes": [
                "Manter padrão; ajustar conforme idade (demanda de Ca aumenta com a idade).",
            ],
        },
        "ACIMA": {
            "aves": [
                "Excesso pode interferir na absorção de outros minerais e reduzir palatabilidade em alguns cenários.",
            ],
            "producao": [
                "Benefício adicional pode ser limitado; custo e risco de desequilíbrio aumentam.",
            ],
            "qualidade": [
                "Pode melhorar casca até certo ponto, mas excesso não é garantia de melhora contínua.",
            ],
            "observar": [
                "Consumo total, consistência de excretas e sinais de desbalanceamento mineral.",
            ],
            "acoes": [
                "Revisar balanço mineral (Ca:P) e adequação do núcleo; ajustar granulometria.",
            ],
        },
    }


def _rules_nucleo() -> Dict[str, Dict[str, List[str]]]:
    return {
        "ABAIXO": {
            "aves": [
                "Risco de deficiência de vitaminas/minerais (ex.: D3, Mn, Zn), com impacto sistêmico.",
                "Maior vulnerabilidade metabólica e possível piora de imunocompetência.",
            ],
            "producao": [
                "Aumento de variabilidade e problemas inespecíficos (produção/qualidade) ao longo do tempo.",
            ],
            "qualidade": [
                "Pode afetar casca e qualidade interna por deficiência de micronutrientes.",
            ],
            "observar": [
                "Piora gradual de casca, uniformidade e sinais gerais (plumagem/viço).",
            ],
            "acoes": [
                "Restabelecer nível de núcleo conforme recomendação do fornecedor e fase do lote.",
            ],
        },
        "DENTRO": {
            "aves": [
                "Cobertura adequada de micronutrientes, reduzindo risco de deficiência.",
            ],
            "producao": [
                "Maior estabilidade e menor risco de problemas metabólicos por carência.",
            ],
            "qualidade": [
                "Ambiente nutricional mais estável para qualidade de ovo.",
            ],
            "observar": [
                "Manter auditoria de mistura e homogeneidade.",
            ],
            "acoes": [
                "Manter padrão e acompanhar recomendações do núcleo por fase/idade.",
            ],
        },
        "ACIMA": {
            "aves": [
                "Em geral aumenta custo; dependendo do núcleo, pode elevar risco de excesso de alguns minerais.",
            ],
            "producao": [
                "Ganho de desempenho pode ser marginal em relação ao custo.",
            ],
            "qualidade": [
                "Efeitos variam conforme composição; foco deve ser evitar desequilíbrio.",
            ],
            "observar": [
                "Consistência de mistura e aderência à formulação alvo.",
            ],
            "acoes": [
                "Revisar dosagem e calibrar balança/misturador; manter dentro do recomendado.",
            ],
        },
    }


def _rules_for_column(col: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Resolve regras por coluna.
    """
    key = _normalize_key(col)

    if key in ("consumo_g_ave_dia", "consumo"):
        return _rules_consumo()
    if key in ("%_milho", "milho_pct", "milho"):
        return _rules_milho()
    if key in ("%_soja", "farelo_soja_pct", "soja"):
        return _rules_soja()
    if key in ("%_calcario", "calcario_pct", "calcario"):
        return _rules_calcario()
    if key in ("%_nucleo", "nucleo_pct", "nucleo"):
        return _rules_nucleo()

    # fallback genérico
    return {
        "ABAIXO": {
            "aves": ["Valor abaixo do alvo; pode indicar desequilíbrio na formulação ou mistura."],
            "producao": ["Risco de impacto em desempenho se persistente."],
            "qualidade": ["Risco de variabilidade de lote e/ou qualidade."],
            "observar": ["Checar consistência de mistura, pesagem e matéria-prima."],
            "acoes": ["Revisar processo e retornar ao alvo."],
        },
        "DENTRO": {
            "aves": ["Dentro do alvo; tende a favorecer estabilidade."],
            "producao": ["Menor risco de oscilação por esta variável."],
            "qualidade": ["Condição favorável para manter padrão."],
            "observar": ["Monitorar tendência e consistência do processo."],
            "acoes": ["Manter padrão."],
        },
        "ACIMA": {
            "aves": ["Valor acima do alvo; pode indicar desequilíbrio na formulação ou mistura."],
            "producao": ["Pode reduzir eficiência e elevar custo se persistente."],
            "qualidade": ["Efeitos variam; monitorar indicadores de qualidade."],
            "observar": ["Checar consistência de mistura, pesagem e matéria-prima."],
            "acoes": ["Revisar processo e retornar ao alvo."],
        },
    }


# =============================================================================
# API pública
# =============================================================================

def diagnosticar_serie(
    df: pd.DataFrame,
    col: str,
    *,
    ref_min: float,
    ref_max: float,
    janela_dias: int = 7,
    thresholds: SeverityThresholds = DEFAULT_THRESHOLDS,
) -> Dict[str, Any]:
    """
    Produz um diagnóstico estruturado (sem Streamlit) para a série 'col'.

    Retorna dict com chaves:
      - col, ref_min, ref_max, janela_dias
      - last_date (se houver), last_value, mean_window, trend
      - status: ABAIXO/DENTRO/ACIMA
      - severity: ok/leve/moderada/alta/indefinida
      - distance_out_of_range
      - textos: impacts_aves, impacts_producao, impacts_qualidade, observar, acoes
      - resumo_curto: frase pronta
    """
    out: Dict[str, Any] = {
        "col": col,
        "ref_min": float(ref_min),
        "ref_max": float(ref_max),
        "janela_dias": int(janela_dias),
        "last_date": None,
        "last_value": None,
        "mean_window": None,
        "trend": None,
        "status": "Sem dados",
        "severity": "indefinida",
        "distance_out_of_range": None,
        "impacts_aves": [],
        "impacts_producao": [],
        "impacts_qualidade": [],
        "observar": [],
        "acoes": [],
        "resumo_curto": "Sem dados suficientes para diagnóstico.",
    }

    if df is None or df.empty or col not in df.columns:
        return out

    window = _get_window(df, col, janela_dias)
    if window.empty:
        return out

    # ordenar por data quando disponível (para last_date)
    if "data" in window.columns:
        window = window.sort_values("data")

    last_row = window.iloc[-1]
    last_value = _safe_float(last_row.get(col))
    if last_value is None:
        return out

    mean_window = _safe_float(window[col].mean())
    if mean_window is None:
        mean_window = last_value

    last_date = None
    if "data" in window.columns:
        try:
            dt = last_row.get("data")
            if pd.notna(dt):
                last_date = pd.to_datetime(dt).to_pydatetime()
        except Exception:
            last_date = None

    status = _compute_status(last_value, float(ref_min), float(ref_max))
    dist = _out_of_range_distance(last_value, float(ref_min), float(ref_max))
    severity = _severity_from_distance(dist, float(ref_min), float(ref_max), thresholds)
    trend = _trend_label(last_value, mean_window)

    rules = _rules_for_column(col)
    msg = rules.get(status, {})

    impacts_aves = msg.get("aves", [])
    impacts_producao = msg.get("producao", [])
    impacts_qualidade = msg.get("qualidade", [])
    observar = msg.get("observar", [])
    acoes = msg.get("acoes", [])

    # resumo curto (pronto para UI)
    ref_txt = f"{float(ref_min):.1f}–{float(ref_max):.1f}"
    resumo_curto = (
        f"{status} ({severity}). Último={last_value:.1f}; "
        f"média{janela_dias}={mean_window:.1f}; tendência={trend}; ref={ref_txt}."
    )

    out.update(
        {
            "last_date": last_date,
            "last_value": float(last_value),
            "mean_window": float(mean_window),
            "trend": trend,
            "status": status,
            "severity": severity,
            "distance_out_of_range": float(dist),
            "impacts_aves": list(impacts_aves),
            "impacts_producao": list(impacts_producao),
            "impacts_qualidade": list(impacts_qualidade),
            "observar": list(observar),
            "acoes": list(acoes),
            "resumo_curto": resumo_curto,
        }
    )

    return out


def formatar_diagnostico_markdown(diag: Dict[str, Any]) -> str:
    """
    Helper opcional: transforma o dict do diagnóstico em Markdown (para Streamlit).
    Mantém o módulo sem dependência de Streamlit; apenas retorna string.
    """
    if not diag or diag.get("status") == "Sem dados":
        return "Sem dados suficientes para diagnóstico."

    lines: List[str] = []
    lines.append(diag.get("resumo_curto", "").strip())

    def _section(title: str, items: List[str]) -> None:
        if not items:
            return
        lines.append("")
        lines.append(f"**{title}**")
        for it in items:
            lines.append(f"- {it}")

    _section("Impacto provável nas aves", diag.get("impacts_aves", []))
    _section("Impacto provável na produção", diag.get("impacts_producao", []))
    _section("Impacto provável na qualidade do ovo", diag.get("impacts_qualidade", []))
    _section("O que observar", diag.get("observar", []))
    _section("Ações sugeridas", diag.get("acoes", []))

    return "\n".join(lines)
