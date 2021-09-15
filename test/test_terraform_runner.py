from typing import List, Optional, Set
from unittest import TestCase

from src import terraform_runner
from src.terraform_runner import TerraformParameterSet


class Test(TestCase):
    def test_filter_changed_files_to_relevant_folders(self):
        sample_changed_folders: List[str] = ["a/b/c", "./a/b", "b/c", "a", "b/a/c"]
        output: List[str] = terraform_runner.filter_changed_files_to_relevant_folders(sample_changed_folders, ["a"])
        self.assertEqual(output, ["a/b/c", "./a/b", "a"])

    def test_extract_terraform_parameter_sets(self):
        available_parameter_sets: List[TerraformParameterSet] = []
        available_parameter_sets.append(TerraformParameterSet("aws", "prod", "app-database"))
        available_parameter_sets.append(TerraformParameterSet("aws", "dev", "app-database"))

        output: Set[TerraformParameterSet] = terraform_runner.extract_terraform_parameter_sets(
            ["./environments/aws/prod/backend.tfvars",
             "environments/aws/dev/app-database/variables.tfvars", "layers/app-database/main.tf"],
            available_parameter_sets, False)
        # For 3 inputs, we're getting 2 outputs, since the results are de-duplicated
        self.assertCountEqual(output, [
            TerraformParameterSet("aws", "dev", "app-database"),
            TerraformParameterSet("aws", "prod", "app-database")
        ])

    def test_list_all_available_parameter_sets(self):
        base_directory = "resources"
        output: List[TerraformParameterSet] = terraform_runner.list_all_available_parameter_sets(base_directory)
        self.assertEqual(len(output), 2)

    def test_find_suitable_parameter_set_for_input(self):
        available_parameter_sets: List[TerraformParameterSet] = []
        available_parameter_sets.append(TerraformParameterSet("aws", "prod", "app-database"))
        available_parameter_sets.append(TerraformParameterSet("aws", "test", "app-database"))
        output: Optional[TerraformParameterSet] = terraform_runner.find_suitable_parameter_set_for_input(available_parameter_sets, "aws", "test", None)
        self.assertEqual(output, TerraformParameterSet("aws", "test", "app-database"))
