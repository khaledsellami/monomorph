import importlib.resources
from typing import Optional

from .prompt import Jinja2Prompt
from monomorph.llm.models import LANGUAGE_MAP, Class
from ...._metadata import PACKAGE_NAME


class LangChainIDgRPCServerPrompt(Jinja2Prompt):
    BASENAME = "using_id_grpc_server"
    VERSION = "0.1.3"
    SYSTEM_VERSION = "0.0.1"
    PROMPT_TEMPLATE = f"using_id_grpc_server_template-{VERSION}.md"
    SYSTEM_PROMPT_TEMPLATE = f"system-using_id_grpc_server_template-{SYSTEM_VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.using_id_grpc_server'

    def __init__(self, proto_prompt: str, proto_response: str, class_id_registry_full_name: str, server_template: Class,
                 mapper_class: Class | None = None, id_class: Class | None = None, id_only: bool = True,
                 references_mapping: Optional[dict] = None, current_microservice: str = "",
                 language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.proto_prompt = proto_prompt
        self.proto_response = proto_response
        self.mapper_class = mapper_class
        self.server_template = server_template
        self.id_class = id_class
        self.id_only = id_only
        self.current_microservice = current_microservice
        self.references_mapping = references_mapping
        self.class_id_registry_full_name = class_id_registry_full_name
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)
        self.system_template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.SYSTEM_PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        kwargs = dict(
            proto_prompt=self.proto_prompt,
            proto_response=self.proto_response,
            language=self.language,
            class_id_registry_full_name=self.class_id_registry_full_name,
            id_class=self.id_class,
            mapper_class=self.mapper_class,
            server_template=self.server_template,
            id_only=self.id_only,
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
