import importlib.resources
from typing import Optional

from .....llm.prompt import Jinja2Prompt
from .....llm.models import LANGUAGE_MAP, Class
from ....._metadata import PACKAGE_NAME


class LangChainDTOgRPCClientPrompt(Jinja2Prompt):
    BASENAME = "using_dto_grpc_client"
    VERSION = "0.0.4"
    SYSTEM_VERSION = "0.0.1"
    PROMPT_TEMPLATE = f"{BASENAME}_template-{VERSION}.md"
    SYSTEM_PROMPT_TEMPLATE = f"system-{BASENAME}_template-{SYSTEM_VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.{BASENAME}'

    def __init__(self, proto_prompt: str, proto_response: str, client_template: Class,  dto_name: str,
                 id_mapper_class: Class | None = None, references_mapping: Optional[dict] = None,
                 current_microservice: str = "", language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.proto_prompt = proto_prompt
        self.proto_response = proto_response
        self.id_mapper_class = id_mapper_class
        self.dto_name = dto_name
        self.client_template = client_template
        self.references_mapping = references_mapping
        self.current_microservice = current_microservice
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)
        self.system_template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.SYSTEM_PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        kwargs = dict(
            proto_prompt=self.proto_prompt,
            proto_response=self.proto_response,
            language=self.language,
            client_template=self.client_template,
            dto_name=self.dto_name,
            id_mapper_class=self.id_mapper_class,
            references_mapping=self.references_mapping,
            current_microservice=self.current_microservice,
        )
        return self.render_prompt(**kwargs)

    def generate_system_prompt(self) -> str:
        kwargs = dict(
            language=self.language,
        )
        return self.render_system_prompt(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}-{self.VERSION}"
        return prompt_type
