from typing import Optional, Any
from abc import ABC, abstractmethod

from .models import NewFile


class Refact(ABC):
    @abstractmethod
    def refactor_class(self, class_name: str, method_names: list[str], microservice_uid: str,
                       client_microservices: set[str], **kwargs) -> (
            tuple)[NewFile, NewFile, dict[str, NewFile], Optional[NewFile], Any]:
        """
        Refactor a class by generating the new server, client and proto files that represent the new remote API
        corresponding to the local API.

        :param class_name: The fully qualified name of the class to be refactored
        :param method_names: The list of method names to be included in the refactored class
        :param microservice_uid: The unique identifier of the microservice the class belongs to
        :param client_microservices: The set of client microservices that will use the refactored class
        :return:
            - The new proto file
            - The new server file
            - The new client file
            - The mapper class file
            - The tracing details (if any)
        """
        raise NotImplementedError()