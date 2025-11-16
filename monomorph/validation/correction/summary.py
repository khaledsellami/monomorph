import uuid
from typing import Callable

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import BaseChatOpenAI

from .nodes import CorrectionState
from ...logging.printer import ConsolePrinter


logger = ConsolePrinter.get_printer("monomorph")


# Prompts (same as above)
INITIAL_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are tasked with creating a concise summary of a conversation. 
    Focus on key points, decisions made, important information exchanged, and the overall flow of the conversation.
    Be concise but comprehensive. Maintain the context that would be important for continuing the conversation."""),
    ("human", "Please summarize the following conversation:\n\n{conversation}")
])

UPDATE_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are tasked with updating an existing conversation summary with new messages.
    Integrate the new information while maintaining the key points from the previous summary.
    Be concise but comprehensive. Focus on what's important for continuing the conversation."""),
    ("human", """Previous summary:
{previous_summary}

New messages to incorporate:
{new_messages}

Please provide an updated summary that incorporates both the previous summary and the new messages.""")
])


def format_messages_for_summary(messages: list[BaseMessage]) -> str:
    """Format messages for summarization prompt."""
    formatted = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            formatted.append(f"SYSTEM: {msg.content}")
        elif isinstance(msg, HumanMessage):
            formatted.append(f"USER: {msg.content}")
        elif isinstance(msg, AIMessage):
            formatted.append(f"ASSISTANT: {msg.content}")
        elif isinstance(msg, ToolMessage):
            formatted.append(f"TOOL: {msg.content}")
        else:
            formatted.append(f"{type(msg).__name__}: {msg.content}")
    return "\n".join(formatted)


def generate_summary(model: BaseChatOpenAI, messages: list[BaseMessage], previous_summary: str | None = None,
                     callback_func: Callable = None) -> str:
    """
    Generate a summary of the conversation messages using the provided model.
    """
    if previous_summary is None:
        # Create initial summary
        prompt = INITIAL_SUMMARY_PROMPT.format_prompt(
            conversation=format_messages_for_summary(messages)
        )
        logger.debug("Creating initial summary", msg_type="node", highlight=True)
    else:
        # Update existing summary
        prompt = UPDATE_SUMMARY_PROMPT.format_prompt(
            previous_summary=previous_summary,
            new_messages=format_messages_for_summary(messages)
        )
        logger.debug("Updating existing summary", msg_type="node", highlight=True)
    if callback_func is not None:
        summary_response = model.with_config(callbacks=callback_func()).invoke(prompt.to_messages())
    else:
        summary_response = model.invoke(prompt.to_messages())
    return summary_response.content.strip()


def create_custom_summarize_node(model: BaseChatOpenAI, callback_func: Callable | None = None):
    """
     Creates a custom summarization node that manages conversation history with direct control.
    """

    # Configuration
    MESSAGES_BEFORE_SUMMARY = 10  # Start summarizing after 20 messages total
    TOKENS_BEFORE_SUMMARY = 5000
    MESSAGES_TO_SUMMARY_WINDOW = 5  # Create summary every 10 messages
    MESSAGES_TO_KEEP = 5  # Keep the last 10 messages after summarization
    MAX_SUMMARY_TOKENS = 1000

    def summarize_node(state: CorrectionState):

        # Get state fields
        full_conversation = state.get("full_conversation", {})
        current_summary = state.get("current_summary", None)
        messages = state.get("messages", [])
        last_summarized_index = state.get("last_summarized_index", -1)  # Track what's been summarized

        for msg in messages:
            msg_id = msg.id
            if msg_id is None:
                if isinstance(msg, ToolMessage):
                    msg_id = msg.tool_call_id
                else:
                    msg_id = str(uuid.uuid4())[:8]
                    msg.id = msg_id
            msg_is_summary = msg.additional_kwargs.get("is_summary", False)
            if msg_id not in full_conversation and not msg_is_summary:
                full_conversation[msg_id] = msg

        state["full_conversation"] = full_conversation
        full_conversation_list = list(full_conversation.values())
        # # Initialize full_conversation if empty
        # if not full_conversation:
        #     full_conversation = messages.copy()
        #     state["full_conversation"] = full_conversation

        # Separate system messages
        system_messages = [m for m in full_conversation_list if isinstance(m, SystemMessage)]
        non_system_messages = [m for m in full_conversation_list if not isinstance(m, SystemMessage)]

        # Check if summarization is needed
        if len(non_system_messages) <= MESSAGES_BEFORE_SUMMARY:
            logger.debug(f"Not enough messages to summarize: {len(non_system_messages)} messages "
                         f"({MESSAGES_BEFORE_SUMMARY} required)", msg_type="node")
            return state

        # Determine which messages to summarize
        messages_to_summarize = non_system_messages[:-MESSAGES_TO_KEEP]
        recent_messages = non_system_messages[-MESSAGES_TO_KEEP:]

        # Find new messages since last summary
        new_messages_start = last_summarized_index + 1 if last_summarized_index >= 0 else 0
        new_messages_to_summarize = messages_to_summarize[new_messages_start:]

        # Calculate tokens
        n_tokens = count_tokens_approximately(new_messages_to_summarize)

        if n_tokens <= TOKENS_BEFORE_SUMMARY or len(new_messages_to_summarize) <= MESSAGES_TO_SUMMARY_WINDOW:
            # No need to summarize yet
            logger.debug(f"No summarization needed: {len(new_messages_to_summarize)} new messages "
                         f"({n_tokens} tokens, threshold: {TOKENS_BEFORE_SUMMARY})", msg_type="node")
            return state

        logger.debug(f"Summarizing: {len(new_messages_to_summarize)} new messages "
                     f"(total to summarize: {len(messages_to_summarize)}, "
                     f"keeping: {len(recent_messages)})", msg_type="node", highlight=True)

        try:
            new_summary = generate_summary(model, new_messages_to_summarize, previous_summary=current_summary,
                                           callback_func=callback_func)

            # Create summary message
            summary_message = HumanMessage(
                content=f"[CONVERSATION SUMMARY]: {new_summary}",
                additional_kwargs={"is_summary": True}
            )

            # Build new message list
            ## If the recent messages include tool calls, we need to ensure that their corresponding ai messages are included even if they are not in the last MESSAGES_TO_KEEP
            first_tool_message_idx = None
            for idx, msg in enumerate(recent_messages):
                if isinstance(msg, ToolMessage):
                    first_tool_message_idx = idx
                    break
            if first_tool_message_idx is not None:
                corresponding_tool_msg = None
                # Find the corresponding AI message
                tool_msg = recent_messages[first_tool_message_idx]
                for msg in recent_messages[first_tool_message_idx::-1]:
                    if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and any([tool_msg.tool_call_id == call.get("id") for call in msg.tool_calls]):
                        corresponding_tool_msg = msg
                        break
                if corresponding_tool_msg is None:
                    # Search backwards in the full conversation starting from the last summarized index
                    for idx in range(len(messages_to_summarize)-1, -1, -1):
                        msg = messages_to_summarize[idx]
                        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                            if any([tool_msg.tool_call_id == call.get("id") for call in msg.tool_calls]):
                                recent_messages = messages_to_summarize[idx:] + recent_messages
                                break
                            else:
                                logger.warning(f"Could not find tool call for {msg}")
                            break

            new_messages = system_messages + [summary_message] + recent_messages

            # Update tracking
            new_last_summarized_index = len(messages_to_summarize) - 1

            logger.debug(f"Summary updated. New message count: {len(new_messages)}",
                         msg_type="node", highlight=True)

            state["current_summary"] = new_summary
            state["last_summarized_index"] = new_last_summarized_index
            state["messages"] = new_messages
            return state

        except Exception as e:
            logger.error(f"Summarization failed: {e}", msg_type="node")
            # If summarization fails, just keep the current state
            raise e
            # return state

    return summarize_node
