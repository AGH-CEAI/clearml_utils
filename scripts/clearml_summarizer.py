#!/usr/bin/env -S uv run --script
# Copyright (c) 2026, AGH Center of Excellence in Artificial Intelligence
# All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "clearml",
#   "joblib",
#   "matplotlib",
#   "numpy",
#   "plotly",
# ]
# ///
import argparse
import logging

from helpers.cli import build_parser
from helpers.data_getter import (
    DataGetter,
    NoMetricsError,
    NoTasksError,
    SummaryType,
    get_subproject_names,
    has_summary_task,
)
from helpers.logging import setup_logging, timed
from helpers.summarizer import DEFAULT_SUMMARY_TAG_NAME, Summarizer


@timed
def main(argv: list[str] | None = None) -> None:
    print(
        "#######################################################\n"
        "#       ▄▖▜       ▖  ▖▖   ▄▖            ▘             #\n"
        "#       ▌ ▐ █▌▀▌▛▘▛▖▞▌▌   ▚ ▌▌▛▛▌▛▛▌▀▌▛▘▌▀▌█▌▛▘       #\n"
        "#       ▙▖▐▖▙▖█▌▌ ▌▝ ▌▙▖  ▄▌▙▌▌▌▌▌▌▌█▌▌ ▌▙▖▙▖▌        #\n"
        "# AGH Center of Excellence in Artificial Intelligence #\n"
        "# ........... Maciej Aleksandrowicz 2026 ............ #\n"
        "#######################################################"
    )
    setup_logging()

    parser = build_parser(
        tags_required=True,
        default_summary_task_name="SUMMARY",
        default_summary_types=[SummaryType.MEAN_MINMAX, SummaryType.MEAN_STD],
    )
    parser.add_argument(
        "--subprojects",
        action="store_true",
        default=False,
        help=(
            "Treat every direct sub-project of `--project-name` as a separate "
            "experiment and summarize each of them."
        ),
    )
    parser.add_argument(
        "--skip-summarized",
        action="store_true",
        default=False,
        help=(
            "Skip a project which already contains a completed `--summary-task-name` "
            f"task with the `{DEFAULT_SUMMARY_TAG_NAME}` tag."
        ),
    )
    args = parser.parse_args(argv)
    log = logging.getLogger(__name__)

    project_names = [args.project_name]
    if args.subprojects:
        project_names = get_subproject_names(args.project_name)
        if not project_names:
            log.warning(f"No sub-projects found in '{args.project_name}'. Exiting.")
            return
        projects_str = "\n\t".join(project_names)
        log.info(f"Found {len(project_names)} sub-project(s):\n\t{projects_str}")

    summarized, skipped = [], []
    for project_name in project_names:
        if args.skip_summarized and has_summary_task(
            project_name, args.summary_task_name, DEFAULT_SUMMARY_TAG_NAME
        ):
            log.info(f"Project '{project_name}' is already summarized. Skipping.")
            skipped.append(project_name)
            continue

        if summarize_project(args, project_name):
            summarized.append(project_name)
        else:
            skipped.append(project_name)

    if args.subprojects:
        log.info(
            f"Summarized {len(summarized)} project(s), skipped {len(skipped)}: {skipped}"
        )


def summarize_project(args: argparse.Namespace, project_name: str) -> bool:
    log = logging.getLogger(__name__)
    log.info(f"===== Summarizing project '{project_name}' =====")
    try:
        data = DataGetter(
            project_name=project_name,
            max_samples=args.max_samples,
            metrics_paths=args.metric_paths,
            tags_select=args.tags,
        )
    except (NoTasksError, NoMetricsError):
        log.info("No tasks to process (check previous logs for more info). Skipping.")
        return False

    summarizer = Summarizer(
        tasks_data=data,
        summary_task_name=args.summary_task_name,
        plots_backend=args.plots_backend,
        summary_types=args.summary_types,
    )
    summarizer.summarize(cleanup_previous_tags=args.cleanup_previous_tags)
    return True


if __name__ == "__main__":
    main()
