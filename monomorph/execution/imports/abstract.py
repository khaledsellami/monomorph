import abc
import logging
import os.path
from typing import Optional, Callable


class AbstractImportParserClient(abc.ABC):
    """
    Abstract base class defining the interface for interacting with
    a Java code import parsing service (CLI or gRPC).
    """

    def __init__(self, directory_path: str):
        """
        Initializes the client.

        Args:
            directory_path: Path to the root directory of the Java project/sources.
        """
        self.directory_path = directory_path
        self.logger = logging.getLogger("monomorph")
        self.logger.debug("Initializing %s", self.__class__.__name__)
        if not (self.directory_path and os.path.exists(self.directory_path)):
            raise FileNotFoundError(f"Directory path does not exist: {self.directory_path}")

    @abc.abstractmethod
    def refactor_single(
        self,
        target_qualified_name: str,
        old_qualified_name: str,
        new_qualified_name: str
    ) -> str:
        """
        Refactors a single old qualified name to a new name in a target class.

        Args:
            target_qualified_name: FQN of the target class.
            old_qualified_name: Old FQN to replace.
            new_qualified_name: New FQN to use.

        Returns:
            The modified source code of the target class.
        """
        raise NotImplementedError("refactor_single() must be implemented in subclasses.")

    @abc.abstractmethod
    def refactor_batch_target(
        self,
        target_qualified_name: str,
        replacements: dict[str, str] | list[tuple[str, str]]
    ) -> Optional[str]:
        """
        Refactors multiple old qualified names within a single target class.

        Args:
            target_qualified_name: FQN of the target class.
            replacements: A dictionary {old_name: new_name} or a list of tuples
                          [(old_name1, new_name1), ...] specifying the changes.

        Returns:
            The modified source code of the target class.
        """
        raise NotImplementedError("refactor_batch_target() must be implemented in subclasses.")

    @abc.abstractmethod
    def refactor_batch_all(
        self,
        replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]]
    ) -> dict[str, Optional[str]]:
        """
        Refactors multiple names across multiple target classes, processing the
        entire directory context once.

        Args:
            replacements_per_target: A dictionary where keys are target class FQNs,
                                     and values are dictionaries {old_name: new_name}
                                     specifying replacements for that target.

        Returns:
            A dictionary where keys are the target class FQNs and values are the
            modified source code strings, or None if processing failed for that specific target.
        """
        raise NotImplementedError("refactor_batch_all() must be implemented in subclasses.")

    @abc.abstractmethod
    def refactor_batch_all_stream(
            self,
            replacements_per_target: dict[str, dict[str, str] | list[tuple[str, str]]],
            callback: Callable[[str, Optional[str], Optional[str]], None]
    ) -> None:
        """
        Refactors multiple names across multiple target classes, processing the
        entire directory context once.

        Args:
            replacements_per_target: A dictionary where keys are target class FQNs,
                                     and values are dictionaries {old_name: new_name}
                                     specifying replacements for that target.
            callback: A callable function that will be called with the modified source code

        Returns:
            A dictionary where keys are the target class FQNs and values are the
            modified source code strings, or None if processing failed for that specific target.
        """
        raise NotImplementedError("refactor_batch_all_stream() must be implemented in subclasses.")
