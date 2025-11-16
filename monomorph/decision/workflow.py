import dataclasses
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from ..logging.printer import ConsolePrinter
from ..llm.langchain.usage import CallbackContext, UsageCallbackHandler
from ..analysis import AppModel
from ..models import UpdatedDecomposition
from ..llm.langgraph.utils import init_model
from .nodes import DecisionCallBackHandler
from .tools import AnalysisTools
from .graph import create_refact_decision_graph
from .models import RefactoringDecision
from .prompts import DECISION_SYSTEM_PROMPT_TEMPLATE, DECISION_USER_PROMPT_TEMPLATE, DECISION_PARSING_SYSTEM_PROMPT


class RefactDecisionWorkflow:
    PREVIEW_LENGTH = 100

    def __init__(self, app_name: str, decomposition: UpdatedDecomposition, analysis_manager: AppModel,
                 decision_model: str, parsing_model: Optional[str] = None, language: str = "java",
                 debug_mode: bool = False, should_stream: bool = False, verbosity: int = 1,
                 block_paid_api: bool = True, relevant_classes: Optional[set[str]] = None,
                 callback_context: Optional[CallbackContext] = None):
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.app_name = app_name
        self.decomposition = decomposition
        self.analysis_manager = analysis_manager
        self.decision_model_name = decision_model
        self.parsing_model_name = parsing_model
        self.language = language
        self.should_stream = should_stream
        self.debug_mode = debug_mode
        self.verbosity = verbosity
        self.tools_manager = AnalysisTools(analysis_manager, decomposition, language=language,
                                           relevant_classes=relevant_classes)
        self.tools = self.tools_manager.get_tools()
        self.logger.debug(f"Using {decision_model} as a decision model", msg_type="workflow", highlight=True)
        self.decision_model = init_model(decision_model, mode="tooling", tools=self.tools, block_paid_api=block_paid_api)
        self.logger.debug(f"Using {parsing_model} as a parsing model", msg_type="workflow", highlight=True)
        self.parsing_model = init_model(parsing_model, mode="structured", output_type=RefactoringDecision,
                                        block_paid_api=block_paid_api)
        self.callback_context = callback_context
        self.callback_handler = DecisionCallBackHandler()
        self.graph = create_refact_decision_graph(self.tools, self.decision_model, self.parsing_model,
                                                  DECISION_PARSING_SYSTEM_PROMPT, should_stream,
                                                  callback_handler=self.callback_handler)
        # self.logger = ConsolePrinter.get_printer("monomorph") if debug_mode else FilteredLogger("monomorph")

    def with_context(self, class_name: str, current_ms: str,
                     model_name: str, task: str) -> Optional[CallbackContext]:
        """
        Sets the callback context for the workflow.
        """
        if self.callback_context:
            callback_context = dataclasses.replace(self.callback_context)
            callback_context.file_type = "decision"
            callback_context.class_name = class_name
            callback_context.target_microservice = current_ms
            callback_context.model_name = model_name
            callback_context.usage_task = task
            return callback_context
        return None

    def create_input_messages(self, class_name: str, current_ms: str) -> dict:
        """
        Creates the input messages for the LLM.
        """
        input_messages = {'messages': [
            SystemMessage(content=DECISION_SYSTEM_PROMPT_TEMPLATE.format(language=self.language)),
            HumanMessage(
                content=DECISION_USER_PROMPT_TEMPLATE.format(
                    class_name=class_name,
                    source_code=self.analysis_manager.get_class_source(class_name),
                    current_ms=current_ms,
                    language=self.language
                )
            ),
        ]}
        return input_messages

    def log_inputs(self, input_messages):
        # Print Initial Messages with Color
        self.logger.debug("Preparing System and first user prompts", msg_type="workflow", highlight=True)
        for msg in input_messages["messages"]:
            if isinstance(msg, SystemMessage):
                self.logger.debug(msg.content, msg_type="system", short_message="System Message")
            elif isinstance(msg, HumanMessage):
                # Limit printing potentially very long user content for readability
                content_preview = (msg.content[:self.PREVIEW_LENGTH] + '...') if len(
                    msg.content) > self.PREVIEW_LENGTH else msg.content
                self.logger.debug(content_preview, msg_type="user", short_message="User Message")

    def invoke(self, input_messages):
        """
        Invokes the graph with the input messages.
        """
        self.logger.debug("Invoking ID and DTO Decision Graph", msg_type="workflow", highlight=True)
        # Execute the graph with the input messages
        result = self.graph.invoke(input_messages)
        return result

    def log_outputs(self, node_name, new_messages):
        if self.verbosity < 1:
            return
        if node_name == "parser":
            return # Don't log parser outputs
        for msg in new_messages:
            if isinstance(msg, AIMessage):
                # This AIMessage is the one accumulated *after* streaming in call_model
                self.logger.debug(f"Node: '{node_name}'", msg_type="ai")
                if msg.tool_calls:
                    self.logger.debug("Tool Calls:", msg_type="ai_toolcall", short_message="Model requested Tool Calls")
                    for tc in msg.tool_calls:
                        self.logger.debug(f" - Tool: {tc['name']}", msg_type="ai_toolcall")
                        self.logger.debug(f" - Args: {tc['args']}", msg_type="ai_toolcall")
                        self.logger.debug(f" - ID: {tc['id']}", msg_type="ai_toolcall")
                if hasattr(msg, 'parsed') and isinstance(msg.parsed, RefactoringDecision):
                    self.logger.debug(f"  - Decision: {msg.parsed.decision}", msg_type="decision")

            elif isinstance(msg, ToolMessage):
                self.logger.debug(f"- Node - {node_name}", msg_type="tool")
                # Shorten potentially long tool outputs in the live log
                content_preview = (msg.content[:self.PREVIEW_LENGTH] + '...') if len(
                    msg.content) > self.PREVIEW_LENGTH else msg.content
                self.logger.debug(f"- Content: {content_preview}", msg_type="tool")
                self.logger.debug(f"- Tool Call ID: {msg.tool_call_id}", msg_type="tool")

    def stream(self, input_messages):
        """
        Streams the graph with the input messages.
        """
        self.logger.debug("Streaming ID and DTO Decision Graph ---", msg_type="workflow", highlight=True)
        results = {}
        # Execute the graph with the input messages
        for output in self.graph.stream(input_messages):
            for node_name, state_update in output.items():
                if "messages" in state_update:
                    self.log_outputs(node_name, state_update["messages"])
                    # final_state = {"messages": state_update["messages"]}
                results = output[node_name]
        return results

    def _preprocess(self, class_name: str, current_ms: str):
        """
        Any preprocessing done before invoking the graph.
        """
        if self.tools_manager.current_ms != current_ms:
            self.tools_manager.set_current_ms(current_ms)
        self.tools_manager.current_class = class_name
        # Set the callback context if provided
        if self.callback_context:
            decision_callback_context = self.with_context(class_name, current_ms, self.decision_model_name, "decision")
            parser_callback_context = self.with_context(class_name, current_ms, self.parsing_model_name, "parsing")
            self.callback_handler.decision_callback = UsageCallbackHandler(decision_callback_context)
            self.callback_handler.parsing_callback = UsageCallbackHandler(parser_callback_context)

    def run(self, class_name: str, ms_name: str) -> tuple[RefactoringDecision | str | dict | None, list[str]]:
        self.logger.debug("Preprocessing workflow inputs", msg_type="workflow", highlight=True)
        self._preprocess(class_name, ms_name)
        self.logger.info("Starting Graph Execution", msg_type="workflow", highlight=True)
        input_messages = self.create_input_messages(class_name, ms_name)
        self.log_inputs(input_messages)
        # Execute the graph with the input messages
        if self.should_stream:
            results = self.stream(input_messages)
        else:
            results = self.invoke(input_messages)
        # Log the final state
        decision = self.log_final_state(results)
        conversation_log = self._create_conversation_log(results)
        self.logger.info("Graph Execution Completed", msg_type="workflow", highlight=True)
        return decision, conversation_log

    def _create_conversation_log(self, final_state_dict) -> list[str] | None:
        """
        Creates a conversation log from the final state dictionary.
        """
        conversation_log = []
        if final_state_dict:
            self.logger.debug(f"Creating Conversation Log", msg_type="workflow", highlight=True)
            for message in final_state_dict.get('messages', []):
                if isinstance(message, AIMessage):
                    conversation_log.append(f"# AI: \n{message.content.replace('# ', '## ')}")
                elif isinstance(message, HumanMessage):
                    conversation_log.append(f"# User: \n{message.content.replace('# ', '## ')}")
                elif isinstance(message, ToolMessage):
                    conversation_log.append(f"# Tool: \n{message.content.replace('# ', '## ')}")
                elif isinstance(message, SystemMessage):
                    conversation_log.append(f"# System: \n{message.content.replace('# ', '## ')}")
                else:
                    conversation_log.append(f"# Unknown: \n{message}")
        return conversation_log

    def log_final_state(self, final_state_dict) -> RefactoringDecision | None:
        if final_state_dict:
            self.logger.debug(f"Postprocessing Final State", msg_type="workflow", highlight=True)

            final_decision = final_state_dict.get('final_response')
            success = False
            if final_decision:
                if isinstance(final_decision, RefactoringDecision):
                    final_decision = final_decision
                    success = True
                elif isinstance(final_decision, dict) and isinstance(final_decision.get('parsed', None), RefactoringDecision):
                    final_decision = final_decision['parsed']
                    success = True

            if success:
                self.logger.debug(f"Final Refactoring Decision (Parsed Successfully)", msg_type="workflow", highlight=True)
                return final_decision
            else:
                attempts = final_state_dict.get('parsing_attempts', 0)
                self.logger.warning(f"Failed to Parse Final Decision after {attempts} attempt(s)", msg_type="error", highlight=True)
                self.logger.debug(f"Final state 'final_response' is None or invalid.", msg_type="error", highlight=True)
                # Optionally print the last few messages for debugging why parsing failed
                # if 'messages' in final_state_dict:
                #     self.logger.debug("\nLast few messages for context:")
                #     for msg in final_state_dict['messages'][-3:]:  # Print last 3 messages
                #         if isinstance(msg, AIMessage):
                #             self.logger.debug(f"  AI: {msg.content[:self.PREVIEW_LENGTH]}...", msg_type="ai")
                #         elif isinstance(msg, HumanMessage):
                #             self.logger.debug(f"  Human: {msg.content[:self.PREVIEW_LENGTH]}...", msg_type="user")
                #         elif isinstance(msg, ToolMessage):
                #             self.logger.debug(f"  Tool: {msg.content[:self.PREVIEW_LENGTH]}...", msg_type="tool")
        else:
            self.logger.warning(f"Graph did not produce a final state dictionary (check execution)", msg_type="error", highlight=True)

    def _simulate_run(self, class_name: str, current_ms: str) -> tuple[RefactoringDecision, None]:
        """
        Simulate the run method for testing purposes. Randomly generates a decision.
        """
        self.logger.warning("This is a simulated run. DO NOT USE IN EXPERIMENTS.")
        import random
        self.logger.debug("--- Simulating Run ---", msg_type="workflow", highlight=True)
        decision = random.choice(["ID-Based", "DTO-Based"])
        reasoning = "This is a simulated reasoning for the decision. DO NOT USE IN EXPERIMENTS!"
        if decision == "DTO-Based":
            class_field_names = [f["variableName"] for f in self.analysis_manager.get_field_details(class_name)]
            if class_field_names:
                suggested_dto_fields = random.sample(class_field_names, k=random.randint(1, len(class_field_names)))
            else:
                suggested_dto_fields = None
        else:
            suggested_dto_fields = None
        self.logger.debug(f"--- Decision: {decision} ---", msg_type="workflow", highlight=True)
        decision_model = RefactoringDecision(
            decision=decision,
            reasoning=reasoning,
            suggested_dto_fields=suggested_dto_fields
        )
        return decision_model, None






