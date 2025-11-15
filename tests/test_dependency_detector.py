import unittest
import os
import json

import pandas as pd

from monomorph.modeling.json import JsonModel
from monomorph.models import UpdatedDecomposition
from monomorph.planning.dependencies import DependencyDetector


class TestDependencyDetector(unittest.TestCase):
    TEST_DIR = os.path.dirname(os.path.abspath(__file__))

    def _prepare_for_test(self):
        # define the app name
        app_name = "example-project-1"
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

    def test_find_boundaries(self):
        decomposition, model = self._prepare_for_test()
        dd = DependencyDetector(decomposition, model)
        # get the output
        class_out, method_out = dd.find_boundaries()
        # expected output
        class_matrix = [
            [0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [1, 1, 0, 0, 0],
            [0, 0, 1, 0, 0]]
        class_order = ["Library", "Book", "User", "ReturnService", "NotificationService"]
        class_df = pd.DataFrame(class_matrix, columns=class_order, index=class_order)
        class_df = class_df > 0
        # postprocess the output
        class_out.columns = [c.split(".")[-1] for c in class_out.columns]
        class_out.index = [c.split(".")[-1] for c in class_out.index]
        class_out = class_out.loc[class_order, class_order]
        class_out = class_out > 0
        # verify the output
        self.assertTrue((class_out == class_df).all().all())

    def test_find_new_apis(self):
        decomposition, model = self._prepare_for_test()
        dd = DependencyDetector(decomposition, model)
        # get the output
        class_apis, method_apis, _ = dd.find_new_apis()
        # expected output
        expected_class_apis = {'com.example.library.models.Book',
                               'com.example.library.models.User',
                               'com.example.library.Library'}
        expected_method_apis = ['com.example.library.models.Book::setBorrowed(boolean)',
                                'com.example.library.models.Book::getTitle()',
                                'com.example.library.models.Book::isBorrowed()',
                                'com.example.library.models.User::getName()',
                                'com.example.library.models.User::getId()',
                                'com.example.library.Library::findBookById(java.lang.String)',
                                'com.example.library.Library::findUserById(java.lang.String)']
        # verify the output
        self.assertEqual(set(class_apis), expected_class_apis, "Detected Class APIs are not as expected")
        self.assertEqual(set(method_apis), set(expected_method_apis), "Detected Method APIs are not as expected")

    def test_find_new_dtos(self):
        decomposition, model = self._prepare_for_test()
        dd = DependencyDetector(decomposition, model)
        # get the output
        dtos = dd.find_new_dtos()
        # expected output
        expected_dtos = {'com.example.library.models.User', 'com.example.library.Library'}
        # verify the output
        self.assertEqual(set(dtos), expected_dtos, "Detected DTOs are not as expected")
