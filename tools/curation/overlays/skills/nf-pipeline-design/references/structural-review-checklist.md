# Structural review checklist

Review the user's selected pipeline sources against these architectural rules after `nextflow lint` passes. `nextflow lint` covers parse-level and strict-syntax errors; these rules cover layout and design choices it does not check.

Read the relevant files and report each violation with its rule ID, file, line and a suggested fix. **Error** rules should be fixed before finishing. **Warning** rules need a fix or a stated reason to keep the current pattern.

## Entrypoint (`main.nf`)

| ID | Severity | Rule |
|---|---|---|
| NF001 | Error | `main.nf` calls subworkflows, not modules (UPPER_SNAKE process names) directly. |
| NF002 | Warning | `main.nf` avoids deep operator chains (more than 3 chained operators on one channel); move the logic into a named subworkflow. |
| NF003 | Error | `main.nf` reads `params.*` only in its setup area, then passes values on as explicit inputs. |
| NF004 | Warning | `main.nf` marks its setup and run sections with comments. |
| NF005 | Error | `include` statements do not use the deprecated `addParams` or `params` clause. |

## Subworkflows

| ID | Severity | Rule |
|---|---|---|
| NF010 | Error | Every subworkflow declares a `take:` block. |
| NF011 | Error | Every subworkflow declares an `emit:` block. |
| NF012 | Warning | Emitted outputs are named. |
| NF013 | Error | A subworkflow runs at most one module per execution path; split umbrella subworkflows that chain several tools. |
| NF014 | Warning | A subworkflow that calls several modules emits a `versions` channel. |
| NF024 | Warning | Subworkflows do not read `params.*`; values arrive through `take:`. |

## Modules and processes

| ID | Severity | Rule |
|---|---|---|
| NF020 | Error | Modules never reference `params.*`, including inside the process script body. |
| NF021 | Warning | Processes do not use a `when:` block for branching; branch in the calling workflow instead. |
| NF022 | Warning | Module scripts do not embed inline glue code in another language (heredoc Python, R and so on); ship it as a script on `PATH` or a separate process. |
| NF023 | Error | Process names are UPPER_SNAKE_CASE. |
| NF041 | Warning | Process scripts do not swallow failures (`set +e`, `\|\| true`, `\|\| echo`). |
| NF042 | Warning | Scripts are called by name on `PATH`, not by an absolute interpreter or script path. |
| NF043 | Warning | Process scripts use staged input files in place instead of copying them. |
| NF050 | Error | Every module process declares a `container` directive. |
| NF052 | Warning | Every module process declares resources, through a label or `cpus`/`memory`/`time`. |

## Language and wiring

| ID | Severity | Rule |
|---|---|---|
| NF030 | Warning | Use lowercase `channel.*` factories, not `Channel.*`. |
| NF031 | Warning | Read environment variables with `env('NAME')`, not as implicit bare variable references. |
| NF032 | Error | No `import` statements (disallowed in strict syntax). |
| NF033 | Error | No `for` or `while` loops; use higher-order operators. |
| NF034 | Error | No `class` declarations in pipeline scripts; move them to `lib/`. |
| NF040 | Warning | Consume process and subworkflow outputs by name, not by numeric index (`.out[0]`). |

## Pipeline

| ID | Severity | Rule |
|---|---|---|
| NF051 | Warning | A `nextflow_schema.json` sits next to `main.nf` and defines the pipeline parameters. |
