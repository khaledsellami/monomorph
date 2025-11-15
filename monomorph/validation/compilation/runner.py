import re
import logging
from typing import Optional, Literal

import docker
from docker.errors import DockerException

from ..docker import MicroserviceDocker


COMPILE_COMMAND_MAP = {
    "maven": {
        True: 'mvn clean compile -B -DskipTests -X',
        False: 'mvn clean compile -B -DskipTests'
    },
    "gradle": {
        True: 'gradle clean build -x test -d',
        False: 'gradle clean build -x test'
    }
}


TEST_COMPILE_COMMAND_MAP = {
    "maven": {
        True: 'mvn clean test-compile -B -DskipTests -X',
        False: 'mvn clean test-compile -B -DskipTests'
    },
    "gradle": {
        True: 'gradle clean build testClasses -x test -d',
        False: 'gradle clean build testClasses -x test'
    }
}


class CompilationRunner:
    """
    Handles the compilation of a generated microservice within a secure and
    isolated Docker container using the docker-py library.
    """
    def __init__(self, ms_docker: MicroserviceDocker, build_system: Literal['maven', 'gradle'],
                 auto_cleanup_container: bool = True, auto_cleanup_image: bool = False,):
        self.ms_docker = ms_docker
        self.build_system = build_system
        self.auto_cleanup_container = auto_cleanup_container
        self.auto_cleanup_image = auto_cleanup_image
        self.logger = logging.getLogger("monomorph")

    def compile_project(self, debug_mode: bool = True, with_tests: bool = False) -> tuple[bool, str]:
        """
        Compiles the project using the appropriate build system.

        Returns:
            A tuple containing (success: bool, logs: str).
        """
        try:
            if self.ms_docker.persistent_container:
                # Use persistent container approach
                self.ms_docker.start_container()

                if with_tests:
                    # Use test compilation commands
                    commands = TEST_COMPILE_COMMAND_MAP[self.build_system]
                else:
                    commands = COMPILE_COMMAND_MAP[self.build_system]
                command = commands[debug_mode]

                exit_code, logs = self.ms_docker.execute_command(command)
                success = exit_code == 0

                if success:
                    self.logger.info("Compilation successful.")
                else:
                    self.logger.warning(f"Compilation failed with exit code {exit_code}")
                    logs = (
                        f"Compilation failed with exit code {exit_code}.\n"
                        f"Container Logs:\n{logs}"
                    )
                return success, logs
            else:
                # Use one-time container approach
                return self._compile_project_oneshot()
        except docker.errors.BuildError as e:
            build_log = "\n".join([item['stream'] for item in e.build_log if 'stream' in item])
            err_msg = f"Docker image build failed.\nBuild Log:\n{build_log}"
            self.logger.error(err_msg)
            return False, err_msg
        except docker.errors.ContainerError as e:
            err_msg = (
                f"Compilation failed with exit code {e.exit_status}.\n"
                f"Container Logs:\n{e.stderr}"
            )
            self.logger.warning(err_msg)
            return False, err_msg
        except docker.errors.APIError as e:
            err_msg = f"An error occurred with the Docker API: {e}"
            self.logger.error(err_msg, exc_info=True)
            return False, err_msg
        except Exception as e:
            err_msg = f"An unexpected error occurred during compilation: {e}"
            self.logger.error(err_msg, exc_info=True)
            raise RuntimeError(err_msg) from e
        finally:
            if self.auto_cleanup_container:
                self.ms_docker.cleanup(self.auto_cleanup_image)

    def _compile_project_oneshot(self) -> tuple[bool, str]:
        """
        Orchestrates the entire compilation process using docker-py.

        Returns:
            A tuple containing (success: bool, logs: str).
        """
        # 1. Build the Docker image
        command_string = ', '.join([f'"{c}"' for c in COMPILE_COMMAND_MAP[self.build_system].split()])
        entrypoint_script = f"CMD [ {command_string} ]"
        image_tag = self.ms_docker.build_image(entrypoint_script)
        # 2. Run the container to perform compilation
        self.logger.info(f"Running compilation in container from image '{image_tag}'...")
        container = self.ms_docker.run_container()
        # Wait for completion and get logs
        result = container.wait()
        exit_code = result['StatusCode']
        logs = container.logs(stdout=True, stderr=True, stream=False)
        container.remove()
        if exit_code == 0:
            self.logger.info("Compilation successful.")
            return True, logs.decode('utf-8').strip()
        else:
            err_msg = (
                f"Compilation failed with exit code {exit_code}.\n"
                f"Container Logs:\n{logs.decode('utf-8')}"
            )
            return False, err_msg

    def find_error_block(self, output: str, debug_mode: bool = False) -> Optional[tuple[str, int, int]]:
        """
        Locates and extracts the raw text block containing compilation errors
        without performing a full parse of each error line.
        Args:
            output: The raw output from the compilation command.
            debug_mode: If True, the logs were generated in debug mode,
        Returns:
            A string containing the lines of the compilation error block,
            or None if no specific block is found.
        """
        self.logger.debug("Attempting to find raw error block in compilation logs.")
        MAVEN_ERROR_REGEX = {
            True: re.compile(r"^\[ERROR].*$"),
            False: re.compile(r"^\[ERROR] .*$")  # More generic for non-debug mode
        }
        GRADLE_ERROR_REGEX = {
            True: re.compile(r"^.*\[ERROR] \[.*].*$"),
            False: re.compile(r"^.*(error|FAILED|FAILURE).*$")  # More generic for non-debug mode
        }
        lines = output.splitlines()
        if self.build_system == "maven":
            regex_to_use = MAVEN_ERROR_REGEX[debug_mode]
        elif self.build_system == "gradle":
            regex_to_use = GRADLE_ERROR_REGEX[debug_mode]
        else:
            self.logger.warning("Unknown build system; cannot reliably find error block.")
            return None
        # Find the start of the error block
        for i, line in enumerate(lines):
            if regex_to_use.match(line):
                self.logger.debug(f"Found error block start at line {i}: {line}")
                break
        else:
            self.logger.debug("No error block start found in the output.")
            self.logger.debug("Output was:\n" + output)
            return None
        start_line = max(0, i - 3)  # Allow some context before the error line
        # Collect all subsequent lines and add line numbers at the start
        error_lines = [f"L{i}: {lines[i]}" for i in range(start_line, len(lines))]
        self.logger.debug(f"Extracted error block lines from {start_line} (total {len(error_lines)})")
        return "\n".join(error_lines), start_line, len(lines)

    def compile_and_parse(self, debug_mode: bool = True,
                          with_tests: bool = False) -> tuple[bool, str, Optional[tuple[str, int, int]]]:
        """
        Compiles the project and parses the output for errors.

        Returns:
            A tuple containing (success: bool, logs: str, error_block: Optional[tuple[str, int, int]]).
        """
        success, logs = self.compile_project(debug_mode, with_tests=with_tests)
        if not success:
            error_block = self.find_error_block(logs, debug_mode)
            return success, logs, error_block
        return success, logs, ("The project compiled successfully without errors.", 0, 0)
