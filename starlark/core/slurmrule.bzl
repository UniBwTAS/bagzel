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

    if use_slurm:
        job_script = ctx.actions.declare_file(ctx.label.name + ".slurm.sh")

        job_id_file = ctx.actions.declare_file(ctx.label.name + ".jobid")

        ctx.actions.write(
            output = job_id_file,
            content = "JOBID",
            is_executable = False,
        )



        #init SLURM, get content of SLURM job

        content = [
            "#!/bin/bash",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --job-name={}".format(ctx.label.name),
            "#SBATCH --cpus-per-task={}".format(ctx.attr.num_cpus),
            "#SBATCH --mem=15G",
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
        additional_inputs = []
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
        cmd = "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/opt/slurm/bin && "
        cmd += "JOBID=$(/opt/slurm/bin/sbatch {dep} {script} | awk '{{print $NF}}') && echo $JOBID > {jobid}".format(
                dep = sbatch_dependency_arg,
                script = job_script.path,
                jobid = job_id_file.path,)


    ### if we do not build it with SLURM: its a simple shell-command
    else:
        cmd = user_cmd

    ctx.actions.run_shell(
        inputs = ctx.files.srcs + ([job_script] if use_slurm else []),
        tools = [ctx.executable.tool] if ctx.attr.tool else [],
        outputs = outputs,
        command = cmd,
        mnemonic = "SlurmRule",
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