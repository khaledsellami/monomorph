from ..analysis.model import AppModel
from ..models import UpdatedDecomposition


class InheritanceHandler:
    """
    This class is responsible for handling the inheritance between classes in the application model by duplicating
    the inherited classes and the extended and implemented interfaces (in the case of Java) into the other services
    that use them.
    """
    def __init__(self, decomposition: UpdatedDecomposition, app_model: AppModel):
        self.decomposition = decomposition
        self.app_model = app_model

    def find_original_service(self, class_name: str) -> str:
        for partition in self.decomposition.partitions:
            if class_name in partition.classes:
                return partition.name

    def get_inheritances(self, class_name: str) -> list[tuple[str, str]]:
        inheritances = []
        for inheritance in self.app_model.get_inheritance(class_name):
            original_service = self.find_original_service(inheritance)
            if original_service is not None:
                inheritances.append((inheritance, original_service))
                inheritances.extend(self.get_inheritances(inheritance))
        return inheritances

    def update_decomposition(self) -> UpdatedDecomposition:
        for partition in self.decomposition.partitions:
            for class_name in partition.classes:
                inheritances = list(set(self.get_inheritances(class_name)))
                inheritances = [(h[0], h[1], "inheritance") for h in inheritances]
                partition.extend_duplicated_classes(inheritances)
        return self.decomposition
