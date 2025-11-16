from enum import Enum
from typing import Optional
from dataclasses import dataclass
import logging

from .decision.models import RefactoringDecision


PROTO_PATH = "src/main/proto"


class ApproachType(Enum):
    DTO_ONLY = "DTO-Only"
    DTO_BASED = "DTO-Based"
    ID_BASED = "ID-Based"

    @classmethod
    def from_string(cls, value: str, default: Optional["ApproachType"] = None) -> "ApproachType":
        """Convert a string to an ApproachType enum."""
        try:
            return ApproachType(value)
        except ValueError:
            if default:
                logging.getLogger("monomorph").warning(f"Invalid ApproachType: {value}. Using default: {default.name}")
                return default
            raise ValueError(f"Invalid ApproachType: {value}. Valid values are: {[e.name for e in cls]}")


@dataclass
class RefactoringMethod:
    """
    Represents the target refactoring method for a class.
    Unlike the RefactoringDecision class, this class' decision field is an ApproachType enum.
    """
    decision: ApproachType
    reasoning: str
    suggested_dto_fields: Optional[list[str]] = None

    @classmethod
    def from_decision(cls, decision: RefactoringDecision) -> "RefactoringMethod":
        """
        Create a RefactoringMethod instance from a RefactoringDecision Pydantic model.
        """
        return cls(decision=ApproachType.from_string(decision.decision), reasoning=decision.reasoning,
                   suggested_dto_fields=decision.suggested_dto_fields)
