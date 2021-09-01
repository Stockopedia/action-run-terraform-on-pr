from typing import List, Optional, Set, Dict, Tuple
from unittest import TestCase

from src import terraform_runner
from src.GithubActionException import GithubActionException
from src.terraform_runner import TerraformParameterSet, extract_aws_credentials


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

    def test_extract_aws_credentials_empty_env_vars(self):
        extracted_aws_credentials: Dict[str, Tuple[str, str, str]] = extract_aws_credentials({})
        self.assertEqual({}, extracted_aws_credentials)

    def test_extract_aws_credentials_correct_env_vars(self):
        correct_env_vars = {
            "AWS__KEY__PROD": "test-key",
            "AWS__SECRET__PROD": "test-secret",
            "AWS__REGION__PROD": "test-region-1",
            "AWS__KEY__DEV": "test-key2",
            "AWS__SECRET__DEV": "test-secret2",
            "AWS__REGION__DEV": "test-region-1",
        }
        extracted_aws_credentials: Dict[str, Tuple[str, str, str]] = extract_aws_credentials(correct_env_vars)
        expected_aws_credentials = {
            "PROD": ("test-key", "test-secret", "test-region-1"),
            "DEV": ("test-key2", "test-secret2", "test-region-1")
        }
        self.assertEqual(expected_aws_credentials, extracted_aws_credentials)

    def test_extract_aws_credentials_missing_env_vars(self):
        env_vars_missing_secret = {
            "AWS__KEY__PROD": "test-key",
            "AWS__REGION__PROD": "test-region-1"
        }
        self.assertRaises(GithubActionException, extract_aws_credentials, env_vars_missing_secret)

    def test_extract_aws_credentials_missing_region_env_vars(self):
        env_vars_missing_region = {
            "AWS__KEY__PROD": "test-key",
            "AWS__SECRET__PROD": "test-secret",
            "AWS__REGION__DEV": "test-region-1"
        }
        self.assertRaises(GithubActionException, extract_aws_credentials, env_vars_missing_region)
