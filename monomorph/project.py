import os
import shutil
import logging
import tempfile
import re
import uuid
import weakref
from typing import Optional

from .helpers import HelperManager
from .models import UpdatedDecomposition, UpdatedPartition
from .microservice import MicroserviceDirectory
from .analysis.model import AppModel
from .assembly.dependency import GrpcDependencyHandler
from .assembly.imports.grpc import GrpcRefactorClient
from .assembly.entrypoint import JavaEntrypointDetector


class MicroservicesProject:
    RPC_TYPE = "grpc"
    BASE_PORT = 50100

    def __init__(self, app_name: str, package_name: str, decomposition: UpdatedDecomposition, source_dir: str,
                 output_path: str, helper_manager: HelperManager, build_tool: str = "maven", java_version: str = "11",
                 directory_name: Optional[str] = None):
        # Assumption: Programming language is Java and granularity is at the class level
        assert build_tool in ["maven", "gradle"]
        self.app_name = app_name
        self.package_name = package_name
        self.decomposition = decomposition
        self.source_dir = source_dir
        self.output_path = output_path
        self.helper_manager = helper_manager
        self.build_tool = build_tool
        self.java_version = java_version
        self.directory_name = directory_name or app_name
        self.project_path = os.path.join(self.output_path, self.directory_name)
        self.microservices: dict[str, MicroserviceDirectory] = {}
        self.dependency_file = None
        self.dockerfile = None
        self.source_root = None
        self._tempdir = None
        self.service_config = {}
        self.dependency_file_copy: dict[str, dict[str, None | str | bool]] = {
            mode: {"path": None, "updated": False} for mode in ["server", "client", "both"]
        }
        self.logger = logging.getLogger("monomorph")
        self.create_project()

    def create_project(self):
        self.init_main_project()
        for i, partition in enumerate(self.decomposition.partitions):
            self.add_microservice(partition, i)
        self.dependency_file, self.source_root = self.find_dependency_file()
        self.dockerfile = self.find_dockerfile()
        self.copy_resources()
        self.copy_source_code()
        self._create_temp_dir()
        self.copy_dependency_file()
        for microservice in self.microservices.values():
            microservice.register_dependency_file(self.dependency_file)

    def _create_temp_dir(self):
        self._tempdir = tempfile.TemporaryDirectory()
        weakref.finalize(self, self._cleanup, self._tempdir.name)

    def _cleanup(self, path):
        """Cleanup function in case object is not properly deleted"""
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)

    def __del__(self):
        """Ensure cleanup on garbage collection"""
        self._tempdir.cleanup()

    def copy_dependency_file(self):
        for mode in self.dependency_file_copy:
            # each mode has its own copy of the dependency file
            new_path = os.path.join(self._tempdir.name, mode, os.path.basename(self.dependency_file))
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            self.logger.debug(f"Copying {self.dependency_file} to {new_path}")
            shutil.copyfile(self.dependency_file, new_path)
            self.dependency_file_copy[mode]["path"] = new_path

    def copy_source_code(self):
        for microservice in self.microservices.values():
            microservice.copy_source_code(self.source_root)

    def find_dependency_file(self) -> tuple[str, str]:
        if self.build_tool == "maven":
            # TODO: currently using a simple heuristic to find the dependency file
            pom_file = os.path.join(self.source_dir, "pom.xml")
            source_root = os.path.join(self.source_dir, "src", "main", "java")
            assert os.path.exists(pom_file)
            assert os.path.exists(source_root)
            return pom_file, self.source_dir
        elif self.build_tool == "gradle":
            # TODO: currently using a simple heuristic to find the dependency file
            build_file = os.path.join(self.source_dir, "build.gradle")
            source_root = os.path.join(self.source_dir, "src", "main", "java")
            assert os.path.exists(build_file)
            assert os.path.exists(source_root)
            return build_file, self.source_dir
        else:
            raise NotImplementedError(f"Build tool {self.build_tool} is not supported.")

    def find_dockerfile(self) -> Optional[str]:
        # assumes the Dockerfile is named "Dockerfile" and is located in the root of the project
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file == "Dockerfile":
                    return os.path.join(root, file)
        return None

    def init_main_project(self):
        if os.path.exists(self.project_path):
            self.logger.warning(f"Project {self.app_name} already exists at {self.project_path}. Deleting it.")
            shutil.rmtree(self.project_path)
        os.makedirs(self.project_path)

    def add_microservice(self, partition: UpdatedPartition, idx: int = 0):
        microservice = MicroserviceDirectory(partition.name, self.package_name, self.project_path, partition,
                                             self.helper_manager, build_tool=self.build_tool, idx=idx)
        self.microservices[microservice.uid] = microservice

    def copy_resources(self):
        # Currently, this copies all files except the source code files in the microservices
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(".java"):
                    continue
                self.logger.debug(f"Copying {root}/{file} to {self.project_path}")
                for microservice in self.microservices.values():
                    relative_path = re.sub(rf"{self.source_dir}/?", "", root)
                    microservice.add_file(relative_path, file, self.source_dir)

    def add_dependency(self, microservice_name: str, mode: str = "client"):
        assert self.dependency_file_copy[mode]["path"] is not None
        microservice: MicroserviceDirectory = self.microservices[microservice_name]
        if microservice.dependency_mode:
            if microservice.dependency_mode in [mode, "both"]:
                return
            else:
                self.logger.debug(f"Replacing dependency file mode {microservice.dependency_mode} only with both "
                                  f"for microservice {microservice.uid}.")
                mode = "both"
                assert self.dependency_file_copy[mode]["path"] is not None
        if not self.dependency_file_copy[mode]["updated"]:
            self.update_dependency_file(mode)
        self.logger.debug(f"Adding dependency {self.RPC_TYPE} dependency to microservice {microservice_name} "
                          f"in {mode} mode")
        microservice.update_dependency_file(self.dependency_file_copy[mode]["path"], mode)

    def update_dependency_file(self, mode: str = "client") -> bool:
        self.logger.debug(f"Updating dependency file for {'server and client' if mode == 'both' else mode} mode")
        GrpcDependencyHandler(self.dependency_file, self.java_version, build_tool=self.build_tool, mode=mode,
                              output_path=self.dependency_file_copy[mode]["path"]).add_dependencies()
        self.logger.debug("Updating dependency file for client")
        return os.path.exists(self.dependency_file_copy[mode]["path"])

    def apply_import_changes(self):
        with GrpcRefactorClient(self.source_dir) as grpc_client:
            n_changes = 0
            for microservice in self.microservices.values():
                self.logger.debug(f"Applying import changes for microservice {microservice.uid}")
                import_changes_plan = dict(microservice.import_plan)

                def apply_changes_callback(target_class: str, source_code: Optional[str], error: Optional[str]):
                    nonlocal microservice, n_changes
                    if error:
                        self.logger.error(f"Error applying changes to {target_class}: {error}")
                    n_changes += int(source_code is not None)
                    microservice.apply_import_changes(target_class, source_code)

                grpc_client.refactor_batch_all_stream(import_changes_plan, callback=apply_changes_callback)
            self.logger.info(f"Applied {n_changes} import changes across all microservices.")

    def create_entrypoints(self, analysis_model: AppModel):
        # Create the configuration mapping for each microservice
        services_config, class_mapping = self.create_config_mapping()
        # Find original entry point class
        entrypoint_class, entrypoint_per_ms = self.find_entrypoint_class(analysis_model)
        # Create the new entry point for each microservice
        for ms_name, microservice in self.microservices.items():
            # Generate the shared helpers for the microservice
            microservice.generate_shared_helpers(services_config, class_mapping)
            # Generate the entry point classes
            service_conf = services_config[ms_name]
            microservice.create_entrypoint(entrypoint_per_ms[ms_name], service_conf)

    def create_config_mapping(self) -> tuple[dict, dict]:
        service_config = {}
        class_mapping = {}
        for i, ms_name in enumerate(self.microservices):
            microservice = self.microservices[ms_name]
            ms_uid = microservice.uid
            ms_port = microservice.port
            service_config[ms_name] = {
                "default_host": "localhost",
                "var_host": f"{ms_uid.upper()}_HOST",
                "default_port": ms_port,
                "var_port": f"{ms_uid.upper()}_PORT",
                "service_id_var": f"{ms_uid.upper()}_SID",
                "uid": ms_uid,
                "exposes_service": microservice.exposes_services(),
            }
            for class_file, class_info in microservice.new_server.items():
                if not class_info.get("full_name", False):
                    continue
                class_name = class_info["full_name"].split(".")[-1]
                original_name = class_info["original_name"].split(".")[-1]
                if class_name in class_mapping:
                    self.logger.warning(f"Class {class_name} already exists in the mapping ({ms_uid} and "
                                        f"{class_mapping[class_name['ms_uid']]}).")
                class_var = f"{class_name.upper()}_CID"
                class_id = str(uuid.uuid4())[:8]
                class_mapping[class_name] = dict(
                    class_name=class_name,
                    env_var=class_var,
                    default_id=class_id,
                    ms_uid=ms_uid,
                    key=original_name,
                )
        return service_config, class_mapping

    def find_entrypoint_class(self, analysis_model: AppModel) -> tuple[Optional[str], dict[str, Optional[str]]]:
        """
        Find the entry point class for each microservice in the decomposition.

        :return: A tuple containing the entry point class and a dictionary mapping microservices to their entry point classes.
        """
        pom_file, gradle_file = None, None
        if self.build_tool == "maven":
            pom_file = self.dependency_file
        elif self.build_tool == "gradle":
            gradle_file = self.dependency_file
        dockerfile = self.dockerfile
        entrypoint_detector = JavaEntrypointDetector(analysis_model, pom_file, gradle_file, dockerfile)
        entrypoint_class = entrypoint_detector.find_entrypoint()
        entrypoint_per_ms = {}
        for ms_name, microservice in self.microservices.items():
            entrypoint_per_ms[ms_name] = entrypoint_class if entrypoint_class in microservice.class_file_map else None
        return entrypoint_class, entrypoint_per_ms

    def to_uid(self, name: str) -> str:
        """
        Convert the name of a microservice to its UID.
        """
        for microservice in self.microservices.values():
            if name == microservice.name:
                return microservice.uid
        raise ValueError(f"Microservice {name} not found in the project.")

    def save_tracing_details(self, path: str):
        """
        Save the tracing details of the microservices to files.
        """
        self.logger.info(f"Saving tracing details to {path}")
        for ms_name, microservice in self.microservices.items():
            microservice.save_tracing_details(path)



