"""Validated public request contracts; secrets are never persisted."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Target(StrictModel):
    position: Literal["near", "far", "description"] = "near"
    description: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_description(self):
        if self.position == "description" and not self.description.strip():
            raise ValueError("请选择近端、远端，或描述要分析的球员")
        return self


class Provider(StrictModel):
    kind: Literal["agent"] = "agent"
    model: str = Field(default="current host", max_length=200)

    def public(self):
        return self.model_dump()

    def runtime(self):
        return self.model_dump()


class RunRequest(StrictModel):
    target: Target = Field(default_factory=Target)
    provider: Provider = Field(default_factory=Provider)
    focus: str = Field(default="", max_length=3000)
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    focus_times: list[float] = Field(default_factory=list, max_length=4)
    mode: Literal["prepare"] = "prepare"

    @model_validator(mode="after")
    def check_window(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        if any(t < self.start or (self.end is not None and t > self.end) for t in self.focus_times):
            raise ValueError("补充观察时间必须在分析范围内")
        return self
