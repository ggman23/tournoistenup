#!/bin/bash
# Setup cron for 1-2 runs per day (7h and 19h)
# Run this script once to install the cron job.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(which python3)
LOG="$SCRIPT_DIR/data/scraper.log"

# Create log directory
mkdir -p "$SCRIPT_DIR/data"

# Cron entry: run at 7:00 and 19:00 every day
CRON_LINE_1="0 7 * * * cd $SCRIPT_DIR && $PYTHON main.py >> $LOG 2>&1"
CRON_LINE_2="0 19 * * * cd $SCRIPT_DIR && $PYTHON main.py >> $LOG 2>&1"

# Add to crontab if not already present
(crontab -l 2>/dev/null | grep -v "tournoistenup"; \
 echo "$CRON_LINE_1"; \
 echo "$CRON_LINE_2") | crontab -

echo "Cron jobs installed:"
echo "  $CRON_LINE_1"
echo "  $CRON_LINE_2"
echo ""
echo "To check: crontab -l"
echo "To remove: crontab -e  (then delete the two lines)"
