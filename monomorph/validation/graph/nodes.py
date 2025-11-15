from typing import Literal, Callable, Optional

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.graph import MessagesState

from .models import CompilationAnalysisReport
from ..common import create_call_model_function, create_stream_model_function
from ..callbacks import ValidationCallBackHandler
from ...llm.langchain.openrouter import OpenRouterChat
from ...llm.langgraph.decision.printer import ConsolePrinter


logger = ConsolePrinter.get_printer("monomorph")


class AgentState(MessagesState):
    # Final structured response from the agent
    compilation_report: CompilationAnalysisReport
    parsing_attempts: int


def define_compilation_analysis_nodes(analysis_model: BaseChatOpenAI, parser_model: Optional[BaseChatOpenAI] = None,
                                      parser_system_prompt: str = "",
                                      callback_handler: Optional[ValidationCallBackHandler] = None,
                                      stream: bool = False) -> list[Callable]:
    """
    Defines the functions for the decision-making process in the workflow based on the given models.

    :param analysis_model: The model used for analyzing the compilation results and making decisions.
    :param parser_model: The model used for parsing the output into structured data. Defaults to the decision model.
    :param parser_system_prompt: The system prompt for the parser model.
    :param callback_handler: Optional callback handler for usage tracking.
    :param stream: If True, the model will stream responses instead of returning them all at once.
    :return: The list of functions to be used in the workflow.
    """
    MAX_PARSING_RETRIES = 3
    # If no parser model is provided, use the decision model
    if parser_model is None:
        parser_model = analysis_model

    if callback_handler is None:
        callback_handler = ValidationCallBackHandler()
    invoke_or_stream_function = create_stream_model_function if stream else create_call_model_function
    analysis_node = invoke_or_stream_function(
        analysis_model, callback_handler.get_main_callback, "compilation analysis", logger
    )

    # Define the function that determines whether to continue to the tools node or end the process
    def should_continue(state: AgentState) -> Literal["tools", "parse_final_answer"]:
        """Determines the next step based on the last message."""
        last_message = state["messages"][-1]
        # If the LLM returned tool calls, route to the tools node
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            logger.debug(f"Invoking {len(last_message.tool_calls)} tools", msg_type="node", highlight=True)
            return "tools"
        logger.debug(f"Proceeding to parsing", msg_type="node", highlight=True)
        return "parse_final_answer"

    def extract_output(state: AgentState):
        last_message = state["messages"][-1]
        if isinstance(last_message, dict) and "parsed" in last_message:
            parsed_output: CompilationAnalysisReport = last_message["parsed"]
        else:
            logger.error(f"Missing 'parsed' key in response. Using initial output",
                         msg_type="node", highlight=True)
            parsed_output = last_message
        return {"compilation_report": parsed_output}

    # Parsing decision node
    def check_parsing_status(state: AgentState) -> Literal["retry_parsing", "__end__"]:
        """
        Checks if parsing succeeded or if retries are exhausted.
        """
        if state.get("compilation_report") is not None:
            compilation_report = state["compilation_report"]
            if isinstance(compilation_report, CompilationAnalysisReport) or isinstance(compilation_report.get("parsed", None), CompilationAnalysisReport):
                # logger.print("--- Decision: Parsing Succeeded -> End", "node", highlight=True)
                logger.debug(f"Parsing successful, Ending workflow", msg_type="node", highlight=True)
                return "__end__"  # Success! End the graph.
            else:
                # logger.print("--- Decision: Parsing Failed -> Retry", "node", highlight=True)
                logger.debug(f"Parsing failed, retrying...", msg_type="node", highlight=True)
                return "retry_parsing"
        elif "parsing_attempts" not in state or state["parsing_attempts"] < MAX_PARSING_RETRIES:
            # logger.print("--- Decision: Parsing Failed, Retrying -> final_parser", "node", highlight=True)
            logger.debug(f"Parsing failed, retrying...", msg_type="node", highlight=True)
            return "retry_parsing"  # Failed, but retries remain. Loop back.
        else:
            # logger.print("--- Decision: Parsing Failed, Max Retries Reached -> End", "node", highlight=True)
            logger.debug(f"Parsing failed and max retries reached, Ending workflow", msg_type="node", highlight=True)
            return "__end__"  # Failed and no more retries. End the graph (with compilation_report=None).

    def parse_output(state: AgentState):
        """
        Attempts to parse the final AI response into RefactoringDecision.
        Uses retry logic with increasing context.
        """
        parsing_attempts = state.get("parsing_attempts", 0)
        # logger.print(f"--- Attempting Final Parsing (Attempt: {parsing_attempts + 1}/{MAX_PARSING_RETRIES}) ---",
        #               "node", highlight=True)
        logger.debug(f"Attempting parsing ({parsing_attempts + 1}/{MAX_PARSING_RETRIES}) with parsing model",
                     msg_type="node", highlight=True)
        messages = state["messages"]

        # Prepare input for the parser LLM based on attempt number
        parser_input_messages = []
        parser_input_messages.append(SystemMessage(content=parser_system_prompt))

        if parsing_attempts == 0:
            # First attempt: Use only the last AI message content
            last_ai_message = messages[-1]
            if isinstance(last_ai_message, AIMessage) and last_ai_message.content:
                # logger.print("--- Using Last AI Message for Parsing ---", "node", highlight=True)
                logger.debug(f"Using last AI message for parsing", msg_type="node", highlight=True)
                parser_input_messages.append(
                    HumanMessage(content=f'"""\n\n{last_ai_message.content}\n\n"""'))
            else:
                # logger.print("--- Last AI Message is not valid for parsing. Skipping attempt. ---", "node",
                #               highlight=True)
                logger.warning("last AI message is not valid for parsing. Skipping attempt.", msg_type="node", highlight=True)
                return {"parsing_attempts": parsing_attempts + 1, "compilation_report": None}
        else:
            # Retry attempts: Use the full conversation history
            # logger.print("--- Using Full Conversation History for Parsing ---", "node", highlight=True)
            logger.debug(f"Using full conversation history for parsing", msg_type="node", highlight=True)
            # Combine history into a single prompt or pass messages directly if parser supports it
            # Let's pass the relevant history as Human message content
            # Exclude the initial system prompt. It's not relevant for the parser task
            history_str = "\n".join([f"{'Human' if isinstance(m, HumanMessage) else 'Assistant' if isinstance(m, AIMessage) else 'Tool'}: {m.content}"
                                    for m in messages if not isinstance(m, SystemMessage)])
            parser_input_messages.append(
                HumanMessage(content=f"Here's the complete conversation history:\n\n{history_str}")
            )
        try:
            # Invoke the parser model with structured output
            if callback_handler.get_parsing_callback():
                output = parser_model.with_config(callbacks=callback_handler.get_parsing_callback()).invoke(parser_input_messages)
            else:
                output = parser_model.invoke(parser_input_messages)
            if isinstance(output, dict) and "parsed" in output:
                parsed_output: CompilationAnalysisReport = output["parsed"]
            else:
                logger.error(f"Missing 'parsed' key in response. Using initial output",
                             msg_type="node", highlight=True)
                parsed_output = output
            # logger.print("--- Successfully Parsed Output ---", "node", highlight=True)
            return {"compilation_report": parsed_output, "parsing_attempts": parsing_attempts + 1}
        except Exception as e:
            # FAILURE: Log error, increment attempt count, keep compilation_report as None
            # logger.print(f"--- Parsing Attempt {parsing_attempts + 1} Failed ---", "error", highlight=True)
            return {"parsing_attempts": parsing_attempts + 1, "compilation_report": None}

    return [analysis_node, should_continue, parse_output, check_parsing_status]
