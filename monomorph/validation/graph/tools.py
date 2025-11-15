from typing import Optional, List
from pathlib import Path

from langchain_core.tools import tool, BaseTool

from ...llm.langgraph.decision.models import ClassNameInput
from ...llm.langgraph.decision.printer import ConsolePrinter
from ...modeling.model import AppModel
from ..utils import parse_docker_path


COMMON_SUFFIX_LANG_MAPPINGS = {
    "proto": "protobuf",
    "cs": "csharp",
    "py": "python",
    "txt": "text",
    "log": "text",
}


class CompilationLogAnalysisTools:
    """Implementations for the tools for analyzing compilation logs."""

    def __init__(self, app_model: AppModel, ms_root: str, generated_classes: dict[str, Path], generated_files: list[str],
                 log_details: dict[str, int | str], language: str = "java",
                 relevant_classes: Optional[List[str]] = None):
        self.app_model = app_model
        self.ms_root = ms_root
        self.language = language
        self.generated_classes: dict = generated_classes
        self.generated_files: list[str] = generated_files
        self.log_details: dict = log_details
        self.names = list(relevant_classes) if relevant_classes else app_model.get_class_names()
        self.logger = ConsolePrinter.get_printer("monomorph")

    def get_source_code(self, class_fqn: str) -> str:
        """
        Use this to Retrieve the source code for a given class (using its full qualified name).
        It is useful for getting the full source code of a specific {self.language} class.
        """
        class_name = class_fqn.split(".")[0]
        self.logger.debug(f"'get_source_code' invoked for class {class_name.split('.')[-1]}", msg_type="tool")
        # ConsolePrinter.get_printer("monomorph").print("--- Retrieving source code ---", "tool")
        if class_name in self.generated_classes:
            # If the class is generated, return the source code directly.
            file_path = self.generated_classes[class_name]
            assert file_path.exists(), f"File {file_path} does not exist"
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return f"The source code of the class `{class_name}` is:\n" + \
                   f"```{self.language}\n{content}\n```"
        elif class_name in self.names:
            # It's a class from the original application
            return f"The source code of the class `{class_name}` is:\n" + \
                   f"```{self.language}\n{self.app_model.get_class_source(class_name)}\n```"
        else:
            # Unknown class, possibly from a library or standard library.
            return f"Unknown class ({class_name})! It may not be part of the application."

    def get_file_content(self, file_path: str) -> str:
        """
        Use this to retrieve the content of a file within the application. It is useful for getting the full content
        of a specific file for analysis or debugging purposes.
        """
        self.logger.debug(f"'get_file_content' invoked for file {file_path}", msg_type="tool")
        parsed_file_path = Path(parse_docker_path(file_path, self.ms_root))
        if not parsed_file_path.exists():
            self.logger.warning(f"File {file_path} does not exist in the application.")
            return f"File {file_path} does not exist in the application."
        with open(parsed_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        file_extension = parsed_file_path.suffix[1:]
        file_lang = COMMON_SUFFIX_LANG_MAPPINGS.get(file_extension, file_extension)
        return f"The content of the file `{file_path}` is:\n```{file_lang}\n{content}\n```"

    def is_new_file(self, file_path: str) -> bool:
        """ Check if a file is newly generated during the refactoring process. """
        self.logger.debug(f"'is_new_file' invoked for file {file_path}", msg_type="tool")
        return file_path in self.generated_files

    def get_additional_logs(self, start_line: int, end_line: int) -> str:
        """ Returns additional logs between the given line numbers for more context, if available. """
        self.logger.debug(f"'get_additional_logs' invoked for lines {start_line} to {end_line}", msg_type="tool")
        if end_line <= start_line:
            self.logger.warning("End line must be greater than start line.")
            return "No logs available in the specified range."
        if end_line < self.log_details["end_line"] and start_line >= self.log_details["start_line"]:
            # The specified range is within the existing log details.
            return "Logs from this range have already been provided. Check above for the full log details."
        return self.log_details["logs"][start_line:end_line]

    def get_tools(self) -> List[BaseTool]:
        """ Returns a list of tools for the analysis. """
        @tool(args_schema=ClassNameInput, description=f"Use this to Retrieve the source code for a given class "
                                                      f"(using its full qualified name). It is useful for getting "
                                                      f"the full source code of a specific {self.language} class.")
        def get_source_code(class_fqn: str) -> str:
            return self.get_source_code(class_fqn)
    
        @tool(description=self.get_file_content.__doc__)
        def get_file_content(file_name: str) -> str:
            return self.get_file_content(file_name)

        @tool(description=self.is_new_file.__doc__)
        def is_new_file(file_name: str) -> bool:
            return self.is_new_file(file_name)

        @tool(description=self.get_additional_logs.__doc__)
        def get_additional_logs(start_line: int, end_line: int) -> str:
            return self.get_additional_logs(start_line, end_line)
    
        tools = [get_source_code, get_file_content, is_new_file, get_additional_logs]
        return tools
