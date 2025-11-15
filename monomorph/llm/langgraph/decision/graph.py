from typing import Optional

from langchain_core.tools import BaseTool
from langchain_openai.chat_models.base import BaseChatOpenAI
from langgraph.constants import END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph

from .nodes import define_decision_nodes, AgentState, DecisionCallBackHandler
from ...langchain.openrouter import OpenRouterChat


def create_refact_decision_graph(tools: list[BaseTool], decision_model: BaseChatOpenAI,
                                 parser_model: Optional[BaseChatOpenAI] = None, parser_system_prompt: str = "",
                                 stream: bool = False,
                                 callback_handler: Optional[DecisionCallBackHandler] = None) -> CompiledStateGraph:
    """
    Creates a state graph for the refactoring decision process.

    Args:
        decision_model: The model used for making refactoring decisions.
        parser_model: The model used for parsing the output into structured data.
        tools: The tools to be used in the decision-making process.
        parser_system_prompt: The system prompt for the parser model.
        stream: Whether to stream the model response or not.
        callback_handler: Optional callback handler for tracking llm usage

    Returns:
        graph: The compiled state graph.
    """

    # Define the node callable functions
    call_model, stream_model, should_continue, check_parsing_status, parse_output = define_decision_nodes(
        decision_model, parser_model, parser_system_prompt, callback_handler=callback_handler)
    agent_node = call_model if not stream else stream_model
    # Define a new graph
    workflow = StateGraph(AgentState)
    # Define the nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("parser", parse_output)
    # Set the entrypoint
    workflow.set_entry_point("agent")
    # Add the conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
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
    workflow.add_edge("tools", "agent")
    # Compile the graph
    return workflow.compile()
