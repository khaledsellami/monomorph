import os
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pydantic import ValidationError, BaseModel

from .models import NewFile
from .refact import Refact
from ..llm.langchain.prompts.grpc_parsing import LangChainGrpcParsingPrompt
from ..llm.langchain.prompts.proto_parsing import LangChainProtoParsingPrompt
from ..const import ApproachType
from ..execution.helpers import HelperManager
from ..modeling.model import AppModel
from ..llm.llm_client import LangChainLLMClient
from ..llm.langchain.output import GRPCSolution, ProtoSolution, GRPCSolution2
from ..llm.models import Class
from ..llm.langchain.prompts.id_grpc_proto import LangChainIDgRPCProtoPrompt
from ..llm.langchain.prompts.id_grpc_server import LangChainIDgRPCServerPrompt
from ..llm.langchain.prompts.id_grpc_client import LangChainIDgRPCClientPrompt
from ..execution.dependency.buildfile import PROTO_PATH
from ..planning.proxies import PlannedAPIClass


def split_markdown(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    prompt_start = content.find('# Prompt') + len('# Prompt')
    response_start = content.find('# Response')
    prompt_text = content[prompt_start:response_start].strip()
    response_text = content[response_start + len('# Response'):].strip()
    return prompt_text, response_text


class IDRefact(Refact):
    #BASE_FILES_PATH = importlib.resources.path('monomorph.resources', 'precompiled')
    BASE_FILES_PATH = os.path.join(os.curdir, "monomorph", "resources", "precompiled")
    SHARED_PROTO_FILE = HelperManager.SHARED_PROTO_FILE
    PROTO_TEMPLATE = HelperManager.SERVICE_PROTO_TEMPLATE
    SERVER_TEMPLATE = HelperManager.SERVICE_IMPLEMENTATION_TEMPLATE
    CLIENT_TEMPLATE = HelperManager.CLIENT_CLASS_TEMPLATE
    MAPPER_FILE = HelperManager.ID_MAPPER_TEMPLATE
    CLASSID_REGISTRY_FILE = HelperManager.CLASSID_REGISTRY_TEMPLATE

    def __init__(self, analysis_model: AppModel, base_package_name: str, helper_manager: HelperManager,
                 model_name: str = "gpt-4o", responses_path: str = None, parsing_model: str = "ministral-3b",
                 api_classes: dict[str, PlannedAPIClass] = None, id_only: bool = True):
        # Assumptions: language model is Java
        self.analysis_model = analysis_model
        self.base_package_name = base_package_name
        self.model_name = model_name
        self.helper_manager = helper_manager
        self.id_only = id_only
        self.responses_path = responses_path if responses_path else os.path.join(os.curdir, "llm_data",
                                                                                 "output-responses")
        self.llm_client = LangChainLLMClient(self.model_name, with_structured_output=False, block_paid_api=False,
                                             llm_response_path=self.responses_path, timeout=120, retries=2)
        self.parsing_model = parsing_model
        self.parsing_proto_client = LangChainLLMClient(self.parsing_model, with_structured_output=True, block_paid_api=False,
                                                llm_response_path=self.responses_path, output_type=ProtoSolution,
                                                       timeout=60)
        self.parsing_grpc_client = LangChainLLMClient(self.parsing_model, with_structured_output=True, block_paid_api=False,
                                                llm_response_path=self.responses_path, output_type=GRPCSolution2,
                                                      timeout=60)
        self.api_classes = api_classes if api_classes else {}
        self.refactored_classes = dict()
        self.logger = logging.getLogger("monomorph")

    def generate_response(self, prompt: str, suffix: str, llm_client: LangChainLLMClient,
                          retries: int = 0) -> tuple[str, str | BaseModel]:
        self.logger.debug(f"Generating response")
        while retries >= 0:
            try:
                result, response = llm_client.refactor(prompt, suffix=suffix)
                return prompt, result
            except ValidationError as e:
                self.logger.error(f"Failed to generate response: {e}")
                if retries <= 0:
                    raise e
                else:
                    self.logger.warning(f"Retrying... {retries} retries left")
                retries -= 1

    def generate_or_load_response(self, prompt: str, suffix: str, retries: int = 0) -> tuple[str, str | BaseModel]:
        out_path = self.llm_client.get_save_path(suffix)
        file_name = f"{self.llm_client.full_name.replace('/', '--')}.md"
        if os.path.exists(os.path.join(out_path, file_name)):
            self.logger.debug(f"Loading response from {os.path.join(out_path, file_name)}")
            prompt, response = split_markdown(os.path.join(out_path, file_name))
            return prompt, response
        else:
            return self.generate_response(prompt, suffix, self.llm_client, retries)

    def get_referenced_class_mapping(self, class_name: str) -> dict[str, dict[str, PlannedAPIClass]]:
        planned_api_class = self.api_classes[class_name]
        class_mapping = dict(idbased={}, dto={})
        for c in planned_api_class.referenced_classes:
            if c in self.api_classes:
                referenced_api_class = self.api_classes[c]
                approach = "idbased" if referenced_api_class.decision == ApproachType.ID_BASED else "dto"
                class_mapping[approach][c] = referenced_api_class
            else:
                self.logger.warning(f"Class {c} is referenced by {class_name} but not found in API classes.")
        return class_mapping
    
    def _create_proto_prompt(self, class_: Class, method_simple_names: list[str], context: dict,
                              object_id_class: Class) -> tuple[str, str]:
        proto_template = self.helper_manager.get_as_class(self.PROTO_TEMPLATE, context)
        referenced_classes = self.get_referenced_class_mapping(class_.full_name)
        prompt_gen = LangChainIDgRPCProtoPrompt(class_, method_simple_names, object_id_class, proto_template,
                                                self.id_only, referenced_classes)
        prompt = prompt_gen.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen.get_prompt_basename(), prompt_gen.get_prompt_type(), class_.name)
        return prompt, suffix

    def generate_proto(self, class_: Class, method_simple_names: list[str]) -> tuple[str, str, NewFile, Class]:
        self.logger.debug(f"Generating proto for class {class_.name}")
        # Prepare context
        api_class = self.api_classes[class_.full_name]
        proto_template_package = api_class.proto_package
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        context = dict(
            package_name=proto_template_package,
            service_name=api_class.service_name.split(".")[-1],
            class_name=class_.name,
            refactor_id_package=".".join(object_id_class.full_name.split(".")[:-1]),
        )
        # Create the prompt
        prompt, suffix = self._create_proto_prompt(class_, method_simple_names, context, object_id_class)
        # Call the LLM
        _, response = self.generate_or_load_response(prompt, suffix)
        # Parse the response
        proto_file = self.parse_proto_response(response, class_)
        # Create and return the proto class
        proto_class = Class(context["service_name"], proto_file.content.proto_code,
                            f"{proto_template_package}.{context['service_name']}")
        return prompt, response, proto_file, proto_class

    def parse_proto_response(self, response: str, class_: Class) -> NewFile:
        self.logger.debug(f"Parsing proto response for class {class_.name} with model "
                          f"{self.parsing_proto_client.full_name}")
        proto_prompt_gen = LangChainProtoParsingPrompt(response)
        prompt = proto_prompt_gen.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              proto_prompt_gen.get_prompt_basename(), proto_prompt_gen.get_prompt_type(), class_.name)
        result: ProtoSolution
        _, result = self.generate_response(prompt, suffix, self.parsing_proto_client, retries=2)
        # path = os.path.join("{ms_root}", "src", "main", "resources")
        path = os.path.join("{ms_root}", *PROTO_PATH.split("/"))
        result.proto_code = self.cleanup_code(result.proto_code, lang="proto")
        # filename = result.file_name
        # filename = f"{class_.name.lower()}.proto"
        filename = self.api_classes[class_.full_name].proto_filename
        result.file_name = filename
        # content = result.proto_code
        return NewFile(filename, path, result)

    def cleanup_code(self, code: str, lang: str = "java") -> str:
        pattern = re.compile(r"```(java|proto)\n([\s\S]*?)\n```")
        match = pattern.search(code)
        if match:
            self.logger.warning(f"Found code enclosed in {match.group(1)} block")
            return match.group(2)
        if code.strip() == "":
            self.logger.warning("Code is empty")
            return ""
        if lang == "java":
            # TODO add code verification for Java
            pass
        return code

    def parse_server_client_response(self, response: str, class_: Class, template: Class,
                                     suffix: str = "server") -> NewFile:
        self.logger.debug(f"Parsing server/client response for class {class_.name} with model "
                          f"{self.parsing_grpc_client.full_name}")
        sc_prompt_gen = LangChainGrpcParsingPrompt(response, mode=suffix)
        prompt = sc_prompt_gen.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              f"{sc_prompt_gen.get_prompt_basename()}_{suffix}",
                              sc_prompt_gen.get_prompt_type(), class_.name)
        result: GRPCSolution2
        _, result = self.generate_response(prompt, suffix, self.parsing_grpc_client, retries=2)
        # path = os.path.join("{ms_root}", "src", "main", "java", *self.package_generated.split("."))
        # filename = result.new_class.class_name + ".java"
        path = os.path.join("{ms_root}", "src", "main", "java", *template.full_name.split(".")[:-1])
        filename = f"{template.name}.java"
        result.source_code = self.cleanup_code(result.source_code, lang="java")
        # content = result.new_class.source_code
        return NewFile(filename, path, result)

    def create_server_template(self, class_: Class, proto_class: Class) -> Class:
        api_class = self.api_classes[class_.full_name]
        impl_full_name = api_class.server_name
        impl_name = impl_full_name.split(".")[-1]
        package_name = self.helper_manager.get_package_name(self.SERVER_TEMPLATE)
        grpc_service = dict(
            impl_name=impl_name,
            name=proto_class.name,
            package_name=".".join(proto_class.full_name.split(".")[:-1]),
        )
        context = dict(
            package_name=package_name,
            grpc_service=grpc_service,
            original_class=class_,
        )
        server_template = self.helper_manager.get_as_class(self.SERVER_TEMPLATE, context)
        server_template.name = impl_name
        server_template.full_name = impl_full_name
        return server_template

    def _create_server_prompt(self, class_: Class, proto_prompt: str, proto_response: str,
                             server_template: Class) -> tuple[str, str]:
        # Prepare prompt context
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        class_id_registry_details = self.helper_manager.helper_mapping[self.CLASSID_REGISTRY_FILE]
        class_id_registry_full_name = f"{class_id_registry_details['package']}.{class_id_registry_details['object_name']}"
        mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        mapper_class_name = f"{mapper_class_details['package']}.{mapper_class_details['object_name']}"
        mapper_class = Class(mapper_class_details['object_name'], "", mapper_class_name)
        referenced_classes = self.get_referenced_class_mapping(class_.full_name)
        current_microservice = self.api_classes[class_.full_name].microservice
        # Create the prompt
        prompt_gen_server = LangChainIDgRPCServerPrompt(proto_prompt, proto_response, class_id_registry_full_name,
                                                        server_template, mapper_class, object_id_class,
                                                        self.id_only, referenced_classes, current_microservice)
        server_prompt = prompt_gen_server.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_server.get_prompt_basename(), prompt_gen_server.get_prompt_type(), class_.name)
        return server_prompt, suffix

    def generate_server(self, class_: Class, proto_prompt: str, proto_response: str, proto_class: Class) -> (
            tuple)[str, str, NewFile]:
        self.logger.debug(f"Generating server for class {class_.name}")
        # Create the server template
        server_template = self.create_server_template(class_, proto_class)
        # Create the server prompt
        server_prompt, suffix = self._create_server_prompt(class_, proto_prompt, proto_response, server_template)
        # mapper_class = self.helper_manager.get_as_class(self.MAPPER_FILE) if has_dto else None
        _, server_response = self.generate_or_load_response(server_prompt, suffix)
        server_file = self.parse_server_client_response(server_response, class_, server_template, suffix="server")
        return server_prompt, server_response, server_file

    def generate_client_template(self, class_: Class, proto_class: Class, microservice_uid: str) -> Class:
        # Create template for the client
        api_class = self.api_classes[class_.full_name]
        package_name = self.helper_manager.get_package_name(self.CLIENT_TEMPLATE)
        grpc_service = dict(
            name=proto_class.name,
            package_name=".".join(proto_class.full_name.split(".")[:-1]),
        )
        client_simple_name = api_class.client_name.split(".")[-1]
        context = dict(
            package_name=package_name,
            grpc_service=grpc_service,
            class_name=client_simple_name,
            target_service_uid=microservice_uid,
        )
        client_template = self.helper_manager.get_as_class(self.CLIENT_TEMPLATE, context)
        client_template.name = client_simple_name
        client_template.full_name = api_class.client_name
        return client_template

    def _create_client_prompt(self, class_: Class, proto_prompt: str, proto_response: str, client_template: Class,
                              client_ms: str) -> tuple[str, str]:
        # Prepare prompt context
        id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        mapper_class_name = f"{mapper_class_details['package']}.{mapper_class_details['object_name']}"
        mapper_class = Class(mapper_class_details['object_name'], "", mapper_class_name)
        referenced_classes = self.get_referenced_class_mapping(class_.full_name)
        # Create the prompt
        prompt_gen_client = LangChainIDgRPCClientPrompt(proto_prompt, proto_response, client_template, id_class,
                                                        mapper_class, self.id_only, referenced_classes,
                                                        client_ms)
        client_prompt = prompt_gen_client.generate_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_client.get_prompt_basename(), prompt_gen_client.get_prompt_type(),
                              client_ms, class_.name)
        return client_prompt, suffix

    def generate_client(self, class_: Class, proto_prompt: str, proto_response: str, proto_class: Class,
                        microservice_uid: str, client_ms: str) -> tuple[str, str, NewFile]:
        self.logger.debug(f"Generating client for class {class_.name} for microservice {client_ms}")
        # Create the client template
        client_template = self.generate_client_template(class_, proto_class, microservice_uid)
        # Create the client prompt
        client_prompt, suffix = self._create_client_prompt(class_, proto_prompt, proto_response, client_template,
                                                           client_ms)
        # current_microservice = self.api_classes[class_.full_name].microservice
        # Call the LLM
        _, client_response = self.generate_or_load_response(client_prompt, suffix)
        # Parse and return the response
        client_file = self.parse_server_client_response(client_response, class_, client_template, suffix="client")
        return client_prompt, client_response, client_file

    def refactor_class(self, class_name: str, method_names: list[str], microservice_uid: str,
                       client_microservices: set[str], **kwargs) -> (
            tuple)[NewFile, NewFile, dict[str, NewFile], Optional[NewFile], None]:
        self.logger.debug(f"Refactoring class {class_name}")
        self._check_class(class_name)
        simple_name = class_name.split(".")[-1]
        class_source = self.analysis_model.get_class_source(class_name)
        class_ = Class(simple_name, class_source, class_name)
        method_simple_names = [method_name.split("::")[-1] for method_name in method_names]
        proto_prompt, proto_response, proto_file, proto_class = self.generate_proto(class_, method_simple_names)
        n_workers = min(2, 1+len(client_microservices))
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            server_job = executor.submit(self.generate_server, class_, proto_prompt, proto_response, proto_class)
            client_jobs = dict()
            for client_ms in client_microservices:
                client_job = executor.submit(self.generate_client, class_, proto_prompt, proto_response, proto_class,
                                             microservice_uid, client_ms)
                client_jobs[client_ms] = client_job
            server_prompt, server_response, server_file = server_job.result()
            client_files = dict()
            for client_ms, client_job in client_jobs.items():
                client_prompt, client_response, client_file = client_job.result()
                client_files[client_ms] = client_file
        self.refactored_classes[class_name] = class_
        return proto_file, server_file, client_files, None, None

    def _check_class(self, class_name: str):
        for ref_type, refs in zip(["input", "output", "field"], [self.analysis_model.get_input_types(class_name),
                                                                 self.analysis_model.get_output_types(class_name),
                                                                 self.analysis_model.get_field_types(class_name)]):
            self._check_used_apis(class_name, refs, ref_type)

    def _check_used_apis(self, class_name: str, referenced_classes: list[str], ref_type: str):
        for c in referenced_classes:
            if c in self.api_classes and c != class_name:
                self.logger.warning(f"Class {class_name} is referencing another API class {c} within its {ref_type}s.")
                if c in self.refactored_classes:
                    self.logger.warning(f"Class {c} has already been refactored. This may cause issues.")



