---
name: onboard-aws-batch
description: Onboard an AWS account to Nextflow Platform as an AWS Batch compute environment. Use when the user wants to connect AWS to Seqera, set up an AWS Batch compute environment, create the IAM policy/role or credentials Seqera needs for AWS, or run pipelines on AWS through Seqera.
---

## Using this skill

For Nextflow Platform operations, read the [MCP connection](../launch-workflow/references/seqera-mcp/README.md) reference. Any `platform_*` names below describe API operations: discover their exact names and parameter schemas with `search_seqera_api`, then invoke `call_seqera_api`. The host manages OAuth for the connected MCP server.

# Onboard AWS Batch to Nextflow Platform

Set up everything Nextflow Platform needs to run Nextflow pipelines on AWS Batch: an S3 work bucket, an IAM policy and role (or user), a Seqera AWS credential, and an AWS Batch compute environment (CE).

Source docs: https://docs.seqera.io/platform-cloud/compute-envs/aws-batch. If anything below disagrees with the live docs, the docs win.

## Main Flow

1. **Pick the Platform workspace** the CE will live in.
2. **Gather decisions** — region, work directory storage, Forge vs Manual, Spot vs On-Demand, credential mode.
3. **Prepare AWS** — S3 bucket, IAM policy, IAM role (or user).
4. **Create the Platform credential.**
5. **Create the compute environment.**
6. **Verify** — CE reaches `AVAILABLE`, then run a test pipeline.

Before running any command that **creates or changes** AWS resources, show the user the exact command and wait for a yes.

## Step 1: Pick the Platform Workspace

Find the workspace with the Platform API. Use `search_seqera_api` to find the exact operation names (e.g. query "list workspaces", "list credentials", "create compute environment"), then `call_seqera_api`:

```
call_seqera_api(service: "platform", api_name: "<list workspaces operation>", parameters: {})
```

Ask the user which organization/workspace to use and record its `workspaceId`. Every later credential and CE call takes it. Check existing CEs (`platform_list_compute_envs`) — if a working AWS Batch CE already exists, ask whether a new one is really needed.

## Step 2: Gather Decisions

Ask the user (propose the recommended default for each):

| Decision | Options | Recommended |
|---|---|---|
| Region | any AWS region | where their data lives |
| Work directory | S3 bucket, EFS, or FSx for Lustre | **S3** (EFS/FSx are incompatible with Studios) |
| Config mode | **Batch Forge** (Seqera creates Batch CEs, queues, roles) or **Manual** (existing Batch queues) | Forge |
| Provisioning | Spot or On-Demand | Spot for cost, On-Demand for reliability |
| Max CPUs | total vCPUs Seqera may provision at once | start small (e.g. 256), raise later |
| Credential mode | **Role** (assume-role, no static keys) or **Keys** (IAM user access key) | **Role** |
| Wave + Fusion v2 | on/off | **on** (needed for Fargate head job, Graviton, fast S3 I/O) |

Check the AWS CLI is installed and logged in to the right account:

```bash
aws --version
aws sts get-caller-identity
```

Confirm the account ID with the user. If the CLI isn't set up, the user can do the AWS steps in the console instead — give them the same values.

## Step 3: Prepare AWS

### 3a. S3 work bucket

Create it in the **same region** as the CE:

```bash
aws s3api create-bucket --bucket <bucket> --region <region> \
  --create-bucket-configuration LocationConstraint=<region>   # omit this line for us-east-1
```

Offer a lifecycle rule that deletes intermediate files under the work prefix after N days (docs suggest 30). Work directories grow fast in production.

### 3b. IAM policy

Write the policy to a local file (e.g. `seqera-forge-policy.json`) and create it as a **managed** policy. Inline user policies cap at 2048 characters and the full policy won't fit.

**Forge mode** — use the full policy from the docs. Its source file is `https://raw.githubusercontent.com/seqeralabs/docs/master/platform-cloud/docs/compute-envs/_policies/aws-batch-full-policy.json` (the same file as the **Download** link on the AWS Batch docs page). It grants:

- Batch create/update/delete/tag on `TowerForge-*` compute environments and job queues; `DescribeComputeEnvironments`, `DescribeJobDefinitions`, `DescribeJobQueues`, `DescribeJobs` on `*`; cancel/register/submit/tag/terminate on job definitions, `TowerForge-*` queues and jobs
- `ec2:` launch template management, plus specific `ec2:Describe…` actions (VPCs, subnets, security groups, images, instance types, key pairs) for the form dropdowns
- `iam:PassRole` on `*`, limited to `batch.amazonaws.com`, `ec2.amazonaws.com`, `ecs-tasks.amazonaws.com`. If you scope it to role ARNs, include `TowerForge-*` and the Fargate/execution roles, and keep `ecs-tasks.amazonaws.com` — otherwise head job definition creation fails
- optional `iam:` role and instance-profile management on `TowerForge-*` — needed only when Forge creates the roles
- `logs:` read access, `s3:Get*`/`List*`/`PutObject`, `ssm:GetParameters` on `/aws/service/ecs/*`
- optional FSx, EFS, Secrets Manager (`tower-*`), `ec2:GetConsoleOutput`, and lineage SNS/S3 (`seqera-lineage-*`) statements

Forge-created resources always start with `TowerForge-`; that prefix can't be changed, so leave the resource scoping on it. If the user tightens the policy, Forge still needs `batch:DescribeJobQueues` and `batch:DescribeComputeEnvironments`.

**Manual mode** — minimum Batch permissions: `batch:DescribeJobs`, `batch:DescribeJobDefinitions`, `batch:RegisterJobDefinition`, `batch:SubmitJob`, `batch:CancelJob`, `batch:TagResource`, `batch:TerminateJob`, plus `batch:DescribeJobQueues` (only for the queue dropdown), `logs:` read access, and S3 access on the work bucket. Manual mode also needs the Batch queues, Batch compute environments, instance/execution roles, and a launch template or AMI with the AWS CLI installed, created first per https://docs.seqera.io/platform-cloud/enterprise/advanced-topics/manual-aws-batch-setup.

Offer to tighten the S3 statement to the work bucket (and any input/output buckets) instead of `*`. Studios and Data Explorer need read/write on each bucket they use.

```bash
aws iam create-policy --policy-name seqera-forge-policy --policy-document file://seqera-forge-policy.json
```

### 3c. IAM role (Role mode — recommended)

Role mode uses no static keys. Platform generates an **External ID** when you save a Role-mode credential, and that credential needs the role ARN, so the order is:

1. Write the trust policy from the docs (AWS Batch page, "IAM role-based credential creation") with `<EXTERNAL_ID>` left as a placeholder. For Seqera Cloud it trusts `arn:aws:iam::161471496260:role/SeqeraPlatformCloudAccessRole` with `sts:AssumeRole` (conditioned on `sts:ExternalId`) and `sts:TagSession`. Copy the JSON from the docs rather than retyping it; Enterprise installs trust their own Platform role instead.
2. Create the role and attach the policy:
   ```bash
   aws iam create-role --role-name seqera-platform-role --assume-role-policy-document file://seqera-trust-policy.json
   aws iam attach-role-policy --role-name seqera-platform-role --policy-arn arn:aws:iam::<account-id>:policy/seqera-forge-policy
   ```
3. Create the Role-mode credential with that role ARN (Step 4) and read back the generated External ID.
4. Put the External ID into the trust policy and apply it:
   ```bash
   aws iam update-assume-role-policy --role-name seqera-platform-role --policy-document file://seqera-trust-policy.json
   ```
   Until this is done, Platform can't assume the role. Pre-flight checks can't detect a missing External ID — it shows up at first launch.

### 3c (alternative). IAM user (Keys mode)

```bash
aws iam create-user --user-name seqera-platform
aws iam attach-user-policy --user-name seqera-platform --policy-arn arn:aws:iam::<account-id>:policy/seqera-forge-policy
```

The **user** creates the access key (IAM > Users > seqera-platform > Security credentials > Create access key, CLI use case). Don't run `aws iam create-access-key` yourself — its output contains the secret key.

## Step 4: Create the Platform Credential

- **Role mode** — the credential holds no secret, so you may create it via the API (`platform_create_credentials`; confirm the body with `search_seqera_api`): query `workspaceId=<id>&useExternalId=true`, body `provider: "aws"`, `keys: {"mode": "role", "assumeRoleArn": "<role-arn>"}`. Without `useExternalId=true` no External ID is generated. Then describe the credential and read `keys.externalId` for Step 3c.4.
- **Keys mode** — the credential holds a secret. Ask the user to add it in Nextflow Platform themselves: workspace > **Credentials** > **Add credentials** > Provider **AWS** (or the CE form's **Credentials** drop-down > **+**), **AWS credential mode: Keys**, then paste Access key and Secret key. If they also set **Assume role**, the optional **Generate External ID** switch appears; the IAM user then needs `sts:AssumeRole` on that role and the role must trust the user. Never ask them to paste keys into the chat.

Then list credentials and record the new `credentialsId`.

## Step 5: Create the Compute Environment

Look up the create-CE request schema with `search_seqera_api` ("create compute environment", platform `aws-batch`). Build the config from Step 2 and **show it to the user before submitting**. Key fields:

| Field | API field | Value |
|---|---|---|
| Name | `name` | e.g. `aws-batch-<region>-spot` (alphanumeric, `-`, `_`) |
| Platform | `platform` | `aws-batch` |
| Credentials | `credentialsId` | from Step 4 |
| Region | `region` | from Step 2; must match bucket / EFS / FSx |
| Work directory | `workDir` | `s3://<bucket>/work` (or EFS/FSx mount path ending in `/work`) |
| Wave / Fusion v2 | `waveEnabled`, `fusion2Enabled` | enabled (Fusion requires Wave) |
| Fast instance storage | `nvnmeStorageEnabled` (sic) | Forge + Fusion v2 only; leave Instance types empty so Platform picks NVMe families, or list NVMe types; never `optimal` |
| Forge: type | `forge.type` | `SPOT` or `EC2` (On-Demand); Platform adds an On-Demand queue for the head job when Spot |
| Forge: max CPUs | `forge.maxCpus` | from Step 2 |
| Forge: instance types | `forge.instanceTypes` | optional, up to 20 |
| Forge: Fargate head job | `forge.fargateHeadEnabled` | optional; requires Wave + Fusion v2 and Spot; not with EFS/FSx; Studios not supported; use EC2 for GPU, custom AMI, or >16 vCPUs |
| Forge: Graviton | `forge.arm64Enabled` | optional; requires Fargate head job (so Spot), Wave and Fusion v2; not with GPUs |
| Forge: GPU | `forge.gpuEnabled` | NVIDIA only; also set GPU instance types |
| Forge: EFS / FSx | `forge.efsId`/`efsMount`/`efsCreate`, `forge.fsxMount`/`fsxSize` | only if not using S3 |
| Forge: VPC / subnets / security groups | `forge.vpcId`, `forge.subnets`, `forge.securityGroups` | blank uses the region's defaults; private subnets need a NAT gateway (or equivalent) for outbound access, which Studios requires |
| Forge: dispose resources | `forge.disposeOnDeletion` | on (deletes Forge resources when the CE is deleted) |
| Manual: head queue / compute queue | `headQueue`, `computeQueue` | existing Batch job queue names; `cliPath` if the AWS CLI isn't at the default path |
| Head job CPUs / memory | `headJobCpus`, `headJobMemoryMb` | MiB, minimum 3584 (4096 with Fargate; Fargate needs a valid CPU/memory combination); empty means 3584 (or 4096) MiB per CPU; also caps Studio session size |

The UI path is workspace > **Compute Environments** > **Add compute environment** > **AWS Batch**, if the user would rather fill the form.

## Step 6: Verify

1. Poll the CE (describe compute env) until status is `AVAILABLE`. `ERRORED` or `INVALID` carries a message — common causes: missing `iam:PassRole`, the credential lacking read/write on the work directory, bucket in a different region, the 50-job-queue-per-account Batch quota. A missing External ID in the trust policy passes pre-flight checks and only fails at launch.
2. Run a test pipeline: hand off to the `launch-workflow` skill with `https://github.com/nextflow-io/hello` on the new CE.
3. If jobs sit in `RUNNABLE`, check Max CPUs, instance types available in the region, and EC2 vCPU quotas (Spot and On-Demand quotas are separate).

## Critical Rules

1. **CONFIRM before changing AWS** — show every create/attach/delete command and wait for the user's yes.
2. **NEVER handle secrets** — don't ask for, print, or pass access keys through the chat or the API. The user enters secret-bearing credentials in the Seqera UI. Prefer Role mode, which has none.
3. **MATCH regions** — bucket, EFS/FSx, and CE must be in the same region.
4. **USE a managed policy**, not an inline user policy (2048-character limit).
5. **KEEP the `TowerForge-` scoping** in Forge policies; the prefix is fixed.
6. **FINISH the trust policy** — create the role, then the credential, then write the generated External ID back into the trust policy. Copy trust policy and IAM policy JSON from the docs; never retype account IDs.
7. **SHOW the CE config** to the user before creating it.
8. **VERIFY** — the CE is only onboarded once it is `AVAILABLE` and a test pipeline succeeds.
