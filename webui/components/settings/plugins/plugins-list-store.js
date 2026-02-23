import { createStore } from "/js/AlpineStore.js";

const fetchApi = globalThis.fetchApi;

const model = {
    loading: false,
    error: "",
    plugins: [],
    configuring: null, // plugin currently being configured

    async init() {
        this.resetState();
        await this.loadPlugins();
    },

    resetState() {
        this.loading = false;
        this.error = "";
        this.plugins = [];
        this.configuring = null;
    },

    onClose() {
        this.resetState();
    },

    async loadPlugins() {
        try {
            this.loading = true;
            this.error = "";
            const response = await fetchApi("/plugins", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "list" }),
            });
            const result = await response.json().catch(() => ({}));
            if (!result.ok) {
                this.error = result.error || "Failed to load plugins";
                this.plugins = [];
                return;
            }
            this.plugins = Array.isArray(result.data) ? result.data : [];
        } catch (e) {
            this.error = e?.message || "Failed to load plugins";
            this.plugins = [];
        } finally {
            this.loading = false;
        }
    },

    async togglePlugin(plugin) {
        if (!plugin) return;
        try {
            const action = plugin.enabled ? "disable" : "enable";
            const response = await fetchApi("/plugins", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action, plugin_id: plugin.id }),
            });
            const result = await response.json().catch(() => ({}));
            if (!result.ok) {
                throw new Error(result.error || "Toggle failed");
            }
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess(
                    `Plugin ${action}d: ${plugin.name}`,
                    "Plugins"
                );
            }
            await this.loadPlugins();
        } catch (e) {
            const msg = e?.message || "Toggle failed";
            if (window.toastFrontendError) {
                window.toastFrontendError(msg, "Plugins");
            }
        }
    },

    openConfig(plugin) {
        // Deep clone config so edits don't directly mutate the list
        this.configuring = {
            ...plugin,
            config: plugin.config.map((f) => ({ ...f })),
        };
    },

    cancelConfig() {
        this.configuring = null;
    },

    async saveConfig() {
        if (!this.configuring) return;
        try {
            const configPayload = {};
            for (const field of this.configuring.config) {
                configPayload[field.key] = field.value;
            }
            const response = await fetchApi("/plugins", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "save_config",
                    plugin_id: this.configuring.id,
                    config: configPayload,
                }),
            });
            const result = await response.json().catch(() => ({}));
            if (!result.ok) {
                throw new Error(result.error || "Save failed");
            }
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess(
                    `Config saved for ${this.configuring.name}`,
                    "Plugins"
                );
            }
            this.configuring = null;
            await this.loadPlugins();
        } catch (e) {
            const msg = e?.message || "Save failed";
            if (window.toastFrontendError) {
                window.toastFrontendError(msg, "Plugins");
            }
        }
    },
};

const store = createStore("pluginsListStore", model);
export { store };
