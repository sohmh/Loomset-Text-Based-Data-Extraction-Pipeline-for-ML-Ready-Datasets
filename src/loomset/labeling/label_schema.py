from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LabelResult(BaseModel):
    label: str = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        return value.strip().lower()
