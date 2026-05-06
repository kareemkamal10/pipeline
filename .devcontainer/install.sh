#!/bin/bash
# install.sh — يُشغَّل تلقائياً عند إنشاء Codespace
# يثبت gcloud CLI وكل المكتبات المطلوبة

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()       { echo -e "${GREEN}  ✔ $1${NC}"; }
log()      { echo -e "${GREEN}▶ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  تثبيت بيئة History Lab Pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. gcloud CLI ─────────────────────────────────────────
log "تثبيت gcloud CLI..."
curl -sSL https://sdk.cloud.google.com > /tmp/install_gcloud.sh
bash /tmp/install_gcloud.sh --disable-prompts --install-dir="${HOME}/google-cloud-sdk"
export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
echo 'export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"' >> ~/.bashrc
echo 'export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"' >> ~/.zshrc 2>/dev/null || true
ok "gcloud $(gcloud version --format='value(Google Cloud SDK)' 2>/dev/null | head -1)"

# ── 2. Python packages ────────────────────────────────────
log "تثبيت Python packages..."
pip install --quiet \
    pyyaml \
    google-cloud-storage
ok "pyyaml + google-cloud-storage"

# ── 3. إعداد مجلد secrets ─────────────────────────────────
log "إعداد مجلد secrets..."
mkdir -p secrets
if [ ! -f "secrets/.gitkeep" ]; then
    touch secrets/.gitkeep
fi
ok "مجلد secrets/ جاهز"

# ── 4. صلاحيات الـ scripts ────────────────────────────────
log "إعداد صلاحيات الـ scripts..."
chmod +x vertex/setup.sh
chmod +x vertex/run.sh
chmod +x vertex/cleanup.sh
chmod +x vertex/entrypoint.sh
ok "صلاحيات الـ scripts مضبوطة"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✔ البيئة جاهزة!${NC}"
echo ""
echo "  الخطوات:"
echo "  1. ارفع secrets/CREDENTIALS.json"
echo "  2. عدّل config.yaml (session_name)"
echo "  3. عدّل playLinks.csv (الروابط)"
echo "  4. bash vertex/setup.sh"
echo "  5. bash vertex/run.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
