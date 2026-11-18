---
name: nextflow-development
description: Run nf-core bioinformatics pipelines (rnaseq, sarek, atacseq) on sequencing data. Use when analyzing RNA-seq, WGS/WES, or ATAC-seq data—either local FASTQs or public datasets from GEO/SRA. Triggers on nf-core, Nextflow, FASTQ analysis, variant calling, gene expression, differential expression, GEO reanalysis, GSE/GSM/SRR accessions, or samplesheet creation.
---
<!-- Adapted for the Nextflow plugin: generic host tools and OAuth MCP. -->

## Using this skill

Use the tools and runtimes available in the user's session. Establish the
pipeline, input data and execution environment from their request or current
context. Use user-selected locations for files and results. Consult companion
skills and the bundled references; each step below links the procedure to follow
with ordinary shell tools (`curl`, `find`, `awk`, `nextflow`).

For Seqera operations, read the [MCP connection](../launch-workflow/references/seqera-mcp/README.md) connection reference. Any `platform_*` examples
describe API operations. Discover their exact names and parameter schemas with
`search_seqera_api`, then invoke `call_seqera_api` using those schemas. The host
manages OAuth for the connected MCP server.


# nf-core Pipeline Deployment

Run nf-core bioinformatics pipelines on local or public sequencing data.

**Target users:** Bench scientists and researchers without specialized bioinformatics training who need to run large-scale omics analyses—differential expression, variant calling, or chromatin accessibility analysis.

## Workflow Checklist

```
- [ ] Step 0: Acquire data (if from GEO/SRA)
- [ ] Step 1: Environment check (MUST pass)
- [ ] Step 2: Select pipeline (confirm with user)
- [ ] Step 3: Run test profile (MUST pass)
- [ ] Step 4: Create samplesheet
- [ ] Step 5: Configure & run (confirm genome with user)
- [ ] Step 6: Verify outputs
```

---

## Step 0: Acquire Data (GEO/SRA Only)

**Skip this step if user has local FASTQ files.**

For public datasets, fetch from GEO/SRA first. See [geo-sra-acquisition](references/geo-sra-acquisition.md) for the full workflow.

**Quick start:** look up the series with NCBI E-utilities to get its organism
and BioProject, list its runs and FASTQ URLs with the ENA file report, group
them by library strategy and layout, download the confirmed group to the user's
selected directory, then build the samplesheet from the downloaded files.

**DECISION POINT:** After fetching study info, confirm with user:
- Which sample subset to download (if multiple data types)
- Suggested genome and pipeline

Then continue to Step 1.

---

## Step 1: Environment Check

**Run first. Pipeline will fail without passing environment.**

Follow the [environment check](references/environment-check.md): Docker, Nextflow
and Java are critical; CPU, memory, disk and network produce warnings.

All critical checks must pass. If any fail, provide fix instructions:

### Docker issues

| Problem | Fix |
|---------|-----|
| Not installed | Install from https://docs.docker.com/get-docker/ |
| Permission denied | `sudo usermod -aG docker $USER` then re-login |
| Daemon not running | `sudo systemctl start docker` |

Read `install-nextflow` for current runtime prerequisites.

### Nextflow issues

| Problem | Fix |
|---------|-----|
| Not installed | Install with the official Nextflow instructions for the user's operating system |
| Version < 23.04 | `nextflow self-update` |

### Java issues

| Problem | Fix |
|---------|-----|
| Not installed / < 17 | `sudo apt install openjdk-17-jdk` |

**Do not proceed until all checks pass.** For HPC/Singularity, see troubleshooting.

---

## Step 2: Select Pipeline

**DECISION POINT: Confirm with user before proceeding.**

| Data Type | Pipeline | Version | Goal |
|-----------|----------|---------|------|
| RNA-seq | `rnaseq` | 3.22.2 | Gene expression |
| WGS/WES | `sarek` | 3.7.1 | Variant calling |
| ATAC-seq | `atacseq` | 2.1.2 | Chromatin accessibility |

Auto-detect from data: follow [data-type detection](references/data-type-detection.md)
to count FASTQ/BAM/CRAM files and score file and directory names against each
pipeline's hints.

For pipeline-specific details:
- [rnaseq](references/pipelines/rnaseq.md)
- [sarek](references/pipelines/sarek.md)
- [atacseq](references/pipelines/atacseq.md)

---

## Step 3: Run Test Profile

**Validates environment with small data. MUST pass before real data.**

Select a writable test-output destination through `--outdir`; inspect the actual
reports the selected test produces.

```bash
nextflow run nf-core/<pipeline> -r <version> -profile test,docker
```

| Pipeline | Command |
|----------|---------|
| rnaseq | `nextflow run nf-core/rnaseq -r 3.22.2 -profile test,docker ` |
| sarek | `nextflow run nf-core/sarek -r 3.7.1 -profile test,docker ` |
| atacseq | `nextflow run nf-core/atacseq -r 2.1.2 -profile test,docker ` |

Verify:
Check the selected run's completion status and locate its MultiQC report from the actual output inventory.

If test fails, see troubleshooting.

---

## Step 4: Create Samplesheet

### Generate automatically

Follow [samplesheets](references/samplesheets.md) to:
- Discover FASTQ/BAM/CRAM files
- Pair R1/R2 reads by file-name markers
- Infer sample, lane, patient, tumor/normal status and replicate
- Validate before writing, using absolute paths

**For sarek:** ask the user for tumor/normal status when the name does not show it.

### Validate existing samplesheet

Check the user's samplesheet against the [validation rules](references/samplesheets.md#validate)
for the chosen pipeline and report errors by row before running.

### Samplesheet formats

**rnaseq:**
```csv
sample,fastq_1,fastq_2,strandedness
SAMPLE1,USER_R1_FQ_GZ,USER_R2_FQ_GZ,auto
```

**sarek:**
```csv
patient,sample,lane,fastq_1,fastq_2,status
patient1,tumor,L001,USER_TUMOR_R1_FQ_GZ,USER_TUMOR_R2_FQ_GZ,1
patient1,normal,L001,USER_NORMAL_R1_FQ_GZ,USER_NORMAL_R2_FQ_GZ,0
```

**atacseq:**
```csv
sample,fastq_1,fastq_2,replicate
CONTROL,USER_CTRL_R1_FQ_GZ,USER_CTRL_R2_FQ_GZ,1
```

---

## Step 5: Configure & Run

### 5a. Check genome availability

Follow [reference genomes](references/reference-genomes.md) to map the organism
to a build, check whether it is an iGenomes key or already local, and download
FASTA/GTF to the user's selected directory only when requested.

Common iGenomes keys: GRCh38 (human), GRCh37 (legacy), GRCm38 (mouse), R64-1-1 (yeast), BDGP6 (fly)

### 5b. Decision points

**DECISION POINT: Confirm with user:**

1. **Genome:** Which reference to use
2. **Pipeline-specific options:**
   - **rnaseq:** aligner (star_salmon recommended, hisat2 for low memory)
   - **sarek:** tools (haplotypecaller for germline, mutect2 for somatic)
   - **atacseq:** read_length (50, 75, 100, or 150)

### 5c. Run pipeline

Supply the user's chosen samplesheet with `--input` and output destination with
`--outdir`; select values from the actual pipeline schema. The command fragment
below shows pipeline/version/execution options without assuming file locations.

```bash
nextflow run nf-core/<pipeline> \
    -r <version> \
    -profile docker \
    --genome <genome> \
    -resume
```

**Key flags:**
- `-r`: Pin version
- `-profile docker`: Use Docker (or `singularity` for HPC)
- `--genome`: iGenomes key
- `-resume`: Continue from checkpoint

**Resource limits (if needed):**
```bash
--max_cpus 8 --max_memory '32.GB' --max_time '24.h'
```

---

## Step 6: Verify Outputs

### Check completion

Check the selected run's completion status and locate its MultiQC report from the actual output inventory.

### Key outputs by pipeline

**rnaseq:**
- Gene-count matrix reported by the pipeline
- TPM matrix reported by the pipeline

**sarek:**
- Variant calls in VCF format
- Analysis-ready alignments in BAM format

**atacseq:**
- Peak calls
- Coverage tracks

---

## Quick Reference

For common exit codes and fixes, see troubleshooting.

### Resume failed run

```bash
nextflow run nf-core/<pipeline> -resume
```

---

## References

- [geo-sra-acquisition](references/geo-sra-acquisition.md) - Downloading public GEO/SRA data
- [environment-check](references/environment-check.md) - Pre-flight checks
- [data-type-detection](references/data-type-detection.md) - Suggesting a pipeline from files
- [samplesheets](references/samplesheets.md) - Building and validating samplesheets
- [reference-genomes](references/reference-genomes.md) - Choosing and downloading references
- [troubleshooting](references/troubleshooting.md) - Common issues and fixes
- [installation](references/installation.md) - Environment setup
- [rnaseq](references/pipelines/rnaseq.md) - RNA-seq pipeline details
- [sarek](references/pipelines/sarek.md) - Variant calling details
- [atacseq](references/pipelines/atacseq.md) - ATAC-seq details
- `references/config/pipelines/*.yaml` - Per-pipeline samplesheet columns, decision points, outputs and resources

---

## Disclaimer

The bundled references and configurations cover three nf-core pipelines:
rnaseq, sarek, and atacseq. For another pipeline, inspect its own documentation
and schema rather than assuming these references apply.

It is intended for educational and research purposes and should not be considered production-ready without appropriate validation for your specific use case. Users are responsible for ensuring their computing environment meets pipeline requirements and for verifying analysis results.

Anthropic does not guarantee the accuracy of bioinformatics outputs, and users should follow standard practices for validating computational analyses. This integration is not officially endorsed by or affiliated with the nf-core community.

## Attribution

When publishing results, cite the appropriate pipeline. Citations are available in each nf-core repository's CITATIONS.md file (e.g., https://github.com/nf-core/rnaseq/blob/3.22.2/CITATIONS.md).

## Licenses

- **nf-core pipelines:** MIT License (https://nf-co.re/about)
- **Nextflow:** Apache License, Version 2.0 (https://www.nextflow.io/about-us.html)
- **NCBI SRA Toolkit:** Public Domain (https://github.com/ncbi/sra-tools/blob/master/LICENSE)
