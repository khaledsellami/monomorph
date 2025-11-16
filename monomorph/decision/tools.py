import itertools
import re
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

import pandas as pd
from langchain_core.tools import tool, BaseTool

from .models import ClassNameInput, MethodNameInput
from ..logging.printer import ConsolePrinter
from ..analysis import AppModel
from ..models import UpdatedDecomposition
from ..planning.dependencies import DependencyDetector


class AnalysisTools:
    """Implementations for the tools for making refactoring decisions."""

    def __init__(self, app_model: AppModel, decomposition: UpdatedDecomposition, current_ms: Optional[str] = None,
                 current_class: Optional[str] = None, language: str = "java",
                 relevant_classes: Optional[List[str]] = None):
        self.app_model = app_model
        self.decomposition = decomposition
        self.current_ms = current_ms
        self.current_class = current_class
        self.language = language
        self.references_dict = {}
        self.references_matrices = {}
        self.names = list(relevant_classes) if relevant_classes else app_model.get_class_names()
        self.method_names = [m for m in app_model.get_method_names() if m.split("::")[0] in self.names]
        self.logger = ConsolePrinter.get_printer("monomorph")
        self._build_interaction_dict()

    def get_source_code(self, class_name: str) -> str:
        """
        Use this to Retrieve the source code for a given class. It is useful for getting the full source code of a
        specific {self.language} class to understand its structure and methods.
        """
        self.logger.debug(f"'get_source_code' invoked for class {class_name.split('.')[-1]}", msg_type="tool")
        # ConsolePrinter.get_printer("monomorph").print("--- Retrieving source code ---", "tool")
        # Check if the class name is the same as the current class
        if self.current_class and (class_name == self.current_class or (class_name.count(".") == 0 and
                                                                        self.current_class.endswith(class_name))):
            # Since the source code of the class is given at the start, no need to bloat the conversation.
            return "Redundant request! Check the initially provided source code."
        if class_name not in self.names:
            class_name = self._find_matching_name(class_name)
            if class_name is None:
                self.logger.warning(f"Class {class_name} not found in the application model.")
                return (f"Class {class_name} not found! It may not be part of the application (potentially from a "
                        f"package of the standard library).")
        text = f"The source code of the class `{class_name}` is:\n"
        return text + f"```{self.language}\n{self.app_model.get_class_source(class_name)}\n```"

    def list_class_fields(self, class_name: str) -> list[str]:
        """
        Use this to list the field names and types within a given class and whether they are from the local application
        or not. It provides a list of field description (e.g., name: 'var', type: 'com.package.MyVar', is local')
        for a class. Helps assess data complexity and potential DTO content.
        """
        self.logger.debug(f"'list_class_fields' invoked for class {class_name.split('.')[-1]}", msg_type="tool")
        fields = self.app_model.get_field_details(class_name)
        return [(f"name: '{field['variableName']}', type_fqn: '{field['type']['fullName']}' "
                 f"and is {'local' if field['type']['typeSource'] == 'LOCAL' else 'not local'}")
                for field in fields]

    def find_class_usages(self, class_name: str) -> str:
        """
        Use this to Find where and how the class is used. CRITICAL: Finds where a class is used throughout the
        codebase. Returns a list, each containing the (caller_class_name, caller_method_name, interaction_type,
        microservice_it_belongs_to) where interaction type can be field usage, method input usage, output usage or
        method invocation. If interaction type is 'field'. Essential for understanding who the consumers are and
        which microservices consume the class.
        """
        self.logger.debug(f"'find_class_usages' invoked for class {class_name.split('.')[-1]}", msg_type="tool")
        # ConsolePrinter.get_printer("monomorph").print("--- Finding class usages ---", "tool")
        if class_name not in self.names:
            class_name = self._find_matching_name(class_name)
            if class_name is None:
                self.logger.warning(f"Class {class_name} not found in the application model.")
                return ""
        usages = list(itertools.chain.from_iterable([refs[class_name] for refs in self.references_dict.values()]))
        return self._format_usages(class_name, usages)

    def get_method_source_code(self, class_name: str, method_name: str) -> str:
        """ Use this to find the source code for a given class and method. Useful for getting the full source code of
        a specific {self.language} method to understand its structure and usage."""
        # ConsolePrinter.get_printer("monomorph").print(f"--- Retrieving source code for method {method_name} ---", "tool")
        self.logger.debug(f"'get_method_source_code' invoked for class {class_name.split('.')[-1]} "
                          f"and method {method_name}", msg_type="tool")
        full_method_name = f"{class_name}::{method_name}"
        if full_method_name not in self.method_names:
            full_method_name = self._find_matching_method(full_method_name)
            if full_method_name is None:
                self.logger.warning(f"Method {full_method_name} not found in the application model.")
                return (f"Method {full_method_name} not found! It may not be part of the application (potentially from "
                        f"a package of the standard library).")
        text = f"The source code of the method `{full_method_name}` is:\n"
        return text + f"```{self.language}\n{self.app_model.get_method_source(full_method_name)}\n```"

    def _format_usages(self, class_name: str, usages: list[tuple[str, Optional[str], str, str]]) -> str:
        """Format the usages for better readability."""
        # def format_usage(caller_class, caller_method, interaction_type, microservice):
        #     usage = interaction_type if not caller_method else 'n '+interaction_type + ' within `' + caller_method + '`'
        #     return f"Used within Class `{caller_class}` in Microservice `{microservice}` as {usage}"
        # return "\n".join([format_usage(*usage) for usage in usages])
        sorted_by_ms =defaultdict(list)
        for caller_class, caller_method, interaction_type, microservice in usages:
            formatted_text = f"- By `{caller_class}` as {interaction_type}"
            sorted_by_ms[microservice].append(formatted_text)
        lines = [f"### Class {class_name} usage:"]
        for ms, usages in sorted_by_ms.items():
            usages = set(usages)
            lines.append(f"#### Microservice {ms}:")
            lines.append("\n".join(usages))
        return "\n".join(lines)

    def _find_matching_method(self, method_full_name: str) -> Optional[str]:
        """ Finds a matching method for the given method name. """
        for m in self.method_names:
            if re.match(r".*" + re.escape(method_full_name) + r"\(?.*", m):
                method_simple_name = method_full_name.split("::")[-1].split("(")[0]
                m_simple_name = m.split("::")[-1].split("(")[0]
                if method_simple_name == m_simple_name:
                    return m
                self.logger.warning(f"Found partial match for method {method_full_name} in {m}.")

    def _find_matching_name(self, class_name: str) -> Optional[str]:
        """ Finds a matching name for the given class name. """
        for c in self.names:
            if c.endswith(class_name):
                return c
        return None

    def _cache_interaction_matrices(self):
        # get the inter-class references
        field_references = self.app_model.get_field_references()
        input_references = self.app_model.get_input_references_in_methods()  # M by C matrix
        output_references = self.app_model.get_output_references_in_methods()  # M by C matrix
        # variable_references = self.app_model.get_variable_references()
        call_data = self.app_model.get_inter_method_calls()  # M by M matrix
        # class and method relationships
        class_methods_df = self.app_model.build_class_methods_matrix()
        # class interactions_df
        class_methods_df, call_data = DependencyDetector.align_method_matrices(class_methods_df, call_data)
        class_interactions = call_data @ class_methods_df.T  # M by C matrix
        self.references_matrices = {}
        for ref_type, m in zip(["field", "input", "output", "invocation"],
                               [field_references, input_references, output_references, class_interactions]):
            if ref_type == "field":
                self.references_matrices[ref_type] = m.astype(bool).loc[self.names, self.names]
            else:
                self.references_matrices[ref_type] = m.astype(bool).loc[self.method_names, self.names]


    def _map_interactions_to_dict(self):
        class_ms_map = self._gen_class_ms_map()

        def refs_to_dict(refs: pd.DataFrame) -> Dict[str, List[str]]:
            return {class_name: refs.index[refs[class_name] > 0].tolist() for class_name in refs.columns}

        def names_to_tuples(names_dict: Dict[str, List[str]], ref_type: str = None) -> (
                Dict)[str, List[Tuple[str, str, str, str]]]:
            return {
                cl: [(c.split("::")[0], c.split("::")[1], ref_type, class_ms_map[c.split("::")[0]])
                     if ref_type != "field" else (c, None, ref_type, class_ms_map[c])
                     for c in refs] for cl, refs in names_dict.items()
            }

        self.references_dict = {}
        for ref_type, m in self.references_matrices.items():
            self.references_dict[ref_type] = names_to_tuples(refs_to_dict(m), ref_type)

    def _build_interaction_dict(self):
        self._cache_interaction_matrices()
        self._map_interactions_to_dict()

    def set_current_ms(self, ms_name: str):
        """ Sets the current microservice name. """
        self.current_ms = ms_name
        # Update the references_dict to reflect the current microservice
        self._map_interactions_to_dict()

    def _gen_class_ms_map(self) -> Dict[str, str]:
        """Generates a mapping of class names to microservice names."""
        partition = None
        if self.current_ms:
            for partition in self.decomposition.partitions:
                if partition.name == self.current_ms:
                    break
            if partition is None:
                raise ValueError(f"Microservice {self.current_ms} not found in the decomposition.")
        ms_per_class = {}
        for c in self.names:
            ms_per_class[c] = None
            if partition and (c in partition.classes or c in partition.duplicated_classes):
                ms_per_class[c] = partition.name
            else:
                for p in self.decomposition.partitions:
                    if c in p.classes or c in p.duplicated_classes:
                        ms_per_class[c] = p.name
                        break
        return ms_per_class

    def get_tools(self) -> List[BaseTool]:
        """ Returns a list of tools for the analysis. """
        @tool(args_schema=ClassNameInput, description=f"Use this to Retrieve the source code for a given class. "
                                                      f"It is useful for getting the full source code of a specific "
                                                      f"{self.language} class to understand its structure and methods.")
        def get_source_code(class_name: str) -> str:
            return self.get_source_code(class_name)
    
        @tool(args_schema=ClassNameInput)
        def find_class_usages(class_name: str) -> str:
            """
            Use this to Find where and how the class is used. CRITICAL: Finds where a class is used throughout the
            codebase. Returns a list, each containing the (caller_class_name, caller_method_name, interaction_type,
            microservice_it_belongs_to) where interaction type can be field usage, method input usage, output usage or
            method invocation. If interaction type is 'field'. Essential for understanding who the consumers are and
            which microservices consume the class.
            """
            return self.find_class_usages(class_name)
    
        @tool(args_schema=MethodNameInput, description=f"Use this to find the source code for a given class and method."
                                                       f"Useful for getting the full source code of a specific "
                                                       f"{self.language} method to understand its structure and usage.")
        def get_method_source_code(class_name: str, method_name: str) -> str:
            return self.get_method_source_code(class_name, method_name)
    
        tools = [get_source_code, find_class_usages, get_method_source_code]
        return tools
