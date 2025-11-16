import json
import os
import shutil
import logging
import uuid
import re
from collections import defaultdict
from typing import Optional

from .helpers import HelperManager
from .models import UpdatedPartition
from .generation.models import NewFile, ProtoSolution, GRPCSolution2
from .assembly.entrypoint import EntryPointGenerator


class MicroserviceDirectory:
    PREFIX = "ms_"
    RPC_TYPE = "grpc"
    CLASS_PREFIX = "MonoMorph"
    START_PORT = 50051
    SERVICE_REGISTRY = HelperManager.SERVICE_REGISTRY_TEMPLATE
    CLASSID_REGISTRY = HelperManager.CLASSID_REGISTRY_TEMPLATE
    ID_MAPPER = HelperManager.ID_MAPPER_TEMPLATE

    def __init__(self, name: str, package_name: str, output_path: str, partition: UpdatedPartition,
                 helper_manager: HelperManager, build_tool: str = "maven", idx: int = 0):
        self.name = name
        self.package_name = package_name
        self.output_path = output_path
        self.partition = partition
        self.build_tool = build_tool
        self.helper_manager = helper_manager
        self.idx = idx
        self.class_file_map = {}
        self.file_map = {}
        self.uid = self.make_shell_safe(self.name)
        self.port = self.START_PORT + idx
        self.directory_path = os.path.join(output_path, self.uid)
        self.source_root = os.path.join(self.directory_path, "src", "main", "java")
        self.mid = uuid.uuid4()
        self.init_microservice()
        self._new_proto = dict()
        self.new_server = dict()
        self._new_client = dict()
        self._new_other = dict()
        self.import_plan = defaultdict(dict)
        self.dependency_mode: Optional[str] = None
        self._entrypoint_grpc_details = None
        self._combined_main_details = None
        self._old_entrypoint_class = None
        self._new_main = None
        self.dependency_file = None
        self._included_helpers = dict()
        self._generated_helpers = dict()
        self.logger = logging.getLogger("monomorph")

    def init_microservice(self):
        if os.path.exists(self.directory_path):
            self.logger.warning(f"Microservice {self.uid} already exists at {self.directory_path}. Deleting it.")
            shutil.rmtree(self.directory_path)
        os.makedirs(self.directory_path)

    def add_file(self, relative_path: str, filename: str, source_root: str) -> str:
        source_path = os.path.join(source_root, relative_path, filename)
        destination_path = os.path.join(self.directory_path, relative_path, filename)
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        self.logger.debug(f"Copying {source_path} to {destination_path}")
        shutil.copyfile(source_path, destination_path)
        self.file_map[source_path] = destination_path
        return destination_path

    def copy_class(self, class_name: str, source_root: str) -> None:
        if re.match(r".*\$\d*", class_name):
            # Skip anonymous classes
            self.class_file_map[class_name] = None
            return
        package = class_name.split(".")[:-1]
        simple_name = class_name.split(".")[-1]
        class_file = f"{simple_name}.java"
        relative_path = os.path.join("src", "main", "java", *package)
        if not os.path.exists(os.path.join(source_root, relative_path, class_file)):
            relative_path = os.path.join("src", "test", "java", *package)
            if not os.path.exists(os.path.join(source_root, relative_path, class_file)):
                self.logger.error(f"Class {class_name} not found in source directory or test directory.")
                # raise FileNotFoundError(f"Class {class_name} not found in source directory or test directory.")
                return
        target = self.add_file(relative_path, class_file, source_root)
        self.class_file_map[class_name] = target

    def copy_source_code(self, source_root: str):
        for class_name in self.partition.classes:
            self.copy_class(class_name, source_root)
        for class_name, original_service in self.partition.duplicated_classes:
            self.copy_class(class_name, source_root)

    def add_proto(self, proto_file: NewFile, original_class, tracing_details: Optional[dict] = None) -> None:
        if proto_file.file_name in self._new_proto:
            self.logger.warning(f"Proto file {proto_file.file_name} already exists in microservice {self.uid}.")
            return
        self.logger.debug(f"Adding proto file {proto_file.file_name} to microservice {self.uid}")
        fqn, path = self.create_file(proto_file)
        content: ProtoSolution = proto_file.content
        if tracing_details is not None and "contract" in tracing_details:
            prompt = tracing_details.get("contract")[0]
        else:
            prompt = ""
        self._new_proto[proto_file.file_name] = dict(
            full_name=fqn,
            path=path,
            file_name=proto_file.file_name,
            original_class=original_class,
            explanation=content.explanation,
            comments=content.additional_comments,
            service_name=content.service_name,
            prompt=prompt,
        )

    def update_dependency_file(self, dependency_file: str, mode: str = "client"):
        shutil.copyfile(dependency_file, self.dependency_file)
        self.dependency_mode = mode

    def register_dependency_file(self, dependency_file: str):
        self.dependency_file = self.file_map.get(dependency_file)

    def add_server(self, server_file: Optional[NewFile], proto_file: NewFile, original_class: str,
                   mapper_file: Optional[NewFile] = None, tracing_details: Optional[dict] = None) -> Optional[dict]:
        if server_file and original_class in self.new_server:
            self.logger.warning(f"Server file {server_file.file_name} already exists in microservice {self.uid}.")
            return self.new_server[original_class]
        mapper_fqn, mapper_path = None, None
        mapper_explanation = "Mapper class to convert between local and DTO classes."
        if mapper_file and proto_file.file_name not in self._new_proto:
            self.logger.debug(f"Adding mapper file {mapper_file.file_name} corresponding to class {original_class} "
                              f"in microservice {self.uid}")
            mapper_fqn, mapper_path = self.create_file(mapper_file)
            self._new_other[original_class] = dict(
                original_class=original_class,
                mapper_path=mapper_path,
                mapper_full_name=mapper_fqn,
                explanation=mapper_explanation,
            )
        self.add_proto(proto_file, original_class, tracing_details=tracing_details)
        if server_file is None:
            # The DTO approach might return None for the server file if it is not needed
            self._new_other[original_class] = dict(
                original_class=original_class,
                mapper_path=mapper_path,
                mapper_full_name=mapper_fqn,
                explanation=mapper_explanation,
            )
            return None
        self.logger.debug(f"Adding server file {server_file.file_name} to microservice {self.uid}")
        self.add_helpers(is_server=True)
        fqn, path = self.create_file(server_file)
        content: GRPCSolution2 = server_file.content
        if tracing_details is not None and "server" in tracing_details:
            server_prompt = tracing_details.get("server")[0]
        else:
            server_prompt = ""
        self.new_server[original_class] = dict(
            full_name=fqn,
            path=path,
            file_name=server_file.file_name,
            original_class=original_class,
            explanation=content.explanation,
            comments=content.additional_comments,
            mapper_path=mapper_path,
            mapper_full_name=mapper_fqn,
            prompt=server_prompt,
        )
        return self.new_server[original_class]

    def add_client(self, client_file: NewFile, proto_file: NewFile, original_class: str, is_dto: bool = False,
                   tracing_details: Optional[dict] = None, ms_name: Optional[str] = None) -> (str, str):
        if client_file.file_name in self._new_client:
            self.logger.warning(f"Client file {client_file.file_name} already exists in microservice {self.uid}.")
            return self._new_client[client_file.file_name]
        self.logger.debug(f"Adding client file {client_file.file_name} to microservice {self.uid}")
        self.add_proto(proto_file, original_class, tracing_details=tracing_details)
        self.add_helpers(is_server=False)
        fqn, path = self.create_file(client_file)
        content: GRPCSolution2 = client_file.content
        if tracing_details is not None and ms_name is not None and "client" in tracing_details and ms_name in tracing_details["client"]:
            prompt = tracing_details["client"][ms_name][0]
        else:
            prompt = ""
        self._new_client[client_file.file_name] = dict(
            full_name=fqn,
            path=path,
            file_name=client_file.file_name,
            original_class=original_class,
            explanation=content.explanation,
            comments=content.additional_comments,
            is_dto=is_dto,
            prompt=prompt,
        )
        return self._new_client[client_file.file_name]

    def create_file(self, new_file: NewFile) -> tuple[str, str]:
        """
        Create a new file in the microservice directory.
        :param new_file: The new file to be created.

        :return:
            - qualified_name: The fully qualified name of the new file.
            - save_path: The path where the new file is saved.
        """
        file_path = new_file.file_path
        content: str
        package_name: str
        match new_file.content:
            case str():
                content = new_file.content
                relative_path = ".".join(new_file.file_path.split(os.sep)[4:])
                qualified_name = f"{relative_path}.{new_file.file_name.split('.')[0]}"
            case ProtoSolution():
                content = new_file.content.proto_code
                service_name = new_file.content.service_name
                qualified_name = ".".join([self.extract_proto_package(content), service_name])
            case GRPCSolution2():
                content = new_file.content.source_code
                package_name = new_file.content.package_name
                class_name = new_file.content.class_name
                qualified_name = ".".join([package_name, class_name])
            case _:
                raise ValueError(f"Unexpected content type: {type(new_file.content)}")

        save_path = os.path.join(file_path.format(ms_root=self.directory_path), new_file.file_name)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        assert not os.path.exists(save_path)
        self.logger.debug(f"Creating file {save_path}")
        with open(save_path, "w") as f:
            f.write(content)
        return qualified_name, save_path

    def add_helpers(self, is_server: bool):
        self.logger.debug(f"Adding helpers for microservice {self.uid}")
        self._included_helpers = self.helper_manager.add_all_helpers(self.directory_path, is_server)

    def replace_imports(self, target_class: str, old_class: str, new_class: str):
        if target_class in self.class_file_map and old_class != new_class:
            self.logger.debug(f"Planning to replace import {old_class} with {new_class} in {target_class}")
            self.import_plan[target_class][old_class] = new_class

    def apply_import_changes(self, target_class: str, source_code: Optional[str] = None):
        if target_class in self.class_file_map and source_code:
            file_path = self.class_file_map[target_class]
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File {file_path} does not exist.")
            self.logger.debug(f"Applying import changes to {file_path}")
            with open(file_path, "w") as f:
                f.write(source_code)

    def create_entrypoint(self, old_entrypoint_class: Optional[str], service_conf: Optional[dict] = None) -> (
            tuple)[Optional[dict], Optional[dict], Optional[str]]:
        """
        :param old_entrypoint_class: The old entrypoint class to be combined with the new one if available.
        :param service_conf: The service configuration for the microservice.
        :return:
            - entrypoint_grpc_details: A dictionary containing the details of the entrypoint class.
            - combined_main_details: A dictionary containing the details of the combined main class.
            - new_main: The fully qualified name of the new main class.
        """
        if self._entrypoint_grpc_details and self._new_main:
            self.logger.warning(f"Entrypoint already created for microservice {self.uid}.")
            return self._entrypoint_grpc_details, self._combined_main_details, self._new_main
        fqn = self._create_grpc_entrypoint(service_conf)
        if not fqn:
            if old_entrypoint_class:
                self._old_entrypoint_class = old_entrypoint_class
            return None, None, None
        if old_entrypoint_class:
            self._old_entrypoint_class = old_entrypoint_class
            combined_fqn = self._create_combined_entrypoint(old_entrypoint_class, fqn)
            self._new_main = combined_fqn
            self.logger.debug(f"Combined main class created: {combined_fqn}")
        else:
            self.logger.debug(f"New entrypoint class created: {fqn}")
            self._new_main = fqn
        return self._entrypoint_grpc_details, self._combined_main_details, self._new_main

    def _create_combined_entrypoint(self, old_entrypoint_class: Optional[str], fqn: str) -> Optional[str]:
        if not old_entrypoint_class:
            return None
        ms_name = self.uid
        package_name = ".".join([self.package_name, "monomorph"])
        self.logger.info(f"Creating a new main class combining {fqn} and {old_entrypoint_class}.")
        combined_class_name = f"{self.CLASS_PREFIX}{ms_name.capitalize()}Main"
        combined_main = EntryPointGenerator(self.helper_manager).generate_combined_entry_point(
            class_name=combined_class_name,
            package_name=package_name,
            old_main=old_entrypoint_class,
            grpc_main=fqn
        )
        combined_file = NewFile(
            file_name=f"{combined_class_name}.java",
            file_path=os.path.join("{ms_root}", "src", "main", "java", *package_name.split(".")),
            content=combined_main
        )
        combined_fqn, combined_path = self.create_file(combined_file)
        self._combined_main_details = {
            "class_name": combined_class_name,
            "full_name": combined_fqn,
            "path": combined_path,
            "package_name": package_name,
            "entrypoint_code": combined_main,
            "old_main": old_entrypoint_class,
            "grpc_main": fqn,
            "explanation": "A new entrypoint class that combines the old entrypoint of the monolith and the new "
                           "gRPC server class"
        }
        return combined_fqn

    def _create_grpc_entrypoint(self, service_conf: Optional[dict] = None) -> Optional[str]:
        # services = [service_details["full_name"] for service, service_details in self.new_server.items() if "full_name" in service_details]
        # services without mapper files correspond to DTOs
        services = [
            {
                "full_name": service_details["full_name"],
                "simple_name": service_details["full_name"].split(".")[-1],
                "is_dto": "mapper_path" in service_details and service_details["mapper_path"] is not None
            }
            for service, service_details in self.new_server.items() if "full_name" in service_details
        ]
        if not services:
            self.logger.debug(f"Skipping  microservice {self.name} ({self.uid}): no gRPC services found.")
            return None
        ms_name = self.uid
        package_name = self.helper_manager.get_package_name(self.helper_manager.GRPC_SERVER_MAIN_TEMPLATE)
        class_name = f"{self.CLASS_PREFIX}{ms_name.capitalize()}ServerGRPC"
        port = self.port
        env_var_name = f"{self.uid.upper()}_PORT"
        if service_conf:
            port = service_conf.get("default_port", port)
            env_var_name = service_conf.get("var_port", env_var_name)
        entrypoint_code = EntryPointGenerator(
            self.helper_manager).generate_grpc_entry_point(ms_name, package_name, class_name, services,
                                                           port, env_var_name)
        new_file = NewFile(
            file_name=f"{class_name}.java",
            file_path=os.path.join("{ms_root}", "src", "main", "java", *package_name.split(".")),
            content=entrypoint_code
        )
        fqn, path = self.create_file(new_file)
        self._entrypoint_grpc_details = {
            "class_name": class_name,
            "full_name": fqn,
            "path": path,
            "package_name": package_name,
            "entrypoint_code": entrypoint_code,
            "port": self.port,
            "env_var_name": env_var_name,
            "explanation": "A Server class with a main method that initializes and exposes the new gRPC services"
        }
        return fqn

    def extract_proto_package(self, proto_source: str) -> str:
        pattern = re.compile(r"package\s+([^;]+);")
        match = pattern.search(proto_source)
        if match:
            return match.group(1)
        return ""

    def build_dockerfile(self, dockerfile_path: str):
        raise NotImplementedError("Dockerfile generation is not implemented yet.")

    def generate_shared_helpers(self, service_mapping: dict, class_mapping: dict):
        if len(self._new_client) == 0 and len(self.new_server) == 0:
            self.logger.debug(f"No gRPC services found in microservice {self.uid}. Skipping shared helpers generation.")
            return
        self.logger.debug(f"Generating shared helpers for microservice {self.uid}")
        self.generate_service_registry(service_mapping)
        self.generate_classid_registry(class_mapping)
        self.generate_id_mapper()

    def generate_id_mapper(self):
        self.logger.debug(f"Generating ID mapper for microservice {self.uid}")
        proxies = [dict(
            full_name=client_file["full_name"],
            name=client_file["full_name"].split(".")[-1],
        ) for client_file in self._new_client.values() if not client_file.get("is_dto", False)]
        context = dict(
            package_name=self.helper_manager.get_package_name(self.ID_MAPPER),
            proxies=proxies,
        )
        id_mapper_source = self.helper_manager.render_helper(self.ID_MAPPER, context)
        name = self.helper_manager.helper_mapping[self.ID_MAPPER]["object_name"]
        package_name = self.helper_manager.helper_mapping[self.ID_MAPPER]["package"]
        id_mapper_file = NewFile(
            file_name=f"{name}.java",
            file_path=os.path.join(self.source_root, *package_name.split(".")),
            content=id_mapper_source
        )
        _, path = self.create_file(id_mapper_file)
        self._generated_helpers[name] = (path, self.ID_MAPPER)
        
    def generate_classid_registry(self, class_mapping: dict):
        self.logger.debug(f"Generating class ID registry for microservice {self.uid}")
        context = dict(
            package_name=self.helper_manager.get_package_name(self.CLASSID_REGISTRY),
            classes=class_mapping.values(),
        )
        classid_source = self.helper_manager.render_helper(self.CLASSID_REGISTRY, context)
        name = self.helper_manager.helper_mapping[self.CLASSID_REGISTRY]["object_name"]
        package_name = self.helper_manager.helper_mapping[self.CLASSID_REGISTRY]["package"]
        classid_file = NewFile(
            file_name=f"{name}.java",
            file_path=os.path.join(self.source_root, *package_name.split(".")),
            content=classid_source
        )
        _, path = self.create_file(classid_file)
        self._generated_helpers[name] = (path, self.CLASSID_REGISTRY)

    def generate_service_registry(self, service_mapping: dict):
        this_service_mapping = service_mapping[self.uid]
        context = dict(
            package_name=self.helper_manager.get_package_name(self.SERVICE_REGISTRY),
            services=[s for s in service_mapping.values() if s["exposes_service"]],
            default_service_id=this_service_mapping["uid"],
            service_id_var=this_service_mapping["service_id_var"],
        )
        self.logger.debug(f"Rendering service registry for microservice {self.uid}")
        registry_source = self.helper_manager.render_helper(self.SERVICE_REGISTRY, context)
        name = self.helper_manager.helper_mapping[self.SERVICE_REGISTRY]["object_name"]
        package_name = self.helper_manager.helper_mapping[self.SERVICE_REGISTRY]["package"]
        registry_file = NewFile(
            file_name=f"{name}.java",
            file_path=os.path.join(self.source_root, *package_name.split(".")),
            content=registry_source
        )
        _, path = self.create_file(registry_file)
        self._generated_helpers[name] = (path, self.SERVICE_REGISTRY)

    def exposes_services(self) -> bool:
        """
        Check if the microservice exposes any gRPC services.

        :return: True if the microservice exposes gRPC services, False otherwise.
        """
        return bool(self.new_server)

    def make_shell_safe(self, name: str) -> str:
        """ Convert a string into a shell-safe variable name . """
        if not name:
            return self.PREFIX + str(self.mid)
        # Replace all non-alphanumeric characters with underscores
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Check if the first character is valid (letter or underscore)
        if not re.match(r'^[a-zA-Z_]', safe_name):
            safe_name = self.PREFIX + safe_name
        return safe_name

    def save_tracing_details(self, path: str):
        """
        Save the tracing details of the microservice to a file.
        :param path: The path where the tracing details will be saved.
        """
        tracing_details = {
            "new_proto": self._new_proto,
            "new_server": self.new_server,
            "new_client": self._new_client,
            "new_other": self._new_other,
            "import_plan": self.import_plan,
            "dependency_mode": self.dependency_mode,
            "entrypoint_grpc_details": self._entrypoint_grpc_details,
            "combined_main_details": self._combined_main_details,
            "old_entrypoint_class": self._old_entrypoint_class,
            "new_main": self._new_main,
            "included_helpers": self._included_helpers,
            "generated_helpers": self._generated_helpers
        }
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, f"{self.name}.json"), 'w') as f:
            json.dump(tracing_details, f)


