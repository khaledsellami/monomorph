import logging
import os
import re

from .inheritance import InheritanceHandler
from ..modeling.model import AppModel
from ..models import UpdatedDecomposition, Decomposition


class DecompositionPreprocessor:
    def __init__(self, decomposition: Decomposition, app_model: AppModel, include_tests: bool = True,
                 restrictive_selection: bool = False, project_root: str = None):
        self.decomposition = UpdatedDecomposition.from_decomposition(decomposition)
        self.app_model = app_model
        self.include_tests = include_tests
        self.restrictive_selection = restrictive_selection
        self.project_root = project_root

    def update_decomposition(self) -> UpdatedDecomposition:
        ih = InheritanceHandler(self.decomposition, self.app_model)
        decomposition = ih.update_decomposition()
        dh = DuplicationHandler(decomposition, self.app_model, self.project_root)
        decomposition = dh.duplicate_missing_classes(self.include_tests, self.restrictive_selection)
        return decomposition


class DuplicationHandler:
    def __init__(self, decomposition: UpdatedDecomposition, app_model: AppModel, project_root: str = None):
        self.decomposition = decomposition
        self.app_model = app_model
        self.project_root = project_root
        self.logger = logging.getLogger("monomorph")

    def duplicate_missing_classes(self, include_tests: bool = True,
                                  restrictive_selection: bool = False) -> UpdatedDecomposition:
        """
        This method duplicates the classes that are not included in the decomposition.
        :param include_tests: Duplicate test classes or not if they are not included in the decomposition
        :param restrictive_selection:  if True, do not duplicate classes that don't respect certain conditions
        (e.g., generic classes, classes without a package, not in path "src/main/java", etc.)
        :return: the updated decomposition with the duplicated classes
        """
        included_classes = [c for partition in self.decomposition.partitions for c in partition.classes] + [
            c for partition in self.decomposition.partitions for c, _ in partition.duplicated_classes
        ]
        missing_classes = [c for c in self.app_model.get_class_names() if c not in included_classes]
        if include_tests:
            classes_to_duplicate = missing_classes
        else:
            test_classes = set(self.app_model.get_method_parent(m) for m in self.app_model.get_test_methods())
            classes_to_duplicate = [c for c in missing_classes if c not in test_classes]
            self.logger.debug(f"Excluding {len(missing_classes) - len(classes_to_duplicate)} test classes "
                              f"from duplication")
        if restrictive_selection:
            before_filter = len(classes_to_duplicate)
            classes_to_duplicate = [c for c in classes_to_duplicate if self.validate_conditions(c)]
            self.logger.debug(f"Excluding {before_filter - len(classes_to_duplicate)} generic or invalid classes "
                              f"from duplication")

        self.logger.debug(f"Duplicating {len(classes_to_duplicate)} classes")
        for partition in self.decomposition.partitions:
            for class_name in classes_to_duplicate:
                partition.add_duplicated_class(class_name, None, "missing_class")
        return self.decomposition

    def validate_conditions(self, class_name: str) -> bool:
        """
        Validates if the class name meets certain conditions.
        :param class_name: The name of the class to validate.
        :return: True if the class name meets the conditions, False otherwise.
        """
        if not self.project_root:
            self.logger.warning("Project root not set. Cannot validate in_main condition.")
            cond = True
        else:
            file_path = self.app_model.get_class_file_path(class_name)
            if file_path is None:
                return False
            else:
                relative_path = os.path.relpath(file_path, self.project_root)
                cond = self.in_main(relative_path)
        return (not self.is_generic(class_name)) and cond

    def is_test_file(self, file_path: str) -> bool:
        test_indicators = ["test", "Test", "spec", "Spec"]
        return any(indicator in file_path for indicator in test_indicators)

    def in_main(self, path: str) -> bool:
        return re.match(r"^src/main/java/.*\.java", path) is not None

    def is_generic(self, class_name: str) -> bool:
        return len(class_name.split(".")) < 2 or class_name.count("$") > 0
