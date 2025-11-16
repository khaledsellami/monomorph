import dataclasses
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, Any, Literal

from langgraph.graph import StateGraph, MessagesState
from langgraph.graph.state import CompiledStateGraph

from .refact import Refact
from .models import NewFile
from ..llm.langchain.usage import CallbackContext
from ..decision.printer import ConsolePrinter


@dataclass
class TracingDetails:
    contract_prompt_response: tuple[str, str] = ("", "")
    client_prompts_responses: dict[str, tuple[str, str]] = None
    server_prompt_response: tuple[str, str] = ("", "")
    mapper_prompt_response: Optional[tuple[str, str]] = None


class RefactState(MessagesState):
    # inputs
    class_name: str
    method_names: list[str]
    microservice_uid: str
    client_microservices: set[str]
    kwargs: dict[str, Any]
    # internal state
    prompts_context: dict[str, Any]
    # outputs
    contract_file: NewFile
    server_file: Optional[NewFile]
    client_files: dict[str, NewFile]
    mapper_file: Optional[NewFile]
    tracing_details: Optional[dict]


class RefactAgent(Refact):
    """
    Refactor a class by generating the new server, client and contract files that represent the new remote API
    corresponding to the local API. Uses a LangGraph agent with LLMs and tool calls to perform the refactoring.
    """
    MAX_WORKERS = 3

    def __init__(self, models_kwargs: dict = None, callback_context: Optional[CallbackContext] = None):
        self.logger = ConsolePrinter.get_printer("monomorph")
        self.models_kwargs = models_kwargs or {}
        self.graph = self.build_graph()
        self.callback_context = callback_context

    def prepare_context(self, refact_type: str, file_type: str, state: RefactState, client_ms: Optional[str] = None) -> (
            Optional)[CallbackContext]:
        """
        Prepare the context for the LLM calls based on the file type and state.
        :param refact_type: The type of refactoring (e.g. "DTO-Based", "ID-Based")
        :param file_type: The type of file being generated (e.g. "server", "client", "contract", "mapper")
        :param state: The current state of the refactoring process
        :param client_ms: The client microservice identifier, if applicable
        """
        if self.callback_context:
            callback_context = dataclasses.replace(self.callback_context)
            callback_context.refact_type = refact_type
            callback_context.file_type = file_type
            callback_context.class_name = state["class_name"]
            callback_context.target_microservice = state["microservice_uid"]
            if client_ms:
                callback_context.target_microservice = client_ms
            return callback_context
        return self.callback_context

    def build_graph(self) -> CompiledStateGraph:
        """
        Build the graph for the refactoring process.
        """
        builder = StateGraph(RefactState)
        # Define the nodes
        builder.add_node("preprocess", self.pre_process)
        builder.add_node("contract", self.generate_contract)
        builder.add_node("server", self.generate_server)
        builder.add_node("clients", self.generate_clients)
        builder.add_node("mapper", self.generate_mapper)
        builder.add_node("postprocess", self.post_process)
        # Define the entry and finish points
        builder.set_entry_point("preprocess")
        builder.set_finish_point("postprocess")
        # Add conditional edges
        builder.add_conditional_edges(
            "mapper",
            self.should_generate_server,
            {
                "yes": "server",
                "no": "postprocess"
            }
        )
        # Add the edges
        builder.add_edge("preprocess", "contract")
        builder.add_edge("contract", "mapper")
        builder.add_edge("contract", "clients")
        # builder.add_edge("mapper", "server")
        builder.add_edge("server", "postprocess")
        builder.add_edge("clients", "postprocess")
        # Compile and return the graph
        return builder.compile()

    def generate_clients(self, state: RefactState) -> dict[str, Any]:
        """
        Generate the client files for the refactoring process.
        """
        self.logger.debug("Generating client files", msg_type="node", highlight=True)
        client_microservices = state.get("client_microservices", set())
        # Run the client generation in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # Submit the client generation jobs
            client_jobs = dict()
            for client_ms in client_microservices:
                client_job = executor.submit(self.generate_client, state, client_ms)
                client_jobs[client_ms] = client_job
            # Wait for the jobs to complete and collect the results
            client_files = dict()
            client_details = dict()
            for client_ms, client_job in client_jobs.items():
                client_output = client_job.result()
                client_file = client_output["client_file"]
                client_files[client_ms] = client_file
                # Store the client prompt and response for tracing
                client_prompt = client_output["client_prompt"]
                client_response = client_output["client_response"]
                client_details[client_ms] = (client_prompt, client_response)
        tracing_details = state.get("tracing_details", {})
        tracing_details["client"] = client_details
        # tracing_details.client_prompts_responses = client_details
        return {"client_files": client_files, "tracing_details": tracing_details}

    def generate_mapper(self, state: RefactState) -> dict[str, Any]:
        """
        Generate the mapper file for the refactoring process.
        """
        self.logger.debug("Skipping Mapper generation for this implementation", msg_type="node")
        # tracing_details = state.get("tracing_details", TracingDetails())
        # tracing_details.mapper_prompt_response = None
        return {"mapper_file": None}

    def post_process(self, state: RefactState) -> dict[str, Any]:
        """
        Node needed to consolidate the output of generate_server and generate_clients
        """
        self.logger.debug(f"Finished processing class {state['class_name']}", msg_type="node", highlight=True)
        return {}

    def should_generate_server(self, state: RefactState) -> Literal["yes", "no"]:
        """
        Determine if the server file should be generated based on whther the class has methods to be exposed.
        """
        method_names = state.get("method_names", [])
        class_name = state.get("class_name")
        choice = "yes" if len(method_names) > 0 else "no"
        log_txt = f"No methods to expose in class {class_name}" if choice == "no" else f"Methods to expose in class {class_name}: {method_names}"
        self.logger.debug(log_txt, msg_type="node", highlight=True)
        return choice

    def refactor_class(self, class_name: str, method_names: list[str], microservice_uid: str,
                       client_microservices: set[str], **kwargs) -> (
            tuple)[NewFile, Optional[NewFile], dict[str, NewFile], Optional[NewFile], Optional[dict]]:
        """
        Refactor a class by generating the new server, client and contract files that represent the new remote API

        :param class_name: The fully qualified name of the class to be refactored
        :param method_names: The list of method names to be included in the refactored class
        :param microservice_uid: The unique identifier of the microservice the class belongs to
        :param client_microservices: The set of client microservices that will use the refactored class
        :param kwargs: Additional arguments for the refactoring process
        :return:
            - The new contract file
            - The new server file
            - The new client files
            - The new optional mapper file
            - The tracing details
        """
        self.logger.debug(f"Refactoring class {class_name}", msg_type="node", highlight=True)
        method_names = list(sorted(method_names))  # Sort method names for prompt consistency
        # Initialize the state
        state = RefactState(
            class_name=class_name,
            method_names=method_names,
            microservice_uid=microservice_uid,
            client_microservices=client_microservices,
            kwargs=kwargs,
            prompts_context={},
            contract_file=None,
            server_file=None,
            client_files={},
            mapper_file=None,
            tracing_details={}
        )
        # Run the graph
        self.logger.debug("Running refactoring graph", msg_type="node", highlight=True)
        output = self.graph.invoke(state)
        # Extract the output files
        contract_file = output.get("contract_file")
        server_file = output.get("server_file", None)
        client_files = output.get("client_files", {})
        mapper_file = output.get("mapper_file", None)
        # Extract the tracing details
        tracing_details = output.get("tracing_details", {})
        # Return the output files
        return contract_file, server_file, client_files, mapper_file, tracing_details

    @abstractmethod
    def pre_process(self, state: RefactState) -> dict[str, Any]:
        """
        Node needed to prepare the state for the refactoring process.
        """
        self.logger.debug(f"Starting processing class {state['class_name']}", msg_type="node", highlight=True)
        raise NotImplementedError("Pre-processing not implemented yet")

    @abstractmethod
    def generate_contract(self, state: RefactState) -> dict[str, Any]:
        """
        Create the contract (e.g. Protobuf file) for the refactoring process.
        """
        self.logger.debug("Generating remote API contract", msg_type="node", highlight=True)
        raise NotImplementedError("Contract generation not implemented yet")

    @abstractmethod
    def generate_server(self, state: RefactState) -> dict[str, Any]:
        """
        Generate the server file for the refactoring process.
        """
        self.logger.debug("Generating server file", msg_type="node", highlight=True)
        raise NotImplementedError("Server generation not implemented yet")

    @abstractmethod
    def generate_client(self, state: RefactState, client_ms: str) -> dict[str, Any]:
        """
        Generate the client file for the refactoring process.
        """
        self.logger.debug("Generating client file", msg_type="node", highlight=True)
        raise NotImplementedError("Client generation not implemented yet")