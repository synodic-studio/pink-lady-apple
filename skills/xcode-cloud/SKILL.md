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

Fix it with a post-clone hook that regenerates the workspace:

```sh
#!/bin/sh
set -eu

PROJECT_DIR="${CI_PRIMARY_REPOSITORY_PATH:-$(cd ../.. && pwd)}/<project-subdir>"
cd "$PROJECT_DIR"

brew install mise               # Homebrew is preinstalled on the runners
eval "$(mise activate sh)"
mise install                    # reads .mise.toml so CI matches the build host
mise exec -- tuist install      # resolve Tuist-managed SPM deps
mise exec -- tuist generate --no-open

if [ ! -d "<Scheme>.xcworkspace" ]; then
    echo "error: tuist generate did not produce <Scheme>.xcworkspace" >&2
    ls -la >&2
    exit 1
fi
```

**Pin Tuist in `.mise.toml`.** Without a pin, CI silently drifts to a newer
Tuist than the build host and generation can change under you.

The trailing existence check matters: without it a failed generation surfaces
much later as a confusing missing-scheme error from `xcodebuild`.

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
| Workflow builds a stale project | Workspace was committed instead of generated | Gitignore it and generate in the post-clone hook |
| `POST /v1/ciProducts` → 403 | Products cannot be created by API | GUI onboarding in Xcode, Account Holder for first enablement |
| Duplicate build number rejections in ASC | Both Xcode Cloud and a Fastlane lane are uploading | Disable one path for that app |

## Related skills

- **`pink-lady-apple:apple-tuist`** — why the workspace is gitignored, and the manifest that generates it.
- **`pink-lady-apple:apple-release`** — the local Fastlane path, signing via match.
- **`pink-lady-apple:testflight-ship`** — ASC API helper, beta groups, the tester-invite steps Xcode Cloud does not do.
