import logging
import re
from typing import Optional

from monomorph.helpers import HelperManager
from ..analysis.model import AppModel
from ..planning.dependencies import APIClass
from ..const import ApproachType, RefactoringMethod


class PlannedAPIClass(APIClass):
    """
    Class representing the plan for an API class.
    """
    NAME_PREFIX = ""

    def __init__(self, helper_manager: HelperManager, name: str, microservice: Optional[str],
                 decision: ApproachType, methods: Optional[set[str]] = None, 
                 interactions: set[tuple[str, str]] = None, reasoning: str = "unspecified", 
                 fields: Optional[list[str]] = None, other_interactions: Optional[set[tuple[str, str]]] = None):
        """
        Generate the planned names for the client, server, and mapper classes involved in the refactoring of the API class.
        """
        super().__init__()
        self.name = name
        self.microservice = microservice
        self.methods = methods if methods else set()
        self.interactions = interactions if interactions else set()
        self.other_interactions = other_interactions if other_interactions else set()
        self.fields = fields
        name_split = name.split(".")
        self.simple_name = name_split[-1]
        self.package_name = ".".join(name_split[:-1])
        self.decision = decision
        self.reasoning = reasoning
        name_with_prefix = f"{self.NAME_PREFIX}{self.simple_name}"
        if decision in [ApproachType.DTO_BASED, ApproachType.DTO_ONLY]:
            client_template = helper_manager.DTO_CLIENT_TEMPLATE
            server_template = helper_manager.DTO_SERVICE_IMPLEMENTATION_TEMPLATE
            proto_template = helper_manager.DTO_PROTO_TEMPLATE
            mapper_template = helper_manager.DTO_MAPPER_TEMPLATE
            self.mapper_name = (f"{helper_manager.helper_mapping[mapper_template]['package']}."
                                f"{name_with_prefix}Mapper")
        else:
            client_template = helper_manager.CLIENT_CLASS_TEMPLATE
            server_template = helper_manager.SERVICE_IMPLEMENTATION_TEMPLATE
            proto_template = helper_manager.SERVICE_PROTO_TEMPLATE
            mapper_template = helper_manager.ID_MAPPER_TEMPLATE
            self.mapper_name = (f"{helper_manager.helper_mapping[mapper_template]['package']}."
                                f"{helper_manager.helper_mapping[mapper_template]['object_name']}")
        self.client_name = f"{helper_manager.helper_mapping[client_template]['package']}.{name_with_prefix}"
        self.proto_package = f"{helper_manager.helper_mapping[proto_template]['package']}.{self.simple_name.lower()}"
        self.server_name = f"{helper_manager.helper_mapping[server_template]['package']}.{name_with_prefix}Impl"
        self.service_name = f"{self.proto_package}.{name_with_prefix}Service"
        self.dto_name = f"{name_with_prefix}DTO"
        self.proto_filename = f"{camel_to_snake(name_with_prefix)}.proto"
        self.referenced_classes = set()
        self.referencing_classes = set()
        self.client_microservices = None
        
    @classmethod
    def from_api_class(cls, api_class: APIClass, helper_manager: HelperManager,
                       decision: ApproachType, reasoning: str = "unspecified"):
        """
        Create a PlannedAPIClass from an APIClass.
        """
        return cls(helper_manager, api_class.name, api_class.microservice, decision, api_class.methods, 
                   api_class.interactions, reasoning, api_class.fields, api_class.other_interactions)
        
        
class ProxyPlanner:
    """
    Class responsible for determining the proxy and mapper that correspond to API classes based on the approach decision.
    It also verifies if any other classes were used as inputs/outputs in the exposed methods or as fields in the new DTOs.
    """
    MAX_ITERATIONS = 10  # Maximum number of iterations to avoid infinite loops

    def __init__(self, analysis_model: AppModel, helper_manager: HelperManager):
        """
        :param analysis_model: The analysis model to be used for extracting information about the application.
        :param helper_manager: The helper manager to be used for generating the planned names for the classes.
        """
        self.analysis_model = analysis_model
        self.helper_manager = helper_manager
        self.all_classes = self.analysis_model.get_class_names()
        self.logger = logging.getLogger("monomorph")

    def find_and_name_all_api_classes(self, initial_decisions: dict[str, RefactoringMethod],
                                      api_classes: dict[str, APIClass]) -> dict[str, PlannedAPIClass]:
        assert len(initial_decisions) == len(api_classes), "The keysets of the decisions and API classes must be the same."
        # Initial phase to handle the original API classes (that expose methods)
        planned_api_classes: dict[str, PlannedAPIClass] = dict()
        updated_api_classes = {c: [d.reasoning] for c, d in initial_decisions.items()}
        for class_name, api_class in api_classes.items():
            # Get the decision for the class
            decision = initial_decisions[class_name].decision
            method_names = api_class.methods
            # Create the planned API class
            planned_api_class = PlannedAPIClass.from_api_class(api_class, self.helper_manager, decision,
                                                               initial_decisions[class_name].reasoning)
            # Update the classes with the decision and the planned API class
            planned_api_classes[class_name] = planned_api_class
            updated_api_classes, all_refs = self.update_api_classes(class_name, decision, updated_api_classes,
                                                                    method_names)
            planned_api_classes[class_name].referenced_classes = all_refs
        # Update the new classes with the DTO-Only decision
        classes_without_decision = set(updated_api_classes.keys()) - set(planned_api_classes.keys())
        if classes_without_decision:
            self.logger.debug(f"Found {len(classes_without_decision)} classes that were part of the API communication.")
        i = 0
        # Second phase to handle the newly added classes
        while classes_without_decision:
            if i > self.MAX_ITERATIONS:
                self.logger.warning(f"Maximum iterations reached ({self.MAX_ITERATIONS}). Stopping the process.")
                break
            self.logger.debug(f"Iteration {i} - Handling {len(classes_without_decision)} new API classes.")
            for class_name in classes_without_decision:
                self.logger.debug(f"Treating class {class_name} as DTO-Only.")
                # The new classes will be treated as DTO-Only as they do not expose any methods to external MSs
                decision = ApproachType.DTO_ONLY
                # Create the planned API class
                ms_name = None
                reasoning = "\n".join(updated_api_classes[class_name])
                planned_api_class = PlannedAPIClass(self.helper_manager, class_name, ms_name, decision, None,
                                                    None, reasoning, None)

                # Update the classes with the decision
                planned_api_classes[class_name] = planned_api_class
                # Check if any of its fields are not already in the API classes
                updated_api_classes, all_refs = self.update_api_classes(class_name, decision, updated_api_classes)
                planned_api_classes[class_name].referenced_classes = all_refs
            i += 1
            classes_without_decision = set(updated_api_classes.keys()) - set(planned_api_classes.keys())
        self.reverse_map_referenced_classes(planned_api_classes)
        return planned_api_classes

    def reverse_map_referenced_classes(self, planned_api_classes: dict[str, PlannedAPIClass]):
        """
        Reverse map the referenced classes to the classes that reference them.
        :param planned_api_classes: The planned API classes to be updated.
        """
        for class_name, planned_api_class in planned_api_classes.items():
            for ref_class in planned_api_class.referenced_classes:
                if ref_class in planned_api_classes:
                    planned_api_classes[ref_class].referencing_classes.add(class_name)
                else:
                    self.logger.debug(f"Class {ref_class} was not found in the planned API classes.")

    def update_api_classes(self, class_name: str, decision: ApproachType, current_api_classes: dict[str, list[str]],
                           method_names: Optional[set[str]] = None) -> tuple[dict[str, list[str]], set]:
        updated_api_classes = current_api_classes.copy()
        all_refs = set()
        list_to_check = {}
        if decision != ApproachType.DTO_ONLY:
            if method_names:
                refs = self.get_refs_in_exposed_methods(method_names, class_name)
                list_to_check["input/output"] = refs
        if decision in [ApproachType.DTO_BASED, ApproachType.DTO_ONLY]:
            field_refs = self.analysis_model.get_field_types(class_name)
            list_to_check["fields"] = field_refs
        for f, l in list_to_check.items():
            for c in l:
                if c in self.all_classes:
                    if self.analysis_model.get_class_file_path(c) is None or self.analysis_model.get_class_source(c) is None or self.analysis_model.get_class_source(c)==c:
                        self.logger.warning(f"Class {c} is not a valid class. Skipping it.")
                        continue
                    all_refs.add(c)
                    if c not in updated_api_classes:
                        # if self.analysis_model.is_interface(c):
                        #     self.logger.debug(f"Found a reference to {c} in {class_name} as input/output/field."
                        #                       f"Since it is an interface, adding it to planned IDs.")
                        #     # add a reason text for tracing
                        #     reasoning = (f"Class {c} was used within the "
                        #                  f"{'fields' if f == 'fields' else 'input/output of methods'} of {class_name} "
                        #                  f"and it is an interface.")
                        # else:
                        self.logger.debug(
                            f"Found a reference to {c} in {class_name} as input/output/field. Adding it to planned DTOs.")
                        # add a reason text for tracing
                        reasoning = (f"Class {c} was used within the "
                                     f"{'fields' if f == 'fields' else 'input/output of methods'} of {class_name}.")
                        if c in updated_api_classes:
                            updated_api_classes[c].append(reasoning)
                        else:
                            updated_api_classes[c] = [reasoning]
        return updated_api_classes, all_refs

    def get_refs_in_exposed_methods(self, method_names: set[str], class_name: str) -> set[str]:
        """
        Get the application's classes referenced in the exposed methods of a class.
        """
        refs = set()
        constructors = set(self.analysis_model.get_class_constructors(class_name))
        if len(method_names) > 0:
            for method_name in method_names.union(constructors):
                # Get the input and output types
                input_types = self.analysis_model.get_method_parameter_types(method_name)
                output_types = [self.analysis_model.get_method_return_type(method_name)]
                generics_in_inputs = self.analysis_model.get_method_generics_in_parameters(method_name)
                generics_in_outputs = self.analysis_model.get_method_generics_in_return_type(method_name)
                # Add the input and output types to the refs
                refs.update(input_types + output_types + generics_in_inputs + generics_in_outputs)
        return refs


def camel_to_snake(camel_str: str) -> str:
    """
    Convert a string from CamelCase to snake_case.

    :param camel_str (str) A string in CamelCase format
    :return: str: The converted string in snake_case format
    """
    # First handle the case where we have consecutive uppercase letters (like HTTP in SimpleHTTPServer)
    # We want to add underscore only before the last uppercase letter in a sequence
    s1 = re.sub(r'([A-Z])([A-Z][a-z])', r'\1_\2', camel_str)
    # Then handle the regular case of a lowercase followed by an uppercase
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower()
