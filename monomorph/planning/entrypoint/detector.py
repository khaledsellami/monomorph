import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

from ...modeling.model import AppModel
from .java_argparser import find_java_main_class, extract_docker_command


class JavaEntrypointDetector:
    """
    Finds the most likely Java application entrypoint (main class) based on
    method analysis data and optional build/configuration files.
    """

    # Define the expected main method signature components
    EXPECTED_METHOD_NAME = "main"
    EXPECTED_RETURN_TYPE = "void"
    EXPECTED_PARAM_TYPES = ["java.lang.String[]", "String[]"]
    REQUIRED_METHOD_MODIFIERS = {"public", "static"}
    # Define annotations to look for (add others if needed)
    SPRING_BOOT_ANNOTATION_SIMPLE = "SpringBootApplication"
    SPRING_BOOT_ANNOTATION_FQ = "org.springframework.boot.autoconfigure.SpringBootApplication"
    PRIORITY_ANNOTATIONS = {SPRING_BOOT_ANNOTATION_SIMPLE, SPRING_BOOT_ANNOTATION_FQ}

    def __init__(self,
                 app_model: AppModel,
                 pom_xml_path: Optional[str] = None,
                 build_gradle_path: Optional[str] = None,
                 dockerfile_path: Optional[str] = None):
        """
        Initializes the finder.

        Args:
            app_model: An instance of a concrete AppModel implementation providing
                       access to method and class details (including annotations
                       and assumed method modifiers).
            pom_xml_path: Optional path to the project's pom.xml file.
            build_gradle_path: Optional path to the project's build.gradle or build.gradle.kts file.
            dockerfile_path: Optional path to the project's Dockerfile.
        """
        if not isinstance(app_model, AppModel):
            raise TypeError("methods_data must be a list of method dictionaries.")
        self.app_model = app_model
        self.pom_xml_path = pom_xml_path
        self.build_gradle_path = build_gradle_path
        self.dockerfile_path = dockerfile_path
        self.logger = logging.getLogger("monomorph")

    def _is_main_method_signature(self, method_name: str) -> bool:
        """Checks if a method signature matches `public static void main(String[] args)`."""

        # 1. Check method name
        simple_name = self.app_model.get_method_simple_name(method_name)
        pattern = rf"^{self.EXPECTED_METHOD_NAME}\(?.*\)?$"
        if not re.match(pattern, simple_name):
            # self.logger.debug(f"Method '{simple_name}' does not match expected name '{self.EXPECTED_METHOD_NAME}'.")
            return False

        # 2. Check modifiers (must contain public and static)
        method_modifiers = set(self.app_model.get_method_modifiers(method_name))
        if not self.REQUIRED_METHOD_MODIFIERS.issubset(method_modifiers):
            self.logger.debug(f"Method '{method_name}' does not have required modifiers: "
                              f"{self.REQUIRED_METHOD_MODIFIERS}. Found: {method_modifiers}.")
            return False

        # 3. Check return type
        if self.app_model.get_method_return_type(method_name) != self.EXPECTED_RETURN_TYPE:
            self.logger.debug(f"Method '{method_name}' does not have expected return type '{self.EXPECTED_RETURN_TYPE}'.")
            return False

        # 4. Check parameters (exactly one parameter of type String[])
        param_types = self.app_model.get_method_parameter_types(method_name)
        if len(param_types) != 1:
            self.logger.debug(f"Method '{method_name}' does not have exactly one parameter. Found: {len(param_types)}.")
            return False

        # 5. Check parameter type (must be String[] or java.lang.String[])
        param_type = param_types[0]
        if param_type not in self.EXPECTED_PARAM_TYPES:
            self.logger.debug(f"Method '{method_name}' parameter type '{param_type}' does not match expected types: "
                              f"{self.EXPECTED_PARAM_TYPES}.")
            return False

        # All checks passed
        return True

    def _find_main_in_pom(self, candidates: list[str]) -> Optional[str]:
        """Parses pom.xml to find mainClass declaration."""
        if not self.pom_xml_path or not os.path.exists(self.pom_xml_path):
            return None
        self.logger.debug(f"Analyzing POM file: {self.pom_xml_path}")
        try:
            tree = ET.parse(self.pom_xml_path)
            root = tree.getroot()
            ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
            query_patterns = [
                './/mvn:plugin[mvn:artifactId="maven-jar-plugin"]/mvn:configuration/mvn:archive/mvn:manifest/mvn:mainClass',
                './/mvn:plugin[mvn:artifactId="maven-assembly-plugin"]/mvn:configuration/mvn:archive/mvn:manifest/mvn:mainClass',
                './/mvn:plugin[mvn:artifactId="spring-boot-maven-plugin"]/mvn:configuration/mvn:mainClass',
                './/mvn:plugin[mvn:artifactId="spring-boot-maven-plugin"]/mvn:configuration/mvn:start-class',
                './/mvn:properties/mvn:main.class',
                './/mvn:properties/mvn:start-class'
            ]
            found_main_class = None
            for pattern in query_patterns:
                element = root.find(pattern, ns)
                if element is not None and element.text:
                    found_main_class = element.text.strip()
                    self.logger.debug(f"Found potential mainClass '{found_main_class}' in POM ({pattern})")
                    break
            if found_main_class and found_main_class in candidates:
                self.logger.info(f"POM mainClass '{found_main_class}' matches a candidate entrypoint.")
                return found_main_class
            elif found_main_class:
                self.logger.warning(f"POM mainClass '{found_main_class}' found, but does not match any potential "
                                    f"entrypoints found via signature analysis: {candidates}")
        except ET.ParseError:
            self.logger.error(f"Error parsing POM XML file: {self.pom_xml_path}")
        except Exception as e:
            self.logger.error(f"Unexpected error reading POM file: {e}")
        return None

    def _find_main_in_gradle(self, candidates: list[str]) -> Optional[str]:
        """Parses build.gradle to find mainClassName/mainClass."""
        if not self.build_gradle_path or not os.path.exists(self.build_gradle_path):
            return None
        self.logger.debug(f"Analyzing Gradle file: {self.build_gradle_path}")
        try:
            with open(self.build_gradle_path, 'r', encoding='utf-8') as f:
                content = f.read()
            patterns = [
                r'mainClassName\s*=\s*["\']([\w\.]+)["\']', r'mainClass\s*=\s*["\']([\w\.]+)["\']',
                r'mainClassName\s*=\s*([\w\.]+)\s*$', r'mainClass\.set\s*\(\s*["\']([\w\.]+)["\']\s*\)',
                r'mainClassName\.set\s*\(\s*["\']([\w\.]+)["\']\s*\)',
            ]
            found_main_class = None
            for pattern in patterns:
                match = re.search(pattern, content, re.MULTILINE)
                if match:
                    found_main_class = match.group(1).strip()
                    self.logger.debug(f"Found potential mainClassName '{found_main_class}' "
                                      f"in Gradle file (regex pattern)")
                    break
            if found_main_class and found_main_class in candidates:
                self.logger.info(f"Gradle mainClassName '{found_main_class}' matches a candidate entrypoint.")
                return found_main_class
            elif found_main_class:
                self.logger.warning(f"Gradle mainClassName '{found_main_class}' found, but does not match any "
                                    f"potential entrypoints found via signature analysis: {candidates}")
        except Exception as e:
            self.logger.error(f"Error reading or parsing Gradle file: {e}")
        return None

    def _find_main_in_dockerfile(self, candidates: list[str]) -> Optional[str]:
        """Placeholder: Parses Dockerfile for ENTRYPOINT or CMD potentially specifying a class."""
        if not self.dockerfile_path or not os.path.exists(self.dockerfile_path):
            return None
        self.logger.info(f"Analyzing Dockerfile: {self.dockerfile_path}")
        try:
            with open(self.dockerfile_path, 'r', encoding='utf-8') as f:
                dockerfile_text = f.read()
            command = extract_docker_command(dockerfile_text)
            if not command:
                self.logger.debug(f"No ENTRYPOINT or CMD found in Dockerfile.")
                return None
            main_class_or_source = find_java_main_class(command)
            if main_class_or_source:
                if main_class_or_source.endswith('.java'):
                    # Main is in a source file, check if it matches a class name
                    for class_name in candidates:
                        file_path = self.app_model.get_class_file_path(class_name)
                        if file_path and file_path.endswith(main_class_or_source):
                            self.logger.info(f"Dockerfile main source '{main_class_or_source}' matches a candidate "
                                             f"entrypoint {class_name}.")
                            return class_name
                    else:
                        self.logger.warning(f"Main class '{main_class_or_source}' found in Dockerfile, but not in "
                                            f"AppModel class names.")
                        return None
                else:
                    # Main is in a class name
                    if main_class_or_source in candidates:
                        self.logger.info(f"Dockerfile main class '{main_class_or_source}' matches a candidate "
                                         f"entrypoint.")
                        return main_class_or_source
                    else:
                        self.logger.warning(f"Dockerfile main class '{main_class_or_source}' found, but does not match "
                                            f"any potential entrypoints found via signature analysis: {candidates}")
                        return None
        except Exception as e:
            self.logger.error(f"Error reading or parsing Dockerfile: {e}")
        return None

    def _find_annotated_main(self, candidates: list[str]) -> Optional[str | list[str]]:
        """Checks candidates for priority annotations like @SpringBootApplication."""
        self.logger.debug("Checking candidates for priority annotations...")
        annotated_candidates = []
        for class_name in candidates:
            try:
                annotations = self.app_model.get_class_annotations(class_name)
                # Check if any of the class's annotations are in our priority list
                if not self.PRIORITY_ANNOTATIONS.isdisjoint(annotations):
                    self.logger.info(
                        f"Found priority annotation ({self.PRIORITY_ANNOTATIONS.intersection(annotations)}) "
                        f"on candidate: {class_name}")
                    annotated_candidates.append(class_name)
            except Exception as e:
                self.logger.error(f"Error getting annotations for class {class_name} from AppModel: {e}")
                continue

        if len(annotated_candidates) == 1:
            self.logger.info(f"Selected entrypoint '{annotated_candidates[0]}' based on unique priority annotation.")
            return annotated_candidates[0]
        elif len(annotated_candidates) > 1:
            self.logger.warning(f"Multiple candidates found with priority annotations: {annotated_candidates}. "
                                f"This is unusual for annotations like @SpringBootApplication. "
                                f"Proceeding to package hierarchy check among these.")
            # We will let the next stage (package hierarchy) decide among these annotated ones
            return annotated_candidates  # Signal that ambiguity remains among annotated candidates
        else:
            self.logger.debug("No candidates found with priority annotations.")
            return None

    def _get_package_depth(self, class_name: str) -> int:
        """Calculates package depth (number of dots)."""
        return class_name.count('.')

    def _select_best_entrypoint(self, potential_entrypoints: list[str]) -> Optional[str]:
        """
        Selects the most likely entrypoint from a list of candidates.

        Priority:
        1. Explicitly defined in pom.xml (if provided and matches a candidate).
        2. Explicitly defined in build.gradle (if provided and matches a candidate).
        3. Explicitly defined in Dockerfile (if provided and matches a candidate).
        4. Class annotated with a priority annotation (e.g., @SpringBootApplication).
           If multiple are annotated, proceed to #5 among the annotated ones.
        5. Class with the shallowest package depth.
        6. Alphabetical order as a final tie-breaker.
        """
        if not potential_entrypoints:
            return None
        if len(potential_entrypoints) == 1:
            return potential_entrypoints[0]

        self.logger.info(f"Multiple potential entrypoints found: {potential_entrypoints}. Attempting disambiguation...")

        # 1. Check build configuration files
        from_pom = self._find_main_in_pom(potential_entrypoints)
        if from_pom:
            return from_pom
        from_gradle = self._find_main_in_gradle(potential_entrypoints)
        if from_gradle:
            return from_gradle
        from_dockerfile = self._find_main_in_dockerfile(potential_entrypoints)
        if from_dockerfile:
            return from_dockerfile

        candidates_for_hierarchy_check = potential_entrypoints

        # 2. Check for priority annotations
        annotated_main = self._find_annotated_main(potential_entrypoints)
        if annotated_main:
            if isinstance(annotated_main, str):
                # _find_annotated_main returns a single choice if exactly one is annotated
                return annotated_main
            else:
                # _find_annotated_main returned multiple candidates
                candidates_for_hierarchy_check = annotated_main
        # If _find_annotated_main returned None or list, it means either:
        # a) No candidates were annotated.
        # b) Multiple candidates were annotated (warning already logged).
        # c) An error occurred fetching annotations.
        # In cases (a) or (b), we proceed to check package hierarchy.
        # If multiple were annotated, we will now apply hierarchy check *only* to those.

        # Refine the list if multiple were annotated (check requires re-calling AppModel, maybe optimize later)

        # 3. Fallback: Package Hierarchy
        self.logger.debug(f"Applying package hierarchy fallback to candidates: {candidates_for_hierarchy_check}.")
        min_depth = float('inf')
        best_candidates_by_depth = []

        for class_name in candidates_for_hierarchy_check:
            depth = self._get_package_depth(class_name)
            self.logger.debug(f"Class: {class_name}, Depth: {depth}")
            if depth < min_depth:
                min_depth = depth
                best_candidates_by_depth = [class_name]
            elif depth == min_depth:
                best_candidates_by_depth.append(class_name)

        if len(best_candidates_by_depth) == 1:
            selected = best_candidates_by_depth[0]
            self.logger.info(f"Selected entrypoint '{selected}' based on shallowest package depth ({min_depth}).")
            return selected
        else:
            # Tie in package depth, use alphabetical order as tie-breaker
            best_candidates_by_depth.sort()
            selected = best_candidates_by_depth[0]
            self.logger.warning(f"Multiple classes found at shallowest package depth ({min_depth}): "
                                f"{best_candidates_by_depth}. Selecting first alphabetically: '{selected}'.")
            return selected

    def find_entrypoint(self) -> Optional[str]:
        """
        Finds the single most likely Java entrypoint class name using the AppModel.

        Returns:
            The fully qualified name of the most likely entrypoint class,
            or None if no suitable entrypoint is found or if ambiguity
            cannot be resolved by the implemented strategies.
        """
        potential_entrypoints_classes = set()
        self.logger.info(
            f"Starting search for potential Java entrypoint methods using AppModel for '{self.app_model.app_name}'...")

        for method in self.app_model.get_local_methods():
            if self._is_main_method_signature(method):
                class_name = self.app_model.get_method_parent(method)
                self.logger.debug(f"Found potential main method signature in class: {class_name}")
                potential_entrypoints_classes.add(class_name)

        candidates = sorted(list(potential_entrypoints_classes))  # Sort for deterministic behavior

        if not candidates:
            self.logger.info("No classes with a valid main method signature found.")
            return None
        elif len(candidates) == 1:
            selected = candidates[0]
            self.logger.info(f"Found unique potential entrypoint: {selected}")
            return selected
        else:
            # More than one candidate, try to select the best one
            return self._select_best_entrypoint(candidates)
