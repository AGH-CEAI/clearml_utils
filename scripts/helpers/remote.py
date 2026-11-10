# Copyright (c) 2026, AGH Center of Excellence in Artificial Intelligence
# All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""
Running the scripts from the ClearML (WebUI -> clone template -> edit `Args` -> enqueue).
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from clearml import Task, TaskTypes

DEFAULT_TEMPLATE_DOCKER = "python:3.14-slim"
RUNNER_TASK_TAGS = ["clearml-utils"]

_SSH_URL = re.compile(r"^(?:ssh://)?[\w.-]+@(?P<host>[\w.-]+)[:/](?P<path>.+)$")


def add_template_arguments(
    parser: argparse.ArgumentParser, template_project: str
) -> None:
    parser.add_argument(
        "--create-template",
        action="store_true",
        default=False,
        help=(
            f"Instead of running, create a draft task in `{template_project}` "
            "with the given args, to be cloned, edited and enqueued from the ClearML WebUI "
            "(e.g. to the `services` queue)."
        ),
    )
    parser.add_argument(
        "--template-docker",
        default=DEFAULT_TEMPLATE_DOCKER,
        help=f"Container image of the template task (default: `{DEFAULT_TEMPLATE_DOCKER}`).",
    )


def init_task_if_remote(project_name: str, task_name: str) -> Task | None:
    """Attach to the task executed by the clearml-agent (no-op when running locally)."""
    if Task.running_locally():
        return None
    return Task.init(project_name=project_name, task_name=task_name)


def create_template(
    project_name: str,
    task_name: str,
    docker_image: str,
    template_arg: str = "create_template",
) -> None:
    """
    Store this script (with the current args) as a draft task to be cloned in the WebUI.
    Exits the process.
    """
    log = logging.getLogger(__name__)
    # ClearML does not follow the imports of the local `helpers` package
    for package in _script_dependencies(Path(sys.argv[0])):
        Task.add_requirements(package)
    task = Task.init(
        project_name=project_name,
        task_name=task_name,
        task_type=TaskTypes.service,
        tags=RUNNER_TASK_TAGS,
        reuse_last_task_id=False,
        auto_connect_frameworks=False,
        auto_resource_monitoring=False,
    )
    task.set_parameter(f"Args/{template_arg}", False)
    task.set_base_docker(docker_image=docker_image)

    # clearml-agent does not translate SSH URLs without git credentials - use HTTPS
    task.set_repo()  # waits for the repository detection
    repo = task.data.script.repository
    https_repo = _to_https(repo)
    if https_repo != repo:
        task.set_repo(repo=https_repo)
    log.info(
        f"Template task '{project_name}/{task_name}' (id={task.task_id}) "
        f"uses repository '{https_repo}' and container '{docker_image}'."
    )
    if task.data.script.diff:
        log.warning(
            "The template contains uncommitted changes (stored as a diff applied by the agent)."
        )

    task.execute_remotely(queue_name=None, exit_process=True)


def _script_dependencies(script: Path) -> list[str]:
    """Read `dependencies` from the inline script metadata (PEP 723) of the uv script."""
    deps, inside = [], False
    for line in script.read_text().splitlines():
        line = line.removeprefix("#").strip()
        if line.startswith("dependencies"):
            inside = True
        elif inside and line.startswith("]"):
            break
        elif inside:
            deps.append(line.strip('",'))
    return [d for d in deps if d]


def _to_https(repo: str) -> str:
    match = _SSH_URL.match(repo or "")
    if not match:
        return repo
    return f"https://{match['host']}/{match['path']}"
