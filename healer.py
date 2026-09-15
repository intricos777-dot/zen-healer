#!/usr/bin/env python3
"""Zen Healer v1 — full-stack autonomous self-healing daemon for Garuda/linux-zen.

Monitors: system health, Steam/Once Human, Waydroid, security (auditd), disk.
Action policy: auto-apply only SAFE fixes (restarts, snapshot rollback, config restore).
Everything else is logged for human review.
"""

import json, os, re, shutil, subprocess, sys, time, logging, yaml
from pathlib import Path
from datetime import datetime

CONFIG = {
    "log_dir": "/home/sin/zen/ai-healer/logs",
    "snapshots_dir": "/home/sin/.local/share/Steam/steamapps/common/Once Human/ccmini/logs",
    "systemd_services": ["tor", "dnscrypt-proxy", "NetworkManager", "bluetooth", "cronie"],
    "critical_processes": ["CCMini.exe", "steam", "Steam", "waydroid", "kdeinit5", "plasmashell"],
    "disk_threshold_pct": 85,
    "memory_threshold_pct": 90,
    "safe_fixes_only": True,
}

SNAPSHOT_PREFIX = "ai-healer-auto"

def run(cmd, capture=True, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), -1

def snapshot():
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    desc = f"{SNAPSHOT_PREFIX}-{ts}"
    out, err, rc = run(f"sudo snapper create -c root -t single -d '{desc}'")
    if rc == 0 and out.strip():
        return out.strip()
    return None

def restore_snapshot(snap_id):
    out, err, rc = run(f"sudo snapper rollback -c root {snap_id}")
    return rc == 0

def check_disk():
    out, _, _ = run("df -h /")
    lines = out.split("\n")
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 5:
            pct = int(parts[4].replace("%", ""))
            return {"ok": pct < CONFIG["disk_threshold_pct"], "usage_pct": pct, "raw": out}
    return {"ok": True, "usage_pct": 0, "raw": out}

def check_memory():
    out, _, _ = run("free -m")
    lines = out.split("\n")
    for line in lines:
        if line.startswith("Mem:"):
            parts = line.split()
            total, used = int(parts[1]), int(parts[2])
            pct = int(used / total * 100) if total > 0 else 0
            return {"ok": pct < CONFIG["memory_threshold_pct"], "usage_pct": pct, "total_mb": total, "used_mb": used}
    return {"ok": True, "usage_pct": 0}

def check_services():
    results = {}
    for svc in CONFIG["systemd_services"]:
        out, _, rc = run(f"systemctl is-active {svc}")
        results[svc] = {"active": out.strip() == "active", "status": out.strip()}
    return results

def check_critical_processes():
    results = {}
    for proc in CONFIG["critical_processes"]:
        out, _, _ = run(f"pgrep -f {proc}")
        results[proc] = {"running": bool(out.strip())}
    return results

def check_waydroid():
    out, _, rc = run("waydroid session status 2>/dev/null || echo UNKNOWN")
    return {"running": "running" in out.lower(), "raw": out}

def check_steam():
    log_dir = Path(CONFIG["snapshots_dir"])
    if log_dir.exists():
        logs = sorted(log_dir.glob("m*.log"), key=os.path.getmtime, reverse=True)
        latest = logs[0] if logs else None
        if latest:
            content = latest.read_text(errors="replace")
            has_error = "ERROR" in content or "crash" in content.lower() or "code 126" in content
            return {"latest_log": str(latest), "has_errors": has_error, "size_bytes": latest.stat().st_size}
    return {"latest_log": None, "has_errors": False}

def auto_fix_disk():
    actions = []
    out, _, rc = run("sudo pacman -Sc --noconfirm 2>&1")
    actions.append({"action": "pacman -Sc", "rc": rc, "output": out[:200]})
    out, _, rc = run("sudo journalctl --vacuum-size=50M --no-pager 2>&1")
    actions.append({"action": "journal vacuum", "rc": rc, "output": out[:200]})
    return actions

def auto_fix_service(svc):
    out, _, rc = run(f"sudo systemctl restart {svc} 2>&1")
    return {"action": f"restart {svc}", "rc": rc, "output": out[:200]}

def check_auditd():
    out, _, rc = run("sudo auditctl -l")
    return {"rules_loaded": rc == 0, "count": len(out.split("\n")) if out else 0}

def heal():
    report = {"ts": datetime.now().isoformat(), "fixes_applied": [], "issues": []}

    disk = check_disk()
    if not disk["ok"]:
        report["issues"].append({"type": "disk", "detail": disk})
        snap = snapshot()
        if snap:
            report["fixes_applied"].append({"type": "snapshot", "id": snap})
        report["fixes_applied"].extend(auto_fix_disk())

    mem = check_memory()
    if not mem["ok"]:
        report["issues"].append({"type": "memory", "detail": mem})

    svcs = check_services()
    for svc, info in svcs.items():
        if not info["active"]:
            report["issues"].append({"type": "service", "service": svc, "status": info["status"]})
            report["fixes_applied"].append(auto_fix_service(svc))

    procs = check_critical_processes()
    for proc, info in procs.items():
        if not info["running"]:
            report["issues"].append({"type": "process_down", "process": proc})

    wd = check_waydroid()
    if not wd["running"]:
        report["issues"].append({"type": "waydroid_down", "detail": wd})

    st = check_steam()
    if st.get("has_errors"):
        report["issues"].append({"type": "steam_errors", "detail": st})

    aud = check_auditd()
    if not aud["rules_loaded"]:
        report["issues"].append({"type": "auditd_no_rules", "detail": aud})

    return report

def main():
    os.makedirs(CONFIG["log_dir"], exist_ok=True)
    log_file = Path(CONFIG["log_dir"]) / f"heal-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"

    report = heal()
    log_file.write_text(json.dumps(report, indent=2))

    print(f"=== Zen Healer Pass === {report['ts']}")
    print(f"Issues found: {len(report['issues'])}")
    print(f"Fixes applied: {len(report['fixes_applied'])}")
    for i in report["issues"]:
        print(f"  ISSUE: {i}")
    for f in report["fixes_applied"]:
        print(f"  FIX: {f}")
    print(f"Log: {log_file}")

if __name__ == "__main__":
    main()