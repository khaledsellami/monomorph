import importlib.resources
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
    VERSION = "0.0.1"
    SYSTEM_VERSION = "0.0.1"

    def __init__(self):
        super().__init__()
        self.env = Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.PROMPT_TEMPLATE = f"{self.BASENAME}_template-{self.VERSION}.md"
        self.SYSTEM_PROMPT_TEMPLATE = f"system-{self.BASENAME}_template-{self.SYSTEM_VERSION}.md"
        self.TEMPLATES_PATH = f'monomorph.resources.prompts.templates.{self.BASENAME}'
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)
        self.system_template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.SYSTEM_PROMPT_TEMPLATE)

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
