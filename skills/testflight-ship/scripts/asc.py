#!/usr/bin/env python3
"""
ASC API helper for the testflight-ship skill.

Run via:
  uv tool run --from authlib --with httpx python3 asc.py <subcommand> [args]

Every subcommand prints its result for the caller to read; non-zero exit on
API errors so the caller can fail loudly.

Credentials are hard-wired to the user's ASC API key. The key is at
~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8 (recoverable from
Proton Pass if lost, per Fanta memory).
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from authlib.jose import jwt
    import httpx
except ImportError:
    print("Install: uv pip install authlib httpx", file=sys.stderr)
    sys.exit(1)

ISSUER_ID = "<ASC_ISSUER_ID>"
KEY_ID = "<ASC_KEY_ID>"
KEY_PATH = Path.home() / ".appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8"
BASE_URL = "https://api.appstoreconnect.apple.com/v1"


def token() -> str:
    """Mint a short-lived JWT for ASC API auth."""
    key = KEY_PATH.read_text()
    header = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": ISSUER_ID,
        "iat": now,
        "exp": now + 1200,
        "aud": "appstoreconnect-v1",
    }
    return jwt.encode(header, payload, key).decode()


def headers(content_type: bool = False) -> dict:
    h = {"Authorization": f"Bearer {token()}"}
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def bail(resp: httpx.Response, action: str) -> None:
    """Print error + exit non-zero."""
    print(f"{action} failed ({resp.status_code}):", file=sys.stderr)
    try:
        print(json.dumps(resp.json(), indent=2), file=sys.stderr)
    except Exception:
        print(resp.text, file=sys.stderr)
    sys.exit(1)


# ---------- subcommands ----------


def cmd_register_bundle(args):
    payload = {
        "data": {
            "type": "bundleIds",
            "attributes": {
                "identifier": args.identifier,
                "name": args.name,
                "platform": args.platform,
            },
        },
    }
    r = httpx.post(
        f"{BASE_URL}/bundleIds",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        bail(r, "Register bundle ID")
    record_id = r.json()["data"]["id"]
    print(f"Bundle ID registered: {args.identifier}")
    print(f"Record: {record_id}")


def cmd_add_capability(args):
    payload = {
        "data": {
            "type": "bundleIdCapabilities",
            "attributes": {"capabilityType": args.capability},
            "relationships": {
                "bundleId": {
                    "data": {"type": "bundleIds", "id": args.bundle_record},
                },
            },
        },
    }
    r = httpx.post(
        f"{BASE_URL}/bundleIdCapabilities",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        bail(r, f"Add capability {args.capability}")
    print(f"Capability {args.capability} enabled on {args.bundle_record}")


def cmd_find_app(args):
    r = httpx.get(
        f"{BASE_URL}/apps",
        params={"filter[bundleId]": args.bundle_id},
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "Find app")
    data = r.json().get("data", [])
    if not data:
        print(
            f"App with bundle ID {args.bundle_id} NOT FOUND in ASC. "
            "Create it manually at https://appstoreconnect.apple.com/apps "
            "(Apple's API forbids app creation via API keys).",
            file=sys.stderr,
        )
        sys.exit(2)
    for app in data:
        a = app["attributes"]
        print(f"id: {app['id']}")
        print(f"name: {a['name']}")
        print(f"bundleId: {a['bundleId']}")
        print(f"sku: {a.get('sku')}")


def cmd_build_status(args):
    r = httpx.get(
        f"{BASE_URL}/builds",
        params={
            "filter[app]": args.app_id,
            "sort": "-version",
            "limit": args.limit,
        },
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "Fetch build status")
    for b in r.json().get("data", []):
        a = b["attributes"]
        uploaded = a.get("uploadedDate", "?")
        enc = a.get("usesNonExemptEncryption")
        print(
            f"build {a['version']}: id={b['id']} "
            f"state={a['processingState']} "
            f"expired={a.get('expired')} "
            f"encryption={enc} "
            f"uploaded={uploaded}",
        )


def cmd_declare_compliance(args):
    payload = {
        "data": {
            "type": "builds",
            "id": args.build_id,
            "attributes": {
                "usesNonExemptEncryption": args.uses_non_exempt_encryption,
            },
        },
    }
    r = httpx.patch(
        f"{BASE_URL}/builds/{args.build_id}",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 204):
        bail(r, "Declare export compliance")
    print(f"Compliance declared on build {args.build_id}: usesNonExemptEncryption={args.uses_non_exempt_encryption}")


def cmd_create_internal_group(args):
    """Create an INTERNAL beta group with hasAccessToAllBuilds.

    Apple's docs say these attributes are read-only, but they are
    actually writable on POST (just not on PATCH). Omitting either flag
    silently produces an external group, which is the recurring failure
    mode this skill prevents."""
    payload = {
        "data": {
            "type": "betaGroups",
            "attributes": {
                "name": args.name,
                "isInternalGroup": True,
                "hasAccessToAllBuilds": True,
            },
            "relationships": {
                "app": {"data": {"type": "apps", "id": args.app_id}},
            },
        },
    }
    r = httpx.post(
        f"{BASE_URL}/betaGroups",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        bail(r, f"Create internal group {args.name}")
    data = r.json()["data"]
    a = data["attributes"]
    if not a.get("isInternalGroup") or not a.get("hasAccessToAllBuilds"):
        print(
            f"WARNING: group created but flags wrong: "
            f"isInternalGroup={a.get('isInternalGroup')} "
            f"hasAccessToAllBuilds={a.get('hasAccessToAllBuilds')}. "
            f"Delete and recreate.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"Internal group '{args.name}' created: {data['id']}")
    print("  isInternalGroup=True hasAccessToAllBuilds=True")
    print("  New VALID builds will auto-distribute to this group.")


def cmd_create_external_group(args):
    """Create an EXTERNAL beta group (for public beta / outside-team users).
    External groups require Beta App Review + a privacy policy URL."""
    payload = {
        "data": {
            "type": "betaGroups",
            "attributes": {
                "name": args.name,
                "publicLinkEnabled": args.public_link,
            },
            "relationships": {
                "app": {"data": {"type": "apps", "id": args.app_id}},
            },
        },
    }
    r = httpx.post(
        f"{BASE_URL}/betaGroups",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        bail(r, f"Create external group {args.name}")
    group_id = r.json()["data"]["id"]
    print(f"External group '{args.name}' created: {group_id}")
    print("  Note: requires Beta App Review before first build is visible.")


def cmd_add_tester(args):
    """Attach a betaTester record to a group. Works for BOTH internal
    and external groups — internal groups stay internal after this."""
    payload = {
        "data": {
            "type": "betaTesters",
            "attributes": {
                "email": args.email,
                "firstName": args.first_name,
                "lastName": args.last_name,
            },
            "relationships": {
                "betaGroups": {
                    "data": [{"type": "betaGroups", "id": args.group_id}],
                },
            },
        },
    }
    r = httpx.post(
        f"{BASE_URL}/betaTesters",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        bail(r, "Add tester")
    tester_id = r.json()["data"]["id"]
    print(f"Tester {args.email} added to group {args.group_id} (tester id: {tester_id})")


def cmd_group_builds(args):
    r = httpx.get(
        f"{BASE_URL}/betaGroups/{args.group_id}/builds",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List group builds")
    builds = r.json().get("data", [])
    if not builds:
        print(
            "No builds visible to this group yet. "
            "If you just uploaded and the group is internal with "
            "hasAccessToAllBuilds=True, wait ~30-60s for ASC to associate.",
            file=sys.stderr,
        )
        sys.exit(3)
    for b in builds:
        a = b["attributes"]
        print(f"  build {a['version']} state={a['processingState']}")


def cmd_group_details(args):
    r = httpx.get(
        f"{BASE_URL}/betaGroups/{args.group_id}",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "Fetch group details")
    a = r.json()["data"]["attributes"]
    print(f"name: {a['name']}")
    print(f"isInternalGroup: {a.get('isInternalGroup')}")
    print(f"hasAccessToAllBuilds: {a.get('hasAccessToAllBuilds')}")
    print(f"feedbackEnabled: {a.get('feedbackEnabled')}")
    print(f"createdDate: {a.get('createdDate')}")
    if a.get("isInternalGroup") is False:
        print(
            "\nWARNING: this group is EXTERNAL. External groups require Beta App Review before testers see builds.",
            file=sys.stderr,
        )


def cmd_build_groups(args):
    r = httpx.get(
        f"{BASE_URL}/builds/{args.build_id}/betaGroups",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List build groups")
    groups = r.json().get("data", [])
    if not groups:
        print(
            "Build is distributed to NO groups. "
            "It is invisible to every tester. "
            "Run `distribute` with a valid group id to complete shipping.",
            file=sys.stderr,
        )
        sys.exit(3)
    for g in groups:
        a = g["attributes"]
        print(f"  {g['id']}: {a['name']} internal={a.get('isInternalGroup')}")


def cmd_distribute(args):
    """Explicit distribution — only valid for EXTERNAL groups.
    Internal groups with hasAccessToAllBuilds=True auto-receive every
    new VALID build; calling distribute on them returns 422."""
    with httpx.Client(timeout=30) as client:
        # Pre-flight: refuse if target group is internal
        r = client.get(
            f"{BASE_URL}/betaGroups/{args.group_id}",
            headers=headers(),
        )
        if r.status_code == 200 and r.json()["data"]["attributes"].get("isInternalGroup"):
            print(
                "REFUSING: this group is internal. Internal groups auto-receive "
                "all VALID builds via hasAccessToAllBuilds=true. Calling distribute "
                "on them returns 422. Use `group-builds` to verify auto-distribution "
                "happened.",
                file=sys.stderr,
            )
            sys.exit(1)

        payload = {"data": [{"type": "betaGroups", "id": args.group_id}]}
        r = client.post(
            f"{BASE_URL}/builds/{args.build_id}/relationships/betaGroups",
            headers=headers(content_type=True),
            json=payload,
        )
        if r.status_code not in (200, 204):
            bail(r, "Distribute build")
        print(f"Build {args.build_id} distributed to external group {args.group_id}")


def cmd_list_testers(args):
    r = httpx.get(
        f"{BASE_URL}/betaGroups/{args.group_id}/betaTesters",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List testers")
    testers = r.json().get("data", [])
    if not testers:
        print(
            "No testers in group. "
            "If you just uploaded a build, it is NOT visible to anyone yet. "
            "Run `add-tester` now or the shipment is incomplete.",
            file=sys.stderr,
        )
        sys.exit(3)
    for t in testers:
        a = t["attributes"]
        print(f"  {a.get('email')} ({a.get('firstName')} {a.get('lastName')})")


def cmd_list_groups(args):
    r = httpx.get(
        f"{BASE_URL}/apps/{args.app_id}/betaGroups",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List groups")
    for g in r.json().get("data", []):
        a = g["attributes"]
        print(
            f"  {g['id']}: {a['name']} internal={a.get('isInternalGroup')} publicLink={a.get('hasPublicLink')}",
        )


def cmd_ensure_invited(args):
    """Force-invite every tester in every internal group of `--app-id` to
    the latest build by linking them via /builds/{id}/relationships/
    individualTesters.

    Workaround for a TestFlight bug where adding a tester to an internal
    group with `hasAccessToAllBuilds: true` does NOT actually trigger
    the invite — `betaTester.state` stays null and TestFlight never
    pings the device. POSTing the tester to the build's individualTesters
    relationship flips state to INVITED, which is what triggers the push.

    One app's build 1 (2026-05-03) hit this: every step of the
    canonical workflow was correct (group internal, hasAccessToAllBuilds,
    tester attached, autoNotifyEnabled patched), but the tester still got
    nothing because tester.state stayed null. Linking via individualTesters
    resolved it.
    """
    # Find the latest build for the app
    r = httpx.get(
        f"{BASE_URL}/builds?filter[app]={args.app_id}&sort=-uploadedDate&limit=1",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "Find latest build")
    builds = r.json().get("data", [])
    if not builds:
        print("No builds found for app", file=sys.stderr)
        sys.exit(3)
    build_id = builds[0]["id"]
    build_version = builds[0]["attributes"].get("version")
    print(f"Latest build: v{build_version} ({build_id})")

    # Find all internal groups for the app
    r = httpx.get(
        f"{BASE_URL}/apps/{args.app_id}/betaGroups",
        headers=headers(),
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List groups")
    internal_groups = [g for g in r.json().get("data", []) if g["attributes"].get("isInternalGroup")]
    print(f"Internal groups: {[g['attributes']['name'] for g in internal_groups]}")

    # Collect every tester in every internal group
    tester_ids: set[str] = set()
    for g in internal_groups:
        rt = httpx.get(
            f"{BASE_URL}/betaGroups/{g['id']}/betaTesters",
            headers=headers(),
            timeout=30,
        )
        for t in rt.json().get("data", []):
            tester_ids.add(t["id"])
    if not tester_ids:
        print("No testers in any internal group — add one via add-tester first", file=sys.stderr)
        sys.exit(3)

    # POST each tester to the build's individualTesters relationship.
    # 409 STATE_ERROR is fine — it means the tester is already linked,
    # which is the desired end state.
    payload = {
        "data": [{"type": "betaTesters", "id": tid} for tid in sorted(tester_ids)],
    }
    r = httpx.post(
        f"{BASE_URL}/builds/{build_id}/relationships/individualTesters",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 204, 409):
        bail(r, "Link testers to build")
    if r.status_code == 409:
        print("(testers already linked — idempotent no-op)")

    # Verify each tester now shows as INVITED on the build
    r = httpx.get(
        f"{BASE_URL}/builds/{build_id}/individualTesters",
        headers=headers(),
        timeout=30,
    )
    invited = r.json().get("data", [])
    print(f"Testers linked to build {build_id}:")
    for t in invited:
        a = t["attributes"]
        print(f"  {a.get('email')} state={a.get('state')}")


def _resolve_internal_group(app_id: str) -> str | None:
    """Find the app's internal beta group id (the one testers live in)."""
    r = httpx.get(
        f"{BASE_URL}/apps/{app_id}/betaGroups",
        headers=headers(),
        params={"limit": 200},
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "List beta groups")
    for g in r.json().get("data", []):
        if g["attributes"].get("isInternalGroup"):
            return g["id"]
    return None


def _build_in_group(group_id: str, build_id: str) -> bool:
    """True if build_id is actually in the group's build list.

    This is the ONLY reliable way to confirm the link: Apple disallows
    GET on /builds/{id}/betaGroups (GET_RELATED not allowed), so we read the
    group's builds instead. High limit so a just-added build isn't off the
    first page.
    """
    r = httpx.get(
        f"{BASE_URL}/betaGroups/{group_id}/builds",
        headers=headers(),
        params={"limit": 200},
        timeout=30,
    )
    if r.status_code != 200:
        return False
    return any(b.get("id") == build_id for b in r.json().get("data", []))


def cmd_add_build_to_group(args):
    """POST /betaGroups/{group_id}/relationships/builds — explicit build→group link,
    then VERIFY and retry until the build actually shows up in the group.

    Works for ANY group type (internal OR external), including internal groups
    that have hasAccessToAllBuilds=False (which normally requires explicit
    distribution even though they are "internal").

    Why the verify loop: right after a build finishes processing, Apple often
    accepts this POST (204) but does NOT actually attach the build — the build
    then never reaches testers, silently. That is the recurring "uploaded but
    invisible" bug. We now confirm via the group's build list and retry, and
    exit non-zero if it never lands so the ship FAILS LOUDLY instead of leaving
    testers on an old build.

    When --app-id is given instead of --build-id, resolves to the latest build.
    When --group-id is omitted, resolves the app's internal group automatically
    (so the Fastfile doesn't need a hard-coded per-app group id).
    """
    group_id = args.group_id
    if not group_id:
        if not args.app_id:
            print("Provide --group-id or --app-id to resolve the internal group", file=sys.stderr)
            sys.exit(2)
        group_id = _resolve_internal_group(args.app_id)
        if not group_id:
            print(f"No internal beta group found for app {args.app_id}", file=sys.stderr)
            sys.exit(3)
        print(f"Resolved internal group: {group_id}")

    if args.app_id and not args.build_id:
        r = httpx.get(
            f"{BASE_URL}/builds?filter[app]={args.app_id}&sort=-uploadedDate&limit=1",
            headers=headers(),
            timeout=30,
        )
        if r.status_code != 200:
            bail(r, "Find latest build")
        data = r.json().get("data", [])
        if not data:
            print("No builds found for app", file=sys.stderr)
            sys.exit(3)
        build_id = data[0]["id"]
        build_version = data[0]["attributes"].get("version")
        print(f"Resolved latest build: v{build_version} ({build_id})")
    else:
        build_id = args.build_id

    payload = {"data": [{"type": "builds", "id": build_id}]}
    for attempt in range(1, 7):
        r = httpx.post(
            f"{BASE_URL}/betaGroups/{group_id}/relationships/builds",
            headers=headers(content_type=True),
            json=payload,
            timeout=30,
        )
        if r.status_code not in (200, 204, 409):
            bail(r, "Add build to group")
        if _build_in_group(group_id, build_id):
            print(f"Build {build_id} confirmed in group {group_id}")
            return
        print(
            f"Build {build_id} not yet visible in group "
            f"(attempt {attempt}/6); waiting 6s for ASC to associate...",
            file=sys.stderr,
        )
        time.sleep(6)

    print(
        f"ERROR: build {build_id} did not land in group {group_id} after 6 "
        "attempts — internal testers will NOT receive it. Re-run add-build-to-group.",
        file=sys.stderr,
    )
    sys.exit(4)


def cmd_auto_notify(args):
    """PATCH /buildBetaDetails/{id} to enable autoNotifyEnabled.

    Without this, internal testers won't get TestFlight push notifications
    when the build becomes available — the build sits in IN_BETA_TESTING
    state but nobody knows it's there. One app's build 1 (2026-05-03)
    hit this exact failure: the build was VALID, the internal group was
    set up, the tester was attached, but autoNotifyEnabled defaulted to
    false on upload, so the tester's phone never pinged.
    """
    if args.app_id and not args.build_id:
        # Resolve to the most recent build for the app.
        r = httpx.get(
            f"{BASE_URL}/builds?filter[app]={args.app_id}&sort=-uploadedDate&limit=1",
            headers=headers(),
            timeout=30,
        )
        if r.status_code != 200:
            bail(r, "Find latest build")
        data = r.json().get("data", [])
        if not data:
            print("No builds found", file=sys.stderr)
            sys.exit(3)
        build_id = data[0]["id"]
    else:
        build_id = args.build_id

    payload = {
        "data": {
            "type": "buildBetaDetails",
            "id": build_id,
            "attributes": {"autoNotifyEnabled": True},
        }
    }
    r = httpx.patch(
        f"{BASE_URL}/buildBetaDetails/{build_id}",
        headers=headers(content_type=True),
        json=payload,
        timeout=30,
    )
    if r.status_code != 200:
        bail(r, "Enable autoNotify")
    a = r.json().get("data", {}).get("attributes", {})
    print(
        f"Build {build_id}: autoNotifyEnabled={a.get('autoNotifyEnabled')} "
        f"internalBuildState={a.get('internalBuildState')}",
    )


# ---------- argparse ----------


def main():
    p = argparse.ArgumentParser(prog="asc", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("register-bundle", help="POST /bundleIds")
    s.add_argument("--identifier", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--platform", default="IOS", choices=["IOS", "MAC_OS"])
    s.set_defaults(func=cmd_register_bundle)

    s = sub.add_parser("add-capability", help="POST /bundleIdCapabilities")
    s.add_argument("--bundle-record", required=True, help="Bundle ID record ID from register-bundle")
    s.add_argument("--capability", required=True, help="e.g. NFC_TAG_READING, ICLOUD, PUSH_NOTIFICATIONS")
    s.set_defaults(func=cmd_add_capability)

    s = sub.add_parser("find-app", help="Locate app record by bundle id")
    s.add_argument("--bundle-id", required=True)
    s.set_defaults(func=cmd_find_app)

    s = sub.add_parser("build-status", help="Show latest build processing state")
    s.add_argument("--app-id", required=True)
    s.add_argument("--limit", type=int, default=3)
    s.set_defaults(func=cmd_build_status)

    s = sub.add_parser("declare-compliance", help="PATCH /builds/{id} usesNonExemptEncryption")
    s.add_argument("--build-id", required=True)
    s.add_argument(
        "--uses-non-exempt-encryption",
        type=lambda v: v.lower() == "true",
        default=False,
    )
    s.set_defaults(func=cmd_declare_compliance)

    s = sub.add_parser(
        "create-internal-group",
        help="POST /betaGroups with isInternalGroup+hasAccessToAllBuilds",
    )
    s.add_argument("--app-id", required=True)
    s.add_argument("--name", default="InternalTesters")
    s.set_defaults(func=cmd_create_internal_group)

    s = sub.add_parser(
        "create-external-group",
        help="POST /betaGroups (external — requires Beta App Review)",
    )
    s.add_argument("--app-id", required=True)
    s.add_argument("--name", default="ExternalTesters")
    s.add_argument("--public-link", action="store_true")
    s.set_defaults(func=cmd_create_external_group)

    s = sub.add_parser(
        "add-tester",
        help="POST /betaTesters with group relationship",
    )
    s.add_argument("--group-id", required=True)
    s.add_argument("--email", default="tester@example.com")
    s.add_argument("--first-name", default="Test")
    s.add_argument("--last-name", default="User")
    s.set_defaults(func=cmd_add_tester)

    s = sub.add_parser("group-details", help="GET /betaGroups/{id}")
    s.add_argument("--group-id", required=True)
    s.set_defaults(func=cmd_group_details)

    s = sub.add_parser("group-builds", help="GET /betaGroups/{id}/builds")
    s.add_argument("--group-id", required=True)
    s.set_defaults(func=cmd_group_builds)

    s = sub.add_parser("build-groups", help="GET /builds/{id}/betaGroups")
    s.add_argument("--build-id", required=True)
    s.set_defaults(func=cmd_build_groups)

    s = sub.add_parser("distribute", help="POST /builds/{id}/relationships/betaGroups")
    s.add_argument("--build-id", required=True)
    s.add_argument("--group-id", required=True)
    s.set_defaults(func=cmd_distribute)

    s = sub.add_parser("list-testers", help="GET /betaGroups/{id}/betaTesters")
    s.add_argument("--group-id", required=True)
    s.set_defaults(func=cmd_list_testers)

    s = sub.add_parser("list-groups", help="GET /apps/{id}/betaGroups")
    s.add_argument("--app-id", required=True)
    s.set_defaults(func=cmd_list_groups)

    s = sub.add_parser(
        "auto-notify",
        help="PATCH buildBetaDetails to set autoNotifyEnabled=true (so testers get pings)",
    )
    s.add_argument("--build-id", help="Build ID to patch (omit if --app-id given)")
    s.add_argument("--app-id", help="App ID — uses the most recent build for this app")
    s.set_defaults(func=cmd_auto_notify)

    s = sub.add_parser(
        "ensure-invited",
        help="Force-invite all internal-group testers to the latest build (workaround for the null-state bug)",
    )
    s.add_argument("--app-id", required=True)
    s.set_defaults(func=cmd_ensure_invited)

    s = sub.add_parser(
        "add-build-to-group",
        help="Link a build to a beta group and VERIFY it landed (retries, fails loud). Works for any group type, including internal groups with hasAccessToAllBuilds=False",
    )
    s.add_argument("--group-id", help="Beta group ID (omit with --app-id to auto-resolve the internal group)")
    s.add_argument("--build-id", help="Build ID (omit if --app-id given)")
    s.add_argument("--app-id", help="App ID — resolves the latest build and, if --group-id is omitted, the internal group")
    s.set_defaults(func=cmd_add_build_to_group)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
