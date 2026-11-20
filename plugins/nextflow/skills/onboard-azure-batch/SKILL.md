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

The two credential types authenticate differently and don't share access; pick one per CE up front (Entra if you need a subnet or managed identity).

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

`--auth-mode login` needs the signed-in user to hold Storage Blob Data Contributor on the account; otherwise create the container in the portal (Storage account > **+ Container**).

Requirements from the docs: storage account key access **enabled**, public access from all networks (Forge can't create compute with restricted networking, and disabling public access isn't supported), Microsoft-managed encryption keys only.

### 3b. Batch account

```bash
az batch account create --name <batchacct> --resource-group <rg> --location <region> \
  --storage-account <storageacct>
```

For Batch Forge it must use pool allocation mode **Batch service** (the default); Manual pools can also use User Subscription. It must allow **Shared Key** authentication — check with:

```bash
az batch account show -n <batchacct> -g <rg> --query allowedAuthenticationModes
```

### 3c. Quotas

New Batch accounts often can't create VMs until quota is raised. Check:

```bash
az batch account show --name <batchacct> --resource-group <rg> \
  --query "{pools:poolQuota, jobs:activeJobAndJobScheduleQuota, dedicatedCores:dedicatedCoreQuota, lowPriCores:lowPriorityCoreQuota, perFamilyEnforced:dedicatedCoreQuotaPerVmFamilyEnforced, perFamily:dedicatedCoreQuotaPerVmFamily}"
```

If `perFamilyEnforced` is true, check the entry for the chosen series (e.g. `standardEDv5Family`).

Needs:
- **Pools** — Forge creates two per CE (`tower-pool-<id>-head` and `-worker`).
- **Active jobs** — each running Nextflow process uses one Batch job per pipeline run.
- **Dedicated vCPUs for the chosen VM family** — at least the concurrent CPUs you want.

The docs' suggested starting quotas: **Pools per Batch account** 50, **Active jobs and job schedules per Batch account** 100, and dedicated vCPUs for the series (e.g. **EDv5 Series** 192). If too low, the user raises them in the portal: Batch account > **Quotas** > **Request quota increase** > Quota type **Batch**. This can take a support ticket and some time.

### 3d. Entra service principal (Entra credential only)

```bash
az ad sp create-for-rbac --name seqera-platform   # assigns no role by default
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
- **Managed Identity Operator** on each managed identity attached to pools — without it Platform can't attach the identity:
  ```bash
  az role assignment create --assignee <client-id> --role "Managed Identity Operator" --scope <identity-resource-id>
  ```

### 3e. Managed identity (optional, Entra only)

Lets pool nodes reach Storage and ACR without keys; recommended with Entra. Needs Nextflow 24.06.0-edge or later. One identity can serve both pools, or use separate head and worker identities to keep worker RBAC narrower.

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

Give them the account names to fill in. Never ask for keys or secrets in the chat. Then list credentials and record the `credentialsId`. In the API, Shared key credentials have provider `azure` and Entra credentials `azure_entra` (not `azure-cloud`). Warn them not to rotate the storage key in Nextflow Platform after the CE is created.

## Step 5: Create the Compute Environment

Look up the create-CE schema with `search_seqera_api` (platform `azure-batch`). Build the config and **show it to the user before submitting**.

**Forge mode:**

| Field | API field | Value |
|---|---|---|
| Name | `name` | e.g. `azure-batch-<region>` |
| Platform | `platform` | `azure-batch` |
| Credentials | `credentialsId` | from Step 4 |
| Region | `region` | e.g. `eastus` |
| Work directory | `workDir` | `az://<container>/work` |
| Wave / Fusion v2 | `waveEnabled`, `fusion2Enabled` | enabled; for production use `Standard_E16d_v5` or larger with ≥200 GB local temp disk; no Premium SSDv2/Ultra disks for Fusion |
| VMs type | `forge.vmType` | set it explicitly — pick a `d` size such as `Standard_E16d_v5` (the docs list `Standard_D4_v3` as the default, the API spec `Standard_D4s_v3`) |
| VMs count | `forge.vmCount` | max VMs under autoscale |
| Autoscale | `forge.autoScale` | on (scales 0 → VMs count) |
| Head job CPUs / memory | `headJobCpus`, `headJobMemoryMb` | optional; memory in MiB, minimum 3584 |
| Subnet ID | `subnetId` | optional, Entra only: `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet>`. With a subnet, Forge pools default to **no public IPs** (`usePrivateAddress: true`), so the subnet needs outbound connectivity such as a NAT gateway; set `usePrivateAddress: false` to keep public IPs |
| Managed identity | head: `managedIdentityClientId` + `managedIdentityHeadResourceId`; worker: `managedIdentityPoolClientId` + `managedIdentityPoolResourceId` | resource IDs required for Forge |
| Container registry credentials | `forge.containerRegIds` | ACR in the same region, if private images |
| Dispose resources | `forge.disposeOnDeletion` | on (deletes pools when the CE is deleted) |
| Max wallclock time | `jobMaxWallClockTime` | default `7d`, up to 180 days |
| Token duration | `tokenDuration` | **default `12h`** — set it at least as long as the longest expected run (e.g. match Max wallclock `7d`) |
| Job cleanup | `deleteJobsOnCompletionEnabled`, `deleteTasksOnCompletion`, `terminateJobsOnCompletion` | defaults: delete jobs **off**, delete tasks **on**, terminate jobs **on** |

**Manual mode** — use it for low-priority/spot nodes or custom images (Forge creates dedicated nodes only). The user creates a pool first (portal: Batch account > Pools > Add) following https://docs.seqera.io/platform-cloud/compute-envs/azure-batch#create-a-nextflow-compatible-azure-batch-pool. Key pool settings: image `microsoft-dsvm` / `ubuntu-hpc` / `2204`, Docker-compatible container config, autoscale with a 5-minute evaluation interval, task slots = vCPUs, and — without Fusion — a start task that installs `azcopy` on every node (resource file `https://nf-xpack.seqera.io/azcopy/linux_amd64_10.8.0/azcopy` saved as `azcopy`). Manual mode doesn't attach a subnet, so set the VNet/subnet on the pool itself. Then set Config mode **Manual**, the **Compute pool name**, and the **Managed identity client ID** if the pool has a user-assigned identity. Manual CEs use a **Jobs cleanup policy** (Always / Never / On success) instead of the Forge toggles.

Environment variables can't be edited after creation; use Seqera pipeline secrets for secrets.

UI path: workspace > **Compute Environments** > **Add compute environment** > **Azure Batch**.

## Step 6: Verify

1. Poll the CE until status is `AVAILABLE`. On `ERRORED` or `INVALID`, read the message (for `INVALID`, check the credential record — rotating the Batch or Storage key in Azure invalidates a Shared key credential). Typical causes: no vCPU/pool/job quota, Storage public access disabled, missing Network Contributor on the VNet, missing Managed Identity Operator on the identity, no outbound path (NAT) from a private subnet.
2. Run a test pipeline: hand off to the `launch-workflow` skill with `https://github.com/nextflow-io/hello` on the new CE.
3. If pool nodes fail to start or tasks can't pull images, check outbound access from the subnet to container registries (quay.io, docker.io), Azure Storage, and Seqera (e.g. via a NAT gateway on the subnet).

## Critical Rules

1. **CONFIRM before changing Azure** — show every create/assign command and wait for the user's yes.
2. **NEVER handle secrets** — account keys and client secrets go straight from the user into the Seqera UI, never through the chat or the API. Don't run commands that print secrets.
3. **MATCH regions** — Storage account and Batch account in the same region.
4. **CHECK quota before creating the CE** — new Batch accounts often have none.
5. **SET Token duration** to cover the longest run — the `12h` default cuts off longer pipelines.
6. **USE Entra** when a VNet subnet or managed identity is needed; access keys support neither.
7. **KEEP Storage public network access and shared key access enabled** for Forge.
8. **SHOW the CE config** to the user before creating it.
9. **VERIFY** — the CE is only onboarded once it is `AVAILABLE` and a test pipeline succeeds.
