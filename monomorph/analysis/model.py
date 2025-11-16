import logging

import pandas as pd


class AppModel:
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.logger = logging.getLogger("monomorph")

    def get_inheritance(self, class_name: str) -> list[str]:
        raise NotImplementedError("get_inheritance not implemented yet")

    def get_inter_method_calls(self) -> pd.DataFrame:
        raise NotImplementedError("get_inter_method_calls not implemented yet")

    def get_class_other_interactions(self) -> pd.DataFrame:
        """
        Returns a DataFrame with all interactions (fields, inputs, outputs, variables ,etc) except method invocations
        between classes and other classes.
        """
        raise NotImplementedError("get_class_other_interactions not implemented yet")

    def build_class_methods_matrix(self) -> pd.DataFrame:
        raise NotImplementedError("build_class_methods_matrix not implemented yet")

    def get_class_names(self) -> list[str]:
        raise NotImplementedError("get_class_names not implemented yet")

    def get_method_names(self) -> list[str]:
        raise NotImplementedError("get_method_names not implemented yet")

    def get_field_references(self) -> pd.DataFrame:
        raise NotImplementedError("get_field_references not implemented yet")

    def get_input_references(self) -> pd.DataFrame:
        raise NotImplementedError("get_input_references not implemented yet")

    def get_output_references(self) -> pd.DataFrame:
        raise NotImplementedError("get_output_references not implemented yet")

    def get_variable_references(self) -> pd.DataFrame:
        raise NotImplementedError("get_variable_references not implemented yet")

    def get_inputs(self, method_name: str) -> list[str]:
        raise NotImplementedError("get_inputs not implemented yet")

    def get_outputs(self, method_name: str) -> list[str]:
        raise NotImplementedError("get_outputs not implemented yet")

    def get_inputs_as_ft(self, method_name: str) -> list[dict]:
        raise NotImplementedError("get_inputs_as_ft not implemented yet")

    def get_outputs_as_ft(self, method_name: str) -> list[dict]:
        raise NotImplementedError("get_outputs_as_ft not implemented yet")

    def get_method_source(self, method_name: str) -> str:
        raise NotImplementedError("get_method_source not implemented yet")

    def get_method_parent(self, method_name: str) -> str:
        raise NotImplementedError("get_method_parent not implemented yet")

    def get_class_source(self, class_name: str) -> str:
        raise NotImplementedError("get_class_source not implemented yet")

    def get_test_methods(self) -> list[str]:
        raise NotImplementedError("get_test_methods not implemented yet")

    def get_local_methods(self) -> list[str]:
        raise NotImplementedError("get_local_methods not implemented yet")

    def get_tags(self, method_name: str) -> set[str]:
        raise NotImplementedError("get_tags not implemented yet")

    def get_class_file_path(self, class_name: str) -> str:
        raise NotImplementedError("get_class_file_path not implemented yet")

    def get_method_simple_name(self, method_name: str) -> str:
        raise NotImplementedError("get_method_simple_name not implemented yet")

    def get_method_modifiers(self, method_name: str) -> list[str]:
        raise NotImplementedError("get_method_modifiers not implemented yet")

    def get_method_return_type(self, method_name: str) -> str:
        raise NotImplementedError("get_method_return_type not implemented yet")

    def get_method_parameter_types(self, method_name: str) -> list[str]:
        raise NotImplementedError("get_method_parameter_types not implemented yet")

    def get_method_generics_in_return_type(self, method_name: str) -> list[str]:
        """
        Get the generics in the return type of a method. (e.g. List<String>)
        This is a list of strings, where each string is a generic type.
        """
        raise NotImplementedError("get_method_generics_in_return_type not implemented yet")

    def get_method_generics_in_parameters(self, method_name: str) -> list[str]:
        """
        Get the generics in the parameter types of a method. (e.g. List<String>)
        This is a list of lists of strings, where each list is a generic type.
        """
        raise NotImplementedError("get_method_generics_in_parameters not implemented yet")

    def get_class_annotations(self, class_name: str) -> list[str]:
        raise NotImplementedError("get_class_annotations not implemented yet")

    def get_field_details(self, class_name: str) -> dict:
        """Get details of a class' field."""
        raise NotImplementedError("get_field_details not implemented yet")

    def get_input_references_in_methods(self) -> pd.DataFrame:
        """ Returns a Methods x Class matrix with the input references for each class. """
        raise NotImplementedError("get_input_references_in_methods not implemented yet")

    def get_output_references_in_methods(self) -> pd.DataFrame:
        """ Returns a Methods x Class matrix with the output references for each class. """
        raise NotImplementedError("get_output_references_in_methods not implemented yet")

    def get_referenced_types(self, class_name: str) -> list[str]:
        """
        Get the types referenced in a class. This includes variables, fields, method parameters, and method return types.
        """
        raise NotImplementedError("get_referenced_types not implemented yet")

    def get_input_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class method input. """
        raise NotImplementedError("get_input_types not implemented yet")

    def get_output_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class method output. """
        raise NotImplementedError("get_output_types not implemented yet")

    def get_field_types(self, class_name: str) -> list[str]:
        """ Get the types referenced in a class field. """
        raise NotImplementedError("get_field_types not implemented yet")

    def get_class_constructors(self, class_name: str) -> list[str]:
        """ Get the constructors of a class. """
        raise NotImplementedError("get_class_constructors not implemented yet")

