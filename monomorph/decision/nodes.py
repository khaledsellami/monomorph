from typing import Literal, Callable, Optional

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.graph import MessagesState

from .models import RefactoringDecision
from ..logging.printer import ConsolePrinter
from ..llm.tracking.usage import UsageCallbackHandler

logger = ConsolePrinter.get_printer("monomorph")


class AgentState(MessagesState):
    # Final structured response from the agent
    final_response: RefactoringDecision
    parsing_attempts: int


class DecisionCallBackHandler:
    def __init__(self):
        self.decision_callback: Optional[UsageCallbackHandler] = None
        self.parsing_callback: Optional[UsageCallbackHandler] = None

    def get_decision_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the decision callback handler if it exists.
        """
        return [self.decision_callback] if self.decision_callback else None

    def get_parsing_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the parsing callback handler if it exists.
        """
        return [self.parsing_callback] if self.parsing_callback else None


def define_decision_nodes(decision_model: BaseChatOpenAI, parser_model: Optional[BaseChatOpenAI] = None,
                          parser_system_prompt: str = "",
                          callback_handler: Optional[DecisionCallBackHandler] = None) -> list[Callable]:
    """
    Defines the functions for the decision-making process in the workflow based on the given models.

    :param decision_model: The model used for making refactoring decisions.
    :param parser_model: The model used for parsing the output into structured data. Defaults to the decision model.
    :param parser_system_prompt: The system prompt for the parser model.
    :param callback_handler: Optional callback handler for usage tracking.
    :return: The list of functions to be used in the workflow.
    """
    MAX_PARSING_RETRIES = 3
    # If no parser model is provided, use the decision model
    if parser_model is None:
        parser_model = decision_model

    if callback_handler is None:
        callback_handler = DecisionCallBackHandler()

    # Define the function that calls the model
    def call_model(state: AgentState):
        # logger.print("--- Calling LLM for Agent ---", "node", highlight=True)
        logger.debug(f"Calling decision model", msg_type="node", highlight=True)
        # response = decision_model.invoke(state["messages"], callbacks=callback_handler.get_decision_callback())
        if callback_handler.get_decision_callback():
            response = decision_model.with_config(callbacks=callback_handler.get_decision_callback()).invoke(state["messages"])
        else:
            response = decision_model.invoke(state["messages"])
        # logger.print(response, "ai", msg_type_suffix=" response")
        short_msg = f"decision model responded"
        logger.debug(f"{short_msg}: {response}", msg_type="node", highlight=True, short_message=short_msg)
        # We return a list, because this will get added to the existing list
        return {"messages": [response]}

    # Define the function that streams the model response
    def stream_model(state: AgentState):
        """
        Invokes the LLM with the current state, streams the response tokens,
        and returns the complete message.
        """
        messages = state["messages"]
        # logger.print("--- Calling LLM for Agent ---", "node", highlight=True)
        logger.debug(f"Calling decision model", msg_type="node", highlight=True)
        # logger.print(f"", "ai", msg_type_suffix=" streaming", end=" ", flush=True)  # Label for streamed output
        logger.debug(f"", msg_type="ai", msg_type_suffix=" streaming", end=" ", flush=True)
        # Use the .stream() method instead of .invoke()
        stream = decision_model.stream(messages)
        # Accumulate chunks to build the final message
        final_message = None
        for chunk in stream:
            # Print the content of the chunk (token)
            if chunk.content:
                logger.print(chunk.content, "ai", end="", flush=True)
            # Add the chunk to the final message
            if final_message is None:
                final_message = chunk
            else:
                final_message += chunk
        short_msg = f"decision model finished responding"
        logger.print("\n", end="", short_message=short_msg)  # Print a newline after streaming is complete
        # Ensure we have a valid message to return, even if the stream was empty
        if final_message is None:
            final_message = AIMessage(content="")  # Or handle error appropriately
        # The accumulated final_message now contains the full content, tool calls, parsed output etc.
        return {"messages": [final_message]}

    # Define the function that determines whether to continue to the tools node or end the process
    def should_continue(state: AgentState) -> Literal["tools", "parse_final_answer"]:
        """Determines the next step based on the last message."""
        last_message = state["messages"][-1]
        # If the LLM returned tool calls, route to the tools node
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            # logger.print("--- Decision: Continue to Tools ---", "node", highlight=True)
            logger.debug(f"Decision made: invoking {len(last_message.tool_calls)} tools", msg_type="node", highlight=True)
            return "tools"
        # Otherwise, if no tool calls, the agent *should* have produced the final structured output.
        # logger.print("--- Decision: Proceed to Final Parsing", "node", highlight=True)
        logger.debug(f"Decision made: Proceeding to final parsing", msg_type="node", highlight=True)
        return "parse_final_answer"  # LangGraph constant for the end node

    # Parsing decision node
    def check_parsing_status(state: AgentState) -> Literal["retry_parsing", "__end__"]:
        """
        Checks if parsing succeeded or if retries are exhausted.
        """
        if state.get("final_response") is not None:
            final_response = state["final_response"]
            if isinstance(final_response, RefactoringDecision) or isinstance(final_response.get("parsed", None), RefactoringDecision):
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
            return "__end__"  # Failed and no more retries. End the graph (with final_response=None).

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
                return {"parsing_attempts": parsing_attempts + 1, "final_response": None}
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
                parsed_output: RefactoringDecision = output["parsed"]
            else:
                logger.error(f"Missing 'parsed' key in response. Using initial output",
                             msg_type="node", highlight=True)
                parsed_output = output
            # logger.print("--- Successfully Parsed Output ---", "node", highlight=True)
            return {"final_response": parsed_output, "parsing_attempts": parsing_attempts + 1}
        except Exception as e:
            # FAILURE: Log error, increment attempt count, keep final_response as None
            # logger.print(f"--- Parsing Attempt {parsing_attempts + 1} Failed ---", "error", highlight=True)
            return {"parsing_attempts": parsing_attempts + 1, "final_response": None}

    return [call_model, stream_model, should_continue, check_parsing_status, parse_output]
