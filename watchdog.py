#!/usr/bin/env python3
"""Healer watchdog — runs every 5 minutes via systemd timer, calls healer.py."""
import subprocess, sys, os
from datetime import datetime

LOG_DIR = "/home/sin/zen/ai-healer/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Run the main healer
result = subprocess.run([sys.executable, "/home/sin/zen/ai-healer/healer.py"],
                        capture_output=True, text=True, timeout=120)

# Also append to a rolling daily log
log_path = os.path.join(LOG_DIR, f"heal-{datetime.now().strftime('%Y%m%d')}.log")
with open(log_path, "a") as f:
    f.write(f"[{datetime.now().isoformat()}] exit={result.returncode}\n")
    f.write(result.stdout)
    if result.stderr:
        f.write(f"STDERR: {result.stderr}\n")

sys.exit(result.returncode)