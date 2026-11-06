---
name: onboard-google-batch
description: Onboard a Google Cloud project to Nextflow Platform as a Google Cloud Batch compute environment. Use when the user wants to connect GCP to Seqera, set up a Google Batch compute environment, create the service accounts, IAM roles, Workload Identity Federation, or credentials Seqera needs for Google Cloud, or run pipelines on GCP through Seqera.
---

## Using this skill

For Nextflow Platform operations, read the [MCP connection](../launch-workflow/references/seqera-mcp/README.md) reference. Any `platform_*` names below describe API operations: discover their exact names and parameter schemas with `search_seqera_api`, then invoke `call_seqera_api`. The host manages OAuth for the connected MCP server.

# Onboard Google Cloud Batch to Nextflow Platform

Set up everything Nextflow Platform needs to run Nextflow pipelines on Google Cloud Batch: enabled APIs, a GCS work bucket, service accounts with the right roles, a Seqera Google credential, and a Google Cloud Batch compute environment (CE).

Source docs: https://docs.seqera.io/platform-cloud/compute-envs/google-cloud-batch. If anything below disagrees with the live docs, the docs win.

## Main Flow

1. **Pick the Platform workspace** the CE will live in.
2. **Gather decisions** — project, location, credential type, Spot, Fusion.
3. **Prepare Google Cloud** — APIs, bucket, service accounts and roles.
4. **Create the Platform credential** — Workload Identity Federation (recommended) or a service account key.
5. **Create the compute environment.**
6. **Verify** — CE reaches `AVAILABLE`, then run a test pipeline.

Before running any command that **creates or changes** GCP resources, show the user the exact command and wait for a yes.

## Step 1: Pick the Platform Workspace

Use `search_seqera_api` to find the exact operation names (e.g. "list workspaces", "list credentials", "create compute environment"), then `call_seqera_api`. Ask which organization/workspace to use and record its `workspaceId`. Check existing CEs (`platform_list_compute_envs`) first — if a working Google Batch CE already exists, ask whether a new one is needed.

## Step 2: Gather Decisions

| Decision | Options | Recommended |
|---|---|---|
| Project | existing or new, billing enabled | dedicated project |
| Location | a region where the Batch API is available | near the data; the bucket and compute can be in any region |
| Credential | **Workload Identity Federation** (no key) or **service account JSON key** | **WIF** for production |
| Service accounts | one SA for everything, or separate credential SA and head job SA | separate for production, one is fine to start |
| Spot | on/off | on for cost; since Nextflow 24.10 Spot reclamations aren't retried on Google by default, so configure a retry strategy (`errorStrategy = 'retry'` with `maxRetries`). Reclaimed tasks exit with code 50001 |
| Wave + Fusion v2 | on/off | **on** |

Check the gcloud CLI:

```bash
gcloud --version
gcloud auth list
gcloud config get-value project
```

Confirm the project with the user. If gcloud isn't set up, the user can follow along in the console with the same values.

## Step 3: Prepare Google Cloud

### 3a. Enable APIs

```bash
gcloud services enable batch.googleapis.com compute.googleapis.com storage-api.googleapis.com --project <project>
```

### 3b. Work bucket

Regional, Standard class, uniform access, public access prevention on:

```bash
gcloud storage buckets create gs://<bucket> --project <project> --location <region> \
  --default-storage-class STANDARD --uniform-bucket-level-access --public-access-prevention
```

### 3c. Service accounts

Don't use the default Compute Engine service account — it has `roles/editor`.

```bash
gcloud iam service-accounts create seqera-platform --project <project> --display-name "Nextflow Platform"
gcloud iam service-accounts create seqera-head-job --project <project> --display-name "Seqera head job"   # skip if using one SA
```

**Credential SA** (submits and monitors the head job, lists buckets, reads logs):

| Role | Scope |
|---|---|
| `roles/batch.jobsEditor` | project |
| `roles/logging.viewer` | project |
| `roles/iam.serviceAccountUser` | on the head job SA |
| `roles/storage.bucketViewer` | project (Seqera needs `storage.buckets.list`, which bucket-level grants can't give) |
| `roles/storage.objectViewer` | work bucket and any bucket that receives reports |
| `roles/secretmanager.admin` | project — only if pipelines use Seqera secrets |

**Head job SA** (runs the Nextflow head job and tasks):

| Role | Scope |
|---|---|
| `roles/batch.agentReporter` | project |
| `roles/batch.jobsEditor` | project |
| `roles/logging.logWriter` | project |
| `roles/iam.serviceAccountUser` | on itself |
| `roles/storage.objectUser` | work bucket and publish bucket |
| `roles/storage.objectViewer` | input-data buckets |
| `roles/storage.bucketViewer` | work and input buckets — **required with Fusion** (`storage.buckets.get`) |
| `roles/secretmanager.secretAccessor` | project — only with Seqera secrets |
| `roles/serviceusage.serviceUsageConsumer` | project — only with requester-pays buckets |

`roles/storage.bucketViewer` is a Beta role. If the org forbids Beta roles, use a custom role with `storage.buckets.get` and `storage.buckets.list`. Without `storage.buckets.get`, Fusion reports the bucket as not found rather than as a permission error.

With one SA, grant both lists to it. If the project needs no access restrictions, `roles/storage.admin` on the project replaces the storage rows for both.

Project-level grant pattern:

```bash
gcloud projects add-iam-policy-binding <project> \
  --member "serviceAccount:<sa-email>" --role <role>
```

Bucket-level and SA-level grants:

```bash
gcloud storage buckets add-iam-policy-binding gs://<bucket> --member "serviceAccount:<sa-email>" --role <role>
gcloud iam service-accounts add-iam-policy-binding <head-sa-email> --member "serviceAccount:<sa-email>" --role roles/iam.serviceAccountUser
```

The person creating the CE also needs `roles/batch.jobsEditor` and `roles/iam.serviceAccountViewer` on the project, and `roles/iam.serviceAccountUser` on the head job SA.

### 3d. Workload Identity Federation (recommended)

Seqera Cloud's OIDC issuer is `https://cloud.seqera.io/api` (the `issuer` advertised at `https://cloud.seqera.io/api/.well-known/openid-configuration`). For Seqera Enterprise, use the `issuer` value from `<api-url>/.well-known/openid-configuration`. It must match exactly.

The binding needs the project **number**, not the ID: `gcloud projects describe <project> --format='value(projectNumber)'`.

```bash
gcloud iam workload-identity-pools create seqera-pool --project <project> --location global --display-name "Seqera"
gcloud iam workload-identity-pools providers create-oidc seqera-provider --project <project> \
  --location global --workload-identity-pool seqera-pool \
  --issuer-uri "https://cloud.seqera.io/api" \
  --attribute-mapping "google.subject=assertion.sub"
gcloud iam service-accounts add-iam-policy-binding <sa-email> --project <project> \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/<project-number>/locations/global/workloadIdentityPools/seqera-pool/*"
```

Leave allowed audiences empty to use GCP's default, or set a custom one and use the same value as the Seqera Token audience. For Data Explorer to view files with the same credential, also grant the SA `roles/iam.serviceAccountTokenCreator` on itself (the Google Cloud CE docs page binds it to the pool `principalSet` instead; if Data Explorer still fails with `iam.serviceAccounts.signBlob` denied, add that binding too).

`/*` trusts every Seqera token the pool accepts. For production, recommend limiting it to one workspace by binding `--member "principal://iam.googleapis.com/projects/<project-number>/locations/global/workloadIdentityPools/seqera-pool/subject/org:<ORG_ID>:wsp:<WORKSPACE_ID>:workflow"` instead.

## Step 4: Create the Platform Credential

- **WIF** — no secret, so you may create it via the API (look up the body with `search_seqera_api`, provider `google`). Fields (API keys `serviceAccountEmail`, `workloadIdentityProvider`, `tokenAudience`): Service account email; Workload Identity Provider `projects/<project-number>/locations/global/workloadIdentityPools/seqera-pool/providers/seqera-provider`; Token audience (only if you set a custom one).
- **Service account key** — the key is a secret. The user creates it (**IAM & Admin > Service Accounts** > select the SA > **Keys > Add key > Create new key** > **JSON** > **Create**) and pastes it into Nextflow Platform themselves: workspace > **Credentials** > **Add credentials** > Provider **Google**. Seqera only accepts `"type": "service_account"` files; it rejects `external_account` files, keys with a non-Google `token_uri`, and keys whose `universe_domain` isn't `googleapis.com`. Don't run `gcloud iam service-accounts keys create` yourself and never read the key file.

List credentials and record the `credentialsId`.

## Step 5: Create the Compute Environment

Look up the create-CE schema with `search_seqera_api` (platform `google-batch`). Build the config and **show it to the user before submitting**:

| Field | API field | Value |
|---|---|---|
| Name | `name` | e.g. `google-batch-<region>` |
| Platform | `platform` | `google-batch` |
| Credentials | `credentialsId` | from Step 4 |
| Location | `location` | region from Step 2 |
| Work directory | `workDir` | `gs://<bucket>/work` |
| Wave / Fusion v2 | `waveEnabled`, `fusion2Enabled` | enabled (Fusion requires Wave). Without an instance template, Nextflow requests a 375 GB scratch disk per task: `local-ssd` on families that support it, otherwise a persistent disk or Hyperdisk. For files over 100 GB set `disk = [request: 750.GB, type: 'local-ssd']`. An instance template must include a 375 GB `local-ssd` disk named `fusion` |
| Spot | `spot` | from Step 2 |
| Service account email | `serviceAccount` | head job SA — **always set it**. If empty, the head job runs as the credential SA (WIF) or as the Compute Engine default SA with `roles/editor` (SA key) |
| VPC + Subnet | `network`, `subnetwork` | set together; required for `usePrivateAddress` and `networkTags` |
| Head job CPUs / memory | `headJobCpus`, `headJobMemoryMb` | memory in MiB, minimum 3584 — size it (below) |
| Instance type | `machineType` | optional default machine type; per-process `machineType` overrides it |
| Boot disk size / image | `bootDiskSizeGb`, `bootDiskImage` | optional |
| Instance templates | `headJobInstanceTemplate`, `computeJobsInstanceTemplate` | optional; template values override the CE's |

Head job sizing — the default is too small for production, and a head job that runs out of memory fails the whole pipeline:

| Pipeline size | CPUs | Memory |
|---|---|---|
| up to 100 tasks | 2 | 4 GB |
| 100–500 tasks | 4 | 8 GB |
| 500+ tasks | 8 | 16 GB (+ head job env var `NXF_JVM_ARGS="-Xms4g -Xmx12g"`) |

A head job instance template overrides these values.

Environment variables can't be edited after the CE is created — put secrets in Nextflow Platform pipeline secrets, not CE env vars.

UI path: workspace > **Compute Environments** > **New Environment** (newer UI: **Add compute environment**) > target platform **Google Cloud Batch**.

## Step 6: Verify

1. Poll the CE until status is `AVAILABLE`. On `ERRORED` or `INVALID`, read the message; for `INVALID`, check the credential record. For WIF, `AVAILABLE` only means the credential is well-formed — the test pipeline is what proves the trust setup.
2. Run a test pipeline: hand off to the `launch-workflow` skill with `https://github.com/nextflow-io/hello` on the new CE.
3. WIF failures at run time — check in order: SA roles, `workloadIdentityUser` binding, issuer URL matches exactly, token audience matches.
4. Jobs that never start often mean a regional CPU/SSD quota or a machine type unavailable in the location.

## Critical Rules

1. **CONFIRM before changing GCP** — show every create/bind command and wait for the user's yes.
2. **NEVER handle secrets** — don't create, read, or paste service account keys. The user adds key-based credentials in the Seqera UI. Prefer WIF, which has no key.
3. **DON'T use the default Compute Engine SA** — it has `roles/editor`. Always set **Service account email** on the CE, or a key-based CE silently falls back to it.
4. **GRANT `storage.buckets.list` at project level** for the credential SA, and `storage.buckets.get` when Fusion is on.
5. **SIZE the head job** for the pipeline; the default is not enough for production.
6. **SHOW the CE config** to the user before creating it.
7. **VERIFY** — the CE is only onboarded once it is `AVAILABLE` and a test pipeline succeeds.
