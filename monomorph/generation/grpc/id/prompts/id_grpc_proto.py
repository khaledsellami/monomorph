from typing import Optional

from .....llm.prompt import Jinja2Prompt
from .....llm.models import LANGUAGE_MAP, Class


class LangChainIDgRPCProtoPrompt(Jinja2Prompt):
    BASENAME = "using_id_grpc_proto"
    VERSION = "0.1.4"
    SYSTEM_VERSION = "0.0.1"

    def __init__(self, class_: Class, methods: list[str], shared_proto: Class, proto_template: Class,
                 id_only: bool = True, references_mapping: Optional[dict] = None, language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.class_ = class_
        self.methods = methods
        self.shared_proto = shared_proto
        self.proto_template = proto_template
        self.id_only = id_only
        self.references_mapping = references_mapping

    def generate_prompt(self) -> str:
        kwargs = dict(
            language=self.language,
            class_=self.class_,
            methods=self.methods,
            shared_proto_package=".".join(self.shared_proto.full_name.split(".")[:-1]),
            proto_template=self.proto_template,
            id_only=self.id_only,
            references_mapping=self.references_mapping,
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
