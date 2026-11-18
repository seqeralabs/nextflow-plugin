---
name: onboard-slurm
description: Onboard a Slurm HPC cluster to Nextflow Platform as a Slurm compute environment. Use when the user wants to connect a Slurm cluster to Seqera, set up SSH, managed identity, or Tower Agent credentials for an HPC cluster, configure Slurm partitions as Seqera head and compute queues, or run pipelines on Slurm through Seqera.
---

## Using this skill

For Nextflow Platform operations, read the [MCP connection](../launch-workflow/references/seqera-mcp/README.md) reference. Any `platform_*` names below describe API operations: discover their exact names and parameter schemas with `search_seqera_api`, then invoke `call_seqera_api`. The host manages OAuth for the connected MCP server.

# Onboard a Slurm Cluster to Nextflow Platform

Connect a Slurm cluster to Nextflow Platform so it can submit the Nextflow head job to the cluster, which then submits tasks with `sbatch`. You'll check the cluster, choose how Seqera connects to it, create the Platform credential, and create a Slurm compute environment (CE).

Source docs: https://docs.seqera.io/platform-cloud/compute-envs/hpc (shared page for Slurm, IBM LSF, PBS Pro, Grid Engine, Moab). If anything below disagrees with the live docs, the docs win.

## Main Flow

1. **Pick the Platform workspace** the CE will live in.
2. **Choose the connection method** — SSH, managed identity, or Tower Agent.
3. **Check the cluster** — scheduler access, Nextflow, partitions, directories, network.
4. **Create the Platform credential.**
5. **Create the compute environment.**
6. **Verify** — run a test pipeline.

Run cluster commands only where the user can see them (their terminal or an SSH session they've set up). Before anything that changes the cluster (creating directories, editing `authorized_keys`, changing permissions), show the command and wait for a yes.

## Step 1: Pick the Platform Workspace

Use `search_seqera_api` to find the exact operation names (e.g. "list workspaces", "list credentials", "create compute environment"), then `call_seqera_api`. Ask which organization/workspace to use and record its `workspaceId`. Check existing CEs (`platform_list_compute_envs`) first.

## Step 2: Choose the Connection Method

| Method | How it works | Use when |
|---|---|---|
| **Managed identity** | Seqera SSHes to the login node as **each user's own** Linux account | multiple users; you want per-user accounting and fair-share. Created by an org owner. |
| **SSH credential** | Seqera SSHes to the login node with **one shared** key | a single user or a service account |
| **Tower Agent** | An agent on the cluster opens an outbound connection to Seqera; no inbound SSH | the login node isn't reachable from the internet |

SSH and managed identity need the login node to accept inbound SSH from Nextflow Platform — confirm with the cluster admins (ask Seqera support for the current source IPs if the firewall needs an allow-list). Tower Agent only needs outbound HTTPS.

## Step 3: Check the Cluster

On the login node:

```bash
sinfo -s                              # partitions and their state
sbatch --version
squeue -u $USER
nextflow -version                     # must be on PATH in a non-interactive login shell
java -version                         # Java 17+ for current Nextflow
curl -sI https://api.cloud.seqera.io | head -1   # outbound to Seqera (use the Enterprise URL if self-hosted)
```

Requirements:
- **Nextflow on the cluster.** Docs list 21.02.0-edge as the floor; recommend a current release. If it's missing, use the `install-nextflow` skill on the cluster. It must be on `PATH` for the shell the head job runs in — confirm with `ssh <login-node> 'which nextflow'` or by loading it via a module in the CE's pre-run script.
- **Compute nodes can submit jobs.** The head job runs on a compute node and calls `sbatch` itself. Check the partition allows that, then confirm the inner job ran:
  ```bash
  sbatch -p <head-partition> --wrap 'sbatch -p <compute-partition> --wrap hostname && squeue -u $USER'
  ```
- **Outbound HTTPS from the head job's node** to Seqera, so Nextflow can report progress.
- **Shared filesystem** visible from login and compute nodes for the work and launch directories.

Pick with the user:
- **Head queue** — partition for the long-running Nextflow head job (low CPU, long wall time).
- **Compute queue** — default partition for tasks (pipelines can override per process with `queue`).
- **Work directory** — absolute path on shared storage, e.g. `/scratch/<user>/seqera/work`. Create it before the first run: the docs state Tower Agent doesn't create directories, and pre-creating it lets you set group permissions. `$TW_AGENT_WORKDIR` and `$TW_AGENT_USER` are expanded for Tower Agent CEs.
- **Launch directory** — optional; defaults to the work directory.

For **managed identities**, every user must share a Linux group that can write the work directory:

```bash
chgrp -R <shared-group> <workdir>
chmod -R g+wxs <workdir>
setfacl -Rdm g::rwX <workdir>
```

## Step 4: Create the Platform Credential

All three hold or derive from a secret the user controls, so the **user** creates them in Nextflow Platform. Guide them step by step; never ask for a private key or token in the chat.

**SSH credential**
1. The user generates a key pair (ideally with a passphrase) and adds the public key to `~/.ssh/authorized_keys` on the cluster:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/seqera_hpc
   ssh-copy-id -i ~/.ssh/seqera_hpc.pub <user>@<login-node>
   ```
2. Org workspace > **Credentials** > **Add credentials** (personal workspace: user menu > **Your credentials** > **Add credentials**) > Name (alphanumeric, `-`, `_`), Provider **SSH**, paste the private key (including the `-----BEGIN/END OPENSSH PRIVATE KEY-----` lines, no extra lines or spaces) and passphrase > **Add**.

The key is shared by everyone in the workspace — all runs use that one cluster identity. The SSH credential stores only the key and passphrase; the Linux username goes on the CE.

**Managed identity** (organization owner)
1. Organization > **Managed identities** tab > **Add managed identity**: a unique **Cluster name**, Provider **Slurm**, **Hostname** (login node FQDN), **Port** (default 22) > **Add cluster**.
2. **Edit** the identity > **Users** tab > **Add credentials**: each user (or an org owner for them) adds their **Linux username**, **SSH private key**, and **Passphrase**. Users show as **Missing** until then. At least one user's credentials must be added before the identity can be used in a CE.

**Tower Agent** — complete these in order; the agent must be running before the CE is created, because Platform validates the CE by running a test command through it.
1. Personal access token: user menu > **Your tokens** > **Add token**; the user copies it immediately and keeps it out of the chat.
2. Workspace > **Credentials** > **Add credentials** > Provider **Tower Agent**; accept or enter the **Agent connection ID** (it must match exactly). Turn on **Shared agent** only if one agent should serve all workspace members — all jobs then run as the agent's Linux user. For per-user identity, leave it off and have each user run their own agent.
3. On the login node:
   ```bash
   curl -fSL https://github.com/seqeralabs/tower-agent/releases/latest/download/tw-agent-linux-x86_64 > tw-agent && chmod +x tw-agent
   mkdir -p /scratch/$USER/seqera/work   # default is ~/work, but home quotas are usually small
   ```
4. In `tmux new -s tower-agent`, the user runs (their token never goes through the chat):
   ```bash
   export TOWER_ACCESS_TOKEN=<token>
   ./tw-agent <connection-id> --work-dir=/scratch/$USER/seqera/work
   ```
   For Seqera Enterprise add `--url=<api-endpoint>` or set `TOWER_API_ENDPOINT` (default `https://api.cloud.seqera.io`). Detach with Ctrl-b d.
5. Keep it running (`tmux`, `screen`, or a systemd user service) and restart it after login-node reboots. If it stops, launches fail.

For SSH or Tower Agent, list workspace credentials and record the `credentialsId`. For a managed identity, list the organization's managed identities and record the `managedIdentityId` — the CE takes `managedIdentityId`, not `credentialsId`. API provider IDs: `ssh` (keys `privateKey`, `passphrase`) and `tw-agent` (keys `connectionId`, `shared`, optional `workDir`).

## Step 5: Create the Compute Environment

Look up the create-CE schema with `search_seqera_api` (platform `slurm-platform`). Build the config and **show it to the user before submitting**:

| Field | API field | Value |
|---|---|---|
| Name | `name` | e.g. `slurm-<cluster>` |
| Platform | `platform` | `slurm-platform` |
| Credentials | `credentialsId` or `managedIdentityId` | from Step 4 |
| Work directory | `workDir` | absolute path from Step 3 |
| Launch directory | `launchDir` | optional |
| Login hostname | `hostName` | login node hostname or public IP; the form may hide or prefill it depending on the credential type |
| Username / port | `userName`, `port` | SSH credential: the cluster Linux username and SSH port (default 22). Managed identity takes the username from each user's identity |
| Head queue name | `headQueue` | head partition |
| Compute queue name | `computeQueue` | compute partition |
| Nextflow queue size | `maxQueueSize` | max jobs Nextflow keeps submitted at once — match the cluster's per-user limit (`sacctmgr show assoc user=$USER format=MaxSubmit`) |
| Head job submit options | `headJobOptions`, `propagateHeadJobOptions` | `sbatch` options for the head job, e.g. `--time=7-00:00:00 --mem=8G --cpus-per-task=2`; optionally applied to compute jobs too; can't be overridden at launch |
| Pre-run script | `preRunScript` | under **Staging options**, e.g. `module load nextflow java` if Nextflow comes from environment modules |
| Environment variables | `environment` (`head` / `compute` booleans) | Name, Value, and Target (**Head job** / **Compute job** / both), e.g. `NXF_OPTS=-Xms1g -Xmx6g` targeted to the head job. They can't be edited after creation; put secrets in pipeline secrets, not here |

Container engine: tasks need Singularity/Apptainer (most HPC) or Docker on compute nodes. Set it under **Staging options** > global Nextflow config (`nextflowConfig`), e.g. `apptainer.enabled = true`; launch-time config can override it.

UI path: workspace > **Compute environments** > **Add compute environment** (older docs: **New environment**) > choose **Slurm** in the **Platform** drop-down.

## Step 6: Verify

1. Run a test pipeline: hand off to the `launch-workflow` skill with `https://github.com/nextflow-io/hello` on the new CE.
2. If the run never starts: SSH to the login node with the same key/user and check `squeue -u <user>`; confirm the head partition accepts jobs and `nextflow` is on `PATH`.
3. If the head job starts but tasks don't: the head partition's nodes can't run `sbatch`, or the queue size exceeds `MaxSubmit`.
4. If the run starts but Seqera shows no progress: outbound HTTPS from compute nodes to Seqera is blocked.

## Critical Rules

1. **CONFIRM before changing the cluster** — show every command that writes files, keys, or permissions, and wait for the user's yes.
2. **NEVER handle secrets** — SSH private keys, passphrases, and access tokens go from the user straight into Nextflow Platform or their own terminal, never through the chat.
3. **CHECK that compute nodes can run `sbatch`** — the head job submits tasks from inside the cluster.
4. **CHECK `nextflow` is on PATH** for non-interactive shells, or load it in the pre-run script.
5. **CREATE the work directory first** — Tower Agent doesn't create directories, and pre-creating it lets you set group permissions.
6. **USE managed identities** when more than one person will run pipelines and per-user accounting matters.
7. **SHOW the CE config** to the user before creating it.
8. **VERIFY** — the CE is only onboarded once a test pipeline succeeds.
