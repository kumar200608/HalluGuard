# HalluGuard MCP Client Configuration
#
# Paste the relevant block into your agent's MCP configuration file.
# Replace "https://your-deployment-url.com" with your actual deployed URL,
# or use "http://localhost:8000" when running locally via docker-compose.

# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE DESKTOP
# File: ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
#       %APPDATA%\Claude\claude_desktop_config.json (Windows)
# ─────────────────────────────────────────────────────────────────────────────
#
# {
#   "mcpServers": {
#     "halluguard": {
#       "command": "node",
#       "args": ["/absolute/path/to/hallu_guard/plugin_manifests/mcp/server.js"],
#       "env": {
#         "HALLUGUARD_API_URL": "http://localhost:8000"
#       }
#     }
#   }
# }
#
# OR using npx (after publishing to npm):
# {
#   "mcpServers": {
#     "halluguard": {
#       "command": "npx",
#       "args": ["-y", "halluguard-mcp"],
#       "env": {
#         "HALLUGUARD_API_URL": "http://localhost:8000"
#       }
#     }
#   }
# }

# ─────────────────────────────────────────────────────────────────────────────
# CURSOR
# File: ~/.cursor/mcp.json  (or via Settings → MCP Servers → Add)
# ─────────────────────────────────────────────────────────────────────────────
#
# {
#   "mcpServers": {
#     "halluguard": {
#       "command": "node",
#       "args": ["/absolute/path/to/hallu_guard/plugin_manifests/mcp/server.js"],
#       "env": {
#         "HALLUGUARD_API_URL": "http://localhost:8000"
#       }
#     }
#   }
# }

# ─────────────────────────────────────────────────────────────────────────────
# CONTINUE.DEV
# File: ~/.continue/config.json
# ─────────────────────────────────────────────────────────────────────────────
#
# {
#   "experimental": {
#     "modelContextProtocolServers": [
#       {
#         "transport": {
#           "type": "stdio",
#           "command": "node",
#           "args": ["/absolute/path/to/hallu_guard/plugin_manifests/mcp/server.js"],
#           "env": {
#             "HALLUGUARD_API_URL": "http://localhost:8000"
#           }
#         }
#       }
#     ]
#   }
# }

# ─────────────────────────────────────────────────────────────────────────────
# CHATGPT ACTIONS (GPT Builder)
# ─────────────────────────────────────────────────────────────────────────────
# 1. Go to: https://chat.openai.com/gpts/editor
# 2. Create or edit a GPT
# 3. Click "Add Actions"
# 4. Import from URL: https://your-deployment-url.com/openapi.json
#    (or paste the contents of plugin_manifests/chatgpt/openapi.yaml)
# 5. Authentication: None (or Bearer token if you enable API_SECRET_KEY)
#
# The GPT will then have access to:
#   - verify_answer      ← use before every factual response
#   - extract_claims     ← decompose text into verifiable claims
#   - validate_source    ← check if a URL citation is real

# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE (API / Projects)
# ─────────────────────────────────────────────────────────────────────────────
# Option A — Claude.ai Plugin Upload (zip):
#   Use the pre-built halissination.zip (top-level SKILL.md)
#   or the plugin_manifests/claude/ directory:
#     cd plugin_manifests/claude && zip -r halluguard-claude.zip .
#
# Option B — Claude API tool_use:
#   Include the tool definition from plugin_manifests/claude/.claude-plugin/plugin.json
#   in your tools array when calling the Anthropic API.
#
# Option C — MCP (Claude Desktop):
#   Use the MCP config above.

# ─────────────────────────────────────────────────────────────────────────────
# GEMINI (Google AI Studio / Vertex AI Extensions)
# ─────────────────────────────────────────────────────────────────────────────
# 1. Go to: https://aistudio.google.com  →  Extensions
# 2. Register a new Extension
# 3. Upload plugin_manifests/gemini/extension.json
#    (update the URL fields to your deployed API)
# 4. Or use the OpenAPI spec at: https://your-deployment-url.com/openapi.json
#    with Vertex AI Extensions (gcloud ai extensions import)

# ─────────────────────────────────────────────────────────────────────────────
# OPENAI ASSISTANTS API (Programmatic)
# ─────────────────────────────────────────────────────────────────────────────
#
# assistant = client.beta.assistants.create(
#     name="HalluGuard Agent",
#     tools=[{"type": "function", "function": {
#         "name": "verify_answer",
#         "description": "Verify answer for hallucinations",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "query": {"type": "string"},
#                 "answer": {"type": "string"},
#                 "mode": {"type": "string", "enum": ["fast","standard","strict","critical"]}
#             },
#             "required": ["query", "answer"]
#         }
#     }}],
#     instructions="Before answering any factual question, call verify_answer with your draft."
# )
