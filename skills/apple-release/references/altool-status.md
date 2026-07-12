# `xcrun altool` — still supported for App Store uploads

When Apple published [TN3147 — Migrating to the latest notarization tool](https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool), there was some confusion about whether `altool` was fully deprecated. It is not — only the **notarization subcommands** are deprecated, with a hard cutoff on Nov 1, 2023:

| Use case | Status |
|---|---|
| `altool --notarize-app` | **Deprecated** — use `xcrun notarytool submit` |
| `altool --notarization-info` | **Deprecated** — use `xcrun notarytool info` |
| `altool --notarization-history` | **Deprecated** — use `xcrun notarytool history` |
| `altool --upload-app` (App Store / TestFlight) | **Still supported** |
| `altool --upload-package` (App Store / TestFlight) | **Still supported** |

Apple confirms this in [fastlane discussion #21347](https://github.com/fastlane/fastlane/discussions/21347). Transporter.app (Apple's official GUI uploader) also wraps `altool --upload-app` internally, so it isn't going away.

## When to use altool as a fallback

1. Fastlane is broken mid-ship (e.g., the `prices` bug hits on a release day and you can't wait for `bundle update`)
2. You want to verify an IPA outside the fastlane stack
3. You're scripting from a context that doesn't have Ruby at all

## The invocation

```bash
xcrun altool --upload-app \
  -f path/to/App.ipa \
  -t ios \
  --apiKey <ASC_KEY_ID> \
  --apiIssuer <ASC_ISSUER_ID>
```

The `--apiKey` value is just the key ID. altool finds the actual `.p8` file by looking in these locations in order:

1. `./AuthKey_<key_id>.p8` (current directory)
2. `./private_keys/AuthKey_<key_id>.p8`
3. `~/private_keys/AuthKey_<key_id>.p8`
4. `~/.private_keys/AuthKey_<key_id>.p8`
5. `~/.appstoreconnect/private_keys/AuthKey_<key_id>.p8` ← recommended standard

So just having the key at `~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8` is enough — no extra flags needed.

## Verification after altool upload

altool prints `UPLOAD SUCCEEDED` immediately after the bytes transfer, but ASC processing takes several minutes more. **Always verify via ASC API before claiming success.** A minimal Python probe using the same `.p8` key:

```python
import sys, httpx, time
sys.path.insert(0, "scripts")
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location("asc", "scripts/asc-setup.py")
asc = module_from_spec(spec)
spec.loader.exec_module(asc)
app = asc.api("GET", f"/apps?filter[bundleId]={asc.BUNDLE_ID}")
app_id = app["data"][0]["id"]
r = httpx.get(
    f"{asc.BASE_URL}/builds?filter[app]={app_id}&sort=-uploadedDate&limit=3",
    headers={"Authorization": f"Bearer {asc.get_token()}"},
    timeout=30,
)
for b in r.json()["data"]:
    a = b["attributes"]
    print(f"build {a['version']}: {a['processingState']}")
```

Never report "uploaded successfully" until ASC shows `VALID`.
