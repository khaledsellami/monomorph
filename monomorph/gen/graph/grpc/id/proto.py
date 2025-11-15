import os
from typing import Optional, Any

from langchain_core.tools import BaseTool

from ....models import NewFile
from .....execution.dependency.buildfile import PROTO_PATH
from .....execution.helpers import HelperManager
from .....llm.langchain.output import ProtoSolution
from .....llm.langchain.prompts import LangChainIDgRPCProtoPrompt
from .....llm.models import Class
from .....planning.proxies import PlannedAPIClass
from ...type import TypeGenAgent, TypeGenState
from ...utils import get_referenced_class_mapping


class IDProtoGenAgent(TypeGenAgent):
    """
    IDgRPCTypeGenAgent is a specialized agent for generating and correcting protobuf files for gRPC services.
    """
    SHARED_PROTO_FILE = HelperManager.SHARED_PROTO_FILE
    PROTO_TEMPLATE = HelperManager.SERVICE_PROTO_TEMPLATE
    OUTPUT_TYPE = ProtoSolution

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
        method_simple_names: list[str] = prompt_context.get("method_simple_names", [])
        if class_ is None:
            raise RuntimeError(f"No class defined for the proto generation process")
        # Create the prompt
        system_prompt, user_prompt, suffix, proto_template = self._create_proto_prompt(class_, method_simple_names)
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

    def _create_proto_prompt(self, class_: Class, method_simple_names: list[str]) -> tuple[str, str, str, Class]:
        # Create the referenced classes mapping
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        # Prepare context
        api_class = self.api_classes[class_.full_name]
        proto_template_package = api_class.proto_package
        object_id_class = self.helper_manager.get_as_class(self.SHARED_PROTO_FILE)
        context = dict(
            package_name=proto_template_package,
            service_name=api_class.service_name.split(".")[-1],
            class_name=class_.name,
            refactor_id_package=".".join(object_id_class.full_name.split(".")[:-1]),
            references_mapping= referenced_classes,
        )
        proto_template = self.helper_manager.get_as_class(self.PROTO_TEMPLATE, context)
        referenced_classes = get_referenced_class_mapping(class_.full_name, self.api_classes)
        prompt_gen = LangChainIDgRPCProtoPrompt(class_, method_simple_names, object_id_class, proto_template,
                                                self.id_only, referenced_classes)
        prompt = prompt_gen.generate_prompt()
        system_prompt = prompt_gen.generate_system_prompt()
        suffix = os.path.join(self.helper_manager.base_package_name.replace(".", "/"),
                              prompt_gen.get_prompt_basename(), prompt_gen.get_prompt_type(), class_.name)
        return system_prompt, prompt, suffix, proto_template

    def postprocess_result(self, state: TypeGenState) -> dict[str, Any]:
        class_: Class = state.get("prompt_context").get("class_")
        generated_code = state.get("generated_code", None)
        corrected_code = state.get("corrected_code", None)
        final_response: ProtoSolution = corrected_code or generated_code
        if final_response:
            path = os.path.join("{ms_root}", *PROTO_PATH.split("/"))
            final_response.proto_code = self.cleanup_code(final_response.proto_code)
            filename = self.api_classes[class_.full_name].proto_filename
            proto_file = NewFile(filename, path, final_response)
            return {"final_response": proto_file, "code_healthy": True}
        return {"final_response": final_response, "code_healthy": True}

