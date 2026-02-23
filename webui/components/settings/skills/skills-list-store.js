import { createStore } from "/js/AlpineStore.js";
import { store as fileBrowserStore } from "/components/modals/file-browser/file-browser-store.js";

const fetchApi = globalThis.fetchApi;

// Path inside Agent Zero – used by edit_work_dir_file API
const AUTO_LOAD_FILE_PATH = "/a0/usr/auto_load_skills.json";

const model = {
  loading: false,
  error: "",
  skills: [],
  projects: [],
  projectName: "",
  agentProfiles: [],
  agentProfileKey: "",
  autoLoadSkills: [],   // array of skill names that are set to auto-load

  async init() {
    this.resetState();
    await Promise.all([this.loadProjects(), this.loadAgentProfiles(), this.loadAutoLoadSetting()]);
    await this.loadSkills();
  },

  resetState() {
    this.loading = false;
    this.error = "";
    this.skills = [];
    this.projects = [];
    this.projectName = "";
    this.agentProfiles = [];
    this.agentProfileKey = "";
    this.autoLoadSkills = [];
  },

  onClose() {
    this.resetState();
  },

  // ── Auto-load: read & write via edit_work_dir_file (session auth) ──
  async loadAutoLoadSetting() {
    try {
      // Use GET to read the file content via edit_work_dir_file
      const response = await fetchApi(
        `/edit_work_dir_file?path=${encodeURIComponent(AUTO_LOAD_FILE_PATH)}`,
        { method: "GET" }
      );
      const result = await response.json().catch(() => ({}));

      if (result.data && result.data.content) {
        const parsed = JSON.parse(result.data.content);
        if (Array.isArray(parsed)) {
          this.autoLoadSkills = parsed.filter(s => typeof s === "string" && s.trim());
          return;
        }
      }
      this.autoLoadSkills = [];
    } catch (e) {
      // File might not exist yet, that's fine
      console.log("Auto-load skills file not found (normal on first use)");
      this.autoLoadSkills = [];
    }
  },

  isAutoLoad(skill) {
    return this.autoLoadSkills.includes(skill.name);
  },

  async toggleAutoLoad(skill) {
    const idx = this.autoLoadSkills.indexOf(skill.name);
    if (idx >= 0) {
      this.autoLoadSkills.splice(idx, 1);
    } else {
      this.autoLoadSkills.push(skill.name);
    }
    await this.saveAutoLoadSetting();
  },

  async saveAutoLoadSetting() {
    try {
      const jsonContent = JSON.stringify(this.autoLoadSkills, null, 2);
      const response = await fetchApi("/edit_work_dir_file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: AUTO_LOAD_FILE_PATH,
          content: jsonContent,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (result.error) {
        throw new Error(result.error);
      }
      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess("Auto-load skills updated", "Skills");
      }
    } catch (e) {
      console.error("Failed to save auto_load_skills:", e);
      if (window.toastFrontendError) {
        window.toastFrontendError("Failed to save: " + (e.message || ""), "Skills");
      }
    }
  },

  // ── Existing methods ──────────────────────────────────────
  async loadAgentProfiles() {
    try {
      const response = await fetchApi("/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list" }),
      });
      const data = await response.json().catch(() => ({}));
      this.agentProfiles = data.ok ? (data.data || []) : [];
    } catch (e) {
      console.error("Failed to load agent profiles:", e);
      this.agentProfiles = [];
    }
  },

  async loadProjects() {
    try {
      const response = await fetchApi("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "list_options" }),
      });
      const data = await response.json().catch(() => ({}));
      this.projects = data.ok ? (data.data || []) : [];
    } catch (e) {
      console.error("Failed to load projects:", e);
      this.projects = [];
    }
  },

  async loadSkills() {
    try {
      this.loading = true;
      this.error = "";
      const response = await fetchApi("/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "list",
          project_name: this.projectName || null,
          agent_profile: this.agentProfileKey || null,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!result.ok) {
        this.error = result.error || "Failed to load skills";
        this.skills = [];
        return;
      }
      this.skills = Array.isArray(result.data) ? result.data : [];
    } catch (e) {
      this.error = e?.message || "Failed to load skills";
      this.skills = [];
    } finally {
      this.loading = false;
    }
  },

  async deleteSkill(skill) {
    if (!skill) return;
    try {
      const response = await fetchApi("/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "delete",
          skill_path: skill.path,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!result.ok) {
        throw new Error(result.error || "Delete failed");
      }
      // Also remove from auto-load if present
      const idx = this.autoLoadSkills.indexOf(skill.name);
      if (idx >= 0) {
        this.autoLoadSkills.splice(idx, 1);
        await this.saveAutoLoadSetting();
      }
      if (window.toastFrontendSuccess) {
        window.toastFrontendSuccess("Skill deleted", "Skills");
      }
      await this.loadSkills();
    } catch (e) {
      const msg = e?.message || "Delete failed";
      if (window.toastFrontendError) {
        window.toastFrontendError(msg, "Skills");
      }
    }
  },

  async openSkill(skill) {
    await fileBrowserStore.open(skill.path);
  },
};

const store = createStore("skillsListStore", model);
export { store };
