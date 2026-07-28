---
name: xcode-cloud
description: Use when setting up, inspecting, or automating Xcode Cloud — creating or editing CI workflows, triggering builds via the App Store Connect API, wiring a Tuist project so Xcode Cloud can actually build it, or debugging a workflow that fails immediately after clone. Covers the ci_scripts hooks (ci_post_clone.sh, ci_pre_xcodebuild.sh, ci_post_xcodebuild.sh), the ciProducts/ciWorkflows/ciBuildRuns API surface, and the hard limit that products and SCM grants cannot be created by any API. Triggers on "Xcode Cloud", "ci_post_clone", "ciWorkflow", "trigger a cloud build", "Xcode Cloud can't find my workspace", "set up CI for this app". For local Fastlane release lanes see pink-lady-apple:apple-release.
---

# Xcode Cloud

## What is and isn't scriptable

This is the whole shape of the thing, verified against the live API rather than
the docs — a deliberately malformed POST makes the API report its own permitted
operations:

| Resource | CREATE | Notes |
|---|---|---|
| `ciProducts` | **No** | `403 … Allowed operations are: DELETE, GET_COLLECTION, GET_INSTANCE` |
| `scmProviders` | **No** | GET only |
| `scmRepositories` | **No** | GET only |
| `ciWorkflows` | **Yes** | plus PATCH and DELETE |
| `ciBuildRuns` | **Yes** | this is how you trigger a build |

So onboarding is GUI-only and everything after it is automatable. Concretely:

- **One-time, requires Xcode on a GUI session, and the Account Holder for the
  first enablement on an org**: create the Xcode Cloud product for the app and
  authorize Apple against the SCM host (GitHub org, etc). There is no API for
  either. This is the single unavoidable manual step.
- **Everything after**: workflows, build triggering, and status polling all go
  through the ASC API with the same key the release lanes already use.

**Hazard: the ASC key can `DELETE` a `ciProduct` but cannot recreate one.** A
mistaken delete costs another GUI session by the Account Holder to rebuild the
product and re-grant SCM access. Treat `DELETE /v1/ciProducts/{id}` as
destructive and never script it speculatively.

## The Tuist collision — read this before the first build

Tuist repos gitignore `*.xcworkspace` and `*.xcodeproj` because they're
generated artifacts. Xcode Cloud clones the repo and then looks for the file
named in the workflow's `containerFilePath`. **That file will not exist**, and
the build fails before `xcodebuild` runs.

Do **not** fix this by committing the workspace — that abandons the manifest as
the single source of truth and the checked-in copy goes stale immediately.

Fix it with a post-clone hook that regenerates the workspace. This is the
canonical version — copy it verbatim and substitute `<project-subdir>` and
`<Scheme>`. `podcast-pusher` runs exactly this shape.

```sh
#!/bin/sh
set -e

# Xcode Cloud checks the primary repo out at $CI_PRIMARY_REPOSITORY_PATH.
cd "$CI_PRIMARY_REPOSITORY_PATH/<project-subdir>"

echo "▸ Installing mise…"
brew install mise               # Homebrew is preinstalled on the runners
eval "$(mise activate sh)"

echo "▸ Installing pinned Tuist…"
# `mise install tuist`, never a bare `mise install` — see the warning below.
mise install tuist

echo "▸ Resolving Tuist-managed SPM dependencies…"
mise exec tuist -- tuist install

echo "▸ Generating the workspace from Project.swift…"
mise exec tuist -- tuist generate --no-open

if [ ! -d "<Scheme>.xcworkspace" ]; then
    echo "error: tuist generate did not produce <Scheme>.xcworkspace" >&2
    ls -la >&2
    exit 1
fi
```

**`brew install tuist` cannot work on Xcode Cloud. Use mise.** This is not a
preference — Homebrew ships Tuist as a **cask**, cask installation calls `sudo`,
and the runners have no TTY and no passwordless sudo. The build dies with:

```
==> Installing Cask tuist
sudo: a terminal is required to read the password; either use the -S option
      to read from standard input or configure an askpass helper
sudo: a password is required
Error: No such file or directory @ rb_file_s_stat - /usr/local/Caskroom
```

Secondary but real: brew also resolves whatever Tuist is current (it pulled
`4.202.6` against a host on `4.200.5`), so even where it installs it drifts away
from the build host, and a manifest-format change between majors then breaks
generation in CI only — which reads as a code problem and isn't.

Add the pin next to whatever is already in `.mise.toml`:

```toml
[tools]
ruby  = "3.3.11"
tuist = "4.200.5"     # must match the build host
```

**Scope every mise call to `tuist`. Never run a bare `mise install` in CI.** A
bare install builds *every* tool in `.mise.toml`. If Ruby is pinned there for
Fastlane — and it usually is, since the same file serves both — mise hands it to
`ruby-build`, which compiles Ruby from source on the runner, burns several
minutes, and then **fails**: openssl can't be configured in that environment, so
the extension doesn't build and `mise install` exits non-zero. Your post-clone
hook dies before Tuist ever runs.

This is a real failure, not a hypothetical — it killed a build with
`Running ci_post_clone.sh script failed (exited with code 1)` and no other
signal, because the useful error is buried four minutes into the script log.

Ruby belongs to the local Fastlane path and is never needed in the cloud. Use
`mise install tuist` and `mise exec tuist -- …` so CI installs exactly one tool
while `.mise.toml` stays the single source of the pin.

The trailing existence check matters: without it a failed generation surfaces
much later as a confusing missing-scheme error from `xcodebuild`.

**None of this changes local development.** `tuist generate`, `tuist build`, and
the Fastlane lanes work exactly as before — the hook only runs inside Xcode
Cloud. The `.mise.toml` pin is the one shared artifact, and it makes local and
CI agree rather than diverge.

## ci_scripts rules

Get any of these wrong and the script is silently skipped or misrun.

- The directory must be named `ci_scripts` and sit **in the same directory as
  the Xcode project or workspace** — not necessarily the repo root. If
  `containerFilePath` is `ios/App.xcworkspace`, the scripts go in
  `ios/ci_scripts/`.
- Exactly three names are recognized, at the top level of `ci_scripts` (no
  subdirectories):
  - `ci_post_clone.sh` — after the clone; where project generation belongs
  - `ci_pre_xcodebuild.sh` — before `xcodebuild`
  - `ci_post_xcodebuild.sh` — after `xcodebuild`, **including on failure**
- **`chmod +x` is required.** Xcode Cloud honors the shebang only if the file is
  executable; otherwise it runs the file as `zsh <file>`, ignoring your shebang.
- The working directory is `ci_scripts` itself, so use
  `$CI_PRIMARY_REPOSITORY_PATH` rather than assuming a relative location.
- Default shell is zsh. Always write an explicit shebang.

Useful environment variables: `CI_PRIMARY_REPOSITORY_PATH`,
`CI_PULL_REQUEST_NUMBER` (only set for PR-triggered builds),
`CI_PRODUCT_PLATFORM`, `CI_WORKFLOW`, `CI_BUILD_NUMBER`.

## Inspecting what exists

Everything here is a plain authenticated GET; reuse the JWT helper in
`pink-lady-apple:testflight-ship`'s `scripts/asc.py`.

```
GET /v1/ciProducts?include=app,primaryRepositories
GET /v1/ciProducts/{id}/workflows
GET /v1/ciWorkflows/{id}
GET /v1/ciWorkflows/{id}/buildRuns?limit=10
GET /v1/scmRepositories
GET /v1/ciXcodeVersions
GET /v1/ciMacOsVersions
```

Reading an existing workflow before authoring a new one is the fastest way to
get the `actions` and start-condition shapes right — they are fiddly and the
docs show only one example.

## Start conditions: default to manual

A workflow fires on whichever start conditions it declares. The two that matter:

- `branchStartCondition` — **automatic**, runs on every push to matching branches
- `manualBranchStartCondition` — runs only when something explicitly POSTs a
  build run

**Measure before choosing.** The intuition that automatic builds will eat the
allowance is usually wrong, and it's cheap to check. A measured iOS `ARCHIVE`
runs about **5.4 minutes**, so a 25-hour month is roughly **280 builds, ~9 per
day**. Compare that against the repo's actual push rate
(`git log --since="14 days ago" --date=short --pretty=%ad <branch> | uniq -c`).
A repo committing a handful of times on its busiest day is nowhere near the
ceiling, and Xcode Cloud triggers per *push*, not per commit, so the real number
is lower still.

Where that's true, **automatic on the working branch is the better default** —
catching a broken build on push is the entire point of CI, and it costs
headroom you aren't using.

Switch to manual when one of these actually applies:

1. **The app also ships via a Fastlane lane and the cloud workflow distributes
   to TestFlight.** Two uploaders race for build numbers and ASC rejects the
   duplicate. This is the one that bites hardest — and note it's really an
   argument against *distributing* from both, not against building.
2. **The push rate genuinely approaches the ceiling** — a busy multi-person repo,
   or a workflow much slower than 5 minutes.
3. **You want builds to be deliberate events** rather than background activity.

Manual doesn't mean clicking anything — triggering stays a one-line API call
(below), so it's still fully scriptable, just deterministic about *when*.

Switch an existing automatic workflow to manual by moving the condition:

```
PATCH /v1/ciWorkflows/{id}
{"data":{"type":"ciWorkflows","id":"<id>","attributes":{
  "branchStartCondition": null,
  "manualBranchStartCondition": {
    "source": {"isAllMatch": false,
               "patterns": [{"pattern": "develop", "isPrefix": false}]}
  }}}}
```

Automatic is the right call when you specifically want PR gating — a
`pullRequestStartCondition` running TEST actions gives real value per push and
doesn't upload anything.

## Creating a workflow

`POST /v1/ciWorkflows`. Required attributes: `name`, `description`,
`isEnabled`, `isLockedForEditing`, `clean`, `containerFilePath`, `actions`, and
at least one start condition. Required relationships: `product`, `repository`,
`xcodeVersion`, `macOsVersion`.

```json
{
  "data": {
    "type": "ciWorkflows",
    "attributes": {
      "name": "Archive develop",
      "description": "Archive on every push to develop",
      "branchStartCondition": {
        "source": { "isAllMatch": false,
                    "patterns": [{ "pattern": "develop", "isPrefix": false }] },
        "filesAndFoldersRule": null,
        "autoCancel": true
      },
      "actions": [{
        "name": "Archive - iOS",
        "actionType": "ARCHIVE",
        "scheme": "<Scheme>",
        "platform": "IOS",
        "isRequiredToPass": true
      }],
      "isEnabled": true,
      "isLockedForEditing": false,
      "clean": true,
      "containerFilePath": "ios/<Scheme>.xcworkspace"
    },
    "relationships": {
      "product":      { "data": { "type": "ciProducts",     "id": "<product-id>" } },
      "repository":   { "data": { "type": "scmRepositories","id": "<repo-id>" } },
      "xcodeVersion": { "data": { "type": "ciXcodeVersions","id": "<version-id>" } },
      "macOsVersion": { "data": { "type": "ciMacOsVersions","id": "<version-id>" } }
    }
  }
}
```

**Use the floating version aliases, not a pinned Xcode build.** `GET
/v1/ciXcodeVersions` returns `Latest Release` and `Latest Beta or Release`
alongside concrete versions; the aliases keep the workflow from rotting when
Apple retires an Xcode.

`actionType` values include `BUILD`, `ANALYZE`, `TEST`, `ARCHIVE`. Only
`ARCHIVE` produces something distributable.

`containerFilePath` is repo-relative and must match what `ci_post_clone.sh`
generates, exactly.

## Triggering a build

```json
POST /v1/ciBuildRuns
{
  "data": {
    "type": "ciBuildRuns",
    "relationships": {
      "workflow":     { "data": { "type": "ciWorkflows",      "id": "<workflow-id>" } },
      "sourceBranchOrTag": { "data": { "type": "scmGitReferences", "id": "<ref-id>" } }
    }
  }
}
```

Poll `GET /v1/ciBuildRuns/{id}` and read `executionProgress` (`PENDING` →
`RUNNING` → `COMPLETE`) plus `completionStatus` (`SUCCEEDED`, `FAILED`,
`ERRORED`, `CANCELED`, `SKIPPED`). `COMPLETE` alone is not success — always
check `completionStatus`.

## Measuring compute against the monthly allowance

The plan includes a fixed number of compute hours per month (25 on the base
tier). **There is no API for consumed allowance** — `ciUsages`,
`ciComputeUsages`, and every similar path 404. Apple surfaces the counter only
in the ASC web UI, which is useless headless.

What you *can* get is per-build wall time, from attributes on the build run:

```
GET /v1/ciWorkflows/{id}/buildRuns?limit=50
→ createdDate, startedDate, finishedDate, startReason, completionStatus
```

`finishedDate - startedDate` is the per-build wall time. Treat it as a close
proxy for billed compute, not as the billed figure itself — Apple doesn't
publish the exact mapping, so budget with headroom rather than to the minute.

**Measured baseline**: a single-scheme iOS `ARCHIVE` on a Tuist project, with
`ci_post_clone.sh` installing mise and Tuist and regenerating the workspace,
runs **~5.4 minutes** end to end (two consecutive successes at 5.3 and 5.4).
Against a 25-hour month that's ~280 builds, ~9 per day. Use it as a starting
estimate, then measure your own — a multi-scheme workflow or one with TEST
actions will be materially slower.

`startReason` is the field worth watching: `GIT_REF_CHANGE` means a push
triggered it, `MANUAL` means something asked for it deliberately. Summing wall
time grouped by `startReason` tells you how much of the allowance is going to
builds nobody requested — which is the concrete argument for manual start
conditions above.

Note that **failed builds still consume the allowance**, and a hook that fails
slowly is the expensive kind: a bare `mise install` compiling Ruby before dying
burned ~5 minutes per attempt for no result.

## Reading build logs (you will need this)

When a build fails, `GET /v1/ciBuildRuns/{id}/actions` and its `/issues`
sub-resource give you almost nothing — typically one line like
`Running ci_post_clone.sh script failed (exited with code 1)`. The actual error
is in the log bundle, and getting it is a three-hop walk:

```
GET /v1/ciBuildRuns/{id}/actions              → action ids
GET /v1/ciBuildActions/{id}/artifacts         → find fileType == LOG_BUNDLE
GET <artifact.downloadUrl>                    → a .zip; follow redirects
```

Unzip it and read `.../ci_post_clone.log`. Scripts that fail slowly bury the
real error thousands of lines in, so read the **tail**, not the head.

Automate this before you need it — debugging Xcode Cloud blind is miserable, and
the web UI is not an option on a headless setup.

## TestFlight from Xcode Cloud vs from Fastlane

An `ARCHIVE` action with `buildDistributionAudience` set will push to TestFlight
directly. Leaving it null means the workflow archives and stops.

These two paths do the same job and **should not both be live for one app** —
two uploads race for build numbers and you get duplicate-build rejections in
ASC. Pick one per app:

- **Fastlane (`pink-lady-apple:apple-release`)** — signing via match, full
  control, runs on the build host, and the post-upload group/tester chain from
  `pink-lady-apple:testflight-ship` is already wired into the lane.
- **Xcode Cloud** — no local build host needed, but signing is Apple-managed and
  the tester-invitation follow-ups in `testflight-ship` still have to happen
  separately. Xcode Cloud archiving does **not** invite anyone.

Whichever you choose, "the build reached the tester's phone" is still the bar —
see `testflight-ship` step 4.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Build fails immediately after clone, no `xcodebuild` output | `containerFilePath` names a gitignored generated workspace | Add `ci_post_clone.sh` that runs `tuist generate --no-open` |
| `ci_post_clone.sh` appears not to run at all | Wrong directory, or not executable | Must be `<project-dir>/ci_scripts/`, and `chmod +x` |
| Script runs but the shebang is ignored | File isn't executable, so Xcode Cloud invokes it as `zsh <file>` | `chmod +x`, commit the mode bit |
| `tuist: command not found` in CI | Runners have no Tuist | Install it in `ci_post_clone.sh`; pin it in `.mise.toml` |
| `sudo: a terminal is required to read the password`, then `No such file or directory @ rb_file_s_stat - /usr/local/Caskroom` | `brew install tuist` — Tuist is a cask, casks need sudo, runners have no TTY | Install via mise instead. Applies to any cask, not just Tuist |
| `Running ci_post_clone.sh script failed (exited with code 1)` with no other detail | Anything in the hook. Read the script log — the real error is often minutes in | Fetch `ci_post_clone.log` from the build's `LOG_BUNDLE` artifact (see below) |
| Hook fails after ~4 min, log shows `ruby-build` and `OpenSSL library could not be found` | A bare `mise install` tried to compile the Ruby pinned for Fastlane | `mise install tuist` / `mise exec tuist -- …` |
| Workflow builds a stale project | Workspace was committed instead of generated | Gitignore it and generate in the post-clone hook |
| `POST /v1/ciProducts` → 403 | Products cannot be created by API | GUI onboarding in Xcode, Account Holder for first enablement |
| Duplicate build number rejections in ASC | Both Xcode Cloud and a Fastlane lane are uploading | Disable one path for that app |

## Related skills

- **`pink-lady-apple:apple-tuist`** — why the workspace is gitignored, and the manifest that generates it.
- **`pink-lady-apple:apple-release`** — the local Fastlane path, signing via match.
- **`pink-lady-apple:testflight-ship`** — ASC API helper, beta groups, the tester-invite steps Xcode Cloud does not do.
