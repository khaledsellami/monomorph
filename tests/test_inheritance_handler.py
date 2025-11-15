import unittest
import os
import json

from monomorph.modeling.json import JsonModel
from monomorph.models import UpdatedDecomposition
from monomorph.preprocessing.inheritance import InheritanceHandler


class TestInheritanceHandler(unittest.TestCase):
    TEST_DIR = os.path.dirname(os.path.abspath(__file__))

    def _prepare_for_test(self):
        # define the app name
        app_name = "example-project-2"
        analysis_data_path = os.path.join(self.TEST_DIR, "data", "analysis", app_name)
        decomposition_file = os.path.join(self.TEST_DIR, "data", "decompositions", app_name, "manual",
                                          "decompositions.json")
        # load the data
        with open(decomposition_file, "r") as f:
            decomposition_dict = json.load(f)[0]
        with open(os.path.join(analysis_data_path, "typeData.json"), "r") as f:
            type_data = json.load(f)
        with open(os.path.join(analysis_data_path, "methodData.json"), "r") as f:
            method_data = json.load(f)
        # preprocess the data
        type_data["classes"] = [{k: v for k, v in value.items() if k not in ["span"]} for value in type_data["classes"]]
        method_data["methods"] = [{k: v for k, v in value.items() if k not in ["span"]} for value in method_data["methods"]]
        for method in method_data["methods"]:
            for key in ["localInvocations", "invocations"]:
                for invocation in method[key]:
                    if "span" in invocation:
                        invocation.pop("span")
        # initialize the classes
        model = JsonModel(app_name, type_data, method_data)
        decomposition = UpdatedDecomposition.from_monoembed(decomposition_dict, app_name)
        return decomposition, model

    def test_update_decomposition(self):
        decomposition, model = self._prepare_for_test()
        ih = InheritanceHandler(decomposition, model)
        # get the output
        decomposition_out = ih.update_decomposition()
        # expected output
        expected_duplicated_classes = {
            "cluster_1": {('com.example.library.services.BasicService', 'cluster_2')},
            "cluster_3": {('com.example.library.services.BasicService', 'cluster_2')},
            "cluster_4": {('com.example.library.services.BorrowService', 'cluster_2')},
            "cluster_5": {("com.example.library.services.ExtendedBasicService", "cluster_3"),
                          ("com.example.library.services.BasicService", "cluster_2")}
        }
        # verify the output
        for partition in decomposition_out.partitions:
            if partition.name not in expected_duplicated_classes:
                self.assertEqual(len(partition.duplicated_classes), 0,
                                 f"The partition {partition.name} should not have the duplicated classes: "
                                 f"{partition.duplicated_classes}")
            else:
                missing_classes = expected_duplicated_classes[partition.name] - set(partition.duplicated_classes)
                self.assertEqual(len(missing_classes), 0,
                                 f"The partition {partition.name} is missing the duplicated classes: {missing_classes}")
                extra_classes = set(partition.duplicated_classes) - expected_duplicated_classes[partition.name]
                self.assertEqual(len(extra_classes), 0,
                                 f"The partition {partition.name} has extra duplicated classes: {extra_classes}")