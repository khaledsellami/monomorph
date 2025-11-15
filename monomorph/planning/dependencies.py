import logging
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

from ..modeling.model import AppModel
from ..models import UpdatedDecomposition, UpdatedPartition


class APIClass:

    def __init__(self):
        # class fully qualified name
        self.name = ""
        # methods that reference this class
        self.methods: set[str] = set()
        # invocations that reference this class from a method (method, service)
        self.interactions: set[tuple[str, str]] = set()
        # The name of the microservice that owns this class
        self.microservice: Optional[str] = None
        # list of suggested fields for refactoring (in case of DTO)
        self.fields: Optional[list[str]] = None
        # interactions that reference this class from another (class, service)
        self.other_interactions: set[tuple[str, str]] = set()

    def __str__(self):
        return f"{self.name} in {self.microservice} with {len(self.methods)} methods: " + ", ".join(self.methods)


class DependencyDetector:
    def __init__(self, decomposition: UpdatedDecomposition, app_model: AppModel):
        self.app_model = app_model
        self.decomposition = decomposition
        self.logger = logging.getLogger("monomorph")

    def find_new_dtos(self) -> list[str]:
        # get the inter-class references
        field_references = self.app_model.get_field_references()
        input_references = self.app_model.get_input_references()
        output_references = self.app_model.get_output_references()
        # variable_references = self.app_model.get_variable_references()
        combined_references = field_references | input_references | output_references
        # get the decomposition mask
        decomposition_df = self.build_decomposition_matrix(self.decomposition)
        same_service_mask = decomposition_df.T @ decomposition_df
        # align the matrices
        decomposition_df, combined_references = self.align_class_references(decomposition_df, combined_references)
        # find the new DTOs
        inter_service_references = combined_references * ~same_service_mask
        class_names = inter_service_references.columns
        new_dtos = class_names[inter_service_references.sum(axis=0) > 0].tolist()
        return new_dtos

    def find_new_apis(self) -> tuple[list[str], list[str], dict[str, list[str]]]:
        self.logger.warning("This method does not handle duplicated classes correctly. "
                            "Use find_new_apis_partition instead.")
        inter_service_class_interactions, inter_service_method_interactions = self.find_boundaries()
        # get the class and method names
        class_names = inter_service_class_interactions.columns
        api_classes = class_names[inter_service_class_interactions.sum(axis=0) > 0].tolist()
        method_names = inter_service_method_interactions.columns
        api_methods = method_names[inter_service_method_interactions.sum(axis=0) > 0].tolist()
        referenced_methods = {method: method_names[np.where(inter_service_method_interactions.loc[:, method] > 0)].tolist()
                              for method in api_methods}
        return api_classes, api_methods, referenced_methods

    def to_api_classes(self, inter_service_method_interactions: dict[str, list[tuple[str, str]]],
                       other_class_interactions: dict[str, list[tuple[str, str]]]) -> dict[str, list[APIClass]]:
        api_classes = defaultdict(APIClass)
        for pname in inter_service_method_interactions:
            for m1, m2 in inter_service_method_interactions[pname]:
                class_name = m2.split("::")[0]
                api_classes[class_name].name = class_name
                api_classes[class_name].methods.add(m2)
                api_classes[class_name].interactions.add((m1, pname))
        for pname in other_class_interactions:
            for c1, c2 in other_class_interactions[pname]:
                class_name = c2
                if c2 not in api_classes:
                    self.logger.debug(f"Class {c2} not found in inter-service method interactions")
                    api_classes[class_name].name = class_name
                api_classes[class_name].other_interactions.add((c1, pname))
        api_classes_per_ms = defaultdict(list)
        for class_name in api_classes:
            for partition in self.decomposition.partitions:
                if class_name in partition.classes:
                    api_classes[class_name].microservice = partition.name
                    api_classes_per_ms[partition.name].append(api_classes[class_name])
                    # in case of duplicated classes, we will you use the first microservice as the owner of the class
                    break
        return dict(api_classes_per_ms)

    def find_new_apis_partition(self) -> (
            tuple)[dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]]:
        call_data = self.app_model.get_inter_method_calls() # M by M matrix
        class_methods_df = self.app_model.build_class_methods_matrix()  # C1 by M matrix
        class_methods_df, call_data = self.align_method_matrices(class_methods_df, call_data)
        class_interactions = class_methods_df @ call_data @ class_methods_df.T  # Cp by Cp matrix
        class_other_interactions = self.app_model.get_class_other_interactions()  # C1 by C1 matrix
        class_other_interactions = class_other_interactions.loc[class_interactions.index, class_interactions.index]
        class_methods = {c: class_methods_df.columns[class_methods_df.loc[c]].tolist() for c in class_methods_df.index}
        inter_service_class_interactions, inter_service_method_interactions = dict(), dict()
        other_class_interactions = dict()
        for partition in self.decomposition.partitions:
            inter_service_classes, inter_service_methods, other_inter_service_classes = (
                self.find_boundaries_partition(partition, call_data, class_interactions, class_methods,
                                               class_other_interactions))
            inter_service_class_interactions[partition.name] = inter_service_classes
            inter_service_method_interactions[partition.name] = inter_service_methods
            other_class_interactions[partition.name] = other_inter_service_classes
        return inter_service_class_interactions, inter_service_method_interactions, other_class_interactions

    def find_boundaries_partition(self, partition: UpdatedPartition, call_data: pd.DataFrame,
                                  class_interactions: pd.DataFrame, class_methods: dict[str, list[str]],
                                  class_other_interactions: pd.DataFrame) -> (
            tuple)[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
        inner_classes = partition.classes + [dup[0] for dup in partition.duplicated_classes]
        outer_classes = [c for c in class_interactions.columns if c not in inner_classes]
        outgoings_class = class_interactions.loc[inner_classes, outer_classes] > 0
        cols1 = outgoings_class.index
        cols2 = outgoings_class.columns
        inter_service_classes = [(cols1[c1], cols2[c2]) for c1, c2 in zip(*np.where(outgoings_class))]
        inner_methods = [m for c in inner_classes for m in class_methods[c]]
        outer_methods = [m for c in outer_classes for m in class_methods[c]]
        outgoings_methods = call_data.loc[inner_methods, outer_methods] > 0
        col1 = outgoings_methods.index
        col2 = outgoings_methods.columns
        inter_service_methods = [(col1[c1], col2[c2]) for c1, c2 in zip(*np.where(outgoings_methods))]
        other_outgoings_class = class_other_interactions.loc[inner_classes, outer_classes] > 0
        cols1 = other_outgoings_class.index
        cols2 = other_outgoings_class.columns
        other_inter_service_classes = [(cols1[c1], cols2[c2]) for c1, c2 in zip(*np.where(other_outgoings_class))]
        return inter_service_classes, inter_service_methods, other_inter_service_classes

    def find_boundaries(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        self.logger.warning("This method does not handle duplicated classes correctly. "
                            "Use find_boundaries_partition instead.")
        call_data = self.app_model.get_inter_method_calls() # M by M matrix
        # class and method relationships
        class_methods_df = self.app_model.build_class_methods_matrix() # C1 by M matrix
        # create the decomposition matrix
        decomposition_df = self.build_decomposition_matrix(self.decomposition) # K by C2 matrix
        # align the matrices to have the shapes (K by C) and (C by M)
        decomposition_df, class_methods_df = self.align_class_matrices(decomposition_df, class_methods_df)
        # row per microservice/class instance (in order to handle duplicated classes)
        class_methods_df = pd.concat([class_methods_df[decomposition_df.iloc[i]].add_prefix(f"ms-{i}.", axis=0)
                                      for i in range(decomposition_df.shape[0])], axis=0) # Cp by M matrix
        # mapping from original class name to duplicate class names
        ms_class_df = class_methods_df.T.apply(lambda x: ".".join(x.name.split(".")[1:]) == decomposition_df.columns,
                                               axis=0).set_index(decomposition_df.columns) # C by Cp matrix
        # align the matrices to have the shapes (C by M) and (M by M)
        class_methods_df, call_data = self.align_method_matrices(class_methods_df, call_data)
        # create the same-service mask (for each microservice/class instance)
        # same_service_mask = decomposition_df.T @ decomposition_df
        # Ignores remote calls to classes that have duplicates in the same service
        ms_decomposition_df = decomposition_df @ ms_class_df # K by Cp matrix
        same_service_mask = ms_decomposition_df.T @ ms_decomposition_df # Cp by Cp matrix
        # class interactions
        class_interactions = class_methods_df @ call_data @ class_methods_df.T # Cp by Cp matrix
        inter_service_class_interactions = class_interactions * ~same_service_mask
        # method interactions
        # method_decomposition_df = (decomposition_df @ class_methods_df).astype(bool)
        method_decomposition_df = (ms_decomposition_df @ class_methods_df).astype(bool)
        same_service_method_mask = method_decomposition_df.T @ method_decomposition_df
        inter_service_method_interactions = call_data * ~same_service_method_mask
        return inter_service_class_interactions, inter_service_method_interactions

    def build_decomposition_matrix(self, decomposition: UpdatedDecomposition) -> pd.DataFrame:
        class_names = self.app_model.get_class_names()
        n_classes = len(class_names)
        n_microservices = len(decomposition.partitions)
        decomposition_matrix = np.zeros((n_microservices, n_classes)).astype(bool)
        for i, partition in enumerate(decomposition.partitions):
            for class_name in partition.classes:
                # We assume that the class name is the same as the key in the type_data dictionary and that all classes
                # are covered in the static analysis
                class_idx = class_names.index(class_name)
                decomposition_matrix[i, class_idx] = True
            # add the duplicated classes
            for class_name, _ in partition.duplicated_classes:
                class_idx = class_names.index(class_name)
                decomposition_matrix[i, class_idx] = True
        decomposition_df = pd.DataFrame(decomposition_matrix, columns=class_names)
        return decomposition_df

    @classmethod
    def align_method_matrices(cls, class_methods_df: pd.DataFrame, call_data: pd.DataFrame) -> (
            tuple)[pd.DataFrame, pd.DataFrame]:
        logger = logging.getLogger("monomorph")
        # find the intersection of method names
        common_elements = class_methods_df.columns.intersection(call_data.columns)
        # check for missing methods
        missing_in_call_data = set(call_data.index) - set(class_methods_df.columns)
        if missing_in_call_data:
            logger.warning(f"Warning: There are {len(missing_in_call_data)} methods in inter-method calls but "
                           f"missing in the class-method matrix!")
        missing_in_class_methods = set(class_methods_df.columns) - set(call_data.index)
        if missing_in_class_methods:
            logger.warning(f"Warning: There are {len(missing_in_class_methods)} methods in the class-method "
                           f"matrix but missing in inter-method calls!")
        # align the matrices
        aligned_class_methods_df = class_methods_df[common_elements]
        aligned_call_data = call_data.loc[common_elements, common_elements]
        return aligned_class_methods_df, aligned_call_data

    def align_class_matrices(self, decomposition_df: pd.DataFrame, class_methods_df: pd.DataFrame) -> (
            tuple)[pd.DataFrame, pd.DataFrame]:
        # find the intersection of class names
        common_elements = decomposition_df.columns.intersection(class_methods_df.index)
        # check for missing classes
        missing_in_class_methods = set(class_methods_df.index) - set(decomposition_df.columns)
        if missing_in_class_methods:
            self.logger.warning(f"Warning: There are {len(missing_in_class_methods)} classes in the static analysis "
                                f"data but missing in decomposition data!")
        missing_in_decomposition = set(decomposition_df.columns) - set(class_methods_df.index)
        if missing_in_decomposition:
            self.logger.warning(f"Warning: There are {len(missing_in_decomposition)} classes in decomposition data "
                                f"but missing in the static analysis data!")
        # align the matrices
        aligned_decomposition_df = decomposition_df[common_elements]
        aligned_class_methods_df = class_methods_df.loc[common_elements, :]
        return aligned_decomposition_df, aligned_class_methods_df

    def align_class_references(self, decomposition_df: pd.DataFrame, combined_references: pd.DataFrame) -> (
            tuple)[pd.DataFrame, pd.DataFrame]:
        # find the intersection of class names
        common_elements = decomposition_df.columns.intersection(combined_references.columns)
        # check for missing classes
        missing_in_references = set(combined_references.index) - set(decomposition_df.columns)
        if missing_in_references:
            self.logger.warning(f"Warning: There are {len(missing_in_references)} classes in the references data but "
                                f"missing in decomposition data!")
        missing_in_decomposition = set(decomposition_df.columns) - set(combined_references.index)
        if missing_in_decomposition:
            self.logger.warning(f"Warning: There are {len(missing_in_decomposition)} classes in decomposition data "
                                f"but missing in the references data!")
        # align the matrices
        aligned_decomposition_df = decomposition_df[common_elements]
        aligned_combined_references = combined_references.loc[common_elements, common_elements]
        return aligned_decomposition_df, aligned_combined_references
