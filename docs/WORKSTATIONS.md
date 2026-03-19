# fusionAIze Gate Workstations

fusionAIze Gate works best when the development checkout and the runtime install are kept separate.

Recommended shape:

- one checkout for active development
- one separate runtime install for OpenClaw, opencode, CLI tools, and local workflows
- one config directory outside the repo
- one writable state directory outside the repo

This keeps local usage stable while `main` and feature branches continue to move.

## General layout

Use one of these patterns:

### User-local runtime

Good for a single workstation user:

- checkout: `~/services/faigate`
- config: `~/.config/faigate`
- state: `~/.local/state/faigate`

### System-style runtime

Good for a more shared or host-like install:

- checkout: `/opt/faigate`
- config: `/etc/faigate`
- state: `/var/lib/faigate`

## Linux

Recommended baseline:

- runtime checkout under `~/services/faigate` or `/opt/faigate`
- config under `~/.config/faigate` or `/etc/faigate`
- DB under `~/.local/state/faigate/faigate.db` or `/var/lib/faigate/faigate.db`
- service manager: `systemd`

Typical start command:

```bash
FAIGATE_DB_PATH="$HOME/.local/state/faigate/faigate.db" \
python -m faigate --config "$HOME/.config/faigate/config.yaml"
```

For long-running user sessions, prefer a `systemd --user` unit or a normal system service.

## macOS

Recommended baseline:

- runtime checkout: `~/services/faigate`
- config: `~/Library/Application Support/faigate`
- state: `~/Library/Application Support/faigate/faigate.db`
- service manager: `launchd` via `~/Library/LaunchAgents`

The repo now ships a starter plist:

- [examples/com.fusionaize.faigate.plist](./examples/com.fusionaize.faigate.plist)
- [`Formula/faigate.rb`](../Formula/faigate.rb)

The standard helper scripts now understand macOS directly:

- `./scripts/faigate-install`
- `./scripts/faigate-start`
- `./scripts/faigate-stop`
- `./scripts/faigate-restart`
- `./scripts/faigate-status`
- `./scripts/faigate-logs`

Suggested local layout:

```text
~/services/faigate
~/Library/Application Support/faigate/config.yaml
~/Library/Application Support/faigate/faigate.env
~/Library/Application Support/faigate/faigate.db
```

Install flow:

```bash
mkdir -p "$HOME/Library/Application Support/faigate"
cp docs/examples/com.fusionaize.faigate.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.fusionaize.faigate.plist"
launchctl kickstart -k "gui/$(id -u)/com.fusionaize.faigate"
```

Use `launchctl print "gui/$(id -u)/com.fusionaize.faigate"` to inspect the loaded job.

### Homebrew on macOS

If you prefer a packaged macOS path, fusionAIze Gate now ships a project-owned Homebrew formula:

- [`Formula/faigate.rb`](../Formula/faigate.rb)

Typical flow:

```bash
brew tap fusionAIze/faigate https://github.com/fusionAIze/faigate
brew install fusionAIze/faigate/faigate
# or, after the tap is present and the name stays unique:
brew install faigate
$EDITOR "$(brew --prefix)/etc/faigate/config.yaml"
$EDITOR "$(brew --prefix)/etc/faigate/faigate.env"
brew services start fusionAIze/faigate/faigate
```

Useful paths for the formula-driven install:

- config: `$(brew --prefix)/etc/faigate/config.yaml`
- env file: `$(brew --prefix)/etc/faigate/faigate.env`
- DB: `$(brew --prefix)/var/lib/faigate/faigate.db`
- logs: `$(brew --prefix)/var/log/faigate/`

The formula is intentionally project-owned rather than targeted at `homebrew/core`. That keeps the Python-service packaging flexible and lets `brew services` manage the local `launchd` path cleanly.

The fully qualified install path is the safest first-run example. Once the tap is added, `brew install faigate` also resolves cleanly as long as no conflicting formula name is introduced by another tap.

If you are testing from a shell that already has an active Python virtualenv, confirm that the Brew-installed binary is the one being called:

```bash
which -a faigate
/opt/homebrew/bin/faigate --version
/opt/homebrew/bin/faigate-menu --help
/opt/homebrew/bin/faigate-client-integrations --matrix
```

The virtualenv binary can appear first on `PATH`, which makes it look like the Homebrew install is missing features when you are actually calling the wrong executable.

## Windows

Recommended baseline:

- runtime checkout: `%USERPROFILE%\\services\\faigate`
- config: `%APPDATA%\\faigate`
- state: `%LOCALAPPDATA%\\faigate\\faigate.db`
- process manager: Task Scheduler at logon, or a later service wrapper if needed

Suggested local layout:

```text
%USERPROFILE%\services\faigate
%APPDATA%\faigate\config.yaml
%APPDATA%\faigate\faigate.env
%LOCALAPPDATA%\faigate\faigate.db
```

Use the venv Python directly instead of relying on shell activation:

```powershell
$env:FAIGATE_DB_PATH="$env:LOCALAPPDATA\faigate\faigate.db"
& "$env:USERPROFILE\services\faigate\.venv\Scripts\python.exe" -m faigate --config "$env:APPDATA\faigate\config.yaml"
```

Task Scheduler is the recommended `v1.2.0`-targeted path. A native Windows service wrapper can come later if it proves necessary.

The repo ships starter files for this path:

- [examples/faigate-start.ps1](./examples/faigate-start.ps1)
- [examples/faigate-task-scheduler.xml](./examples/faigate-task-scheduler.xml)

Suggested install flow:

```powershell
New-Item -ItemType Directory -Force -Path "$env:APPDATA\faigate" | Out-Null
Copy-Item ".\docs\examples\faigate-start.ps1" "$env:APPDATA\faigate\faigate-start.ps1"
schtasks /Create /TN faigate /XML ".\docs\examples\faigate-task-scheduler.xml" /F
```

If you want to avoid XML import, create one logon task that runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:APPDATA\faigate\faigate-start.ps1"
```

## Config and state placement

Keep these out of the repo checkout:

- `.env`
- `config.yaml` for the live runtime
- the SQLite DB
- generated logs

This keeps upgrades, worktrees, and branch switches from colliding with the running gateway.

## Runtime vs development checkout

Do not run day-to-day client traffic from the same checkout you are actively editing.

Preferred workflow:

1. develop in your main repo or Codex worktree
2. run fusionAIze Gate for clients from a stable runtime checkout
3. upgrade that runtime checkout intentionally, ideally from tags or reviewed `main`

## Suggested upgrade path

For workstation installs:

1. keep the runtime checkout pinned to a release tag or known-good `main` commit
2. store config and DB outside the checkout
3. stop the service
4. update the checkout
5. run one manual health check
6. start the service again

This keeps local OpenClaw, opencode, and CLI tooling stable while development continues elsewhere.
