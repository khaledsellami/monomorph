import logging
import datetime
import json
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal
from collections import deque

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


@dataclass
class CallbackContext:
    """Context for callback handlers to track the current state."""
    app_name: str = ""
    exp_id: str = ""
    refact_type: Literal["DTO-Based", "ID-Based"] = "DTO-Based"
    class_name: str = ""
    target_microservice: str = ""
    file_type: Literal["server", "client", "contract", "mapper", "decision"] = "server"
    usage_task: Literal["generation", "correction", "decision", "parsing", "expert", "summary"] = "generation"
    model_name: str = ""

    @classmethod
    def from_dict(cls, d: dict):
        """Create a CallbackContext instance from a dictionary."""
        return CallbackContext(
            app_name=d.get("app_name", ""),
            exp_id=d.get("exp_id", ""),
            refact_type=d.get("refact_type", "DTO-Based"),
            class_name=d.get("class_name", ""),
            target_microservice=d.get("target_microservice", ""),
            file_type=d.get("file_type", "server"),
            usage_task=d.get("usage_task", "generation"),
            model_name=d.get("model_name", "")
        )


@dataclass
class UsageMetadata:
    """Metadata for usage tracking."""
    timestamp: str
    response_id: str
    openrouter_id: str
    metadata: dict
    context: CallbackContext

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        """Create a UsageMetadata instance from a dictionary."""
        return UsageMetadata(
            timestamp=d.get("timestamp"),
            response_id=d.get("response_id"),
            openrouter_id=d.get("openrouter_id"),
            metadata=d.get("metadata", {}),
            context=CallbackContext.from_dict(d.get("context", {}))
        )


class GlobalUsageTracker:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.call_records = deque()
                    cls._instance.records_lock = threading.Lock()
                    cls._instance.io_lock = threading.Lock()
                    cls._instance._auto_save = False
                    cls._instance._auto_save_path = None
        return cls._instance

    @classmethod
    def set_auto_save(cls, auto_save_path: str):
        """
        Set auto-save path for usage history.
        Args:
            auto_save_path: Path to save the usage history JSON file
        """
        if cls._instance is not None:
            cls._instance._auto_save = True
            cls._instance._auto_save_path = auto_save_path

    @classmethod
    def disable_auto_save(cls):
        """Disable auto-save functionality."""
        if cls._instance is not None:
            cls._instance._auto_save = False
            cls._instance._auto_save_path = None

    def add_record(self, record):
        with self.records_lock:
            self.call_records.append(record)
        if self._auto_save and self._auto_save_path is not None:
            self.save_usage_history(self._auto_save_path)

    def add_records(self, records):
        """
        Add multiple records thread-safely.
        Args:
            records: List of UsageMetadata instances to add
        """
        with self.records_lock:
            self.call_records.extend(records)
        if self._auto_save and self._auto_save_path is not None:
            self.save_usage_history(self._auto_save_path)

    def reset_usage_history(self):
        """Clear all stored usage history thread-safely"""
        with self.records_lock:
            self.call_records.clear()

    def save_usage_history(self, path: str):
        """
        Save usage history to JSON file thread-safely
        Args:
            path: File path where to save the JSON data
        """
        with self.records_lock:
            records_data = [record.to_dict() for record in self.call_records]
        # Create directory if it doesn't exist
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to JSON
        with self.io_lock:
            with open(file_path, 'w') as f:
                json.dump(records_data, f, indent=2)

    def load_usage_history(self, path: str):
        """
        Load usage history from JSON file thread-safely
        Args:
            path: File path where the JSON data is stored
            """
        if not Path(path).exists():
            return
        with self.io_lock:
            with open(path, 'r') as f:
                records_data = json.load(f)
        self.reset_usage_history()
        self.add_records([UsageMetadata.from_dict(record) for record in records_data])


class UsageCallbackHandler(BaseCallbackHandler):
    """A callback handler to track usage of LLM calls within MonoMorph."""
    # (context, timestamp, response_id, openrouter_id, metadata)
    # usage_history: list[UsageMetadata] = []

    def __init__(self, context: CallbackContext):
        """Initialize the UsageCallbackHandler with a context."""
        super().__init__()
        self.current_context = context
        self.tracker = GlobalUsageTracker()
        self.logger = logging.getLogger("monomorph")

    def on_llm_end(self, response: dict, *args, **kwargs: dict) -> None:
        """Track the response metadata."""
        # self.logger.debug("LLM call ended, tracking usage.")]
        response_id = str(kwargs.get("run_id"))
        try:
            if isinstance(response, LLMResult):
                metadata = response.llm_output
            elif isinstance(response, dict):
                metadata = response.get("response_metadata", {})
            else:
                self.logger.warning("Unexpected response type, cannot track usage.")
                return
            if metadata:
                openrouter_id = metadata.get("id", None)
                now = datetime.datetime.now().isoformat()
                usage = UsageMetadata(
                    timestamp=now,
                    response_id=response_id,
                    openrouter_id=openrouter_id,
                    metadata=metadata,
                    context=self.current_context
                )
                self.tracker.add_record(usage)
            else:
                self.logger.warning("No response metadata found in the LLM response.")
        except Exception as e:
            self.logger.error(f"Error processing LLM response: {e}")
            return

