import os
from typing import Optional, Any

from langchain_core.tools import BaseTool

from ....models import NewFile
from .....execution.helpers import HelperManager
from .....llm.langchain.output import GRPCSolution2
from .....llm.langchain.prompts import LangChainIDgRPCServerPrompt
from .....llm.models import Class
from .....planning.proxies import PlannedAPIClass
from ...type import TypeGenAgent, TypeGenState
from ...utils import get_referenced_class_mapping


class IDServerGenAgent(TypeGenAgent):
    """
    IDServerGenAgent is a specialized agent for generating and correcting the server side of the new gRPC services.
    """
    SHARED_PROTO_FILE = HelperManager.SHARED_PROTO_FILE
    SERVER_TEMPLATE = HelperManager.SERVICE_IMPLEMENTATION_TEMPLATE
    MAPPER_FILE = HelperManager.ID_MAPPER_TEMPLATE
    CLASSID_REGISTRY_FILE = HelperManager.CLASSID_REGISTRY_TEMPLATE
    OUTPUT_TYPE = GRPCSolution2

    def __init__(self, helper_manager: HelperManager, api_classes: dict[str, PlannedAPIClass] = None,
                 id_only: bool = False, gen_model: str = "gpt-4o", parsing_model: str = "gpt-4o",
                 correction_model: str = "gpt-4o", max_correction_attempts: int = 3, llm_kwargs: dict = None,
                 **kwargs: Any):
        super().__init__(gen_model, parsing_model, correction_model, max_correction_attempts, llm_kwargs, **kwargs)
        self.helper_manager = helper_manager
        self.api_classes = api_classes
        self.id_only = id_only

    def define_gen_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_gen_prompts(self, state: TypeGenState) -> tuple[str, str, str, dict]:
        # TODO change the prompts
        prompt_context = state.get("prompt_context", {})
        class_: Optional[Class] = prompt_context.get("class_", None)
        proto_prompt, proto_response = prompt_context.get("proto_output", ("", ""))
        if class_ is None:
            raise RuntimeError(f"No class defined for the proto generation process")
        # Create the prompt
        system_prompt, user_prompt, suffix, server_template = self._create_server_prompt(
            class_, proto_prompt, proto_response)
        return system_prompt, user_prompt, "", {"server_template": server_template}

    def define_correction_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_correction_prompts(self, state: TypeGenState) -> tuple[str, str, str]:
        # TODO: implement this
        return "", "", ""

    def verify_code(self, state: TypeGenState) -> tuple[bool, str]:
        # TODO: implement this
        return True, ""

    def _create_server_prompt(self, class_: Class, proto_prompt: str, proto_response: str) -> (
            tuple)[str, str, str, Class]:
        """
        Create the user prompt for the server class generation process.
        :param class_: The API class for which the server class is generated.
        :param proto_prompt: The prompt that is used to generate the proto class.
        :param proto_response: The model's response to the proto class generation.
        :return: A tuple containing the server generation system and user prompt and the suffix for tracing purposes.
        """
        # Create the server template
        server_template = self._create_server_template(class_)
        # Prepare context
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        class_id_registry_details = self.helper_manager.helper_mapping[self.CLASSID_REGISTRY_FILE]
        class_id_registry_full_name = f"{class_id_registry_details['package']}.{class_id_registry_details['object_name']}"
        mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        mapper_class_name = f"{mapper_class_details['package']}.{mapper_class_details['object_name']}"
        mapper_class = Class(mapper_class_details['object_name'], "", mapper_class_name)
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        current_microservice = self.api_classes[class_.full_name].microservice
        # Create the prompt
        prompt_gen_server = LangChainIDgRPCServerPrompt(proto_prompt, proto_response, class_id_registry_full_name,
                                                        server_template, mapper_class, object_id_class,
                                                        self.id_only, referenced_classes, current_microservice)
        server_prompt = prompt_gen_server.generate_prompt()
        system_prompt = prompt_gen_server.generate_system_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_server.get_prompt_basename(), prompt_gen_server.get_prompt_type(), class_.name)
        return system_prompt, server_prompt, suffix, server_template

    def _create_server_template(self, class_: Class) -> Class:
        """
        Create the server template for the given class and its proto class.
        :param class_: The API class for which the server template is customized.
        :return: The customized server template class.
        """
        api_class = self.api_classes[class_.full_name]
        impl_full_name = api_class.server_name
        impl_name = impl_full_name.split(".")[-1]
        package_name = self.helper_manager.get_package_name(self.SERVER_TEMPLATE)
        grpc_service = dict(
            impl_name=impl_name,
            name=api_class.service_name.split(".")[-1],
            package_name=api_class.proto_package,
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

    def postprocess_result(self, state: TypeGenState) -> dict[str, Any]:
        generated_code = state.get("generated_code", None)
        corrected_code = state.get("corrected_code", None)
        server_template = state.get("additional_info").get("server_template")
        final_response: GRPCSolution2 = generated_code or corrected_code
        if final_response:
            path = os.path.join("{ms_root}", "src", "main", "java", *server_template.full_name.split(".")[:-1])
            filename = f"{server_template.name}.java"
            final_response.source_code = self.cleanup_code(final_response.source_code)
            server_file = NewFile(filename, path, final_response)
            return {"final_response": server_file, "code_healthy": True}
        return {"final_response": final_response, "code_healthy": True}

