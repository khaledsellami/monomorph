import logging

from langchain.prompts import PromptTemplate

from jinja2 import Environment, BaseLoader


class LangChainPrompt:
    BASENAME = "default"

    def __init__(self):
        self.logger = logging.getLogger("monomorph")

    def generate_prompt(self) -> PromptTemplate:
        raise NotImplementedError("generate_prompt not implemented yet")

    def get_prompt_type(self) -> str:
        return "default"

    def generate_system_prompt(self) -> str:
        """
        Returns the system prompt.
        """
        self.logger.warning("The system prompt is not defined in the base class.")
        return ""

    @classmethod
    def get_prompt_basename(cls) -> str:
        return cls.BASENAME


class Jinja2Prompt(LangChainPrompt):
    """Jinja2 prompt template."""

    def __init__(self):
        super().__init__()
        self.env = Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template_path = None
        self.system_template_path = None

    def render_prompt(self, **kwargs) -> str:
        """Generate the prompt using Jinja2."""
        if not self.template_path:
            raise ValueError("Template is not set. Please set the template before generating the prompt.")
        template_txt = self.template_path.read_text(encoding="utf-8")
        template = self.env.from_string(template_txt)
        return template.render(**kwargs)

    def render_system_prompt(self, **kwargs) -> str:
        """
        Returns the system prompt.
        """
        if not self.system_template_path:
            return super().generate_system_prompt()
        system_template_txt = self.system_template_path.read_text(encoding="utf-8")
        system_template = self.env.from_string(system_template_txt)
        return system_template.render(**kwargs)
