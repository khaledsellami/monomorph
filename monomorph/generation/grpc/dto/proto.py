import os
from typing import Optional

from langchain_core.tools import BaseTool

from .prompts import LangChainDTOgRPCProtoPrompt
from ....helpers import HelperManager
from ....llm.models import Class
from ...type import TypeGenState
from ...models import ProtoSolution
from ...utils import get_referenced_class_mapping
from ..id.proto import IDProtoGenAgent


class DTOProtoGenAgent(IDProtoGenAgent):
    """
    DTOgRPCTypeGenAgent is a specialized agent for generating and correcting protobuf files for gRPC services.
    """
    DTO_PROTO_TEMPLATE = HelperManager.DTO_PROTO_TEMPLATE
    OUTPUT_TYPE = ProtoSolution

    def define_gen_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_gen_prompts(self, state: TypeGenState) -> tuple[str, str, str, dict]:
        # TODO change the prompts
        prompt_context = state.get("prompt_context", {})
        class_: Optional[Class] = prompt_context.get("class_", None)
        method_simple_names: list[str] = prompt_context.get("method_simple_names", [])
        fields: Optional[list[str]] = prompt_context.get("fields", None)
        if class_ is None:
            raise RuntimeError(f"No class defined for the proto generation process")
        # Create the prompt
        system_prompt, user_prompt, suffix, proto_template = self._create_proto_prompt(
            class_, method_simple_names, fields)
        return system_prompt, user_prompt, "", {"proto_template": proto_template}

    def define_correction_tools(self) -> list[BaseTool]:
        # TODO: implement this
        return []

    def create_correction_prompts(self, state: TypeGenState) -> tuple[str, str, str]:
        # TODO: implement this
        return "", "", ""

    def verify_code(self, state: TypeGenState) -> tuple[bool, str]:
        # TODO: implement this
        return True, ""

    def _create_proto_prompt(self, class_: Class, method_simple_names: list[str],
                                  fields: Optional[list[str]] = None) -> tuple[str, str, str, Class]:
        # Create the referenced classes mapping
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        # Prepare context
        api_class = self.api_classes[class_.full_name]
        dto_name = api_class.dto_name
        proto_template_package = api_class.proto_package
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        service_name = api_class.service_name.split(".")[-1]
        context = dict(
            package_name=proto_template_package,
            service_name=service_name if method_simple_names else None,
            class_name=class_.name,
            dto_name=dto_name,
            references_mapping= referenced_classes,
        )
        fields = fields if fields else []
        proto_template = self.helper_manager.get_as_class(self.DTO_PROTO_TEMPLATE, context)
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        prompt_gen = LangChainDTOgRPCProtoPrompt(class_, method_simple_names, object_id_class, fields, proto_template,
                                                 referenced_classes)
        prompt = prompt_gen.generate_prompt()
        system_prompt = prompt_gen.generate_system_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen.get_prompt_basename(), prompt_gen.get_prompt_type(), class_.name)
        return system_prompt, prompt, suffix, proto_template

