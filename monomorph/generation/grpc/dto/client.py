import os
from typing import Optional, Any

from langchain_core.tools import BaseTool

from .prompts import LangChainDTOgRPCClientPrompt
from ..id.client import IDClientGenAgent
from ...models import NewFile, GRPCSolution2
from ...type import TypeGenState
from ...utils import get_referenced_class_mapping
from ....helpers import HelperManager
from ....llm.models import Class


class DTOClientGenAgent(IDClientGenAgent):
    """
    DTOClientGenAgent is a specialized agent for generating and correcting the client side of the new gRPC services.
    """
    SHARED_PROTO_FILE = HelperManager.SHARED_PROTO_FILE
    CLIENT_TEMPLATE = HelperManager.DTO_CLIENT_TEMPLATE
    MAPPER_FILE = HelperManager.ID_MAPPER_TEMPLATE
    OUTPUT_TYPE = GRPCSolution2
    SERVICE_REGISTRY_TEMPLATE = HelperManager.SERVICE_REGISTRY_TEMPLATE

    def define_gen_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_gen_prompts(self, state: TypeGenState) -> tuple[str, str, str, dict]:
        prompt_context = state.get("prompt_context", {})
        class_: Optional[Class] = prompt_context.get("class_", None)
        proto_prompt, proto_response = prompt_context.get("proto_output", ("", ""))
        client_ms = prompt_context.get("client_ms")
        microservice_uid = prompt_context.get("microservice_uid")
        method_names = prompt_context.get("method_names")
        if class_ is None:
            raise RuntimeError(f"No class defined for the proto generation process")
        # Create the prompt
        system_prompt, user_prompt, suffix, client_template = self._create_client_prompt(
            class_, proto_prompt, proto_response, microservice_uid, client_ms, method_names)
        return system_prompt, user_prompt, "", {"client_template": client_template}

    def define_correction_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_correction_prompts(self, state: TypeGenState) -> tuple[str, str, str]:
        # TODO: implement this
        return "", "", ""

    def verify_code(self, state: TypeGenState) -> tuple[bool, str]:
        # TODO: implement this
        return True, ""

    def _create_client_prompt(self, class_: Class, proto_prompt: str, proto_response: str,
                              microservice_uid: str, client_ms: str,method_names: Optional[list[str]] = None) -> (
            tuple)[str, str, str, Class]:
        """
        Create the user prompt for the client class generation process.
        :param class_: The API class for which the client class is generated.
        :param proto_prompt: The prompt that is used to generate the proto class.
        :param proto_response: The model's response to the proto class generation.
        :param microservice_uid: The UID of the microservice to which the API class belongs.
        :param client_ms: The microservice that is the client of the API class.
        :param method_names: Optional list of method names required for the client template.
        :return: A tuple containing the client generation system and user prompt and the suffix for tracing purposes.
        """
        # Create the client template
        api_class = self.api_classes[class_.full_name]
        dto_name = api_class.dto_name
        client_template = self._generate_client_template(class_, microservice_uid, method_names)
        # Prepare prompt context
        id_mapper_class_details = self.helper_manager.helper_mapping[self.MAPPER_FILE]
        id_mapper_class_name = f"{id_mapper_class_details['package']}.{id_mapper_class_details['object_name']}"
        id_mapper_class = Class(id_mapper_class_details['object_name'], "", id_mapper_class_name)
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        # Create the prompt
        prompt_gen_client = LangChainDTOgRPCClientPrompt(proto_prompt, proto_response, client_template, dto_name,
                                                         id_mapper_class, referenced_classes, client_ms)
        client_prompt = prompt_gen_client.generate_prompt()
        system_prompt = prompt_gen_client.generate_system_prompt()
        if client_ms is None or class_.name is None or prompt_gen_client.get_prompt_basename() is None or prompt_gen_client.get_prompt_type() is None:
            raise RuntimeError(f"Invalid parameters for client prompt generation: "
                               f"{client_ms}, {class_.name}, {prompt_gen_client.get_prompt_basename()}, "
                               f"{prompt_gen_client.get_prompt_type()}")
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen_client.get_prompt_basename(), prompt_gen_client.get_prompt_type(),
                              client_ms, class_.name)
        return system_prompt, client_prompt, suffix, client_template

    def _generate_client_template(self, class_: Class, microservice_uid: str,
                                  method_names: Optional[list[str]] = None) -> Class:
        """
        Create the client template for the given class, its proto class and its owner microservice.
        :param class_: The API class for which the client template is customized.
        :param microservice_uid: The UID of the microservice to which the API class belongs.
        :param method_names: Optional list of method names required for the client template.
        :return: The customized client template class.
        """
        # Create the template for the client
        api_class = self.api_classes[class_.full_name]
        dto_name = api_class.dto_name
        package_name = self.helper_manager.get_package_name(self.CLIENT_TEMPLATE)
        registry_package_name = self.helper_manager.get_package_name(self.SERVICE_REGISTRY_TEMPLATE)
        grpc_service = dict(
            name=api_class.service_name.split(".")[-1],
            package_name=api_class.proto_package,
        )
        client_simple_name = api_class.client_name.split(".")[-1]
        context = dict(
            package_name=package_name,
            class_name=client_simple_name,
            dto_name=dto_name,
            grpc_service=grpc_service,
            method_names=method_names,
            registry_package_name=registry_package_name,
            target_service_uid=microservice_uid,
        )
        client_template = self.helper_manager.get_as_class(self.CLIENT_TEMPLATE, context)
        client_template.name = client_simple_name
        client_template.full_name = api_class.client_name
        return client_template

    def postprocess_result(self, state: TypeGenState) -> dict[str, Any]:
        generated_code = state.get("generated_code", None)
        corrected_code = state.get("corrected_code", None)
        client_template = state.get("additional_info").get("client_template")
        final_response: GRPCSolution2 = generated_code or corrected_code
        if final_response:
            path = os.path.join("{ms_root}", "src", "main", "java", *client_template.full_name.split(".")[:-1])
            filename = f"{client_template.name}.java"
            final_response.source_code = self.cleanup_code(final_response.source_code)
            client_file = NewFile(filename, path, final_response)
            return {"final_response": client_file, "code_healthy": True}
        return {"final_response": final_response, "code_healthy": True}
