import subprocess
import os
import pathlib
import tempfile
import json
from importlib import resources
from typing import Optional

from .abstract import AbstractImportParserClient


class CliImportParserClient(AbstractImportParserClient):
    """
    Implementation of the import parser client that interacts with the
    Java tool via its command-line interface (using Picocli subcommands).

    Assumes the Java tool is packaged as an assembly JAR.
    """
    IMPORT_PARSER_JAR_PATH: pathlib.Path = resources.files("monomorph.resources").joinpath("java-import-parser.jar")

    def __init__(
            self,
            directory_path: str,
            timeout_seconds: Optional[int] = 60
    ):
        """
        Initializes the CLI Java Parser Client.

        Args:
            directory_path: Path to the root directory of the Java project/sources.
            timeout_seconds: Timeout for subprocess execution in seconds.

        Raises:
            ValueError: If required JAR path is not configured or file/executable is not found.
        """
        super().__init__(directory_path) 
        self.java_executable = os.environ.get("JAVA_EXEC_PATH", "java")
        self._check_config()
        self.timeout_seconds = timeout_seconds
        self._command_base = self._build_command_base()

    def _check_config(self):
        """Checks if required Java paths and executables are configured and valid."""
        self.logger.debug("Checking Java Import Parser configuration...")
        if not self.IMPORT_PARSER_JAR_PATH.exists():
            raise ValueError(f"Refactor JAR path not configured or not found: {self.IMPORT_PARSER_JAR_PATH}.")
        # Basic check if java executable seems valid
        # try:
        #     subprocess.run([self.java_executable, "-version"], check=True, capture_output=True, timeout=10)
        # except FileNotFoundError:
        #     raise ValueError(f"Java executable '{self.java_executable}' not found. Check JAVA_EXEC_PATH env var or "
        #                      f"system PATH.")
        # except subprocess.CalledProcessError as e:
        #     raise ValueError(f"Java executable '{self.java_executable}' failed version check: {e}. Stderr: "
        #                      f"{e.stderr.decode(errors='ignore')}")
        # except subprocess.TimeoutExpired:
        #     raise ValueError(f"Java executable '{self.java_executable}' timed out during version check.")
        # except Exception as e:
        #     raise ValueError(f"Unexpected error checking Java executable '{self.java_executable}': {e}")

    def _build_command_base(self) -> list[str]:
        """Builds the common part of the command using -jar."""
        return [
            str(self.java_executable),
            "-jar",
            str(self.IMPORT_PARSER_JAR_PATH),
            str(self.directory_path)
        ]

    def _execute_subprocess(self, command: list[str], timeout_seconds: Optional[int]) -> str:
        """Executes the Java subprocess and handles output/errors."""
        try:
            self.logger.debug(f"Executing command: {' '.join(command)}")
            process = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                encoding='utf-8',
                errors='replace'
            )
            if process.stderr:
                self.logger.debug(f"Java process stderr:\n---\n{process.stderr.strip()}\n---")
            if process.returncode != 0:
                # Include command and more context in error
                err_msg = (
                    f"Java refactoring process failed with exit code {process.returncode}. "
                    f"Command: {' '.join(command)}. "
                    f"Check logs (stderr) for details."
                )
                raise RuntimeError(err_msg)

            # Check for empty stdout on success, as it indicates an issue (e.g., target not found in Java)
            if not process.stdout and process.returncode == 0:
                err_msg = (
                     f"Java process succeeded (exit 0) but produced no output. "
                     f"Command: {' '.join(command)}. "
                     f"This might mean the target class was not found or processing failed silently."
                )
                raise RuntimeError(err_msg)
            return process.stdout
        except FileNotFoundError:
            raise RuntimeError(f"Java executable '{self.java_executable}' not found during execution.")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Java refactoring process timed out after {timeout_seconds} seconds. "
                               f"Command: {' '.join(command)}")
        except Exception as e:
            raise RuntimeError(f"Subprocess execution failed unexpectedly: {e}")

    def refactor_single(
        self,
        target_qualified_name: str,
        old_qualified_name: str,
        new_qualified_name: str
    ) -> str:
        if not all([target_qualified_name, old_qualified_name, new_qualified_name]):
            raise ValueError("All arguments for refactor_single must be non-empty.")

        command = self._command_base.copy()
        command.append("single")
        command.append(target_qualified_name)
        command.append(old_qualified_name)
        command.append(new_qualified_name)

        # Define the timeout for the subprocess
        timeout_seconds = self.timeout_seconds

        self.logger.info(f"Executing CLI 'single' refactoring for target '{target_qualified_name}'")
        result = self._execute_subprocess(command, timeout_seconds)
        self.logger.info(f"CLI 'single' refactoring for '{target_qualified_name}' completed.")
        return result.strip()

    def refactor_batch_target(
        self,
        target_qualified_name: str,
        replacements: dict[str, str] | list[tuple[str, str]]
    ) -> Optional[str]:
        if not target_qualified_name:
            raise ValueError("target_qualified_name must be non-empty.")
        if not replacements:
            raise ValueError("Replacements cannot be empty for batch_target.")

        command = self._command_base.copy()
        command.append("batch-target")
        command.append(target_qualified_name)

        # Add replacement options
        if isinstance(replacements, dict):
            items = replacements.items()
        elif isinstance(replacements, list):
            items = replacements
        else:
            raise TypeError("Replacements must be a mapping (dict) or a list of tuples.")

        if not items:
            raise ValueError("Replacements cannot be empty for batch_target.")

        for old_name, new_name in items:
            if not isinstance(old_name, str) or not isinstance(new_name, str) or not old_name or not new_name:
                raise ValueError(f"Invalid replacement pair found: {old_name} -> {new_name}")
            command.append("-r")
            command.append(f"{old_name}={new_name}")
        # Define the timeout for the subprocess
        timeout_seconds = self.timeout_seconds
        self.logger.info(f"Executing CLI 'batch-target' refactoring for target '{target_qualified_name}'")
        result = self._execute_subprocess(command, timeout_seconds)
        self.logger.info(f"CLI 'batch-target' refactoring for '{target_qualified_name}' completed.")
        return result.strip()

    def refactor_batch_all(
        self,
        replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]],
    ) -> dict[str, Optional[str]]:
        if not replacements_per_target:
            self.logger.warning("Replacements_per_target map is empty. Java tool will perform no action.")
            return {}
        replacements_as_dict = replacements_per_target.copy()
        for target, reps in replacements_as_dict.items():
            if isinstance(reps, list):
                # Convert list of tuples to dict
                replacements_as_dict[target] = dict(reps)
            elif not isinstance(reps, dict):
                raise TypeError(f"Value for target '{target}' must be a dictionary/mapping.")
        try:
            # Using NamedTemporaryFile to ensure it's cleaned up
            with tempfile.NamedTemporaryFile(mode='w', suffix=".json", delete=False, encoding='utf-8') as tmp_file:
                json.dump(replacements_as_dict, tmp_file)  # Write JSON
                tmp_file_path = tmp_file.name
                self.logger.debug(f"Wrote batch_all replacements to temporary file: {tmp_file_path}")

                # --- Build and Execute Command ---
                command = self._command_base.copy()
                command.append("batch-all")
                command.append("-f")
                command.append(tmp_file_path)
                # Define the timeout for the subprocess
                timeout_seconds = max(self.timeout_seconds * len(replacements_as_dict), self.timeout_seconds)
                self.logger.info(f"Executing CLI 'batch-all' refactoring using file '{tmp_file_path}'")
                result_json_str = self._execute_subprocess(command, timeout_seconds)
                self.logger.info(f"CLI 'batch-all' refactoring completed.")

            # --- Parse JSON output ---
            try:
                result_map = json.loads(result_json_str)
                # Ensure the structure is Dict[str, Optional[str]] - allow null values from Java
                if not isinstance(result_map, dict):
                    raise TypeError(f"Expected JSON object (dict) output, but got {type(result_map)}")
                # No further validation on values needed here, allow None/null
                return result_map
            except json.JSONDecodeError as json_err:
                self.logger.debug(f"Raw output:\n{result_json_str}")
                raise RuntimeError(f"Failed to decode JSON output from Java 'batch-all': {json_err}")
        finally:
            # --- Clean up temporary file ---
            if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                    self.logger.debug(f"Removed temporary file: {tmp_file_path}")
                except OSError as e:
                    self.logger.warning(f"Failed to remove temporary file {tmp_file_path}: {e}")

    def refactor_batch_all_stream(
            self,
            replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]],
            callback: callable
    ) -> None:
        raise NotImplementedError("Batch all stream refactoring is not implemented in CLI client.")
