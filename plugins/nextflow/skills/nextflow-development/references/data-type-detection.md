# Data Type Detection

Suggest rnaseq, sarek or atacseq from the user's files. This is a heuristic on
file and directory names only; always confirm the pipeline with the user.

## 1. Inventory the directory

Search recursively (follow symlinks, count each real file once):

| Type | Extensions (case-insensitive) |
|------|-------------------------------|
| FASTQ | `.fastq.gz`, `.fq.gz`, `.fastq`, `.fq` |
| BAM | `.bam` |
| CRAM | `.cram` |

```bash
find -L <data-dir> -type f \( -iname '*.fastq.gz' -o -iname '*.fq.gz' -o -iname '*.fastq' -o -iname '*.fq' \) | wc -l
find -L <data-dir> -type f -iname '*.bam'  | wc -l
find -L <data-dir> -type f -iname '*.cram' | wc -l
du -sh <data-dir>
```

Stop if there are no FASTQ, BAM or CRAM files. When several types exist, the
input type is FASTQ, then BAM, then CRAM, in that order.

## 2. Score each pipeline

Lower-case all file names and subdirectory names (relative to the data
directory). Add points per pipeline; each hint list scores once, on its first
match.

| Signal | rnaseq | sarek | atacseq |
|--------|--------|-------|---------|
| File name contains a `detection_hints.filename` entry | +10 each | +10 each | +10 each |
| Subdirectory contains a `detection_hints.directory` entry | +15 each | +15 each | +15 each |
| Has a file type in `samplesheet.input_types` | +5 (FASTQ) | +5 per FASTQ/BAM/CRAM present | +5 (FASTQ) |
| Any name contains `rna`, `rnaseq`, `mrna`, `expression`, `transcript`, `counts` | +15 | | |
| Any file name contains `tumor`, `tumour`, `cancer`, `met`, `primary`, `normal`, `germline`, `blood`, `control` | | +20 | |
| Any name contains `wgs`, `wes`, `exome`, `dna`, `variant`, `snp`, `indel` | | +10 | |
| Any name contains `atac`, `atacseq`, `chromatin`, `accessibility`, `peak`, `macs` | | | +20 |

The `detection_hints` lists live in
[config/pipelines/rnaseq.yaml](config/pipelines/rnaseq.yaml),
[config/pipelines/sarek.yaml](config/pipelines/sarek.yaml) and
[config/pipelines/atacseq.yaml](config/pipelines/atacseq.yaml).

Recommend the highest score. BAM or CRAM input points to sarek, the only one of
the three that accepts them. A tie or all-low scores means the names carry no
signal: ask the user what assay produced the data.

## 3. Report

Show the file counts, total size, each pipeline's score with the matched hints,
and the recommended pipeline with its pinned version (`version` in the YAML).
Then continue with the [environment check](environment-check.md), the test
profile (`test_profile.command` in the YAML) and the [samplesheet](samplesheets.md).

For public data, the SRA `library_strategy` is a stronger signal than file
names; see [geo-sra-acquisition](geo-sra-acquisition.md#supported-pipelines).
