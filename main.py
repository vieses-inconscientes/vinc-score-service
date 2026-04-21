from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(
    title="vinc-score-service",
    version="2.0.0",
    description="Serviço inicial de validação, completude e score base do V'inC.",
)

BLOCKS = [f"B{i}" for i in range(1, 7)]
UNITS_PER_BLOCK = 6


# =========================================================
# MODELOS DE ENTRADA
# =========================================================

class UnitPayload(BaseModel):
    polo_escolhido: Optional[Literal["A", "B"]] = None
    valor_likert_nao_escolhido: Optional[int] = Field(default=None, ge=1, le=5)


class ScoreRequest(BaseModel):
    submission_id: str
    instrument_version: str
    methodology_version: str
    submitted_at: str
    source: str
    status: str
    form: Dict[str, Any] = Field(default_factory=dict)
    entry: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)
    normalized: Dict[str, UnitPayload]


# =========================================================
# MATRIZ TÉCNICA
# =========================================================

class MatrixEntry(BaseModel):
    block: str
    label: str
    weight: float = 1.0
    pole_A_direction: Optional[int] = None
    pole_B_direction: Optional[int] = None
    notes: Optional[str] = None


def build_placeholder_matrix() -> Dict[str, MatrixEntry]:
    matrix: Dict[str, MatrixEntry] = {}

    for b in range(1, 7):
        for u in range(1, 7):
            unit_key = f"B{b}_U{u}"
            matrix[unit_key] = MatrixEntry(
                block=f"B{b}",
                label=f"Placeholder {unit_key}",
                weight=1.0,
                pole_A_direction=None,
                pole_B_direction=None,
                notes="Direção ainda não definida na matriz técnica.",
            )

    return matrix


SCORING_MATRIX: Dict[str, MatrixEntry] = build_placeholder_matrix()

SCORING_MATRIX.update({
    "B1_U1": MatrixEntry(
        block="B1",
        label="Perfeccionismo e autoexigência",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = perfeccionismo normativo / autoexigência elevada. "
            "Polo B = excelência flexível. "
            "Maior rigidez autoavaliativa no polo A."
        ),
    ),
    "B1_U2": MatrixEntry(
        block="B1",
        label="Descanso condicionado ao merecimento",
        weight=1.0,
        pole_A_direction=-1,
        pole_B_direction=+1,
        notes=(
            "Polo A = descanso integrado à produtividade. "
            "Polo B = descanso condicionado ao dever concluído. "
            "Maior produtivismo internalizado no polo B."
        ),
    ),
    "B1_U3": MatrixEntry(
        block="B1",
        label="Valorização do sofrimento como via de crescimento",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = sofrimento formador / mérito via dor. "
            "Polo B = desenvolvimento sem glorificação do sofrimento. "
            "Maior romantização da dor no polo A."
        ),
    ),
    "B1_U4": MatrixEntry(
        block="B1",
        label="Autodisciplina com ou sem sacrifício do bem-estar",
        weight=1.0,
        pole_A_direction=-1,
        pole_B_direction=+1,
        notes=(
            "Polo A = disciplina integrada ao bem-estar. "
            "Polo B = disciplina punitiva e sacrificial. "
            "Maior endurecimento e autoimposição rígida no polo B."
        ),
    ),
    "B1_U5": MatrixEntry(
        block="B1",
        label="Reconhecimento de conquistas e suficiência subjetiva",
        weight=1.0,
        pole_A_direction=-1,
        pole_B_direction=+1,
        notes=(
            "Polo A = reconhecimento realista de conquistas. "
            "Polo B = insuficiência crônica percebida. "
            "Maior invalidação de progresso e autodesqualificação no polo B."
        ),
    ),
    "B1_U6": MatrixEntry(
        block="B1",
        label="Crescimento sem cobrança permanente",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = cobrança permanente de melhoria. "
            "Polo B = crescimento sem pressão crônica. "
            "Maior mandato interno de aperfeiçoamento contínuo no polo A."
        ),
    ),
})

SCORING_MATRIX.update({
    "B2_U1": MatrixEntry(
        block="B2",
        label="Necessidade de aprovação",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = aprovação indispensável. "
            "Polo B = autovalidação suficiente. "
            "Maior dependência de aprovação externa no polo A."
        ),
    ),
    "B2_U2": MatrixEntry(
        block="B2",
        label="Comparação social como referência central",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = comparação frequente como guia. "
            "Polo B = referência interna mais estável. "
            "Maior autoavaliação baseada em contraste social no polo A."
        ),
    ),
    "B2_U3": MatrixEntry(
        block="B2",
        label="Medo de desapontar expectativas",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = medo de desapontar os outros. "
            "Polo B = liberdade relativa diante de expectativas. "
            "Maior conformidade por medo de decepcionar no polo A."
        ),
    ),
    "B2_U4": MatrixEntry(
        block="B2",
        label="Imagem social e necessidade de boa impressão",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = boa impressão como necessidade. "
            "Polo B = autenticidade com menor dependência de imagem. "
            "Maior hipervigilância reputacional no polo A."
        ),
    ),
    "B2_U5": MatrixEntry(
        block="B2",
        label="Dificuldade de sustentar discordância",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = cede para evitar desaprovação. "
            "Polo B = sustenta discordância com regulação. "
            "Maior dificuldade de diferenciação interpessoal no polo A."
        ),
    ),
    "B2_U6": MatrixEntry(
        block="B2",
        label="Reconhecimento externo como prova de valor",
        weight=1.0,
        pole_A_direction=+1,
        pole_B_direction=-1,
        notes=(
            "Polo A = valor confirmado por reconhecimento. "
            "Polo B = valor não dependente de visibilidade. "
            "Maior dependência de elogio, destaque e confirmação externa no polo A."
        ),
    ),
})


# =========================================================
# HELPERS
# =========================================================

def expected_unit_keys() -> List[str]:
    return [f"B{b}_U{u}" for b in range(1, 7) for u in range(1, 7)]


def unit_is_complete(unit: Optional[UnitPayload]) -> bool:
    if unit is None:
        return False
    return (
        unit.polo_escolhido is not None
        and unit.valor_likert_nao_escolhido is not None
    )


def matrix_entry_is_defined(entry: MatrixEntry) -> bool:
    return (
        entry.pole_A_direction in (-1, 1)
        and entry.pole_B_direction in (-1, 1)
    )


def chosen_direction(unit: UnitPayload, entry: MatrixEntry) -> Optional[int]:
    if unit.polo_escolhido == "A":
        return entry.pole_A_direction
    if unit.polo_escolhido == "B":
        return entry.pole_B_direction
    return None


def compute_classification_stub(weighted_mean: Optional[float]) -> Optional[str]:
    if weighted_mean is None:
        return None

    if weighted_mean <= -2.5:
        return "faixa_flexibilidade_elevada_provisoria"
    if weighted_mean < -0.5:
        return "faixa_flexibilidade_moderada_provisoria"
    if weighted_mean <= 0.5:
        return "faixa_neutra_provisoria"
    if weighted_mean < 2.5:
        return "faixa_rigidez_moderada_provisoria"
    return "faixa_rigidez_elevada_provisoria"


def compute_matrix_status() -> str:
    total = len(SCORING_MATRIX)
    defined = sum(
        1 for entry in SCORING_MATRIX.values()
        if matrix_entry_is_defined(entry)
    )

    if defined == 0:
        return "placeholder_pending_scientific_key"
    if defined < total:
        return "partial_real_matrix"
    return "real_matrix_complete"


def analyze_unit(unit_key: str, payload_unit: Optional[UnitPayload]) -> Dict[str, Any]:
    entry = SCORING_MATRIX[unit_key]

    if payload_unit is None:
        return {
            "unit_key": unit_key,
            "block": entry.block,
            "label": entry.label,
            "weight": entry.weight,
            "chosen_pole": None,
            "nonchosen_likert": None,
            "completeness_status": "missing",
            "score_status": "not_scored",
            "direction_used": None,
            "raw_directional_score": None,
            "weighted_score": None,
            "notes": ["Unidade ausente na submissão."],
        }

    if not unit_is_complete(payload_unit):
        return {
            "unit_key": unit_key,
            "block": entry.block,
            "label": entry.label,
            "weight": entry.weight,
            "chosen_pole": payload_unit.polo_escolhido,
            "nonchosen_likert": payload_unit.valor_likert_nao_escolhido,
            "completeness_status": "incomplete",
            "score_status": "not_scored",
            "direction_used": None,
            "raw_directional_score": None,
            "weighted_score": None,
            "notes": ["Unidade presente, mas incompleta."],
        }

    if not matrix_entry_is_defined(entry):
        return {
            "unit_key": unit_key,
            "block": entry.block,
            "label": entry.label,
            "weight": entry.weight,
            "chosen_pole": payload_unit.polo_escolhido,
            "nonchosen_likert": payload_unit.valor_likert_nao_escolhido,
            "completeness_status": "complete",
            "score_status": "matrix_pending",
            "direction_used": None,
            "raw_directional_score": None,
            "weighted_score": None,
            "notes": ["Direções A/B ainda não definidas na matriz técnica."],
        }

    direction = chosen_direction(payload_unit, entry)
    likert_value = payload_unit.valor_likert_nao_escolhido or 0
    raw_directional_score = direction * likert_value
    weighted_score = round(raw_directional_score * entry.weight, 4)

    return {
        "unit_key": unit_key,
        "block": entry.block,
        "label": entry.label,
        "weight": entry.weight,
        "chosen_pole": payload_unit.polo_escolhido,
        "nonchosen_likert": payload_unit.valor_likert_nao_escolhido,
        "completeness_status": "complete",
        "score_status": "scored",
        "direction_used": direction,
        "raw_directional_score": raw_directional_score,
        "weighted_score": weighted_score,
        "notes": [],
    }


def summarize_block(block: str, unit_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    block_units = [
        result for result in unit_results.values()
        if result["block"] == block
    ]

    units_expected = UNITS_PER_BLOCK
    units_complete = sum(
        1 for item in block_units
        if item["completeness_status"] == "complete"
    )
    units_scored = sum(
        1 for item in block_units
        if item["score_status"] == "scored"
    )

    missing_units = [
        item["unit_key"] for item in block_units
        if item["completeness_status"] != "complete"
    ]

    scored_values = [
        item["weighted_score"] for item in block_units
        if item["weighted_score"] is not None
    ]

    weighted_sum = round(sum(scored_values), 4) if scored_values else None
    weighted_mean = (
        round(sum(scored_values) / len(scored_values), 4)
        if scored_values else None
    )

    completeness_percent = round((units_complete / units_expected) * 100, 2)
    scoreable_percent = round((units_scored / units_expected) * 100, 2)

    return {
        "block": block,
        "units_expected": units_expected,
        "units_complete": units_complete,
        "units_scored": units_scored,
        "units_missing": len(missing_units),
        "missing_units": missing_units,
        "completeness_percent": completeness_percent,
        "scoreable_percent": scoreable_percent,
        "weighted_sum": weighted_sum,
        "weighted_mean": weighted_mean,
    }


def build_flags(
    payload: ScoreRequest,
    total_units_complete: int,
    total_units_scored: int,
    total_units_expected: int,
) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []

    if payload.status.lower() != "completed":
        flags.append({
            "code": "status_not_completed",
            "severity": "medium",
            "message": "O status recebido não é 'completed'.",
        })

    if total_units_complete < total_units_expected:
        flags.append({
            "code": "partial_submission",
            "severity": "medium",
            "message": "A submissão está incompleta.",
        })

    if total_units_scored == 0:
        flags.append({
            "code": "matrix_pending",
            "severity": "info",
            "message": "Nenhuma unidade foi pontuada porque a matriz técnica ainda não está definida.",
        })

    if total_units_complete > 0 and total_units_scored < total_units_complete:
        flags.append({
            "code": "complete_but_not_scored",
            "severity": "info",
            "message": "Há unidades completas, mas ainda não pontuáveis por falta de direção técnica.",
        })

    return flags


# =========================================================
# ROTAS
# =========================================================

@app.get("/")
def root() -> Dict[str, str]:
    return {
        "service": "vinc-score-service",
        "status": "running",
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "vinc-score-service",
    }


@app.post("/score")
def score(payload: ScoreRequest) -> Dict[str, Any]:
    expected_keys = expected_unit_keys()

    unit_results: Dict[str, Dict[str, Any]] = {}
    for unit_key in expected_keys:
        payload_unit = payload.normalized.get(unit_key)
        unit_results[unit_key] = analyze_unit(unit_key, payload_unit)

    total_units_expected = len(expected_keys)
    total_units_received = len(payload.normalized)
    total_units_complete = sum(
        1 for unit in unit_results.values()
        if unit["completeness_status"] == "complete"
    )
    total_units_scored = sum(
        1 for unit in unit_results.values()
        if unit["score_status"] == "scored"
    )

    missing_units = [
        unit["unit_key"] for unit in unit_results.values()
        if unit["completeness_status"] != "complete"
    ]

    scored_values = [
        unit["weighted_score"] for unit in unit_results.values()
        if unit["weighted_score"] is not None
    ]

    global_weighted_sum = round(sum(scored_values), 4) if scored_values else None
    global_weighted_mean = (
        round(sum(scored_values) / len(scored_values), 4)
        if scored_values else None
    )
    classification_stub = compute_classification_stub(global_weighted_mean)

    completeness_percent = round((total_units_complete / total_units_expected) * 100, 2)
    scored_percent = round((total_units_scored / total_units_expected) * 100, 2)

    block_scores: Dict[str, Any] = {
        block: summarize_block(block, unit_results)
        for block in BLOCKS
    }

    flags = build_flags(
        payload=payload,
        total_units_complete=total_units_complete,
        total_units_scored=total_units_scored,
        total_units_expected=total_units_expected,
    )

    return {
        "submission_id": payload.submission_id,
        "instrument_version": payload.instrument_version,
        "methodology_version": payload.methodology_version,
        "algorithm_version": "score_v2_base_0_1_0",
        "status": "accepted",
        "matrix_status": compute_matrix_status(),
        "completeness": {
            "units_expected": total_units_expected,
            "units_received": total_units_received,
            "units_complete": total_units_complete,
            "units_missing": len(missing_units),
            "missing_units": missing_units,
            "completeness_percent": completeness_percent,
            "can_score_fully": total_units_complete == total_units_expected,
        },
        "global_score": {
            "units_scored": total_units_scored,
            "scoreable_percent": scored_percent,
            "weighted_sum": global_weighted_sum,
            "weighted_mean": global_weighted_mean,
            "classification_stub": classification_stub,
        },
        "block_scores": block_scores,
        "unit_results": unit_results,
        "flags": flags,
        "next_step": (
            "Continuar preenchimento da matriz técnica real: direção A/B, pesos, "
            "interpretação e pontos de corte."
        ),
    }
