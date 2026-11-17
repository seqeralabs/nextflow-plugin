# Reference Genomes

Pick a reference for the user's organism, check whether it is already local,
and download it only when the user asks. Confirm the genome with the user
before any run.

## Organism to genome

[config/genomes.yaml](config/genomes.yaml) maps organism names as they appear
in GEO/SRA (`ScientificName`, GEO `taxon`) to a suggested build, NCBI taxid and
aliases. Match the organism exactly, then case-insensitively, then against the
aliases. Not every suggested build there is an iGenomes key: use the table
below to decide between `--genome` and `--fasta`/`--gtf`.

## iGenomes keys

nf-core pipelines resolve `--genome <key>` through their `conf/igenomes.config`
from the public `s3://ngi-igenomes/igenomes/` bucket. Checked keys:

| Key | Organism | UCSC equivalent | Bucket path under `igenomes/` |
|-----|----------|---------|-------------------------------|
| `GRCh38` | Human | hg38 | `Homo_sapiens/NCBI/GRCh38` |
| `GRCh37` | Human (legacy) | hg19 | `Homo_sapiens/Ensembl/GRCh37` |
| `GRCm38` | Mouse | mm10 | `Mus_musculus/Ensembl/GRCm38` |
| `R64-1-1` | Yeast S288C | sacCer3 | `Saccharomyces_cerevisiae/Ensembl/R64-1-1` |
| `BDGP6` | Fruit fly | dm6 | `Drosophila_melanogaster/Ensembl/BDGP6` |
| `WBcel235` | C. elegans | ce11 | `Caenorhabditis_elegans/Ensembl/WBcel235` |
| `GRCz10` | Zebrafish | danRer10 | `Danio_rerio/Ensembl/GRCz10` |
| `Rnor_6.0` | Rat | rn6 | `Rattus_norvegicus/Ensembl/Rnor_6.0` |
| `TAIR10` | Arabidopsis | | `Arabidopsis_thaliana/Ensembl/TAIR10` |
| `CanFam3.1` | Dog | canFam3 | `Canis_familiaris/Ensembl/CanFam3.1` |
| `IRGSP-1.0` | Rice | | `Oryza_sativa_japonica/Ensembl/IRGSP-1.0` |

These newer builds are **not** iGenomes keys: GRCm39 (mouse), GRCz11
(zebrafish), GRCg6a (chicken), Sscrofa11.1 (pig), ARS-UCD1.2 (cow). For them, or
when the user wants current annotation (iGenomes GTFs are old; GENCODE is
preferred for human/mouse RNA-seq), download FASTA and GTF from Ensembl or
GENCODE and pass `--fasta` and `--gtf` instead of `--genome`. The pipeline's own
`conf/igenomes.config` is the authority; check it when in doubt.

## Check what is available

A genome counts as local when `genome.fa` exists in the user's reference
directory (`genes.gtf` alongside it for RNA-seq). List what the bucket holds for
a build without credentials:

```bash
curl -s "https://ngi-igenomes.s3.amazonaws.com/?list-type=2&delimiter=/&prefix=igenomes/Homo_sapiens/NCBI/GRCh38/Sequence/" \
  | grep -o '<Prefix>[^<]*</Prefix>'
```

## Download (only on request)

Each build keeps the same layout under its bucket path:

| Component | Path | Use |
|-----------|------|-----|
| `fasta` | `Sequence/WholeGenomeFasta/genome.fa` | All pipelines |
| `gtf` | `Annotation/Genes/genes.gtf` | rnaseq, atacseq |
| `bwa_index` | `Sequence/BWAIndex/` | sarek, atacseq |
| `star_index` | `Sequence/STARIndex/` | rnaseq |

Fetch the minimum (FASTA and GTF) into a user-selected directory; skip files
that already exist unless the user asks to overwrite:

```bash
base=https://ngi-igenomes.s3.amazonaws.com/igenomes/Homo_sapiens/NCBI/GRCh38
dest=<reference-dir>/GRCh38
mkdir -p "$dest"
curl -fL -C - -o "$dest/genome.fa"  "$base/Sequence/WholeGenomeFasta/genome.fa"
curl -fL -C - -o "$dest/genes.gtf" "$base/Annotation/Genes/genes.gtf"
```

Index directories hold many files; copy them with the AWS CLI if installed:
`aws s3 cp --no-sign-request --recursive s3://ngi-igenomes/igenomes/<path>/Sequence/STARIndex/ "$dest/star_index/"`.

Pre-downloading is optional: with `--genome <key>` the pipeline stages the
references itself on each run.

## Pipeline parameters

- Local files present: pass `--fasta <dest>/genome.fa` and, if present, `--gtf <dest>/genes.gtf`.
- Otherwise, for an iGenomes key: `--genome <key>`.
