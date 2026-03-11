from pathlib import Path

from generate_workflows_lib import (
    get_lint_job_datas,
    get_test_job_datas,
    get_tox_envs,
)

tox_ini_path = Path(__file__).parent.parent.parent.joinpath("tox.ini")


def get_gh_contexts_from_jobs(job_datas):
    return [
        f"""      {{ context = "{job["ui_name"]}" }},\n""" for job in job_datas
    ]


jobs = sorted(
    get_gh_contexts_from_jobs(get_lint_job_datas(get_tox_envs(tox_ini_path)))
    + get_gh_contexts_from_jobs(
        get_test_job_datas(get_tox_envs(tox_ini_path), ["ubuntu-latest"])
    )
)
with open("opentelemetry-admin-jobs.txt", "w") as f:
    for job in jobs:
        f.write(job)
