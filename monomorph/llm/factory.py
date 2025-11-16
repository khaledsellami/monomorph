import importlib.resources
import json
import logging
from typing import Optional, Callable, Type

from langchain_openai.chat_models.base import BaseChatOpenAI
from pydantic import BaseModel

from .._metadata import PACKAGE_NAME
from .custom_chat import (OpenRouterChat, AzureFoundryChat, GeminiChat, create_class_with_checkpoint,
                          create_class_with_fallback)
from .tracking.usage import CallbackContext


with importlib.resources.open_text(f'{PACKAGE_NAME}.resources', f'model_map.json') as f:
    MODEL_MAP = json.load(f)


def get_model(name: str, block_paid_api: bool = True) -> str:
    logger = logging.getLogger(PACKAGE_NAME)
    if name in MODEL_MAP["free"]:
        full_name = MODEL_MAP["free"].get(name)
    elif name in MODEL_MAP["paid"]:
        if block_paid_api:
            logger.error(f"Paid model {name} is blocked!")
            raise ValueError(f"Paid model {name} is blocked!")
        logger.warning(f"Using paid model {name}")
        full_name = MODEL_MAP["paid"].get(name)
    else:
        logger.error(f"Model {name} not found!")
        raise ValueError(f"Model {name} not found!")
    return full_name


def init_model(model_name: Optional[str], mode: str = "tooling", tools: Optional[list[Callable]] = None,
               output_type: Optional[Type[BaseModel]] = None, block_paid_api: bool = False,
               callback_context: Optional[CallbackContext] = None, checkpoint: bool = True,
               temperature: float = 0.0, fallback_model: Optional[BaseChatOpenAI] = None) -> Optional[BaseChatOpenAI]:
    """
    Initializes the model if a short model name is provided.
    """
    if model_name:
        BaseClassToUse, full_model_name, kwargs = get_chat_class(model_name, block_paid_api)
        ChatClass = BaseClassToUse if not checkpoint else create_class_with_checkpoint(BaseClassToUse)
        if fallback_model:
            ChatClass = create_class_with_fallback(ChatClass, fallback_model=fallback_model)
        model = ChatClass(full_model_name, require_parameters=True, callback_context=callback_context,
                          temperature=temperature, **kwargs)
        if tools is not None:
            bound_model: BaseChatOpenAI = model.bind_tools(tools)
            return bound_model
        elif mode == "structured" and output_type:
            structured_model: BaseChatOpenAI = model.with_structured_output(output_type, include_raw=True)
            return structured_model
        else:
            return model
    else:
        return None


def get_chat_class(model_name: str, block_paid_api: bool = False) -> tuple[Type[BaseChatOpenAI], str, dict]:
    """
    Returns the appropriate chat class based on the model name and the model name without the prefix.
    The model name can be "mm_openrouter/owner/model" or "mm_azure/my_model" or "my_model".

    Args:
        model_name (str): The model name, which can include a prefix like "mm_openrouter" or "mm_azure".
        block_paid_api (bool): If True, blocks access to paid OpenRouter APIs.
    Returns:
        tuple: A tuple containing the chat class and the full model name without the prefix.
    """
    parts = model_name.split("/")
    if len(parts) == 1:
        # default model name without prefix
        return OpenRouterChat, get_model(model_name, block_paid_api), {}
    name = "/".join(parts[1:])
    if parts[0] == "mm_openrouter":
        # explicitly specified OpenRouter model
        return OpenRouterChat, get_model(name, block_paid_api), {}
    elif parts[0] == "mm_azure":
        # Azure foundry/openai deployment
        return AzureFoundryChat, name, {}
    elif parts[0] == "mm_google":
        # Google Gemini model
        name_split = name.split("::")
        if len(name_split) > 1:
            name = name_split[0]
            reasoning_effort = name_split[1]
            return GeminiChat, name, {"reasoning_effort": reasoning_effort}
        return GeminiChat, name, {}
    else:
        # Default to OpenRouterChat for any other prefix
        return OpenRouterChat, model_name, {}
