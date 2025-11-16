from typing import Callable

from typing_extensions import TypedDict
from langchain_core.messages import AIMessage
from langchain_openai.chat_models.base import BaseChatOpenAI

from ..logging.printer import ConsolePrinter


def create_call_model_function(model_or_callback: BaseChatOpenAI | Callable, callback_func: Callable, task_str: str,
                               logger: ConsolePrinter) -> Callable:
    """ Factory function to create a model invocation function. """
    # Define the function that calls the model
    def call_model(state: TypedDict):
        logger.debug(f"Calling {task_str} model", msg_type="node", highlight=True)
        logger.debug(f"{len(state['messages'])} messages in state", msg_type="node", highlight=True)
        model = model_or_callback if isinstance(model_or_callback, BaseChatOpenAI) else model_or_callback()
        if callback_func():
            response = model.with_config(
                callbacks=callback_func()
            ).invoke(state["messages"])
        else:
            response = model.invoke(state["messages"])
        short_msg = f"{task_str} model responded"
        logger.debug(f"{short_msg}: {response}", msg_type="node", highlight=True, short_message=short_msg)
        state["messages"].append(response)
        return state

    return call_model


def create_stream_model_function(model_or_callback: BaseChatOpenAI | Callable, callback_func: Callable, task_str: str,
                                 logger: ConsolePrinter) -> Callable:
    """ Factory function to create a model streaming function. """
    # Define the function that streams the model response
    def stream_model(state: TypedDict):
        """
        Invokes the LLM with the current state, streams the response tokens,
        and returns the complete message.
        """
        messages = state["messages"]
        logger.debug(f"Calling {task_str} model", msg_type="node", highlight=True)
        logger.debug(f"", msg_type="ai", msg_type_suffix=" streaming", end=" ", flush=True)
        model = model_or_callback if isinstance(model_or_callback, BaseChatOpenAI) else model_or_callback()
        # Use the .stream() method instead of .invoke()
        stream = model.stream(messages)
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
        short_msg = f"{task_str} model finished responding"
        logger.print("\n", end="", short_message=short_msg)  # Print a newline after streaming is complete
        if final_message is None:
            final_message = AIMessage(content="")  # Or handle error appropriately
        state["messages"].append(final_message)
        return state

    return stream_model