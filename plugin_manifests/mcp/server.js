#!/usr/bin/env node
/**
 * HalluGuard MCP Server
 *
 * Model Context Protocol server that exposes HalluGuard verification tools
 * to ANY MCP-compatible agent host:
 *   - Claude Desktop
 *   - Cursor
 *   - GitHub Copilot (via MCP bridge)
 *   - Continue.dev
 *   - Cline / Roo
 *   - Any OpenAI-compatible client with MCP support
 *
 * Install:  npm install
 * Run:      node server.js
 * Config:   Set HALLUGUARD_API_URL env var to your deployed API base URL.
 *           Defaults to http://localhost:8000 for local development.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

const API_BASE = process.env.HALLUGUARD_API_URL || "http://localhost:8000";

// ─────────────────────────────────────────────────────────────────────────────
// Tool definitions
// ─────────────────────────────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "verify_answer",
    description:
      "Verify an AI-generated answer for hallucinations before presenting it to the user. " +
      "Submit the user's original query and your draft answer. " +
      "The plugin extracts every factual claim, retrieves evidence, checks entailment, " +
      "validates calculations deterministically, detects contradictions and fake citations, " +
      "checks temporal freshness, and returns a gate decision. " +
      "ALWAYS use the returned 'answer' field as your final response. " +
      "NEVER present UNSUPPORTED claims as facts. " +
      "NEVER use citations not returned by this tool.",
    inputSchema: {
      type: "object",
      required: ["query", "answer"],
      properties: {
        query: {
          type: "string",
          description: "The original user question",
        },
        answer: {
          type: "string",
          description: "Your draft answer to verify before sending to the user",
        },
        context: {
          type: "string",
          description: "Optional additional context",
        },
        mode: {
          type: "string",
          enum: ["fast", "standard", "strict", "critical"],
          default: "standard",
          description:
            "Verification depth. fast=high-risk claims only. standard=all verifiable claims. " +
            "strict=every claim. critical=multiple authoritative sources required (use for medical/legal/financial).",
        },
        debug: {
          type: "boolean",
          default: false,
          description: "Return per-claim debug details",
        },
      },
    },
  },
  {
    name: "extract_claims",
    description:
      "Decompose any text into atomic, independently verifiable factual claims. " +
      "Each claim is classified by type (FACT, DATE, PERSON, API_BEHAVIOR, etc.) and risk level.",
    inputSchema: {
      type: "object",
      required: ["text"],
      properties: {
        text: {
          type: "string",
          description: "The text to decompose into atomic claims",
        },
        context: {
          type: "string",
          description: "Optional surrounding context",
        },
      },
    },
  },
  {
    name: "validate_source",
    description:
      "Validate whether a citation URL is real, reachable, and actually supports a claim. " +
      "Detects fabricated citations before they reach the user.",
    inputSchema: {
      type: "object",
      required: ["url", "claim_text"],
      properties: {
        url: {
          type: "string",
          description: "The URL to validate",
        },
        claim_text: {
          type: "string",
          description: "The claim this URL is supposed to support",
        },
      },
    },
  },
  {
    name: "health_check",
    description: "Check if the HalluGuard service is running and healthy.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// HTTP helper
// ─────────────────────────────────────────────────────────────────────────────

async function apiCall(path, body = null) {
  const method = body !== null ? "POST" : "GET";
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${path}`, options);

  if (!response.ok) {
    const errorText = await response.text();
    throw new McpError(
      ErrorCode.InternalError,
      `HalluGuard API error ${response.status}: ${errorText}`
    );
  }

  return await response.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// Format verification response for readability in chat
// ─────────────────────────────────────────────────────────────────────────────

function formatVerificationResult(result) {
  const report = result.verification_report;
  const riskEmoji = {
    LOW: "🟢",
    MEDIUM: "🟡",
    HIGH: "🟠",
    CRITICAL: "🔴",
  }[report.hallucination_risk] || "⚪";

  const gateEmoji = {
    ALLOW: "✅",
    REWRITE: "✏️",
    BLOCK_AND_REGENERATE: "🚫",
    REGENERATE_WITH_CONFLICT_DISCLOSURE: "⚠️",
    RETURN_UNCERTAIN_ANSWER: "❓",
  }[report.gate_decision] || "⚪";

  let output = `## HalluGuard Verification Report\n\n`;
  output += `${gateEmoji} **Gate**: ${report.gate_decision}  \n`;
  output += `${riskEmoji} **Risk**: ${report.hallucination_risk}  \n`;
  output += `📊 **Status**: ${report.overall_status}  \n`;
  output += `🔍 **Claims checked**: ${report.claims.length}\n\n`;

  if (report.claims.length > 0) {
    output += `### Claims\n\n`;
    for (const c of report.claims) {
      const statusEmoji = {
        VERIFIED: "✅",
        PARTIALLY_VERIFIED: "🔶",
        CONTRADICTED: "❌",
        UNSUPPORTED: "❌",
        INFERENCE: "💭",
        USER_PROVIDED: "👤",
        UNVERIFIABLE: "❓",
      }[c.status] || "⚪";
      output += `${statusEmoji} **[${c.claim.claim_type}]** ${c.claim.text}\n`;
      output += `   Status: \`${c.status}\` | Confidence: ${(c.confidence * 100).toFixed(0)}%\n`;
      if (c.fake_citation_detected) output += `   ⚠️ FAKE CITATION DETECTED\n`;
      if (c.repair_instruction) output += `   🔧 ${c.repair_instruction}\n`;
      output += "\n";
    }
  }

  if (report.warnings?.length > 0) {
    output += `### Warnings\n`;
    for (const w of report.warnings) output += `- ⚠️ ${w}\n`;
    output += "\n";
  }

  if (report.citations?.length > 0) {
    output += `### Validated Citations\n`;
    for (const c of report.citations) {
      output += `- [${c.title || c.domain}](${c.url}) — Tier ${c.tier}\n`;
    }
    output += "\n";
  }

  output += `---\n### Verified Answer\n\n${result.answer}`;
  return output;
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Server
// ─────────────────────────────────────────────────────────────────────────────

const server = new Server(
  { name: "halluguard", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "verify_answer": {
        const result = await apiCall("/v1/verify", {
          query: args.query,
          answer: args.answer,
          context: args.context || null,
          mode: args.mode || "standard",
          debug: args.debug || false,
        });
        return {
          content: [
            {
              type: "text",
              text: formatVerificationResult(result),
            },
          ],
        };
      }

      case "extract_claims": {
        const result = await apiCall("/v1/claims/extract", {
          text: args.text,
          context: args.context || null,
        });
        const lines = result.claims.map(
          (c) =>
            `- **[${c.claim_type}]** [${c.risk_level} risk] ${c.claim_text || c.text}`
        );
        return {
          content: [
            {
              type: "text",
              text: `## Extracted Claims (${result.claims.length})\n\n${lines.join("\n")}`,
            },
          ],
        };
      }

      case "validate_source": {
        const result = await apiCall("/v1/sources/validate", {
          url: args.url,
          claim_text: args.claim_text,
        });
        const available = result.source.is_available ? "✅ Reachable" : "❌ Unreachable / Fake";
        return {
          content: [
            {
              type: "text",
              text:
                `## Source Validation\n\n` +
                `${available}\n` +
                `URL: ${result.source.url}\n` +
                `Domain: ${result.source.domain}\n` +
                `Tier: ${result.source.tier} (1=Primary, 4=Low confidence)\n` +
                `HTTP Status: ${result.source.http_status ?? "N/A"}\n\n` +
                result.summary,
            },
          ],
        };
      }

      case "health_check": {
        const result = await apiCall("/health");
        return {
          content: [
            {
              type: "text",
              text: `✅ HalluGuard is healthy. Version: ${result.version}`,
            },
          ],
        };
      }

      default:
        throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
    }
  } catch (error) {
    if (error instanceof McpError) throw error;
    throw new McpError(
      ErrorCode.InternalError,
      `Tool execution failed: ${error.message}`
    );
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Start
// ─────────────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("HalluGuard MCP server running. API base:", API_BASE);
