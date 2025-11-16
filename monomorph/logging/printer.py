import logging
import sys
from typing import Optional, Literal

import colorama


class FilteredLogger:
    """logger class to enable the same interface for logging and ConsolePrinter."""
    TRUNCATE_LENGTH = 100

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.kwargs_to_ignore = ["msg_type_suffix", "highlight", "end", "flush"]

    def log(self, level: int, message: str, short_message: Optional[str] = None, stacklevel: int = 2, *args, **kwargs):
        msg_type = kwargs.pop("msg_type", "default")
        msg_type_suffix = kwargs.pop("msg_type_suffix", "")
        message = short_message if short_message else message[:self.TRUNCATE_LENGTH]
        message = f"[{msg_type}{msg_type_suffix}]: {message}"
        for key in self.kwargs_to_ignore:
            if key in kwargs:
                kwargs.pop(key)
        if self.logger.isEnabledFor(level):
            self.logger.log(level, message, stacklevel=stacklevel, *args, **kwargs)

    def info(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.log(logging.INFO, message, stacklevel=stacklevel+1, *args, **kwargs)

    def debug(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.log(logging.DEBUG, message, stacklevel=stacklevel+1, *args, **kwargs)

    def warning(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.log(logging.WARNING, message, stacklevel=stacklevel+1, *args, **kwargs)

    def error(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.log(logging.ERROR, message, stacklevel=stacklevel+1, *args, **kwargs)


class DummyColor:
    def __getattr__(self, name):
        return ""


def update_color_map(fore) -> dict:
    return {
        "default": fore.WHITE,
        "system": fore.YELLOW,
        "user": fore.LIGHTGREEN_EX,
        "ai": fore.BLUE,
        "ai_toolcall": fore.CYAN,
        "tool": fore.MAGENTA,
        "error": fore.RED,
        "node": fore.WHITE,
        "decision": fore.GREEN,
    }


def update_highlight(style) -> dict:
    return {
        True: style.BRIGHT,
        False: "",
    }


class ConsolePrinter:
    """
    Class for printing messages to the console in color based in the message type. Designed to debug LangGraph nodes.
    """
    registered_printers: dict = {}
    colors: bool = True
    verbosity: int = 1
    Fore = DummyColor()
    Style = DummyColor()
    Back = DummyColor()
    color_map = update_color_map(Fore)
    highlight = update_highlight(Style)
    LOGGING_MODE = "logger"

    def __init__(self, name: str = "monomorph"):
        self.name = name
        self.logger = FilteredLogger(name)

    def print(self, message: str, msg_type: str = "default", highlight: bool = False, end: str = "\n",
              msg_type_suffix: str = "", flush: bool = False, short_message: Optional[str] = None,
              stacklevel: int = 2, *args, **kwargs):
        if self.LOGGING_MODE == "logger":
            if flush:
                return  # ignore streaming output in logger mode
            log_level = kwargs.pop("level", logging.DEBUG)
            self.logger.log(log_level, message, msg_type=msg_type, msg_type_suffix=msg_type_suffix,
                            highlight=highlight, end=end, flush=flush, short_message=short_message,
                            stacklevel=stacklevel+1, *args, **kwargs)
            return
        if self.verbosity == 0:
            return
        if end:
            print(f"{self.color_map.get(msg_type, self.Fore.WHITE)}{self.highlight[highlight]}[{msg_type}{msg_type_suffix}]: "
                  f"{message}"
                  f"{self.Style.RESET_ALL}", end=end)
        else:
            print(f"{self.color_map.get(msg_type, self.Fore.WHITE)}{self.highlight[highlight]}"
                  f"{message}"
                  f"{self.Style.RESET_ALL}", end=end)
        if flush:
            sys.stdout.flush()

    @classmethod
    def set_verbosity(cls, verbosity: int):
        """
        Sets the verbosity level.
        """
        cls.verbosity = verbosity

    @classmethod
    def set_colors(cls, colors: bool):
        cls.colors = colors
        cls.Fore = colorama.Fore if colors else DummyColor()
        cls.Style = colorama.Style if colors else DummyColor()
        cls.Back = colorama.Back if colors else DummyColor()
        cls.color_map = update_color_map(cls.Fore)
        cls.highlight = update_highlight(cls.Style)

    @classmethod
    def create_printer(cls, name: str):
        """
        Creates a printer by name.
        """
        printer = ConsolePrinter(name)
        cls.registered_printers[name] = printer
        return printer

    @classmethod
    def get_printer(cls, name: str):
        """
        Gets or creates a printer by name.
        """
        if name not in cls.registered_printers:
            return cls.create_printer(name)
        else:
            return cls.registered_printers[name]

    def info(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.print(message, level=logging.INFO, stacklevel=stacklevel+1, *args, **kwargs)

    def debug(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.print(message, level=logging.DEBUG, stacklevel=stacklevel+1, *args, **kwargs)

    def warning(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.print(message, level=logging.WARNING, stacklevel=stacklevel+1, *args, **kwargs)

    def error(self, message: str, stacklevel: int = 2, *args, **kwargs):
        self.print(message, level=logging.ERROR, stacklevel=stacklevel+1, *args, **kwargs)

    @classmethod
    def set_logging_mode(cls, mode: Literal["printer", "logger"] = "logger"):
        """
        Sets the logging mode to either 'printer' or 'logger'. Default is 'logger'.
        """
        cls.LOGGING_MODE = mode
