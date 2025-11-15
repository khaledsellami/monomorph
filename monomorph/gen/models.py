from dataclasses import dataclass

from ..llm.langchain.output import GRPCSolution, ProtoSolution


@dataclass
class NewFile:
    file_name: str
    file_path: str
    content: GRPCSolution | ProtoSolution | str


