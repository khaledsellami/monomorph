import json
import os
import logging
from typing import Optional

import httpx
from openai import APITimeoutError, APIConnectionError
from langchain_openai import ChatOpenAI
import dotenv
from pydantic import BaseModel

from ..._metadata import PACKAGE_NAME, APP_NAME
from .output import RPCSolution


class LangChainModel:
    OPENROUTER_API = "https://openrouter.ai/api/v1"

    def __init__(self, name: str, full_name: str, prompt: str, with_structured_output: bool = False,
                 json_mode: bool = False, output_type: type[BaseModel] | None = None, llm_response_path: str = None,
                 timeout: Optional[int] = None, retries: int = None, **kwargs):
        if with_structured_output and output_type is None:
            raise ValueError("output_type must be provided when with_structured_output is True")
        self.name = name
        self.full_name = full_name
        self.prompt = prompt
        self.with_structured_output = with_structured_output
        self.json_mode = json_mode
        self.output_type = output_type
        self.timeout = timeout
        self.retries = retries
        self.output_path = llm_response_path if llm_response_path else os.path.join(os.getcwd(), "llm_data", "responses")
        self.logger = logging.getLogger(PACKAGE_NAME)
        dotenv.load_dotenv()
        self.llm_client = self.init_llm()

    def init_llm(self) -> ChatOpenAI:
        OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        if OPENROUTER_API_KEY is None:
            self.logger.error("API key not found!")
            raise ValueError("API key not found!")
        self.logger.info(f"Refactoring using {self.name} model")
        extra_body = {
            "provider": {
                "require_parameters": True if self.with_structured_output else False,
                "data_collection": "deny"
            },
        }
        llm_client = ChatOpenAI(
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=self.OPENROUTER_API,
            model_name=self.full_name,
            default_headers={
                    "X-Title": APP_NAME,
                },
            model_kwargs={
                "extra_headers": {
                    "X-Title": APP_NAME,
                },
                # "extra_body": extra_body
            },
            extra_body=extra_body,
            request_timeout=httpx.Timeout(self.timeout) if self.timeout else None,
        )
        if self.with_structured_output:
            if self.json_mode:
                llm_client = llm_client.with_structured_output(self.output_type.model_json_schema(), include_raw=True)
            else:
                llm_client = llm_client.with_structured_output(self.output_type, include_raw=True)
        return llm_client

    def refactor(self) -> tuple[str | BaseModel, any]:
        if self.retries:
            errors = (httpx.TimeoutException, httpx.ConnectTimeout, APITimeoutError, APIConnectionError)
            response = self.llm_client.with_retry(retry_if_exception_type=errors,
                                                  stop_after_attempt=self.retries).invoke(self.prompt)
        else:
            response = self.llm_client.invoke(self.prompt)
        if self.with_structured_output:
            if "parsed" in response or response["parsing_error"] is not None:
                self.logger.debug("response was parsed correctly")
                return response["parsed"], response
            self.logger.warning("response was not parsed correctly")
            return response["raw"], response
        else:
            try:
                text = response.content
                if text:
                    return text, response
            except Exception:
                return "", response

    def save_output(self, output: str, output_path: str|None = None, structured_result: BaseModel | dict | None = None):
        output_path = output_path or self.output_path
        os.makedirs(output_path, exist_ok=True)
        result = """\n# Prompt\n{prompt}\n\n# Response\n{response}\n""".format(prompt=self.prompt, response=output)
        self.logger.debug(f"Saving output to {output_path}")
        with open(os.path.join(output_path, f"{self.full_name.replace('/', '--')}.md"), "w") as f:
            f.write(result)
        if structured_result:
            self.logger.debug(f"Saving structured output to {output_path}")
            if isinstance(structured_result, BaseModel):
                structured_result_json = structured_result.model_dump(mode="json")
            else:
                structured_result_json = structured_result
            with open(os.path.join(output_path, f"{self.full_name.replace('/', '--')}.json"), "w") as f:
                json.dump(structured_result_json, f, indent=2)


class ModelPostProcessor:
    # TODO add a method that checks if the source code has incorrect raw encoding (e.g. \\n instead of \n)
    @classmethod
    def post_process_response(cls, rpc_solution: RPCSolution) -> RPCSolution:
        for new_class in rpc_solution.new_classes:
            new_class.source_code = cls.validate_source_code(new_class.source_code)
        return rpc_solution

    @classmethod
    def validate_source_code(cls, source_code) -> str:
        # Remove ```language or ``` from source code if they exist
        if source_code.startswith("```"):
            # Find the first newline character after the initial ```
            first_newline = source_code.find("\n")
            if first_newline != -1:
                # Remove the initial ``` and the language identifier
                source_code = source_code[first_newline + 1:]
            # Remove the trailing ```
            source_code = source_code.rstrip("`")
        return source_code

