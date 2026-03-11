from pathlib import Path

from generate_workflows_lib import (
    get_lint_job_datas,
    get_misc_job_datas,
    get_test_job_datas,
    get_tox_envs,
)

tox_ini_path = Path(__file__).parent.parent.parent.joinpath("tox.ini")


def get_gh_contexts_from_jobs(job_datas):
    def get_job_name(job):
        if isinstance(job, str):
            return job
        return job["ui_name"]

    return [
        f"""      {{ context = "{get_job_name(job)}" }},\n"""
        for job in job_datas
    ]


jobs = sorted(
    get_gh_contexts_from_jobs(get_lint_job_datas(get_tox_envs(tox_ini_path)))
    + get_gh_contexts_from_jobs(
        get_test_job_datas(get_tox_envs(tox_ini_path), ["ubuntu-latest"])
    )
    + get_gh_contexts_from_jobs(get_misc_job_datas(get_tox_envs(tox_ini_path)))
)
with open("opentelemetry-admin-jobs.txt", "w") as f:
    for job in jobs:
        f.write(job)
