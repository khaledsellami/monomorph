import dataclasses
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from .nodes import AgentState, define_compilation_analysis_nodes
from .tools import CompilationLogAnalysisTools
from .models import CompilationAnalysisReport
from .prompts import CompilationLogAnalysisPrompt
from ..callbacks import ValidationCallBackHandler
from ..utils import compile_generated_classes_files
from ...helpers import HelperManager
from ...microservice import MicroserviceDirectory
from ...generation.prompts import PARSING_SYSTEM_PROMPT_TEMPLATE
from ...llm.tracking.usage import CallbackContext, UsageCallbackHandler
from ...llm.langgraph.utils import init_model
from ...analysis.model import AppModel
from ...logging.printer import ConsolePrinter
from ...logging.utils import log_inputs, log_outputs, create_conversation_log


class CompilationAnalysisWorkflow:
    PREVIEW_LENGTH = 100

    def __init__(self, package_name: str, microservice: MicroserviceDirectory, helper_manager: HelperManager,
                 log_details: dict[str, int | str], analysis_manager: AppModel,
                 decision_model: str, parsing_model: Optional[str] = None, language: str = "java",
                 debug_mode: bool = False, should_stream: bool = False, verbosity: int = 1,
                 block_paid_api: bool = True, relevant_classes: Optional[set[str]] = None,
                 callback_context: Optional[CallbackContext] = None):
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.package_name = package_name
        self.current_microservice = microservice.name
        self.ms_root = microservice.directory_path
        self.analysis_manager = analysis_manager
        self.log_details = log_details
        self.decision_model_name = decision_model
        self.parsing_model_name = parsing_model
        self.language = language
        self.should_stream = should_stream
        self.debug_mode = debug_mode
        self.verbosity = verbosity
        generated_files, generated_classes, _ = compile_generated_classes_files(microservice, helper_manager,
                                                                                language=language)
        self.logger.debug("getting analysis tools", msg_type="workflow", highlight=True)
        self.tools_manager = CompilationLogAnalysisTools(analysis_manager, self.ms_root, generated_classes,
                                                         generated_files, log_details, language=language,
                                                         relevant_classes=relevant_classes)
        self.tools = self.tools_manager.get_tools()
        self.logger.debug(f"Using {decision_model} as a compilation analysis model", msg_type="workflow", highlight=True)
        self.decision_model = init_model(decision_model, mode="tooling", tools=self.tools,
                                         block_paid_api=block_paid_api)
        parsing_model = parsing_model or decision_model
        self.logger.debug(f"Using {parsing_model} as a parsing model", msg_type="workflow", highlight=True)
        self.parsing_model = init_model(parsing_model, mode="structured", output_type=CompilationAnalysisReport,
                                        block_paid_api=block_paid_api)
        parsing_system_prompt = PARSING_SYSTEM_PROMPT_TEMPLATE.format(
            type_name=CompilationAnalysisReport.__class__.__name__)
        self.callback_context = callback_context
        self.callback_handler = ValidationCallBackHandler()
        self.graph = self.create_compilation_analysis_graph(self.tools, self.decision_model, self.parsing_model,
                                                            parsing_system_prompt, should_stream,
                                                            callback_handler=self.callback_handler)

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

    def create_input_messages(self) -> dict:
        """
        Creates the input messages for the LLM.
        """
        prompt_gen = CompilationLogAnalysisPrompt(self.log_details["error_logs"], self.package_name,
                                                  self.current_microservice, self.language)
        input_messages = {'messages': [
            SystemMessage(content=prompt_gen.generate_system_prompt()),
            HumanMessage(content=prompt_gen.generate_prompt()),
        ]}
        return input_messages

    def invoke(self, input_messages):
        """
        Invokes the graph with the input messages.
        """
        self.logger.debug("Invoking Compilation Logs Analysis Graph", msg_type="workflow", highlight=True)
        # Execute the graph with the input messages
        result = self.graph.invoke(input_messages)
        return result

    def stream(self, input_messages):
        """
        Streams the graph with the input messages.
        """
        self.logger.debug("Streaming Compilation Logs Analysis Graph ---", msg_type="workflow", highlight=True)
        results = {}
        # Execute the graph with the input messages
        for output in self.graph.stream(input_messages):
            for node_name, state_update in output.items():
                if "messages" in state_update:
                    log_outputs(node_name, self.logger, state_update["messages"], self.PREVIEW_LENGTH, self.verbosity)
                    # final_state = {"messages": state_update["messages"]}
                results = output[node_name]
        return results

    def _preprocess(self):
        """
        Any preprocessing done before invoking the graph.
        """
        # Set the callback context if provided
        if self.callback_context:
            main_callback_context = self.with_context("", self.current_microservice,
                                                          self.decision_model_name, "correction")
            parser_callback_context = self.with_context("", self.current_microservice,
                                                        self.parsing_model_name, "parsing")
            self.callback_handler.main_callback = UsageCallbackHandler(main_callback_context)
            self.callback_handler.parsing_callback = UsageCallbackHandler(parser_callback_context)

    def run(self) -> tuple[CompilationAnalysisReport | str | dict | None, list[str]]:
        self.logger.debug("Preprocessing workflow inputs", msg_type="workflow", highlight=True)
        self._preprocess()
        self.logger.info("Starting Graph Execution", msg_type="workflow", highlight=True)
        input_messages = self.create_input_messages()
        log_inputs(self.logger, input_messages, self.PREVIEW_LENGTH)
        # Execute the graph with the input messages
        if self.should_stream:
            results = self.stream(input_messages)
        else:
            results = self.invoke(input_messages)
        # Log the final state
        analysis_report = self.log_final_state(results)
        conversation_log = create_conversation_log(self.logger, results)
        self.logger.info("Graph Execution Completed", msg_type="workflow", highlight=True)
        return analysis_report, conversation_log

    def log_final_state(self, final_state_dict: dict) -> CompilationAnalysisReport | None:
        if final_state_dict:
            self.logger.debug(f"Postprocessing Final State", msg_type="workflow", highlight=True)

            final_decision = final_state_dict.get('compilation_report')
            success = False
            if final_decision:
                if isinstance(final_decision, CompilationAnalysisReport):
                    final_decision = final_decision
                    success = True
                elif isinstance(final_decision, dict) and isinstance(final_decision.get('parsed', None),
                                                                     CompilationAnalysisReport):
                    final_decision = final_decision['parsed']
                    success = True
            if success:
                self.logger.debug(f"Final Analysis (Parsed Successfully)", msg_type="workflow", highlight=True)
                return final_decision
            else:
                attempts = final_state_dict.get('parsing_attempts', 0)
                self.logger.warning(f"Failed to Parse Analysis Report after {attempts} attempt(s)", msg_type="error",
                                    highlight=True)
                self.logger.debug(f"Final state 'final_response' is None or invalid.", msg_type="error",
                                  highlight=True)
                return None
        else:
            self.logger.warning(f"Graph did not produce a final state dictionary (check execution)", msg_type="error",
                                highlight=True)
            return None

    def create_compilation_analysis_graph(self, tools: list[BaseTool],
                                          decision_model: BaseChatOpenAI,
                                          parser_model: Optional[BaseChatOpenAI] = None,
                                          parser_system_prompt: str = "",
                                          stream: bool = False,
                                          callback_handler: Optional[ValidationCallBackHandler] = None) -> CompiledStateGraph:
        """
        Creates a state graph for the compilation analysis and correction workflow.

        Args:
            tools: The tools to be used in the decision-making process.
            decision_model: The model used for making refactoring decisions.
            parser_model: The model used for parsing the output into structured data.
            parser_system_prompt: The system prompt for the parser model.
            stream: Whether to stream the model response or not.
            callback_handler: Optional callback handler for tracking llm usage

        Returns:
            graph: The compiled state graph.
        """

        # Define the node callable functions
        nodes = define_compilation_analysis_nodes(
            decision_model, parser_model, parser_system_prompt, callback_handler=callback_handler, stream=stream)
        analysis_node, should_continue, parse_output, check_parsing_status = nodes
        # Define a new graph
        workflow = StateGraph(AgentState)
        # Define the nodes
        workflow.add_node("analysis_agent", analysis_node)
        workflow.add_node("analysis_tools", ToolNode(tools))
        workflow.add_node("parser", parse_output)
        # Set the entrypoint
        workflow.set_entry_point("analysis_agent")
        # Add the conditional edges
        workflow.add_conditional_edges(
            "analysis_agent",
            should_continue,
            {
                "tools": "analysis_tools",
                "parse_final_answer": "parser",
            },
        )

        # Conditional edge from parser
        workflow.add_conditional_edges(
            "parser",
            check_parsing_status,
            {
                "retry_parsing": "parser",  # Loop back on failure if retries remain
                "__end__": END,  # End on success or max retries failure
            },
        )
        # Add edges
        ## So the tools node call back to the agent node
        workflow.add_edge("analysis_tools", "analysis_agent")
        # Compile the graph
        return workflow.compile()






