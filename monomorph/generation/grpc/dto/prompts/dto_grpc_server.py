import importlib.resources
from typing import Optional

from .....llm.prompt import Jinja2Prompt
from .....llm.models import LANGUAGE_MAP, Class
from ....._metadata import PACKAGE_NAME


class LangChainDTOgRPCServerPrompt(Jinja2Prompt):
    BASENAME = "using_dto_grpc_server"
    VERSION = "0.0.3"
    SYSTEM_VERSION = "0.0.1"
    PROMPT_TEMPLATE = f"using_dto_grpc_server_template-{VERSION}.md"
    SYSTEM_PROMPT_TEMPLATE = f"system-using_dto_grpc_server_template-{SYSTEM_VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.using_dto_grpc_server'

    def __init__(self, proto_prompt: str, proto_response: str, server_template: Class, mapper_class: Class,
                 id_mapper_class: Class | None = None, references_mapping: Optional[dict] = None,
                 current_microservice: str = "", language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.proto_prompt = proto_prompt
        self.proto_response = proto_response
        self.mapper_class = mapper_class
        self.server_template = server_template
        self.current_microservice = current_microservice
        self.references_mapping = references_mapping
        self.id_mapper_class = id_mapper_class
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)
        self.system_template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.SYSTEM_PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        kwargs = dict(
            proto_prompt=self.proto_prompt,
            proto_response=self.proto_response,
            language=self.language,
            mapper_class=self.mapper_class,
            server_template=self.server_template,
            references_mapping=self.references_mapping,
            current_microservice=self.current_microservice,
            id_mapper_class=self.id_mapper_class,
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
