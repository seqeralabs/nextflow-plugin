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

**Forge mode** — use the full policy from the docs. Get the current version from the docs page (download link: `https://docs.seqera.io/assets/files/aws-batch-full-policy-21552c5a558545c07707257a720b6167.json` — if it 404s, copy it from the "IAM" section of the AWS Batch page). It grants:

- `batch:*` management on `TowerForge-*` compute environments and job queues, plus `Describe*` and job submit/cancel/terminate
- `ec2:` launch template management and `Describe*` (for dropdowns)
- `iam:PassRole` conditioned on `batch.amazonaws.com`, `ec2.amazonaws.com`, `ecs-tasks.amazonaws.com`
- `iam:` role and instance-profile management on `TowerForge-*`
- `logs:` read access, `s3:Get*`/`List*`/`PutObject`, `ssm:GetParameters` on `/aws/service/ecs/*`
- optional FSx, EFS, Secrets Manager (`tower-*`), `ec2:GetConsoleOutput`, and lineage SNS/S3 (`seqera-lineage-*`) statements

Forge-created resources always start with `TowerForge-`; that prefix can't be changed, so leave the resource scoping on it.

**Manual mode** — minimum Batch permissions: `batch:DescribeJobs`, `batch:DescribeJobDefinitions`, `batch:RegisterJobDefinition`, `batch:SubmitJob`, `batch:CancelJob`, `batch:TagResource`, `batch:TerminateJob`, plus `batch:DescribeJobQueues` (only for the queue dropdown), `logs:` read access, and S3 access on the work bucket.

Offer to tighten the S3 statement to the work bucket (and any input/output buckets) instead of `*`. Studios and Data Explorer need read/write on each bucket they use.

```bash
aws iam create-policy --policy-name seqera-forge-policy --policy-document file://seqera-forge-policy.json
```

### 3c. IAM role (Role mode — recommended)

Role mode uses no static keys. Seqera assumes the role with an **External ID** that Seqera generates when you create the credential, so the order matters:

1. Create the credential in Nextflow Platform first in Role mode (Step 4) — or start it in the UI — to get the External ID.
2. Create the role with the trust policy shown in the docs/Seqera UI. It trusts Seqera's platform role and requires `sts:ExternalId` to equal the generated value; it also allows `sts:TagSession`. **Copy the trusted principal ARN from the docs or the Platform credential form — don't type it from memory.**
3. Attach the policy:
   ```bash
   aws iam create-role --role-name seqera-platform-role --assume-role-policy-document file://seqera-trust-policy.json
   aws iam attach-role-policy --role-name seqera-platform-role --policy-arn arn:aws:iam::<account-id>:policy/seqera-forge-policy
   ```

### 3c (alternative). IAM user (Keys mode)

```bash
aws iam create-user --user-name seqera-platform
aws iam attach-user-policy --user-name seqera-platform --policy-arn arn:aws:iam::<account-id>:policy/seqera-forge-policy
```

The **user** creates the access key (IAM > Users > seqera-platform > Security credentials > Create access key, CLI use case). Don't run `aws iam create-access-key` yourself — its output contains the secret key.

## Step 4: Create the Platform Credential

- **Role mode** — the credential holds no secret, so you may create it via the API: provider `aws`, the role ARN as `assumeRoleArn`. Look up the exact request body with `search_seqera_api` ("create credentials"). Read back the generated External ID and put it in the trust policy (Step 3c).
- **Keys mode** — the credential holds a secret. Ask the user to add it in Nextflow Platform themselves: workspace > **Credentials** > **Add credentials** > Provider **AWS** > paste Access key and Secret key (optionally an Assume role ARN). Never ask them to paste keys into the chat.

Then list credentials and record the new `credentialsId`.

## Step 5: Create the Compute Environment

Look up the create-CE request schema with `search_seqera_api` ("create compute environment", platform `aws-batch`). Build the config from Step 2 and **show it to the user before submitting**. Key fields:

| Field | Value |
|---|---|
| Name | e.g. `aws-batch-<region>-spot` (alphanumeric, `-`, `_`) |
| Platform | `aws-batch` |
| Credentials | `credentialsId` from Step 4 |
| Region | from Step 2; must match bucket / EFS / FSx |
| Work directory | `s3://<bucket>/work` (or EFS/FSx mount path ending in `/work`) |
| Wave / Fusion v2 | enabled (Fusion requires Wave) |
| Fast instance storage | with Fusion v2, use NVMe instance types (e.g. `c6id`, `m6id`, `r6id`) |
| Forge: type | `SPOT` or `EC2` (On-Demand); Seqera adds an On-Demand queue for the head job when Spot |
| Forge: max CPUs | from Step 2 |
| Forge: Fargate head job | optional; requires Fusion v2 and Spot; not with EFS/FSx |
| Forge: GPU | NVIDIA only; also set GPU instance types in Advanced options |
| Manual: head queue / compute queue | existing Batch job queue names |
| Head job CPUs / memory | memory in MiB, minimum 3584 (4096 with Fargate) |
| VPC / subnets / security groups | blank uses defaults; private subnets need NAT for Studios and image pulls |
| Dispose resources | on (deletes Forge resources when the CE is deleted) |

The UI path is workspace > **Compute Environments** > **Add compute environment** > **AWS Batch**, if the user would rather fill the form.

## Step 6: Verify

1. Poll the CE (describe compute env) until status is `AVAILABLE`. `ERRORED` includes a message — common causes: missing `iam:PassRole`, wrong External ID in the trust policy, bucket in a different region, the 50-job-queue-per-account Batch quota.
2. Run a test pipeline. Hand off to `the `launch-workflow` skill` with `https://github.com/nextflow-io/hello` on the new CE.
3. If jobs sit in `RUNNABLE`, check Max CPUs, instance types available in the region, and EC2 vCPU quotas (Spot and On-Demand quotas are separate).

## Critical Rules

1. **CONFIRM before changing AWS** — show every create/attach/delete command and wait for the user's yes.
2. **NEVER handle secrets** — don't ask for, print, or pass access keys through the chat or the API. The user enters secret-bearing credentials in the Seqera UI. Prefer Role mode, which has none.
3. **MATCH regions** — bucket, EFS/FSx, and CE must be in the same region.
4. **USE a managed policy**, not an inline user policy (2048-character limit).
5. **KEEP the `TowerForge-` scoping** in Forge policies; the prefix is fixed.
6. **COPY trust policy principals and policy JSON from the docs or Seqera UI** — never reconstruct account IDs from memory.
7. **SHOW the CE config** to the user before creating it.
8. **VERIFY** — the CE is only onboarded once it is `AVAILABLE` and a test pipeline succeeds.
