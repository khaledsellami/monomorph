from typing import Optional

from ..llm.tracking.usage import UsageCallbackHandler


class ValidationCallBackHandler:
    def __init__(self):
        self.main_callback: Optional[UsageCallbackHandler] = None
        self.parsing_callback: Optional[UsageCallbackHandler] = None
        self.expert_callback: Optional[UsageCallbackHandler] = None
        self.summary_callback: Optional[UsageCallbackHandler] = None

    def get_main_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the main callback handler if it exists.
        """
        return [self.main_callback] if self.main_callback else None

    def get_parsing_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the parsing callback handler if it exists.
        """
        return [self.parsing_callback] if self.parsing_callback else None

    def get_expert_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the expert callback handler if it exists.
        """
        return [self.expert_callback] if self.expert_callback else None

    def get_summary_callback(self) -> Optional[list[UsageCallbackHandler]]:
        """
        Returns the summary callback handler if it exists.
        """
        return [self.summary_callback] if self.summary_callback else None
