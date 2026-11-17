# Samplesheets

Build or validate a samplesheet for rnaseq, sarek or atacseq from the user's
read files. Write absolute paths, validate before writing, then show the user
the first rows for confirmation. Column specs, defaults and allowed values also
live under `samplesheet.columns` in `references/config/pipelines/<pipeline>.yaml`.

## Contents
- [Column specs](#column-specs)
- [Discover files](#discover-files)
- [Pair R1 and R2](#pair-r1-and-r2)
- [Infer sample metadata](#infer-sample-metadata)
- [Pipeline-specific rules](#pipeline-specific-rules)
- [Validate](#validate)

## Column specs

**rnaseq** (FASTQ only)

| Column | Required | Value |
|--------|----------|-------|
| `sample` | Yes | Sample ID; rows sharing a name are merged (lanes, technical replicates) |
| `fastq_1` | Yes | Absolute R1 path |
| `fastq_2` | No | Absolute R2 path; empty for single-end |
| `strandedness` | Yes | `auto` (default), `forward`, `reverse`, `unstranded` |

**sarek** (FASTQ, BAM or CRAM)

| Column | Required | Value |
|--------|----------|-------|
| `patient` | Yes | Subject ID; groups tumor and normal samples |
| `sample` | Yes | Sample ID, unique within a patient |
| `lane` | For FASTQ | Lane ID, default `L001` |
| `fastq_1`, `fastq_2` | FASTQ input | Absolute R1/R2 paths |
| `bam`, `bai` | BAM input | Absolute BAM and index paths |
| `cram`, `crai` | CRAM input | Absolute CRAM and index paths |
| `status` | No | `0` normal (default), `1` tumor; required for somatic calling |

**atacseq** (paired-end FASTQ only)

| Column | Required | Value |
|--------|----------|-------|
| `sample` | Yes | Condition/group name; replicates share it |
| `fastq_1` | Yes | Absolute R1 path |
| `fastq_2` | Yes | Absolute R2 path |
| `replicate` | Yes | Integer, default `1`, unique within a sample |

Write only columns that apply to the input type, in the order above.

## Discover files

Search recursively for the input type (extensions in
[data-type detection](data-type-detection.md#1-inventory-the-directory)),
follow symlinks, and drop duplicates that resolve to the same real file.
Confirm the chosen pipeline accepts the input type (only sarek takes BAM/CRAM).

For each BAM/CRAM, look for its index next to it: `<file>.bai` or
`<stem>.bai` for BAM, `<file>.crai` or `<stem>.crai` for CRAM. Warn about any
alignment file without an index.

## Pair R1 and R2

Classify each FASTQ by the strongest read marker in its file name
(case-insensitive). If the R2 score beats the R1 score it is R2; otherwise any
R1 match, or no marker at all, makes it R1 (single-end).

| Marker regex | Example | Score |
|--------------|---------|-------|
| `_R[12]_\d{3}` | `S1_L001_R1_001.fastq.gz` (Illumina) | 10 |
| `_R[12]([_.]\|$)` | `S1_R1.fq.gz` | 8 |
| `\.R[12]([_.]\|$)` | `S1.R1.fastq` | 8 |
| `_R[12]\.f` | `S1_R1.fastq` | 6 |
| `_[12]([_.]\|$)` | `SRR123_1.fastq.gz` | 5 |
| `_[12]\.f` | `S1_2.fq` | 4 |

Pair R1 and R2 files that produce the same sample key (below), plus the lane
when it is not `L001`. Report R1 files with no partner as single-end, and treat
an R2 with no R1 as an error.

## Infer sample metadata

Derive the sample key from the file name:

1. Strip the extension (`.fastq.gz`, `.fq.gz`, `.fastq`, `.fq`, `.bam`, `.cram`).
2. Lane: take `L(\d{3})` between `_` or `.` separators as `L<nnn>` (default `L001`), and remove it.
3. Cut at the first read marker from the table above, dropping everything after it.
4. Trim trailing `_`, `.` and `-`; collapse runs of separators into one `_`.

`SAMPLE1_S1_L002_R1_001.fastq.gz` gives sample `SAMPLE1_S1`, lane `L002`.

**Patient** (sarek): the first match at the start of the sample key, otherwise
the sample key itself:
`^(P\d+)[-_]`, `^(patient\d+)[-_]`, `^(TCGA-\w+-\w+)`, `^([A-Z]{2,3}\d{3,})[-_]`.

**Tumor/normal status** (sarek): test the sample name, case-insensitive.
Tumor keywords win when both match.

- Tumor (`1`): words `tumor`, `tumour`, `metastasis`, `met`, `primary`, `cancer`, `malignant`; or `T` as a token (`_T_`, `-T1` at the end, `T1_` at the start).
- Normal (`0`): words `normal`, `germline`, `blood`, `pbmc`, `control`, `healthy`, `matched`; or `N` as a token in the same positions.

Ask the user for the status of any sample that matches neither; default to `0`
only if they say so.

**Replicate** (atacseq): after removing the read marker, take the first match of
`[_.]rep(\d+)`, `[_.]replicate(\d+)`, then `[-_](\d+)$`. Remove that suffix from
the name so replicates share one `sample` value. Without a match, number rows of
the same sample 1, 2, 3 in file order.

Show inferred names, patients, statuses and replicates to the user before
writing; file names are often ambiguous.

## Pipeline-specific rules

- **rnaseq:** set `strandedness` to `auto` unless the user knows the kit (see [rnaseq](pipelines/rnaseq.md)).
- **sarek:** each patient with a tumor (`1`) should have a normal (`0`); otherwise warn that somatic calling works best with a matched normal, or use tumor-only mode. Choose `--tools` from the statuses (germline vs somatic, see [sarek](pipelines/sarek.md)).
- **atacseq:** every row needs `fastq_2`. Warn when a sample has fewer than two replicates (consensus peaks need 2+).

## Validate

Use the same rules for a generated sheet and for a user-provided one (read it
as CSV with a header row). Report errors by row number, counting the header as
row 1.

Errors (do not run until fixed):

- Empty samplesheet or unknown pipeline.
- A required column missing or empty with no default.
- A path in `fastq_1`, `fastq_2`, `bam`, `bai`, `cram` or `crai` that does not exist or is not a regular file.
- A value outside the allowed set (`strandedness`, `status`).
- `fastq_2` set without `fastq_1`.
- atacseq: missing `fastq_2`, or a duplicate replicate number within a sample.

Warnings (show, then continue if the user agrees):

- Single-end rows (`fastq_1` without `fastq_2`).
- Duplicate `sample` values (fine for multi-lane data; confirm the grouping).
- sarek: tumor without a matched normal, or rows with no status.
- atacseq: a sample with only one replicate.

Quick checks from the shell:

```bash
head -n 4 samplesheet.csv
# Every listed file exists (skips empty cells and the header)
awk -F, 'NR>1 { for (i=1;i<=NF;i++) if ($i ~ /^\//) print $i }' samplesheet.csv \
  | while read -r f; do [ -f "$f" ] || echo "missing: $f"; done
```
