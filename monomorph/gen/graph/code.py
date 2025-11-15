import dataclasses
from typing import Any, Type, Literal, Optional

import httpx
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.constants import END
from langgraph.graph import MessagesState
from langgraph.graph.state import CompiledStateGraph, StateGraph
from langgraph.prebuilt import ToolNode
from openai import APITimeoutError, APIConnectionError
from pydantic import BaseModel

from .prompts import PARSING_SYSTEM_PROMPT_TEMPLATE
from ...llm.langchain.openrouter import OpenRouterChat
from ...llm.langchain.usage import CallbackContext
from ...llm.langgraph.decision.printer import ConsolePrinter
from ...llm.langgraph.utils import init_model


class CodeGenState(MessagesState):
    """
    State for the code generation process.
    """
    gen_system_prompt: str
    gen_user_prompt: str
    parsing_system_prompt: str
    parsing_attempts: int
    final_response: Any
    raw_output: Any


class CodeGenInvoker:
    """
    Basic class responsible for invoking the code generation or correction process using LLMs.
    """
    def __init__(self, output_type: Type[BaseModel], gen_model: str, parsing_model: str, tools: list[BaseTool],
                 max_attempts: int = 3, block_paid_api: bool = False, stream_mode: bool = False,
                 callback_context: Optional[CallbackContext] = None):
        self.output_type = output_type
        self.gen_model_name = gen_model
        self.parsing_model_name = parsing_model
        self.tools = tools
        self.max_attempts = max_attempts
        self.block_paid_api = block_paid_api
        self.stream_mode = stream_mode
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.callback_context = callback_context
        self.gen_model, self.parsing_model = self.init_models()
        self.graph = self._build_graph()

    def with_context(self, task: Optional[str] = None) -> Optional[CallbackContext]:
        """
        Prepare the callback context for the LLM calls.
        :param task: The task being performed (e.g. "generation", "correction")
        """
        if self.callback_context:
            callback_context = dataclasses.replace(self.callback_context)
            if task:
                callback_context.usage_task = task
            return callback_context
        return None

    def init_models(self) -> tuple[BaseChatOpenAI, BaseChatOpenAI]:
        """
        Initialize the models for code generation and parsing.
        """
        gen_model = init_model(self.gen_model_name, mode="tooling", tools=self.tools,
                               block_paid_api=self.block_paid_api, callback_context=self.with_context())
        parsing_model = init_model(self.parsing_model_name, mode="structured", output_type=self.output_type,
                                   block_paid_api=self.block_paid_api, callback_context=self.with_context("parsing"))
        return gen_model, parsing_model

    def _build_graph(self) -> CompiledStateGraph:
        """
        Build the graph for the code generation process.
        """
        builder = StateGraph(CodeGenState)
        # Define and add the node callable functions
        gen_node = self.stream_gen_llm if self.stream_mode else self.invoke_gen_llm
        builder.add_node("prompt", self.build_prompt)
        builder.add_node("agent", gen_node)
        builder.add_node("parser", self.parse_output)
        builder.add_node("tools", ToolNode(self.tools))
        # Define the entrypoint
        builder.set_entry_point("prompt")
        # Add the conditional edges
        # tool usage
        builder.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tools": "tools",
                "parse_final_answer": "parser",
            },
        )
        # parser retry
        builder.add_conditional_edges(
            "parser",
            self.check_parsing_status,
            {
                "retry_parsing": "parser",  # Loop back on failure if retries remain
                END: END,  # End on success or max retries failure
            },
        )
        # Add the edges
        builder.add_edge("prompt", "agent")
        builder.add_edge("tools", "agent")
        # Compile and return the graph
        return builder.compile()

    def build_prompt(self, state: CodeGenState) -> dict[str, Any]:
        """
        Build the prompt for the code generation process.
        """
        self.logger.debug("Building prompt", msg_type="node", highlight=True)
        # Prepare the system and user prompts
        gen_system_prompt = state.get("gen_system_prompt")
        gen_user_prompt = state.get("gen_user_prompt")
        # Prepare the messages for the LLM
        messages = [SystemMessage(content=gen_system_prompt), HumanMessage(content=gen_user_prompt)]
        return {"messages": messages}

    def parse_output(self, state: CodeGenState) -> dict[str, Any]:
        """
        Attempts to parse the final AI response into the structured output type.
        Uses retry logic with increasing context.
        """
        parsing_attempts = state.get("parsing_attempts", 0)
        self.logger.debug(f"Attempting parsing ({parsing_attempts + 1}/{self.max_attempts}) with parsing model",
                          msg_type="node", highlight=True)
        messages = state["messages"]
        parser_system_prompt = state.get("parsing_system_prompt", PARSING_SYSTEM_PROMPT_TEMPLATE.format(
            type_name=self.output_type.__class__.__name__ if self.output_type else "output"
        ))
        # Prepare input for the parser LLM based on attempt number
        parser_input_messages = []
        parser_input_messages.append(SystemMessage(content=parser_system_prompt))
        if parsing_attempts == 0:
            # First attempt: Use only the last AI message content
            last_ai_message = messages[-1]
            if isinstance(last_ai_message, AIMessage) and last_ai_message.content:
                self.logger.debug(f"Using last AI message for parsing", msg_type="node", highlight=True)
                parser_input_messages.append(
                    HumanMessage(content=f'"""\n\n{last_ai_message.content}\n\n"""'))
            else:
                self.logger.warning("last AI message is not valid for parsing. Skipping attempt.", msg_type="node",
                                    highlight=True)
                return {"parsing_attempts": parsing_attempts + 1, "final_response": None}
        else:
            # Retry attempts: Use the full conversation history
            self.logger.debug(f"Using full conversation history for parsing", msg_type="node", highlight=True)
            # Combine history into a single prompt. Let's pass the relevant history as Human message content
            # Exclude the initial system prompt. It's not relevant for the parser task
            history_str = "\n".join([
                f"{'Human' if isinstance(m, HumanMessage) else 'Assistant' if isinstance(m, AIMessage) else 'Tool'}: "
                f"{m.content}" for m in messages if not isinstance(m, SystemMessage)]
            )
            parser_input_messages.append(
                HumanMessage(content=f"Here's the complete conversation history:\n\n{history_str}")
            )
        try:
            # Invoke the parser model with structured output
            output = self.parsing_model.invoke(parser_input_messages)
            parsed_output = output["parsed"]
            raw_output = output["raw"]
            return {"final_response": parsed_output, "parsing_attempts": parsing_attempts + 1, "raw_output": raw_output}
        except KeyError as e:
            raise e
        except Exception as e:
            # FAILURE: Log error, increment attempt count, keep final_response as None
            return {"parsing_attempts": parsing_attempts + 1, "final_response": None}

    def invoke_gen_llm(self, state: CodeGenState) -> dict[str, Any]:
        """
        Invoke the LLM to generate or correct code.
        """
        self.logger.debug(f"Calling gen model {self.gen_model.model_name}", msg_type="node", highlight=True)
        if self.max_attempts:
            errors = (httpx.TimeoutException, httpx.ConnectTimeout, APITimeoutError, APIConnectionError)
            response = self.gen_model.with_retry(retry_if_exception_type=errors,
                                                 stop_after_attempt=self.max_attempts).invoke(state["messages"])
        else:
            response = self.gen_model.invoke(state["messages"])
        short_msg = f"gen model responded"
        self.logger.debug(f"{short_msg}: {response}", msg_type="node", highlight=True, short_message=short_msg)
        return {"messages": [response]}

    def stream_gen_llm(self, state: CodeGenState) -> dict[str, Any]:
        """
        Stream the LLM response for code generation or correction.
        """
        messages = state["messages"]
        self.logger.debug(f"Calling gen model", msg_type="node", highlight=True)
        self.logger.debug(f"", msg_type="ai", msg_type_suffix=" streaming", end=" ", flush=True)
        stream = self.gen_model.stream(messages)
        final_message = None
        for chunk in stream:
            if chunk.content:
                self.logger.debug(chunk.content, "ai", end="", flush=True)
            if final_message is None:
                final_message = chunk
            else:
                final_message += chunk
        short_msg = f"decision model finished responding"
        self.logger.debug("\n", end="", short_message=short_msg)  # Print a newline after streaming is complete
        # Ensure we have a valid message to return, even if the stream was empty
        if final_message is None:
            final_message = AIMessage(content="")
        return {"messages": [final_message]}

    # Define the function that determines whether to continue to the tools node or end the process
    def should_continue(self, state: CodeGenState) -> Literal["tools", "parse_final_answer"]:
        """Determines whether to continue to the tools node or proceed to final parsing."""
        last_message = state["messages"][-1]
        # If the LLM returned tool calls, route to the tools node
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            # logger.print("--- Decision: Continue to Tools ---", "node", highlight=True)
            self.logger.debug(f"Decision made: invoking {len(last_message.tool_calls)} tools", msg_type="node", highlight=True)
            return "tools"
        # Otherwise, if no tool calls, the agent *should* have produced the final structured output.
        self.logger.debug(f"Decision made: Proceeding to final parsing", msg_type="node", highlight=True)
        return "parse_final_answer"  # LangGraph constant for the end node

    # Parsing decision node
    def check_parsing_status(self, state: CodeGenState) -> Literal["retry_parsing", END]:
        """
        Checks if parsing succeeded or if retries are exhausted.
        """
        if state.get("final_response") is not None:
            final_response = state["final_response"]
            if (isinstance(final_response, self.output_type) or
                    isinstance(final_response.get("parsed", None), self.output_type)):
                self.logger.debug(f"Parsing successful, Ending workflow", msg_type="node", highlight=True)
                return END  # Success! End the graph.
            else:
                self.logger.debug(f"Parsing failed, retrying...", msg_type="node", highlight=True)
                return "retry_parsing"
        elif "parsing_attempts" not in state or state["parsing_attempts"] < self.max_attempts:
            self.logger.debug(f"Parsing failed, retrying...", msg_type="node", highlight=True)
            return "retry_parsing"  # Failed, but retries remain. Loop back.
        else:
            self.logger.debug(f"Parsing failed and max retries reached, Ending workflow", msg_type="node",
                              highlight=True)
            return END  # Failed and no more retries. End the graph (with final_response=None).


