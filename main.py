from typing import Any, Dict, Literal, Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(
    title="vinc-score-service",
    version="1.0.0",
    description="Serviço inicial de validação e preparação de score do V'inC."
)


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


def unit_is_complete(unit: UnitPayload) -> bool:
    return (
        unit.polo_escolhido is not None
        and unit.valor_likert_nao_escolhido is not None
    )


def list_missing_units(normalized: Dict[str, UnitPayload]) -> list[str]:
    missing = []
    for key, unit in normalized.items():
        if not unit_is_complete(unit):
            missing.append(key)
    return missing


def summarize_blocks(normalized: Dict[str, UnitPayload]) -> Dict[str, Dict[str, Any]]:
    blocks: Dict[str, Dict[str, Any]] = {}

    for block_num in range(1, 7):
        block_key = f"B{block_num}"
        block_units = {
            key: unit
            for key, unit in normalized.items()
            if key.upper().startswith(f"{block_key}_")
        }

        total_units = len(block_units)
        complete_units = 0
        missing_units = []
        likert_values = []

        for key, unit in block_units.items():
            if unit_is_complete(unit):
                complete_units += 1
                likert_values.append(unit.valor_likert_nao_escolhido)
            else:
                missing_units.append(key)

        media_likert_placeholder = (
            round(sum(likert_values) / len(likert_values), 2)
            if likert_values
            else None
        )

        blocks[block_key] = {
            "unidades_recebidas": total_units,
            "unidades_completas": complete_units,
            "unidades_faltantes": len(missing_units),
            "missing_units": missing_units,
            "media_likert_placeholder": media_likert_placeholder,
        }

    return blocks


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "service": "vinc-score-service",
        "status": "running"
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "vinc-score-service"
    }


@app.post("/score")
def score(payload: ScoreRequest) -> Dict[str, Any]:
    units_received = len(payload.normalized)
    missing_units = list_missing_units(payload.normalized)
    units_complete = units_received - len(missing_units)
    blocks_summary = summarize_blocks(payload.normalized)

    return {
        "submission_id": payload.submission_id,
        "instrument_version": payload.instrument_version,
        "methodology_version": payload.methodology_version,
        "algorithm_version": "score_stub_v1_0_0",
        "status": "accepted",
        "validation": {
            "units_received": units_received,
            "units_complete": units_complete,
            "units_missing": len(missing_units),
            "missing_units": missing_units,
            "can_score_fully": units_complete == 36
        },
        "blocks": blocks_summary,
        "next_step": "Aplicar matriz técnica real de score"
    }
