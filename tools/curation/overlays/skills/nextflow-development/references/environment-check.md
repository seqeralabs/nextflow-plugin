# Environment Check

Run these checks before any pipeline run. Docker, Nextflow and Java are
critical: the environment is **ready** only when all three pass. Resources and
network only produce warnings.

Report each check as PASS, WARN or FAIL with the fix, then a one-line verdict.

## Critical checks

| Check | Command | Pass when | Fix on failure |
|-------|---------|-----------|----------------|
| Docker installed | `command -v docker` | Path printed | Install from https://docs.docker.com/get-docker/ |
| Docker daemon | `docker info` (allow ~15 s) | Exit code 0 | See the stderr table below |
| Nextflow | `nextflow -version` | First `X.Y.Z` in output is 23.04 or newer | Not found: install per `install-nextflow`. Too old: `nextflow self-update` |
| Java | `java -version` (prints to stderr) | `version "N` with N ≥ 17 | Install a Java 17+ JDK (for example `sudo apt install openjdk-17-jdk`) or point `JAVA_HOME` at one |

Nextflow uses calendar versioning (`YY.MM.PATCH`), so compare year, then month.
If the version cannot be parsed but the command runs, treat it as a pass and
note the unknown version. Read `install-nextflow` for current requirements.

`docker info` stderr tells you which Docker fix applies:

| stderr contains | Problem | Fix |
|-----------------|---------|-----|
| `permission denied` | User not in the docker group | `sudo usermod -aG docker $USER`, then log out and back in (or `newgrp docker`) |
| `cannot connect` / `Is the docker daemon running` | Daemon stopped | `sudo systemctl start docker` (Linux) or start Docker Desktop (macOS) |
| Command times out | Daemon hung | `sudo systemctl status docker` |

On HPC without Docker, check `singularity --version` or `apptainer --version`
instead and use `-profile singularity` (see [troubleshooting](troubleshooting.md)).

## Resource checks (warnings only)

```bash
# CPUs
nproc 2>/dev/null || sysctl -n hw.ncpu
# Memory in bytes (Linux reads MemTotal in kB)
awk '/MemTotal/ {print $2*1024}' /proc/meminfo 2>/dev/null || sysctl -n hw.memsize
# Free disk space where the pipeline will write
df -h <work-or-output-dir>
```

| Condition | Warning to give |
|-----------|-----------------|
| CPUs < 4 | Low CPU count; cap with `--max_cpus <n>` |
| Memory < 8 GB | Low memory; cap with `--max_memory '<n>.GB'` |
| Free disk < 50 GB | Low disk; human pipelines need ~100 GB (sarek WGS ~500 GB) |

Per-pipeline minimum and recommended resources are in
`references/config/pipelines/<pipeline>.yaml` under `resources`.

## Network check

```bash
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 https://hub.docker.com
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 https://nf-co.re
```

- Both reachable (status below 400): pass.
- Only Docker Hub reachable: pass with a note; pipelines can still be pulled from GitHub.
- Docker Hub unreachable: fail; containers need registry access. Check the connection and proxy settings.

For GEO/SRA work also check `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi`
and `https://www.ebi.ac.uk/ena/portal/api/` the same way (use GET, not HEAD:
E-utilities rejects HEAD requests).
