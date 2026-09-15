# Zen Healer

Autonomous self-healing daemon for Garuda/linux-zen systems.

## What it does

Full-stack monitoring with auto-remediation of safe fixes only:

- **Disk**: detects >85% usage, creates snapper snapshot, runs `pacman -Sc` + journal vacuum
- **Memory**: alerts if >90% usage (no auto-fix — requires human review)
- **Services**: restarts failed systemd services (tor, dnscrypt-proxy, NetworkManager, bluetooth, cronie)
- **Processes**: monitors CCMini.exe, steam, waydroid, kdeinit5, plasmashell
- **Waydroid**: checks session status
- **Steam/Once Human**: scans ccmini logs for ERROR/crash/code 126
- **Auditd**: verifies rules are loaded

## Action policy

- **Safe auto-fixes**: service restarts, pacman cache clean, journal vacuum, snapper snapshots before changes
- **Logged for review**: process down, waydroid down, steam errors, memory pressure, auditd rules
- **Never auto-applies**: network config changes, config file edits, package installs/removes

## Install

```bash
sudo cp zen-healer.service zen-healer.timer zen-healer-watchdog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zen-healer.timer
sudo systemctl start zen-healer.timer
```

## Logs

JSON logs in `logs/` directory, one file per pass:
```
logs/heal-YYYYMMDD-HHMMSS.json
```

## Repo

https://github.com/intricos777-dot/zen-healer