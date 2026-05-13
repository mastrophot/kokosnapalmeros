#!/bin/bash
# Локальний скрипт синхронізації Instagram → GitHub Pages
# Запускається через crontab або launchd на маці
#
# Встановлення в crontab (кожні 12 годин):
#   crontab -e
#   0 */12 * * * cd /Users/maximbutrik/.gemini/antigravity/scratch/kokosnapalmeros_repo && bash sync-and-push.sh >> sync.log 2>&1
#
# Або через launchd (див. com.kokosnapalmeros.sync.plist)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=== $(date '+%Y-%m-%d %H:%M:%S') | Instagram Sync ==="

# 1. Синхронізуємо фото
python3 sync-instagram.py --limit 50

# 2. Оновлюємо HTML галерею
node update-gallery.js

# 3. Комітимо та пушимо
git add images/ gallery-data.json gallery-items.js index.html
if git diff --staged --quiet; then
    echo "✅ Нових фото немає"
else
    git commit -m "🤖 Auto-sync: Update gallery from Instagram"
    git push origin main
    echo "✅ Зміни запушені"
fi

echo "=== Done ==="
