# Utility scripts

[Back to main README](../README.md)

---
## Tools for ClearML tasks management

> [!NOTE]
> Be sure to get the ClearML project structure to this:
```
PROJECTS/.../
└── YOUR_PROJECT/
    ├── EXPERIMENT_1/
    │   ├── SUMMARY
    │   ├── trial_run_1
    │   ├── trial_run_2
    │   ├── ...
    │   └── trial_run_N
    ├── EXPERIMENT_2/
    │   ├── SUMMARY
    │   ├── trial_run_1
    │   ├── trial_run_2
    │   ├── ...
    │   └── trial_run_N
    ├── EXPERIMENT_3/
    │   ├── SUMMARY
    │   ├── trial_run_1
    │   ├── trial_run_2
    │   ├── ...
    │   └── trial_run_N
    └── EXPERIMENTS_SUMMARY
```
where `SUMMARY` is the result of the `clearml_summarizer.py` run in the `YOUR_PROJECT/EXPERIMENT_X` project name path, and the `EXPERIMENTS_SUMMARY` is the result of the `clearml_exp_plotter.py` run in the `YOUR_PROJECT` project name path.

#### Example usage
```bash
# 1. Schedule tasks to a given queue
./clearml_enqueue_tasks.py --base-task-id=BASE-TASK-ID --tasks-num=20 --queue-name=robolab

# 2. Summarize experiments
./clearml_summarizer.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim/net64_temper_actor --tags net64 hyperopt
./clearml_summarizer.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim/net128_temper_actor --tags net128 hyperopt
./clearml_summarizer.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim/net256_temper_actor --tags net256 hyperopt
./clearml_summarizer.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim/net512_temper_actor --tags net512 hyperopt
# ...or summarize every sub-project at once (skipping the already summarized ones)
./clearml_summarizer.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim --subprojects --skip-summarized --tags hyperopt

# 3. Aggregate experiment summaries
./clearml_exp_plotter.py --cleanup-previous-tags --project-name PROJ_EXP1/architecture_rl-sim -h
```

---

### [`clearml_enqueue_tasks.py`](./clearml_enqueue_tasks.py)
Clone task multiple times into a selected queue.

```bash
./clearml_enqueue_tasks.py --base-task-id=BASE-TASK-ID --tasks-num=20 --queue-name=geonosis
```

By default each task gets its own seed: task `i` gets `--seed-start` + `i` (default 0..N-1, also the `_<n>` in its name), written into the
`seed = ...` line of the base task's configuration section `--seed-section` (default `rl`, key `--seed-key`
`seed`), and into `Args/seed` if the base task has it. The ClearML agent runs a task with its stored
configuration and ignores the `Args` overrides of it, so the seed has to be set in the configuration. Each
clone is read back to check it. `--no-seeds` keeps the base task's seed in all the tasks.

```bash
# seeds 10..14
./clearml_enqueue_tasks.py --base-task-id=BASE-TASK-ID --tasks-num=5 --queue-name=geonosis --seed-start=10
# all with the base task's seed
./clearml_enqueue_tasks.py --base-task-id=BASE-TASK-ID --tasks-num=5 --queue-name=geonosis --no-seeds
```

---

### [`clearml_enqueue_eval_tasks.py`](./clearml_enqueue_eval_tasks.py)
For each completed training task in a source project, clone an eval template and enqueue.

```bash
./clearml_enqueue_eval_tasks.py --eval-template-id=TEMPLATE-TASK-ID --source-project=PROJECT-PATH --queue-name=geonosis
```

---

### [`clearml_exp_plotter.py`](./clearml_exp_plotter.py)
Aggregate summaries of multiple ClearML experiments into comparison plots!

#### Usage

To use it properly, you need to run the `clearml_summarizer.py` first.

```bash
uv run --script ./clearml_exp_plotter.py --cleanup-previous-tags --project-name PROJECT/PATH
uv run --script ./clearml_exp_plotter.py -h
```

---
## [`clearml_summarizer.py`](./clearml_summarizer.py)
Summarize ClearML experiments.

### Usage
```bash
uv run --script ./clearml_summarizer.py --cleanup-previous-tags --project-name PROJECT/PATH --tags bc
uv run --script ./clearml_summarizer.py -h
```

> [!TIP]
> Use `--max-samples` equal to the number of reported iterations (e.g. `5000` for iterations `0..4999`), otherwise the ClearML server downsamples the data.

### Running from the ClearML WebUI
The summarizer can be executed by a clearml-agent (e.g. the `clearml-services` one, listening on the `services` queue):
1. Create (once) a draft template task in the `CLEARML_UTILS/summarize` project. The given args become the template defaults:
   ```bash
   ./clearml_summarizer.py --create-template --cleanup-previous-tags --project-name REACHER_BASELINE_1 --subprojects --skip-summarized --tags run --max-samples 5000
   ```
   The same works for `clearml_exp_plotter.py`, which creates its template in the `CLEARML_UTILS/exp_plot` project:
   ```bash
   ./clearml_exp_plotter.py --create-template --cleanup-previous-tags --project-name REACHER_BASELINE_1 --max-samples 5000
   ```
2. In the WebUI: clone the template, edit `CONFIGURATION -> HYPERPARAMETERS -> Args` and enqueue it to the `services` queue.

> [!NOTE]
> The agent clones the repository at the template's commit (HTTPS URL) and applies its stored uncommitted changes (`git diff`).
> New, untracked files are not part of the diff: commit them, or at least `git add -N <file>`, before creating the template.

#### Container image
By default the template uses the `python:3.14-slim` image, and the agent installs the packages on each run.
To skip the installation, build the [`Dockerfile`](./Dockerfile) on the machine running the agent:
```bash
docker build -t clearml-utils:latest scripts/
```
and set `clearml-utils:latest` as the image (`--template-docker clearml-utils:latest`, or in the WebUI: `EXECUTION -> CONTAINER`).

---

## Dataset manipulation

---
### [`upload_urdf_to_clearml.py`](./upload_urdf_to_clearml.py)
Upload URDF model, required by simulators, into ClearML.

#### Uploading
1. Generate standalone URDF model with [aegis_ros/aegis_description](https://github.com/AGH-CEAI/aegis_ros/tree/humble-devel/aegis_description) launch command:
```bash
ros2 launch aegis_description generate_standalone_urdf.launch.py disable_cell:=true
```
Which will generate the whole URDF file with 3D models in a default `~/ceai_ws/aegis_urdf` directory.

2. Run the [`upload_urdf_to_clearml.py`](./upload_urdf_to_clearml.py) script with the following options:
```bash
python3 ./upload_urdf_to_clearml.py ~/ceai_ws/aegis_urdf --name AegisURDFModel --project AEGIS_GRASP --desc "Aegis simulator assets"
```
> [!WARNING]
> **To update the dataset** make sure to add an additional option: `--parent "PREVIOUS_DATASET_ID"`

3. Check the ClearML server's datasets.

#### Usage

In the robot's config set the `urdf_model_id` param to the ClearML's dataset ID.

> [!IMPORTANT]
> In case of failure to obtain the model, the code will try to load URDF model from `~/ceai_ws/aegis_urdf` directory.

---

[Back to main README](../README.md)
