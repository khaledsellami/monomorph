import logging

from .buildfile import BuildFile
from .maven import MavenPomFile
from .gradle import GradleBuildFile


class GrpcDependencyHandler:
    def __init__(self, dependency_file: str, java_version: str, output_path: str,
                 build_tool: str = "maven", backup: bool = False, mode: str = "client"):
        self.dependency_file = dependency_file
        self.java_version = java_version
        self.backup = backup
        self.output_path = output_path
        self.build_tool = build_tool.lower()
        self._added_dependencies = False
        self.mode = mode
        self.logger = logging.getLogger("monomorph")
        self.build_file = self._load_build_file()

    def _load_build_file(self) -> BuildFile:
        """Load the appropriate BuildFile implementation based on build tool."""
        if self.build_tool == "maven":
            return MavenPomFile(self.dependency_file, self.java_version, self.output_path, mode=self.mode)
        elif self.build_tool == "gradle":
            return GradleBuildFile(self.dependency_file, self.java_version, self.output_path, mode=self.mode)
        else:
            raise ValueError(f"Unsupported build tool: {self.build_tool}")

    def add_dependencies(self):
        """Add required dependencies for gRPC."""
        if self._added_dependencies:
            return
        self.logger.debug(f"Analyzing {self.build_file.path}...")
        self.build_file.parse()
        # --- Add Dependencies ---
        self.logger.debug("Adding gRPC dependencies...")
        self.build_file.add_all_dependencies()
        # --- Add Plugins/Extensions ---
        self.logger.debug("Adding gRPC build extension...")
        self.build_file.add_extension()
        self.logger.debug("Adding gRPC build plugins...")
        self.build_file.add_plugins()
        # Save if changes were made
        self.build_file.save(backup=self.backup)
        self._added_dependencies = True
