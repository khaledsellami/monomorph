import dataclasses
import re
from abc import ABC, abstractmethod
from typing import Any, Literal, Optional

from langchain_core.tools import BaseTool
from langgraph.constants import END
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph, StateGraph
from pydantic import BaseModel

from .code import CodeGenInvoker
from ...llm.langchain.usage import CallbackContext
from ...llm.langgraph.decision.printer import ConsolePrinter


class TypeGenState(MessagesState):
    # inputs
    prompt_context: dict[str, Any]
    # internal state
    correction_attempts: int
    additional_info: dict[str, Any]
    generated_code: Any
    corrected_code: Any
    # outputs
    final_response: Any
    code_healthy: bool


class TypeGenAgent(ABC):
    OUTPUT_TYPE = BaseModel

    def __init__(self, gen_model: str, parsing_model: str, correction_model: str, max_correction_attempts: int = 3,
                 llm_kwargs: dict = None, callback_context: Optional[CallbackContext] = None):
        self.gen_model = gen_model
        self.parsing_model = parsing_model
        self.correction_model = correction_model
        self.max_correction_attempts = max_correction_attempts
        self.llm_kwargs = llm_kwargs or {}
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.graph = self._build_graph()
        self.callback_context = callback_context

    def with_context(self, task: Literal["generation", "correction"]) -> Optional[CallbackContext]:
        """
        Prepare the context for the LLM calls based on the model name and task.
        :param task: The task being performed (e.g. "generation", "correction")
        """
        if self.callback_context:
            callback_context = dataclasses.replace(self.callback_context)
            callback_context.usage_task = task
            return callback_context
        return None

    def _build_graph(self) -> CompiledStateGraph:
        builder = StateGraph(TypeGenState)
        # Define the nodes
        builder.add_node("gen", self.generate_code)
        builder.add_node("correct", self.correct_code)
        builder.add_node("postprocess", self.postprocess_result)
        # Define the entry point
        builder.set_entry_point("gen")
        # Add the conditional edges
        builder.add_conditional_edges(
            "gen",
            self.proceed_with_correction,
            {
                "try_correction": "correct",
                "continue": "postprocess",
                END: END,
            },
        )
        builder.add_conditional_edges(
            "correct",
            self.proceed_with_correction,
            {
                "try_correction": "correct",
                "continue": "postprocess",
                END: END,
            },
        )
        # Compile and return the graph
        return builder.compile()

    def generate_code(self, state: TypeGenState) -> dict[str, Any]:
        """
        Generate code (e.g. class source code or proto file) using the code generation subgraph.
        """
        self.logger.debug("Calling code generation subgraph", msg_type="node", highlight=True)
        gen_system_prompt, gen_user_prompt, parsing_system_prompt, additional_info = self.create_gen_prompts(state)
        tools = self.define_gen_tools()
        code_gen_invoker = CodeGenInvoker(self.OUTPUT_TYPE, self.gen_model, self.parsing_model, tools,
                                          callback_context=self.with_context("generation"), **self.llm_kwargs)
        gen_state = dict(
            gen_system_prompt=gen_system_prompt,
            gen_user_prompt=gen_user_prompt,
            parsing_system_prompt=parsing_system_prompt,
        )
        output = code_gen_invoker.graph.invoke(gen_state)
        generated_code = output.get("final_response", None)
        additional_info = state.get("additional_info", {}) | additional_info
        return {"generated_code": generated_code, "additional_info": additional_info,
                "messages": output.get("messages", [])}

    def correct_code(self, state: TypeGenState) -> dict[str, Any]:
        """
        Correct the generated code using the code correction subgraph.
        """
        self.logger.debug("Calling code correction subgraph", msg_type="node", highlight=True)
        c_system_prompt, c_user_prompt, parsing_system_prompt, additional_info = self.create_correction_prompts(state)
        tools = self.define_correction_tools()
        code_gen_invoker = CodeGenInvoker(self.OUTPUT_TYPE, self.correction_model, self.parsing_model, tools,
                                          callback_context=self.with_context("correction"), **self.llm_kwargs)
        gen_state = dict(
            gen_system_prompt=c_system_prompt,
            gen_user_prompt=c_user_prompt,
            parsing_system_prompt=parsing_system_prompt,
        )
        output = code_gen_invoker.graph.invoke(gen_state)
        corrected_code = output.get("final_response", None)
        additional_info = state.get("additional_info", {}) | additional_info
        return {"corrected_code": corrected_code, "additional_info": additional_info,
                "messages": output.get("messages", [])}

    def postprocess_result(self, state: TypeGenState) -> dict[str, Any]:
        """
        Postprocess the result of the code generation or correction process. This node is only reached
        if the code is valid.
        """
        generated_code = state.get("generated_code", None)
        corrected_code = state.get("corrected_code", None)
        final_response = generated_code or corrected_code
        return {"final_response": final_response, "code_healthy": True}

    def proceed_with_correction(self, state: TypeGenState) -> Literal["continue", "try_correction", END]:
        """
        Verify the generated or corrected code. Exits the workflow if the code code is valid or
        correction attempt limits are reached.
        """
        # Verify if the generated or corrected code is valid
        code_healthy, feedback = self.verify_code(state)
        if code_healthy:
            self.logger.debug("No issues found in the code. Continuing workflow.", msg_type="node", highlight=True)
            return "continue"
        # The code is not valid, check if we can correct it
        correction_attempts = state.get("correction_attempts", 0)
        if correction_attempts >= self.max_correction_attempts:
            # Max correction attempts reached
            self.logger.debug(f"Max correction attempts ({self.max_correction_attempts}) reached. Exiting workflow.",
                              msg_type="node", highlight=True)
            return END
        elif correction_attempts == 0:
            # First correction attempt
            self.logger.debug("Found issues in the generated code. Attempting to correct it.",
                              msg_type="node", highlight=True)
        else:
            # Subsequent correction attempts
            self.logger.debug(f"Found issues in the corrected code. Attempting to correct it again "
                              f"({correction_attempts + 1}/{self.max_correction_attempts}).",
                              msg_type="node", highlight=True)
        return "try_correction"

    def cleanup_code(self, code: str) -> str:
        pattern = re.compile(r"```(\S*)\n([\s\S]*?)\n```")
        match = pattern.search(code)
        if match:
            self.logger.warning(f"Found code enclosed in {match.group(1)} block")
            return match.group(2)
        if code.strip() == "":
            self.logger.warning("Code is empty")
            return ""
        return code

    @abstractmethod
    def define_gen_tools(self) -> list[BaseTool]:
        """
        Define the tools to be used in the code generation process.
        """
        # This method should be overridden in subclasses to define specific tools.
        self.logger.warning("Tools are not defined yet. Returning empty list.", msg_type="system", highlight=True)
        raise NotImplementedError("Tools are not defined yet. Returning empty list.")

    @abstractmethod
    def create_gen_prompts(self, state: TypeGenState) -> tuple[str, str, str, dict]:
        """
        Create the system and user prompts for the code generation process.
        """
        # This method should be overridden in subclasses to create specific prompts.
        self.logger.warning("Prompts are not defined yet. Returning empty strings.", msg_type="system", highlight=True)
        raise NotImplementedError("Prompts are not defined yet. Returning empty strings.")

    @abstractmethod
    def define_correction_tools(self) -> list[BaseTool]:
        """
        Define the tools to be used in the code correction process.
        """
        # This method should be overridden in subclasses to define specific tools.
        self.logger.warning("Tools are not defined yet. Returning empty list.", msg_type="system", highlight=True)
        raise NotImplementedError("Tools are not defined yet. Returning empty list.")

    @abstractmethod
    def create_correction_prompts(self, state: TypeGenState) -> tuple[str, str, str, dict]:
        """
        Create the system and user prompts for the code correction process.
        """
        # This method should be overridden in subclasses to create specific prompts.
        self.logger.warning("Prompts are not defined yet. Returning empty strings.", msg_type="system", highlight=True)
        raise NotImplementedError("Prompts are not defined yet. Returning empty strings.")

    @abstractmethod
    def verify_code(self, state: TypeGenState) -> tuple[bool, str]:
        """
        Verify the generated or corrected code. This method should be overridden in subclasses to implement
        specific verification logic.
        """
        # This method should be overridden in subclasses to implement specific verification logic.
        self.logger.warning("Verification logic is not defined yet. Returning True.", msg_type="system", highlight=True)
        raise NotImplementedError("Verification logic is not defined yet. Returning True.")




