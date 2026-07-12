# ASC API Endpoint Reference

Raw HTTP request shapes for the endpoints used by `testflight-ship`, for when you need to go beyond `scripts/asc.py`. All require a JWT bearer token built from the user's API key (`AuthKey_<ASC_KEY_ID>.p8`). See `scripts/asc.py:token()` for the JWT construction.

## Apple's API restrictions (things the API does NOT let you do)

Apple treats some operations as "user session required" — API-key auth returns 403. These are the only true API blockers:

| Operation | API verb | Result with API key |
|---|---|---|
| Create an app | `POST /v1/apps` | `403 FORBIDDEN_ERROR` ("does not allow 'CREATE'") |
| Modify `visibleApps` for account holder | `PATCH /users/{id}/relationships/visibleApps` | `403 FORBIDDEN_ERROR.ALL_APPS_VISIBLE` (they have all-apps access by role) |

When you hit these, prompt the user to do it in the ASC web UI.

### Things that LOOK blocked but aren't (Apple's docs are misleading)

| Operation | Docs say | Reality |
|---|---|---|
| Set `isInternalGroup` on create | "read-only" | Writable on POST. Just not on PATCH. Always pass it on create. |
| Set `hasAccessToAllBuilds` on create | "read-only" | Same — writable on POST, not PATCH. |
| Add betaTester to internal group | (undocumented) | Works. Group stays internal. |

### Things you canNOT do for a different reason (API intent, not auth)

| Operation | Result | Why |
|---|---|---|
| Explicitly distribute a build to an internal group | `422 ENTITY_UNPROCESSABLE: "Cannot add internal group to a build."` | Internal groups with `hasAccessToAllBuilds` auto-receive all builds. Don't call distribute. |

## Bundle IDs and Capabilities

### Register a bundle ID

```
POST /v1/bundleIds
{
  "data": {
    "type": "bundleIds",
    "attributes": {
      "identifier": "com.example.MyApp",
      "name": "MyApp",
      "platform": "IOS"
    }
  }
}
```

Response 201: `data.id` is the bundle ID record (e.g. `<bundle-record-id>`) — save it, you'll need it to attach capabilities.

### Add a capability to a bundle ID

```
POST /v1/bundleIdCapabilities
{
  "data": {
    "type": "bundleIdCapabilities",
    "attributes": {"capabilityType": "NFC_TAG_READING"},
    "relationships": {
      "bundleId": {"data": {"type": "bundleIds", "id": "<bundle-record-id>"}}
    }
  }
}
```

Common capability types: `NFC_TAG_READING`, `ICLOUD`, `PUSH_NOTIFICATIONS`, `HEALTHKIT`, `IN_APP_PURCHASE`, `ASSOCIATED_DOMAINS`, `APP_GROUPS`, `HOMEKIT`, `WIRELESS_ACCESSORY_CONFIGURATION`.

## Apps

### Look up an app by bundle ID

```
GET /v1/apps?filter[bundleId]=com.example.MyApp
```

Response 200: `data[0].id` is the app's ASC ID (e.g. `<app-id>`) — pass as `app_id` in later calls.

### Create an app

**Do not attempt via API.** Returns `403 FORBIDDEN_ERROR`. Manual step in ASC web UI.

## Builds

### List recent builds

```
GET /v1/builds?filter[app]=<app-id>&sort=-version&limit=3
```

Key attributes:
- `processingState` = `PROCESSING` | `VALID` | `INVALID` | `FAILED`
- `usesNonExemptEncryption` = `true` | `false` | `null` (null = not declared = build cannot be distributed)
- `uploadedDate`, `expired`, `expirationDate`

### Declare export compliance on a build

```
PATCH /v1/builds/{build_id}
{
  "data": {
    "type": "builds",
    "id": "<build_id>",
    "attributes": {"usesNonExemptEncryption": false}
  }
}
```

Response 200. Needed if `ITSAppUsesNonExemptEncryption` was not set in Info.plist at build time. Bake the Info.plist key in once and this step becomes unnecessary.

### List the beta groups a build is distributed to

```
GET /v1/builds/{build_id}/betaGroups
```

Empty array = build is invisible to every tester. This is the canary for "I shipped but forgot to distribute."

## Beta Groups

### List groups for an app

```
GET /v1/apps/{app_id}/betaGroups?limit=100
```

### Get group details

```
GET /v1/betaGroups/{group_id}
```

Key attributes:
- `isInternalGroup` (read-only) — `true` means ASC-user-based internal group, distribute is instant; `false` means external, requires Beta App Review
- `hasAccessToAllBuilds` (read-only) — `true` means every new VALID build auto-distributes to the group; `false` means you must distribute each build manually
- `feedbackEnabled` — tester feedback on/off
- `publicLinkEnabled`, `publicLink`, `publicLinkLimit` — external-only public invite

### Create an internal group (with auto-distribution)

```
POST /v1/betaGroups
{
  "data": {
    "type": "betaGroups",
    "attributes": {
      "name": "InternalTesters",
      "isInternalGroup": true,
      "hasAccessToAllBuilds": true
    },
    "relationships": {
      "app": {"data": {"type": "apps", "id": "<app_id>"}}
    }
  }
}
```

Both attributes are writable on POST despite Apple's docs describing them as read-only. Without them, the group comes out external — that's the recurring failure mode.

### Create an external group

```
POST /v1/betaGroups
{
  "data": {
    "type": "betaGroups",
    "attributes": {
      "name": "ExternalTesters",
      "publicLinkEnabled": false
    },
    "relationships": {
      "app": {"data": {"type": "apps", "id": "<app_id>"}}
    }
  }
}
```

External groups require Beta App Review and a privacy policy URL before any tester sees any build. Used rarely — only when you need testers outside the ASC team.

### Distribute a build to an EXTERNAL group

```
POST /v1/builds/{build_id}/relationships/betaGroups
{
  "data": [{"type": "betaGroups", "id": "<external_group_id>"}]
}
```

Response 204 for external groups. For internal groups, this returns `422 "Cannot add internal group to a build"` — don't call it. Internal groups with `hasAccessToAllBuilds: true` auto-receive all VALID builds; use `GET /betaGroups/{id}/builds` to verify.

### Delete a beta group

```
DELETE /v1/betaGroups/{group_id}
```

Response 204. Testers in the group are unaffected (they exist independently); the group is just dissolved.

## Beta Testers

### Create a tester and attach to an external group

```
POST /v1/betaTesters
{
  "data": {
    "type": "betaTesters",
    "attributes": {
      "email": "person@example.com",
      "firstName": "First",
      "lastName": "Last"
    },
    "relationships": {
      "betaGroups": {
        "data": [{"type": "betaGroups", "id": "<external_group_id>"}]
      }
    }
  }
}
```

Response 201. **Do not call on internal groups** — doing so flips them to external and you can't flip them back.

### Tester records are per-app

Testers cannot be reused across apps. If a tester with that email already exists for a different app, a new POST returns `409 STATE_ERROR` when you try to attach. Create a new record for each app where they need access.

### List testers in a group

```
GET /v1/betaGroups/{group_id}/betaTesters
```

### Remove a tester from a group

```
DELETE /v1/betaGroups/{group_id}/relationships/betaTesters
{
  "data": [{"type": "betaTesters", "id": "<tester_id>"}]
}
```

Note: `httpx.delete()` doesn't accept a `json=` kwarg; use `client.request("DELETE", url, json=...)` instead.

### Delete a tester record entirely

```
DELETE /v1/betaTesters/{tester_id}
```

## ASC Users

### List ASC users

```
GET /v1/users
```

Returns team members. Useful for looking up user IDs (e.g. the ACCOUNT_HOLDER), but not required for internal testing — internal testers are added to groups via `POST /betaTesters` with emails, not user IDs.

### Visible apps

```
PATCH /v1/users/{user_id}/relationships/visibleApps
```

Fails with `403 FORBIDDEN_ERROR.ALL_APPS_VISIBLE` if the user has ACCOUNT_HOLDER or ADMIN roles — they see everything by role, and you can't reduce that via API.

## Endpoint-to-step map

| Step in SKILL.md | Endpoint(s) |
|---|---|
| 1a. Register bundle ID | `POST /bundleIds` |
| 1b. Enable capabilities | `POST /bundleIdCapabilities` |
| 1c. Create app | (manual — API is 403) |
| 3. Build + upload | (fastlane, not direct API) |
| 4a. Verify VALID | `GET /builds?filter[app]=...` |
| 4b. Declare compliance | `PATCH /builds/{id}` (skip if Info.plist has `ITSAppUsesNonExemptEncryption`) |
| 4c. Create internal group | `POST /betaGroups` with `isInternalGroup:true` + `hasAccessToAllBuilds:true` |
| 4d. Add tester | `POST /betaTesters` with group relationship |
| 4e. Distribute build | NO-OP for internal (auto-distributes); for external: `POST /builds/{id}/relationships/betaGroups` |
| 4f. Verify | `GET /betaGroups/{id}/builds` + `GET /betaGroups/{id}/betaTesters` |
