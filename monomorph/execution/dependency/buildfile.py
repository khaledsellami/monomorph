import logging
import os
import shutil
import re
from abc import ABC, abstractmethod
from typing import Optional, Any


# --- dependencies versions ---
GRPC_VERSION = "1.71.0"
PROTOBUF_VERSION = "3.25.5"  # Often aligned with gRPC
ANNOTATION_API_VERSION = "1.3.2"
CAFFEINE_VERSION = "2.8.0"
MAPSTRUCT_VERSION = "1.6.3"

PROTO_PATH = "src/main/proto"


# Dependencies required for gRPC
REQUIRED_DEPENDENCIES = [
    {"groupId": "io.grpc", "artifactId": "grpc-netty-shaded", "version": GRPC_VERSION, "scope": "runtime"},
    {"groupId": "io.grpc", "artifactId": "grpc-protobuf", "version": GRPC_VERSION},
    {"groupId": "io.grpc", "artifactId": "grpc-stub", "version": GRPC_VERSION},
    # protobuf-java is a runtime dependency of grpc-protobuf
    {"groupId": "com.google.protobuf", "artifactId": "protobuf-java", "version": PROTOBUF_VERSION},
    # Needed by grpc-stub generated code for Java 9+ compatibility.
    {"groupId": "javax.annotation", "artifactId": "javax.annotation-api", "version": ANNOTATION_API_VERSION,
     "scope": "provided"}
]

SERVER_REQUIRED_DEPENDENCIES = [
    # Caffeine is used for the leasing logic in the server.
    {"groupId": "com.github.ben-manes.caffeine", "artifactId": "caffeine", "version": CAFFEINE_VERSION},
    # MapStruct is used for the DTO mapping logic in the server.
    {"groupId": "org.mapstruct", "artifactId": "mapstruct", "version": MAPSTRUCT_VERSION},
]

CLIENT_REQUIRED_DEPENDENCIES = []


class BuildFile(ABC):
    """Abstract base class for build file manipulation."""
    def __init__(self, path: str, java_version: str, output_path: Optional[str] = None, mode: str = "client"):
        self.path = path
        self.java_version = java_version
        self.output_path = output_path or path
        self.is_modified = False
        self._backup_path = None
        self.mode = mode
        self.logger = logging.getLogger("monomorph")

    def _get_java_version_as_int(self) -> int:
        """Converts the Java version string to an integer for comparison."""
        pattern = r"(1\.)?(\d+)"
        match = re.match(pattern, self.java_version)
        if match:
            return int(match.group(2))
        else:
            raise ValueError(f"Invalid Java version: {self.java_version}")

    @abstractmethod
    def parse(self) -> None:
        """Load and parse the build file."""
        pass

    @abstractmethod
    def save(self, backup: bool = False) -> None:
        """Save the changes back to the build file, optionally creating a backup."""
        pass

    @abstractmethod
    def has_dependency(self, group_id: str, artifact_id: str) -> bool:
        """Check if a specific dependency exists."""
        pass

    @abstractmethod
    def add_dependency(self, dep_info: dict[str, Any]) -> None:
        """Add a dependency if it doesn't exist."""
        pass

    def add_all_dependencies(self):
        """Add all required dependencies."""
        java_version_int = self._get_java_version_as_int()
        # Exclude javax.annotation-api if Java version is < 9
        if java_version_int < 9:
            dependencies = [dep for dep in REQUIRED_DEPENDENCIES if dep["artifactId"] != "javax.annotation-api"]
        else:
            dependencies = REQUIRED_DEPENDENCIES.copy()
        if self.mode in ["server", "both"]:
            dependencies.extend(SERVER_REQUIRED_DEPENDENCIES)
        if self.mode in ["client", "both"]:
            dependencies.extend(CLIENT_REQUIRED_DEPENDENCIES)
        dependencies = self._include_children_dependencies(dependencies)
        # Remove duplicates based on groupId and artifactId
        dependency_map = {f"{dep['groupId']}:{dep['artifactId']}": dep for dep in dependencies}
        dependencies = list(dependency_map.values())
        for dep in dependencies:
            self.add_dependency(dep)

    @abstractmethod
    def has_plugin(self, group_id: str, artifact_id: str) -> bool:
        """Check if a specific build plugin exists."""
        pass

    @abstractmethod
    def add_plugin(self, plugin_info: dict[str, Any]) -> None:
        """Add a build plugin if it doesn't exist."""
        pass

    @abstractmethod
    def add_plugins(self) -> None:
        """Add build plugins."""
        pass

    @abstractmethod
    def has_extension(self, group_id: str, artifact_id: str) -> bool:
        """Check if a specific build extension exists."""
        pass

    @abstractmethod
    def add_extension(self) -> None:
        """Add a build extension if it doesn't exist."""
        pass

    # @abstractmethod
    # def update_java_version_in_compiler_plugin(self) -> None:
    #     """Update the Java source/target version in the compiler plugin *if* it exists."""
    #     pass

    def create_backup(self) -> bool:
        """Create a backup of the build file."""
        self._backup_path = self.output_path + ".bak"
        try:
            self.logger.debug(f"Creating backup: {self._backup_path}")
            os.makedirs(os.path.dirname(self._backup_path), exist_ok=True)
            shutil.copy2(self.path, self._backup_path)  # copy2 preserves metadata
        except Exception as e:
            self.logger.error(f"Error creating backup: {e}. Save aborted.")
            return False  # Abort save if backup fails
        return True

    def delete_backup(self) -> None:
        """Delete the backup file."""
        if self._backup_path and os.path.exists(self.output_path):
            try:
                self.logger.debug(f"Deleting backup: {self._backup_path}")
                os.remove(self._backup_path)
                self._backup_path = None
            except Exception as e:
                self.logger.error(f"Error deleting backup: {e}")

    def _include_children_dependencies(self, dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Can be overridden in subclasses if needed to include additional dependencies
        return dependencies
