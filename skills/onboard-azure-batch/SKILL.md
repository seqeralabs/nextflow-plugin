---
name: onboard-azure-batch
description: Onboard an Azure subscription to Nextflow Platform as an Azure Batch compute environment. Use when the user wants to connect Azure to Seqera, set up an Azure Batch compute environment, create the Batch account, storage account, Entra service principal, managed identity, or credentials Seqera needs for Azure, or run pipelines on Azure through Seqera.
---

## Using this skill

For Nextflow Platform operations, read the [MCP connection](../launch-workflow/references/seqera-mcp/README.md) reference. Any `platform_*` names below describe API operations: discover their exact names and parameter schemas with `search_seqera_api`, then invoke `call_seqera_api`. The host manages OAuth for the connected MCP server.

# Onboard Azure Batch to Nextflow Platform

Set up everything Nextflow Platform needs to run Nextflow pipelines on Azure Batch: a resource group, a Storage account with a Blob container, a Batch account with enough quota, a Seqera Azure credential, and an Azure Batch compute environment (CE).

Source docs: https://docs.seqera.io/platform-cloud/compute-envs/azure-batch. If anything below disagrees with the live docs, the docs win.

## Main Flow

1. **Pick the Platform workspace** the CE will live in.
2. **Gather decisions** — region, credential type, Forge vs Manual, VM sizes, networking.
3. **Prepare Azure** — resource group, Storage account and container, Batch account, quotas, (optional) service principal and managed identity.
4. **Create the Platform credential.**
5. **Create the compute environment.**
6. **Verify** — CE reaches `AVAILABLE`, then run a test pipeline.

Before running any command that **creates or changes** Azure resources, show the user the exact command and wait for a yes.

## Step 1: Pick the Platform Workspace

Use `search_seqera_api` to find the exact operation names (e.g. "list workspaces", "list credentials", "create compute environment"), then `call_seqera_api`. Ask which organization/workspace to use and record its `workspaceId`. Check existing CEs (`platform_list_compute_envs`) first.

## Step 2: Gather Decisions

| Decision | Options | Recommended |
|---|---|---|
| Region | any region with Azure Batch | near the data; Storage and Batch must match |
| Credential | **Access keys** (Batch + Storage keys) or **Entra service principal** | **Entra** — required for VNet/subnet and managed identities |
| Config mode | **Batch Forge** (Seqera creates head and worker pools) or **Manual** (existing pool) | Forge |
| VM size | e.g. `Standard_E16d_v5` | E-series `d` sizes (local temp disk) for Fusion |
| VMs count | max VMs with autoscale | start small, matches your vCPU quota |
| Networking | default or a VNet subnet | default unless policy requires a VNet |
| Wave + Fusion v2 | on/off | **on** |

The two credential types are not interchangeable: a CE created with one can't switch to the other.

Check the Azure CLI:

```bash
az version
az account show
```

Confirm the subscription with the user.

## Step 3: Prepare Azure

### 3a. Resource group, Storage account, container

```bash
az group create --name <rg> --location <region>
az storage account create --name <storageacct> --resource-group <rg> --location <region> \
  --sku Standard_LRS --kind StorageV2 --allow-shared-key-access true --public-network-access Enabled
az storage container create --name <container> --account-name <storageacct> --auth-mode login
```

Requirements from the docs: storage account key access **enabled**, public access from all networks (Forge can't create compute with restricted networking, and disabling public access isn't supported), Microsoft-managed encryption keys only.

### 3b. Batch account

```bash
az batch account create --name <batchacct> --resource-group <rg> --location <region> \
  --storage-account <storageacct>
```

It must use pool allocation mode **Batch service** (the default) and allow **Shared Key** authentication.

### 3c. Quotas

New Batch accounts often can't create VMs until quota is raised. Check:

```bash
az batch account show --name <batchacct> --resource-group <rg> \
  --query "{pools:poolQuota, jobs:activeJobAndJobScheduleQuota, dedicatedCores:dedicatedCoreQuota, lowPriCores:lowPriorityCoreQuota, perFamily:dedicatedCoreQuotaPerVmFamilyEnforced}"
```

Needs:
- **Pools** — Forge creates two per CE (`tower-pool-<id>-head` and `-worker`).
- **Active jobs** — each running Nextflow process uses one Batch job per pipeline run.
- **Dedicated vCPUs for the chosen VM family** — at least the concurrent CPUs you want.

If too low, the user raises them in the portal: Batch account > **Quotas** > **Request quota increase**. This can take a support ticket and some time.

### 3d. Entra service principal (Entra credential only)

```bash
az ad sp create-for-rbac --name seqera-platform --skip-assignment
```

This prints a client secret. **Don't run it yourself** — have the user run it in their own terminal (or create the app registration in the portal) and keep the secret out of the chat. Then assign roles with the app's client ID (`az ad sp list --display-name seqera-platform --query "[].appId" -o tsv`):

```bash
az role assignment create --assignee <client-id> --role "Storage Blob Data Contributor" \
  --scope $(az storage account show -n <storageacct> -g <rg> --query id -o tsv)
az role assignment create --assignee <client-id> --role "Azure Batch Data Contributor" \
  --scope $(az batch account show -n <batchacct> -g <rg> --query id -o tsv)
```

Plus, only when used:
- **Network Contributor** (or a custom role with `Microsoft.Network/virtualNetworks/subnets/join/action`) on the VNet, if the CE uses a Subnet ID.
- **Managed Identity Operator** on each managed identity attached to pools.

### 3e. Managed identity (optional, Entra only)

Lets pool nodes reach Storage and ACR without keys. Needs Nextflow 24.06.0-edge or later.

```bash
az identity create --name seqera-pool-identity --resource-group <rg> --location <region>
az role assignment create --assignee <identity-principal-id> --role "Storage Blob Data Contributor" --scope <storage-account-id>
az role assignment create --assignee <identity-principal-id> --role AcrPull --scope <acr-id>   # if using ACR
```

Record its client ID and resource ID. A misconfigured identity fails the run — Seqera won't fall back to keys.

## Step 4: Create the Platform Credential

Both Azure credential types contain secrets (account keys or a client secret), so **the user enters them in Nextflow Platform**: workspace > **Credentials** > **Add credentials** > Provider **Azure**:

- **Shared key** tab — Batch account name + key (Batch account > Keys), Blob Storage account name + key (Storage account > Access keys).
- **Entra** tab — Batch account name, Blob Storage account name, Tenant ID, Client ID, Client secret.

Give them the account names to fill in. Never ask for keys or secrets in the chat. Then list credentials and record the `credentialsId`. Warn them not to rotate the storage key in Nextflow Platform after the CE is created.

## Step 5: Create the Compute Environment

Look up the create-CE schema with `search_seqera_api` (platform `azure-batch`). Build the config and **show it to the user before submitting**.

**Forge mode:**

| Field | Value |
|---|---|
| Name | e.g. `azure-batch-<region>` |
| Platform | `azure-batch` |
| Credentials | `credentialsId` from Step 4 |
| Region | e.g. `eastus` |
| Work directory | `az://<container>/work` |
| Wave / Fusion v2 | enabled; for production use `Standard_E16d_v5` or larger with ≥200 GB local temp disk; no Premium SSDv2/Ultra disks for Fusion |
| VMs type | default `Standard_D4_v3`; pick a `d` size |
| VMs count | max VMs under autoscale |
| Autoscale | on (scales 0 → VMs count) |
| Head VM type / CPUs / memory | optional; memory in MiB, minimum 3584 |
| Subnet ID | optional, Entra only: `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet>` |
| Managed identity | head and worker pool client ID + resource ID (resource IDs required for Forge) |
| Container registry credentials | ACR in the same region, if private images |
| Dispose resources | on (deletes pools when the CE is deleted) |
| Max wallclock time | default `7d`, up to 180 days |
| Token duration | SAS lifetime — must exceed the longest expected run |
| Job cleanup | defaults: delete tasks on completion, terminate jobs on completion |

**Manual mode** — the user creates a pool first (portal: Batch account > Pools > Add) following https://docs.seqera.io/platform-cloud/enterprise/advanced-topics/manual-azure-batch-setup. Key pool settings: image `microsoft-dsvm` / `ubuntu-hpc` / `2204`, Docker-compatible container config, autoscale, task slots = vCPUs, and — without Fusion — a start task that installs `azcopy` on every node. Then set Config mode **Manual** and the **Compute pool name**.

Environment variables can't be edited after creation; use Seqera pipeline secrets for secrets.

UI path: workspace > **Compute Environments** > **Add compute environment** > **Azure Batch**.

## Step 6: Verify

1. Poll the CE until status is `AVAILABLE`. On `ERRORED`, read the message — typical causes: no vCPU/pool quota, Storage public access disabled, missing Network Contributor on the VNet, access-key credential used with a Subnet ID.
2. Run a test pipeline: hand off to `the `launch-workflow` skill` with `https://github.com/nextflow-io/hello` on the new CE.
3. If pool nodes fail to start or tasks can't pull images, check outbound access from the subnet to container registries (quay.io, docker.io), Azure Storage, and Seqera.

## Critical Rules

1. **CONFIRM before changing Azure** — show every create/assign command and wait for the user's yes.
2. **NEVER handle secrets** — account keys and client secrets go straight from the user into the Seqera UI, never through the chat or the API. Don't run commands that print secrets.
3. **MATCH regions** — Storage account and Batch account in the same region.
4. **CHECK quota before creating the CE** — new Batch accounts often have none.
5. **USE Entra** when a VNet subnet or managed identity is needed; access keys support neither.
6. **KEEP Storage public network access and shared key access enabled** for Forge.
7. **SHOW the CE config** to the user before creating it.
8. **VERIFY** — the CE is only onboarded once it is `AVAILABLE` and a test pipeline succeeds.
