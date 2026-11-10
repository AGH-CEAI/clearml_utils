#!/usr/bin/env -S uv run --script
# Copyright (c) 2026, AGH Center of Excellence in Artificial Intelligence
# All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "clearml",
#   "tqdm",
# ]
# ///

"""
Enqueue a batch of tasks to a given ClearML queue.

By default each task gets its own seed (`--seed-start` + its index), written into the `seed = ...`
line of the base task's configuration section (`--seed-section`, `rl` in aegis_gym). The ClearML
agent runs a task with its stored configuration and ignores the `Args` overrides of it, so the seed
must be set there. Disable it with `--no-seeds`.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections.abc import Iterable
from typing import Any

from clearml import Task
from clearml.automation import ClearmlJob
from helpers.logging import setup_logging, timed
from helpers.remote import add_template_arguments, create_template, init_task_if_remote
from tqdm import tqdm

TASKS_NUM_SAFEGUARD_LIMIT = 100
TEMPLATE_PROJECT_NAME = "CLEARML_UTILS/enqueue"
TEMPLATE_TASK_NAME = "clearml_enqueue_tasks"
SEED_ARG = "Args/seed"


@timed
def main():
    """
    Command-line interface for enqueuing tasks to a ClearML queue.

    Usage: python enqueue_tasks.py <base_task_id> <tasks_num> <queue_name> [--tags TAG1 TAG2] [--parameters JSON_STRING]
    """
    log = logging.getLogger(f"{__name__}")

    parser = build_parser()
    add_template_arguments(parser, TEMPLATE_PROJECT_NAME)
    args = parser.parse_args()

    if args.create_template:
        create_template(
            project_name=TEMPLATE_PROJECT_NAME,
            task_name=TEMPLATE_TASK_NAME,
            docker_image=args.template_docker,
        )
        return
    # Not `required=True`: the args of a remote run are filled in from the task (WebUI)
    missing = [
        f"--{name.replace('_', '-')}"
        for name in ("base_task_id", "tasks_num", "queue_name")
        if not getattr(args, name)
    ]
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")
    parameters = json.loads(args.parameters) if args.parameters else {}
    runner_task = init_task_if_remote(
        project_name=TEMPLATE_PROJECT_NAME, task_name=TEMPLATE_TASK_NAME
    )

    if args.tasks_num >= TASKS_NUM_SAFEGUARD_LIMIT and not args.allow_large_batch:
        log.warning(
            f"You are trying to enqueue {args.tasks_num} tasks. "
            f"The safeguard limit is {TASKS_NUM_SAFEGUARD_LIMIT} tasks. "
            "If you REALLY want to eqnue that much, please add the `--allow-large-batch` flag."
        )
        time.sleep(1)
        sys.exit(1)

    base_task = Task.get_task(task_id=args.base_task_id)
    seed_config = None
    if not args.no_seeds:
        seed_config = base_task.get_configuration_object(args.seed_section)
        if seed_config is None:
            log.error(
                f"The base task has no `{args.seed_section}` configuration section for the seed "
                "(see `--seed-section`, or `--no-seeds`)."
            )
            return
        # fails before anything is enqueued
        with_seed(config=seed_config, key=args.seed_key, seed=args.seed_start)
    seeds = (
        f"{args.seed_start}..{args.seed_start + args.tasks_num - 1} "
        f"({args.seed_section}.{args.seed_key})"
        if not args.no_seeds
        else "base task's"
    )

    log.info(
        "Proceeding to enquee:\n"
        f"\n> Base task: \t{base_task.task_id}"
        f"\n> B. task name: {base_task.name}"
        f"\n> Project path: {base_task.get_project_name()}"
        f"\n> Batch size: \t{args.tasks_num}"
        f"\n> Queue name: \t{args.queue_name}"
        f"\n> Tags: \t{args.tags}"
        f"\n> Extra params: {parameters}"
        f"\n> Seeds: \t{seeds}\n"
    )
    # A chance to abort a local run (no one to watch a remote one)
    if runner_task is None:
        sleep_countdown(8)

    enqueue_tasks(
        base_task=base_task,
        tasks_num=args.tasks_num,
        queue_name=args.queue_name,
        tags=args.tags,
        parameters=parameters,
        seed_config=seed_config,
        seed_section=args.seed_section,
        seed_key=args.seed_key,
        seed_start=args.seed_start,
    )
    log.info(f"{args.tasks_num} tasks enqeued to {args.queue_name} queue.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Enqueue a batch of tasks to a given ClearML queue."
    )
    p.add_argument(
        "--base-task-id", help="The ID of the base task to clone for each job."
    )
    p.add_argument("--tasks-num", type=int, help="The number of tasks to enqueue.")
    p.add_argument(
        "--queue-name", help="The name of the ClearML queue to enqueue the tasks to."
    )
    p.add_argument("--tags", nargs="*", help="Optional tags to add to each task.")
    p.add_argument(
        "--parameters", help="Optional parameter overrides as a JSON string."
    )
    p.add_argument(
        "--allow-large-batch",
        action="store_true",
        default=False,
        help="Disable safeguard mechanism for sending a large batch of runs.",
    )
    # a plain flag (not `BooleanOptionalAction`): shown as `no_seeds` in the WebUI `Args`
    p.add_argument(
        "--no-seeds",
        action="store_true",
        default=False,
        help="Keep the base task's seed in all the tasks (default: each task gets its own).",
    )
    p.add_argument(
        "--seed-start", type=int, default=0, help="The seed of the first task."
    )
    p.add_argument(
        "--seed-section",
        default="rl",
        help="The configuration section holding the seed.",
    )
    p.add_argument("--seed-key", default="seed", help="The seed's key in that section.")
    return p


def with_seed(config: str, key: str, seed: int) -> str:
    """The configuration text with its single top-level `key = ...` line set to the `seed`."""
    new, num = re.subn(rf"(?m)^{re.escape(key)}\s*[=:].*$", f"{key} = {seed}", config)
    if num != 1:
        raise ValueError(
            f"Expected one top-level `{key}` line in the configuration, found {num}."
        )
    return new


def enqueue_tasks(
    base_task: Task,
    tasks_num: int,
    queue_name: str,
    tags: Iterable[str] | None = None,
    parameters: dict[str, Any] | None = None,
    seed_config: str | None = None,
    seed_section: str = "rl",
    seed_key: str = "seed",
    seed_start: int = 0,
) -> None:
    """
    Enqueue a batch of tasks to a given ClearML queue.

    This function creates and launches multiple ClearML jobs based on a base task,
    allowing for batch processing of tasks with optional parameter overrides and tags.

    Args:
        base_task_id (str): The ID of the base task to clone for each job.
        tasks_num (int): The number of tasks to enqueue.
        queue_name (str): The name of the ClearML queue to enqueue the tasks to.
        tags (Iterable[str], optional): A list of tags to add to each task. Defaults to an empty list.
        parameters (dict[str, Any], optional): A dictionary of parameter overrides for each task. Defaults to an empty dict.
        seed_config (str, optional): The base task's `seed_section` configuration text; if given,
            the task `i` gets the seed `seed_start + i` in its `seed_key` line (and in `Args/seed`,
            if the base task has it). Defaults to None (the base task's seed).
    """
    log = logging.getLogger(f"{__name__}")

    # An empty `Args/tags` in the WebUI can come as `['']`
    tags = [t for t in (tags or []) if t]
    parameters = parameters or {}

    TEMPLATE_PREFIX = "TEMPLATE_"

    base_name = base_task.name
    base_name = base_name.removeprefix(TEMPLATE_PREFIX)

    has_seed_arg = SEED_ARG in base_task.get_parameters()

    for cnt in tqdm(range(tasks_num), desc="Scheduling", unit="task"):
        task_name = f"{base_name}_{cnt}"
        task_parameters = dict(parameters)
        configuration = None
        if seed_config is not None:
            seed = seed_start + cnt
            configuration = {
                seed_section: with_seed(config=seed_config, key=seed_key, seed=seed)
            }
            # only shown in the UI, the agent takes the seed from the configuration
            if has_seed_arg:
                task_parameters[SEED_ARG] = str(seed)
        job = ClearmlJob(
            base_task_id=base_task.id,
            parameter_override=task_parameters,
            configuration_overrides=configuration,
            task_overrides={
                "name": task_name,
                "tags": list(set(tags)),
            },
        )
        if configuration is not None:
            stored = job.task.get_configuration_object(seed_section)
            if stored != configuration[seed_section]:
                raise RuntimeError(
                    f"{job.task_id()}: the `{seed_section}` configuration wasn't stored."
                )
            log.info(f"{task_name} {job.task_id()}: {seed_section}.{seed_key} = {seed}")
        job.launch(queue_name=queue_name)


def sleep_countdown(t_sleep: int) -> None:
    logger = logging.getLogger()

    # Countdown loop with logging
    for i in range(t_sleep, -1, -1):
        logger.info(f"{i} seconds remaining... ")
        sys.stdout.write("\r")
        sys.stdout.flush()
        time.sleep(1)

    # Completion message
    logger.info("Proceeding...\n")
    sys.stdout.flush()


if __name__ == "__main__":
    setup_logging()
    log = logging.getLogger(f"{__name__}")
    try:
        main()
    except KeyboardInterrupt:
        pass
    log.info("Exiting")
