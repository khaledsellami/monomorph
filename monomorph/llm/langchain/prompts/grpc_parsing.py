import importlib.resources

from langchain.prompts import PromptTemplate

from .prompt import LangChainPrompt
from ...._metadata import PACKAGE_NAME


class LangChainGrpcParsingPrompt(LangChainPrompt):
    BASENAME = "grpc_parsing"
    VERSION = "0.0.3"
    PROMPT_TEMPLATE = f"grpc_parsing_template-{VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.grpc_parsing'

    def __init__(self, response_txt: str, mode: str = "server", **kwargs):
        super().__init__()
        self.response_txt = response_txt
        self.mode = mode
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        template = self.template_path.read_text(encoding="utf-8")
        prompt = PromptTemplate.from_template(template, template_format="jinja2")
        kwargs = dict(
            response=self.response_txt,
        )
        return prompt.format(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}_{self.mode}-{self.VERSION}"
        return prompt_type

