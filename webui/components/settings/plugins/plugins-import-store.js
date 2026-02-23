import { createStore } from "/js/AlpineStore.js";

const fetchApi = globalThis.fetchApi;

const model = {
    loading: false,
    loadingMessage: "",
    error: "",

    pluginsFile: null,
    preview: null,
    result: null,

    init() {
        this.resetState();
    },

    resetState() {
        this.loading = false;
        this.loadingMessage = "";
        this.error = "";
        this.preview = null;
        this.result = null;
    },

    onClose() {
        this.resetState();
        this.pluginsFile = null;
    },

    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        this.pluginsFile = file;
        this.error = "";
        this.result = null;
        this.preview = null;

        await this.previewImport();
    },

    buildFormData() {
        const formData = new FormData();
        formData.append("plugins_file", this.pluginsFile);
        formData.append("ctxid", globalThis.getContext ? globalThis.getContext() : "");
        return formData;
    },

    async previewImport() {
        if (!this.pluginsFile) {
            this.error = "Please select a plugin .zip file first";
            return;
        }

        try {
            this.loading = true;
            this.loadingMessage = "Scanning plugin archive...";
            this.error = "";
            this.preview = null;

            const response = await fetchApi("/plugins_import", {
                method: "POST",
                body: (() => {
                    const fd = this.buildFormData();
                    fd.append("action", "preview");
                    return fd;
                })(),
            });

            const result = await response.json();
            if (!result.ok) {
                this.error = result.error || "Preview failed";
                return;
            }

            this.preview = result.data;
        } catch (e) {
            this.error = `Preview error: ${e.message}`;
        } finally {
            this.loading = false;
            this.loadingMessage = "";
        }
    },

    async performImport() {
        if (!this.pluginsFile) {
            this.error = "Please select a plugin .zip file first";
            return;
        }

        try {
            this.loading = true;
            this.loadingMessage = "Importing plugins...";
            this.error = "";
            this.result = null;

            const response = await fetchApi("/plugins_import", {
                method: "POST",
                body: (() => {
                    const fd = this.buildFormData();
                    fd.append("action", "import");
                    return fd;
                })(),
            });

            const result = await response.json();
            if (!result.ok) {
                this.error = result.error || "Import failed";
                return;
            }

            this.result = result.data;
            this.preview = null;
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess(
                    `Imported ${result.data.imported_count} plugin(s)`,
                    "Plugins"
                );
            }
        } catch (e) {
            this.error = `Import error: ${e.message}`;
        } finally {
            this.loading = false;
            this.loadingMessage = "";
        }
    },
};

const store = createStore("pluginsImportStore", model);
export { store };
