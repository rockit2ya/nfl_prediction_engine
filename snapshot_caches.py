#!/usr/bin/env python3
"""
snapshot_caches.py — Weekly Cache Archival

Archives all current cache files into a timestamped snapshot directory.
Useful for preserving weekly state for backtest replay and audit trails.

Usage:
    python snapshot_caches.py
"""

import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(BASE_DIR, 'snapshots')

CACHE_FILES = [
    'nfl_stats_cache.json',
    'nfl_stats_recent_cache.json',
    'nfl_injuries.csv',
    'nfl_schedule_cache.json',
    'nfl_weather_cache.json',
    'nfl_odds_cache.json',
    'nfl_sos_cache.json',
    'model_config.json',
    'bankroll.json',
]


def snapshot():
    """Create a timestamped snapshot of all cache files."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    snap_dir = os.path.join(SNAPSHOT_DIR, timestamp)
    os.makedirs(snap_dir, exist_ok=True)

    copied = 0
    for fname in CACHE_FILES:
        src = os.path.join(BASE_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(snap_dir, fname))
            copied += 1

    # Also copy any fair_line_log and bet_tracker CSVs
    for pattern_prefix in ['fair_line_log_', 'bet_tracker_']:
        for f in os.listdir(BASE_DIR):
            if f.startswith(pattern_prefix) and f.endswith('.csv'):
                shutil.copy2(os.path.join(BASE_DIR, f), os.path.join(snap_dir, f))
                copied += 1

    print(f"  ✅ Snapshot saved: {snap_dir}")
    print(f"     {copied} files archived.")
    return snap_dir


def list_snapshots():
    """List existing snapshots."""
    if not os.path.exists(SNAPSHOT_DIR):
        print("  No snapshots yet.")
        return
    snaps = sorted(os.listdir(SNAPSHOT_DIR), reverse=True)
    if not snaps:
        print("  No snapshots yet.")
        return
    print(f"\n  Existing snapshots:")
    for s in snaps[:10]:
        snap_path = os.path.join(SNAPSHOT_DIR, s)
        count = len(os.listdir(snap_path))
        print(f"    {s}  ({count} files)")
    if len(snaps) > 10:
        print(f"    ... and {len(snaps) - 10} more")


def main():
    print("\n  🏈 NFL Prediction Engine — Cache Snapshot Tool\n")
    print("  [1] Create new snapshot")
    print("  [2] List existing snapshots")
    print("  [Q] Quit\n")

    choice = input("  Select: ").strip().upper()
    if choice == '1':
        snapshot()
    elif choice == '2':
        list_snapshots()
    elif choice != 'Q':
        print("  ❌ Invalid choice.")


if __name__ == '__main__':
    main()
