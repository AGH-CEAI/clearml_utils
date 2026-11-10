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
#   "tqdm",
# ]
# ///
import logging
import sys

from helpers.cli import build_parser, summary_type_parser
from helpers.data_getter import DataGetter, NoMetricsError, NoTasksError, SummaryType
from helpers.logging import setup_logging, timed
from helpers.remote import add_template_arguments, create_template, init_task_if_remote
from helpers.summarizer import Summarizer

TEMPLATE_PROJECT_NAME = "CLEARML_UTILS/exp_plot"
TEMPLATE_TASK_NAME = "clearml_exp_plotter"


@timed
def main(argv: list[str] | None = None) -> None:
    print(
        "#######################################################\n"
        "#      ▄▖▜       ▖  ▖▖   ▄▖      ▄▖▜   ▗ ▗            #\n"
        "#      ▌ ▐ █▌▀▌▛▘▛▖▞▌▌   ▙▖▚▘▛▌  ▙▌▐ ▛▌▜▘▜▘█▌▛▘       #\n"
        "#      ▙▖▐▖▙▖█▌▌ ▌▝ ▌▙▖  ▙▖▞▖▙▌  ▌ ▐▖▙▌▐▖▐▖▙▖▌        #\n"
        "#                            ▌                        #\n"
        "# AGH Center of Excellence in Artificial Intelligence #\n"
        "# ........... Maciej Aleksandrowicz 2026 ............ #\n"
        "#######################################################"
    )
    setup_logging()

    parser = build_parser(
        tags_required=False,
        default_summary_task_name="EXPERIMENTS_SUMMARY",
        default_summary_types=[SummaryType.MEAN],
    )
    add_template_arguments(parser, TEMPLATE_PROJECT_NAME)
    args = parser.parse_args(argv)
    args.summary_types = summary_type_parser(args.summary_types)

    if args.create_template:
        create_template(
            project_name=TEMPLATE_PROJECT_NAME,
            task_name=TEMPLATE_TASK_NAME,
            docker_image=args.template_docker,
        )
        return
    init_task_if_remote(
        project_name=TEMPLATE_PROJECT_NAME, task_name=TEMPLATE_TASK_NAME
    )
    try:
        data = DataGetter(
            project_name=args.project_name,
            max_samples=args.max_samples,
            recursive_projects=True,
            metrics_paths=args.metric_paths,
            tags_select=["summary"] + args.tags,
            merge_summaries_metrics=True,
            n_jobs=args.n_jobs,
        )
    except (NoTasksError, NoMetricsError):
        log = logging.getLogger(__name__)
        log.info("No tasks to process (check previous logs for more info). Exiting.")
        return

    TAG_EXP_PLOTTER = "exp-summary"
    summarizer = Summarizer(
        tasks_data=data,
        summary_task_name=args.summary_task_name,
        plots_backend=args.plots_backend,
        summary_task_tags=[TAG_EXP_PLOTTER],
        experiments_summary_mode=True,
        summary_types=args.summary_types,
        n_jobs=args.n_jobs,
    )
    if not summarizer.summarize(
        tag_for_tasks=TAG_EXP_PLOTTER,
        cleanup_previous_tags=args.cleanup_previous_tags,
        add_tag_to_tasks=True,
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
