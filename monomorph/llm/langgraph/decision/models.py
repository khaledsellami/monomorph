from typing import Literal, Optional, List

from pydantic import BaseModel, Field


class ClassNameInput(BaseModel):
    """Input model for tools operating on a single class name."""
    class_name: str = Field(description="The fully qualified name of the class. e.g., 'com.example.MyClass'.")


class MethodNameInput(BaseModel):
    """Input model for tools operating on a single method name."""
    class_name: str = Field(description="The fully qualified name of the class that contains the method. e.g., "
                                        "'com.example.MyClass'.")
    method_name: str = Field(description="The name of the method to be analyzed. e.g., 'setName(java.lang.String)'.")


class RefactoringDecision(BaseModel):
    """Output model for the refactoring decision."""
    decision: Literal["ID-Based", "DTO-Based"] = Field(description="The recommended refactoring approach.")
    reasoning: str = Field(description="Step-by-step explanation citing tool results and criteria for the decision.")
    suggested_dto_fields: Optional[List[str]] = Field(default=None,
                                                      description="If DTO-Based, a list of suggested field names "
                                                                  "(as strings) to include in the DTO. Null otherwise.")

