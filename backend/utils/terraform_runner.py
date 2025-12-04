import os
import json
import shutil
import subprocess
import zipfile


def _run_terraform_outputs(job_dir: str, env: dict) -> dict:
    """
    Helper: Run `terraform output -json` and return parsed dict.
    If command fails, returns {}.
    """
    try:
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=job_dir,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            return {}
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    except Exception:
        return {}


def run_terraform_template_job(
    job_id: int,
    template_name: str,
    variables: dict,
    aws_access_key: str,
    aws_secret_key: str,
    aws_region: str,
    base_dir: str,
    logs_dir: str,
):
    """
    Run a Terraform template for a specific job.

    - Copies the selected template to a job-specific folder
    - Creates terraform.auto.tfvars.json with user-provided variables
    - Runs `terraform init` and `terraform apply`
    - Captures logs in a log file
    - After success, runs `terraform output -json` and returns outputs dict

    Returns:
        (success: bool, log_file_path: str | error_code, outputs: dict)
    """

    # Paths
    templates_root = os.path.join(base_dir, "..", "infra", "templates", "aws")
    jobs_root = os.path.join(base_dir, "..", "infra", "jobs")
    os.makedirs(jobs_root, exist_ok=True)

    template_dir = os.path.join(templates_root, template_name)
    if not os.path.isdir(template_dir):
        return False, f"TEMPLATE_NOT_FOUND::{template_dir}", {}

    job_dir = os.path.join(jobs_root, f"job_{job_id}")

    # Fresh job dir
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)
    shutil.copytree(template_dir, job_dir)

    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, f"job_{job_id}.log")

    # TF vars
    tfvars_path = os.path.join(job_dir, "terraform.auto.tfvars.json")
    with open(tfvars_path, "w", encoding="utf-8") as f:
        json.dump(variables, f, indent=2)

    # ENV
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_access_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    env["AWS_DEFAULT_REGION"] = aws_region

    commands = [
        ["terraform", "init", "-input=false"],
        ["terraform", "apply", "-auto-approve", "-input=false"],
    ]

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Job #{job_id} - Template: {template_name}\n")
        log_file.write(f"Working directory: {job_dir}\n")
        log_file.write("-" * 60 + "\n\n")
        log_file.flush()

        for cmd in commands:
            log_file.write(f">>> Running: {' '.join(cmd)}\n\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                cwd=job_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
            process.wait()

            if process.returncode != 0:
                log_file.write(
                    f"\nCommand failed with exit code {process.returncode}\n"
                )
                log_file.flush()
                return False, log_file_path, {}

    # If we reach here: apply success
    outputs = _run_terraform_outputs(job_dir, env)
    return True, log_file_path, outputs


def run_terraform_custom_job(
    job_id: int,
    zip_file_path: str,
    custom_jobs_root: str,
    aws_access_key: str,
    aws_secret_key: str,
    aws_region: str,
    logs_dir: str,
):
    """
    Custom Mode runner:

    - Takes a user-uploaded Terraform project ZIP
    - Extracts to custom_jobs/job_<id>/
    - Runs `terraform init` and `terraform apply`
    - Captures logs in a log file
    - After success, runs `terraform output -json`

    Returns:
        (success: bool, log_file_path: str | error_code, outputs: dict)
    """

    os.makedirs(custom_jobs_root, exist_ok=True)
    job_dir = os.path.join(custom_jobs_root, f"job_{job_id}")

    if os.path.exists(job_dir):
        shutil.rmtree(job_dir)
    os.makedirs(job_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(job_dir)
    except zipfile.BadZipFile:
        return False, "INVALID_ZIP_FILE", {}

    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, f"job_{job_id}.log")

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_access_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    env["AWS_DEFAULT_REGION"] = aws_region

    commands = [
        ["terraform", "init", "-input=false"],
        ["terraform", "apply", "-auto-approve", "-input=false"],
    ]

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Custom Job #{job_id}\n")
        log_file.write(f"Working directory: {job_dir}\n")
        log_file.write("-" * 60 + "\n\n")
        log_file.flush()

        for cmd in commands:
            log_file.write(f">>> Running: {' '.join(cmd)}\n\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                cwd=job_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
            process.wait()

            if process.returncode != 0:
                log_file.write(
                    f"\nCommand failed with exit code {process.returncode}\n"
                )
                log_file.flush()
                return False, log_file_path, {}

    outputs = _run_terraform_outputs(job_dir, env)
    return True, log_file_path, outputs


def run_terraform_destroy_job(
    job_id: int,
    job_mode: str,
    template_name: str,
    custom_jobs_root: str,
    base_dir: str,
    logs_dir: str,
    aws_access_key: str,
    aws_secret_key: str,
    aws_region: str,
):
    """
    Runs `terraform destroy` for an existing job.
    Uses the SAME folder where the terraform apply was executed.

    For template mode:
        folder = infra/jobs/job_<id>/

    For custom mode:
        folder = custom_jobs/job_<id>/

    Returns:
        (success: bool, log_file_path: str)
    """

    if job_mode == "template":
        job_dir = os.path.join(base_dir, "..", "infra", "jobs", f"job_{job_id}")
    else:
        job_dir = os.path.join(custom_jobs_root, f"job_{job_id}")

    if not os.path.isdir(job_dir):
        return False, f"JOB_FOLDER_NOT_FOUND::{job_dir}"

    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, f"job_{job_id}_destroy.log")

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = aws_access_key
    env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
    env["AWS_DEFAULT_REGION"] = aws_region

    command = ["terraform", "destroy", "-auto-approve", "-input=false"]

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Destroy Job #{job_id}\n")
        log_file.write(f"Working Directory: {job_dir}\n")
        log_file.write("-" * 60 + "\n\n")
        log_file.flush()

        log_file.write(f">>> Running: {' '.join(command)}\n\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
        )
        process.wait()

        if process.returncode != 0:
            log_file.write(
                f"\nDestroy FAILED with exit code {process.returncode}\n"
            )
            return False, log_file_path

    return True, log_file_path
