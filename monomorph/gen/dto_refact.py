import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .models import NewFile
from .id_refact import IDRefact
from ..llm.langchain.prompts.dto_grpc_client import LangChainDTOgRPCClientPrompt
from ..llm.langchain.prompts.dto_grpc_proto import LangChainDTOgRPCProtoPrompt
from ..llm.langchain.prompts.dto_grpc_server import LangChainDTOgRPCServerPrompt
from ..execution.helpers import HelperManager
from ..modeling.model import AppModel
from ..llm.models import Class
from ..planning.proxies import PlannedAPIClass


class DTORefact(IDRefact):
    DTO_PROTO_TEMPLATE = HelperManager.DTO_PROTO_TEMPLATE
    DTO_MAPPER_TEMPLATE = HelperManager.DTO_MAPPER_TEMPLATE
    DTO_CLIENT_TEMPLATE = HelperManager.DTO_CLIENT_TEMPLATE
    DTO_SERVER_TEMPLATE = HelperManager.DTO_SERVICE_IMPLEMENTATION_TEMPLATE

    def __init__(self, analysis_model: AppModel, base_package_name: str, helper_manager: HelperManager,
                 model_name: str = "gpt-4o", responses_path: str = None, parsing_model: str = "ministral-3b",
                 api_classes: dict[str, PlannedAPIClass] = None, id_only: bool = True):
        super().__init__(analysis_model, base_package_name, helper_manager, model_name, responses_path,
                         parsing_model, api_classes, id_only)
        
    def _create_proto_prompt(self, class_: Class, method_names: list[str], context: dict, object_id_class: Class,
                            fields: Optional[list[str]] = None) -> tuple[str, str]:
        fields = fields if fields else []
        proto_template = self.helper_manager.get_as_class(self.DTO_PROTO_TEMPLATE, context)
        references_mapping = self.get_referenced_class_mapping(class_.full_name)
        prompt_gen = LangChainDTOgRPCProtoPrompt(class_, method_names, object_id_class, fields, proto_template,
                                                 references_mapping)
        prompt = prompt_gen.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen.get_prompt_basename(), prompt_gen.get_prompt_type(), class_.name)
        return prompt, suffix

    def generate_proto(self, class_: Class, method_names: list[str], fields: Optional[list[str]] = None) -> (
            tuple)[str, str, NewFile, Class, str]:
        self.logger.debug(f"Generating proto for class {class_.name} with the DTO pattern.")
        # Prepare the context for the proto generation
        api_class = self.api_classes[class_.full_name]
        dto_name = api_class.dto_name
        proto_template_package = api_class.proto_package
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        service_name = api_class.service_name.split(".")[-1]
        context = dict(
            package_name=proto_template_package,
            service_name=service_name if method_names else None,
            class_name=class_.name,
            dto_name=dto_name,
        )
        # Create the proto prompt
        prompt, suffix = self._create_proto_prompt(class_, method_names, context, object_id_class, fields)
        # Generate the proto file
        _, response = self.generate_or_load_response(prompt, suffix)
        # Parse the proto response
        proto_file = self.parse_proto_response(response, class_)
        # Create and return the proto class
        proto_class = Class(service_name, proto_file.content.proto_code,
                            f"{proto_template_package}.{service_name}")
        return prompt, response, proto_file, proto_class, dto_name

    def _create_server_prompt(self, class_: Class, proto_prompt: str, proto_response: str,
                              server_template: Class, mapper_class: Class) -> tuple[str, str]:
        id_mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        id_mapper_class_name = f"{id_mapper_class_details['package']}.{id_mapper_class_details['object_name']}"
        id_mapper_class = Class(id_mapper_class_details['object_name'], "", id_mapper_class_name)
        referenced_classes = self.get_referenced_class_mapping(class_.full_name)
        current_microservice = self.api_classes[class_.full_name].microservice
        prompt_gen_server = LangChainDTOgRPCServerPrompt(proto_prompt, proto_response, server_template, mapper_class,
                                                         id_mapper_class, referenced_classes, current_microservice)
        server_prompt = prompt_gen_server.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_server.get_prompt_basename(), prompt_gen_server.get_prompt_type(), class_.name)
        return server_prompt, suffix


    def generate_server(self, class_: Class, proto_prompt: str, proto_response: str, proto_class: Class,
                        dto_name: [Optional] = None, method_names: Optional[list[str]] = None) -> (
            tuple)[str, str, Optional[NewFile], NewFile]:
        dto_name = dto_name if dto_name else f"{class_.name}DTO"
        mapper_file, mapper_class = self.generate_mapper(class_, proto_class, dto_name)
        if not method_names:
            self.logger.debug(f"class {class_.name} has no methods to expose. Skipping DTO server generation.")
            return "", "", None, mapper_file
        self.logger.debug(f"Generating server for class {class_.name} with the DTO pattern.")
        server_template = self.create_server_template(class_, proto_class, dto_name, mapper_class)
        server_prompt, suffix = self._create_server_prompt(class_, proto_prompt, proto_response, server_template,
                                                           mapper_class)
        _, server_response = self.generate_or_load_response(server_prompt, suffix)
        server_file = self.parse_server_client_response(server_response, class_, server_template, suffix="dto_server")
        return server_prompt, server_response, server_file, mapper_file

    def create_server_template(self, class_: Class, proto_class: Class, dto_name: str, mapper_class: Class) -> Class:
        api_class = self.api_classes[class_.full_name]
        impl_full_name = api_class.server_name
        impl_name = impl_full_name.split(".")[-1]
        package_name = self.helper_manager.get_package_name(self.DTO_SERVER_TEMPLATE)
        grpc_service = dict(
            impl_name=impl_name,
            name=proto_class.name,
            package_name=".".join(proto_class.full_name.split(".")[:-1]),
        )
        context = dict(
            package_name=package_name,
            grpc_service=grpc_service,
            original_class=class_,
            dto_name=dto_name,
            mapper_class=mapper_class,
        )
        server_template = self.helper_manager.get_as_class(self.DTO_SERVER_TEMPLATE, context)
        server_template.name = impl_name
        server_template.full_name = impl_full_name
        return server_template
    
    def generate_mapper(self, class_: Class, proto_class: Class, dto_name: str) -> tuple[NewFile, Class]:
        api_class = self.api_classes[class_.full_name]
        mapper_full_name = api_class.mapper_name
        package_name = self.helper_manager.get_package_name(self.DTO_MAPPER_TEMPLATE)
        proto_package = ".".join(proto_class.full_name.split(".")[:-1])
        original_class = class_
        mapper_name = mapper_full_name.split(".")[-1]
        dto_class = dict(name=dto_name, full_name=f"{proto_package}.{dto_name}")
        mapper_class = dict(name=mapper_name)
        context = dict(
            package_name=package_name,
            original=original_class,
            dto=dto_class,
            mapper=mapper_class,
        )
        gen_mapper_class = self.helper_manager.get_as_class(self.DTO_MAPPER_TEMPLATE, context)
        gen_mapper_class.name = mapper_name
        mapper_package = ".".join(gen_mapper_class.full_name.split(".")[:-1])
        gen_mapper_class.full_name = f"{mapper_package}.{mapper_name}"
        path = os.path.join("{ms_root}", "src", "main", "java", *gen_mapper_class.full_name.split(".")[:-1])
        mapper_file = NewFile(
            content=gen_mapper_class.code,
            file_name=f"{mapper_name}.java",
            file_path=path
        )
        return mapper_file, gen_mapper_class

    def _create_client_prompt(self, class_: Class, proto_prompt: str, proto_response: str, client_template: Class,
                             client_ms: str, dto_name: [Optional] = None) -> tuple[str, str]:
        dto_name = dto_name if dto_name else f"{class_.name}DTO"
        id_mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        id_mapper_class_name = f"{id_mapper_class_details['package']}.{id_mapper_class_details['object_name']}"
        id_mapper_class = Class(id_mapper_class_details['object_name'], "", id_mapper_class_name)
        referenced_classes = self.get_referenced_class_mapping(class_.full_name)
        prompt_gen_client = LangChainDTOgRPCClientPrompt(proto_prompt, proto_response, client_template, dto_name,
                                                         id_mapper_class, referenced_classes, client_ms)
        client_prompt = prompt_gen_client.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_client.get_prompt_basename(), prompt_gen_client.get_prompt_type(),
                              client_ms, class_.name)
        return client_prompt, suffix

    def generate_client(self, class_: Class, proto_prompt: str, proto_response: str, proto_class: Class,
                        microservice_uid: str, client_ms: str, dto_name: [Optional] = None,
                        method_names: Optional[list[str]] = None) -> tuple[str, str, NewFile]:
        dto_name = dto_name if dto_name else f"{class_.name}DTO"
        client_template = self.create_client_template(class_, proto_class, microservice_uid, dto_name, method_names)
        # if not method_names:
        #     self.logger.debug(f"class {class_.name} has no methods to consume. No need to call LLM. "
        #                       f"Using template instead.")
        #     template_package_as_list = client_template.full_name.split(".")[:-1]
        #     path = os.path.join("{ms_root}", "src", "main", "java", *template_package_as_list)
        #     filename = f"{client_template.name}.java"
        #     # content = result.new_class.source_code
        #     content = GRPCSolution2(
        #         class_name=client_template.name,
        #         package_name=".".join(template_package_as_list),
        #         source_code=client_template.code,
        #         explanation=f"class {class_.name} has no methods to expose to external microservices. "
        #                     f"The DTO described within the proto file is self-sufficient. No need to call LLM to "
        #                     f"generate additional logic for the client. Using the template basic approach instead.",
        #         additional_comments="",
        #     )
        #     return "", "", NewFile(filename, path, content)
        self.logger.debug(f"Generating client for class {class_.name} with the DTO pattern for MS {client_ms}.")
        # current_microservice = self.api_classes[class_.full_name].microservice
        client_prompt, suffix = self._create_client_prompt(class_, proto_prompt, proto_response, client_template,
                                                           client_ms, dto_name)
        _, client_response = self.generate_or_load_response(client_prompt, suffix)
        client_file = self.parse_server_client_response(client_response, class_, client_template,
                                                            suffix="dto_client")
        return client_prompt, client_response, client_file

    def create_client_template(self, class_: Class, proto_class: Class, microservice_uid: str, dto_name: str,
                               method_names: Optional[list[str]] = None) -> Class:
        # Create template for the client
        api_class = self.api_classes[class_.full_name]
        package_name = self.helper_manager.get_package_name(self.DTO_CLIENT_TEMPLATE)
        registry_package_name = self.helper_manager.get_package_name(self.helper_manager.SERVICE_REGISTRY_TEMPLATE)
        grpc_service = dict(
            name=proto_class.name,
            package_name=".".join(proto_class.full_name.split(".")[:-1]),
        )
        context = dict(
            package_name=package_name,
            class_name=api_class.client_name.split(".")[-1],
            dto_name=dto_name,
            grpc_service=grpc_service,
            method_names=method_names,
            registry_package_name=registry_package_name,
            target_service_uid=microservice_uid,
        )
        client_template = self.helper_manager.get_as_class(self.DTO_CLIENT_TEMPLATE, context)
        client_template.name = api_class.client_name.split(".")[-1]
        client_template.full_name = api_class.client_name
        return client_template

    def refactor_class(self, class_name: str, method_names: list[str], microservice_uid: str,
                       client_microservices: set[str], fields: Optional[list[str]] = None, **kwargs) -> (
            tuple)[NewFile, NewFile, dict[str, NewFile], Optional[NewFile], None]:
        self.logger.debug(f"Refactoring class {class_name} with the DTO pattern.")
        self._check_class(class_name)
        simple_name = class_name.split(".")[-1]
        class_source = self.analysis_model.get_class_source(class_name)
        class_ = Class(simple_name, class_source, class_name)
        method_simple_names = [method_name.split("::")[-1] for method_name in method_names]
        # Exclude getters and setters of the class's fields
        method_simple_names = self._exclude_getters_setters(class_name, method_simple_names)
        # Get list of fields to include
        if fields is None:
            fields = [f["variableName"] for f in self.analysis_model.get_field_details(class_name)
                      if f["type"]["typeSource"] != "LIBRARY"]
        # Generate the proto file
        proto_prompt, proto_response, proto_file, proto_class, dto_name = self.generate_proto(class_,
                                                                                              method_simple_names,
                                                                                              fields)
        # Generate the server and client files concurrently
        n_workers = min(2, 1+len(client_microservices))
        with ThreadPoolExecutor(max_workers=2) as executor:
            server_job = executor.submit(self.generate_server, class_, proto_prompt, proto_response, proto_class,
                                         dto_name, method_simple_names)
            client_jobs = dict()
            for client_ms in client_microservices:
                client_job = executor.submit(self.generate_client, class_, proto_prompt, proto_response, proto_class,
                                             microservice_uid, client_ms, dto_name, method_simple_names)
                client_jobs[client_ms] = client_job
            server_prompt, server_response, server_file, mapper_file = server_job.result()
            client_files = dict()
            for client_ms, client_job in client_jobs.items():
                client_prompt, client_response, client_file = client_job.result()
                client_files[client_ms] = client_file
        return proto_file, server_file, client_files, mapper_file, None

    def _exclude_getters_setters(self, class_name: str, names: list[str]) -> list[str]:
        """
        Exclude getter and setter methods from the list of method names.
        """
        field_names = [f["variableName"] for f in self.analysis_model.get_field_details(class_name)]
        names = [n.split("(")[0] for n in names]
        excluded_names = []
        for name in names:
            match = re.match(r"^(get|set|is)([A-Z][^.]*)?", name)
            if match:
                potential_field_name = match.group(2)
                potential_field_name = potential_field_name[0].lower() + potential_field_name[1:]
                if potential_field_name in field_names:
                    self.logger.debug(f"Excluding getter/setter {name} for field {potential_field_name}")
                    continue
            excluded_names.append(name)
        return excluded_names


