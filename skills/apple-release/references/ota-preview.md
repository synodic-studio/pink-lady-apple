# OTA Preview Builds Reference

Self-hosted OTA app distribution at `preview.kj6.dev` via Cloudflare Pages.

## Deploy Script

Works from any repo:
```bash
<deploy-preview-script> \
  --name "App Name Dev" \
  --bundle-id "com.example.AppName.debug" \
  --ipa /path/to/App.ipa \
  --description "Short description" \
  --icon-emoji "📱"
```

**Critical rules for `--name`:** Use the Debug display name (e.g. "an example app Dev", not "an example app"). This becomes the manifest `title` which iOS shows during install. Must match `CFBundleDisplayName` from the Debug build.

## Details

- Registry at `~/.config/app-preview/apps.json` — each deploy is additive (existing apps stay)
- Site files at `~/.config/app-preview/site/` — regenerated from registry on each deploy
- Landing page auto-generated with all registered apps
- Uses `itms-services://` protocol — open preview.kj6.dev on iPhone to install
- Development signing only — registered devices in provisioning profile
- **Bump build number** between deploys or iOS won't recognize the update

## Typical Workflow

Archive, export, deploy:
```bash
xcodebuild archive -scheme AppName -project App.xcodeproj -configuration Debug \
  -archivePath /tmp/App.xcarchive -destination 'generic/platform=iOS' -quiet
xcodebuild -exportArchive -archivePath /tmp/App.xcarchive \
  -exportPath /tmp/App-export -exportOptionsPlist ExportOptions.plist
<deploy-preview-script> --name "App Name Dev" \
  --bundle-id "com.example.AppName.debug" --ipa /tmp/App-export/AppName.ipa \
  --description "Short desc" --icon-emoji "🎯"
```
