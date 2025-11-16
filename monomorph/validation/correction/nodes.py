import json
from typing import Literal, Callable

from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage, BaseMessage, AnyMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.prebuilt import ToolNode
from langmem.short_term import summarize_messages
from typing_extensions import TypedDict

from ...logging.printer import ConsolePrinter

logger = ConsolePrinter.get_printer("monomorph")


class CorrectionState(TypedDict):
    """State for the correction node, extending MessagesState."""
    messages: list[AnyMessage]
    should_exit_to_different_node: bool
    exit_reason: str
    expert_messages: list[AIMessage] | None
    expert_request_message: str | None
    exit_type: Literal["llm", "compilation_success", "recursion_limit", "default"]
    # running_summary: RunningSummary | None
    full_conversation: dict[str, BaseMessage]
    current_summary: str | None
    last_summarized_index: int


def should_exit_condition(state: CorrectionState) -> Literal["continue", "__end__", "expert"]:
    """Determine which node to go to next based on tool results."""
    if state.get("should_exit_to_different_node", False):
        if state.get("exit_type", "") == "expert":
            logger.debug(f"Invoking expert node due to llm's request", msg_type="node", highlight=True)
            return "expert"
        logger.debug(f"Exiting correction process: {state.get('exit_reason', 'No reason provided')}",
                     msg_type="node", highlight=True)
        return "__end__"
    return "continue"


def finished_correction(state: CorrectionState) -> Literal["tools", "__end__"]:
    """
    Determines whether to continue to the correction tools node or end the process after correction.
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        logger.debug(f"Invoking {len(last_message.tool_calls)} tools after correction", msg_type="node",
                     highlight=True)
        return "tools"
    logger.debug(f"Moving on after correction", msg_type="node", highlight=True)
    return "__end__"


def standard_exit_node(state: CorrectionState):
    """Node that handles exit due to llm completing its invocation without calling the exit_process tool or having
    a successful compilation."""
    exit_reason = "LLM completed without exit tool or explicit successful compilation"
    exit_type = "default"
    logger.debug(f"Exiting correction process: {exit_reason}",)
    state["should_exit_to_different_node"] = True
    state["exit_reason"] = exit_reason
    state["exit_type"] = exit_type
    return state


def wrap_tool_node(tool_node: ToolNode):
    def tool_node_with_decision(state: CorrectionState):
        """Enhanced tool node that can handle exit conditions."""
        # First, run the regular ToolNode
        result = tool_node.invoke(state)

        # Check if any tool returned an exit signal
        messages = result["messages"]
        should_exit = False
        exit_reason = ""
        exit_type = "default"
        expert_request_message = None

        for i, message in enumerate(messages):
            if isinstance(message, ToolMessage):
                try:
                    content = json.loads(message.content)
                    if isinstance(content, dict):
                        if content.get("tool_name") == "compile_microservice":
                            compilation_logs = content.get("compilation_logs", "")
                            message.additional_kwargs["is_compilation_logs"] = True
                            message.content = compilation_logs
                            continue
                        if content.get("action") == "EXIT_CORRECTION":
                            should_exit = True
                            exit_reason = content.get("exit_reason", "")
                            exit_type = content.get("exit_type", "default")
                            break
                        elif content.get("action") == "CALL_EXPERT":
                            should_exit = True
                            exit_type = content.get("exit_type", "default")
                            expert_request_message = content.get("exit_reason", "")
                            break
                except (json.JSONDecodeError, TypeError):
                    # Not a JSON message, continue normally
                    continue

        # Update state with exit condition
        state["should_exit_to_different_node"] = should_exit
        state["exit_reason"] = exit_reason
        state["exit_type"] = exit_type
        state["expert_request_message"] = expert_request_message
        state["messages"] += messages
        return state
    return tool_node_with_decision


def create_summarize_node(model: BaseChatOpenAI):
    """
    Creates a node that summarizes the correction process using the provided model.
    This node can be used to generate a summary of the corrections made.
    """
    # The conversation history, excluding the system message, is summarized if it exceeds a certain number of messages
    # and these messages exceed a certain number of tokens.
    MESSAGES_BEFORE_SUMMARY = 20  # Number of messages to consider before summarizing
    TOKENS_BEFORE_SUMMARY = 10000  # Number of tokens to consider before summarizing
    MESSAGES_TO_KEEP = 10  # Number of messages to keep in the state after summarization
    SUMMARY_TOKENS = 5000  # Number of tokens to use for the summary

    def summarize_node(state: CorrectionState):
        """Node that summarizes the conversation history."""
        messages = state.get("messages", [])
        non_system_messages = [m for m in messages if not isinstance(m, SystemMessage)]
        if len(non_system_messages) > MESSAGES_BEFORE_SUMMARY:
            messages_to_consider = messages[:-MESSAGES_TO_KEEP]
            non_system_messages = [m for m in messages_to_consider if not isinstance(m, SystemMessage)]
            n_tokens = count_tokens_approximately(non_system_messages)
            if n_tokens > TOKENS_BEFORE_SUMMARY:
                logger.debug(f"Summarizing conversation history with {len(messages_to_consider)} messages and "
                             f"{n_tokens} tokens", msg_type="node", highlight=True)
                running_messages = state.get("running_summary", None)
                summary_result = summarize_messages(messages_to_consider, running_summary=running_messages,
                                                    model=model, max_tokens=SUMMARY_TOKENS)
                new_messages = summary_result.messages + messages[-MESSAGES_TO_KEEP:]
                state["messages"] = new_messages
                state["running_summary"] = summary_result.running_summary
                logger.debug(f"Summary generated with {len(new_messages)} messages remaining", msg_type="node",
                             highlight=True)
                logger.debug(f"Summary content: {new_messages[-1].content}", msg_type="node", highlight=True)
        return state

    return summarize_node


def create_expert_nodes(model: BaseChatOpenAI, system_prompt: str, callback_func: Callable):
    """
    Creates a node that invokes an expert system based on the LLM's request.
    This node is used when the LLM suggests invoking an expert for further assistance.
    """

    def init_expert_node(state: CorrectionState):
        """Node that initializes the expert request based on the LLM's suggestion."""
        expert_request_message = state.get("expert_request_message", "")
        messages = [system_prompt, HumanMessage(content=expert_request_message)]
        logger.debug(f"Initializing expert node with request", msg_type="node", highlight=True)
        state["expert_messages"] = messages
        state["expert_request_message"] = None
        return state

    def invoke_expert_node(state: CorrectionState):
        """Node that handles the invocation of an expert based on the LLM's request."""
        logger.debug(f"Invoking expert node", msg_type="node", highlight=True)

        expert_messages = state.get("expert_messages", [])

        logger.debug(f"Calling expert model", msg_type="node", highlight=True)
        if callback_func():
            response = model.with_config(
                callbacks=callback_func()
            ).invoke(expert_messages)
        else:
            response = model.invoke(expert_messages)
        short_msg = f"Expert model responded"
        logger.debug(f"{short_msg}: {response}", msg_type="node", highlight=True, short_message=short_msg)

        state["expert_messages"] = expert_messages + [response]
        return state

    def exit_expert_node(state: CorrectionState):
        """Node that resumes the correction process after invoking the expert."""
        logger.debug(f"Using expert's response to continue correction", msg_type="node", highlight=True)
        expert_last_message = state["expert_messages"][-1]
        if isinstance(expert_last_message, AIMessage):
            # Append the expert's response to the messages
            state["messages"].append(HumanMessage(content=expert_last_message.content))
        else:
            logger.warning(f"Expert's last message is not an AIMessage: {expert_last_message}")
        return state

    def expert_tool_decision(state: CorrectionState) -> Literal["tools", "__end__"]:
        """
        Decision node that determines whether to follow up with tools or end the expert invocation process.
        """
        expert_last_message = state["expert_messages"][-1]
        if isinstance(expert_last_message, AIMessage) and expert_last_message.tool_calls:
            logger.debug(f"Invoking {len(expert_last_message.tool_calls)} tools after expert", msg_type="node",
                         highlight=True)
            return "tools"
        logger.debug(f"Moving on after expert", msg_type="node", highlight=True)
        return "__end__"

    return init_expert_node, invoke_expert_node, exit_expert_node, expert_tool_decision
