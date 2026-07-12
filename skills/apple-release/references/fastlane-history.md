# Fastlane `prices` relationship bug — full history

## The symptom

On fastlane 2.205.1 (or any version before 2.212.2), any call that lists or looks up an app via ASC API crashes with:

```
Spaceship::UnexpectedResponse:
  A parameter has an invalid value - 'prices' is not a valid relationship name
```

This happens inside `pilot`'s `fetch_app_id`, during:
- `upload_to_testflight`
- `latest_testflight_build_number`
- `app_store_build_number`
- Anything that calls `Spaceship::ConnectAPI::App.find` or `.all`

The failure occurs BEFORE the actual upload — so if you hit this error, your IPA is still fine and can be shipped via `xcrun altool` as a fallback.

## The root cause

Apple removed the `prices` relationship from the `apps` resource in the App Store Connect API during the **March 2023 pricing overhaul**. Before that change, apps had prices directly attached; after, prices live in a separate `appPriceSchedules` hierarchy.

Fastlane's Spaceship layer (`spaceship/lib/spaceship/connect_api/models/app.rb`) had `prices` hard-coded in `ESSENTIAL_INCLUDES`, which meant every app lookup sent `include=prices` as a query parameter. Apple accepted this silently for some time, then began enforcing the new schema around April 2024, at which point the requests started failing with the error above.

## The fix

[fastlane/fastlane#21187](https://github.com/fastlane/fastlane/pull/21187) — "[spaceship] remove deprecated attributes from apps requests" — removed `prices` from `ESSENTIAL_INCLUDES`. Shipped in **fastlane 2.212.2** on 2023-04-16.

```
gem "fastlane", ">= 2.212.2"
```

## The Ruby version cliff

| Fastlane version range | Minimum Ruby |
|---|---|
| 2.212.2 – 2.226.0 | 2.6 |
| 2.227.0 – current | 2.7+ |

If you're stuck on system macOS Ruby (`2.6.10` on Sonoma and later), cap at `~> 2.226`. If you have mise or rbenv available, install Ruby 3.3.x and use current stable (`~> 2.232`) — this is the recommended standard.

## Why mise + vendor/bundle

Using system Ruby + global `gem install fastlane` creates three problems:

1. **Version drift across repos** — `gem install` is user-global. Every repo uses whatever was installed last. No way to pin per-project.
2. **Native extension breakage** — on macOS updates, bundled Ruby gems with C extensions (`json`, `ffi`, `patron`, `libxml-ruby`, `digest-crc`, `bigdecimal`, `date`) often break their builds. `Ignoring ffi-1.15.5 because its extensions are not built. Try: gem pristine ffi --version 1.15.5` — you've seen this. System Ruby 2.6 on macOS Sonoma is particularly fragile.
3. **Can't upgrade fastlane without upgrading everything** — if repo A needs fastlane 2.232 and repo B needs 2.226, you can't have both with global gems.

Solution: mise-managed Ruby (pinned per repo via `.mise.toml`) + bundler-managed gems in `vendor/bundle/` (per repo). Each repo is hermetic. `bundle install` gives you the exact version you committed in `Gemfile.lock`, nothing else.

## Sources

- [Issue #21975 — 'prices' is not a valid relationship name](https://github.com/fastlane/fastlane/issues/21975)
- [Issue #21819 — 'prices' is not a relationship on the resource](https://github.com/fastlane/fastlane/issues/21819)
- [Issue #21125 — Listing apps fails due to pricing update](https://github.com/fastlane/fastlane/issues/21125)
- [PR #21187 — [spaceship] remove deprecated attributes from apps requests](https://github.com/fastlane/fastlane/pull/21187)
- [Release 2.212.2](https://github.com/fastlane/fastlane/releases/tag/2.212.2)
- [RubyGems 2.226.0 — required_ruby_version >= 2.6](https://rubygems.org/gems/fastlane/versions/2.226.0)
- [RubyGems 2.232.2 — required_ruby_version >= 2.7](https://rubygems.org/gems/fastlane/versions/2.232.2)
