import os.path


import numpy as np
import pandas as pd
from decparsing import DataHandler
from decparsing.analysis.analysisRuntimeClient import AnalysisRuntimeClient

from .model import AppModel
from ..utils import silence_all


class JsonModel(AppModel):
    def __init__(self, app_name: str, type_data: dict, method_data: dict, api_data: dict = None, dto_data: dict = None,
                 save_cache: bool = False, cache_path: str = None):
        super().__init__(app_name)
        self.type_data = self.map_data(type_data, "classes")
        self.method_data = self.map_data(method_data, "methods")
        self.api_data = self.map_data(api_data, "apiTypes") if api_data else {}
        self.dto_data = self.map_data(dto_data, "dtos") if dto_data else {}
        self.save_cache = save_cache
        self.cache_path = cache_path if cache_path else os.path.join(os.getcwd(), "data", "parsing-cache")
        self._excluded_fields = ["span", "GenericInFieldTypes", "VariableTypes", "GenericInReferencedTypes",
                                 "annotations", "modifiers"]

    def _filter_fields(self, type_data: dict, method_data: dict) -> tuple[dict, dict]:
        type_data = {key: {k: v for k, v in value.items() if k not in self._excluded_fields}
                     for key, value in type_data.items()}
        method_data = {key: {k: v for k, v in value.items() if k not in self._excluded_fields}
                       for key, value in method_data.items()}
        for m, method in method_data.items():
            for key in ["localInvocations", "invocations"]:
                for invocation in method[key]:
                    if "span" in invocation:
                        invocation.pop("span")
        for c, class_ in type_data.items():
            for invocation in class_["fieldCalls"]:
                if "span" in invocation:
                    invocation.pop("span")
        return type_data, method_data

    @staticmethod
    def map_data(data: dict, datatype: str = "classes"):
        return {item["fullName"]: item for item in data[datatype]}

    def get_inheritance(self, class_name: str) -> list[str]:
        return self.type_data[class_name]["inheritedTypes"]

    def build_class_methods_matrix(self) -> pd.DataFrame:
        n_classes = len(self.type_data)
        n_methods = len(self.method_data)
        class_methods_matrix = np.zeros((n_classes, n_methods)).astype(bool)
        class_names = list(self.type_data.keys())
        method_names = list(self.method_data.keys())
        for i, method_name in enumerate(method_names):
            method_ = self.method_data[method_name]
            if method_["parentName"]:
                class_idx = class_names.index(method_["parentName"])
                class_methods_matrix[class_idx, i] = True
        class_methods_df = pd.DataFrame(class_methods_matrix, columns=method_names, index=class_names)
        return class_methods_df

    def get_inter_method_calls(self) -> pd.DataFrame:
        # initialize the analysis and parsing clients
        output_path = self.cache_path if self.save_cache else None
        if self._excluded_fields:
            type_data, method_data = self._filter_fields(self.type_data, self.method_data)
        else:
            type_data, method_data = self.type_data, self.method_data
        analysis = AnalysisRuntimeClient(self.app_name, list(type_data.values()), list(method_data.values()),
                                         [])
        parsing_client = DataHandler(analysis, output_path=output_path)
        # get the method interaction data
        with silence_all():
            _, call_data = parsing_client.get_data("calls", "method")  # M by M matrix
        return call_data

    def get_class_other_interactions(self) -> pd.DataFrame:
        # initialize the analysis and parsing clients
        output_path = self.cache_path if self.save_cache else None
        if self._excluded_fields:
            type_data, method_data = self._filter_fields(self.type_data, self.method_data)
        else:
            type_data, method_data = self.type_data, self.method_data
        analysis = AnalysisRuntimeClient(self.app_name, list(type_data.values()), list(method_data.values()),
                                         [])
        parsing_client = DataHandler(analysis, output_path=output_path)
        # get the class interaction data
        with silence_all():
            _, call_data = parsing_client.get_data("calls", "class") # C by C matrix
            _, all_interaction_data = parsing_client.get_data("interactions", "class")  # C by C matrix
            other_interaction_data = all_interaction_data - call_data
        return other_interaction_data

    def get_class_names(self) -> list[str]:
        return list(self.type_data.keys())

    def get_method_names(self) -> list[str]:
        return list(self.method_data.keys())

    def get_field_references(self) -> pd.DataFrame:
        class_names = self.get_class_names()
        field_references = np.zeros((len(class_names), len(class_names))).astype(bool)
        for i, class_name in enumerate(class_names):
            class_ = self.type_data[class_name]
            for ref_class_ in class_["fieldTypes"]:
                if ref_class_ in class_names:
                    j = class_names.index(ref_class_)
                    field_references[i, j] = True
        return pd.DataFrame(field_references, columns=class_names, index=class_names)

    def get_input_references(self) -> pd.DataFrame:
        class_names = self.get_class_names()
        input_references = np.zeros((len(class_names), len(class_names))).astype(bool)
        for i, class_name in enumerate(class_names):
            class_ = self.type_data[class_name]
            for ref_class_ in class_["parameterTypes"]:
                if ref_class_ in class_names:
                    j = class_names.index(ref_class_)
                    input_references[i, j] = True
        return pd.DataFrame(input_references, columns=class_names, index=class_names)

    def get_output_references(self) -> pd.DataFrame:
        class_names = self.get_class_names()
        output_references = np.zeros((len(class_names), len(class_names))).astype(bool)
        for i, class_name in enumerate(class_names):
            class_ = self.type_data[class_name]
            for ref_class_ in class_["returnTypes"]:
                if ref_class_ in class_names:
                    j = class_names.index(ref_class_)
                    output_references[i, j] = True
        return pd.DataFrame(output_references, columns=class_names, index=class_names)

    def get_variable_references(self) -> pd.DataFrame:
        # TODO: add a separate field for variable references
        return super().get_variable_references()

    def get_inputs(self, method_name: str) -> list[str]:
        return self.method_data[method_name]["parameterTypes"]

    def get_outputs(self, method_name: str) -> list[str]:
        return [self.method_data[method_name]["returnType"]]

    def get_inputs_as_ft(self, method_name: str) -> list[dict]:
        return self.api_data[method_name]["inputTypes"]

    def get_outputs_as_ft(self, method_name: str) -> list[dict]:
        return [self.api_data[method_name]["outputType"]]

    def get_method_source(self, method_name: str) -> str:
        return self.method_data[method_name]["content"]

    def get_method_parent(self, method_name: str) -> str:
        return self.method_data[method_name]["parentName"]

    def get_class_source(self, class_name: str) -> str:
        return self.type_data[class_name]["content"]

    def get_test_methods(self) -> list[str]:
        return [method_name for method_name, method_ in self.api_data.items() if "isTest" in method_]

    def get_local_methods(self) -> list[str]:
        return [method_name for method_name, method_ in self.method_data.items() if method_.get("isLocal", False)]

    def get_tags(self, method_name: str) -> set[str]:
        return self.method_data.get(method_name, {}).get("tags", set())

    def get_class_file_path(self, class_name: str) -> str:
        return self.type_data[class_name]["filePath"]

    def get_method_simple_name(self, method_name: str) -> str:
        return self.method_data[method_name]["simpleName"]

    def get_method_modifiers(self, method_name: str) -> list[str]:
        return self.method_data[method_name].get("modifiers", [])

    def get_method_return_type(self, method_name: str) -> str:
        return self.method_data[method_name]["returnType"]

    def get_method_parameter_types(self, method_name: str) -> list[str]:
        return self.method_data[method_name]["parameterTypes"]

    def _get_generic_from_api_type_details(self, api_details: dict) -> list[str]:
        generics = []
        # recursive call to get generics
        if api_details["genericTypes"]:
            for generic_details in api_details["genericTypes"]:
                generics += self.get_method_generics_in_return_type(generic_details)
        # get this generic type
        type_name = api_details["fullName"]
        # extract name from type name (e.g. List<String> -> List, String[] -> String)
        if type_name.endswith("[]"):
            type_name = type_name[:-2]
        elif type_name.endswith(">"):
            type_name = type_name.split("<")[0]
        generics.append(type_name)
        return generics

    def get_method_generics_in_return_type(self, method_name: str) -> list[str]:
        generics = []
        api_details = self.api_data.get(method_name, {})
        if api_details and api_details["outputType"] and api_details["outputType"]["genericTypes"]:
            for generic_details in api_details["outputType"]["genericTypes"]:
                generics = self._get_generic_from_api_type_details(generic_details)
        return generics

    def get_method_generics_in_parameters(self, method_name: str) -> list[str]:
        """
        Get the generics in the parameter types of a method. (e.g. List<String>)
        This is a list of lists of strings, where each list is a generic type.
        """
        generics = []
        api_details = self.api_data.get(method_name, {})
        if api_details:
            for input_type in api_details["inputTypes"]:
                if input_type["genericTypes"]:
                    for generic_details in input_type["genericTypes"]:
                        generics += self._get_generic_from_api_type_details(generic_details)
        return generics


    def get_class_annotations(self, class_name: str) -> list[str]:
        return self.type_data[class_name].get("annotations", [])

    def get_field_details(self, class_name: str) -> dict:
        return self.dto_data[class_name].get("fields", {})

    def get_input_references_in_methods(self) -> pd.DataFrame:
        """ Returns a Methods x Class matrix with the input references for each class. """
        class_names = self.get_class_names()
        method_names = self.get_method_names()
        input_references = np.zeros((len(method_names), len(class_names))).astype(bool)
        for i, method_name in enumerate(method_names):
            method_ = self.method_data[method_name]
            for ref_class_ in method_["parameterTypes"]:
                if ref_class_ in class_names:
                    j = class_names.index(ref_class_)
                    input_references[i, j] = True
        return pd.DataFrame(input_references, columns=class_names, index=method_names)

    def get_output_references_in_methods(self) -> pd.DataFrame:
        """ Returns a Methods x Class matrix with the output references for each class. """
        class_names = self.get_class_names()
        method_names = self.get_method_names()
        output_references = np.zeros((len(method_names), len(class_names))).astype(bool)
        for i, method_name in enumerate(method_names):
            method_ = self.method_data[method_name]
            ref_class_ = method_["returnType"]
            if ref_class_ in class_names:
                j = class_names.index(ref_class_)
                output_references[i, j] = True
        return pd.DataFrame(output_references, columns=class_names, index=method_names)

    def get_referenced_types(self, class_name: str) -> list[str]:
        """
        Get the types referenced in a class. This includes variables, fields, method parameters, and method return types.
        """
        return self.type_data[class_name]["referencedTypes"]

    def get_input_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class method input. """
        return self.type_data[class_name]["parameterTypes"]

    def get_output_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class method output. """
        return self.type_data[class_name]["returnTypes"]

    def get_field_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class field. """
        return self.type_data[class_name]["fieldTypes"]

    def get_class_constructors(self, class_name: str) -> list[str]:
        """ Get the constructors of a class. """
        class_details = self.type_data[class_name]
        return ["::".join([class_details["fullName"], c]) for c in class_details.get("constructors", [])]








