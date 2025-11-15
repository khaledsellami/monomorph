import logging
import os
import json
from typing import Optional

from pydantic import BaseModel

from .langchain.generate import LangChainModel
from .langchain.output import from_solution_to_md
from .utils import get_model
from .._metadata import PACKAGE_NAME


class LLMClient:
    """Base class for LLM clients"""
    def __init__(self, name: str, save_output: bool = True, block_paid_api: bool = True,
                 **kwargs):
        self.name = name
        self.full_name = get_model(name, block_paid_api)
        self.save_output = save_output
        self.logger = logging.getLogger(PACKAGE_NAME)
        self.kwargs = kwargs

    def get_model(self) -> str:
        return self.full_name

    def refactor(self, prompt: str, suffix: str | None = None) -> tuple[str, any]:
        raise NotImplementedError()


class LangChainLLMClient(LLMClient):
    def __init__(self, name: str, save_output: bool = True, block_paid_api: bool = True,
                 with_structured_output: bool = False, json_mode: bool = False,
                 strict: bool = False, output_type: type[BaseModel] | None = None, timeout: Optional[int] = None,
                 retries: Optional[int] = None, **kwargs):
        super().__init__(name, save_output, block_paid_api, **kwargs)
        self.with_structured_output = with_structured_output
        self.json_mode = json_mode
        self.strict = strict
        self.output_type = output_type
        self.timeout = timeout
        self.retries = retries

    def refactor(self, prompt: str, suffix: str | None = None) -> tuple[str | BaseModel | dict, any]:
        api_model = LangChainModel(self.name, self.full_name, prompt, json_mode=self.json_mode,
                                   with_structured_output=self.with_structured_output, output_type=self.output_type,
                                   timeout=self.timeout, retries=self.retries, **self.kwargs)
        # output_path = os.path.join(api_model.output_path, suffix) if suffix else None
        output_path = self.get_save_path(suffix, api_model)
        try:
            outputs = api_model.refactor()
            if self.with_structured_output and self.strict:
                if self.json_mode and not isinstance(outputs[0], dict):
                    raise ValueError("The model did not return a structured output")
                if not self.json_mode and not isinstance(outputs[0], BaseModel):
                    raise ValueError("The model did not return a structured output")
            if outputs[0] is not None and self.save_output:
                structured_result = None
                if self.with_structured_output:
                    if isinstance(outputs[0], BaseModel):
                        output_str = from_solution_to_md(outputs[0])
                        structured_result = outputs[0]
                    elif self.json_mode:
                        output_str = json.dumps(outputs[0], indent=2)
                        structured_result = outputs[0]
                    else:
                        output_str = outputs[0]
                else:
                    output_str = outputs[0]
                api_model.save_output(output_str, output_path, structured_result)
            return outputs
        except Exception as e:
            # self.logger.error(f"Error while refactoring: {e}")
            output_str = "FAILED TO GENERATE CORRECT OUTPUT\n"
            output_str += "Stack trace:\n"
            output_str += str(e)
            api_model.save_output(output_str, output_path)
            raise e

    def get_save_path(self, suffix: str | None = None, api_model: LangChainModel | None = None) -> str:
        if api_model is None:
            api_model = LangChainModel(self.name, self.full_name, "", json_mode=self.json_mode,
                                       with_structured_output=self.with_structured_output, output_type=self.output_type,
                                       **self.kwargs)
        return os.path.join(api_model.output_path, suffix) if suffix else None
