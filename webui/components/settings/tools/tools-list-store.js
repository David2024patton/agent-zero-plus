import { createStore } from "/js/AlpineStore.js";
import { store as fileBrowserStore } from "/components/modals/file-browser/file-browser-store.js";

const fetchApi = globalThis.fetchApi;

const model = {
    loading: false,
    error: "",
    tools: [],

    async init() {
        this.resetState();
        await this.loadTools();
    },

    resetState() {
        this.loading = false;
        this.error = "";
        this.tools = [];
    },

    onClose() {
        this.resetState();
    },

    async loadTools() {
        try {
            this.loading = true;
            this.error = "";
            const response = await fetchApi("/tools", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "list" }),
            });
            const result = await response.json().catch(() => ({}));
            if (!result.ok) {
                this.error = result.error || "Failed to load tools";
                this.tools = [];
                return;
            }
            this.tools = Array.isArray(result.data) ? result.data : [];
        } catch (e) {
            this.error = e?.message || "Failed to load tools";
            this.tools = [];
        } finally {
            this.loading = false;
        }
    },

    async toggleTool(tool) {
        if (!tool) return;
        try {
            const response = await fetchApi("/tools", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "toggle",
                    tool_path: tool.path,
                }),
            });
            const result = await response.json().catch(() => ({}));
            if (!result.ok) {
                throw new Error(result.error || "Toggle failed");
            }
            const action = result.data?.enabled ? "enabled" : "disabled";
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess(`Tool ${tool.name} ${action}`, "Tools");
            }
            await this.loadTools();
        } catch (e) {
            const msg = e?.message || "Toggle failed";
            if (window.toastFrontendError) {
                window.toastFrontendError(msg, "Tools");
            }
        }
    },

    async openTool(tool) {
        await fileBrowserStore.open(tool.path);
    },
};

const store = createStore("toolsListStore", model);
export { store };
