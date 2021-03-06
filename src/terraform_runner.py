import json
import os
import re
from json import JSONDecodeError
from typing import List, Tuple, Any, Optional, Iterator, Set, Dict, Match

from python_terraform import Terraform

from .aws_credentials_for_environment import AwsCredentialsForEnvironment
from .github_action_exception import GithubActionException
from .terraform_parameter_set import TerraformParameterSet

RELEVANT_TERRAFORM_FOLDERS: List[str] = ["layers", "environments"]
AWS_KEY_REGEX = re.compile(r"^AWS__KEY__(\w+)", re.IGNORECASE)
AWS_SECRET_REGEX = re.compile(r"^AWS__SECRET__(\w+)", re.IGNORECASE)


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


def extract_terraform_parameter_sets(file_list: List[str], available_parameter_sets: List[TerraformParameterSet], ignore_non_aws_changes: bool) -> Set[TerraformParameterSet]:
    terraform_parameter_sets: Set[TerraformParameterSet] = set()
    for file_path in file_list:
        layer_path_search = re.search(r"^[./]*layers/([\w-]+)/?.+", file_path, re.IGNORECASE)
        environment_with_layer_path_search = re.search(r"^[./]*environments/([\w-]+)/([\w-]+)/([\w-]+)/.+", file_path, re.IGNORECASE)
        environment_without_layer_path_search = re.search(r"^[./]*environments/([\w-]+)/([\w-]+)/[\w]+.tf[\w]*.+", file_path, re.IGNORECASE)

        param_set_to_add: Optional[TerraformParameterSet] = None
        provider: Optional[str] = None
        environment: Optional[str] = None
        layer: Optional[str] = None

        if layer_path_search:
            param_set_to_add = extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, None, None, layer_path_search.group(1))

        elif environment_with_layer_path_search:
            provider = environment_with_layer_path_search.group(1)
            environment = environment_with_layer_path_search.group(2)
            layer = environment_with_layer_path_search.group(3)
            param_set_to_add = extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, provider, environment, layer)

        elif environment_without_layer_path_search:
            provider = environment_without_layer_path_search.group(1)
            environment = environment_without_layer_path_search.group(2)
            layer = None
            param_set_to_add = extract_parameter_set_for_input(ignore_non_aws_changes, available_parameter_sets, provider, environment, layer)

        if param_set_to_add:
            terraform_parameter_sets.add(param_set_to_add)

    return terraform_parameter_sets


def extract_parameter_set_for_input(ignore_non_aws_changes: bool, available_parameter_sets: List[TerraformParameterSet], provider: Optional[str], environment: Optional[str], layer: Optional[str]) \
        -> Optional[TerraformParameterSet]:
    # We perform this step in case we only have partial inputs. We'll use that partial input and identify a TerraformParameterSet which matches
    parameter_set_for_given_layer: Optional[TerraformParameterSet] = find_suitable_parameter_set_for_input(available_parameter_sets=available_parameter_sets, provider=provider, environment=environment, layer=layer)
    # If we need to ignore non-aws changes, only let aws ones through. Otherwise, let all.
    if (ignore_non_aws_changes and parameter_set_for_given_layer and parameter_set_for_given_layer.provider.lower() == "aws") or not ignore_non_aws_changes:
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


def extract_aws_credentials(environment_vars: Dict[str, Any] = os.environ.__dict__) -> Dict[str, AwsCredentialsForEnvironment]:
    # Detect AWS credentials, for one or more environments (dev/staging/prod, us/eu/asia, etc)
    # The generic format is AWS__(KEY/SECRET)__[profile]. Examples: AWS__KEY__TEST / AWS__SECRET__TEST.

    # The output of this function is a dictionary with entries in the format: Environment -> (AWS API Key, AWS API Secret, AWS API Region)
    credentials: Dict[str, AwsCredentialsForEnvironment] = {}
    for key in environment_vars.keys():
        aws_key_match: Optional[Match] = AWS_KEY_REGEX.search(key)
        aws_secret_match: Optional[Match] = AWS_SECRET_REGEX.search(key)
        if aws_key_match is not None:
            env_from_aws_key = aws_key_match.group(1)
            if env_from_aws_key in credentials:
                # The credentials for the current environment have already been set
                continue
            if f"AWS__SECRET__{env_from_aws_key}" not in environment_vars or f"AWS__REGION__{env_from_aws_key}" not in environment_vars:
                raise GithubActionException(
                    f"One of the required AWS credentials is missing for environment: {env_from_aws_key}. Required: 'AWS__KEY__{env_from_aws_key}', 'AWS__SECRET__{env_from_aws_key}', 'AWS__REGION__{env_from_aws_key}'")

            aws_key_for_environment = environment_vars[aws_key_match.group(0)]
            aws_secret_for_environment = environment_vars[f"AWS__SECRET__{env_from_aws_key}"]
            aws_region_for_environment = environment_vars[f"AWS__REGION__{env_from_aws_key}"]
            credentials[env_from_aws_key] = AwsCredentialsForEnvironment(aws_key_for_environment, aws_secret_for_environment, aws_region_for_environment)
        if aws_secret_match is not None:
            env_from_aws_secret = aws_secret_match.group(1)
            if env_from_aws_secret in credentials:
                # The credentials for the current environment have already been set
                continue
            if f"AWS__KEY__{env_from_aws_secret}" not in environment_vars or f"AWS__REGION__{env_from_aws_secret}" not in environment_vars:
                raise GithubActionException(
                    f"One of the required AWS credentials is missing for environment: {env_from_aws_secret}. Required: 'AWS__KEY__{env_from_aws_secret}', 'AWS__SECRET__{env_from_aws_secret}', 'AWS__REGION__{env_from_aws_secret}'")

            aws_key_for_environment = environment_vars[f"AWS__KEY__{env_from_aws_secret}"]
            aws_secret_for_environment = environment_vars[aws_secret_match.group(0)]
            aws_region_for_environment = environment_vars[f"AWS__REGION__{aws_key_for_environment}"]
            credentials[env_from_aws_secret] = AwsCredentialsForEnvironment(aws_key_for_environment, aws_secret_for_environment, aws_region_for_environment)
    return credentials


def main():
    # Checking that "CHANGED_FILE_LIST" is present in the with: input
    if 'INPUT_CHANGED_FILE_LIST' not in os.environ:
        raise Exception("Could not find CHANGED_FILE_LIST set in the input (the with: block) variables.")

    # - Take input from https://github.com/Stockopedia/action-get-changed-files
    # Example: [".github/workflows/lint.yaml",".github/workflows/terraform.yaml",".github/workflows/terraform_apply.yaml","layers/rds-data-platform-bcp-db/main.tf"]
    changed_files: List[str] = []
    try:
        changed_files = json.loads(os.getenv("INPUT_CHANGED_FILE_LIST"))
    except JSONDecodeError:
        print("ERROR: Unable to deserialise input JSON for variable CHANGED_FILE_LIST.")
        exit(1)

    # Input: base folder of the terraform folder, to lookup all available providers/environments/layers
    base_directory: str = os.getenv("INPUT_BASE_DIRECTORY", default="/github/workspace")

    # This determines if the Terraform plan should also be applied after the plan step is complete. This should only be triggered after approvals & other checks are completed.
    terraform_apply_mode: bool = os.getenv("INPUT_APPLY_MODE", default="False") == "True"

    # This determines if the Terraform plan/apply should include non-AWS providers. This may be useful if the Terraform runner has access to the AWS account, but not to the rest of the stack (EC2, RDS)
    ignore_non_aws_changes: bool = "INPUT_DISABLE_NON_AWS_CHANGES" in os.environ

    # The output of this function is a dictionary with entries in the format: Environment -> AwsCredentialsForEnvironment(AWS API Key, AWS API Secret, AWS API Region)
    aws_credentials_for_environments: Dict[str, AwsCredentialsForEnvironment] = extract_aws_credentials(os.environ.__dict__)

    print(f"Running the script for file(s): {changed_files}")
    # Filter by whitelist folder, e.g.: layers/*
    relevant_changed_files: List[str] = filter_changed_files_to_relevant_folders(changed_files,
                                                                                 RELEVANT_TERRAFORM_FOLDERS)
    print(f"Detected {len(relevant_changed_files)} changed file(s) relevant to Terraform: {relevant_changed_files}")

    available_parameter_sets: List[TerraformParameterSet] = list_all_available_parameter_sets(base_directory=base_directory)
    print(f"Available TF stack(s) in the whole repository (useful to confirm the repo state): {available_parameter_sets}")
    # - Build set of (env / provider / layer)
    # - If env['disable-non-aws'] is present, it will not include any non-aws provider
    terraform_parameter_sets: Set[TerraformParameterSet] = extract_terraform_parameter_sets(relevant_changed_files, available_parameter_sets, ignore_non_aws_changes)
    print(f"Transformed the changed file(s) into the following TF stack(s) that need to be planned: {terraform_parameter_sets}")

    # - For every mix in step 2, run
    # 	terraform -chdir=layers/$(layer) init \
    # 		-backend=true \
    # 		-reconfigure \
    # 		-backend-config=../../environments/$(provider)/$(env)/backend.tfvars \
    # 		-backend-config="key=tf-$(layer).tfstate"
    # 	terraform -chdir=layers/$(layer) plan --var-file=../../environments/$(provider)/$(env)/$(layer)/variables.tfvars
    terraform_plan_output_text: str = ""
    terraform_apply_output_text: str = ""
    terraform_error_output_text: str = ""
    for parameter_set in terraform_parameter_sets:
        os.environ["AWS_PROFILE"] = str(parameter_set.environment).lower()
        os.environ['AWS_ACCESS_KEY_ID'] = str(aws_credentials_for_environments[parameter_set.environment].api_key)
        os.environ['AWS_SECRET_ACCESS_KEY'] = str(aws_credentials_for_environments[parameter_set.environment].api_secret)
        os.environ['AWS_DEFAULT_REGION'] = str(aws_credentials_for_environments[parameter_set.environment].api_region)

        chdir_path = "%s/layers/%s" % (base_directory, parameter_set.layer)
        print(f"Setting the terraform working path (chdir) to {chdir_path}")
        terraform = Terraform(working_dir=chdir_path)
        tf_layer_specific_tfvars_path: str = "%s/environments/%s/%s/backend.tfvars" % (base_directory, parameter_set.provider, parameter_set.environment)
        tf_layer_specific_key_tfstate_path: str = "key=tf-%s.tfstate" % parameter_set.layer
        tf_vars: List[str] = [tf_layer_specific_tfvars_path, tf_layer_specific_key_tfstate_path]
        print(f"Running Terraform Init for the following tfvars: {tf_vars}")
        init_return: Tuple[Any, str, str] = terraform.init(backend=True, reconfigure=True,
                                                           backend_config=tf_vars)
        print("::group::Terraform init output")
        print(init_return[1])
        print("::endgroup::")

        terraform_error_output_text += init_return[2] + os.linesep + os.linesep

        tf_plan_var_file_path: str = "%s/environments/%s/%s/%s/variables.tfvars" % (base_directory, parameter_set.provider, parameter_set.environment, parameter_set.layer)
        print(f"Running Terraform plan for the following tfvars: {tf_plan_var_file_path}")
        plan_return: Tuple[Any, str, str] = terraform.plan(var_file=tf_plan_var_file_path)
        print("::group::Terraform plan output")
        print(plan_return[1])
        print("::endgroup::")
        terraform_plan_output_text += plan_return[1] + os.linesep + os.linesep
        terraform_error_output_text += plan_return[2] + os.linesep + os.linesep

        if terraform_apply_mode:
            # 	terraform -chdir=layers/$(layer) apply --var-file=../../environments/$(provider)/$(env)/$(layer)/variables.tfvars
            print(f"Running Terraform apply for the following tfvars: {tf_plan_var_file_path}")
            apply_return: Tuple[Any, str, str] = terraform.apply(var_file=tf_plan_var_file_path)
            print("::group::Terraform apply output")
            print(apply_return[1])
            print("::endgroup::")
            terraform_apply_output_text += apply_return[1] + os.linesep + os.linesep
            terraform_error_output_text += apply_return[2] + os.linesep + os.linesep
        else:
            print("APPLY_MODE is disabled, skipping the Terraform apply step")

    terraform_plan_output_text = terraform_plan_output_text.replace("\n", "%0A")
    terraform_apply_output_text = terraform_apply_output_text.replace("\n", "%0A")
    terraform_error_output_text = terraform_error_output_text.replace("\n", "%0A")

    print(f"::set-output name=terraform_plan_output::{terraform_plan_output_text}")
    print(f"::set-output name=terraform_apply_output::{terraform_apply_output_text}")
    print(f"::set-output name=terraform_error_output::{terraform_error_output_text}")


if __name__ == "__main__":
    main()
