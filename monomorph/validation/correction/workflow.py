import dataclasses
import uuid
from pathlib import Path
from typing import Optional, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END
from langgraph.errors import GraphRecursionError
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from ...helpers import HelperManager
from ...llm.tracking.usage import UsageCallbackHandler, CallbackContext
from ...llm.tracking.checkpoints import CheckpointStorage
from ...llm.tracking.compare import CompilationLogComparator
from ...llm.factory import init_model
from ...microservice import MicroserviceDirectory
from ...logging.utils import log_inputs, create_conversation_log, log_outputs
from ...logging.printer import ConsolePrinter
from ..callbacks import ValidationCallBackHandler
from ..common import create_stream_model_function, create_call_model_function
from ..compilation import CompilationRunner
from ..correction.prompts import CompilationCorrectionPrompt, ExpertPrompt
from ..correction.tools import ErrorCorrectionTools
from ..docker import MicroserviceDocker
# from ..log_analysis.models import RootCauseAnalysis, CompilationAnalysisReport
from ..utils import compile_generated_classes_files
from .nodes import CorrectionState, should_exit_condition, standard_exit_node, wrap_tool_node, finished_correction, \
    create_expert_nodes
from .summary import create_custom_summarize_node, generate_summary


class CompilationCorrectionWorkflow:
    PREVIEW_LENGTH = 100
    MAX_ATTEMPTS = 20

    def __init__(self, package_name: str, microservice: MicroserviceDirectory, ms_docker: MicroserviceDocker,
                 compilation_handler: CompilationRunner, helper_manager: HelperManager,
                 correction_model: str, expert_model: str,  #compilation_report: CompilationAnalysisReport,
                 language: str = "java", should_stream: bool = False, verbosity: int = 1,
                 block_paid_api: bool = True, callback_context: Optional[CallbackContext] = None,
                 include_previous_results: bool = True, fallback_model: Optional[str] = None):
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.package_name = package_name
        self.current_microservice = microservice.name
        # self.compilation_report = compilation_report
        self.correction_model_name = correction_model
        self.expert_model_name = expert_model
        self.fallback_model_name = fallback_model if fallback_model else expert_model
        self.language = language
        self.should_stream = should_stream
        self.verbosity = verbosity
        self.callback_context = callback_context
        self.include_previous_results = include_previous_results
        checkpoint_model_outputs = True
        generated_files, generated_classes, refactoring_details = compile_generated_classes_files(
            microservice, helper_manager, language=language)
        original_classes = {c: Path(p) for c, p in microservice.class_file_map.items()}
        # Get the correction tools
        self.logger.debug('getting correction tools', msg_type="workflow", highlight=True)
        correction_tools = ["read_file", "write_file", "fuzzy_file_search",
                            "show_directory_tree", "get_source_code", "execute_command", "compile_microservice",
                            "can_modify_file", "get_file_context", "commit_changes", "request_expert_help"]
        self.correction_tools_manager = ErrorCorrectionTools(ms_docker, compilation_handler, generated_classes,
                                                             original_classes, refactoring_details, language)
        self.correction_tools = self.correction_tools_manager.get_tools(correction_tools)
        # Get the expert tools
        expert_tools = ["read_file", "fuzzy_file_search", "show_directory_tree", "get_source_code",
                        "can_modify_file", "get_file_context"]
        self.expert_tools = self.correction_tools_manager.get_tools(expert_tools)
        # Initialize the models
        self.logger.debug(f"Using {self.correction_model_name} as a correction model", msg_type="workflow",
                          highlight=True)
        self.fallback_model = init_model(self.fallback_model_name, mode="tooling", tools=self.correction_tools,
                                         block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs)
        self.correction_model = init_model(self.correction_model_name, mode="tooling", tools=self.correction_tools,
                                           block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs,
                                           fallback_model=self.fallback_model)
        self.summary_model = init_model(self.correction_model_name, mode="summary",
                                        block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs,
                                           fallback_model=self.fallback_model).with_config(max_tokens=1000)
        self.expert_model = init_model(self.expert_model_name, mode="expert", tools=self.expert_tools,
                                       block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs)
        other_fallback_model = init_model(self.correction_model_name, mode="tooling", tools=self.correction_tools,
                                         block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs)
        self.advanced_model = init_model(self.fallback_model_name, mode="advanced", tools=self.correction_tools,
                                         block_paid_api=block_paid_api, checkpoint=checkpoint_model_outputs,
                                         fallback_model=other_fallback_model)
        self.use_advanced_model = False
        # Create the correction graph
        self.callback_handler = ValidationCallBackHandler()
        self.graph = self.create_compilation_correction_graph(self.correction_tools, self.correction_model,
                                                              self.expert_tools, self.expert_model,
                                                              should_stream, callback_handler=self.callback_handler)

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

    def create_input_messages(self, logs: str, results: CorrectionState | None = None) -> dict:
        """
        Creates the input messages for the LLM.
        """
        prompt_gen = CompilationCorrectionPrompt(logs, self.package_name, self.current_microservice,
                                                 self.language)
        input_messages = {'messages': [
            SystemMessage(content=prompt_gen.generate_system_prompt()),
        ]}
        if results is not None and self.include_previous_results:
            previous_results_summary = self._create_summary(results)
            if previous_results_summary is not None:
                summary_message = AIMessage(
                    "Work done so far:\n" + previous_results_summary
                )
                input_messages['messages'].append(summary_message)
        logs_message = HumanMessage(content=prompt_gen.generate_prompt())
        logs_message.additional_kwargs["is_compilation_logs"] = True
        input_messages['messages'].append(logs_message)
        return input_messages

    def _preprocess(self):
        """
        Any preprocessing done before invoking the graph.
        """
        # Set the callback context if provided
        if self.callback_context:
            main_callback_context = self.with_context("", self.current_microservice,
                                                      self.correction_model_name, "correction")
            self.callback_handler.main_callback = UsageCallbackHandler(main_callback_context)
            expert_callback_context = self.with_context("", self.current_microservice,
                                                        self.expert_model_name, "expert")
            self.callback_handler.expert_callback = UsageCallbackHandler(expert_callback_context)
            summary_callback_context = self.with_context("", self.current_microservice,
                                                         self.correction_model_name, "summary")
            self.callback_handler.summary_callback = UsageCallbackHandler(summary_callback_context)

    def run(self, with_tests: bool = False) -> tuple[ErrorCorrectionTools, list, Any, bool, list]:
        self.logger.debug("Preprocessing workflow inputs", msg_type="workflow", highlight=True)
        old_with_tests = self.correction_tools_manager.with_tests
        old_chpt_config = CheckpointStorage().get_config()
        self.correction_tools_manager.set_with_tests(with_tests)
        log_suffix = ' (with tests)' if with_tests else ''
        self._preprocess()
        comparator = CompilationLogComparator()
        conversation_logs = []
        all_results = []
        exit_reasons = []
        error_resolution_attempts = 0
        results = None
        self.logger.info(f"Starting correction {log_suffix} loop", msg_type="workflow", highlight=True)
        # Initial compilation
        compilation_logs = self.correction_tools_manager.compile_microservice(only_logs=True)
        success = "Microservice compiled successfully." in compilation_logs
        if success:
            self.logger.info(f"Microservice compiled{log_suffix} successfully, "
                             f"no errors to correct.", msg_type="workflow", highlight=True)
            return self.correction_tools_manager, conversation_logs, all_results, success, exit_reasons
        while not success and error_resolution_attempts < self.MAX_ATTEMPTS:
            error_resolution_attempts += 1
            self.logger.info(f"Starting correction {log_suffix} attempt {error_resolution_attempts}/{self.MAX_ATTEMPTS} "
                             f"for microservice {self.current_microservice}", msg_type="workflow", highlight=True)
            input_messages = self.create_input_messages(compilation_logs, results)
            log_inputs(self.logger, input_messages, self.PREVIEW_LENGTH)
            config = {
                "configurable": {
                    "thread_id": uuid.uuid4(),
                },
                "recursion_limit": 100
            }
            # Execute the graph with the input messages
            try:
                if self.should_stream:
                    old_mode = ConsolePrinter.LOGGING_MODE
                    ConsolePrinter.set_logging_mode("printer")
                    results = self.stream(input_messages, config=config)
                    ConsolePrinter.set_logging_mode(old_mode)
                else:
                    results = self.invoke(input_messages, config=config)
            except GraphRecursionError as e:
                self.logger.error(f"Graph recursion error: {e}", msg_type="workflow", highlight=True)
                # results = input_messages.copy()
                results = self.graph.get_state(config).values
                results["should_exit"] = True
                results["exit_reason"] = f"Graph recursion limit reached: {e}"
                results["exit_type"] = "recursion_limit"
            all_results.append(results)
            conversation_log = create_conversation_log(self.logger, results)
            conversation_logs.append(conversation_log)
            exit_reasons.append(results.get("exit_reason", "No exit reason provided"))
            exit_type = results.get("exit_type", "default")
            if exit_type == "compilation_success":
                self.logger.info(f"Compilation{log_suffix} successful after {error_resolution_attempts} corrections",
                                 msg_type="workflow", highlight=True)
                break
            new_compilation_logs = self.correction_tools_manager.compile_microservice(only_logs=True)
            success = "Microservice compiled successfully." in new_compilation_logs
            same_error = not comparator.has_compilation_error_changed(compilation_logs, new_compilation_logs)
            # same_error = new_compilation_logs == compilation_logs
            if success:
                self.logger.info(f"Microservice{log_suffix} compiled successfully after corrections.",
                                 msg_type="workflow", highlight=True)
                break
            if same_error:
                self.logger.error(f"Compilation{log_suffix} failed with the same error after {error_resolution_attempts} "
                                  f"correction attempts", msg_type="workflow", highlight=True)
                success = False
                # break
            else:
                compilation_logs = new_compilation_logs
            if results["exit_type"] == "recursion_limit":
                error_resolution_attempts -= 1  # Do not count this as a correction attempt
            if same_error and (exit_type == "recursion_limit" or exit_type == "default"):
                # disable loading previous results to avoid getting stuck in a loop
                CheckpointStorage().set_config(old_chpt_config.current_exp_id, False,
                                               old_chpt_config.should_save)
                self.use_advanced_model = True
            else:
                # restore previous checkpoint config
                CheckpointStorage().set_config(old_chpt_config.current_exp_id, old_chpt_config.should_load,
                                               old_chpt_config.should_save)
                self.use_advanced_model = False

        # len_results = len(self.compilation_report.analysis_results)
        # if len_results == 0:
        #     self.logger.error("No analysis results available, ending workflow", msg_type="workflow", highlight=True)
        #     return self.correction_tools_manager, conversation_logs, all_results
        # for i, error_cause in enumerate(self.compilation_report.analysis_results):
        #     self.logger.info(f"Processing error {i+1}/{len_results}: {error_cause.error_summary}",
        #                      msg_type="workflow", highlight=True)
        #
        #     self.logger.debug("Starting Graph Execution", msg_type="workflow", highlight=True)
        #     input_messages = self.create_input_messages(error_cause)
        #     log_inputs(self.logger, input_messages, self.PREVIEW_LENGTH)
        #     # Execute the graph with the input messages
        #     try:
        #         if self.should_stream:
        #             results = self.stream(input_messages)
        #         else:
        #             results = self.invoke(input_messages)
        #     except GraphRecursionError as e:
        #         self.logger.error(f"Graph recursion error: {e}", msg_type="workflow", highlight=True)
        #         results = input_messages.copy()
        #         results["should_exit"] = True
        #         results["exit_reason"] = f"Graph recursion limit reached: {e}"
        #         results["exit_type"] = "recursion_limit"
        #     all_results.append(results)
        #     conversation_log = create_conversation_log(self.logger, results)
        #     conversation_logs.append(conversation_log)
        self.logger.info(f"Finished correction{log_suffix} loop", msg_type="workflow", highlight=True)
        self.logger.debug("Applying final commit", msg_type="workflow", highlight=True)
        self.correction_tools_manager.ms_docker.commit_git_changes("Final commit after correction agent finished")
        self.logger.info("Graph Execution Completed", msg_type="workflow", highlight=True)
        self.correction_tools_manager.set_with_tests(old_with_tests)
        CheckpointStorage().set_config(old_chpt_config.current_exp_id, old_chpt_config.should_load,
                                       old_chpt_config.should_save)
        return self.correction_tools_manager, conversation_logs, all_results, success, exit_reasons

    def invoke(self, input_messages, config: Optional[dict] = None):
        """
        Invokes the graph with the input messages.
        """
        if config is None:
            config = {"recursion_limit": 100}
        self.logger.debug("Invoking Correction Graph", msg_type="workflow", highlight=True)
        # Execute the graph with the input messages
        result = self.graph.invoke(input_messages, config)
        return result

    def stream(self, input_messages, config: Optional[dict] = None):
        """
        Streams the graph with the input messages.
        """
        if config is None:
            config = {"recursion_limit": 100}
        self.logger.debug("Streaming Correction Graph ---", msg_type="workflow", highlight=True)
        results = {}
        # Execute the graph with the input messages
        for output in self.graph.stream(input_messages, config):
            for node_name, state_update in output.items():
                if "messages" in state_update:
                    log_outputs(node_name, self.logger, state_update["messages"], self.PREVIEW_LENGTH, self.verbosity)
                results = output[node_name]
        return results

    def _create_summary(self, results: CorrectionState) -> str | None:
        """
        Uses the summary model to create a summary of the results.
        """
        if not results or "messages" not in results:
            return None
        messages = results["messages"]
        if not messages:
            return None
        callback_func = self.callback_handler.get_summary_callback if self.callback_handler else None
        # Create a summary of the messages
        summary_messages = [msg for msg in messages if isinstance(msg, (HumanMessage, AIMessage))]
        # summary_input = [msg.content for msg in messages if isinstance(msg, (HumanMessage, AIMessage))]
        # summary_result = summarize_messages(summary_input, running_summary=None,
        #                                     model=self.summary_model, max_tokens=1000)
        # summary = summary_result.messages[-1].content
        summary = generate_summary(self.summary_model, summary_messages, callback_func=callback_func)
        return summary

    def get_current_correction_model(self) -> BaseChatOpenAI:
        """
        Returns the current correction model being used.
        """
        if self.use_advanced_model:
            self.logger.warning("Using advanced model", msg_type="workflow", highlight=True)
            return self.advanced_model
        return self.correction_model

    def create_compilation_correction_graph(self, correction_tools, correction_model, expert_tools, expert_model,
                                            stream: bool = False,
                                            callback_handler: Optional[ValidationCallBackHandler] = None):
        """
        Creates the graph for the compilation correction workflow.
        """
        # Create the correction model nodes
        invoke_or_stream_function = create_stream_model_function if stream else create_call_model_function
        correction_node = invoke_or_stream_function(
            self.get_current_correction_model, callback_handler.get_main_callback, "correction", self.logger
        )

        # Create the summary model nodes
        tool_node = wrap_tool_node(ToolNode(correction_tools))
        summary_node = create_custom_summarize_node(self.summary_model, callback_handler.get_summary_callback)

        # Create the expert model nodes
        expert_system_prompt = ExpertPrompt(self.package_name, self.current_microservice,
                                            self.language).generate_system_prompt()
        init_expert_node, invoke_expert_node, exit_expert_node, expert_tool_decision = create_expert_nodes(
            expert_model, expert_system_prompt, callback_handler.get_expert_callback
        )
        expert_tool_node = ToolNode(expert_tools)

        # Define a new graph
        workflow = StateGraph(CorrectionState)
        # Define the nodes
        workflow.add_node("correction_agent", correction_node)
        workflow.add_node("correction_tools", tool_node)
        workflow.add_node("standard_exit", standard_exit_node)
        workflow.add_node("summary_agent", summary_node)
        workflow.add_node("expert_init", init_expert_node)
        workflow.add_node("expert_invoke", invoke_expert_node)
        workflow.add_node("expert_exit", exit_expert_node)
        workflow.add_node("expert_tools", expert_tool_node)
        # Set the entrypoint
        workflow.set_entry_point("correction_agent")
        # Add the conditional edges
        workflow.add_conditional_edges(
            "correction_agent",
            finished_correction,
            {
                "tools": "correction_tools",
                "__end__": "standard_exit",
            },
        )
        ## So the tools node call back to the agent node
        workflow.add_conditional_edges(
            "correction_tools",
            should_exit_condition,
            {
                "continue": "summary_agent",
                END: END,
                "expert": "expert_init",
            },
        )
        ## Expert node conditional edges
        workflow.add_conditional_edges(
            "expert_invoke",
            expert_tool_decision,
            {
                "tools": "expert_tools",
                "__end__": "expert_exit",
            },
        )
        # Add edges
        workflow.add_edge("summary_agent", "correction_agent")
        ## Expert node edges
        workflow.add_edge("expert_init", "expert_invoke")
        workflow.add_edge("expert_tools", "expert_invoke")
        workflow.add_edge("expert_exit", "correction_agent")
        # workflow.add_edge("correction_tools", "correction_agent")
        workflow.add_edge("standard_exit", END)
        # Add a checkpointer
        checkpointer = InMemorySaver()
        # Compile the graph
        return workflow.compile(checkpointer=checkpointer)


