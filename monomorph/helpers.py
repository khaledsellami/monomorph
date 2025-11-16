import logging
import os
import pathlib
from importlib import resources
from typing import Optional

import jinja2

from .llm.models import Class
from .const import PROTO_PATH


class HelperManager:
    TEMPLATES_DIR: pathlib.Path = resources.files("monomorph.resources").joinpath("templates")
    # --- helper classes for id based refactoring ---
    # helper classes from the previous implementation
    SHARED_PROTO_FILE = "shared.proto"
    # MAPPER_CLASS_FILE = "RefactoredObjectMapper.java"
    # CLIENT_CLASS_FILE = "RefactoredObjectClient.java"
    # FACTORY_CLASS_FILE = "RefactoredObjectFactory.java"
    # current helpers
    # proto files
    LEASING_PROTO_FILE = "leasing.proto"
    SERVICE_PROTO_TEMPLATE = "serviceTemplate.proto"
    # client classes
    LEASING_CLIENT_CLASS_FILE = "LeaseRpcClient.java"
    LEASING_GRPC_CLIENT_CLASS_FILE = "GrpcLeaseRpcClient.java"
    ABSTRACT_CLIENT_CLASS_FILE = "AbstractRefactoredClient.java"
    CLIENT_CLASS_TEMPLATE = "ClientTemplate.java"
    # server classes
    LEASE_KEY = "LeaseKey.java"
    LEASE_MANAGER_CLASS_FILE = "LeaseManager.java"
    LEASE_MANAGER_CAFFEINE_CLASS_FILE = "CaffeineLeaseManager.java"
    LEASE_SERVICE_CLASS_FILE = "LeasingServiceImpl.java"
    SERVICE_IMPLEMENTATION_TEMPLATE = "ServiceImplTemplate.java"
    GRPC_SERVER_MAIN_TEMPLATE = "GrpcMainServerTemplate.java"
    COMBINED_MAIN_TEMPLATE = "CombinedMainTemplate.java"
    SERVER_OBJECT_MANAGER = "ServerObjectManager.java"
    # shared by both server and client
    SERVICE_REGISTRY_TEMPLATE = "ServiceRegistryTemplate.java"
    CLASSID_REGISTRY_TEMPLATE = "ClassIdRegistryTemplate.java"
    ID_MAPPER_TEMPLATE = "IDMapperTemplate.java"
    # --- helper classes for dto based refactoring ---
    DTO_PROTO_TEMPLATE = "dtoServiceTemplate.proto"
    DTO_MAPPER_TEMPLATE = "DtoMapperTemplate.java"
    DTO_CLIENT_TEMPLATE = "DtoClientTemplate.java"
    DTO_SERVICE_IMPLEMENTATION_TEMPLATE = "DtoServiceImplTemplate.java"
    # files whose package names do not follow the common pattern ("shared.<client|server>" if basic
    # else "generated.<client|server>" if template)
    CUSTOM_PACKAGES = {
        # ID files
        LEASING_PROTO_FILE: "shared.leasing",
        SHARED_PROTO_FILE: "shared",
        SERVICE_REGISTRY_TEMPLATE: "generated.helpers",
        CLASSID_REGISTRY_TEMPLATE: "generated.helpers",
        ID_MAPPER_TEMPLATE: "generated.helpers",
        SERVICE_PROTO_TEMPLATE: "generated.proto",
        COMBINED_MAIN_TEMPLATE: "generated.entrypoint",
        GRPC_SERVER_MAIN_TEMPLATE: "generated.entrypoint",
        SERVICE_IMPLEMENTATION_TEMPLATE: "generated.server",
        CLIENT_CLASS_TEMPLATE: "generated.client",
        # ABSTRACT_CLIENT_CLASS_FILE: "shared.client",
        # DTO files
        DTO_PROTO_TEMPLATE: "generated.proto",
        DTO_MAPPER_TEMPLATE: "generated.server",
        DTO_CLIENT_TEMPLATE: "generated.client",
        DTO_SERVICE_IMPLEMENTATION_TEMPLATE: "generated.server",
    }
    CUSTOM_NAMES = {
        # ID files
        LEASING_PROTO_FILE: "LeasingService",
        SHARED_PROTO_FILE: "RefactoredObjectID",
        SERVICE_REGISTRY_TEMPLATE: "ServiceRegistry",
        CLASSID_REGISTRY_TEMPLATE: "ClassIdRegistry",
        ID_MAPPER_TEMPLATE: "IDMapper",
        # DTO files
    }
    DESCRIPTIONS = {
        # ID files
        SHARED_PROTO_FILE: "The proto file that describes the RefactoredObjectID messages required for exchanging instance IDs across microservices.",
        LEASING_PROTO_FILE: "The proto file describing the leasing service api and messages. Required for the leasing/TTL logic.",
        LEASING_CLIENT_CLASS_FILE: "The LeaseRpcClient interface defines the methods that the client microservices can use to interact with the LeaseManager.",
        LEASING_GRPC_CLIENT_CLASS_FILE: "The GrpcLeaseRpcClient class is a gRPC client that implements LeaseRpcClient and that interacts with the LeasingServiceImpl class.",
        ABSTRACT_CLIENT_CLASS_FILE: "The AbstractRefactoredClient class is a base class for all client classes that use the leasing API. It provides the common methods for the generated client classes and incorporates the leasing logic.",
        LEASE_KEY: "The LeaseKey class is used to identify the lease of an object in the leasing system. It is defined by a RefactoredObjectID instance and a clientID (the microservice that is using the instance).",
        LEASE_MANAGER_CLASS_FILE: "The LeaseManager interface defines the methods for managing leases.",
        LEASE_MANAGER_CAFFEINE_CLASS_FILE: "The CaffeineLeaseManager class is an implementation of the LeaseManager interface that uses Caffeine for caching leases in the runtime memory. It implements the leasing logic required for managing the lifecycle of classes across different microservices.",
        LEASE_SERVICE_CLASS_FILE: "The LeasingServiceImpl class is a gRPC service implementation that exposes the leasing API so that client microservices can interact with server microservices and handle the leasing interactions.",
        SERVER_OBJECT_MANAGER: "The ServerObjectManager interface defines the methods for managing the objects to IDs and vice versa.",
        SERVICE_REGISTRY_TEMPLATE: "A utility class that serves as a placeholder for service discovery.",
        CLASSID_REGISTRY_TEMPLATE: "A utility class that defines the CLASSIDs for the classes that are exchanged between microservices.",
        ID_MAPPER_TEMPLATE: "A utility class for mapping a RefactoredObjectID into actual type instances (if the type is in the microservice) or client instances and vice versa.",
        # DTO files
        DTO_PROTO_TEMPLATE: "TODO",
        DTO_MAPPER_TEMPLATE: "TODO",
        DTO_CLIENT_TEMPLATE: "TODO",
        DTO_SERVICE_IMPLEMENTATION_TEMPLATE: "TODO",
    }
    HELPERS_FOR_DTO = {
        DTO_PROTO_TEMPLATE,
        DTO_MAPPER_TEMPLATE,
        DTO_CLIENT_TEMPLATE,
        DTO_SERVICE_IMPLEMENTATION_TEMPLATE
    }

    def __init__(self, base_package_name: str):
        if base_package_name is None:
            raise RuntimeError("base_package_name cannot be None")
        self.base_package_name = base_package_name
        self.package_name = f"{self.base_package_name}.monomorph.id" if self.base_package_name else "monomorph.id"
        self.package_name_dto = f"{self.base_package_name}.monomorph.dto" if self.base_package_name else "monomorph.dto"
        # categorize the helpers
        self.server_helpers = [
            # ID files
            self.LEASE_KEY, self.LEASE_MANAGER_CLASS_FILE, self.LEASE_MANAGER_CAFFEINE_CLASS_FILE,
            self.LEASE_SERVICE_CLASS_FILE, self.SERVICE_IMPLEMENTATION_TEMPLATE, self.GRPC_SERVER_MAIN_TEMPLATE,
            self.COMBINED_MAIN_TEMPLATE, self.SERVER_OBJECT_MANAGER,
            # DTO files
            self.DTO_MAPPER_TEMPLATE, self.DTO_SERVICE_IMPLEMENTATION_TEMPLATE
        ]
        self.client_helpers = [
            # ID files
            self.LEASING_CLIENT_CLASS_FILE, self.LEASING_GRPC_CLIENT_CLASS_FILE, self.CLIENT_CLASS_TEMPLATE,
            self.ABSTRACT_CLIENT_CLASS_FILE,
            # DTO files
            self.DTO_CLIENT_TEMPLATE
        ]
        self.proto_helpers = [self.SHARED_PROTO_FILE, self.LEASING_PROTO_FILE, self.SERVICE_PROTO_TEMPLATE,  # ID proto files
                              self.DTO_PROTO_TEMPLATE]  # DTO proto files
        self.shared_helpers = [self.SERVICE_REGISTRY_TEMPLATE, self.CLASSID_REGISTRY_TEMPLATE, self.ID_MAPPER_TEMPLATE,
                               self.ABSTRACT_CLIENT_CLASS_FILE, self.LEASING_CLIENT_CLASS_FILE,
                               self.LEASING_GRPC_CLIENT_CLASS_FILE, self.SERVER_OBJECT_MANAGER]
        # helper classes that only require the package name to be generated
        self.basic_helpers = [self.SHARED_PROTO_FILE, self.LEASING_PROTO_FILE, self.LEASE_KEY,
                              self.LEASE_MANAGER_CLASS_FILE, self.LEASE_MANAGER_CAFFEINE_CLASS_FILE,
                              self.LEASE_SERVICE_CLASS_FILE, self.LEASING_CLIENT_CLASS_FILE,
                              self.LEASING_GRPC_CLIENT_CLASS_FILE, self.ABSTRACT_CLIENT_CLASS_FILE,
                              self.SERVER_OBJECT_MANAGER]
        self.include_in_id_dto = [self.SERVICE_REGISTRY_TEMPLATE]
        # helpers that require additional information to be generated
        self.template_helpers = [
            # ID templates
            self.SERVICE_IMPLEMENTATION_TEMPLATE, self.GRPC_SERVER_MAIN_TEMPLATE, self.COMBINED_MAIN_TEMPLATE,
            self.CLIENT_CLASS_TEMPLATE, self.SERVICE_REGISTRY_TEMPLATE, self.SERVICE_PROTO_TEMPLATE,
            self.CLASSID_REGISTRY_TEMPLATE, self.ID_MAPPER_TEMPLATE,
            # DTO templates
            self.DTO_PROTO_TEMPLATE, self.DTO_MAPPER_TEMPLATE, self.DTO_CLIENT_TEMPLATE,
            self.DTO_SERVICE_IMPLEMENTATION_TEMPLATE
        ]
        self.helper_mapping = self._map_helpers()
        assert self.TEMPLATES_DIR.exists(), f"Templates directory {self.TEMPLATES_DIR} does not exist."
        self.logger = logging.getLogger("monomorph")
        self._check_all_helpers_exist()

    def get_package_name(self, helper: str) -> str:
        """
        Get the base package name for a helper. (e.g. "monomorph.id.shared" for an ID based helper)
        """
        return self.package_name_dto if helper in self.HELPERS_FOR_DTO else self.package_name

    def _map_helpers(self) -> dict[str, dict[str, str | pathlib.Path]]:
        """
        Map the helper files to their respective classes and paths.
        """
        def get_path(helper_file: str) -> pathlib.Path:
            if helper_file in self.server_helpers:
                return self.TEMPLATES_DIR / "server" / helper_file
            elif helper_file in self.client_helpers:
                return self.TEMPLATES_DIR / "client" / helper_file
            else:
                return self.TEMPLATES_DIR / helper_file

        def get_package(helper_file: str) -> str:
            package_name = self.get_package_name(helper_file)
            if helper_file in self.CUSTOM_PACKAGES:
                return f"{package_name}.{self.CUSTOM_PACKAGES[helper_file]}"
            else:
                return f"{package_name}.{'generated' if helper_file in self.template_helpers else 'shared'}.{'client' if helper_file in self.client_helpers else 'server'}"

        def get_object_name(helper_file: str) -> Optional[str]:
            if helper_file in self.CUSTOM_NAMES:
                return self.CUSTOM_NAMES[helper_file]
            elif helper_file in self.template_helpers:
                return None  # defined by the refactoring logic
            else:
                return helper_file.split(".")[0]

        def get_description(helper_file: str) -> Optional[str]:
            if helper_file not in self.DESCRIPTIONS:
                return None
            if helper_file in self.template_helpers:
                suffix = " It is customized for each microservice."
            else:
                if helper_file in self.shared_helpers:
                    loc = ""
                elif helper_file in self.client_helpers:
                    loc = "client "
                else:
                    loc = "server "
                suffix = f" It is shared by all {loc}microservices."
            return self.DESCRIPTIONS[helper_file] + suffix

        return {
            helper_file: {
                "name": helper_file.split(".")[0],
                "path": get_path(helper_file),
                "file": helper_file,
                "package": get_package(helper_file),
                "object_name": get_object_name(helper_file),
                "source": None,
                "description": get_description(helper_file),
            } for helper_file in set(self.server_helpers + self.client_helpers + self.proto_helpers + self.shared_helpers)
        }

    def _check_all_helpers_exist(self):
        """
        Check if all helper files exist in the templates directory.
        """
        for helper_file in self.helper_mapping:
            if not self.helper_mapping[helper_file]["path"].exists():
                raise FileNotFoundError(f"Helper file {helper_file} not found in templates directory.")

    def _render_template(self, helper: str, context: dict) -> str:
        """
        Generate a file from a template and a context.
        """
        self.logger.debug(f"Rendering template {helper}")
        template_loader = jinja2.FileSystemLoader(searchpath=self.helper_mapping[helper]["path"].parent)
        template_env = jinja2.Environment(loader=template_loader)
        template = template_env.get_template(self.helper_mapping[helper]["file"])
        return template.render(context)

    def render_helper(self, helper: str, context: Optional[dict] = None) -> str:
        """
        Render a basic helper file.
        """
        if helper in self.basic_helpers:
            context = {"package_name": self.get_package_name(helper)}
            return self._render_template(helper, context)
        elif helper in self.template_helpers and context:
            return self._render_template(helper, context)
        else:
            raise ValueError(f"Helper {helper} not found or context not provided.")

    def save_basic_helper(self, helper: str, project_root: str) -> Optional[str]:
        """
        Get the file path of a helper. Assumes that the project uses the "src/main/java" structure.
        """
        assert helper in self.helper_mapping, f"Helper {helper} not found."
        if helper in self.template_helpers:
            raise ValueError(f"Helper {helper} is a template and cannot be saved directly.")
        else:
            helper_details = self.helper_mapping[helper]
            if not self.helper_mapping[helper]["source"]:
                self.helper_mapping[helper]["source"] = self.render_helper(helper)
            if helper in self.proto_helpers:
                # Different path for proto files
                new_file_path = (pathlib.Path(project_root) / PROTO_PATH.replace("/", os.sep) / helper_details["file"])
            else:
                # Path is based on the package name
                source_root = os.path.join(project_root, "src", "main", "java")
                new_file_path = (pathlib.Path(source_root) / helper_details["package"].replace(".", "/") /
                                 helper_details["file"])
            if new_file_path.exists():
                self.logger.debug(f"File {new_file_path} already exists. Skipping.")
            else:
                self.logger.debug(f"Saving helper {helper} to {new_file_path}")
                new_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(new_file_path, "w") as f:
                    f.write(self.helper_mapping[helper]["source"])
            return str(new_file_path)

    def add_all_helpers(self, project_root: str, is_server: bool = False, is_dto: bool = False) -> dict[str, str]:
        """
        Add all helpers to the source root (server or client).
        :param project_root: The root directory of the project. Assumes the structure is "src/main/java".
        :param is_server: Whether to add server or client helpers.
        :return: A dictionary mapping the helper names to their new file paths.
        """
        added_helpers = {}
        helpers_to_add = set((self.server_helpers if is_server else self.client_helpers) + self.shared_helpers +
                             [self.SHARED_PROTO_FILE, self.LEASING_PROTO_FILE])
        helpers_to_add = {h for h in helpers_to_add if (is_dto == (h in self.HELPERS_FOR_DTO)) or
                          h in self.include_in_id_dto}
        for helper in helpers_to_add:
            if helper in self.basic_helpers:
                added_helpers[helper] = self.save_basic_helper(helper, project_root)
        return added_helpers

    def get_as_class(self, helper: str, context: Optional[dict] = None) -> Class:
        """
        Get the helper as a Class object.
        :param helper: The name of the helper.
        :param context: The context for the template.
        :return: The Class object.
        """
        if helper in self.basic_helpers:
            if not self.helper_mapping[helper]["source"]:
                self.helper_mapping[helper]["source"] = self.render_helper(helper)
            name = self.helper_mapping[helper]["object_name"]
            full_name = f"{self.helper_mapping[helper]['package']}.{name}"
            code = self.helper_mapping[helper]["source"]
        elif helper in self.template_helpers and context:
            name = self.helper_mapping[helper]["object_name"]
            full_name = f"{self.helper_mapping[helper]['package']}.{name}" if self.helper_mapping[helper]["package"] else None
            code = self._render_template(helper, context)
        else:
            raise ValueError(f"Helper {helper} not found or context not provided.")
        return Class(name=name, full_name=full_name, code=code)