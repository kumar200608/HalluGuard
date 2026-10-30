#!/usr/bin/env bash
# build_plugins.sh — Package all four plugin formats as distributable zips
# Usage: ./scripts/build_plugins.sh [--url https://your-deployment-url.com]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
MANIFESTS="$ROOT/plugin_manifests"
DIST="$ROOT/dist"
URL="${2:-https://your-deployment-url.com}"

mkdir -p "$DIST"

echo "🔧 Building HalluGuard plugin packages..."
echo "   API URL: $URL"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Patch the deployment URL into all manifests
# ─────────────────────────────────────────────────────────────────────────────
patch_url() {
  local file="$1"
  sed -i.bak "s|https://your-deployment-url.com|$URL|g" "$file"
  rm -f "${file}.bak"
}

patch_url "$MANIFESTS/chatgpt/ai-plugin.json"
patch_url "$MANIFESTS/chatgpt/openapi.yaml"
patch_url "$MANIFESTS/claude/.claude-plugin/plugin.json"
patch_url "$MANIFESTS/gemini/extension.json"

# ─────────────────────────────────────────────────────────────────────────────
# 1. ChatGPT Actions zip
#    Contains: ai-plugin.json + openapi.yaml
# ─────────────────────────────────────────────────────────────────────────────
echo "📦 Building ChatGPT Actions package..."
cd "$MANIFESTS/chatgpt"
zip -j "$DIST/halluguard-chatgpt-actions.zip" ai-plugin.json openapi.yaml
echo "   ✅ $DIST/halluguard-chatgpt-actions.zip"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Claude plugin zip
#    Format A: .claude-plugin/plugin.json (manifest format)
#    Format B: top-level SKILL.md (skill format — for Claude.ai upload)
# ─────────────────────────────────────────────────────────────────────────────
echo "📦 Building Claude plugin packages..."

# Format A — manifest zip
cd "$MANIFESTS/claude"
zip -r "$DIST/halluguard-claude-manifest.zip" .claude-plugin/
echo "   ✅ $DIST/halluguard-claude-manifest.zip"

# Format B — SKILL.md zip (Claude.ai Upload a plugin)
cd "$MANIFESTS/claude"
zip -j "$DIST/halluguard-claude-skill.zip" SKILL.md
echo "   ✅ $DIST/halluguard-claude-skill.zip"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Gemini Extension zip
#    Contains: extension.json + openapi.yaml (copied from chatgpt/)
# ─────────────────────────────────────────────────────────────────────────────
echo "📦 Building Gemini Extension package..."
cp "$MANIFESTS/chatgpt/openapi.yaml" "$MANIFESTS/gemini/openapi.yaml"
cd "$MANIFESTS/gemini"
zip -j "$DIST/halluguard-gemini-extension.zip" extension.json openapi.yaml
rm -f openapi.yaml
echo "   ✅ $DIST/halluguard-gemini-extension.zip"

# ─────────────────────────────────────────────────────────────────────────────
# 4. MCP server zip
#    Contains: server.js + package.json
# ─────────────────────────────────────────────────────────────────────────────
echo "📦 Building MCP server package..."
cd "$MANIFESTS/mcp"
zip -j "$DIST/halluguard-mcp-server.zip" server.js package.json
echo "   ✅ $DIST/halluguard-mcp-server.zip"

# ─────────────────────────────────────────────────────────────────────────────
# 5. Universal zip (all formats + docs)
# ─────────────────────────────────────────────────────────────────────────────
echo "📦 Building universal all-platforms zip..."
cd "$MANIFESTS"
zip -r "$DIST/halluguard-universal.zip" \
  chatgpt/ \
  claude/ \
  gemini/ \
  mcp/ \
  CLIENT_CONFIGS.md
echo "   ✅ $DIST/halluguard-universal.zip"

echo ""
echo "✅ All packages built in $DIST/"
echo ""
echo "Distribution:"
ls -lh "$DIST/"*.zip
echo ""
echo "Next steps:"
echo "  ChatGPT : Import $DIST/halluguard-chatgpt-actions.zip via GPT Builder → Actions"
echo "  Claude  : Upload $DIST/halluguard-claude-skill.zip via Settings → Plugins"
echo "  Gemini  : Upload $DIST/halluguard-gemini-extension.zip via AI Studio → Extensions"
echo "  MCP     : Unzip $DIST/halluguard-mcp-server.zip, npm install, add to client config"
