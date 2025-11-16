import os
import shlex
import uuid
import logging
import tempfile
from pathlib import Path
from typing import Optional, Literal

import docker
import dotenv
from docker.errors import DockerException
from docker.models.containers import Container

from .const import (DEFAULT_DOCKER_WORKDIR, CONTAINER_TEMPLATE, DEFAULT_DOCKER_IMAGES, DEFAULT_ENTYPOINT_SCRIPT,
                    CONTAINER_TEMPLATE_RESUME)
from ..microservice import MicroserviceDirectory


class MicroserviceDocker:
    """
    A class representing an instance of a refactoring microservice deployed in a Docker container.
    """
    PREVIEW_LENGTH = 100

    def __init__(
            self,
            app_name: str,
            microservice: MicroserviceDirectory,
            original_dockerfile_path: Optional[str] = None,
            build_system: Literal["gradle", "maven"] = "maven",
            timeout_seconds: Optional[int] = 300,
            persistent_container: bool = False,
            resume_from: Optional[str] = None
    ):
        """
        Initializes the MicroserviceDocker.

        Args:
            app_name: The name of the application.
            microservice: The MicroserviceDirectory instance representing the generated microservice.
            original_dockerfile_path: Path to the original application's Dockerfile.
            build_system: The build system used ("maven" or "gradle").
            timeout_seconds: Timeout for the container run process in seconds.
            persistent_container: Whether to keep the container running for multiple operations.
            resume_from: Optional path to resume from a previous state.

        Raises:
            ValueError: If inputs are invalid (e.g., paths don't exist, invalid build_system).
            RuntimeError: If Docker is not available or the daemon is not running.
        """
        self.app_name = app_name
        self.microservice = microservice
        self.microservice_path = Path(self.microservice.directory_path)
        self.original_dockerfile_path = Path(original_dockerfile_path) if original_dockerfile_path else None
        self.build_system = build_system
        self.timeout_seconds = timeout_seconds
        self.persistent_container = persistent_container
        if resume_from is not None:
            self.resume_from = Path(resume_from)
            if (self.resume_from / self.microservice.name).is_dir():
                self.resume_from_ms_path = self.resume_from / self.microservice.name
            else:
                self.resume_from_ms_path = None

        else:
            self.resume_from = None
            self.resume_from_ms_path = None
        self.validation_id = str(uuid.uuid4())[:8]
        self.image_tag = f"{self.app_name}-{self.microservice.name}-{self.validation_id}"
        self.container_name = f"{self.app_name}-{self.microservice.name}-container-{self.validation_id}"
        self.dockerfile_content: Optional[str] = None
        self.base_image: Optional[str] = None
        self.logger = logging.getLogger("monomorph")
        # Initialize the Docker client
        try:
            dotenv.load_dotenv()
            CUSTOM_DOCKER_SOCKET = os.getenv("CUSTOM_DOCKER_SOCKET")
            self.client = docker.DockerClient(base_url=CUSTOM_DOCKER_SOCKET)
        except DockerException as e:
            raise RuntimeError(f"Could not initialize Docker client. Is Docker installed and configured? Error: {e}")
        # Validate inputs and prerequisites
        self._validate_inputs()

    @classmethod
    def validate_prerequisites(cls):
        logger = logging.getLogger("monomorph")
        try:
            dotenv.load_dotenv()
            docker_socket = os.getenv("CUSTOM_DOCKER_SOCKET")
            if docker_socket is None:
                logger.debug("No CUSTOM_DOCKER_SOCKET environment variable set.")
                return False
            client = docker.DockerClient(base_url=docker_socket)
            return client.ping()
        except docker.errors.APIError as e:
            logger.error(f"Could not connect to Docker daemon. Please start Docker to proceed. Error: {e}")
            return False
        except DockerException as e:
            logger.error(f"Could not initialize Docker client or . Is Docker installed and configured? Error: {e}")
            return False

    def to_container_path(self, path: str | Path) -> str:
        """
        Converts a host path to a container path based on the Dockerfile's WORKDIR.
        If the path is already absolute, it returns it as is.
        """
        path = str(path)
        if os.path.isabs(path):
            ms_path = os.path.abspath(self.microservice.directory_path)
            if path.startswith(ms_path):
                return path.replace(ms_path, DEFAULT_DOCKER_WORKDIR)
            else:
                self.logger.warning(f"Path {path} is not absolute. Returning it as is.")
                return path
        return str(Path(DEFAULT_DOCKER_WORKDIR) / path)

    def cleanup(self, cleanup_image: bool = False, force: bool = True):
        """Cleans up the Docker image and container after compilation."""
        status, container = self.get_container_status()
        try:
            if container is not None:
                if status:
                    self.logger.debug(f"Stopping container '{self.container_name}' before removal.")
                    container.stop()
                container.remove(force=force)
                self.logger.debug(f"Removed container '{self.container_name}'.")
            if cleanup_image:
                self.client.images.remove(image=self.image_tag, force=force)
                self.logger.debug(f"Removed image '{self.image_tag}'.")
        except docker.errors.ImageNotFound:
            self.logger.debug(f"Image '{self.image_tag}' not found for cleanup (likely failed to build).")
        except docker.errors.APIError as e:
            self.logger.warning(f"Failed to clean up image '{self.image_tag}' and container '{self.container_name}': "
                                f"{e}")

    def _validate_inputs(self):
        """Checks if required paths and configurations are valid."""
        self.logger.debug("Validating CompilationRunner inputs...")
        if not self.microservice_path.is_dir():
            raise ValueError(f"Project path does not exist or is not a directory: {self.microservice_path}")
        if self.resume_from is not None and not self.resume_from.is_dir():
            raise ValueError(f"Previous state path does not exist or is not a directory: {self.resume_from}")
        if self.original_dockerfile_path is not None and not self.original_dockerfile_path.is_file():
            raise ValueError(
                f"Original Dockerfile path does not exist or is not a file: {self.original_dockerfile_path}")
        if self.build_system not in ["maven", "gradle"]:
            raise ValueError(f"Invalid build system '{self.build_system}'. Must be 'maven' or 'gradle'.")
        # Check if the Docker daemon is running by pinging it.
        try:
            if not self.client.ping():
                raise RuntimeError("Docker daemon responded with an error.")
        except docker.errors.APIError as e:
            raise RuntimeError(f"Could not connect to Docker daemon. Please start Docker to proceed. Error: {e}")

    def _extract_base_image(self) -> str:
        """Extracts the 'FROM' instruction line from the original Dockerfile."""
        if self.original_dockerfile_path is None:
            default_image = DEFAULT_DOCKER_IMAGES[self.build_system]
            self.logger.debug(f"No original Dockerfile provided, using default base image: {default_image}")
            self.base_image = default_image
            return f"FROM {default_image}"
        self.logger.debug(f"Extracting base image from {self.original_dockerfile_path}...")
        with open(self.original_dockerfile_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped_line = line.strip()
                if stripped_line.upper().startswith("FROM "):
                    self.logger.info(f"Found base image instruction: '{stripped_line}'")
                    self.base_image = stripped_line.split()[1]  # Get the image name after 'FROM'
                    return stripped_line
        raise ValueError(f"Could not find a 'FROM' instruction in {self.original_dockerfile_path}")

    def _create_validation_dockerfile(self, base_image_line: str, dockerfile_path: Optional[str] = None,
                                      entrypoint_script: Optional[str] = None) -> Path:
        """Creates the 'DockerfileValid'"""
        # Generate the Dockerfile content based on the build system
        template = CONTAINER_TEMPLATE if self.resume_from_ms_path is None else CONTAINER_TEMPLATE_RESUME
        if self.persistent_container or entrypoint_script is None:
            entrypoint_script = DEFAULT_ENTYPOINT_SCRIPT
        self.dockerfile_content = template.format(
            base_image_line=base_image_line,
            default_workdir=DEFAULT_DOCKER_WORKDIR,
            entrypoint_script=entrypoint_script
        )
        if dockerfile_path is None:
            # Save the Dockerfile content to 'DockerfileValid' in a temporary file
            validation_dockerfile_path = Path(tempfile.NamedTemporaryFile(delete=False).name)
        else:
            # Use the provided path for the Dockerfile
            validation_dockerfile_path = Path(dockerfile_path)
            # Ensure the directory exists
            validation_dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Creating validation Dockerfile at: {validation_dockerfile_path}")
        with open(validation_dockerfile_path, 'w', encoding='utf-8') as f:
            f.write(self.dockerfile_content)
        return validation_dockerfile_path

    def build_image(self, entrypoint_script: Optional[str] = None) -> str:
        """
        Builds the Docker image for the microservice using the specified build system.
        If the image already exists and entrypoint_script is None, it skips the build process.
        Args:
            entrypoint_script: Optional custom entrypoint script to use in the Dockerfile.

        Returns:
            The name of the built Docker image.

        Raises:
            RuntimeError: If the Docker image build fails.
            APIError: If there is an error with the Docker API.
        """
        try:
            if self.client.images.get(self.image_tag) and entrypoint_script is None:
                self.logger.debug(f"Image '{self.image_tag}' already built.")
                return self.image_tag
        except docker.errors.ImageNotFound:
            # self.is_image_built is false and the image does not exist, proceed to build it.
            pass
        self.logger.info(f"Building Docker image '{self.image_tag}'")
        from_base_image_line = self._extract_base_image()
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dockerfile_path = os.path.join(tmpdir, "DockerfileValid")
            validation_dockerfile_path = self._create_validation_dockerfile(from_base_image_line, temp_dockerfile_path,
                                                                            entrypoint_script)
            if self.resume_from_ms_path is None:
                if self.resume_from is not None:
                    self.logger.warning(f"Previous state path {self.resume_from_ms_path} does not exist. "
                                        f"Using microservice path: {self.microservice_path}")
                else:
                    self.logger.info(f"Using microservice path: {self.microservice_path}")
                microservice_path = self.microservice_path
            else:
                self.logger.info(f"Resuming from microservice path: {self.resume_from_ms_path}")
                microservice_path = self.resume_from_ms_path
            self.client.images.build(
                path=str(microservice_path),
                dockerfile=str(validation_dockerfile_path),
                tag=self.image_tag,
                rm=True  # Remove intermediate containers
            )
        self.logger.info(f"Docker image '{self.image_tag}' built successfully.")
        return self.image_tag

    def image_exists(self) -> bool:
        try:
            self.client.images.get(self.image_tag)
            return True
        except docker.errors.ImageNotFound:
            return False

    def get_container_status(self) -> tuple[Literal["running", "stopped", "not_found"], Optional[Container]]:
        """
        Checks the status of the container.

        Returns:
            "running" if the container is running,
            "stopped" if it exists but is not running,
            "not_found" if the container does not exist.
        """
        try:
            container = self.client.containers.get(self.container_name)
            status = "running" if container.status == "running" else "stopped"
            return status, container
        except docker.errors.NotFound:
            return "not_found", None

    def start_container(self) -> Container:
        """
        Starts a persistent container from the built image. Will build the image if it does not exist.
        If the container is already running, it returns the existing container instance.
        If the container exists but is stopped, it restarts the container.

        Returns:
            The running container instance.
        """

        if not self.image_exists():
            self.build_image()

        # Check the status of the container
        container_status, container = self.get_container_status()
        if container_status == "running":
            assert container is not None, "Container should not be None if status is 'running'."
            self.logger.debug(f"Container '{self.container_name}' already running.")
            return container

        # If the container exists but is stopped, restart it
        if container_status == "stopped":
            assert container is not None, "Container should not be None if status is 'stopped'."
            self.logger.debug(f"Container '{self.container_name}' exists but is stopped. Restarting it.")
            container.start()
            return container

        # If the container does not exist, create and start a new one
        self.logger.info(f"Starting container '{self.container_name}'")
        container = self.client.containers.run(
            image=self.image_tag,
            name=self.container_name,
            detach=True,
            tty=True,
            stdin_open=True,
            working_dir=DEFAULT_DOCKER_WORKDIR
        )
        return container

    def run_container(self) -> Container:
        """
        Runs the container for one-time operations. This is useful for tasks that do not require a persistent container.
        It will build the image if it does not exist. It will restart the container if it exists but is stopped or running.

        Returns:
            The running container instance.
        """
        if not self.image_exists():
            self.build_image()

        status, container = self.get_container_status()
        if status != "not_found":
            self.logger.warning(f"Stopping and removing existing container '{self.container_name}'")
            if status == "running":
                container.stop()
            container.remove(force=True)
        self.logger.info(f"Running one-time container '{self.container_name}'")
        container = self.client.containers.run(
            image=self.image_tag,
            name=self.container_name,
            detach=True,  # Run in background
            stdout=True,
            stderr=True
        )
        return container

    def execute_command(self, command: str, workdir: Optional[str] = None) -> tuple[int, str]:
        """
        Executes a command in the running container.

        Args:
            command: The command to execute.
            workdir: Optional working directory for the command.

        Returns:
            A tuple containing (exit_code: int, output: str).
        """
        status, container = self.get_container_status()
        if status != "running":
            self.logger.warning(f"Container '{self.container_name}' is not running.")
            container = self.start_container()

        cmd_to_log = command if len(command) <= self.PREVIEW_LENGTH else command[:self.PREVIEW_LENGTH] + "..."
        self.logger.debug(f"Executing command in container: {cmd_to_log}...")
        exec_result = container.exec_run(
            cmd=["sh", "-c", command],
            workdir=workdir or DEFAULT_DOCKER_WORKDIR,
            stdout=True,
            stderr=True
        )

        output = exec_result.output.decode('utf-8') if exec_result.output else ""
        return exec_result.exit_code, output

    def copy_from_container(self, container_path: str, host_path: str) -> bool:
        """
        Copies files/directories from container to host.

        Args:
            container_path: Path in the container to copy from.
            host_path: Path on the host to copy to.

        Returns:
            True if successful, False otherwise.
        """
        status, container = self.get_container_status()
        if status != "running":
            self.logger.error("Container is not running")
            return False
        host_path = Path(host_path)
        if not host_path.parent.exists():
            self.logger.debug(f"Creating parent directory for {host_path}")
            host_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(host_path, 'wb') as f:
                bits, _ = container.get_archive(container_path)
                for chunk in bits:
                    f.write(chunk)

            self.logger.debug(f"Copied {container_path} to {host_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to copy from container: {e}")
            return False

    def read_file(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """
        Reads the content of a file in the container.

        Args:
            file_path: Path to the file in the container.

        Returns:
            File content as string, or None if failed.
        """
        exit_code, output = self.execute_command(f"cat {file_path}")
        return (output, None) if exit_code == 0 else (None, output)

    def write_file(self, file_path: str, content: str) -> tuple[bool, Optional[str]]:
        """
        Writes content to a file in the container.

        Args:
            file_path: Path to the file in the container.
            content: Content to write.

        Returns:
            True if successful, False otherwise.
        """
        # Escape content for shell
        escaped_content = content.replace("'", "'\"'\"'")
        exit_code, output = self.execute_command(f"echo '{escaped_content}' > {file_path}")
        return exit_code == 0, output if exit_code != 0 else None

    def delete_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """
        Deletes a file in the container.

        Args:
            file_path: Path to the file in the container.

        Returns:
            True if successful, False otherwise.
        """
        exit_code, output = self.execute_command(f"rm -f {file_path}")
        return exit_code == 0, output if exit_code != 0 else None

    def list_files(self, directory: str = ".") -> tuple[bool, list[str], Optional[str]]:
        """
        Lists files recursively in a directory in the container.

        Args:
            directory: Directory path in the container.

        Returns:
            Tuple of (success: bool, error: Optional[str], files: Optional[list[str]]).
        """
        # Return absolute path for the found files
        exit_code, output = self.execute_command(f'find "$(realpath "{directory}")" -type f')
        if exit_code == 0:
            files = output.splitlines() if output else []
            return True, files, None
        else:
            return False, [], output

    def get_absolute_path(self, path: str) -> str:
        """
        Gets the absolute path of a file or directory in the container.

        Args:
            path: Path to the file or directory.
        Returns:
            Absolute path as a string.
        """
        exit_code, output = self.execute_command(f'realpath "{path}"')
        if exit_code == 0:
            return output.strip()
        else:
            raise MicroserviceDockerError(f"Failed to get absolute path for '{path}': {output}")

    def list_content_with_details(self, directory: str = ".", max_depth: int = 1) -> (
            tuple)[bool, list[str], Optional[str]]:
        """
        Lists files and directories with details in a directory in the container.

        Args:
            directory: Directory path in the container.
            max_depth: Maximum depth to search for files.

        Returns:
            Tuple of (success: bool, files: Optional[list[str]], error: Optional[str]).
        """
        exit_code, output = self.execute_command(f'find "$(realpath "{directory}")" -maxdepth {max_depth} -printf \'%p|%s|%T@|%m|%y\\n\' 2>/dev/null')
        if exit_code == 0:
            details = output.splitlines() if output else []
            return True, details, None
        else:
            return False, [], output

    def commit_git_changes(self, commit_message: str = "Automated commit by Monomorph") -> tuple[bool, Optional[str]]:
        """
        Commits changes in the container's git repository.

        Args:
            commit_message: The commit message to use.

        Returns:
            Tuple of (success: bool, error: Optional[str]).
        """
        escaped_message = shlex.quote(commit_message)
        exit_code, output = self.execute_command(f'git add -A && git commit -m {escaped_message}')
        if exit_code == 0:
            return True, None
        else:
            return False, output if output else "Failed to commit changes"


class MicroserviceDockerError(Exception):
    """Base class for exceptions in the MicroserviceDocker module."""
    pass
