from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    """A detailed analysis of a single root cause for one or more compilation errors."""
    error_summary: str = Field(
        ...,
        description="A concise, one-sentence summary of the root cause. Example: 'Missing import for a DTO class in the gRPC service implementation'."
    )
    detailed_explanation: str = Field(
        ...,
        description="A more detailed explanation of the problem, how it was identified, and why it causes the observed compilation errors."
    )
    log_start_line: int = Field(description="The start line number from the compilation logs that represents the section that includes the manifestations of this single root cause.")

    log_end_line: int = Field(description="The end line number from the compilation logs that represents the section that includes the manifestations of this single root cause.")
    affected_files: List[List[str]] = Field(
        ...,
        description="A list of tuples, each containing the file path and a brief reason for change. Each tuple should be in the format (file_path, reason_for_change)."
    )
    solution_plan: List[str] = Field(
        ...,
        description="A precise, ordered list of steps to be taken to fix the error. Each step should be a clear, actionable instruction."
    )


class CompilationAnalysisReport(BaseModel):
    """The root model for the compilation analysis report, containing a list of all identified root causes."""
    analysis_results: List[RootCauseAnalysis] = Field(
        ...,
        description="A list containing the analysis for each identified root cause of the compilation failure."
    )