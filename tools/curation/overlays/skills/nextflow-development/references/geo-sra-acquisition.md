<!-- Adapted for the Nextflow plugin: generic host tools and OAuth MCP. -->
# GEO/SRA Data Acquisition

Download raw sequencing data from NCBI GEO/SRA and prepare it for nf-core pipelines.

**Use this when:** Reanalyzing published datasets, validating findings, or comparing results against public cohorts.

## Table of Contents

- [Workflow Overview](#workflow-overview)
- [Step 1: Fetch Study Information](#step-1-fetch-study-information)
- [Step 2: Review Sample Groups](#step-2-review-sample-groups)
- [Step 3: Download FASTQ Files](#step-3-download-fastq-files)
- [Step 4: Generate Samplesheet](#step-4-generate-samplesheet)
- [Step 5: Run nf-core Pipeline](#step-5-run-nf-core-pipeline)
- [Supported Pipelines](#supported-pipelines)
- [Supported Organisms](#supported-organisms)
- [Complete Example](#complete-example)
- [Troubleshooting](#troubleshooting)

---

## Workflow Overview

Example: "Find differentially expressed genes in GSE309891 (drug-treated vs control)"

Inspect study metadata, identify the available data types, confirm the desired
sample subset and reference genome, then acquire the selected reads and prepare
a samplesheet for the chosen nf-core pipeline.

All lookups use public APIs over HTTPS with no credentials:

- NCBI E-utilities: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` (stay under 3 requests per second without an API key)
- ENA Portal API: `https://www.ebi.ac.uk/ena/portal/api/`

---

## Instructions

When assisting users with GEO/SRA data acquisition:

1. **Always fetch study info first** to show the user what data is available
2. **Ask for confirmation before downloading** - Present the sample groups and sizes, then ask the user which subset to download
3. **Suggest appropriate genome and pipeline** based on the organism and data type
4. **Return to main SKILL.md workflow** after data preparation is complete

Example confirmation question:
```
Question: "Which sample group would you like to download?"
Options:
  - "RNA-Seq:PAIRED (42 samples, ~192 GB)"
  - "RNA-Seq:SINGLE (7 samples, ~11 GB)"
  - "All samples (49 samples, ~203 GB)"
```

---

## Step 1: Fetch Study Information

Get metadata about a GEO series before downloading.

1. Find the series UID in the GEO DataSets database. The search returns the
   series plus its samples and platforms; use the result whose `accession`
   equals the GSE (for series it is `200` followed by the zero-padded number,
   e.g. GSE110004 → `200110004`).

   ```bash
   curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gds&term=GSE110004%5BAccession%5D&retmode=json"
   ```

2. Fetch its summary:

   ```bash
   curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gds&id=200110004&retmode=json"
   ```

   Read these fields from `result.<uid>`:

   | Field | Meaning |
   |-------|---------|
   | `title`, `summary` | Study title and abstract ("This SuperSeries is composed of..." marks a SuperSeries) |
   | `taxon` | Organism, used to suggest the genome |
   | `n_samples` | Number of GSM samples |
   | `entrytype`, `gdstype` | Series type and assay description |
   | `bioproject` | Linked BioProject (e.g. `PRJNA432544`), used to find runs |
   | `gpl`, `pubmedids` | Platforms and linked publications |

3. If `bioproject` is empty, follow the link instead:
   `elink.fcgi?dbfrom=gds&db=bioproject&id=<uid>&retmode=json`, then
   `esummary.fcgi?db=bioproject&id=<linked id>&retmode=json` and read `project_acc`.

**Report to the user:** title, organism with suggested genome
([reference genomes](reference-genomes.md)), sample and run counts, data types,
download size (Step 2), suggested pipeline ([Supported Pipelines](#supported-pipelines))
and a summary trimmed to ~300 characters. Offer to save this as JSON if they
want a record.

---

## Step 2: Review Sample Groups

List every run with the ENA file report for the BioProject. It also accepts an
SRA study (`SRP…`), experiment, sample or run accession, but not a GSE.

```bash
curl -s "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=PRJNA432544&result=read_run&format=tsv&fields=run_accession,sample_alias,sample_title,library_strategy,library_layout,scientific_name,read_count,base_count,fastq_ftp,fastq_bytes,fastq_md5,secondary_study_accession" > runs.tsv
```

| Field | Meaning |
|-------|---------|
| `run_accession` | SRR/ERR/DRR run ID |
| `sample_alias` | GSM accession for GEO submissions |
| `sample_title` | GEO sample title, often the condition and replicate |
| `library_strategy`, `library_layout` | e.g. `RNA-Seq`, `PAIRED` |
| `fastq_ftp` | `;`-separated FASTQ locations (one for single-end, two for paired) |
| `fastq_bytes`, `fastq_md5` | `;`-separated sizes and checksums, same order |
| `secondary_study_accession` | SRA study (`SRP…`); a SuperSeries can span several |

Group runs by `library_strategy:library_layout` and total the bytes:

```bash
awk -F'\t' 'NR>1 { n=split($10,b,";"); s=0; for (i=1;i<=n;i++) s+=b[i];
  k=$4":"$5; c[k]++; sz[k]+=s; t+=s }
  END { for (k in c) printf "%-22s %4d runs %8.1f GB\n", k, c[k], sz[k]/1e9;
        printf "%-22s %4d runs %8.1f GB\n", "TOTAL", NR-1, t/1e9 }' runs.tsv
```

**Example output (GSE110004):**
```
RNA-Seq:PAIRED           42 runs    192.5 GB
RNA-Seq:SINGLE            7 runs     11.0 GB
TOTAL                    49 runs    203.4 GB
```

Present each group with its run count, GSM range (`GSM2976181-GSM2976187` when
consecutive, otherwise the first GSM and a count) and size.

**NCBI alternative.** If ENA has no record yet, get runs from SRA:
`esearch.fcgi?db=sra&term=<SRP or GSM accession>&retmax=1000&retmode=json`, then
`efetch.fcgi?db=sra&id=<comma-separated ids>&rettype=runinfo&retmode=csv`.
The runinfo CSV currently has no header row; its columns are, in order:
`Run, ReleaseDate, LoadDate, spots, bases, spots_with_mates, avgLength, size_MB,
AssemblyName, download_path, Experiment, LibraryName, LibraryStrategy,
LibrarySelection, LibrarySource, LibraryLayout, InsertSize, InsertDev, Platform,
Model, SRAStudy, BioProject, Study_Pubmed_id, ProjectID, Sample, BioSample,
SampleType, TaxID, ScientificName, SampleName, …` (`SampleName` holds the GSM).
If the first line starts with `Run,`, it is a header. Estimate download size as
`bases / 4` bytes. SRA search by GSE fails for SuperSeries; use the BioProject
route through ENA instead.

**DECISION POINT:** Review the sample groups. Decide which subset to download if the study has multiple data types.

---

## Step 3: Download FASTQ Files

Download FASTQ files from ENA (faster than SRA, already split into R1/R2).

1. Filter `runs.tsv` to the confirmed group (e.g. `RNA-Seq` and `PAIRED`).
2. Turn each `fastq_ftp` entry into an HTTPS URL by prefixing `https://`
   (e.g. `https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR635/000/SRR6357070/SRR6357070_1.fastq.gz`).
3. Download into the user-selected directory, skipping complete files, resuming
   partial ones, four at a time:

```bash
dest=<fastq-dir>; mkdir -p "$dest"
awk -F'\t' 'NR>1 && $4=="RNA-Seq" && $5=="PAIRED" { n=split($9,u,";"); for (i=1;i<=n;i++) print "https://" u[i] }' runs.tsv \
  | xargs -n 1 -P 4 curl -fsSL -C - --retry 3 -O --output-dir "$dest"
```

(`--output-dir` needs curl 7.73+; otherwise run the command from inside `$dest`.)

4. Verify checksums against `fastq_md5` and re-download any mismatch:

```bash
awk -F'\t' 'NR>1 { n=split($9,u,";"); split($11,m,";");
  for (i=1;i<=n;i++) { f=u[i]; sub(/.*\//,"",f); print m[i] "  " f } }' runs.tsv > "$dest/md5.txt"
(cd "$dest" && md5sum -c --ignore-missing md5.txt)   # macOS: compare against `md5 -r`
```

ENA names files `<run>_1.fastq.gz` and `<run>_2.fastq.gz` for paired-end and
`<run>.fastq.gz` for single-end. Re-running the download resumes an interrupted
transfer.

---

## Step 4: Generate Samplesheet

Map each downloaded run to a samplesheet row. Use the column specs in
[samplesheets](samplesheets.md#column-specs).

- **Files:** paired runs use `<run>_1.fastq.gz` and `<run>_2.fastq.gz`; single runs use `<run>.fastq.gz` (or `<run>_1.fastq.gz`). Skip runs whose files are missing and say which.
- **Sample name:** default to the run accession. Prefer the GSM (`sample_alias`) or a cleaned `sample_title` (letters, digits and underscores only) when the user wants readable names. Runs of the same GSM share one sample name so rnaseq merges them.
- **Extra columns:** rnaseq `strandedness=auto`; atacseq groups replicates under a condition name with `replicate` numbers taken from `sample_title`; sarek needs `patient` and `status` from the study metadata (ask the user).
- Use absolute paths, then [validate](samplesheets.md#validate) before running.

Report the sample count, suggested pipeline and genome.

---

## Step 5: Run nf-core Pipeline

Choose the appropriate nf-core pipeline and pin its version. Supply the user's
selected samplesheet, output destination, genome, and supported execution profile:

```bash
nextflow run nf-core/<pipeline> -r <version> -profile docker \
    --input <samplesheet> --outdir <outdir> --genome <genome>
```

**DECISION POINT:** Review and confirm:
1. Is the suggested pipeline correct?
2. Is the genome reference correct for your organism?
3. Do you need additional pipeline options?

Then return to the main SKILL.md workflow (Step 1: Environment Check) to proceed with pipeline execution.

---

## Supported Pipelines

Suggest a pipeline from the dominant `library_strategy` (upper-cased). Pipelines marked with ★ are fully supported with configs, samplesheet rules, and documentation in this skill. Others are suggested but require manual setup following nf-core documentation.

| Library Strategy | Suggested Pipeline | Support |
|------------------|--------------------|---------|
| RNA-Seq          | nf-core/rnaseq     | ★ Full  |
| ATAC-seq         | nf-core/atacseq    | ★ Full  |
| WGS/WXS          | nf-core/sarek      | ★ Full  |
| ChIP-seq         | nf-core/chipseq    | Manual  |
| Bisulfite-Seq/RRBS | nf-core/methylseq | Manual  |
| miRNA-Seq        | nf-core/smrnaseq   | Manual  |
| Amplicon         | nf-core/ampliseq   | Manual  |
| Hi-C             | nf-core/hic        | Manual  |

The same mapping is under `pipeline_suggestions` in [config/genomes.yaml](config/genomes.yaml).

---

## Supported Organisms

Common organisms and the genome to suggest:

| Organism | Genome | Notes |
|----------|--------|-------|
| Homo sapiens | GRCh38 | Human reference |
| Mus musculus | GRCm38 | iGenomes key; GRCm39 needs `--fasta`/`--gtf` |
| Saccharomyces cerevisiae | R64-1-1 | Yeast S288C |
| Drosophila melanogaster | BDGP6 | Fruit fly |
| Caenorhabditis elegans | WBcel235 | C. elegans |
| Danio rerio | GRCz10 | iGenomes key; GRCz11 needs `--fasta`/`--gtf` |
| Arabidopsis thaliana | TAIR10 | Arabidopsis |
| Rattus norvegicus | Rnor_6.0 | Rat |

More organisms are mapped in [config/genomes.yaml](config/genomes.yaml); see
[reference genomes](reference-genomes.md) for which builds are iGenomes keys.

---

## Complete Example

Reanalyze GSE110004 (yeast RNA-seq):

1. GDS esearch and esummary for `GSE110004`: SuperSeries, *Saccharomyces cerevisiae* (suggest `R64-1-1`), 49 samples, BioProject `PRJNA432544`.
2. ENA file report for `PRJNA432544`: `RNA-Seq:PAIRED` (42 runs, ~192 GB) and `RNA-Seq:SINGLE` (7 runs, ~11 GB).
3. User picks `RNA-Seq:PAIRED`; download those 84 FASTQ files and verify MD5s.
4. Build an rnaseq samplesheet with `strandedness=auto`, validate it, and continue at SKILL.md Step 1.

---

## Troubleshooting

### ENA Download Fails
If ENA downloads fail, the data may need to be fetched directly from SRA:

Install the SRA Toolkit through the user's supported package environment, retrieve
the selected run accession with `prefetch`, and convert it with `fasterq-dump --split-files`
into the user-selected destination, then compress with `gzip`.

### No SRA Runs Found
Some GEO datasets only have processed data, not raw sequencing reads. If the
GDS summary has no `bioproject`, no BioProject link, and the ENA file report
returns only a header line, the dataset has no raw data in SRA.

### SuperSeries Support
A GEO SuperSeries (summary starts "This SuperSeries is composed of...") groups
several SubSeries. Its `bioproject` is an umbrella project; the ENA file report
for it returns runs from every SubSeries, possibly under several SRA studies
(`secondary_study_accession`).

Example: GSE110004 is a SuperSeries that links to BioProject PRJNA432544.

### Genome Not Recognized
If the organism is not in the genome mapping, ask the user for the reference and
supply it with `--fasta` and `--gtf`. See [reference genomes](reference-genomes.md).

---

## Requirements

- `curl` and `awk`; `md5sum` (or `md5` on macOS) for checksums
- Network access to NCBI and ENA
- SRA Toolkit only for the SRA fallback
