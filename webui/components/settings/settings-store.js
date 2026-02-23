import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

// Constants
const VIEW_MODE_STORAGE_KEY = "settingsActiveTab";
const SUB_TAB_STORAGE_KEY = "settingsActiveSubTab";
const DEFAULT_TAB = "agent";
const DEFAULT_SUB_TAB = "agent-config";

// Sub-items for tabs that have collapsible children
const TAB_SUB_ITEMS = {
  agent: [
    { id: 'agent-config', label: 'Agent Config' },
    { id: 'chat-model', label: 'Chat Model' },
    { id: 'util-model', label: 'Utility Model' },
    { id: 'browser-model', label: 'Browser Model' },
    { id: 'subagent-model', label: 'Sub-Agent Model' },
    { id: 'embed-model', label: 'Embedding Model' },
    { id: 'memory', label: 'Memory' },
    { id: 'speech', label: 'Speech' },
    { id: 'workdir', label: 'Workdir' },
  ],
  external: [
    { id: 'api-keys', label: 'API Keys' },
    { id: 'secrets', label: 'Secrets' },
    { id: 'auth', label: 'Authentication' },
    { id: 'external-api', label: 'External API' },
    { id: 'update-checker', label: 'Update Checker' },
    { id: 'elevenlabs', label: 'ElevenLabs TTS' },
    { id: 'model-failover', label: 'Model Failover' },
    { id: 'cloudflare', label: 'Cloudflare' },
    { id: 'tunnel', label: 'Flare Tunnel' },
  ],
  litellm: [
    { id: 'general', label: 'General' },
    { id: 'litellm-api-keys', label: 'API Keys' },
    { id: 'caching', label: 'Caching' },
    { id: 'proxy-auth', label: 'Proxy Auth' },
    { id: 'advanced', label: 'Advanced' },
  ],
  developer: [
    { id: 'dev-general', label: 'Development' },
    { id: 'dev-subagents', label: 'Sub-Agents' },
    { id: 'dev-sandbox', label: 'Sandbox & Security' },
    { id: 'dev-cron', label: 'Cron Webhooks' },
    { id: 'dev-webmcp', label: 'WebMCP' },
    { id: 'dev-lifecycle', label: 'Lifecycle' },

    { id: 'dev-sysinfo', label: 'System Info' },
  ],
  skills: [
    { id: 'skills-list', label: 'List Skills' },
    { id: 'skills-import', label: 'Import Skills' },
  ],
  tools: [
    { id: 'tools-list', label: 'List Tools' },
  ],
  plugins: [
    { id: 'plugins-list', label: 'List Plugins' },
    { id: 'plugins-import', label: 'Import' },
    { id: 'plugins-discord', label: '🎮 Discord' },
    { id: 'plugins-email', label: '📧 Email' },
    { id: 'plugins-telegram', label: '📱 Telegram' },
    { id: 'plugins-slack', label: '💼 Slack' },
    { id: 'plugins-teams', label: '🏢 Teams' },
    { id: 'plugins-whatsapp', label: '📲 WhatsApp' },
    { id: 'plugins-matrix', label: '🔷 Matrix' },
    { id: 'plugins-webhook', label: '🔗 Webhook' },
    { id: 'plugins-openclaw', label: '⚙️ OpenClaw' },
  ],
  swarm: [
    { id: 'swarm-general', label: 'General' },
    { id: 'swarm-limits', label: 'Limits & Safety' },
    { id: 'swarm-tiers', label: 'Model Tiers' },
    { id: 'swarm-manifests', label: 'Agent Manifests' },
  ],
};

// Field button actions (field id -> modal path)
const FIELD_BUTTON_MODAL_BY_ID = Object.freeze({
  mcp_servers_config: "settings/mcp/client/mcp-servers.html",
  backup_create: "settings/backup/backup.html",
  backup_restore: "settings/backup/restore.html",
  show_a2a_connection: "settings/a2a/a2a-connection.html",
  external_api_examples: "settings/external/api-examples.html",
});

// Helper for toasts
function toast(text, type = "info", timeout = 5000) {
  notificationStore.addFrontendToastOnly(type, text, "", timeout / 1000);
}

// Settings Store
const model = {
  // State
  isLoading: false,
  error: null,
  settings: null,
  additional: null,
  workdirFileStructureTestOutput: "",
  systemTestRunning: false,
  systemTestOutput: "",

  // Tab state
  _activeTab: DEFAULT_TAB,
  _activeSubTab: DEFAULT_SUB_TAB,
  _tabExpanded: true,
  get activeTab() {
    return this._activeTab;
  },
  set activeTab(value) {
    const previous = this._activeTab;
    this._activeTab = value;
    this.applyActiveTab(previous, value);
  },

  get activeSubTab() {
    return this._activeSubTab;
  },
  set activeSubTab(value) {
    this._activeSubTab = value;
    try { localStorage.setItem(SUB_TAB_STORAGE_KEY, value); } catch { }
  },

  // Get sub-items for a tab
  tabSubItems(tabName) {
    return TAB_SUB_ITEMS[tabName] || [];
  },

  // Whether a tab has sub-items
  hasSubItems(tabName) {
    return !!(TAB_SUB_ITEMS[tabName] && TAB_SUB_ITEMS[tabName].length);
  },

  // Lifecycle
  init() {
    // Restore persisted tab
    try {
      const saved = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
      if (saved) this._activeTab = saved;
      const savedSub = localStorage.getItem(SUB_TAB_STORAGE_KEY);
      if (savedSub) this._activeSubTab = savedSub;
    } catch { }
  },

  async onOpen() {
    this.error = null;
    this.isLoading = true;

    try {
      const response = await API.callJsonApi("settings_get", null);
      if (response && response.settings) {
        this.settings = response.settings;
        this.additional = response.additional || null;
      } else {
        throw new Error("Invalid settings response");
      }
    } catch (e) {
      console.error("Failed to load settings:", e);
      this.error = e.message || "Failed to load settings";
      toast("Failed to load settings", "error");
    } finally {
      this.isLoading = false;
    }

    // Trigger tab activation for current tab
    this.applyActiveTab(null, this._activeTab);
  },

  cleanup() {
    this.settings = null;
    this.additional = null;
    this.error = null;
    this.isLoading = false;
  },

  // Tab management
  applyActiveTab(previous, current) {
    // Persist
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, current);
    } catch { }
  },

  switchTab(tabName) {
    // Toggle collapse if clicking the already-active tab that has sub-items
    if (tabName === this._activeTab && TAB_SUB_ITEMS[tabName]?.length) {
      this._tabExpanded = !this._tabExpanded;
      return;
    }
    this.activeTab = tabName;
    this._tabExpanded = true; // always expand when switching to a new tab
    // Auto-select first sub-item if tab has sub-items
    const subs = TAB_SUB_ITEMS[tabName];
    if (subs && subs.length) {
      // Only change sub-tab if current sub-tab isn't already in this tab's subs
      const currentBelongs = subs.some(s => s.id === this._activeSubTab);
      if (!currentBelongs) {
        this.activeSubTab = subs[0].id;
      }
    }
  },



  get apiKeyProviders() {
    const seen = new Set();
    const options = [];
    const addProvider = (prov) => {
      if (!prov?.value) return;
      const key = prov.value.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      options.push({ value: prov.value, label: prov.label || prov.value });
    };
    (this.additional?.chat_providers || []).forEach(addProvider);
    (this.additional?.embedding_providers || []).forEach(addProvider);
    // Additional service API keys (not model providers)
    const extraKeys = [
      { value: 'hostinger', label: 'Hostinger' },
      { value: 'github', label: 'GitHub' },
      { value: 'pastebin', label: 'Pastebin' },
      { value: 'dokploy', label: 'Dokploy' },
      { value: 'huggingface_token', label: 'HuggingFace Token' },
    ];
    extraKeys.forEach(addProvider);
    options.sort((a, b) => a.label.localeCompare(b.label));
    return options;
  },

  // Categorized API key providers for the grouped UI
  get apiKeyCategories() {
    const allProviders = this.apiKeyProviders; // reuse the flat list

    // Simple category mapping: provider value (lowercase) -> category index
    const LOCAL_PROVIDERS = new Set(['ollama', 'lmstudio', 'lm_studio']);
    const HOSTING_PROVIDERS = new Set([
      'github', 'github_copilot', 'dokploy', 'hostinger', 'pastebin',
      'huggingface', 'huggingface_token',
    ]);

    const categories = [
      { name: 'LLM Providers', icon: '🤖', providers: [] },
      { name: 'Local Models', icon: '💻', providers: [] },
      { name: 'Hosting & Developer Tools', icon: '🛠️', providers: [] },
    ];

    for (const prov of allProviders) {
      const key = prov.value.toLowerCase();
      if (LOCAL_PROVIDERS.has(key)) {
        categories[1].providers.push(prov);
      } else if (HOSTING_PROVIDERS.has(key)) {
        categories[2].providers.push(prov);
      } else {
        categories[0].providers.push(prov); // default: LLM Provider
      }
    }

    // Filter out empty categories
    return categories.filter(c => c.providers.length > 0);
  },

  // Save settings
  async saveSettings() {
    if (!this.settings) {
      toast("No settings to save", "warning");
      return false;
    }

    this.isLoading = true;
    try {
      const response = await API.callJsonApi("settings_set", { settings: this.settings });
      if (response && response.settings) {
        this.settings = response.settings;
        this.additional = response.additional || this.additional;
        toast("Settings saved successfully", "success");
        document.dispatchEvent(
          new CustomEvent("settings-updated", { detail: response.settings })
        );
        return true;
      } else {
        throw new Error("Failed to save settings");
      }
    } catch (e) {
      console.error("Failed to save settings:", e);
      toast("Failed to save settings: " + e.message, "error");
      return false;
    } finally {
      this.isLoading = false;
    }
  },

  // Close the modal
  closeSettings() {
    window.closeModal("settings/settings.html");
  },

  // Save and close
  async saveAndClose() {
    const success = await this.saveSettings();
    if (success) {
      this.closeSettings();
    }
  },

  // Save and run system tests (iTaK integration)
  async saveAndRunTests() {
    const success = await this.saveSettings();
    if (!success) return false;

    this.switchTab("external");
    toast("Settings saved. Check External Services for connectivity.", "info");
    return true;
  },

  async testWorkdirFileStructure() {
    if (!this.settings) return;
    try {
      const response = await API.callJsonApi("settings_workdir_file_structure", {
        workdir_path: this.settings.workdir_path,
        workdir_max_depth: this.settings.workdir_max_depth,
        workdir_max_files: this.settings.workdir_max_files,
        workdir_max_folders: this.settings.workdir_max_folders,
        workdir_max_lines: this.settings.workdir_max_lines,
        workdir_gitignore: this.settings.workdir_gitignore,
      });
      this.workdirFileStructureTestOutput = response?.data || "";
      window.openModal("settings/agent/workdir-file-structure-test.html");
    } catch (e) {
      console.error("Error testing workdir file structure:", e);
      toast("Error testing workdir file structure", "error");
    }
  },

  // Field helpers for external components
  // Handle button field clicks (opens sub-modals)
  async handleFieldButton(field) {
    const modalPath = FIELD_BUTTON_MODAL_BY_ID[field?.id];
    if (modalPath) window.openModal(modalPath);
  },

  // Open settings modal from external callers
  async open(initialTab = null) {
    if (initialTab) {
      this._activeTab = initialTab;
    }
    await window.openModal("settings/settings.html");
  },
};

const store = createStore("settings", model);

export { store };

