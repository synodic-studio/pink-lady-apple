#!/usr/bin/env bash
#
# pink-lady-apple — live terminal demo
#
# What this plugin is: eight Claude Code skills that encode the Apple shipping
# toolchain — Tuist, Fastlane, App Store Connect, TestFlight, notarization —
# including the specific traps that each cost somebody an afternoon the first
# time. This demo shows the encoded knowledge and proves it is still true. It
# deliberately does NOT run a TestFlight upload: that takes many minutes and
# needs signing credentials, and a demo you cannot finish is not a demo.
#
# THE BEATS
#
#   1. The trap.        One encoded failure, quoted from the skill: the verbatim
#                       error, the root cause, the upstream PR that fixed it,
#                       the version to bump to, and the escape hatch for when
#                       you have to ship anyway.
#   2. The census.      Every skill carries a section whose job is failures.
#                       Counted live by one grep over section headings, plus
#                       the size of the corpus and a fence-balance check.
#   3. Still true?      The skill claims three Ruby version floors. Both the
#                       claim and the truth are computed live — the claim is
#                       parsed out of the markdown, the truth comes off the
#                       rubygems API — and diffed. PASS or DRIFT, either is a
#                       real answer.
#   4. The handoff.     What another engineer actually gets: manifest validated
#                       strict, component inventory, per-session token cost,
#                       and the ASC helper's real subcommand list.
#
# FLAGS
#
#   --auto        Run start to finish with no keypresses. Rehearsal and smoke test.
#   --cleanup     Remove the fetched rubygems response from a previous run.
#   -h, --help    Print this header.
#
# SETTINGS
#
#   scripts/demo.env (gitignored) overrides anything in scripts/demo.env.example.
#   RUBYGEMS_URL points beat 3 somewhere else — a mirror, or a dead host to
#   watch the degrade path. Every value has a default; the file is optional.
#
# HOSTILE NETWORK
#
#   Beat 3 is the only beat that touches the network. It times out in
#   RUBYGEMS_TIMEOUT seconds, says so, and the demo keeps going. Beats 1, 2
#   and 4 are entirely local, which is why the demo ends on a local beat.
#
# FIRST-RUN CHECKLIST — do all of this before the live run, not during it
#
#   [ ] ./scripts/demo.sh --auto        # warms the uv package cache that beat 4
#                                       # needs, and proves every beat runs
#   [ ] ./scripts/demo.sh --cleanup     # so the live run is a fresh fetch
#   [ ] claude plugin details pink-lady-apple
#       If the version disagrees with .claude-plugin/plugin.json, run
#         claude plugin marketplace update pink-lady-apple
#         claude plugin update pink-lady-apple@pink-lady-apple
#       Preflight warns about this, but fix it beforehand so it stays quiet.
#   [ ] Terminal at 100 columns or wider. Beat 1 quotes a runbook verbatim.
#
# Run it once with --auto, then --cleanup, so the first live run is not the
# first run.
#
# Deliberately no `set -e`. A beat that fails should print its failure and let
# the remaining beats run — losing the rest of the demo to one dead endpoint is
# a far worse outcome than one red line on screen. Do not "fix" this.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

# ---------------------------------------------------------------- appearance

if [ -t 1 ] && [ -z "$NO_COLOR" ]; then
  B=$'\033[1m'; D=$'\033[2m'; Y=$'\033[33m'; G=$'\033[32m'
  C=$'\033[36m'; M=$'\033[31m'; R=$'\033[0m'
else
  B=''; D=''; Y=''; G=''; C=''; M=''; R=''
fi

AUTO=""
CLEANUP=""

for arg in "$@"; do
  case "$arg" in
    --auto)      AUTO=1 ;;
    --cleanup)   CLEANUP=1 ;;
    -h|--help)   awk 'NR < 3 { next } !/^#/ { exit } { sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
                 exit 0 ;;
    *)           printf 'unknown flag: %s (try -h)\n' "$arg" >&2; exit 2 ;;
  esac
done

warn() { printf '%s   !  %s%s\n' "$Y" "$1" "$R"; }
die()  { printf '%s   x  %s%s\n' "$M" "$1" "$R"; exit 1; }

beat() {
  printf '\n\n%s%s══ %s %s%s\n\n' "$C" "$B" "$1" "$2" "$R"
}

# Quote an argument for display so the echoed command is one somebody can paste
# back. Without this, `grep -rn "some phrase"` renders as five bare words and a
# skeptic cannot re-run the thing you just claimed to have run.
_q() {
  case "$1" in
    ''|*[![:alnum:]_./=:@,+-]*) printf "'%s'" "$1" ;;
    *)                          printf '%s' "$1" ;;
  esac
}

# The command is part of the evidence. Print it, then run it, so nothing on
# screen arrives without the audience seeing where it came from.
run() {
  local a disp=""
  for a in "$@"; do disp="$disp $(_q "$a")"; done
  printf '%s%s$%s%s\n' "$B" "$C" "$disp" "$R"
  "$@"
}

# Same, for pipelines that have to go through a shell.
runsh() {
  printf '%s%s$ %s%s\n' "$B" "$C" "$1" "$R"
  bash -c "$1"
}

# Print the command, run it, and keep its output in CAP_OUT as well as showing
# it — for the one beat that has to compare what it printed against something
# else. Capturing runsh directly would swallow the echoed command line into the
# data, which is exactly the bug this exists to avoid.
capsh() {
  printf '%s%s$ %s%s\n' "$B" "$C" "$1" "$R"
  CAP_OUT="$(bash -c "$1")"
  CAP_RC=$?
  [ -n "$CAP_OUT" ] && printf '%s\n' "$CAP_OUT"
  return $CAP_RC
}

stat_line() { printf '   %s%-32s%s %s%s%s\n' "$D" "$1" "$R" "$B" "$2" "$R"; }

# Anything the operator has to do or say gets its own voice, so it can never be
# mistaken for program output.
cue() {
  printf '\n%s%s   %s%s\n' "$Y" "$B" "$1" "$R"
  printf '%s%s   %s%s\n' "$Y" "$D" "$2" "$R"
}

# Every prompt says what the keypress does. "[any key]" leaves the operator
# guessing whether they are advancing a slide or ending their turn.
advance() {
  [ -n "$AUTO" ] && return 0
  printf '\n%s   [ %s ]%s' "$D" "$1" "$R"
  read -n 1 -s -r _ <&3
  printf '\r%*s\r' $((${#1} + 12)) ""
}

# ---------------------------------------------------------------- settings

RUBYGEMS_URL_DEFAULT="https://rubygems.org/api/v1/versions/fastlane.json"
[ -f "$REPO/scripts/demo.env" ] && . "$REPO/scripts/demo.env"
RUBYGEMS_URL="${RUBYGEMS_URL:-$RUBYGEMS_URL_DEFAULT}"
RUBYGEMS_TIMEOUT="${RUBYGEMS_TIMEOUT:-12}"
DEMO_CACHE="${DEMO_CACHE:-${TMPDIR:-/tmp}/pink-lady-apple-demo}"
DEMO_CACHE="$(printf '%s' "$DEMO_CACHE" | sed 's://*:/:g')"   # TMPDIR often ends in /

HIST="skills/apple-release/references/fastlane-history.md"
RELEASE="skills/apple-release/SKILL.md"
ASC="skills/testflight-ship/scripts/asc.py"

# ---------------------------------------------------------------- cleanup

if [ -n "$CLEANUP" ]; then
  # Refuse to remove anything this demo did not create. A typo in demo.env must
  # not be able to reach a directory somebody works in.
  case "$DEMO_CACHE" in
    ""|"/"|"$HOME"|"$REPO"|"$REPO"/*|/etc*|/usr*|/var|/tmp|/private/tmp)
      die "refusing to clean up '$DEMO_CACHE' — that is not a path this demo created" ;;
  esac
  if [ ! -e "$DEMO_CACHE" ]; then
    printf '   nothing to clean: %s does not exist\n' "$DEMO_CACHE"
    exit 0
  fi
  if [ ! -f "$DEMO_CACHE/.pink-lady-demo" ]; then
    die "refusing to clean up '$DEMO_CACHE' — no .pink-lady-demo marker inside it"
  fi
  rm -rf -- "$DEMO_CACHE" && printf '   removed %s\n' "$DEMO_CACHE"
  exit 0
fi

# ---------------------------------------------------------------- tty guard

# Without a terminal every keypress returns instantly and all four beats scroll
# past in one second, which looks exactly like the demo crashing. Test the
# redirect in a subshell first: a failed `exec` prints its own error before a
# 2>/dev/null on the same line can suppress it.
if [ -z "$AUTO" ]; then
  if (exec 3</dev/tty) 2>/dev/null; then
    exec 3</dev/tty
  else
    warn "No terminal to read keypresses from, so every beat would run at once."
    warn "Run it from a terminal, or use --auto to run the whole thing."
    exit 1
  fi
fi

# ---------------------------------------------------------------- preflight

printf '\n%s%spink-lady-apple — preflight%s\n\n' "$B" "$C" "$R"

[ -f .claude-plugin/plugin.json ] || die "not in the pink-lady-apple repo (no .claude-plugin/plugin.json)"
[ -f "$HIST" ] || die "missing $HIST — beats 1 and 3 read it"
[ -f "$RELEASE" ] || die "missing $RELEASE — beat 1 reads it"

# Beat 3's whole point is that the number came off the wire in the last second.
# A response left over from an earlier run would let a skeptic ask whether this
# is yesterday's file, and there would be no good answer. Refuse up front and
# name the flag, rather than discovering it on the last slide.
if [ -e "$DEMO_CACHE" ]; then
  warn "A previous run left $DEMO_CACHE behind."
  warn "Beat 3 must fetch fresh or it proves nothing. Clear it:"
  printf '\n       %s./scripts/demo.sh --cleanup%s\n\n' "$B" "$R"
  exit 1
fi

TREE_VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' .claude-plugin/plugin.json)"
printf '   working tree      %s v%s%s\n' "$B" "$TREE_VERSION" "$R"

HAVE_CURL=1; HAVE_JQ=1; HAVE_CLAUDE=1; HAVE_UV=1
command -v curl >/dev/null 2>&1 || { HAVE_CURL=""; warn "no curl — beat 3 will degrade"; }
command -v jq   >/dev/null 2>&1 || { HAVE_JQ="";   warn "no jq — beat 3 will degrade"; }
command -v uv   >/dev/null 2>&1 || { HAVE_UV="";   warn "no uv — beat 4 skips the asc.py subcommand list"; }

if command -v claude >/dev/null 2>&1; then
  INSTALLED="$(claude plugin details pink-lady-apple 2>/dev/null | sed -n '1s/^pink-lady-apple *//p')"
  if [ -z "$INSTALLED" ]; then
    warn "pink-lady-apple is not installed as a plugin — beat 4 will show the tree only"
    warn "  claude plugin marketplace add synodic-studio/pink-lady-apple"
  elif [ "$INSTALLED" != "$TREE_VERSION" ]; then
    warn "installed plugin is v$INSTALLED but the tree is v$TREE_VERSION — beat 4 will disagree with itself"
    warn "  claude plugin marketplace update pink-lady-apple && claude plugin update pink-lady-apple@pink-lady-apple"
  else
    printf '   installed plugin  %s v%s%s   (matches the tree)\n' "$B" "$INSTALLED" "$R"
  fi
else
  HAVE_CLAUDE=""
  warn "no claude CLI — beat 4 will show the tree without the component inventory"
fi

printf '   rubygems          %s%s%s\n' "$D" "$RUBYGEMS_URL" "$R"
printf '\n%s   preflight done — nothing below this line is cached or hardcoded%s\n' "$G" "$R"

advance "press to start beat 1 — the trap"

# ============================================================ BEAT 1 — the trap

beat "1/4" "The trap, in the skill's own words"

cue "Say: this is a real error somebody hit shipping a real build." \
    "The plugin is searchable by the error text you paste out of a failed lane."

run grep -rn "is not a valid relationship name" skills/ --include='*.md'

printf '\n'
runsh "awk '/^## The symptom/,/^## The root cause/' $HIST | sed '\$d'"

advance "press for the answer the skill gives"

runsh "awk '/^### .+prices. is not a valid relationship name/{f=1} f && /^### / && !/relationship name/{exit} f' $RELEASE"

printf '\n'
runsh "grep -n 'PR fastlane/fastlane#21187\\|pull/21187' $HIST $RELEASE skills/apple-release/templates/Gemfile.tmpl"

cue "Say: error text, root cause, the upstream PR, the version to bump to," \
    "and the escape hatch for when you have to ship tonight anyway."

advance "press for beat 2 — how many of these are in here"

# ============================================================ BEAT 2 — the census

beat "2/4" "How much of this plugin is failure knowledge"

cue "Say: one grep, one pattern, no curated list of strings." \
    "Every skill has a section whose entire job is the ways this breaks."

# One copy of the pattern. If the list on screen and the count under it were
# allowed to drift apart, the demo would contradict itself in front of the
# audience — which is precisely what it is here to argue against.
TRAP_RE='^## .*(troubleshoot|gotcha|mistake|silent failure|common error|what NOT to do|\bbug\b|\btrap\b|landmine|block a )'

run grep -rniE "$TRAP_RE" skills/ --include=*.md

TRAP_SECTIONS="$(grep -rniE "$TRAP_RE" skills/ --include='*.md' 2>/dev/null | wc -l | tr -d ' ')"
SKILLS="$(find skills -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')"
WITH_TRAPS="$(grep -rliE "$TRAP_RE" skills/ --include='*.md' 2>/dev/null | cut -d/ -f2 | sort -u | wc -l | tr -d ' ')"
CORPUS_FILES="$(find skills -type f \( -name '*.md' -o -name '*.py' -o -name '*.tmpl' \) | wc -l | tr -d ' ')"
CORPUS_LINES="$(find skills -type f \( -name '*.md' -o -name '*.py' -o -name '*.tmpl' \) -exec cat {} + | wc -l | tr -d ' ')"

# An odd fence count means a code block somewhere never closes, which silently
# swallows whatever follows it. Cheap to check, so check it on screen.
FENCES="$(grep -rc '^```' skills/ --include='*.md' 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')"
if [ $((FENCES % 2)) -eq 0 ]; then
  FENCE_NOTE="${G}all balanced${R}"
else
  FENCE_NOTE="${M}UNBALANCED — a code block somewhere never closes${R}"
fi

printf '\n'
stat_line "skills"                        "$SKILLS"
stat_line "with a failure section"        "$WITH_TRAPS of $SKILLS"
stat_line "such sections"                 "$TRAP_SECTIONS"
stat_line "files / lines"                 "$CORPUS_FILES / $CORPUS_LINES"
printf '   %s%-32s%s %s%s%s  (%b)\n' "$D" "code blocks" "$R" "$B" "$((FENCES / 2))" "$R" "$FENCE_NOTE"

cue "Say: those are lift-and-run blocks, not illustrations." \
    "The whole reason it ships placeholders is so you can paste them."

advance "press for beat 3 — but is any of it still true"

# ============================================================ BEAT 3 — conformance

beat "3/4" "The claim, checked against the source, live"

cue "Say: encoded knowledge rots. Fastlane raises its Ruby floor in point" \
    "releases. So the skill ships the query that regenerates its own table."

printf '   %sclaimed, parsed out of %s:%s\n\n' "$D" "$HIST" "$R"
runsh "sed -n '/^| Fastlane version range/,/^\$/p' $HIST"

CLAIMED=""
while IFS=' ' read -r cv cf; do
  [ -n "$cv" ] && CLAIMED="$CLAIMED$cv $cf"$'\n'
done < <(sed -n 's/^| \([0-9][0-9.]*\)[^|]*| \([0-9][0-9.]*\) |$/\1 \2/p' "$HIST")

if [ -z "$CLAIMED" ]; then
  warn "could not parse a version table out of $HIST — skipping the comparison"
else
  advance "press to fetch the truth from rubygems"

  mkdir -p "$DEMO_CACHE" && : > "$DEMO_CACHE/.pink-lady-demo"
  RESP="$DEMO_CACHE/fastlane-versions.json"

  printf '\n'
  if [ -n "$HAVE_CURL" ]; then
    run curl -sS --max-time "$RUBYGEMS_TIMEOUT" "$RUBYGEMS_URL" \
        -o "$RESP" -w 'HTTP %{http_code}   %{size_download} bytes   %{time_total}s\n'
    CURL_RC=$?
  else
    CURL_RC=127
  fi

  LIVE=""
  if [ "$CURL_RC" -eq 0 ] && [ -s "$RESP" ] && [ -n "$HAVE_JQ" ]; then
    # This is the command the skill's own reference tells you to run. Each row
    # is the first fastlane release to demand that Ruby floor.
    CLIFF_CMD="jq -r '.[] | select(.prerelease | not) | [.number, .ruby_version] | @tsv' '$RESP' \\
  | sort -t. -k1,1n -k2,2n -k3,3n \\
  | awk -F'\t' '{gsub(/[^0-9.]/, \"\", \$2)} \$2 != p { print \$1 \"\t\" \$2; p = \$2 }'"
    printf '\n'
    capsh "$CLIFF_CMD"
    LIVE="$CAP_OUT"
  fi

  if [ -z "$LIVE" ]; then
    warn "could not reach $RUBYGEMS_URL (curl exit $CURL_RC) — no live table this run."
    warn "The check is the mechanism, not the result. Beat 4 is entirely local."
  else
    LATEST="$(jq -r '[.[] | select(.prerelease | not)] | .[0] | "\(.number)  needs Ruby \(.ruby_version)"' "$RESP" 2>/dev/null)"
    printf '\n   %scomparing every claimed floor against the fetched table%s\n\n' "$D" "$R"

    DRIFT=0
    MAX_CLAIMED=""
    while IFS=' ' read -r cv cf; do
      [ -z "$cv" ] && continue
      MAX_CLAIMED="$cv"
      lv="$(printf '%s\n' "$LIVE" | awk -F'\t' -v f="$cf" '$2 == f { print $1; exit }')"
      if [ -z "$lv" ]; then
        printf '   %sDRIFT%s  Ruby %s — the skill says it starts at %s; rubygems has no such floor\n' "$M" "$R" "$cf" "$cv"
        DRIFT=$((DRIFT + 1))
      elif [ "$lv" = "$cv" ]; then
        printf '   %sok%s     Ruby %-4s floor starts at %-9s  %s(skill agrees)%s\n' "$G" "$R" "$cf" "$lv" "$D" "$R"
      else
        printf '   %sDRIFT%s  Ruby %-4s floor starts at %-9s  %sskill says %s%s\n' "$M" "$R" "$cf" "$lv" "$M" "$cv" "$R"
        DRIFT=$((DRIFT + 1))
      fi
    done <<< "$CLAIMED"

    # A floor the skill has never heard of, newer than anything it claims, is a
    # cliff that appeared after the file was last touched. That is the failure
    # mode this check exists to catch.
    while IFS=$'\t' read -r lv lf; do
      [ -z "$lv" ] && continue
      # A floor the skill already names is handled by the loop above, even when
      # it names the wrong version — reporting it again here would double-count.
      if ! printf '%s\n' "$CLAIMED" | awk -v f="$lf" '$2 == f { hit = 1 } END { exit !hit }'; then
        newer="$(printf '%s\n%s\n' "$lv" "$MAX_CLAIMED" | sort -V | tail -1)"
        if [ "$newer" = "$lv" ] && [ "$lv" != "$MAX_CLAIMED" ]; then
          printf '   %sDRIFT%s  a new cliff landed: %s now requires Ruby %s, newer than anything the skill claims\n' "$M" "$R" "$lv" "$lf"
          DRIFT=$((DRIFT + 1))
        fi
      fi
    done <<< "$LIVE"

    printf '\n   %scurrent stable%s   %s%s%s\n' "$D" "$R" "$B" "$LATEST" "$R"
    printf '   %sraw response%s     %s\n' "$D" "$R" "$RESP"
    if [ "$DRIFT" -eq 0 ]; then
      printf '\n   %s%sPASS — every floor the skill claims matches rubygems right now%s\n' "$G" "$B" "$R"
    else
      printf '\n   %s%sDRIFT — %s claim(s) no longer match. That is the check earning its keep.%s\n' "$M" "$B" "$DRIFT" "$R"
    fi
  fi
fi

if [ -n "$LIVE" ]; then
  cue "Say: this exact check is why the table is right. It was wrong before I ran it." \
      "Open that JSON yourself if you would rather not take my word for it."
else
  cue "Say: this exact check is why the table is right. It was wrong before I ran it." \
      "The endpoint is public — rubygems.org/api/v1/versions/fastlane.json — check it later."
fi

advance "press for beat 4 — what another engineer actually gets"

# ============================================================ BEAT 4 — the handoff

beat "4/4" "The handoff — install it, price it, run it"

if [ -n "$HAVE_CLAUDE" ]; then
  run claude plugin validate . --strict
  printf '\n'
  run claude plugin details pink-lady-apple
else
  warn "no claude CLI on this machine — showing the tree instead"
  run find skills -maxdepth 1 -mindepth 1 -type d
fi

printf '\n   %sand it is not only prose — the TestFlight skill ships a working ASC client:%s\n\n' "$D" "$R"

if [ -n "$HAVE_UV" ]; then
  runsh "cd $(dirname "$ASC") && uv run --quiet --with authlib --with httpx python3 $(basename "$ASC") --help 2>/dev/null | sed -n '/^positional/,/^options/p' | sed '\$d'"
  SUBCMDS="$(grep -c 'sub.add_parser(' "$ASC" 2>/dev/null | tr -d ' ')"
  printf '\n   %s%s App Store Connect subcommands, %s lines, credentials as placeholders:%s\n' "$B" "$SUBCMDS" "$(wc -l < "$ASC" | tr -d ' ')" "$R"
else
  warn "no uv — listing the subcommands from source instead"
fi

printf '\n'
run grep -n '^ISSUER_ID\|^KEY_ID' "$ASC"

printf '\n   %sinstall path for anyone else:%s\n' "$D" "$R"
printf '     %sclaude plugin marketplace add synodic-studio/pink-lady-apple%s\n' "$B" "$R"
printf '     %sclaude plugin install pink-lady-apple@pink-lady-apple%s\n' "$B" "$R"
printf '     %shttps://github.com/synodic-studio/pink-lady-apple%s\n\n' "$C" "$R"

cue "Say: the afternoons are already spent. This is what stops them being spent twice." \
    "Two commands and another engineer has all of it — including the traps."

advance "press to finish"

printf '\n%s%s   done.%s  clear the fetched response before the next run:  %s./scripts/demo.sh --cleanup%s\n\n' "$G" "$B" "$R" "$B" "$R"
