import logging
import os
import time
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Optional, Type, Any

from google.api_core.exceptions import InternalServerError
from grpc import FutureTimeoutError
from langchain_core.language_models import LanguageModelInput, BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI, AzureChatOpenAI
import dotenv
from langchain_openai.chat_models.base import BaseChatOpenAI
from openai import RateLimitError
from pydantic import Field, PrivateAttr

from ...llm.tracking.usage import CallbackContext, UsageCallbackHandler
from ...llm.tracking.checkpoints import CheckpointLogger
from ..._metadata import APP_NAME


logger = logging.getLogger("monomorph")


def merge_dicts_recursive(dict1: dict, dict2: dict) -> dict:
    """
    Recursively merge two dictionaries.
    Values in dict2 override values in dict1 unless both values are dictionaries,
    in which case they are merged recursively.
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if (
            key in result and
            isinstance(result[key], dict) and
            isinstance(value, dict)
        ):
            result[key] = merge_dicts_recursive(result[key], value)
        else:
            result[key] = value
    return result


class OpenRouterChat(ChatOpenAI):
    """
    Custom ChatOpenAI class for OpenRouter integration.
    """

    def __init__(self, model_name: str, require_parameters: bool = False, deny_data_collection: bool = True,
                 callback_context: Optional[CallbackContext] = None, temperature: float = 0.0, *args, **kwargs):
        dotenv.load_dotenv()
        OPENROUTER_API = "https://openrouter.ai/api/v1"
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        if OPENROUTER_API_KEY is None:
            raise ValueError("API key not found!")
        extra_body = {}
        if require_parameters or deny_data_collection:
            extra_body["provider"] = {}
            if require_parameters:
                extra_body["provider"]["require_parameters"] = require_parameters
            if deny_data_collection:
                extra_body["provider"]["data_collection"] = "deny"
            if "deepseek" in model_name:
                extra_body["provider"]["quantizations"] = ['fp8', 'fp16', 'bf16', 'fp32', 'unknown']
        default_kwargs = dict(
            default_headers={
                "X-Title": APP_NAME,
            },
            model_kwargs={
                "extra_headers": {
                    "X-Title": APP_NAME,
                },
            },
            extra_body=extra_body
        )
        if callback_context:
            callback_context.model_name = model_name
            callbacks = [UsageCallbackHandler(callback_context)]
            default_kwargs["callbacks"] = callbacks
        # purge openai_api_key and openai_api_base from kwargs
        if "openai_api_key" in kwargs:
            del kwargs["openai_api_key"]
        if "openai_api_base" in kwargs:
            del kwargs["openai_api_base"]
        # merge default kwargs with kwargs (prioritize kwargs)
        merged_kwargs = merge_dicts_recursive(default_kwargs, kwargs)
        # initialize the parent class
        super().__init__(
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=OPENROUTER_API,
            model_name=model_name,
            temperature=temperature,
            *args, **merged_kwargs
        )


class AzureFoundryChat(AzureChatOpenAI):
    def __init__(self, model_name: str, require_parameters: bool = False, deny_data_collection: bool = True,
                 callback_context: Optional[CallbackContext] = None, temperature: float = 0.0, *args, **kwargs):
        dotenv.load_dotenv()
        AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
        AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
        AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
        default_kwargs = dict()
        if callback_context:
            callback_context.model_name = model_name
            callbacks = [UsageCallbackHandler(callback_context)]
            default_kwargs["callbacks"] = callbacks
        # merge default kwargs with kwargs (prioritize kwargs)
        merged_kwargs = merge_dicts_recursive(default_kwargs, kwargs)
        # initialize the parent class
        super().__init__(
            azure_deployment=model_name,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version=AZURE_OPENAI_API_VERSION,
            api_key=AZURE_OPENAI_API_KEY,
            temperature=1,
            *args, **merged_kwargs
        )

    def invoke(self, *args, **kwargs):
        """
        Override the invoke method to handle RateLimitError
        """
        MAX_RETRIES = 3
        n_tries = 0
        error = RuntimeError("Encountered unexpected error in Azure OpenAI API")
        while n_tries < MAX_RETRIES:
            try:
                return super().invoke(*args, **kwargs)
            except RateLimitError as e:
                n_tries += 1
                wait_time = 120
                logger.error(f"Rate limit exceeded raised by Azure OpenAI API. Waiting for {wait_time} seconds before retrying.")
                logger.debug(f"Rate limit error details: {e}")
                error = e
                import time
                time.sleep(wait_time)  # Wait for 60 seconds before retrying
                logger.debug("Resuming after rate limit wait time.")
        raise error


# class GeminiChat(ChatOpenAI):
#     """
#     Custom ChatOpenAI class for Google Gemini integration.
#     """
#
#     def __init__(self, model_name: str, require_parameters: bool = False, deny_data_collection: bool = True,
#                  callback_context: Optional[CallbackContext] = None, temperature: float = 0.0,
#                  reasoning_effort: str = "medium", *args, **kwargs):
#         dotenv.load_dotenv()
#         GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/"
#         GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
#         if GEMINI_API_KEY is None:
#             raise ValueError("API key not found!")
#         extra_body = {
#             "reasoning_effort": reasoning_effort,
#         }
#         default_kwargs = dict(
#             extra_body=extra_body
#         )
#         if callback_context:
#             callback_context.model_name = model_name
#             callbacks = [UsageCallbackHandler(callback_context)]
#             default_kwargs["callbacks"] = callbacks
#         # merge default kwargs with kwargs (prioritize kwargs)
#         merged_kwargs = merge_dicts_recursive(default_kwargs, kwargs)
#         # initialize the parent class
#         super().__init__(
#             openai_api_key=GEMINI_API_KEY,
#             openai_api_base=GEMINI_API,
#             model_name=model_name,
#             temperature=temperature,
#             timeout=120,
#             *args, **merged_kwargs
#         )


class GeminiChat(ChatGoogleGenerativeAI):
    """
    Custom Chat class for Google Gemini integration.
    """
    model_name: str = Field(default="unknown", description="The model name to use for the chat. "
                                                           "Same as model in ChatGoogleGenerativeAI")

    def __init__(self, model_name: str, require_parameters: bool = False, deny_data_collection: bool = True,
                 callback_context: Optional[CallbackContext] = None, temperature: float = 0.0,
                 reasoning_effort: str = "medium", *args, **kwargs):
        dotenv.load_dotenv()
        # GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/"
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if GEMINI_API_KEY is None:
            raise ValueError("API key not found!")
        extra_body = {
            "reasoning_effort": reasoning_effort,
        }
        default_kwargs = dict(
            model_kwargs=extra_body
        )
        if callback_context:
            callback_context.model_name = model_name
            callbacks = [UsageCallbackHandler(callback_context)]
            default_kwargs["callbacks"] = callbacks
        # merge default kwargs with kwargs (prioritize kwargs)
        merged_kwargs = merge_dicts_recursive(default_kwargs, kwargs)
        # initialize the parent class
        super().__init__(
            google_api_key=GEMINI_API_KEY,
            # openai_api_base=GEMINI_API,
            model=model_name,
            temperature=temperature,
            timeout=120,
            **merged_kwargs
        )
        self.model_name = model_name


class OpenRouterChatWithCheckpoint(OpenRouterChat):
    def invoke(self, input: LanguageModelInput, config: Optional[RunnableConfig] = None,
               *args, **kwargs):
        """
        Initialize the OpenRouterChatWithCheckpoint with additional parameters.
        """
        if config is not None and "callbacks" in config:
            callbacks = config["callbacks"]
            if not (isinstance(callbacks, list) and len(callbacks) > 0):
                callbacks = self.callbacks
        else:
            callbacks = self.callbacks
        checkpointer = CheckpointLogger(callbacks, input)
        if checkpointer.can_load():
            response = checkpointer.load()
        else:
            response = super().invoke(input, *args, **kwargs)
            checkpointer.save(response)
        return response


def create_class_with_checkpoint(class_type: Type[BaseChatOpenAI] | Type[ChatGoogleGenerativeAI], *args, **kwargs) -> type:
    """
    Factory function to create a subclass of ChatOpenAI that supports checkpoints.
    """
    assert issubclass(class_type, BaseChatOpenAI) or issubclass(class_type, ChatGoogleGenerativeAI), \
        "class_type must be a subclass of BaseChatOpenAI or ChatGoogleGenerativeAI"

    # if issubclass(class_type, ChatGoogleGenerativeAI):
    #     class MyChatSubType(class_type):
    #         model_name: str = Field(default="unknown", description="The model name to use for the chat. "
    #                                                                "Same as model in ChatGoogleGenerativeAI")
    #         def __init__(self, model_name: str, *args, **kwargs):
    #             super().__init__(model_name=model_name, *args, **kwargs)
    #             self.model_name = model_name
    #
    # else:
    #     MyChatSubType = class_type

    class ChatOpenAIWithCheckpoint(class_type):
        def invoke(self, input: LanguageModelInput, config: Optional[RunnableConfig] = None,
                   *args, **kwargs):
            if config is not None and "callbacks" in config:
                callbacks = config["callbacks"]
                if not (isinstance(callbacks, list) and len(callbacks) > 0):
                    callbacks = self.callbacks
            else:
                callbacks = self.callbacks
            checkpointer = CheckpointLogger(callbacks, input)
            if checkpointer.can_load():
                response = checkpointer.load()
            else:
                try:
                    response = super().invoke(input, *args, **kwargs)
                except InternalServerError as e:
                    logger.error(f"Internal server error during model invocation: {e}")
                    raise e
                checkpointer.save(response)
            return response

    return ChatOpenAIWithCheckpoint


def create_class_with_fallback(
        class_type: Type[BaseChatOpenAI] | Type[ChatGoogleGenerativeAI],
        invoke_timeout: float = 60.0,
        fallback_model: Optional[BaseChatModel] = None,
        max_retries: int = 0,
        retry_delay: float = 2.0,
        *args, **kwargs
) -> type:
    """
    Factory function to create a subclass that supports both timeout/fallback.
    """
    assert issubclass(class_type, BaseChatOpenAI) or issubclass(class_type, ChatGoogleGenerativeAI), \
        "class_type must be a subclass of BaseChatOpenAI or ChatGoogleGenerativeAI"

    class ChatWithTimeOut(class_type):
        # Timeout configuration
        _invoke_timeout: float = PrivateAttr(default=60.0)
        _fallback_model: Optional[BaseChatModel] = PrivateAttr(default=None)
        _max_retries: int = PrivateAttr(default=0)
        _retry_delay: float = PrivateAttr(default=2.0)

        def __init__(self, *init_args, **init_kwargs):
            # Initialize parent class
            super().__init__(*init_args, **init_kwargs)
            # Extract timeout-specific parameters
            self._invoke_timeout = init_kwargs.pop('invoke_timeout', invoke_timeout)
            self._max_retries = init_kwargs.pop('max_retries', max_retries)
            self._retry_delay = init_kwargs.pop('retry_delay', retry_delay)

            # Initialize fallback model
            self._fallback_model = fallback_model

        def _invoke_with_timeout(self, *args, **kwargs) -> Any:
            """Execute the model invocation with a timeout."""
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(super().invoke, *args, **kwargs)
                try:
                    result = future.result(timeout=self._invoke_timeout)
                    return result
                except FutureTimeoutError:
                    print(f"Model invocation timed out after {self._invoke_timeout} seconds")
                    logger.warning(f"Model invocation timed out after {self._invoke_timeout} seconds")
                    future.cancel()
                    raise TimeoutError(f"Model invocation timed out after {self._invoke_timeout} seconds")

        def invoke(self, *args, **kwargs):
            """Invoke with timeout, fallback, and checkpoint functionality."""

            # Timeout and fallback logic
            last_exception = None

            for attempt in range(self._max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"Retrying primary model (attempt {attempt + 1}/{self._max_retries + 1})")
                        time.sleep(self._retry_delay)

                    result = self._invoke_with_timeout(*args, **kwargs)

                    return result

                except (TimeoutError, FutureTimeoutError) as e:
                    last_exception = e
                    logger.warning(f"Primary model attempt {attempt + 1} failed: {type(e).__name__}: {e}")

                    if attempt == self._max_retries and self._fallback_model:
                        break
                    elif attempt == self._max_retries:
                        raise e

            # Try fallback
            if self._fallback_model:
                try:
                    logger.info("Attempting fallback model")
                    result = self._fallback_model.invoke(*args, **kwargs)
                    return result

                except Exception as fallback_error:
                    logger.error(f"Fallback model failed: {fallback_error}")
                    raise last_exception from fallback_error
            else:
                raise last_exception

    return ChatWithTimeOut
