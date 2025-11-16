import json
import os.path
from typing import Optional, List
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from .context import ClassChangeHistory, ClassChange, FileContextManager
from ..compilation import CompilationRunner
from ...logging.printer import ConsolePrinter
from ..docker import MicroserviceDocker, MicroserviceDockerError
from ..raaid import fuzzy_find_project_files
from ..utils import parse_docker_path, is_binary_file, format_file_for_markdown, parse_find_details, \
    build_tree_structure, render_tree, get_class_name_from_content

EXTENSIONS_MAPPING = {
    "java": [".java"],
    "python": [".py"],
    "csharp": [".cs"],
}


class ErrorCorrectionTools:
    """Implementations for the tools for error correction."""

    def __init__(self, ms_docker: MicroserviceDocker, compilation_handler: CompilationRunner,
                 generated_classes: dict[str, Path], relevant_classes: dict[str, Path],
                 refactoring_details: dict[str, tuple[str, str]], language: str = "java",
                 with_tests: bool = False):
        """
        Initialize the ErrorCorrectionTools with the necessary components.
        Args:
            ms_docker (MicroserviceDocker): The Docker instance handler for the microservice.
            compilation_handler (CompilationRunner): The handler for compilation tasks.
            generated_classes (dict[str, str]): A dictionary mapping newly generated class names to their file paths in the initial microservice repository.
            relevant_classes (dict[str, str]): A dictionary mapping the monolith's class names to their file paths in the initial microservice repository.
            refactoring_details (dict[str, tuple[str, str]]): A dictionary mapping file paths to tuples containing the prompt and reasoning for the refactoring.
            language (str): The programming language of the microservice (default: "java").
            with_tests (bool): Whether to compile tests as well (default: False).
        """
        self.ms_docker = ms_docker
        self.compilation_handler = compilation_handler
        # self.original_java_files = original_java_files
        self.class_change_history = ClassChangeHistory(
            generated_classes={k: ClassChange(k, str(v), self.ms_docker.to_container_path(os.path.abspath(v)))
                               for k, v in generated_classes.items()},
            relevant_classes={k: ClassChange(k, str(v), self.ms_docker.to_container_path(os.path.abspath(v)))
                              for k, v in relevant_classes.items()},
        )
        self.refactoring_details = refactoring_details
        self.file_context = FileContextManager(refactoring_details, self.class_change_history)
        self.language = language
        self.with_tests = with_tests
        self.original_java_files = [v for v in relevant_classes.values()]
        self.changes_log = dict()
        self.logger = ConsolePrinter.get_printer("monomorph")

    def set_with_tests(self, with_tests: bool):
        self.with_tests = with_tests

    def can_modify_file(self, file_path: str) -> bool:
        """
        Use this to check if a file can be modified. {language} source code files that are part of the original
        application cannot be modified to ensure the integrity of the application.
        It is useful for determining if a file can be changed during the error correction process.

        Args:
            file_path (str): The path to the file to check.
        Returns:
            bool: True if the file can be modified, False otherwise.
        """
        original_root = os.path.abspath(self.ms_docker.microservice.directory_path)
        parsed_path = Path(parse_docker_path(file_path, original_root))
        if parsed_path in self.original_java_files:
            self.logger.debug(f"File {file_path} is part of the original application and cannot be modified.",
                              msg_type="tool")
            return False
        # self.logger.debug(f"File {file_path} can be modified.", msg_type="tool")
        return True

    def _is_source_file(self, file_path: str) -> bool:
        """
        Determine if a file is a source code file based on its extension. (e.g., .java, .py, .cs).
        """
        accepted_extensions = EXTENSIONS_MAPPING.get(self.language, [])
        extension = Path(file_path).suffix
        if extension not in accepted_extensions:
            return False
        return True

    def read_file(self, file_path: str) -> str:
        """
        Use this to read the content of a file.
        It is useful for getting the full content of a specific file for analysis or debugging purposes.
        """
        self.logger.debug(f"'read_file' invoked for file {file_path}", msg_type="tool")
        if is_binary_file(file_path):
            self.logger.warning(f"File {file_path} is binary and cannot be read as text.")
            return f"File {file_path} is binary and cannot be read as text."
        output, error_str = self.ms_docker.read_file(file_path)
        if output is None:
            self.logger.warning(f"Failed to read file {file_path}: {error_str}")
            return f"Failed to read file {file_path}: {error_str}"
        self.logger.debug(f"File {file_path} read successfully.", msg_type="tool")
        return format_file_for_markdown(file_path, output)
        # return output

    def write_file(self, file_path: str, content: str) -> str:
        """
        Use this to write content to a file.
        It is useful for modifying or creating files within the microservice's environment.
        """
        self.logger.debug(f"'write_file' invoked for file {file_path}", msg_type="tool")
        if not self.can_modify_file(file_path):
            return f"File {file_path} cannot be modified and will not be written to."
        if is_binary_file(file_path):
            self.logger.warning(f"File {file_path} is binary and cannot be written to as text.")
            return f"File {file_path} is binary and cannot be written to as text."
        success, error_str = self.ms_docker.write_file(file_path, content)
        if not success:
            self.logger.warning(f"Failed to write to file {file_path}: {error_str}")
            return f"Failed to write to file {file_path}: {error_str}"
        self.logger.debug(f"File {file_path} written successfully.", msg_type="tool")
        self.changes_log[file_path] = ("write", file_path)
        if self._is_source_file(file_path):
            class_details = self.class_change_history.get_with_container_path(file_path)
            if class_details is not None:
                class_details.changes_log.append(("write", f"written in {file_path}"))
            else:
                class_name = get_class_name_from_content(content)
                class_details = self.class_change_history.get_with_class_name(class_name)
                if class_details is None:
                    # New class created
                    class_details = ClassChange(class_name, None, file_path)
                    self.class_change_history.new_classes[class_name] = class_details
                else:
                    # Existing class modified (moved)
                    old_path = class_details.container_path
                    class_details.container_path = file_path
                    class_details.changes_log.append(("move", f"moved from {old_path} to {file_path}"))
        return f"File {file_path} has been successfully written."

    def delete_file(self, file_path: str) -> str:
        """
        Use this to delete a file.
        It is useful for removing files that are no longer needed or are causing issues.
        """
        self.logger.debug(f"'delete_file' invoked for file {file_path}", msg_type="tool")
        if not self.can_modify_file(file_path):
            return f"File {file_path} cannot be modified and will not be deleted."
        success, error_str = self.ms_docker.delete_file(file_path)
        if not success:
            self.logger.warning(f"Failed to delete file {file_path}: {error_str}")
            return f"Failed to delete file {file_path}: {error_str}"
        self.logger.debug(f"File {file_path} deleted successfully.", msg_type="tool")
        self.changes_log[file_path] = ("delete", file_path)
        if self._is_source_file(file_path):
            class_details = self.class_change_history.get_with_container_path(file_path)
            if class_details is not None:
                class_details.changes_log.append(("delete", f"deleted {file_path}"))
                class_details.container_path = None
            else:
                self.logger.error(f"Missing class details for file {file_path}. Cannot track deletion.")
        return f"File {file_path} has been successfully deleted."

    def fuzzy_file_search(self, search_term: str, directory: str = ".") -> str:
        """
        Use this to perform a fuzzy search for files in a directory if the exact file path is not known.
        It is useful for finding files that match a certain pattern or name within a specific directory.
        This tool searches for files within a defined directory using fuzzy string matching, allowing
        for approximate matches to the search term. It returns a list of matched files along with their
        match scores.

        Args:
            search_term: String to match against file paths
            directory: Root Path to start the search from (defaults to the microservice's root directory)

        Returns:
            List of tuples containing (file_path, match_score)
        """
        try:
            self.logger.debug(f"'fuzzy_file_search' invoked with search term '{search_term}' in directory '{directory}'",
                              msg_type="tool")
            results = fuzzy_find_project_files(
                ms_docker=self.ms_docker,
                search_term=search_term,
                repo_path=directory,
                threshold=60,  # Default threshold
                max_results=5,
                include_hidden=True
            )
            if len(results) == 0:
                return f"No files found matching '{search_term}' in directory '{directory}'."
            formatted_results = "\n".join([f"{file_path} (Score: {score})" for file_path, score in results])
            return f"Files matching '{search_term}':\n{formatted_results}"
        except MicroserviceDockerError as e:
            return str(e)

    def show_directory_tree(self, directory: str = ".", depth: int = 1, include_can_modif: bool = True,
                            include_changed: bool = True, include_modif_time_size: bool = False) -> str:
        """
        Use this to show the content of a given directory and its subdirectories (depending on depth).
        It is useful for exploring the structure of the microservice's file system.

        Args:
            directory (str): The directory path to explore (defaults to current directory).
            depth (int): The depth of subdirectories to include in the output (default: 1 to show only current dir).
            include_can_modif (bool): Whether to include information about whether files can be modified (default: True).
            include_changed (bool): Whether to include information about whether files have been changed since the initial compilation (default: True).
            include_modif_time_size (bool): Whether to include last modification times and the size of files (default: False).

        Returns:
            str: A formatted string representing the directory structure.
        """
        self.logger.debug(f"'show_directory_tree' invoked for path {directory} with depth {depth}", msg_type="tool")
        success, content_details, error_str = self.ms_docker.list_content_with_details(directory, depth)
        if error_str:
            self.logger.warning(f"Failed to list directory {directory}: {error_str}")
            return f"Failed to list directory {directory}: {error_str}"
        if len(content_details) == 0:
            self.logger.warning(f"No content found in directory {directory}.")
            return f"No content found in directory {directory}."
        content_dict = parse_find_details(content_details)
        for path, content in content_dict.items():
            content["can_modify"] = self.can_modify_file(path)
            content["is_changed"] = path in self.changes_log
        try:
            director_abs_path = self.ms_docker.get_absolute_path(directory)
        except MicroserviceDockerError as e:
            self.logger.warning(f"Failed to get absolute path for directory {directory}: {e}")
            # Fallback to using the provided directory path
            director_abs_path = directory
        tree_dict = build_tree_structure(content_dict, director_abs_path)
        tree_str = "\n".join(render_tree(tree_dict, prefix="", root_path=directory,
                                         include_can_modif=include_can_modif, include_changed=include_changed,
                                         include_modif_time_size=include_modif_time_size))
        root_name = Path(director_abs_path).name
        return f"Directory structure of `{directory}`:\n```\n{root_name}/\n{tree_str}\n```"

    def get_source_code(self, class_name: str) -> str:
        """
        Use this to retrieve the source code of a specific {language} class.
        It is useful for getting the full source code of a specific class if the path is not known.
        """
        self.logger.debug(f"'get_source_code' invoked for class {class_name}", msg_type="tool")
        class_details = self.class_change_history.get_with_class_name(class_name)
        if class_details is None:
            self.logger.warning(f"Class {class_name} not found in the application.")
            return f"Class {class_name} not found in the microservice."
            # TODO: Maybe add fuzzy search for class names?
        if class_details.container_path is None:
            self.logger.warning(f"Class {class_name} has no associated file in the microservice.")
            return f"Class {class_name} has no associated file in the microservice and was likely deleted."
        file_path = class_details.container_path
        output, error_str = self.ms_docker.read_file(file_path)
        if output is None:
            self.logger.warning(f"Failed to read the source code of {class_name}: {error_str}")
            return f"Failed to read the source code of {class_name}: {error_str}"
        self.logger.debug(f"Class {class_name} successfully retrieved.", msg_type="tool")
        # return format_file_for_markdown(file_path, output)
        return output

    def execute_command(self, command: str) -> str:
        """
        Use this to execute a command in the microservice's environment and return the output.
        It is useful for running shell commands or scripts within the microservice's context.
        ONLY USE THIS IF ABSOLUTELY NECESSARY, as it can have side effects on the microservice's state.
        """
        self.logger.debug(f"'execute_command' invoked with command '{command}'", msg_type="tool")
        status, output = self.ms_docker.execute_command(command)
        if status != 0:
            self.logger.warning(f"Command execution failed: {output}")
            return f"Command execution failed: {output}"
        self.logger.debug(f"Command executed successfully.", msg_type="tool")
        return output

    def compile_microservice(self, debug_mode: bool = False, only_logs: bool = False) -> str:
        """
        Use this to compile the microservice and return the compilation logs if any errors occur.
        It is useful for validating that the microservice can be built successfully after changes.
        debug_mode (bool): If True, enables debug mode for more verbose output.
        ONLY USE THIS IF YOU ARE SURE THAT THE CHANGES MADE SO FAR ARE SUFFICIENT TO ALLOW A SUCCESSFUL COMPILATION.
        """
        self.logger.debug("'compile_microservice' invoked", msg_type="tool")
        success, logs, error_block_details = self.compilation_handler.compile_and_parse(debug_mode,
                                                                                        with_tests=self.with_tests)
        if success:
            self.logger.debug("Microservice compiled successfully.", msg_type="tool")
            if only_logs:
                return "Microservice compiled successfully."
            else:
                return json.dumps({
                    "action": "EXIT_CORRECTION",
                    "exit_reason": "Microservice compiled successfully.",
                    "exit_type": "compilation_success"
                })
            # return "Microservice compiled successfully."
        if error_block_details is None:
            self.logger.warning("Compilation failed but no error details were provided.")
            logs = "Compilation failed but no error details were provided."
            if only_logs:
                return logs
            else:
                return json.dumps({
                    "tool_name": "compile_microservice",
                    "compilation_logs": logs
                })
        self.logger.debug("Compilation failed. Returning compilation logs.")
        logs = f"Compilation failed. Logs:\n```\n{error_block_details[0]}\n```"
        if only_logs:
            return logs
        else:
            return json.dumps({
                "tool_name": "compile_microservice",
                "compilation_logs": logs
            })

    def request_expert_help(self, detailed_request: str) -> dict:
        """
        Use this when you are struggling to fix an error and your attempts so far have not been successful.
        This tool allows you to request expert help for a specific issue or error you are facing.
        Provide a detailed description of the issue, including any relevant context or error messages.
        """
        self.logger.debug(f"'request_expert_help' invoked with request", msg_type="tool")
        return {
            "action": "CALL_EXPERT",
            "exit_reason": detailed_request,
            "exit_type": "expert"
        }

    def get_file_context(self, generated_class_or_proto_file: str) -> str:
        """
        Use this to get the context of a generated file (e.g., {language} class or proto file) in the microservice.
        Some of these files were generated by other agents. Since they can make mistakes, it is useful to understand
        what they were tasked to do to create the file.
        For example, if looking into how the proto file "cart.proto" was generated, provide the path "src/main/proto/cart.proto"
        Or if looking into how the class "CartService.java" was generated, provide the path "src/main/java/com/example/CartService.java"
        """
        self.logger.debug(f"'get_file_context' invoked for {generated_class_or_proto_file}", msg_type="tool")
        # if generated_class_or_proto_file not in self.refactoring_details:
        #     self.logger.debug(f"File {generated_class_or_proto_file} has no generation context available.", msg_type="tool")
        #     return f"File {generated_class_or_proto_file} was not generated by the refactoring process."
        try:
            match = self.file_context.find_file_context(generated_class_or_proto_file)
            if match is None:
                self.logger.debug(f"File {generated_class_or_proto_file} has no generation context available.", msg_type="tool")
                return f"File {generated_class_or_proto_file} was not generated by the refactoring process."
            else:
                query, prompt, reasoning = match
                self.logger.debug(f"Found context for {generated_class_or_proto_file}: query='{query}'", msg_type="tool")
        except Exception as e:
            self.logger.error(f"Error retrieving context for {generated_class_or_proto_file}: {e}", exc_info=True, msg_type="tool")
            return f"File {generated_class_or_proto_file} was not generated by the refactoring process or context retrieval failed."

        # prompt, reasoning = self.refactoring_details[generated_class_or_proto_file]
        self.logger.debug(f"Context for {generated_class_or_proto_file} retrieved successfully.", msg_type="tool")
        file_section = f"## File: \nThe file `{generated_class_or_proto_file}` was generated because:\n\n"
        prompt_section = f"## Prompt\n {prompt}\n\n" if prompt else ""
        reasoning_section = f"## Reasoning: \n{reasoning}"
        return f"{file_section}{prompt_section}{reasoning_section}"

    def fixed_error(self, error_description: str, fix_description: str) -> str:
        """
        Use this to indicate that an error has been fixed and provide a description of the fix.
        This node must be invoked after any error in the compilation process has been fixed in order to continue the
        error correction process. Do not call this tool if a new error has been introduced directly because of the changes
        you made.
        """
        self.logger.debug(f"'fixed_error' invoked with error '{error_description}' and fix '{fix_description}'",
                          msg_type="tool")
        # Here we can log the fixed error and the fix description
        self.logger.info(f"Error fixed: {error_description}. Fix: {fix_description}", msg_type="tool")
        return json.dumps({
            "action": "EXIT_CORRECTION",
            "exit_reason": f"Error '{error_description}'\n\nFix: {fix_description}",
            "exit_type": "llm"
        })

    def commit_changes(self, error_description: str, fix_description: str) -> str:
        """
        Use this to commit your changes whenever you fixed an error in the compilation logs.
        Provide a description of the error you encountered and how you fixed it.
        Do not call this tool if a new error has been introduced directly because of the changes you made.
        """
        self.logger.debug(f"'commit_changes' invoked with error '{error_description}' and fix '{fix_description}'",
                          msg_type="tool")
        # Here we can log the fixed error and the fix description
        self.logger.info(f"commiting error fix: Error {error_description}. Fix: {fix_description}", msg_type="tool")
        commit_message = f"Fixed error: {error_description}. Fix: {fix_description}"
        success, error_str = self.ms_docker.commit_git_changes(commit_message)
        if not success:
            self.logger.warning(f"Failed to commit changes: {error_str}")
            return f"Failed to commit changes: {error_str}"
        return json.dumps({
            "action": "EXIT_CORRECTION",
            "exit_reason": f"Error '{error_description}'\n\nFix: {fix_description}",
            "exit_type": "llm"
        })

    def get_tools(self, tools: Optional[List[str]] = None) -> List[BaseTool]:
        """ Returns a list of tools for the analysis. """
        @tool(description=self.read_file.__doc__)
        def read_file(file_path: str) -> str:
            return self.read_file(file_path)

        @tool(description=self.write_file.__doc__)
        def write_file(file_path: str, content: str) -> str:
            return self.write_file(file_path, content)

        @tool(description=self.delete_file.__doc__)
        def delete_file(file_path: str) -> str:
            return self.delete_file(file_path)

        @tool(description=self.fuzzy_file_search.__doc__)
        def fuzzy_file_search(search_term: str, directory: str = ".") -> str:
            return self.fuzzy_file_search(search_term, directory)

        @tool(description="Use this to show the content of a given directory and its subdirectories "
                          "(depending on depth). It is useful for exploring the structure of the microservice's "
                          "file system.")
        def show_directory_tree(directory: str = ".", depth: int = 1) -> str:
            return self.show_directory_tree(directory, depth, True, True, False)

        @tool(description=self.get_source_code.__doc__.format(language=self.language))
        def get_source_code(class_name: str) -> str:
            return self.get_source_code(class_name)

        @tool(description=self.execute_command.__doc__)
        def execute_command(command: str) -> str:
            return self.execute_command(command)

        @tool(description=self.compile_microservice.__doc__)
        def compile_microservice(debug_mode: bool = False) -> str:
            return self.compile_microservice(debug_mode)

        @tool(description=self.can_modify_file.__doc__.format(language=self.language))
        def can_modify_file(file_path: str) -> bool:
            return self.can_modify_file(file_path)

        @tool(description=self.get_file_context.__doc__.format(language=self.language))
        def get_file_context(generated_class_or_proto_file: str) -> str:
            return self.get_file_context(generated_class_or_proto_file)

        @tool(description=self.fixed_error.__doc__)
        def fixed_error(error_description: str, fix_description: str) -> str:
            return self.fixed_error(error_description, fix_description)

        @tool(description=self.request_expert_help.__doc__)
        def request_expert_help(detailed_request: str) -> dict:
            return self.request_expert_help(detailed_request)

        @tool(description=self.commit_changes.__doc__)
        def commit_changes(error_description: str, fix_description: str) -> str:
            return self.commit_changes(error_description, fix_description)

        tools_map = {
            "read_file": read_file,
            "write_file": write_file,
            "delete_file": delete_file,
            "fuzzy_file_search": fuzzy_file_search,
            "show_directory_tree": show_directory_tree,
            "get_source_code": get_source_code,
            "execute_command": execute_command,
            "compile_microservice": compile_microservice,
            "can_modify_file": can_modify_file,
            "get_file_context": get_file_context,
            "fixed_error": fixed_error,
            "request_expert_help": request_expert_help,
            "commit_changes": commit_changes,
        }
        if tools is None:
            return list(tools_map.values())
        else:
            return [tools_map[tool_name] for tool_name in tools if tool_name in tools_map]

