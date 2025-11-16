from typing import Any, Optional

from .client import IDClientGenAgent
from .proto import IDProtoGenAgent
from .server import IDServerGenAgent
from ...agentic import RefactState, RefactAgent
from ...type import TypeGenState
from ...utils import format_messages
from ...models import NewFile
from ....helpers import HelperManager
from ....llm.models import Class
from ....llm.tracking.usage import CallbackContext
from ....analysis.model import AppModel
from ....planning.proxies import PlannedAPIClass


class IDRefactAgent(RefactAgent):
    """
    IDRefactAgent is the implementation of the ID-based refactoring approach with the agentic method
    """
    def __init__(self, analysis_handler: AppModel, helper_manager: HelperManager,
                 api_classes: dict[str, PlannedAPIClass] = None, id_only: bool = False,
                 models_kwargs: dict = None, callback_context: Optional[CallbackContext] = None):
        super().__init__(models_kwargs, callback_context)
        self.analysis_handler = analysis_handler
        self.helper_manager = helper_manager
        self.api_classes = api_classes
        self.id_only = id_only
        self.refactored_classes = dict()

    def generate_contract(self, state: RefactState) -> dict[str, Any]:
        self.logger.debug("Generating Proto file for")
        # Get the proto file generation details
        prompts_context = state.get("prompts_context")
        class_: Class = prompts_context.get("class_")
        method_simple_names: list[str] = prompts_context.get("method_simple_names", [])
        proto_state = TypeGenState(
            prompt_context={
                "class_": class_,
                "method_simple_names": method_simple_names,
            }
        )
        # Prepare the tracing context
        callback_context = self.prepare_context(refact_type="ID-Based", file_type="contract",
                                                state=state, client_ms=None)
        # Invoke the proto file generation graph
        proto_graph = IDProtoGenAgent(self.helper_manager, self.api_classes, self.id_only,
                                      callback_context=callback_context, **self.models_kwargs)
        proto_result = proto_graph.graph.invoke(proto_state)
        # Parse the proto file generation result
        proto_response: NewFile = proto_result.get("final_response")
        if proto_response is None:
            raise RuntimeError("Proto file generation failed")
        # Propagate the tracing details
        messages = proto_result.get("messages")
        proto_details = (format_messages(messages[:-1]), messages[-1].content)
        tracing_details = state.get("tracing_details", {})
        tracing_details["contract"] = proto_details
        # if tracing_details is None:
        #     tracing_details = TracingDetails()
        # tracing_details.contract_prompt_response = proto_details
        # Add them to the kwargs
        prompts_context = state.get("prompts_context", {})
        prompts_context["proto_prompt"] = proto_details[0]
        prompts_context["proto_response"] = proto_details[1]
        self.logger.debug("Proto file generated successfully")
        return {"contract_file": proto_response, "tracing_details": tracing_details,
                "prompts_context": prompts_context}

    def generate_client(self, state: RefactState, client_ms: str) -> dict[str, Any]:
        self.logger.debug(f"Generating client file for {client_ms}")
        # Get the client file generation details
        prompts_context = state.get("prompts_context")
        class_: Class = prompts_context.get("class_")
        proto_prompt: str = prompts_context.get("proto_prompt", "")
        proto_response: str = prompts_context.get("proto_response", "")
        microservice_uid: str = state.get("microservice_uid")
        client_state = TypeGenState(
            prompt_context={
                "class_": class_,
                "proto_output": (proto_prompt, proto_response),
                "client_ms": client_ms,
                "microservice_uid": microservice_uid,
            }
        )
        # Prepare the tracing context
        callback_context = self.prepare_context(refact_type="ID-Based", file_type="client",
                                                state=state, client_ms=client_ms)
        # Invoke the client file generation graph
        client_graph = IDClientGenAgent(self.helper_manager, self.api_classes, self.id_only,
                                        callback_context=callback_context, **self.models_kwargs)
        client_result = client_graph.graph.invoke(client_state)
        # Parse the client file generation result
        client_response: NewFile = client_result.get("final_response")
        if client_response is None:
            raise RuntimeError("Client file generation failed")
        # Prepare output
        messages = client_result.get("messages")
        output = {
            "client_file": client_response,
            "client_prompt": format_messages(messages[:-1]),
            "client_response": messages[-1].content,
        }
        self.logger.debug(f"Generated client file for {client_ms}")
        return output

    def generate_server(self, state: RefactState) -> dict[str, Any]:
        self.logger.debug("Generating server file for")
        # Get the server file generation details
        prompts_context = state.get("prompts_context")
        class_: Class = prompts_context.get("class_")
        proto_prompt: str = prompts_context.get("proto_prompt", "")
        proto_response: str = prompts_context.get("proto_response", "")
        server_state = TypeGenState(
            prompt_context={
                "class_": class_,
                "proto_output": (proto_prompt, proto_response),
            }
        )
        # Prepare the tracing context
        callback_context = self.prepare_context(refact_type="ID-Based", file_type="server",
                                                state=state, client_ms=None)
        # Invoke the server file generation graph
        server_graph = IDServerGenAgent(self.helper_manager, self.api_classes, self.id_only,
                                        callback_context=callback_context, **self.models_kwargs)
        server_result = server_graph.graph.invoke(server_state)
        # Parse the server file generation result
        server_response: NewFile = server_result.get("final_response")
        if server_response is None:
            raise RuntimeError("Server file generation failed")
        # Propagate the tracing details
        messages = server_result.get("messages")
        server_details = (format_messages(messages[:-1]), messages[-1].content)
        tracing_details = state.get("tracing_details", {})
        tracing_details["server"] = server_details
        # tracing_details.server_prompt_response = server_details
        self.logger.debug("Server file generated successfully")
        return {"server_file": server_response, "tracing_details": tracing_details}

    def pre_process(self, state: RefactState) -> dict[str, Any]:
        class_name = state.get("class_name")
        method_names = state.get("method_names")
        self.logger.debug(f"Refactoring class {class_name} using the ID-based approach")
        self._check_class(class_name)
        simple_name = class_name.split(".")[-1]
        class_source = self.analysis_handler.get_class_source(class_name)
        class_ = Class(simple_name, class_source, class_name)
        method_simple_names = [method_name.split("::")[-1] for method_name in method_names]
        prompt_context = {
            "class_": class_,
            "method_simple_names": method_simple_names,
        }
        return {
            "prompts_context": prompt_context
        }

    def post_process(self, state: RefactState) -> dict[str, Any]:
        """
        Node needed to consolidate the output of generate_server and generate_clients
        """
        self.logger.debug(f"Finished processing class {state['class_name']}", msg_type="node", highlight=True)
        self.refactored_classes[state["class_name"]] = state["prompts_context"]["class_"]
        return {}

    def _check_class(self, class_name: str):
        for ref_type, refs in zip(["input", "output", "field"], [self.analysis_handler.get_input_types(class_name),
                                                                 self.analysis_handler.get_output_types(class_name),
                                                                 self.analysis_handler.get_field_types(class_name)]):
            self._check_used_apis(class_name, refs, ref_type)

    def _check_used_apis(self, class_name: str, referenced_classes: list[str], ref_type: str):
        for c in referenced_classes:
            if c in self.api_classes and c != class_name:
                self.logger.warning(f"Class {class_name} is referencing another API class {c} within its {ref_type}s.")
                if c in self.refactored_classes:
                    self.logger.warning(f"Class {c} has already been refactored. This may cause issues.")



