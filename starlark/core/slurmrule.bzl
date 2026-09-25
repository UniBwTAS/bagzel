# SPDX-FileCopyrightText: 2025 Lukas Beer <lukas.beer@unibw.de>
# SPDX-FileCopyrightText: 2026 Leon Pohl <leon.pohl@unibw.de>
#
# SPDX-License-Identifier: Apache-2.0

# In your .bzl file
SlurmInfo = provider(
    fields = {
        "job_id_file": "The file containing the SLURM job ID.",
    },
    doc = "Provides the job ID file from a slurmrule execution.",
)


def _slurmrule_impl(ctx):
    outputs = []
    outputs.extend(ctx.outputs.out_files)
    for _out_dir in ctx.attr.out_dirs:
        out_dir = ctx.actions.declare_directory(_out_dir)
        for output in outputs:
            if output.path.startswith(out_dir.path + "/"):
                fail("output {} is nested within output directory {}; outputs cannot be nested within each other!".format(output.path, out_dir.path))
            if output.is_directory and out_dir.path.startswith(output.path + "/"):
                fail("output directory {} is nested within output directory {}; outputs cannot be nested within each other!".format(out_dir.path, output.path))
        outputs.append(out_dir)

    if not outputs:
        fail("No outputs specified: outputs must not be empty.")

    rule_dir = "/".join([ctx.bin_dir.path, ctx.label.workspace_root, ctx.label.package]).replace("//", "/")
    log_dir = rule_dir + "/logs"

    # Prepare the actual user command
    user_cmd = ctx.attr.cmd.replace("$(RULEDIR)", rule_dir)
    for out_dir in ctx.attr.out_dirs:
        location_str = "$(location {})".format(out_dir)
        out_dir_path = "/".join([rule_dir, out_dir])
        user_cmd = user_cmd.replace(location_str, out_dir_path)

    user_cmd = ctx.expand_location(
        user_cmd,
        targets = ctx.attr.srcs + ([ctx.attr.tool] if ctx.attr.tool else []),
    )

    # Use SLURM if the build is invoked with --define use_slurm=true
    use_slurm = ctx.var.get("use_slurm", "false") == "true"

    additional_inputs = []

    if use_slurm:
        job_script = ctx.actions.declare_file(ctx.label.name + ".slurm.sh")

        job_id_file = ctx.actions.declare_file(ctx.label.name + ".jobid")



        #init SLURM, get content of SLURM job

        content = [
            "#!/bin/bash",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --job-name={}".format(ctx.label.name),
            "#SBATCH --cpus-per-task={}".format(ctx.attr.num_cpus),
            "#SBATCH --mem=15G",
            "#SBATCH --nice=1000000",   # yield to other jobs
            "#SBATCH --requeue",        # allow SLURM auto-requeue after NODE_FAIL/BOOT_FAIL/PREEMPTED
        ]

        # Only add this line if num_gpus > 0:
        if ctx.attr.num_gpus > 0:
            content.append("#SBATCH --partition=gpu")
            content.append("#SBATCH --gres=gpu:{}".format(ctx.attr.num_gpus))

        content.extend([
            "#SBATCH --output={}/{}.out".format(log_dir, ctx.label.name),
            "#SBATCH --error={}/{}.err".format(log_dir, ctx.label.name),
            "#SBATCH --time=48:00:00",
            "echo $SLURM_JOB_ID > {}".format(job_id_file.path),
            "",
            "set -e",
            'echo ""',
            'echo "==== CPU Info (Allocated) ===="',
            'echo "CPUs visible to this process (nproc): $(nproc)"',
            'echo "CPU affinity mask (taskset):"',
            'taskset -cp $$',
            'echo ""',
            'echo "==== SLURM CPU Environment Variables ===="',
            'echo "SLURM_CPUS_PER_TASK: $SLURM_CPUS_PER_TASK"',
            'echo "SLURM_CPUS_ON_NODE : $SLURM_CPUS_ON_NODE"',
            'now="$(date +"%T")"',
            'echo "Start time : $now"',
            #'nvidia-smi',
            user_cmd,
            'now="$(date +"%T")"',
            'echo "End time : $now"',
        ])


        #write it as shell script

        ctx.actions.write(
            output = job_script,
            content = "\n".join(content),
            is_executable = True,
        )



        # DEPENDENCY OF PREVIOUS SLURM-JOB
        sbatch_dependency_arg = ""
        if ctx.attr.after:
            # Get the jobid file from the provider of the dependency target
            previous_jobid_file = ctx.attr.after[SlurmInfo].job_id_file
            if not previous_jobid_file:
                fail("The dependency target {} did not provide a job ID file.".format(ctx.attr.after.label))

            # Add the previous job's ID file to our action's inputs
            additional_inputs.append(previous_jobid_file)

            # Defer reading the file until execution time with `$(cat ...)`
            sbatch_dependency_arg = "--dependency=afterok:$(cat {})".format(previous_jobid_file.path)




        #execute the shell script and directly write the JOBID to the file
        cmd = """
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/opt/slurm/bin

JOBID=""
cancel_slurm_job() {{
  if [ -n "$JOBID" ]; then
    echo "Cancelling Slurm job $JOBID for {name}" >&2
    /opt/slurm/bin/scancel "$JOBID" 2>/dev/null || true
  fi
}}
trap cancel_slurm_job INT TERM HUP EXIT

SUBMIT_OUTPUT=$(/opt/slurm/bin/sbatch --parsable {dep} {script})
JOBID="${{SUBMIT_OUTPUT%%;*}}"
echo "$JOBID" > {jobid}
echo "Submitted Slurm job $JOBID for {name}"

# Wait through SLURM auto-requeues. After NODE_FAIL / BOOT_FAIL /
# PREEMPTED, SLURM keeps the same JobID and re-schedules it; the job
# stays in squeue across those transitions. We only consult sacct for
# the terminal verdict once squeue has fully drained, bounded by the
# cluster's MaxJobRequeue.
while true; do
  QSTATE=$(/opt/slurm/bin/squeue -j "$JOBID" -h -O State 2>/dev/null | awk 'NF {{ print $1; exit }}' || true)
  if [ -n "$QSTATE" ]; then
    sleep 5
    continue
  fi

  STATE=$(/opt/slurm/bin/sacct -j "$JOBID" -X --noheader --format=State%30 2>/dev/null | awk 'NF {{ print $1; exit }}' || true)
  BASE_STATE="${{STATE%%+*}}"
  case "$BASE_STATE" in
    COMPLETED)
      trap - INT TERM HUP EXIT
      echo "Slurm job $JOBID completed successfully"
      exit 0
      ;;
    FAILED|CANCELLED|TIMEOUT|OUT_OF_MEMORY|NODE_FAIL|PREEMPTED|BOOT_FAIL|DEADLINE|REVOKED)
      trap - INT TERM HUP EXIT
      echo "Slurm job $JOBID failed with state $STATE" >&2
      exit 1
      ;;
    "")
      sleep 5
      ;;
    *)
      sleep 5
      ;;
  esac
done
""".format(
            dep = sbatch_dependency_arg,
            script = job_script.path,
            jobid = job_id_file.path,
            name = ctx.label.name,
        )


    ### if we do not build it with SLURM: its a simple shell-command
    else:
        cmd = user_cmd

    ctx.actions.run_shell(
        inputs = ctx.files.srcs + additional_inputs + ([job_script] if use_slurm else []),
        tools = [ctx.executable.tool] if ctx.attr.tool else [],
        outputs = outputs + ([job_id_file] if use_slurm else []),
        command = cmd,
        mnemonic = "SlurmRule",
        execution_requirements = {
            # SlurmRule targets often produce large, non-hermetic dataset
            # directories. Keep them off remote exec/cache to avoid CAS upload
            # failures for multi-GB artifacts.
            "no-remote-exec": "1",
        },
    )


    return [
    DefaultInfo(
        files = depset(outputs),
        runfiles = ctx.runfiles(ctx.files.tool),
    ),
        SlurmInfo(job_id_file = job_id_file) if use_slurm else SlurmInfo(job_id_file = None),
    ]

slurmrule = rule(
    implementation = _slurmrule_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True, mandatory = True),
        "out_files": attr.output_list(),
        "out_dirs": attr.string_list(mandatory = True),
        "cmd": attr.string(mandatory = True),
        "tool" : attr.label(
            allow_files = True,
            executable=True,
            cfg = "exec",
            doc = "Optional tools that are required to run the command.",
        ),
        "num_cpus": attr.int(default = 1),
        "num_gpus": attr.int(default = 0),
        "after": attr.label(
            doc = "A previous slurmrule target to wait for.",
            providers = [SlurmInfo], # Ensures the dependency is a slurmrule
        ),

    },
)
