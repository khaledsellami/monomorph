import importlib.resources

from langchain.prompts import PromptTemplate

from .prompt import LangChainPrompt
from ...._metadata import PACKAGE_NAME


class LangChainProtoParsingPrompt(LangChainPrompt):
    BASENAME = "proto_parsing"
    VERSION = "0.0.3"
    PROMPT_TEMPLATE = f"proto_parsing_template-{VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.proto_parsing'

    def __init__(self, response_txt: str, **kwargs):
        super().__init__()
        self.response_txt = response_txt
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        template = self.template_path.read_text(encoding="utf-8")
        prompt = PromptTemplate.from_template(template, template_format="jinja2")
        kwargs = dict(
            response=self.response_txt,
        )
        return prompt.format(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}-{self.VERSION}"
        return prompt_type

