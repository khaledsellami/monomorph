import importlib.resources

from ..._metadata import PACKAGE_NAME
from ...llm.langchain.prompts.prompt import Jinja2Prompt
from monomorph.llm.models import LANGUAGE_MAP


class CompilationCorrectionPrompt(Jinja2Prompt):
    """
    Prompt for correcting compilation logs.
    """
    BASENAME = "compilation_correcting_impl"
    VERSION = "0.0.2"
    PROMPT_TEMPLATE = f"compilation_correcting_impl_template-{VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.compilation_correcting_impl'

    def __init__(self, logs: str, package_name: str, current_microservice: str = "ms1",
                 language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.current_microservice = current_microservice
        self.package_name = package_name
        self.logs = logs
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        # user_prompt = f"""
        # # Error Root Cause
        # ## Error Summary
        # {self.root_cause.error_summary}
        # ## Error Details
        # {self.root_cause.detailed_explanation}
        # ## Affected files
        # {'\n- '.join([l[0] + " : '" + l[1] + "'" for l in self.root_cause.affected_files])}
        # ## Solution Plan
        # {'\n- '.join([str(i) + ") " + s for i, s in enumerate(self.root_cause.solution_plan)])}
        # """
        user_prompt = f"""
# Relevant Error Compilation Logs
{self.logs}
"""
        return user_prompt

    def generate_system_prompt(self) -> str:
        kwargs = dict(
            language=self.language,
            current_microservice=self.current_microservice,
            package_name=self.package_name,
        )
        return self.render_prompt(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}-{self.VERSION}"
        return prompt_type


class ExpertPrompt(Jinja2Prompt):
    """
    Prompt for expert in investigating issues in the codebase and providing solutions.
    """
    BASENAME = "compilation_correcting_expert"
    VERSION = "0.0.1"
    PROMPT_TEMPLATE = f"{BASENAME}_template-{VERSION}.md"
    TEMPLATES_PATH = f'{PACKAGE_NAME}.resources.prompts.templates.{BASENAME}'

    def __init__(self, package_name: str, current_microservice: str = "ms1",
                 language: str = "java", **kwargs):
        super().__init__()
        self.language = LANGUAGE_MAP[language]
        self.current_microservice = current_microservice
        self.package_name = package_name
        self.template_path = importlib.resources.files(self.TEMPLATES_PATH).joinpath(self.PROMPT_TEMPLATE)

    def generate_prompt(self) -> str:
        return ""

    def generate_system_prompt(self) -> str:
        kwargs = dict(
            language=self.language,
            current_microservice=self.current_microservice,
            package_name=self.package_name,
        )
        return self.render_prompt(**kwargs)

    def get_prompt_type(self) -> str:
        prompt_type = f"{self.BASENAME}-{self.VERSION}"
        return prompt_type
