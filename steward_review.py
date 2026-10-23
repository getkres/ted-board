#!/usr/bin/env python3
"""Print ambiguous inbox cards and mockup batches for Ted's judgment pass."""
import argparse
import sys
import time
import inbox_steward as steward


def main(argv=None, now=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    cards, mockups, pins = steward.snapshot()
    rows = steward.plan(cards, mockups, pins, time.time() if now is None else now)['review']
    print('id | project | title | age | last message | suggested move')
    for row in rows:
        print(' | '.join([row['id'], row['project'], steward.clean(row['title'], 64),
                          str(round(row['age_hours']/24, 1))+'d', steward.clean(row['last_message'], 100),
                          row['suggested_move']+': '+row['reason']]))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('steward review failed, check private inputs and connectivity', file=sys.stderr)
        sys.exit(1)
