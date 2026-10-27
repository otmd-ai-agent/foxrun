---
type: doc
workspace: system
timestamp: 2026-10-27T02:00:28.180296+00:00
---

# Foxrun 0.1.0: independent Linux evaluation

Evaluated on 2026-10-27 at source commit `73076296106a6785da721694dd474c435b8fe980`.

## Assessment

Foxrun's local task and memory plumbing works in the workflows exercised here. A clean source install and a package built with uv both completed and passed `doctor`. An independent CLI workflow created a task, required completion evidence, rejected the finisher's sign-off, accepted another reviewer's sign-off, and recovered a saved lesson in a fresh process. Direct startup and after-compaction hook calls recovered that lesson for both supported runtimes.

The evidence does **not** establish that Foxrun buys back a week, improves model output, reduces token spend, or reliably runs a business unattended. Its own memory evaluation passes ten of eleven groups, while the recovery group scores 4/11. A manual nightly dry run returns exit 0 while reporting 1,498 lint findings and two failed memory checks. The automated test suites also contain failures and environmental dependencies that prevent a clean Linux result.

This is a completed evaluation of the local workflows described below, not a completed live-agent, multi-model, macOS, or seven-night trial. Treat Foxrun as a promising early local coordination toolkit; require additional evidence before relying on unattended execution.

## Scope and method

- Repository: <https://github.com/foxrun-ai/foxrun>.
- Release label: 0.1.0. The checkout was not modified to make tests pass.
- Host: Linux x86-64, kernel 6.18.55, Python 3.12.14. Some upstream tests explicitly invoke `/usr/bin/python3` instead of the evaluator's Python.
- Trial data: synthetic person `evaluator`, workspace `sample-shop`, inventory task, proof file, and lesson. No business accounts or real customer records were connected.
- System, portfolio, runtime settings, package installation, and evidence were kept under `/workspace/foxrun-evaluation`.
- Installation used `--runtime-home`, so the hook checks used separate settings. Scheduling was disabled with `--no-schedule`; the README already limits scheduling to macOS.
- Evaluation layers: documented installation, independent CLI checks, direct hook execution, package build/install, shipped design evaluations, top-level regression suite, and discovery of component test suites.
- Passing a command is evidence only for that command. Synthetic fixtures do not establish real-world agent behavior. Repeated tests and subtests are not independent business outcomes.

The executable independent harness and raw command results were retained with the local report. It records arguments, exit status, output, and elapsed time. The first attempt is retained separately: it supplied an absolute proof path outside the receipt root, which Foxrun correctly refused. The final attempt uses a workspace-relative proof path. That correction is evaluator setup, not a product fix.

## Claims and observed results

| Claim in README | Evidence from this run | Verdict and limit |
|---|---|---|
| Local files and a SQLite database; no Foxrun server/account | Source and package installs, task read/write, lesson retrieval, state generation, and local backup export worked without a Foxrun account | Supported for the tested core. This was not a network/privacy audit of every optional integration. |
| Every task must say what done means | An incomplete task was refused; a task with the documented fields was accepted | Supported for the normal `create` path tested. No claim that direct database editing is prevented. |
| Nobody grades their own work | `done` moved T3 into review; `accept --by worker` failed with the finisher rule; `accept --by reviewer` succeeded | Supported for declared CLI actor names. This is not authenticated proof of two different people or models. |
| A task closes only with proof attached | Missing proof was refused; a relative proof file allowed the completion/review workflow | Supported for attachment requirements. The program did not independently count inventory or judge whether the proof was truthful. |
| Start from current work rather than chat memory | A fresh process showed the created task and saved lesson | Supported for the tested persisted records. |
| Startup and compaction restore context | Both Claude and Codex session-start and after-compact scripts exited 0 and included the lesson | Supported for direct hook execution with synthetic payloads. Actual runtime dispatch and model adherence were not exercised. |
| Parallel workers have separate folders | Sixteen concurrent `runs.py new` calls with the same task, seat, and label returned sixteen distinct paths | Supported for allocation in this probe. Folders do not prevent an agent writing elsewhere. |
| Updates preserve personal data | Same-version update refused before changing files because `/` belongs to UID 65534; local bytes and task remained intact | Update preservation after a successful update is unverified on this host. Refusal preserved the tested state. |
| A nightly pass checks memory, compiles sources, rebuilds state, and exports records | `dream.py code` completed six code steps, including state and backup export; nightly dry run reported findings | Partially supported. No completed model half, live scheduler, alert delivery, or seven-night run. |
| Lean pages, fewer tokens, better work, time saved | Lint and model-tier configuration exist | Outcome claims unverified. No baseline, token accounting, quality scoring, or time-savings study was run. |
| Tools vetted on real work; broad capture support | Optional tool documentation and component tests are present | Author's experience and live web/social capture claims were not independently verified. |

Source anchors: [README](https://github.com/foxrun-ai/foxrun/blob/73076296106a6785da721694dd474c435b8fe980/README.md), [INSTALL](https://github.com/foxrun-ai/foxrun/blob/73076296106a6785da721694dd474c435b8fe980/INSTALL.md), [GUIDE](https://github.com/foxrun-ai/foxrun/blob/73076296106a6785da721694dd474c435b8fe980/GUIDE.md).

## End-to-end local run

### Installation and package route

The source installation finished in 3.233 seconds according to its own timer. It wrote trial Claude and Codex hook settings and Codex trust rows. The standalone doctor result was `Doctor: 0 failed`.

The uv route built the package from the pinned local checkout, installed `foxrun==0.1.0`, and exposed its executable in an isolated bin directory. Using that executable to install a second system completed in 3.292 seconds; its installed doctor also returned `Doctor: 0 failed`. This tests the checkout's package build and installer, not an independently downloaded PyPI artifact or every remote `uv tool install git+...` behavior. These two timings are observations, not benchmarks.

### Task, evidence, review, and restart

The final independent sequence created T3, an inventory task with an acceptance criterion of three counted units. It checked the following:

1. Creating an incomplete task failed.
2. Creating a fully specified task succeeded, and a new start process displayed it.
3. Accepting before completion failed.
4. Completing with a missing proof file failed.
5. Completing with `inventory-proof.txt` below the receipt root succeeded and moved the task to review.
6. The finisher's sign-off failed: `finisher rule: worker finished T3 ... worker cannot sign it off`.
7. `reviewer` accepted it; a later `show` returned `status: done`.
8. A saved lesson appeared in a subsequent start process and in all four direct hook probes.
9. An unknown workspace was refused, and repeated hook setup reported `Nothing changed.`

The harness has eighteen assertions. Seventeen passed and one failed: successful same-version update. Two passing preservation assertions follow the refused update and must not be interpreted as proof of a completed update migration.

### Nightly and memory processing

`dream.py code` exited 0. It reported passes for kept links/inbox, state, index, daily, backup, and checks. It exported one database and rebuilt the workspace state. The fixture had little source history, so this does not demonstrate semantic compilation of a populated knowledge base.

Its final output still said `Health: dream fail; 0 lead beats recorded`. The health file had `ok: false`, no finished dream, and stale lead signals. A successful code half therefore did not establish a healthy complete dream run.

`cron/nightly.py --dry-run --workspace sample-shop --workspaces ...` also exited 0. Its summary reported:

```text
Nightly: exit 0; lint 1498 findings; check 2 failed checks; failed steps: none
```

The printed output included unresolved wikilinks in the generated workspace schema. Handoff checking was skipped because no handoff/session-transcript pair existed. State push was skipped because the trial `state/` was not a Git repository.

This exit behavior is intentional in the implementation: completed lint and memory-check scans can report findings without counting as failed execution steps. Monitoring must inspect findings and health, rather than treating exit 0 as a clean workspace. The finding count is for this synthetic install after the probes, not a count of independently confirmed product defects.

## Shipped memory evaluations

Ran `evals/memory/run.py` from source with `FOXRUN_PERSON=evaluator`, then from the installed system with its home/portfolio/person configuration. Both produced the following scores. An initial unconfigured source run failed to resolve the person for some groups; that setup failure is preserved separately.

| Evaluation | Passed cases | Group result |
|---|---:|---|
| 01 rule / dictionary routing | 94/94 | Pass |
| 02 read / bounded memory routes | 35/35 | Pass |
| 03 reliability | 6/6 | Pass |
| 04 code first | 28/28 | Pass |
| 05 trace / source chains | 101/101 | Pass |
| 06 fetch / bounded queries | 21/21 | Pass |
| 07 triangulate | 3/3 | Pass |
| 08 field evidence | 6/6 | Pass |
| 09 portability | 3/3 | Pass |
| 10 night shift | 6/6 | Pass |
| 11 seven nights | 4/11 | Fail |

These are the project's own synthetic design checks, not independent measurements of the marketed outcomes. In particular, the field-evidence fixtures are explicitly labeled fake by the project. Passing them does not validate the author's real-world effectiveness claims.

The failed final group reports seven gaps:

- Model adapter failure is retained; successful recovery remains unproven.
- Blank input is refused and original bytes remain; recovery remains unproven.
- A dead lock needs manual recovery; automatic stale-lease recovery is unproven.
- Atomic writing preserves the previous page on disk pressure; quota/catch-up recovery is absent.
- Corrupt backup input is refused and last-good bytes stay; successful recovery is unproven.
- Seven completed live nightly receipts are absent.
- Independent evidence of local alert delivery is absent.

The first five distinguish safe refusal/preservation from restored service. The final two are missing evidence, not observed failed deliveries. The project's [evaluation README](https://github.com/foxrun-ai/foxrun/blob/73076296106a6785da721694dd474c435b8fe980/evals/memory/README.md) makes this distinction explicitly.

## Regression testing and diagnosis

The documented top-level command ran 201 tests in 104.629 seconds and ended with 18 failures and 12 errors. This is not a clean test result, but it is also not evidence of thirty independent product defects.

Confirmed contributors include:

- A fresh-install test invokes macOS `/usr/bin/plutil`, absent on this Linux host.
- Update acceptance setup invokes `git archive 7e836f09:src` from the checkout's parent. That assumed source layout/history is unavailable here.
- A seat test expects `skillwright/skills/setup`, which is absent in this revision.
- Several workspace-lead tests try to write under the real user's `.local/state/foxrun/staging`, outside the trial paths and the writable sandbox.
- The installer privacy test derives a banned pattern from the OS username. Here the username is `agent`, which matches legitimate product text. One failing assertion explicitly reports `match='agent'`; repeated installer failures list hundreds of matching files. Those counts do not establish leaked personal data.

Component discovery results are appended below. These runs are diagnostic, not a single supported all-project test command. They include duplicated orchestrate suites, skipped tests, import/setup failures, and subtest errors; do not sum error counts as unique defects.

Environment-sensitive checks were followed up selectively. Configuring `FOXRUN_HOME`, `FOXRUN_PORTFOLIO`, and `FOXRUN_PERSON` reduced the agent suite from seven errors to one failure across 80 tests. The remaining failure is `test_reviewed_keeper_is_generic_and_owns_its_ruled_parts`.

The host lacks the `sqlite3` CLI, although Python's SQLite module works and the core task workflow succeeded. Multiple base tests fail while spawning that CLI. Attempts to install it through apt lacked system permissions; sudo is unavailable. The installed Pandoc is 3.1.11.1; memory link tests invoke `--syntax-highlighting=none`, and that invocation returns exit 6 here. Configuring the Foxrun environment does not resolve those Pandoc errors. No fake CLI or patched test was substituted to turn these failures green.

## Specific follow-up work

1. Make the documented tests portable: declare CLI/version prerequisites, skip macOS-only checks on Linux, isolate staging paths, and remove assumptions about a private checkout layout/history.
2. Change username-based privacy fixtures so a generic account name such as `agent` cannot classify ordinary product text as personal data.
3. Reconcile stale skill references and documentation. GUIDE describes eleven product skills, while README advertises 62 skills; explain which inventory each count means and replace retired `setup` references where appropriate.
4. Expose a clear operational status that distinguishes successful scans, unresolved findings, and a completed healthy nightly run. Keep the existing detailed receipts.
5. Demonstrate recovery, not just preservation, for the five failed fault cases. Then collect seven live receipts and an independently observed scheduler-down alert on macOS.
6. Test successful update and rollback on a normally owned filesystem. This host's root ownership triggers the source-trust guard before the update starts; do not weaken the guard just to accommodate this test host.
7. Run a separate live-agent benchmark with fixed tasks and ground truth: compare bare Claude/Codex against Foxrun for completion accuracy, evidence quality, cross-session recall, tokens, cost, and elapsed time. Record multiple trials, model versions, failures, and human interventions. None of those outcome improvements has been established by this run.

## Reproduction

Use a disposable writable directory and a fresh clone at the evaluated commit. Replace the absolute paths below if needed. The test suite has some host-path assumptions described above.

```sh
python install.py --home /workspace/foxrun-evaluation/system \
  --portfolio /workspace/foxrun-evaluation/portfolio --yes \
  --person evaluator --workspace sample-shop --runtime both \
  --runtime-home /workspace/foxrun-evaluation/runtime --hookup --no-schedule
python /workspace/foxrun-evaluation/system/foxrun.py doctor
python /workspace/foxrun-evaluation/system/foxrun.py start --workspace sample-shop
python -m unittest discover -s tests -p 'test_*.py'
FOXRUN_PERSON=evaluator python -B evals/memory/run.py
```

For installed memory evaluations and direct memory/nightly commands, set `FOXRUN_HOME`, `FOXRUN_PORTFOLIO`, and `FOXRUN_PERSON` to the trial values. Run `memory/dream.py code` and `cron/nightly.py --dry-run` separately and read their summaries and `health.json`.

The local evidence directory contains `evaluate.py`, `logs/independent-commands.json`, `logs/independent-results.json`, `logs/hook-probes.json`, install/doctor logs, all three source/configured/installed memory-evaluation outputs, component logs, and `logs/suite-results.json`. Raw logs remain local: some contain long fixture dumps and generated token-like test strings, so this report does not publish them wholesale.

This report was written from executed commands and source inspection, with the Clarity skill applied to the prose. It does not present synthetic fixtures as field evidence or claim that an agent runtime was exercised merely because a hook script ran.

## Component discovery results

These results are from the unconfigured source discovery pass. The configured follow-ups are described above. Error counts include subtests.

| Suite | Tests reported | Result |
|---|---:|---|
| `agents/tests` | 80 | FAILED (errors=7) |
| `base/tests` | 918 | FAILED (failures=51, errors=335, skipped=9) |
| `capture/tests` | 2 | OK |
| `cron/tests` | 32 | OK |
| `decisions/tests` | 0 | NO TESTS RAN |
| `events/tests` | 6 | OK (skipped=1) |
| `memory/tests` | 126 | FAILED (failures=1, errors=372) |
| `skills/orchestrate/tests` | 26 | FAILED (errors=3, skipped=1) |
| `skillwright/skills/agent-new/tests` | 2 | OK |
| `skillwright/skills/foxrun-help/tests` | 5 | OK |
| `skillwright/skills/foxrun-setup/tests` | 16 | OK |
| `skillwright/skills/handoff/tests` | 55 | OK (skipped=7) |
| `skillwright/skills/imessage/tests` | 3 | OK |
| `skillwright/skills/jev/tests` | 1 | OK |
| `skillwright/skills/orchestrate/tests` | 26 | FAILED (errors=3, skipped=1) |
| `skillwright/skills/runtime-session-search/tests` | 1 | FAILED (errors=1) |
| `skillwright/skills/skillify/tests` | 46 | FAILED (errors=5) |
| `skillwright/skills/thread/tests` | 15 | OK |
| `skillwright/tests` | 188 | FAILED (failures=8, errors=51) |
| `work/tests` | 626 | FAILED (failures=1, skipped=1) |

The work suite's single failure was the schema backup/verify/undo test: it tried to invoke the absent `sqlite3` CLI. Its 626-test result was one failure and one skip. A suite with no discovered tests provides no coverage.
