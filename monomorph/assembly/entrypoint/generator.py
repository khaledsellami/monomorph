from importlib import resources
from pathlib import Path

from ...helpers import HelperManager


class EntryPointGenerator:
    """
    This class is responsible for generating the entry point for the monomorph microservices.
    """
    TEMPLATES_DIR: Path = resources.files("monomorph.resources").joinpath("templates")
    GRPC_SERVER_TEMPLATE: str = HelperManager.GRPC_SERVER_MAIN_TEMPLATE
    COMBINED_MAIN_TEMPLATE: str = HelperManager.COMBINED_MAIN_TEMPLATE
    DEFAULT_LEASE_DURATION: int = 60000
    LEASE_DURATION_ENV_VAR_NAME: str = "MM_LEASE_DURATION"

    def __init__(self, helper_manager: HelperManager):
        self.helper_manager = helper_manager

    def generate_grpc_entry_point(self, ms_name: str, package_name: str, class_name: str, services: list[dict],
                                  port: int = 50051, env_var_name: str = "MR_GRPC_PORT") -> str:
        """
        Generate the entry point server
        """
        context = {
            "ms_name": ms_name,
            "package_name": package_name,
            "server_class_name": class_name,
            "port": port,
            "port_env_var_name": env_var_name,
            "service_impl_fqns": services,
            "default_lease_duration": self.DEFAULT_LEASE_DURATION,
            "lease_duration_env_var_name": self.LEASE_DURATION_ENV_VAR_NAME,
        }
        output_lines = self.helper_manager.render_helper(self.GRPC_SERVER_TEMPLATE, context).splitlines()
        return "\n".join([line for line in output_lines[:2] if line.strip() if line.strip()] + output_lines[2:])

    def generate_combined_entry_point(self, class_name: str, package_name: str, old_main: str, grpc_main: str) -> str:
        """
        Generate the entry point server
        """
        context = {
            "package_name": package_name,
            "combined_main_class_name": class_name,
            "old_main_fqn": old_main,
            "old_main_class_name": old_main.split(".")[-1],
            "grpc_server_fqn": grpc_main if ".".join(grpc_main.split(".")[:-1]) != package_name else None,
            "grpc_server_class_name": grpc_main.split(".")[-1],
        }
        output_lines = self.helper_manager.render_helper(self.COMBINED_MAIN_TEMPLATE, context).splitlines()
        return "\n".join([line for line in output_lines[:2] if line.strip() if line.strip()] + output_lines[2:])
