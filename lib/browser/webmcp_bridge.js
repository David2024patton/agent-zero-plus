/**
 * WebMCP Bridge for Agent Zero
 * =============================
 * Client-side JavaScript bridge that enables Agent Zero's browser agent
 * to discover and invoke WebMCP tools on pages that support the protocol.
 *
 * WebMCP (Web Model Context Protocol) is Google's browser-based protocol
 * allowing websites to expose structured functions via `navigator.modelContext`.
 *
 * This script is injected alongside init_override.js into every page context.
 */
(function () {
    "use strict";

    // ─── Tool Discovery ────────────────────────────────────────────────
    // Checks both the imperative API (navigator.modelContext) and
    // declarative manifests (<link rel="webmcp-tool">).

    /**
     * Discover all available WebMCP tools on the current page.
     * Returns a JSON-serializable array of tool descriptors.
     *
     * @returns {Promise<Array<{name: string, description: string, parameters: object, source: string}>>}
     */
    window.__A0_webmcp_discover = async function () {
        const tools = [];

        // 1. Check imperative API (navigator.modelContext)
        if (
            typeof navigator !== "undefined" &&
            navigator.modelContext &&
            typeof navigator.modelContext.getTools === "function"
        ) {
            try {
                const mcpTools = await navigator.modelContext.getTools();
                if (Array.isArray(mcpTools)) {
                    for (const tool of mcpTools) {
                        tools.push({
                            name: tool.name || "unknown",
                            description: tool.description || "",
                            parameters: tool.parameters || tool.inputSchema || {},
                            source: "imperative",
                        });
                    }
                }
            } catch (e) {
                console.warn("[A0 WebMCP] Error discovering imperative tools:", e);
            }
        }

        // 2. Check declarative manifests (<link rel="webmcp-tool">)
        const linkElements = document.querySelectorAll(
            'link[rel="webmcp-tool"], link[rel="webmcp"]'
        );
        for (const link of linkElements) {
            const href = link.getAttribute("href");
            if (!href) continue;
            try {
                const url = new URL(href, window.location.origin);
                const resp = await fetch(url.toString(), {
                    credentials: "same-origin",
                    signal: AbortSignal.timeout(5000),
                });
                if (resp.ok) {
                    const manifest = await resp.json();
                    // Manifest can be a single tool or an array of tools
                    const manifestTools = Array.isArray(manifest)
                        ? manifest
                        : manifest.tools || [manifest];
                    for (const tool of manifestTools) {
                        tools.push({
                            name: tool.name || "unknown",
                            description: tool.description || "",
                            parameters: tool.parameters || tool.inputSchema || {},
                            source: "declarative",
                            manifestUrl: url.toString(),
                        });
                    }
                }
            } catch (e) {
                console.warn("[A0 WebMCP] Error fetching manifest:", href, e);
            }
        }

        return tools;
    };

    // ─── Tool Invocation ───────────────────────────────────────────────

    /**
     * Call a WebMCP tool by name with the given parameters.
     *
     * @param {string} toolName - Name of the tool to invoke
     * @param {object} params - Parameters to pass to the tool
     * @returns {Promise<{success: boolean, result: any, error: string|null}>}
     */
    window.__A0_webmcp_call = async function (toolName, params) {
        // Prefer imperative API
        if (
            typeof navigator !== "undefined" &&
            navigator.modelContext &&
            typeof navigator.modelContext.callTool === "function"
        ) {
            try {
                const result = await navigator.modelContext.callTool(toolName, params);
                return {
                    success: true,
                    result: result,
                    error: null,
                };
            } catch (e) {
                return {
                    success: false,
                    result: null,
                    error: `WebMCP callTool error: ${e.message || e}`,
                };
            }
        }

        return {
            success: false,
            result: null,
            error:
                "WebMCP not available on this page (navigator.modelContext not found)",
        };
    };

    // ─── Status Check ──────────────────────────────────────────────────

    /**
     * Quick check if WebMCP is available on this page.
     *
     * @returns {{available: boolean, imperative: boolean, declarative: boolean, toolCount: number}}
     */
    window.__A0_webmcp_status = function () {
        const hasImperative = !!(
            typeof navigator !== "undefined" &&
            navigator.modelContext &&
            typeof navigator.modelContext.getTools === "function"
        );
        const declarativeLinks = document.querySelectorAll(
            'link[rel="webmcp-tool"], link[rel="webmcp"]'
        );
        const hasDeclarative = declarativeLinks.length > 0;

        return {
            available: hasImperative || hasDeclarative,
            imperative: hasImperative,
            declarative: hasDeclarative,
            declarativeCount: declarativeLinks.length,
        };
    };

    console.log("[A0 WebMCP] Bridge loaded");
})();
