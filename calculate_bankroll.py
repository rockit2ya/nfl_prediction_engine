#!/usr/bin/env python3
"""
calculate_bankroll.py — Simple NFL bankroll calculator.

Reads bankroll.json and shows current status.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    path = os.path.join(BASE_DIR, 'bankroll.json')
    if not os.path.exists(path):
        print("  No bankroll.json found. Configure via: python post_mortem.py → [5] Bankroll Tracker")
        return
    with open(path) as f:
        data = json.load(f)
    print(f"  Starting Bankroll: ${data['starting_bankroll']:,.2f}")
    print(f"  Unit Size:         ${data['unit_size']:,.2f}")
    print(f"  Edge Cap:          {data.get('edge_cap', 10)} pts")
    print(f"  Created:           {data.get('created', 'unknown')}")

if __name__ == '__main__':
    main()
