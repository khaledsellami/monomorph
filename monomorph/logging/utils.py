import contextlib
import sys
import os
import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import MessagesState

from .printer import ConsolePrinter


@contextlib.contextmanager
def silence_all(silence_stdout=True, silence_stderr=True, log_level=logging.CRITICAL):
    # Store original stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    # Store the original logging level
    original_level = logging.root.getEffectiveLevel()
    try:
        # Redirect stdout if requested
        if silence_stdout:
            sys.stdout = open(os.devnull, 'w')

        # Redirect stderr if requested
        if silence_stderr:
            sys.stderr = open(os.devnull, 'w')

        # Set logging level
        logging.root.setLevel(log_level)

        # Run the code inside the with block
        yield

    finally:
        # Restore original stdout/stderr
        if silence_stdout:
            sys.stdout.close()
            sys.stdout = old_stdout

        if silence_stderr:
            sys.stderr.close()
            sys.stderr = old_stderr

        # Restore the original logging level
        logging.root.setLevel(original_level)
        
        
def log_inputs(logger: ConsolePrinter, input_messages: MessagesState, preview_length: int = 100):
    # Print Initial Messages with Color
    logger.debug("Preparing System and first user prompts", msg_type="workflow", highlight=True)
    for msg in input_messages["messages"]:
        if isinstance(msg, SystemMessage):
            logger.debug(msg.content, msg_type="system", short_message="System Message")
        elif isinstance(msg, HumanMessage):
            # Limit printing potentially very long user content for readability
            content_preview = (msg.content[:preview_length] + '...') if len(
                msg.content) > preview_length else msg.content
            logger.debug(content_preview, msg_type="user", short_message="User Message")
            

def log_outputs(node_name: str, logger: ConsolePrinter, new_messages: MessagesState, preview_length: int = 100, 
                verbosity: int = 1):
    if verbosity < 1:
        return
    if node_name == "parser":
        return # Don't log parser outputs
    for msg in new_messages:
        if isinstance(msg, AIMessage):
            # This AIMessage is the one accumulated *after* streaming in call_model
            logger.debug(f"Node: '{node_name}'", msg_type="ai")
            if msg.tool_calls:
                logger.debug("Tool Calls:", msg_type="ai_toolcall", short_message="Model requested Tool Calls")
                for tc in msg.tool_calls:
                    logger.debug(f" - Tool: {tc['name']}", msg_type="ai_toolcall")
                    logger.debug(f" - Args: {tc['args']}", msg_type="ai_toolcall")
                    logger.debug(f" - ID: {tc['id']}", msg_type="ai_toolcall")
            # if hasattr(msg, 'parsed') and isinstance(msg.parsed, CompilationAnalysisReport):
            #     logger.debug(f"  - Decision: {msg.parsed.decision}", msg_type="decision")
        elif isinstance(msg, ToolMessage):
            logger.debug(f"- Node - {node_name}", msg_type="tool")
            # Shorten potentially long tool outputs in the live log
            content_preview = (msg.content[:preview_length] + '...') if len(
                msg.content) > preview_length else msg.content
            logger.debug(f"- Content: {content_preview}", msg_type="tool")
            logger.debug(f"- Tool Call ID: {msg.tool_call_id}", msg_type="tool")


def create_conversation_log(logger: ConsolePrinter, final_state_dict) -> list[str] | None:
    """
    Creates a conversation log from the final state dictionary.
    """
    conversation_log = []
    if final_state_dict:
        logger.debug(f"Creating Conversation Log", msg_type="workflow", highlight=True)
        for message in final_state_dict.get('messages', []):
            if isinstance(message, AIMessage):
                conversation_log.append(f"# AI: \n{str(message.content).replace('# ', '## ')}")
            elif isinstance(message, HumanMessage):
                conversation_log.append(f"# User: \n{str(message.content).replace('# ', '## ')}")
            elif isinstance(message, ToolMessage):
                conversation_log.append(f"# Tool: \n{str(message.content).replace('# ', '## ')}")
            elif isinstance(message, SystemMessage):
                conversation_log.append(f"# System: \n{str(message.content).replace('# ', '## ')}")
            else:
                conversation_log.append(f"# Unknown: \n{message}")
    return conversation_log
