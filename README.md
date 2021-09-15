# Stockopedia's Terraform PR GitHub Action

[![Unit Tests](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/unittests.yml/badge.svg)](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/unittests.yml)
[![Lint](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/python.yml/badge.svg)](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/python.yml)
[![Integration Test](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/integration.yml/badge.svg)](https://github.com/Stockopedia/action-run-terraform-on-pr/actions/workflows/integration.yml)

## About

This GitHub Action provides a way for a DevOps engineer to automate the planning and deployment of Stockopedia's Terraform infrastructure stack, eliminating the need for developers to request AWS Production access.

It achieves something similar to [Atlantis](https://github.com/runatlantis/atlantis), with minor differences. A brief comparison below:
* Atlantis needs a server to run and listen for webhook calls from GitHub
* Atlantis stores a lock when there's an active plan on a specific stack. This helps to avoid commit conflicts when multiple developers work on the same stack.
* This action runs as a GitHub Action, in a Docker container. 

### Terraform file structure

This GitHub Action was started due to Stockopedia's Terraform stack file/folder structure, which differs from what existing CI/CD tools supported at the time. 

Our typical Terraform repo structure looks like this:

```text
├── environments
│   ├── aws
│   │   ├── prod
│   │   │   ├── backend.tfvars
│   │       ├── rds-app-db
│   │       │   └── variables.tfvars
│   │   └── test
│   │       ├── backend.tfvars
│   │       ├── rds-app-db
│   │       │   └── variables.tfvars
│   ├── mysql
│   │   └── test
│   │       ├── app-db-users
│   │       │   └── variables.tfvars
│   │       └── backend.tfvars
├── layers
│   ├── app-db-users
│   │   ├── main.tf
│   │   └── variables.tf
│   ├── rds-app-db
│   │   ├── main.tf
│   │   ├── output.tf
│   │   ├── terraform.plan
│   │   └── variables.tf
```

There are 2 layers represented above:
* rds-app-db: an AWS-provided layer, creating an AWS RDS MySQL instance for our application
* app-db-users: a MySQL-provided layer, configuring the MySQL instance created above, and configuring aspects such as databases/users/permissions.

## Usage

TBC

### Example workflows

TBC

### Inputs

All inputs are set in the `with:` section of the GitHub workflow .yaml file.

| Input                         |       Required       |       Default value          |                      Description            |
|-------------------------------|----------------------|------------------------------|-----------------|
| CHANGED_FILE_LIST | Yes |  | A comma separated list of file paths, indicating files that have changed in the current PR. If all files in the repository are passed in, this will re-plan the entire stack. | 
| BASE_DIRECTORY | No | /app | The base directory of the terraform project. Used to look up the ./environments/ folder under it. |
| DISABLE_NON_AWS_CHANGES | No | false | Can have any value. If present, only aws provided layers will be considered by terraform. |
| APPLY_MODE | No | false | Determines whether the script should also run 'terraform apply' after the 'terraform plan' step. | 

### Outputs

| Output                                             | Description                                        |
|------------------------------------------------------|-----------------------------------------------|
| terraform_plan_output | Output from the Terraform Plan action(s). If multiple plans ran, the plans will be separated by 2 line separators. |
| terraform_apply_output | Output from the Terraform Apply action(s). This will be empty if APPLY_MODE was not set to true. If multiple plans ran, the plans will be separated by 2 line separators. |
| terraform_error_output | Error outputs from any of the steps (Init, Plan, Apply). If multiple plans ran, the plans will be separated by 2 line separators. |