import os
import json
import subprocess
from pathlib import Path
from importlib import resources

from .model import AppModel
from .json import JsonModel


class LocalAnalysis:
    ANALYSIS_JAR_PATH: Path = resources.files("monomorph.resources").joinpath("decomp-analysis-refact.jar")

    def __init__(self, app_name: str, code_path: str, analysis_path: str, parsing_path: str = None,
                 save_parsed: bool = False, create_subdirs: bool = True):
        self.app_name = app_name
        self.code_path = code_path
        self.analysis_path = analysis_path
        self.parsing_path = parsing_path
        self.save_parsed = save_parsed
        self.true_analysis_path = os.path.join(self.analysis_path, self.app_name) if create_subdirs else self.analysis_path
        self.java_executable = os.environ.get("JAVA_EXEC_PATH", "java")
        # self._excluded_fields = ["span", "GenericInFieldTypes", "VariableTypes", "GenericInReferencedTypes",
        #                          "annotations", "modifiers"]
        if not self.ANALYSIS_JAR_PATH.exists():
            raise FileNotFoundError(f"Analysis jar file not found at {self.ANALYSIS_JAR_PATH}")

    def data_exists(self) -> bool:
        return all([os.path.exists(os.path.join(self.true_analysis_path, f"{filename}.json")) for filename in
                    ["typeData", "methodData", "apiTypesData", "dtoData"]])

    def analyze(self) -> int:
        if not self.data_exists():
            command = [self.java_executable, "-jar", str(self.ANALYSIS_JAR_PATH), "analyze", self.app_name, "-p", self.code_path, "-o",
                       self.analysis_path]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = process.communicate()
            return process.returncode
        return -1

    # def _filter_fields(self, type_data: dict, method_data: dict) -> tuple[dict, dict]:
    #     type_data["classes"] = [{k: v for k, v in value.items() if k not in self._excluded_fields} for value in
    #                             type_data["classes"]]
    #     method_data["methods"] = [{k: v for k, v in value.items() if k not in self._excluded_fields} for value in
    #                               method_data["methods"]]
    #     for method in method_data["methods"]:
    #         for key in ["localInvocations", "invocations"]:
    #             for invocation in method[key]:
    #                 if "span" in invocation:
    #                     invocation.pop("span")
    #     for class_ in type_data["classes"]:
    #         for invocation in class_["fieldCalls"]:
    #             if "span" in invocation:
    #                 invocation.pop("span")
    #     return type_data, method_data

    def load(self) -> AppModel:
        if not self.data_exists():
            self.analyze()
        with open(os.path.join(self.true_analysis_path, "typeData.json"), "r") as file:
            type_data = json.load(file)
        with open(os.path.join(self.true_analysis_path, "methodData.json"), "r") as file:
            method_data = json.load(file)
        with open(os.path.join(self.true_analysis_path, "apiTypesData.json"), "r") as file:
            api_types_data = json.load(file)
        with open(os.path.join(self.true_analysis_path, "dtoData.json"), "r") as file:
            dto_data = json.load(file)
        # if self._excluded_fields:
        #     type_data, method_data = self._filter_fields(type_data, method_data)
        return JsonModel(self.app_name, type_data, method_data, api_types_data, dto_data, self.save_parsed,
                         self.parsing_path)
