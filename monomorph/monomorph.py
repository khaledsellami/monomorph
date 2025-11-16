import datetime
import os
import logging
import queue
import shutil
import tarfile
import threading
import re
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Optional
import uuid

from .logging.printer import ConsolePrinter
from .llm.langgraph.checkpoints import CheckpointStorage
from .llm.langchain.usage import CallbackContext, GlobalUsageTracker
from .helpers import HelperManager
from .models import Decomposition, UpdatedDecomposition
from .const import ApproachType, RefactoringMethod
from .project import MicroservicesProject
from .microservice import MicroserviceDirectory
from .analysis import AppModel, LocalAnalysis
from .planning.preprocessing import DecompositionPreprocessor
from .planning.proxies import ProxyPlanner, PlannedAPIClass
from .planning.dependencies import DependencyDetector, APIClass
from .decision.models import RefactoringDecision
from .decision.workflow import RefactDecisionWorkflow
from .generation.models import NewFile
from .generation.refact import Refact
from .generation.grpc.id.agent import IDRefactAgent
from .generation.grpc.dto.agent import DTORefactAgent
from .validation.compilation import CompilationRunner
from .validation.correction import CompilationCorrectionWorkflow
from .validation.docker import MicroserviceDocker
from .report import ReportWriter


class MonoMorph:
    analysis_model: AppModel
    updated_decomposition: UpdatedDecomposition
    project: MicroservicesProject
    id_refact: Refact
    dto_refact: Refact

    def __init__(self, app_name: str, source_code_path: str, package_name: str, decomposition: Decomposition,
                 output_path: Optional[str], analysis_path: Optional[str], refact_model: str = "gpt-4o",
                 parsing_model: str = "ministral-3b", decision_model: str = "gpt-4o", correction_model: str = "gpt-4o",
                 fallback_model: str = "gpt-4o", include_tests: bool = True,
                 original_dockerfile_path: Optional[str] = None,
                 id_approach_only: bool = False, restrictive_mode: bool = False, build_tool: str = "maven",
                 llm_response_path: Optional[str] = None, use_multithreading: bool = True,
                 checkpoint_config: Optional[dict] = None, run_id: Optional[str] = None,
                 resume_from: Optional[str] = None):
        """
        Initialize the MonoMorph class.
        :param app_name: The name of the application to be refactored.
        :param source_code_path: The path to the source code of the application.
        :param package_name: The package name of the application.
        :param decomposition: The target decomposition of the application.
        :param output_path: The path to save the refactored output. default is "./data/monomorph-output".
        :param analysis_path: The path to save or load the analysis data. default is "./data/analysis".
        :param refact_model: The LLM model to use for refactoring. default is "gpt-4o".
        :param parsing_model: The LLM model to use for parsing the refactoring LLM responses. default is "ministral-3b".
        :param decision_model: The LLM model to use for making refactoring decisions. default is "gpt-4o".
        :param correction_model: The LLM model to use for correcting compilation errors. default is "gpt-4o".
        :param fallback_model: The LLM model to use as a fallback for refactoring. default is "gpt-4o".
        :param include_tests: Whether to include test files in the refactoring process if not already included.
        :param original_dockerfile_path: The path to the original application's Dockerfile if it exists. default is None.
        :param id_approach_only: Whether to only apply the ID-based approach for refactoring.
        :param restrictive_mode: Whether to apply restrictive selection for class duplication.
        :param build_tool: The build tool to use for the project. default is "maven".
        :param llm_response_path: The path to save the LLM responses. default is None.
        :param use_multithreading: Whether to use multithreading for refactoring. default is True.
        :param checkpoint_config: Configuration for the checkpointing mechanism.
        :param run_id: A unique identifier for the refactoring run. If None, a random UUID will be generated.
        :param resume_from: The path to a previous (identical) run to resume the correction workflow from.
        """
        self.app_name = app_name
        self.source_code_path = source_code_path
        self.package_name = package_name
        self.decomposition = decomposition
        self.refact_model = refact_model
        self.parsing_model = parsing_model
        self.decision_model = decision_model
        self.correction_model = correction_model
        self.fallback_model = fallback_model
        self.original_dockerfile_path = original_dockerfile_path
        self.output_path = output_path or os.path.join(os.getcwd(), "data", "monomorph-output")
        self.analysis_path = analysis_path or os.path.join(os.getcwd(), "data", "analysis")
        self.include_tests = include_tests
        self.restrictive_mode = restrictive_mode
        self.id_approach_only = id_approach_only
        self.build_tool = build_tool
        self.resume_from = resume_from
        self.run_id = str(uuid.uuid4())[:8] if run_id is None else run_id
        self.directory_name = (f"{app_name}-{datetime.datetime.now().strftime('%y%m%d%H%M')}-"
                               f"{self.run_id[:4]}") if self.run_id else app_name
        llm_response_path = llm_response_path or os.path.join(os.getcwd(), "data", "monomorph-llm-responses")
        self.llm_response_path = os.path.join(llm_response_path, self.directory_name)
        self.callback_context = CallbackContext(app_name=self.app_name, exp_id=self.directory_name)
        if checkpoint_config and isinstance(checkpoint_config, dict):
            checkpoint_storage = CheckpointStorage(checkpoint_config.get("path", llm_response_path))
            checkpoint_storage.set_config(self.run_id, checkpoint_config.get("should_load", False),
                                          checkpoint_config.get("should_save", False))
        self.debugging = False
        self.use_multithreading = use_multithreading
        os.makedirs(self.output_path, exist_ok=True)
        os.makedirs(self.analysis_path, exist_ok=True)
        self.helper_manager = HelperManager(self.package_name)
        self.logger = logging.getLogger("monomorph")
        self._init_usage_history(app_name, llm_response_path, run_id)

    def _init_usage_history(self, app_name: str, llm_response_path: str, run_id: Optional[str] = None):
        """
        Initialize the usage history for the refactoring run.
        :param app_name: The name of the application to be refactored.
        :param llm_response_path: The path where the LLM responses are saved.
        :param run_id: The unique identifier for the refactoring run.
        """
        if run_id is not None and os.path.exists(llm_response_path):
            # previous save/load usage history assumed to be in the same path as llm_response_path)
            pattern = f"{app_name}-(.*)-{run_id[:4]}"
            directories = [(d, re.match(pattern, d).group(1)) for d in os.listdir(llm_response_path) if os.path.isdir(os.path.join(llm_response_path, d))
                           and re.match(pattern, d)]
            ## sort directories by datetime and use the most recent directory
            directories.sort(key=lambda d: datetime.datetime.strptime(d[1], '%y%m%d%H%M'))
            if directories:
                most_recent_dir = os.path.join(llm_response_path, directories[-1][0])
                if os.path.exists(os.path.join(most_recent_dir, 'llm_usage.json')):
                    self.logger.debug(f"Loading usage history from {os.path.join(most_recent_dir, 'llm_usage.json')}")
                    GlobalUsageTracker().load_usage_history(os.path.join(most_recent_dir, 'llm_usage.json'))
        else:
            GlobalUsageTracker().reset_usage_history()
        GlobalUsageTracker.set_auto_save(os.path.join(self.llm_response_path, 'llm_usage.json'))

    def analyzing_app(self) -> AppModel:
        """ Generate or load the static analysis data of the app """
        # Load the analysis model
        create_subdirs = self.app_name not in self.analysis_path
        analysis_handler = LocalAnalysis(self.app_name, self.source_code_path, self.analysis_path, create_subdirs=create_subdirs)
        analysis_model = analysis_handler.load()
        return analysis_model

    def refactor(self):
        self.logger.info(f"Starting the refactoring process for {self.app_name} (run_id: {self.run_id})")
        ## Ensure that the validation runner has all the pre-requisites
        prereq_valid = MicroserviceDocker.validate_prerequisites()
        if not prereq_valid:
            raise RuntimeError("Validation prerequisites are not met. Please ensure that the necessary tools are "
                               "installed and configured.")
        ## Load the analysis model
        self.logger.debug("Loading the analysis model")
        self.analysis_model = self.analyzing_app()
        # Pre-process the decomposition
        self.logger.debug("Pre-processing the decomposition")
        preprocessor = DecompositionPreprocessor(self.decomposition, self.analysis_model, self.include_tests,
                                                 self.restrictive_mode, self.source_code_path)
        self.updated_decomposition = preprocessor.update_decomposition()
        # Detect dependencies and inter-service communication
        self.logger.debug("Detecting dependencies and inter-service communication")
        dependency_detector = DependencyDetector(self.updated_decomposition, self.analysis_model)
        isci, ismi, oisci = dependency_detector.find_new_apis_partition()
        api_classes_per_ms = dict(dependency_detector.to_api_classes(ismi, oisci))
        # Decide which classes to apply the ID-method on and which to create DTOs from
        reasoning_dict: dict[str, RefactoringMethod]
        if self.id_approach_only:
            self.logger.debug("ID-approach only selected. All classes will be refactored using the ID-method.")
            reasoning = "Defaulting to ID-based refactoring due to 'id_approach_only'=True"
            reasoning_dict = {c.name: RefactoringMethod(decision=ApproachType.ID_BASED, reasoning=reasoning)
                              for m, api_classes in api_classes_per_ms.items() for c in api_classes}
        else:
            self.logger.debug("Starting the ID or DTO decision process")
            reasoning_dict = self.decide_approach(api_classes_per_ms)
        # Prepare the helper and template manager
        self.logger.debug("Preparing the helper and template manager")
        # Start the new api class planning by finding nested classes (within methods APIs or the DTO fields)
        self.logger.debug("Searching for nested classes")
        proxy_planner = ProxyPlanner(self.analysis_model, self.helper_manager)
        api_classes = {c.name: c for ms in api_classes_per_ms.values() for c in ms}
        planned_api_classes = proxy_planner.find_and_name_all_api_classes(reasoning_dict, api_classes)
        # Sort the api classes by microservice and approach
        id_classes_per_ms, dto_classes_per_ms = self.sort_by_ms_and_approach(planned_api_classes)
        # Prepare the refactoring classes
        self.logger.debug("Initializing the refactoring classes")
        ## ID based refactoring class
        self.logger.debug("Initializing the IDRefact class")
        model_kwargs = {"gen_model": self.refact_model, "parsing_model": self.parsing_model}
        self.id_refact = IDRefactAgent(self.analysis_model, self.helper_manager, planned_api_classes,
                                       id_only=self.id_approach_only, models_kwargs=model_kwargs,
                                       callback_context=self.callback_context)
        ## DTO based refactoring class
        self.logger.debug("Initializing the DTORefact class")
        self.dto_refact = DTORefactAgent(self.analysis_model, self.helper_manager, planned_api_classes,
                                         id_only=self.id_approach_only, models_kwargs=model_kwargs,
                                         callback_context=self.callback_context)
        # Start the project handler
        self.logger.debug("Initializing the output microservices project")
        self.project = MicroservicesProject(self.app_name, self.package_name, self.updated_decomposition,
                                            self.source_code_path, self.output_path, self.helper_manager,
                                            directory_name=self.directory_name, build_tool=self.build_tool)
        # Refactor all api classes
        self.logger.debug("Refactoring the classes")
        self.logger.info("Starting ID-based refactoring")
        self.logger.info(f"ID-based classes: {len([c for ms in id_classes_per_ms.values() for c in ms])}")
        self.refactor_classes(id_classes_per_ms, all_api_classes=planned_api_classes, is_dto=False)
        if self.id_approach_only:
            self.logger.info("Skipping DTO-based refactoring.")
        else:
            self.logger.info("Starting DTO-based refactoring")
            self.logger.info(f"DTO-based classes: {len([c for ms in dto_classes_per_ms.values() for c in ms])}")
            self.refactor_classes(dto_classes_per_ms, all_api_classes=planned_api_classes, is_dto=True)
        # Save the llm usage history
        self.logger.debug("Saving the LLM usage history")
        GlobalUsageTracker().save_usage_history(os.path.join(self.llm_response_path, 'llm_usage.json'))
        # Apply any import changes that were planned during the refactoring
        self.logger.debug("Applying import changes")
        self.project.apply_import_changes()
        # Create the entry point servers for each microservice
        self.project.create_entrypoints(self.analysis_model)
        # Save tracing details for debugging purposes
        self.logger.debug("Saving tracing details for debugging purposes")
        self.project.save_tracing_details(self.llm_response_path)
        # Validate the project syntax and structure
        self.logger.debug("Validating the project syntax and structure")
        self.validate_project()
        # Build the new configuration files
        self.logger.debug("Building the new configuration files")
        self.build_config_files()
        # Build the new dockerfile and docker-compose files
        self.logger.debug("Building the new docker files")
        self.build_docker_files()
        # Generate the README file
        self.logger.debug("Generating the README file")
        self.generate_readme(planned_api_classes)
        self.logger.info(f"Refactoring process (run_id={self.run_id}) completed successfully")

    def decide_approach(self, api_classes_per_ms: dict[str, list[APIClass]]) -> dict[str, RefactoringMethod]:
        """
        Decide which classes to apply the ID-method on and which to create DTOs from.
        :param api_classes_per_ms: A dictionary containing the API classes per microservice.
        :return: A tuple containing two dictionaries: one for ID-method classes and
                    one for DTO classes along with the recommended fields.
        """
        id_classes = list()
        dto_classes = list()
        dto_only_classes = list()
        reasoning_per_class = dict()
        failures = 0
        self.logger.debug("Initializing the decision workflow")
        self.logger.debug(f"Deciding the approach for "
                          f"{len([c for apis in api_classes_per_ms.values() for c in apis])} classes")
        relevant_classes = set([c for p in self.updated_decomposition.partitions for c in p.classes] +
                               [c[0] for p in self.updated_decomposition.partitions for c in p.duplicated_classes])
        decision_workflow = RefactDecisionWorkflow(self.app_name, self.updated_decomposition, self.analysis_model,
                                                   self.decision_model, self.parsing_model, block_paid_api=False,
                                                   relevant_classes=relevant_classes,
                                                   callback_context=self.callback_context)
        for ms_name, api_classes in api_classes_per_ms.items():
            self.logger.debug(f"Processing microservice {ms_name} with {len(api_classes)} API classes")
            for api_class in api_classes:
                self.logger.debug(f"API Class: {api_class.name}")
        for ms_name, api_classes in api_classes_per_ms.items():
            for api_class in api_classes:
                class_name = api_class.name
                # Check if the class is a DTO-only class
                if len(api_class.methods) == 0:
                    # Classes that do not expose any methods are automatically considered DTO-only classes
                    self.logger.debug(f"Class {class_name} is a DTO-only class. Skipping decision workflow.")
                    dto_only_classes.append(api_class)
                    reasoning_template = ("Class {c1} was used within the fields/inputs/outputs of class {c2} "
                                          "from microservice {m}.")
                    reasoning = "\n".join([reasoning_template.format(c1=class_name, c2=c[0], m=c[1])
                                           for c in api_class.other_interactions])
                    refact_method = RefactoringMethod(decision=ApproachType.DTO_ONLY, reasoning=reasoning)
                    reasoning_per_class[class_name] = refact_method
                    continue
                self.logger.debug(f"Invoking the decision workflow for class {class_name} in microservice {ms_name}")
                if not self.debugging:
                    decision, conversation_log = decision_workflow.run(class_name, ms_name)
                    # Save the conversation log for debugging purposes
                    self._save_decision_logs(class_name, conversation_log)
                else:
                    decision, _ = decision_workflow._simulate_run(class_name, ms_name)  # Used only for testing
                if decision and isinstance(decision, RefactoringDecision):
                    refact_method = RefactoringMethod.from_decision(decision)
                    if refact_method.decision == ApproachType.DTO_BASED:
                        self.logger.debug(f"Decision workflow returned DTO-based decision for class {class_name}")
                        api_class.fields = refact_method.suggested_dto_fields
                        dto_classes.append(api_class)
                    else:
                        self.logger.debug(f"Decision workflow returned ID-based decision for class {class_name}")
                        id_classes.append(api_class)
                    reasoning_per_class[class_name] = refact_method
                else:
                    reasoning = (f"Decision workflow returned an invalid decision for class {class_name}. "
                                 f"Defaulting to ID-Based.")
                    self.logger.warning(reasoning)
                    refact_method = RefactoringMethod(decision=ApproachType.ID_BASED, reasoning=reasoning)
                    id_classes.append(api_class)
                    reasoning_per_class[class_name] = refact_method
                    failures += 1
        self.logger.debug("Decision workflow completed")
        self.logger.debug(f"ID-based classes: {len(id_classes)}")
        self.logger.debug(f"DTO-based classes: {len(dto_classes)}")
        self.logger.debug(f"DTO-only classes: {len(dto_only_classes)}")
        self.logger.debug(f"Failures: {failures}")
        return reasoning_per_class

    def _save_decision_logs(self, class_name: str, conversation_log: list[str]):
        llm_response_path = self.llm_response_path or os.path.join("llm_responses", "output-responses")
        log_path = os.path.join(llm_response_path,
                                self.package_name.replace(".",os.sep), "decision_logs",
                                f"{class_name}.md")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            self.logger.debug(f"Saving decision log in {log_path}")
            f.write("\n\n".join(conversation_log))

    def _assign_microservice(self, api_class: PlannedAPIClass) -> str:
        ms_name = api_class.microservice
        if not ms_name:
            # find matching microservice
            for partition in self.updated_decomposition.partitions:
                if api_class.name in partition.classes:
                    ms_name = partition.name
                    api_class.microservice = ms_name
                    break
            else:
                raise ValueError(f"Could not find a matching microservice for class {api_class.name}")
        return ms_name

    def _assign_client_microservice(self, api_class: PlannedAPIClass, api_classes: dict[str, PlannedAPIClass]) -> set[str]:
        if api_class.client_microservices is not None:
            return api_class.client_microservices
        invoking_classes = self._get_invoking_classes(api_class, api_classes, include_same=True)
        clients = set(invoking_classes.keys())
        for ms_name, classes in invoking_classes.items():
            for c in classes:
                if c == api_class.name:
                    # Should be avoided in _get_invoking_classes but just in case
                    continue
                if c in api_classes:
                    c_clients = api_classes[c].client_microservices
                    if c_clients is None:
                        c_clients = self._assign_client_microservice(api_classes[c], api_classes)
                    clients.update(c_clients)
        api_class.client_microservices = {ms for ms in clients if ms != api_class.microservice}
        return clients

    def sort_by_ms_and_approach(self, api_classes: dict[str, PlannedAPIClass]) -> (
            tuple)[dict[str, list[PlannedAPIClass]], dict[str, list[PlannedAPIClass]]]:
        id_classes_per_ms = defaultdict(list)
        dto_classes_per_ms = defaultdict(list)
        for class_name, planned_api_class in api_classes.items():
            ms_name = self._assign_microservice(planned_api_class)
            # Assign client microservices
            self._assign_client_microservice(planned_api_class, api_classes)
            if planned_api_class.decision != ApproachType.ID_BASED:
                dto_classes_per_ms[ms_name].append(planned_api_class)
            else:
                id_classes_per_ms[ms_name].append(planned_api_class)
        return dict(id_classes_per_ms), dict(dto_classes_per_ms)
    
    def refactor_classes(self, api_classes_per_ms: dict[str, list[PlannedAPIClass]],
                         all_api_classes: dict[str, PlannedAPIClass], is_dto: bool = False):
        """
        The public method for the refactoring loop for all the classes in the microservices.

        :param api_classes_per_ms: A dictionary containing the API classes per microservice.
        :param all_api_classes: A dictionary containing all the API classes in the application.
        :param is_dto: A boolean indicating whether to use DTO-based or ID-based refactoring.
        """
        if self.use_multithreading:
            self._refactor_classes_mt(api_classes_per_ms, all_api_classes, is_dto)
        else:
            self._refactor_classes_sg(api_classes_per_ms, all_api_classes, is_dto)

    def _refactor_classes_sg(self, api_classes_per_ms: dict[str, list[PlannedAPIClass]],
                             all_api_classes: dict[str, PlannedAPIClass], is_dto: bool = False):
        """
        The refactoring loop for all the classes in the microservices. Single-threaded version.

        :param api_classes_per_ms: A dictionary containing the API classes per microservice.
        :param is_dto: A boolean indicating whether to use DTO-based or ID-based refactoring.
        """
        # Select the refactoring method based on the is_dto flag
        refact_class = self.dto_refact if is_dto else self.id_refact
        total_classes = sum(len(classes) for classes in api_classes_per_ms.values())
        refactored_classes = 0
        for ms_name in api_classes_per_ms:
            ## Iterate over api classes in the microservice
            ms_uid = self.project.to_uid(ms_name)
            self.logger.debug(f"Refactoring classes in microservice {ms_uid}")
            for api_class in api_classes_per_ms[ms_name]:
                fields = api_class.fields
                self.logger.debug(f"Refactoring class {api_class.name}")
                ### Load class details
                class_name = api_class.name
                method_names = list(api_class.methods)
                # client_microservices = set(self._get_invoking_classes(api_class, refact_class.api_classes).keys())
                client_microservices = api_class.client_microservices
                ### Refactor the class
                proto_file, server_file, client_files, mapper_file, tracing_details = refact_class.refactor_class(
                    class_name, method_names, ms_uid, fields=fields, client_microservices=client_microservices)
                self.logger.debug(f"Refactoring was successful. Applying changes to the project")
                self.apply_new_classes(api_class, proto_file, server_file, client_files, mapper_file, ms_uid,
                                       all_api_classes, tracing_details, is_dto=is_dto)
                refactored_classes += 1
                self.logger.info(f"Refactored {refactored_classes}/{total_classes} classes")

    def _refactor_classes_mt(self, api_classes_per_ms: dict[str, list[PlannedAPIClass]],
                             all_api_classes: dict[str, PlannedAPIClass], is_dto: bool = False):
        """
        The refactoring loop for all the classes in the microservices. Multithreaded version.

        :param api_classes_per_ms: A dictionary containing the API classes per microservice.
        :param is_dto: A boolean indicating whether to use DTO-based or ID-based refactoring.
        """
        total_classes = sum(len(classes) for classes in api_classes_per_ms.values())
        # Create a lock for thread-safe operations
        refactor_lock = threading.Lock()
        refactored_classes = 0
        applied_classes = 0
        # Queue to store results from refactoring operations
        results_queue = queue.Queue()
        # Select the refactoring method based on the is_dto flag
        refact_class = self.dto_refact if is_dto else self.id_refact

        def refactor_class_task(class_name: str, method_names: list[str], ms_uid: str,
                                fields: Optional[list[str]] = None, client_microservices: Optional[set[str]] = None):
            """Worker function for the thread pool"""
            nonlocal refactored_classes, total_classes
            assert client_microservices is not None
            # Refactor the class
            proto_file, server_file, client_files, mapper_file, tracing_details = refact_class.refactor_class(
                class_name, method_names, ms_uid, fields=fields, client_microservices=client_microservices)
            with refactor_lock:
                refactored_classes += 1
                logger = logging.getLogger("monomorph")
                logger.info(f"Refactoring was successful for {class_name} ({refactored_classes}/{total_classes})")
            # Enqueue the results with needed context to apply changes
            results_queue.put((class_name, proto_file, server_file, client_files, mapper_file, tracing_details))

        for ms_name in api_classes_per_ms:
            tasks = []
            ## Iterate over api classes in the microservice
            ms_uid = self.project.to_uid(ms_name)
            self.logger.debug(f"Preparing to refactor classes in microservice {ms_uid}")
            for api_class in api_classes_per_ms[ms_name]:
                fields = api_class.fields
                ### Load class details
                class_name = api_class.name
                method_names = list(api_class.methods)
                # client_microservices = set(self._get_invoking_classes(api_class, refact_class.api_classes).keys())
                client_microservices = api_class.client_microservices
                tasks.append((class_name, method_names, ms_uid, fields, client_microservices))
            # Start the thread pool executor and submit tasks
            self.logger.debug(f"Starting refactoring tasks for microservice {ms_uid}")
            with ThreadPoolExecutor(max_workers=5) as executor:
                # Submit all tasks to the executor
                futures = [executor.submit(refactor_class_task, class_name, method_names, ms_uid, fields, c_ms)
                           for class_name, method_names, ms_uid, fields, c_ms in tasks]
                self.logger.debug(f"Waiting for refactoring tasks to complete for microservice {ms_uid}")
                # Wait for all futures to complete
                for future in futures:
                    try:
                        future.result()  # This will raise any exceptions that occurred in the thread
                    except Exception as e:
                        self.logger.error(f"Error during refactoring: {str(e)}")
                        raise e
            # Process the results from the queue
            self.logger.debug(f"Applying changes for microservice {ms_uid}")
            results_map = {class_name: (proto_file, server_file, client_files, mapper_file, tracing_details)
                           for class_name, proto_file, server_file, client_files, mapper_file, tracing_details
                           in results_queue.queue}
            results_queue.queue.clear()  # Clear the queue for the next microservice
            if len(results_map) != len(tasks):
                results_classes = set(results_map.keys())
                tasks_classes = set(task[0] for task in tasks)
                mismatch_classes = results_classes.symmetric_difference(tasks_classes)
                self.logger.error(f"Mismatch in number of classes refactored: {len(results_map)} vs {len(tasks)}")
                if mismatch_classes:
                    self.logger.error(f"Classes mismatch: {mismatch_classes}")
                else:
                    self.logger.error(f"Potential duplicate classes refactored: {[task[0] for task in tasks]}")
                raise RuntimeError("Mismatch in number of classes refactored")
            for api_class in api_classes_per_ms[ms_name]:
                class_name = api_class.name
                proto_file, server_file, client_files, mapper_file, tracing_details = results_map[class_name]
                self.apply_new_classes(api_class, proto_file, server_file, client_files, mapper_file, ms_uid,
                                       all_api_classes, tracing_details, is_dto=is_dto)
                applied_classes += 1
                self.logger.info(f"Applied changes to {applied_classes}/{total_classes} classes")

    def _get_invoking_classes(self, api_class: PlannedAPIClass, api_classes: dict[str, PlannedAPIClass],
                              use_uid: bool = False, include_same: bool = False) -> dict[str, set[str]]:
        """
        Get the invoking classes for a given API class.

        :param api_class: The API class to get the invoking classes for.
        :param api_classes: A dictionary containing the API classes.
        :param use_uid: Whether to use UID for the microservice name.
        :return: A dictionary containing the invoking classes.
        """
        def add_class_to_dict_if_valid(class_name: str, other_ms_name: str, log: bool = False):
            if (include_same and class_name != api_class.name) or other_ms_name != api_class.microservice:
                if use_uid:
                    other_ms_name = self.project.to_uid(other_ms_name)
                invoking_classes[other_ms_name].add(class_name)
                if log:
                    self.logger.debug(f"Added {class_name} to invoking classes of {api_class.name} in {other_ms_name}")

        invoking_classes = defaultdict(set)
        for method_name, other_ms_name in api_class.interactions:
            add_class_to_dict_if_valid(method_name.split("::")[0], other_ms_name)
        for class_name, other_ms_name in api_class.other_interactions:
            add_class_to_dict_if_valid(class_name, other_ms_name, log=True)
        for class_name in api_class.referencing_classes:
            other_ms_name = api_classes[class_name].microservice
            add_class_to_dict_if_valid(class_name, other_ms_name, log=False)
        return dict(invoking_classes)

    def apply_new_classes(self, api_class: PlannedAPIClass, proto_file: NewFile, server_file: Optional[NewFile],
                          client_files: dict[str, NewFile], mapper_file: Optional[NewFile], ms_name: str,
                          api_classes: dict[str, PlannedAPIClass], tracing_details: Optional[dict] = None,
                          is_dto: bool = False):
        """
        Apply the new generated code to the project and update the microservices.

        :param api_class: The API class to be refactored.
        :param proto_file: The generated proto file.
        :param server_file: The generated gRPC server file.
        :param client_files: The list of generated gRPC client file per microservice.
        :param mapper_file: The generated mapper file (only in DTO mode).
        :param ms_name: The name of the microservice.
        :param api_classes: A dictionary containing the API classes.
        :param tracing_details: Optional tracing details for the refactored classes
        :param is_dto: Whether the refactoring is for DTO-based classes.
        """
        # Add maven or gradle grpc dependencies if not already present to the microservice
        self.project.add_dependency(ms_name, mode="server")
        # Add the new proto file and server class to the server microservice
        server_microservice = self.project.microservices[ms_name]
        server_microservice.add_server(server_file, proto_file, api_class.name, mapper_file=mapper_file,
                                       tracing_details=tracing_details)
        # Update invoking microservices and methods
        invoking_classes = self._get_invoking_classes(api_class, api_classes)
        for non_uid_other_ms_name, client_file in client_files.items():
            other_ms_name = self.project.to_uid(non_uid_other_ms_name)
            client_microservice = self.project.microservices[other_ms_name]
            # Add maven or gradle grpc dependencies if not already present to the client microservice
            self.project.add_dependency(other_ms_name, mode="client")
            # Add the new proto file and client class to the microservice
            client_microservice.add_client(client_file, proto_file, api_class.name, tracing_details=tracing_details,
                                           ms_name=other_ms_name, is_dto=is_dto)
            # Redirect the imports of the server class to the client class
            old_class_name = api_class.name
            new_class_name = f"{client_file.content.package_name}.{client_file.content.class_name}"
            classes = invoking_classes.get(non_uid_other_ms_name, set())
            for invoking_class in classes:
                client_microservice.replace_imports(invoking_class, old_class_name, new_class_name)

    def build_config_files(self):
        # TODO: Implement the build_config_files method
        # raise NotImplementedError("Build config files not implemented yet")
        self.logger.error("Build config files not implemented yet")
        pass

    def build_docker_files(self):
        # TODO: Implement the build_docker_files method
        # raise NotImplementedError("Build docker files not implemented yet")
        self.logger.error("Build docker files not implemented yet")
        pass

    def generate_readme(self, api_classes: dict[str, PlannedAPIClass]):
        metadata = {
            "run_id": self.run_id,
            "include_tests": f"All test classes that were not already in the decomposition were "
                             f"{'added to' if self.include_tests else 'excluded from'} the refactoring process",
            "restrictive_mode": f"Restrictive mode was {'enabled' if self.restrictive_mode else 'disabled'}: "
                                f"All Java classes that were not already in the decomposition, were detected "
                                f"by the analysis tool and were not in the source package src/main/java were excluded "
                                f"from the execution",
        }
        writer = ReportWriter(self.project)
        writer.generate_report(api_classes, metadata)

    def validate_project(self):
        """
        Validate the project syntax and structure.
        This method should be implemented to ensure the generated code is valid.
        """
        ## Create the corrected microservices directory to temporarily store the corrected microservices
        corrected_microservices_dir = os.path.join(self.project.project_path, "corrected_microservices")
        os.makedirs(corrected_microservices_dir, exist_ok=True)
        # Validate each microservice
        for ms_name, microservice in self.project.microservices.items():
            # self.logger.debug(f"Validating microservice {ms_name}")
            tar_file = os.path.join(corrected_microservices_dir, microservice.uid, "docker_copy.tar")
            success = self.validate_microservice(microservice, tar_file)
            if success:
                self.logger.info(f"Microservice {microservice.name} compiled successfully.")
            self.replace_refactored_with_corrected(microservice, tar_file)
        # Remove the corrected microservices directory if it is empty
        try:
            os.rmdir(corrected_microservices_dir)
        except OSError as e:
            self.logger.error(f"Failed to remove {corrected_microservices_dir}: {e}")

    def replace_refactored_with_corrected(self, microservice: MicroserviceDirectory, tar_file: str):
        ## Create debugging directory to save the original microservice backup in
        debugging_dir = os.path.join(self.project.project_path, "debugging")
        os.makedirs(debugging_dir, exist_ok=True)
        # Decompress the tar file to the microservice directory and move the original to the debugging directory
        if os.path.exists(tar_file):
            # Move the original microservice files to the debugging directory
            refactoring_dir = microservice.directory_path
            ms_debugging_dir = os.path.join(debugging_dir, microservice.uid)
            shutil.move(refactoring_dir, ms_debugging_dir)
            self.logger.debug(f"Moved original microservice files to {ms_debugging_dir}")
            # Decompress the tar file to the microservice directory
            self.logger.debug(f"Decompressing the tar file {tar_file} to {microservice.directory_path}")
            transit_dir = os.path.dirname(tar_file)
            with tarfile.open(tar_file, "r") as tar:
                tar.extractall(path=transit_dir)
            # Move the decompressed files to the microservice directory
            self.logger.debug(f"Decompressed the tar file to {microservice.directory_path}")
            decompressed_files = os.path.join(transit_dir, "app")
            shutil.move(decompressed_files, refactoring_dir)
            self.logger.debug(f"Moved decompressed files to {refactoring_dir}")
            # Remove the tar file
            self.logger.debug(f"Removing the tar file {tar_file}")
            os.remove(tar_file)
            # Remove its parent directory if it is empty
            try:
                os.rmdir(transit_dir)
            except OSError as e:
                self.logger.error(f"Failed to remove {transit_dir}: {e}")
        else:
            self.logger.warning(f"Tar file {tar_file} does not exist. Keeping the original microservice files ")

    def validate_microservice(self, microservice: MicroserviceDirectory, tar_file: str) -> bool:
        self.logger.debug(f"Validating microservice {microservice.name}")
        # Create the microservice's docker handler
        ms_docker = MicroserviceDocker(self.app_name, microservice, self.original_dockerfile_path,
                                       build_system=self.build_tool, persistent_container=True,
                                       resume_from=self.resume_from)
        try:
            # Compile the microservice
            compilation_handler = CompilationRunner(ms_docker, self.build_tool, False, False)
            success, logs, error_block_details = compilation_handler.compile_and_parse(False, True)
            error_block, start_line, end_line = error_block_details
            if success:
                self.logger.info(f"Microservice {microservice.name} compiled successfully at first try.")
                return success
            # Parse the logs to find the errors
            # log_details = {
            #     "logs": logs,
            #     "error_logs": error_block,
            #     "start_line": start_line,
            #     "end_line": end_line,
            # }
            # # Invoke the log analysis agent
            # relevant_classes = set([c for p in self.updated_decomposition.partitions for c in p.classes] +
            #                        [c[0] for p in self.updated_decomposition.partitions for c in p.duplicated_classes])
            # log_analysis_agent = CompilationAnalysisWorkflow(self.package_name, microservice, self.helper_manager,
            #                                                  log_details, self.analysis_model, self.decision_model,
            #                                                  self.parsing_model, block_paid_api=False,
            #                                                  relevant_classes=relevant_classes,
            #                                                  callback_context=self.callback_context)
            # self.logger.debug(f"Analyzing compilation logs for microservice {microservice.name}")
            # analysis_report, conversation_log = log_analysis_agent.run()
            # Start the correction workflow
            self.logger.debug(f"Starting the compilation correction workflow for microservice {microservice.name}")
            if self.debugging:
                ConsolePrinter.set_logging_mode("printer")
            correction_agent = CompilationCorrectionWorkflow(self.package_name, microservice, ms_docker, compilation_handler,
                                                             self.helper_manager, self.correction_model, self.decision_model,
                                                             fallback_model=self.fallback_model,
                                                             block_paid_api=False, callback_context=self.callback_context,
                                                             should_stream=False, verbosity=1)

            self.logger.info(f"Invoking compilation correction workflow for microservice {microservice.name}")
            skip_standard_run = True
            if not skip_standard_run:
                results = correction_agent.run()
                if self.debugging:
                    ConsolePrinter.set_logging_mode("logger")
                import pickle
                conversation_log_path = os.path.join(self.llm_response_path, microservice.name,
                                                     "compilation_correction_conversation_log.pkl")
                os.makedirs(os.path.dirname(conversation_log_path), exist_ok=True)
                with open(conversation_log_path, "wb") as f:
                    pickle.dump(results[1:], f)
                # Copy the corrected version of the microservice to the output path
                os.makedirs(os.path.dirname(tar_file), exist_ok=True)
            # ms_docker.copy_from_container("/app", tar_file)  # Copy the corrected microservice files
            # Try to compile with tests now
            self.logger.info(f"Invoking compilation (with tests) correction workflow for "
                             f"microservice {microservice.name}")
            results = correction_agent.run(with_tests=True)
            test_conversation_log_path = os.path.join(self.llm_response_path, microservice.name,
                                                 "compilation_correction_conversation_log_with_tests.pkl")
            with open(test_conversation_log_path, "wb") as f:
                pickle.dump(results[1:], f)
            # Replace the corrected microservice files with the new ones
            if os.path.exists(tar_file):
                os.remove(tar_file)
            # ms_docker.copy_from_container("/app", tar_file)
            # Clean up the docker container and image if the correction fails
            # ms_docker.cleanup(True, True)  # Cleanup the container and image
            return results[3]  # Return the success status of the correction
        finally:
            self.logger.info(f"Copying the corrected microservice files to {tar_file}")
            os.makedirs(os.path.dirname(tar_file), exist_ok=True)
            ms_docker.copy_from_container("/app", tar_file)  # Copy the corrected microservice files
            self.logger.info("Cleaning up the docker artifacts")
            ms_docker.cleanup(True, True)


