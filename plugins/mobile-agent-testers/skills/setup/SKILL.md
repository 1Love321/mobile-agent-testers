---
name: setup
description: Set up and run parallel AI testers for an iOS/Android app (Flutter, React Native, Expo, native, KMP, Capacitor, MAUI) - one headless Claude Code agent per iOS Simulator or Android emulator, each with a persona and a different device, on GitHub Actions, with encrypted reports.
---

# Set up mobile agent testers

Goal: the user gets a testers repo where one workflow builds their app, boots
one phone per persona (Android emulators on Linux runners, iOS Simulators on
macOS runners), lets a Claude Code agent use the app like a new user, and
returns encrypted reports with screenshots, merged into one SUMMARY.md.

Template and full docs: https://github.com/pierridotite/mobile-agent-testers

## 1. Tell the user the rules before anything else

- Runners are free only for **public** repos (about 20 jobs at once, 5 on
  macOS, on the Free plan; check GitHub's current docs). In a private repo,
  macOS minutes count 10x.
- GitHub's terms reserve hosted runners for the project of the repository.
  Fine: open-source app, or testers inside the app's own repo. Grey zone:
  pulling a closed-source app into a public repo only to get free Macs. Say
  so, and offer the private-repo or self-hosted alternative.
- A Claude Pro/Max subscription token can be used up quickly: 20 agents at
  once used a 5-hour window in about 15 minutes. Recommend batches of 6-10.
- Logs of a public repo are public. The template encrypts build logs, apps,
  screenshots and reports. Never add a step that prints them.

## 2. Create the testers repo

Ask where the testers should live, then:

```bash
gh repo create <name> --public --template pierridotite/mobile-agent-testers --clone
cd <name> && ./setup.sh
```

`setup.sh` creates the results key pair (private half in
`~/.mobile-agent-testers/`), sets `ARTIFACT_PASSPHRASE`, asks for
`CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY`,
and pushes the public key. Never ask the user to paste a token into the chat:
they type it into setup.sh.

Offer the demo first (`gh workflow run agent-testers.yml`): it tests the
bundled Tiny Todo app, which has 11 deliberate bugs listed in
`demo-app/BUGS.md`, so the user can see what the agents catch.

## 3. Point it at the user's app

Read the app to fill the workflow inputs (pass them with `-f` or change the
defaults in `.github/workflows/agent-testers.yml`):

| Input | How to find it |
|---|---|
| `source_repo` | owner/name of the app repo (empty if the app is in the testers repo) |
| `ref` | branch or full SHA to test |
| `app_dir` | folder with package.json (`.` for most apps) |
| `app_id` | `expo.android.package` / `expo.ios.bundleIdentifier` in app.json, or `applicationId` in android/app/build.gradle and `PRODUCT_BUNDLE_IDENTIFIER` in the Xcode project |

If the app repo is private, have the user create a fine-grained token with
Contents: read on that one repo and store it with
`gh secret set SOURCE_REPO_TOKEN`.

The build detects the framework (`scripts/build/detect.sh`): Flutter, Expo,
React Native, Capacitor/Ionic, Kotlin Multiplatform, native Kotlin/Java and
Swift/Objective-C, .NET MAUI (beta). Force it with `-f framework=<name>` if
detection is wrong. For anything else, or to test an app that is already
built, pass `android_build` + `apk_path` and `ios_build` + `ios_app_path`
(a build command or a download; paths relative to `app_dir`). For a native
iOS project with several schemes, set the repo variable: `gh variable set IOS_SCHEME --body <scheme>`.

## 4. Personas and brief

Rewrite `personas.json` for the app's real audience. Each persona has a
profile, a goal, a locale, a GPS position and a device. Cover what breaks
layouts: a small phone, an old OS (Android API 30), a tablet, font scale 1.3
or an accessibility text size, dark mode, another language, someone who
refuses permissions.

Adapt `AGENT_BRIEF.md` to the app: what to check, how to sign up (test
accounts, `success+<id>@simulator.amazonses.com` for e-mails), what is out of
scope. Keep the rules "screenshot after every action" and "write
findings.json". For a quick targeted check, write a second, short brief and
pass `-f brief=<file>`.

Add the app's analytics and ad hosts to `block_hosts` so test runs never reach
production stats.

## 5. Run, collect, triage

```bash
gh workflow run agent-testers.yml -f android_personas=a,b -f ios_personas=c,d -f app_id=com.example.app
bash scripts/collect.sh <run id>      # downloads + decrypts into runs/<id>/
```

Read `runs/<id>/SUMMARY.md`, then open the screenshots of each important
issue before you trust it: agents sometimes misread a screen. Check that no
agent stopped on a usage limit (collect.sh warns). Turn confirmed issues into
fixes or tickets, most severe first, and say which personas hit each one.
