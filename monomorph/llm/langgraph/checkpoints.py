import hashlib
import json
import pickle
import datetime
import logging
import re
from typing import Any, Dict, Optional, List, Sequence, Literal, Union
from pathlib import Path
from dataclasses import asdict, dataclass

from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ChatMessage, \
    MessageLikeRepresentation, ToolMessage
from langchain_core.prompt_values import PromptValue

from ..langchain.usage import CallbackContext
from ...validation.compilation import CompilationLogComparator


@dataclass
class CheckpointData:
    """Data structure for storing checkpoint information."""
    checkpoint_id: str
    response: Any
    run_id: Optional[str] = None
    timestamp: str = ""
    context: Optional[Dict[str, Any]] = None
    exp_id: Optional[str] = None
    prompt: Any = None


@dataclass
class CheckpointConfig:
    should_load: bool = False
    should_save: bool = False
    current_exp_id: Optional[str] = None


class CheckpointStorage:
    """Singleton class to manage checkpoint storage operations per experiment."""

    _instance = None
    _storage: Dict[str, CheckpointData] = {}  # checkpoint_id -> CheckpointData
    _storage_path: Optional[Path] = None
    # _current_exp_id: Optional[str] = None
    # _loaded_exp_id: Optional[str] = None
    _checkpoint_config: CheckpointConfig = CheckpointConfig()

    def __new__(cls, storage_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path and not hasattr(self, '_initialized'):
            self._storage_path = Path(storage_path)
            self._storage_path.mkdir(parents=True, exist_ok=True)
            self._initialized = True
        self.logger = logging.getLogger("monomorph")

    def set_config(self, exp_id: str, should_load: bool = False, should_save: bool = False):
        """
        This method updates global variables for checkpointing behavior.
        :param exp_id: The experiment ID to set.
        :param should_load: Whether to load checkpoints for this experiment.
        :param should_save: Whether to save checkpoints for this experiment.
        """
        current_exp_id = self._checkpoint_config.current_exp_id
        new_config = CheckpointConfig(should_load, should_save, exp_id)
        self._checkpoint_config = new_config
        if current_exp_id != exp_id:
            self._load_experiment_checkpoints(exp_id)
            
    def get_config(self) -> CheckpointConfig:
        """Get the current checkpoint configuration."""
        return self._checkpoint_config

    def _get_experiment_path(self, exp_id: Optional[str] = None) -> Path:
        """Get the storage path for a specific experiment."""
        exp_id = exp_id or self._checkpoint_config.current_exp_id
        if not self._storage_path:
            raise ValueError("Storage path not set")
        if not exp_id:
            raise ValueError("Current experiment ID not set in checkpoint config")
        exp_path = self._storage_path /exp_id
        exp_path.mkdir(parents=True, exist_ok=True)
        return exp_path

    def _load_experiment_checkpoints(self, exp_id: str):
        """Load checkpoints for a specific experiment."""
        if not self._storage_path:
            return
        try:
            exp_path = self._get_experiment_path(exp_id)
            storage_file = exp_path / "checkpoints.pkl"
            if storage_file.exists():
                with open(storage_file, 'rb') as f:
                    checkpoint_list: List[CheckpointData] = pickle.load(f)
                    # Convert list to dict for faster lookup
                    self._storage = {cp.checkpoint_id: cp for cp in checkpoint_list}
                    self.logger.debug(f"Loaded {len(self._storage)} checkpoints for experiment: {exp_id}")
            else:
                self._storage = {}
                self.logger.debug(f"No existing checkpoints found for experiment: {exp_id}")
        except Exception as e:
            self.logger.warning(f"Could not load checkpoints for experiment {exp_id}: {e}")
            self._storage = {}

    def _save_experiment_checkpoints(self):
        """Save current checkpoints to the experiment's storage file."""
        if not self._storage_path or self._checkpoint_config.current_exp_id is None:
            return
        try:
            exp_path = self._get_experiment_path()
            storage_file = exp_path / "checkpoints.pkl"

            # Convert dict to list for storage
            checkpoint_list = list(self._storage.values())

            with open(storage_file, 'wb') as f:
                pickle.dump(checkpoint_list, f)
            self.logger.debug(f"Saved {len(checkpoint_list)} checkpoints for experiment: "
                              f"{self._checkpoint_config.current_exp_id}")
        except Exception as e:
            self.logger.warning(f"Could not save checkpoints for experiment "
                                f"{self._checkpoint_config.current_exp_id}: {e}")

    def exists(self, checkpoint_id: str) -> bool:
        """Check if a checkpoint exists in current experiment."""
        return checkpoint_id in self._storage

    def get(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Get a checkpoint by ID from current experiment."""
        return self._storage.get(checkpoint_id)

    def set(self, checkpoint_data: CheckpointData):
        """Set a checkpoint in current experiment."""
        self._storage[checkpoint_data.checkpoint_id] = checkpoint_data
        self._save_experiment_checkpoints()

    def get_all_checkpoints(self) -> List[CheckpointData]:
        """Get all checkpoints for current experiment."""
        return list(self._storage.values())

    def clear_experiment(self, exp_id: Optional[str] = None):
        """Clear checkpoints for an experiment."""
        target_exp_id = exp_id or self._checkpoint_config.current_exp_id
        if target_exp_id and self._storage_path:
            exp_path = self._get_experiment_path(target_exp_id)
            storage_file = exp_path / "checkpoints.pkl"
            if storage_file.exists():
                storage_file.unlink()
            if target_exp_id == self._checkpoint_config.current_exp_id:
                self._storage = {}


class CheckpointLogger:
    """
    Handles checkpointing and loading of LLM responses based on context and input.
    """

    def __init__(self, callbacks: list, input_data: LanguageModelInput):
        self.callbacks = callbacks or []
        self.input_data = input_data
        self.storage = CheckpointStorage()
        self.context = self._extract_context()
        self.exp_id = self._get_exp_id()
        self.checkpoint_id = self._generate_checkpoint_id()
        self.run_id = None  # Will be set after response
        self.logger = logging.getLogger("monomorph")

    def _extract_context(self) -> Optional[CallbackContext]:
        """Extract CallbackContext from callbacks."""
        for callback in self.callbacks:
            # Check UsageCallbackHandler pattern
            if hasattr(callback, 'current_context') and callback.current_context:
                return callback.current_context
            # # Check other patterns
            # if hasattr(callback, 'context') and callback.context:
            #     return callback.context
            # # Check if callback itself is a context-like object
            # if hasattr(callback, 'app_name') and hasattr(callback, 'exp_id'):
            #     return callback
        return None

    def _get_exp_id(self) -> Optional[str]:
        """Extract experiment ID from context or global variable."""
        # if self.context and hasattr(self.context, 'exp_id'):
        #     return self.context.exp_id
        global_config = self.storage.get_config()
        return global_config.current_exp_id if global_config else None

    def _generate_checkpoint_id(self) -> Optional[str]:
        """
        Generate a unique checkpoint ID based on context and input within an experiment.
        Returns None if context is not available.
        """
        if not self.context:
            return None

        # Create a hash based on context and input
        context_dict = asdict(self.context) if hasattr(self.context, '__dataclass_fields__') else vars(self.context)

        # Remove exp_id from context dict for hashing since we're already scoped by exp_id
        context_for_hash = {k: v for k, v in context_dict.items() if k != 'exp_id'}

        # Convert input to string representation
        # input_str = str(self.input_data)
        # if hasattr(self.input_data, 'to_string'):
        #     input_str = self.input_data.to_string()
        # elif hasattr(self.input_data, 'content'):
        #     input_str = str(self.input_data.content)
        input_str = prompt_input_to_str(self.input_data)

        # Create combined hash
        combined_data = {
            'context': context_for_hash,
            'input': input_str
        }

        # Generate hash
        hash_input = json.dumps(combined_data, sort_keys=True, default=str)
        return hashlib.md5(hash_input.encode()).hexdigest()

    def can_load(self) -> bool:
        if not self.storage.get_config().should_load:
            return False

        if not self.checkpoint_id:
            return False

        if not self.exp_id:
            return False

        if not self.storage.exists(self.checkpoint_id):
            # self.logger.debug(f"Checkpoint {self.checkpoint_id} does not exist")
            return False

        return True

    def load(self) -> Any:
        """Load response from checkpoint."""
        if not self.can_load():
            raise ValueError("Cannot load checkpoint - conditions not met")

        checkpoint_data = self.storage.get(self.checkpoint_id)
        if not checkpoint_data:
            raise ValueError(f"Checkpoint data not found for ID: {self.checkpoint_id}")

        self.logger.debug(f"Loaded checkpoint: {self.checkpoint_id} from experiment: {self.exp_id}")
        return checkpoint_data.response

    def save(self, response: Any) -> None:
        """
        Save response to checkpoint if SHOULD_SAVE is True.
        """

        if not self.storage.get_config().should_save:
            self.logger.debug("Saving disabled - SHOULD_SAVE is False")
            return

        if not self.checkpoint_id:
            self.logger.warning("Cannot save checkpoint - no checkpoint_id generated")
            return

        if not self.exp_id:
            self.logger.warning("Cannot save checkpoint - no exp_id available")
            return

        if self.can_load():
            # If we can load, we should not overwrite existing checkpoint
            self.logger.debug(f"Checkpoint {self.checkpoint_id} already exists, skipping save")
            return

        if hasattr(response, "response_metadata") and response.response_metadata.get(
                "additional_kwargs", {}).get("finish_reason") == "MALFORMED_FUNCTION_CALL":
            # If the response indicates a malformed function call, we should not save it
            self.logger.warning(f"Response for checkpoint {self.checkpoint_id} is malformed, not saving")
            return

        # Extract run_id from response if available
        run_id = self._extract_run_id(response)

        # Create checkpoint data
        checkpoint_data = CheckpointData(
            checkpoint_id=self.checkpoint_id,
            response=response,
            run_id=run_id,
            timestamp=datetime.datetime.now().isoformat(),
            context=asdict(self.context) if self.context and hasattr(self.context, '__dataclass_fields__') else None,
            exp_id=self.exp_id,
            prompt=self.input_data
        )

        self.storage.set(checkpoint_data)
        self.logger.debug(f"Saved checkpoint: {self.checkpoint_id} to experiment: {self.exp_id}")

    def set_run_id(self, run_id: str):
        """Set the run_id after getting response (for potential future use)."""
        self.run_id = run_id

    def _extract_run_id(self, response: Any) -> Optional[str]:
        """Extract run_id from response. This might need adjustment based on response type."""
        # The run_id is typically available in the callback, not the response itself
        # But we'll try to extract it if it's somehow embedded in the response
        # if hasattr(response, 'run_id'):
        #     return str(response.run_id)
        # elif isinstance(response, dict) and 'run_id' in response:
        #     return str(response['run_id'])
        if isinstance(response, dict) and "response_metadata" in response:
            # Try to extract run_id from response_metadata
            metadata = response["response_metadata"]
            if isinstance(metadata, dict) and "id" in metadata:
                return str(metadata["id"])
        # If not found in response, it should be set via callback or other means
        return self.run_id

    def get_checkpoint_info(self) -> Dict[str, Any]:
        """Get information about the current checkpoint."""
        global SHOULD_LOAD, SHOULD_SAVE

        return {
            'checkpoint_id': self.checkpoint_id,
            'exp_id': self.exp_id,
            'should_load': SHOULD_LOAD,
            'should_save': SHOULD_SAVE,
            'can_load': self.can_load(),
            'exists': self.storage.exists(self.checkpoint_id) if self.checkpoint_id else False,
            'context': asdict(self.context) if self.context and hasattr(self.context, '__dataclass_fields__') else None
        }

    def clear_checkpoint(self) -> bool:
        """Clear the current checkpoint if it exists."""
        if self.checkpoint_id and self.storage.exists(self.checkpoint_id):
            # Remove from storage
            if self.checkpoint_id in self.storage._storage:
                del self.storage._storage[self.checkpoint_id]
                self.storage._save_experiment_checkpoints()
                return True
        return False


def prompt_input_to_str(input_data: LanguageModelInput) -> str:
    """
    Convert LanguageModelInput to a string representation using only the prompt string.
    Handles different types of input data.
    """
    if isinstance(input_data, str):
        return string_to_checkpoint_id(input_data)  # If input is already a string, return it directly
    elif isinstance(input_data, PromptValue):
        return string_to_checkpoint_id(input_data.to_string())  # Use the PromptValue's method to get string representation
    elif isinstance(input_data, Sequence):
        # If input is a sequence of messages, convert each message to string
        return "\n".join(message_like_to_str(msg) for msg in input_data)
    else:
        # For other types, convert to string directly
        logger = logging.getLogger("monomorph")
        logger.warning(f"Input data {input_data} is not a recognized type ({type(input_data)})")
        return string_to_checkpoint_id(str(input_data))


def string_to_checkpoint_id(input_str: str, max_words: int = 100) -> str:
    return "".join(re.sub(r'\s+', ' ', re.sub(r'\n+', ' ', input_str)).split(" ")[:max_words])


def message_like_to_str(message: MessageLikeRepresentation) -> str:
    """
    Convert a MessageLikeRepresentation to a normalized string format.
    Handles various message types including BaseMessage, HumanMessage, AIMessage, etc.
    """
    if isinstance(message, BaseMessage):
        return message_to_string(message)
    elif isinstance(message, str):
        return string_to_checkpoint_id(message)  # If it's already a string, return it directly
    elif isinstance(message, dict):
        # If it's a dictionary representation of a message
        role = message.get("role", "unknown")
        content = message.get("content", "")
        return string_to_checkpoint_id(f"{role}: {content}")
    elif isinstance(message, list) or isinstance(message, tuple):
        if len(message) == 2:
            # If it's a tuple or list with two elements, assume (role, content)
            role, content = message
            return string_to_checkpoint_id(f"{role}: {content}")
        else:
            # If it's a list of messages, convert each to string
            return "\n".join([string_to_checkpoint_id(m) for m in message])
    else:
        logger = logging.getLogger("monomorph")
        logger.warning(f"{message} is not a recognized message type: {type(message)}")
        return string_to_checkpoint_id(str(message))


def message_to_string(message: BaseMessage) -> str:
    """Convert a single message to a normalized string format."""
    if message.additional_kwargs.get("is_compilation_logs"):
        # If this is a compilation log, handle it separately
        role = "compilation_log"
        content = CompilationLogComparator().normalize_log(message.content, compare_full_log=True)
        ckpt_str = f"{role}: {content}"
        return string_to_checkpoint_id(ckpt_str, max_words=-1)
    # Get the role/type of message
    if isinstance(message, HumanMessage):
        role = "human"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, ToolMessage):
        return "tool"  # Ignore tool messages for checkpointing purposes
    elif isinstance(message, ChatMessage):
        role = message.role
    else:
        role = message.__class__.__name__.lower().replace("message", "")

    # Extract content, ignoring metadata
    content = message.content
    if isinstance(content, list):
        # Handle multimodal content
        content_parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    content_parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    # For images, just note that there's an image (without the actual URL/data)
                    content_parts.append("[IMAGE]")
                else:
                    # Handle other content types generically
                    content_parts.append(f"[{part.get('type', 'UNKNOWN').upper()}]")
            else:
                content_parts.append(str(part))
        content = "".join(content_parts)

    return string_to_checkpoint_id(f"{role}: {content}")