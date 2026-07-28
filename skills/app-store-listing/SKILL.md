---
name: app-store-listing
description: Use when staging or editing an app's public App Store listing — metadata text, screenshots, categories, age rating, content rights, privacy/support URLs, attaching a build to a version, or preparing a version for review. Covers the deliver/upload_to_app_store split needed to work around the first-version "No data" bug, the ASC API recipes for everything deliver can't do, and the irreversible build-expiry trap. Triggers on "fill out the App Store listing", "upload screenshots", "set categories", "age rating", "submit for review", "get it ready for review", "app metadata". This is distinct from TestFlight — for beta distribution see pink-lady-apple:testflight-ship.
---

# App Store Listing

## Scope

TestFlight (`beta`) and the public App Store listing are separate jobs with
separate failure modes. This skill is the listing: metadata, screenshots,
categories, age rating, and getting a version to "ready for review". For
uploading builds to beta testers, see **`pink-lady-apple:testflight-ship`**.

The short version: **`deliver` (`upload_to_app_store`) is reliable for text
metadata and screenshots, but its category/app-info step throws `No data` on the
very first version of an app.** Set categories, content rights, age rating, and
the build link via the ASC API instead. All of it stages with
`submit_for_review: false` — getting a listing "ready for review" is fully
headless; only the final submit and the privacy attestation need a human.

## Two lanes, not one (the first-version `No data` bug)

`upload_to_app_store` with metadata + screenshots + categories dies with a bare
`No data` on a first app version (fastlane issues #20538, #29431). It uploads the
version localization text FIRST (that lands fine), then throws when it PATCHes the
app-info categories. So split it:

```ruby
lane :push_metadata do        # text only
  upload_to_app_store(api_key: k, app_identifier: ID,
    metadata_path: "fastlane/metadata",
    skip_binary_upload: true, skip_screenshots: true,
    submit_for_review: false, force: true, run_precheck_before_submit: false)
end
lane :push_screenshots do     # images only
  upload_to_app_store(api_key: k, app_identifier: ID,
    screenshots_path: "fastlane/screenshots",
    skip_binary_upload: true, skip_metadata: true, overwrite_screenshots: true,
    submit_for_review: false, force: true, run_precheck_before_submit: false)
end
```

Then do categories / content-rights / age-rating / build-link via the API (below).

Notes:
- `force: true` skips the HTML preview confirmation (required headless).
- `release_notes` / whatsNew is silently SKIPPED on a first version ("this is the
  first version of the app") — expected, not an error. It's used from v2 on.
- `skip_screenshots` uploads a duplicate set on retry: deliver's "…is missing on
  App Store Connect" is a false negative from ASC eventual consistency, so its
  retry re-uploads and you end up with 2x the screenshots (e.g. 6 instead of 3).
  Dedup via the API afterward (keep one per `fileName`).

## Field length limits (deliver won't warn, ASC rejects at submit)

| File | Limit |
|---|---|
| `name.txt` | 30 |
| `subtitle.txt` | 30 |
| `promotional_text.txt` | 170 |
| `keywords.txt` | 100 (comma-separated, no spaces — the commas count) |
| `description.txt` | 4000 |

## Screenshots from an XCUITest

Capture mechanics live in **`pink-lady-apple:sim-capture`**. What matters here:

- Capture to a known dir (`/tmp/…`), `XCUIScreen.main.screenshot().pngRepresentation`.
- **1320×2868** (iPhone 17 Pro Max, 6.9") is accepted and lands in ASC display type
  `APP_IPHONE_67` (Apple folds 6.9" into the 6.7" set). 1290×2796 works too.
- **Seed varied, realistic mock data.** A single repeated mock turn (a) reads as
  filler and (b) ACCUMULATES — turns persisted to `UserDefaults` survive between
  simulator test runs, so you get the same line 4-5 times. Overwrite a curated
  conversation on each launch.
- **Inject presentable config via launch args**, not the persisted default:
  `app.launchArguments += ["-serverURL", "http://localhost:31552"]`. `@AppStorage`
  reads the NSArgumentDomain first, so this wins over whatever a prior run wrote —
  fixes stale values (e.g. an old port) showing in a Settings capture.
- **LOOK at every capture before uploading** (`Read` renders PNGs). Watch for: a
  stale/localhost server URL, a visible token (leak), or an empty/placeholder
  state that reads as a broken app. A bad screenshot is worse than none.

## ASC API recipes (authlib JWT + httpx)

Auth is the same pattern as `testflight-ship/scripts/asc.py` (`token()` →
`Bearer`, base `https://api.appstoreconnect.apple.com/v1`). Key id / issuer from
`pass show asc-key-id` / `asc-issuer-id`, `.p8` at
`~/.appstoreconnect/private_keys/AuthKey_<KID>.p8`.

**Content rights** — PATCH the app:
```
PATCH /apps/{appId}
{"data":{"type":"apps","id":appId,"attributes":{"contentRightsDeclaration":"DOES_NOT_USE_THIRD_PARTY_CONTENT"}}}
```

**Categories** — live on the editable appInfo, not the version:
```
appInfoId = GET /apps/{appId}/appInfos    # the PREPARE_FOR_SUBMISSION one
PATCH /appInfos/{appInfoId}
{"data":{"type":"appInfos","id":appInfoId,"relationships":{
  "primaryCategory":{"data":{"type":"appCategories","id":"DEVELOPER_TOOLS"}},
  "secondaryCategory":{"data":{"type":"appCategories","id":"UTILITIES"}}}}}
```

**Age rating (2025 schema)** — the declaration hangs off the **appInfo**, not the
appStoreVersion (`/appStoreVersions/{id}/ageRatingDeclaration` → 404; use
`/appInfos/{id}/ageRatingDeclaration`). Its `id` equals the appInfo id. **All 22
fields are required in a single PATCH** — a partial body 409s
(`ENTITY_ERROR.ATTRIBUTE.REQUIRED`) listing what's missing. For a clean 4+:
- Enum `"NONE"`: `alcoholTobaccoOrDrugUseOrReferences`, `contests`,
  `gamblingSimulated`, `gunsOrOtherWeapons`, `horrorOrFearThemes`,
  `matureOrSuggestiveThemes`, `medicalOrTreatmentInformation`,
  `profanityOrCrudeHumor`, `sexualContentGraphicAndNudity`,
  `sexualContentOrNudity`, `violenceCartoonOrFantasy`, `violenceRealistic`,
  `violenceRealisticProlongedGraphicOrSadistic`
- Boolean `false`: `gambling`, `unrestrictedWebAccess`, `lootBox`, and the newer
  2025 capability fields `advertising`, `ageAssurance`, `healthOrWellnessTopics`,
  `messagingAndChat`, `parentalControls`, `userGeneratedContent`
- `kidsAgeBand`: `null` (not required)
```
PATCH /ageRatingDeclarations/{appInfoId}   {"data":{"type":"ageRatingDeclarations","id":…,"attributes":{…22 fields…}}}
```

**Attach a build to the version** (so it's submit-ready):
```
PATCH /appStoreVersions/{versionId}/relationships/build
{"data":{"type":"builds","id":buildId}}      # 204
```
Find the build id: `GET /builds?filter[app]={appId}&filter[version]={buildNum}`.

**Dedup screenshots**:
```
setId  = GET /appStoreVersionLocalizations/{locId}/appScreenshotSets
shots  = GET /appScreenshotSets/{setId}/appScreenshots   # attributes.fileName
DELETE /appScreenshots/{id}   # for every id past the first per fileName
```

## Expiring old builds is IRREVERSIBLE — do it by build number, never a lookup

Two related traps, learned the hard way shipping one app's 0.1.0:

- **Going backwards in version shadows the new build.** If you drop from 1.0.0 to
  0.1.0, TestFlight groups builds by version string and surfaces the *higher*
  version (1.0.0) as the default, so the tester "still sees the old build" even
  though the new one is a higher build number. Fix: expire the higher-version
  builds so only the intended version remains offered.
- **`PATCH /builds/{id} {expired:true}` cannot be undone** — un-expire returns
  `409 ENTITY_ERROR.ATTRIBUTE.INVALID`. So when bulk-expiring, do NOT filter by a
  version lookup that can silently fail: an `include=preReleaseVersion` that
  doesn't resolve leaves every build's version as `"?"`, and a `!= "0.1.0"` filter
  then expires EVERYTHING — including the build attached to your editable version.

Rules: (1) key off the exact build **numbers** you already know, not a lookup;
(2) NEVER expire the build currently attached to the PREPARE_FOR_SUBMISSION
version (`GET /appStoreVersions/{vid}/build` first and exclude it); (3) print the
kill list and confirm before PATCHing. Recovery if you botch it: you can't
un-expire, so upload a fresh build and re-attach it.

## What still needs a human (not headless)

- **App Privacy "nutrition label"** (data-collection questionnaire) — separate
  from the privacy-policy URL. `/apps/{id}/appDataUsages` 404s via the API until
  it's initialized once in the ASC UI; it is a developer *attestation*, so leave
  it to the human rather than auto-filling. (For an app that sends data only to a
  server the *user* operates, "Data Not Collected" is usually defensible — but
  that's the developer's call.)
- **Review notes / demo credentials** — if the app needs a backend for review,
  the reviewer needs a way in. Don't bake credentials into the binary without the
  owner's say-so.
- **Submit for Review** — the final button. Everything above stages with
  `submit_for_review: false`; a listing can be fully "ready" without it.

## Privacy + support pages (Apple requires both URLs)

Host on the marketing site. For a single-page Hugo entry (a leaf `foo.md`, not a
section), add sibling pages with a `url:` front-matter override so you don't have
to restructure into a branch bundle:

```yaml
# content/english/foo-privacy.md
url: "/foo/privacy/"     # clean nested URL, no leaf-vs-branch collision
```
Build and grep the output for a duplicate-target-URL warning to confirm.

## Related skills

- **`pink-lady-apple:testflight-ship`** — beta distribution, the ASC API helper script, tester invitation.
- **`pink-lady-apple:apple-release`** — Fastlane plumbing, Ruby pinning, signing via match.
- **`pink-lady-apple:sim-capture`** — driving the simulator to produce the screenshots.
