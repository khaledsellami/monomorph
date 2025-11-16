import importlib.resources

from ...llm.prompt import Jinja2Prompt
from ...llm.models import LANGUAGE_MAP
from .models import CompilationAnalysisReport


class CompilationLogAnalysisPrompt(Jinja2Prompt):
    """
    Prompt for analyzing compilation logs.
    """
    BASENAME = "compilation_correcting"
    VERSION = "0.0.2"

    def __init__(self, logs: str, package_name: str, current_microservice: str = "ms1", language: str = "java",
                 **kwargs):
        super().__init__()
        self.logs = logs
        self.language = LANGUAGE_MAP[language]
        self.current_microservice = current_microservice
        self.package_name = package_name
        self.output_type_name: str = CompilationAnalysisReport.__class__.__name__
        self.USER_PROMPT_TEMPLATE = """
        # Compilation Logs
```text
{compilation_logs}
```
        """

    def generate_prompt(self) -> str:
        return self.USER_PROMPT_TEMPLATE.format(compilation_logs=self.logs)

    def generate_system_prompt(self) -> str:
        kwargs = dict(
            language=self.language,
            current_microservice=self.current_microservice,
            output_type_name=self.output_type_name,
            package_name=self.package_name,
        )
        return self.render_prompt(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}-{self.VERSION}"
        return prompt_type
