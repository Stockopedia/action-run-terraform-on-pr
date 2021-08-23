import os
import re
from collections import namedtuple
from typing import List, Tuple, Any, Optional, Iterator, Set

from python_terraform import Terraform

RELEVANT_TERRAFORM_FOLDERS: List[str] = ["layers", "environments"]
TerraformParameterSet = namedtuple("TerraformParameterSet", ["provider", "environment", "layer"])


# Sample inputs (actual values replaced by $(placeholder))
# ./environments/$(provider)/$(env)/backend.tfvars
# environments/$(provider)/$(env)/$(layer)/variables.tfvars
# layers/$(layer)/main.tf
def filter_changed_files_to_relevant_folders(changed_files: List[str], relevant_folders: List[str]) -> List[str]:
    relevant_changed_files: List[str] = []
    for file_path in changed_files:
        if relevant_folder_search := re.search(r"^[./]*([\w-]+)/?.*", file_path):
            if relevant_folder_search.group(1) in relevant_folders:
                relevant_changed_files.append(file_path)
    return relevant_changed_files


def extract_terraform_parameter_sets(file_list: List[str], available_parameter_sets: List[TerraformParameterSet]) -> Set[TerraformParameterSet]:
    ignore_non_aws_changes: bool = "INPUT_DISABLE_NON_AWS_CHANGES" in os.environ
    terraform_parameter_sets: Set[TerraformParameterSet] = set()
    for file_path in file_list:
        layer_path_search = re.search(r"^[./]*layers/([\w-]+)/?.+", file_path, re.IGNORECASE)
        environment_with_layer_path_search = re.search(r"^[./]*environments/([\w-]+)/([\w-]+)/([\w-]+)/.+", file_path, re.IGNORECASE)
        environment_without_layer_path_search = re.search(r"^[./]*environments/([\w-]+)/([\w-]+)/[\w]+.tf[\w]*.+", file_path, re.IGNORECASE)

        if layer_path_search:
            terraform_parameter_sets.add(extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, None, None, layer_path_search.group(1)))

        elif environment_with_layer_path_search:
            provider: str = environment_with_layer_path_search.group(1)
            environment: str = environment_with_layer_path_search.group(2)
            layer: str = environment_with_layer_path_search.group(3)
            terraform_parameter_sets.add(extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, provider, environment, layer))

        elif environment_without_layer_path_search:
            provider: str = environment_without_layer_path_search.group(1)
            environment: str = environment_without_layer_path_search.group(2)
            layer: Optional[str] = None
            terraform_parameter_sets.add(extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, provider, environment, layer))

    return terraform_parameter_sets


def extract_parameter_set_for_input(ignore_non_aws_changes: bool, available_parameter_sets: List[TerraformParameterSet], provider: Optional[str], environment: Optional[str], layer: Optional[str]) -> Optional[TerraformParameterSet]:
    # We perform this step in case we only have partial inputs. We'll use that partial input and identify a TerraformParameterSet which matches
    parameter_set_for_given_layer: TerraformParameterSet = find_suitable_parameter_set_for_input(available_parameter_sets=available_parameter_sets, provider=provider, environment=environment, layer=layer)
    # If we need to ignore non-aws changes, only let aws ones through. Otherwise, let all.
    if (ignore_non_aws_changes and parameter_set_for_given_layer.provider.lower() == "aws") or not ignore_non_aws_changes:
        return parameter_set_for_given_layer
    else:
        return None


def list_all_available_parameter_sets(base_directory: str) -> List[TerraformParameterSet]:
    terraform_parameter_sets: List[TerraformParameterSet] = []
    # the output of os.walk is [('pwd', [subfolders], [files in folder])]
    walk_result: Iterator[Tuple[str, List[str], List[str]]] = os.walk(base_directory + "/environments/")
    for entry in walk_result:
        # Ignore any folder that has subfolders. We need the leaf nodes
        if entry[1] != []:
            continue
        current_path = entry[0]
        if result := re.search(r"^%s/environments/([\w-]+)/([\w-]+)/([\w-]+)" % base_directory,
                               current_path, re.IGNORECASE):
            matched_provider: str = result.group(1)
            matched_environment: str = result.group(2)
            matched_layer: str = result.group(3)
            terraform_parameter_sets.append(TerraformParameterSet(matched_provider, matched_environment, matched_layer))
    return terraform_parameter_sets


def find_suitable_parameter_set_for_input(available_parameter_sets: List[TerraformParameterSet], provider: Optional[str], environment: Optional[str], layer: Optional[str]) -> Optional[TerraformParameterSet]:
    # Now we must filter our list for matching parameter sets
    for parameter_set in available_parameter_sets:
        if provider is not None and parameter_set.provider != provider:
            continue
        if environment is not None and parameter_set.environment != environment:
            continue
        if layer is not None and parameter_set.layer != layer:
            continue
        return parameter_set

    return None


def main():
    if 'INPUT_CHANGED_FILE_LIST' not in os.environ:
        raise Exception("Could not find INPUT_CHANGED_FILE_LIST set in the environment variables.")

    # - Take input from https://github.com/Stockopedia/action-get-changed-files
    # Example: [.github/workflows/lint.yaml,.github/workflows/terraform.yaml,layers/rds-data-platform-bcp-db/main.tf]
    changed_files: List[str] = os.getenv("INPUT_CHANGED_FILE_LIST").split(",")
    # Input: base folder of the terraform folder, to lookup all available providers/environments/layers
    base_directory: str = os.getenv("INPUT_BASE_DIRECTORY", default="/app")

    # Filter by whitelist folder, e.g.: layers/*
    relevant_changed_files: List[str] = filter_changed_files_to_relevant_folders(changed_files,
                                                                                 RELEVANT_TERRAFORM_FOLDERS)

    available_parameter_sets: List[TerraformParameterSet] = list_all_available_parameter_sets(base_directory=base_directory)
    # - Build set of (env / provider / layer)
    # - If env['disable-non-aws'] is present, it will not include any non-aws provider
    terraform_parameter_sets: Set[TerraformParameterSet] = extract_terraform_parameter_sets(relevant_changed_files, available_parameter_sets)

    # - For every mix in step 2, run
    # 	terraform -chdir=layers/$(layer) init \
    # 		-backend=true \
    # 		-reconfigure \
    # 		-backend-config=../../environments/$(provider)/$(env)/backend.tfvars \
    # 		-backend-config="key=tf-$(layer).tfstate"
    # 	terraform -chdir=layers/$(layer) plan --var-file=../../environments/$(provider)/$(env)/$(layer)/variables.tfvars
    terraform_plan_output_text: str = ""
    terraform_error_output_text: str = ""
    for parameter_set in terraform_parameter_sets:
        chdir_path = "%s/layers/%s" % (base_directory, parameter_set.layer)
        terraform = Terraform(working_dir=chdir_path)
        tf_layer_specific_tfvars_path: str = "%s/environments/%s/%s/backend.tfvars" % (base_directory, parameter_set.provider, parameter_set.environment)
        tf_layer_specific_key_tfstate_path: str = "key=tf-%s.tfstate" % parameter_set.layer
        init_return: Tuple[Any, str, str] = terraform.init(backend=True, reconfigure=True,
                                                           backend_config=[tf_layer_specific_tfvars_path, tf_layer_specific_key_tfstate_path])
        print(init_return[1])
        terraform_error_output_text += init_return[2] + os.linesep + os.linesep

        tf_plan_var_file_path: str = "%s/environments/%s/%s/%s/variables.tfvars" % (base_directory, parameter_set.provider, parameter_set.environment, parameter_set.layer)
        plan_return: Tuple[Any, str, str] = terraform.plan(var_file=tf_plan_var_file_path)
        print(plan_return[1])
        terraform_plan_output_text += plan_return[1] + os.linesep + os.linesep
        terraform_error_output_text += plan_return[2] + os.linesep + os.linesep

    print(f"::set-output name=terraform_plan_output::{terraform_plan_output_text}")
    print(f"::set-output name=terraform_error_output::{terraform_error_output_text}")


if __name__ == "__main__":
    sample_input: List[str] = [".github/workflows/lint.yaml", ".github/workflows/terraform.yaml",
                               "layers/rds-data-platform-bcp-db/main.tf"]
    main()
