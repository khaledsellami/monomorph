from datetime import datetime
import json
import re

import numpy as np


class Partition:
    def __init__(self, name: str, classes: list[str]):
        self.name = name
        self.classes = classes

    def __str__(self):
        return f"Partition {self.name} with {len(self.classes)} classes"


class Decomposition:
    def __init__(self, name: str, app_name: str, partitions: list[dict], language: str = "java", level: str = "class"):
        self.name = name
        self.appName = app_name
        self.language = language
        self.level = level
        self.partitions: list[Partition] = self.to_partitions(partitions)

    @staticmethod
    def to_partitions(partitions: list[dict]) -> list[Partition]:
        return [Partition(**partition) for partition in partitions]

    @staticmethod
    def from_monoembed(decomposition: dict, name: str = None):
        app_name = decomposition["application"]
        if name is None:
            timestamp = datetime.strptime(decomposition["time"], "%Y-%m-%d %H:%M:%S")
            name = f"decomp_{app_name}_{timestamp.strftime('%Y%m%d%H%M')}"
        clusters = decomposition["clusters"]
        names = decomposition["names"]
        granularity = decomposition["granularity"]
        language = "java"
        partitions = [{"name": f"cluster_{i}", "classes": [".".join(names[j].split(".")[2:])
                                                           for j in np.where(clusters == i)[0]]}
                      for i in np.unique(clusters)]
        return Decomposition(name, app_name, partitions, language, granularity)

    @staticmethod
    def from_microrefact(decomposition: dict, app_name: str, granularity: str = "class",
                         language: str = "java"):
        name = decomposition["name"]
        cluster_string = decomposition["clusterString"]
        cluster_string = re.sub(r"(\d+)\w*:", r'"\1":', cluster_string)
        cluster_string = cluster_string.replace("'", '"')
        clusters = json.loads(cluster_string)
        if isinstance(clusters, list):
            clusters = clusters[0]
        assert isinstance(clusters, dict)
        partitions = [{"name": cname, "classes": classes} for cname, classes in clusters.items()]
        return Decomposition(name, app_name, partitions, language, granularity)

    def __str__(self):
        return "\n".join([f"Decomposition {self.name} for {self.appName} with {len(self.partitions)} partitions:"] +
                         [str(partition) for partition in self.partitions])


class UpdatedPartition(Partition):
    def __init__(self, name: str, classes: list[str]):
        super().__init__(name, classes)
        self.duplicated_classes: list[tuple[str, str]] = []
        self.duplication_reasons: dict[tuple[str, str], str] = {}

    def add_duplicated_class(self, class_name: str, original_service: str, reason: str = "unspecified"):
        if not ((class_name, original_service) in self.duplicated_classes or class_name in self.classes):
            self.duplicated_classes.append((class_name, original_service))
            self.duplication_reasons[(class_name, original_service)] = reason

    def extend_duplicated_classes(self, duplicated_classes: list[tuple[str, str, str]]):
        new_duplicates = {(dup[0], dup[1]): dup[2] for dup in duplicated_classes
                          if (dup[0], dup[1]) not in self.duplicated_classes and dup[0] not in self.classes}
        self.duplicated_classes.extend(list(new_duplicates.keys()))
        self.duplication_reasons.update(new_duplicates)

    @staticmethod
    def from_partition(partition: Partition):
        return UpdatedPartition(partition.name, partition.classes)

    def __str__(self):
        return super().__str__() + f" and {len(self.duplicated_classes)} duplicates"


class UpdatedDecomposition(Decomposition):
    def __init__(self, name: str, app_name: str, partitions: list[dict], language: str = "java", level: str = "class"):
        super().__init__(name, app_name, partitions, language, level)
        self.partitions: list[UpdatedPartition] = [UpdatedPartition.from_partition(partition)
                                                   for partition in self.partitions]

    @staticmethod
    def from_decomposition(decomposition: Decomposition):
        ud = UpdatedDecomposition(decomposition.name, decomposition.appName, [],
                                  decomposition.language, decomposition.level)
        ud.partitions = [UpdatedPartition.from_partition(partition) for partition in decomposition.partitions]
        return ud




