/* UCC SHARED RUNTIME v1.7.0 */
(function (global) {
"use strict";
if (global.UCCShared) return;

function escapeHtml(value) {
const div = document.createElement("div");
div.textContent = value == null ? "" : String(value);
return div.innerHTML;
}

function csvCell(value) {
return `"${String(value == null ? "" : value)
      .replace(/"/g, '""')
      .replace(/\s+/g, " ")
      .trim()}"`;
}

function tableToCsv(table) {
return Array.from(table.querySelectorAll("tr"))
.map(row =>
Array.from(row.querySelectorAll("th,td"))
.map(cell => csvCell(cell.innerText))
.join(",")
)
.join("\n");
}

function download(name, content, type) {
const mime = type || "text/csv;charset=utf-8";
const blob = new Blob(["\ufeff", content], { type: mime });
const url = URL.createObjectURL(blob);
const anchor = document.createElement("a");
anchor.href = url;
anchor.download = name;
document.body.appendChild(anchor);
anchor.click();
anchor.remove();
URL.revokeObjectURL(url);
}

function doctypeRoute(doctype) {
if (!doctype) return "#";
let slug = "";
if (
global.frappe &&
frappe.router &&
typeof frappe.router.slug === "function"
) {
slug = frappe.router.slug(doctype);
} else {
slug = String(doctype)
.trim()
.toLowerCase()
.replace(/[^a-z0-9]+/g, "-")
.replace(/^-+|-+$/g, "");
}
return "/app/" + slug;
}

function openDoctype(doctype) {
if (!doctype) return;
global.open(doctypeRoute(doctype), "_blank", "noopener,noreferrer");
}

function readStorage(key, fallback) {
try {
const value = localStorage.getItem(key);
return value == null ? fallback : value;
} catch (error) {
return fallback;
}
}

function writeStorage(key, value) {
try {
localStorage.setItem(key, value);
} catch (error) {}
}

global.UCCShared = Object.freeze({
escapeHtml,
csvCell,
tableToCsv,
download,
doctypeRoute,
openDoctype,
readStorage,
writeStorage
});
})(window);
// Consolidates a dashboard's separate "Data Quality" and "Sources" tabs into a
// single "Sources & Data Quality" tab: the Data Quality panel's content is moved
// into the Sources panel and the Data Quality tab button is removed. Shared by
// all three dashboard architectures (demo/C4/C5) via their own tab attributes.
window.__uccMergeSourcesQuality=function(dash,tabAttr,panelAttr){
if(!dash||dash.dataset.sqMerged==="1")return;
const sourcesTab=dash.querySelector(`[${tabAttr}="sources"]`),qualityTab=dash.querySelector(`[${tabAttr}="quality"]`);
const sourcesPanel=dash.querySelector(`[${panelAttr}="sources"]`),qualityPanel=dash.querySelector(`[${panelAttr}="quality"]`);
if(!sourcesTab||!sourcesPanel)return;
dash.dataset.sqMerged="1";
sourcesTab.textContent="Sources & Data Quality";
if(qualityPanel){while(qualityPanel.firstChild)sourcesPanel.appendChild(qualityPanel.firstChild);qualityPanel.remove();}
if(qualityTab)qualityTab.remove();
};
(function () {
"use strict";
const root = typeof root_element !== "undefined"
? root_element.querySelector("#uccIntelligencePlatform")
: document.querySelector("#uccIntelligencePlatform");
if (!root || root.dataset.platformReady === "1") {
return;
}
root.dataset.platformReady = "1";
const workspaceButtons = Array.from(
root.querySelectorAll("[data-ucc-workspace]")
);
const workspacePanels = Array.from(
root.querySelectorAll("[data-ucc-workspace-panel]")
);
const dashboardControl = root.querySelector("[data-ucc-dashboard-control]");
const status = root.querySelector("[data-ucc-platform-status]");
const dashboardSelect = root.querySelector("#uccDashboardSelect");
function setWorkspace(workspace) {
workspaceButtons.forEach(function (button) {
const active = button.dataset.uccWorkspace === workspace;
button.classList.toggle("is-active", active);
button.setAttribute("aria-pressed", active ? "true" : "false");
});
workspacePanels.forEach(function (panel) {
panel.hidden = panel.dataset.uccWorkspacePanel !== workspace;
});
if (dashboardControl) {
dashboardControl.hidden = workspace !== "analytics" && workspace !== "explore";
}
if (status) {
if (workspace === "analytics") {
status.textContent = "Analytics is active. Criteria 1–7 now use permission-aware live sources or live API foundations; unavailable fields are shown explicitly.";
} else if (workspace === "explore") {
status.textContent = "Explore is active. Search the visual catalogue and open the original live diagram in one click.";
} else {
status.textContent = "Ask UCC is active. Choose the assistant and record first; guided questions work without OpenAI.";
}
}
}
workspaceButtons.forEach(function (button) {
button.addEventListener("click", function () {
setWorkspace(button.dataset.uccWorkspace);
});
});
const dashboardPanels = Array.from(root.querySelectorAll("[data-dashboard-panel]"));
const shell = root.querySelector(".ucc-platform-shell");
const shellToggle = root.querySelector("[data-shell-toggle]");
const shellToggleIcon = root.querySelector("[data-shell-toggle-icon]");
const shellToggleLabel = root.querySelector("[data-shell-toggle-label]");
const CRITERION_LABELS = Object.freeze({"criterion_1": "Criterion 1 · Leadership and Strategic Planning", "criterion_2": "Criterion 2 · Corporate Administration", "criterion_3": "Criterion 3 · External Recruitment Agents", "criterion_4": "Criterion 4 · Student Protection and Support Services", "criterion_5": "Criterion 5 · Academic Systems and Processes", "criterion_6": "Criterion 6 · Quality Assurance, Innovation and Continual Improvement", "criterion_7": "Criterion 7 · Performance Outcomes"});
let shellCollapsed = false;

function activeWorkspaceName() {
const active = workspaceButtons.find(function (button) { return button.classList.contains("is-active"); });
return active ? active.dataset.uccWorkspace : "analytics";
}
function scrollDashboardToTop(dashboard) {
const panel = dashboardPanels.find(function (item) { return item.dataset.dashboardPanel === dashboard; });
const target = panel ? (panel.querySelector(".hero") || panel) : root;
requestAnimationFrame(function () {
try {
target.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
} catch (error) {
try { target.scrollIntoView(true); } catch (ignored) {}
}
let current = root.parentElement;
while (current && current !== document.body) {
const style = window.getComputedStyle(current);
const scrollable = /(auto|scroll)/.test(style.overflowY || "") && current.scrollHeight > current.clientHeight;
if (scrollable) {
const top = Math.max(0, target.getBoundingClientRect().top - current.getBoundingClientRect().top + current.scrollTop - 12);
try { current.scrollTo({ top: top, behavior: "smooth" }); } catch (error) { current.scrollTop = top; }
break;
}
current = current.parentElement;
}
});
}
function setDashboard(dashboard) {
dashboardPanels.forEach(function (panel) { panel.classList.toggle("ucc-hidden", panel.dataset.dashboardPanel !== dashboard); });
if (dashboardSelect && dashboardSelect.value !== dashboard) dashboardSelect.value = dashboard;
if (status) {
const workspace = activeWorkspaceName();
if (workspace === "explore") status.textContent = "Explore is active. Search the live visual catalogue for the selected criterion.";
else if (workspace === "ask") status.textContent = "Ask UCC is active. Choose the assistant and record first.";
else {
const label = CRITERION_LABELS[dashboard] || dashboard;
const fullLive = dashboard === "criterion_4" || dashboard === "criterion_5";
status.textContent = fullLive
? label + " is active with mature live, permission-aware analytics."
: label + " is active with a permission-aware live API foundation. Unsupported fields are shown explicitly.";
}
}
try { localStorage.setItem("ucc.dashboard", dashboard); } catch (error) {}
scrollDashboardToTop(dashboard);
try { root.dispatchEvent(new CustomEvent("ucc:dashboard-change", { detail: { dashboard: dashboard } })); } catch (error) {}
}
if (dashboardSelect) dashboardSelect.addEventListener("change", function () { setDashboard(dashboardSelect.value); });
function applyShellState() {
if (!shell || !shellToggle) return;
shell.classList.toggle("is-collapsed", shellCollapsed);
shellToggle.setAttribute("aria-expanded", shellCollapsed ? "false" : "true");
shellToggle.setAttribute("aria-label", shellCollapsed ? "Expand UCC navigation" : "Minimise UCC navigation");
shellToggle.setAttribute("title", shellCollapsed ? "Expand navigation" : "Minimise navigation");
if (shellToggleIcon) shellToggleIcon.textContent = shellCollapsed ? "›" : "‹";
if (shellToggleLabel) shellToggleLabel.textContent = shellCollapsed ? "Expand navigation" : "Minimise navigation";
}
let shellPlaceholder = null;
function frappeTopOffset() {
const navbar = document.querySelector(".navbar.navbar-expand, header.navbar, .desk-navbar, .navbar");
if (!navbar) return 8;
const rect = navbar.getBoundingClientRect();
return rect.bottom > 0 ? Math.max(8, Math.round(rect.bottom + 8)) : 8;
}
function syncFloatingShell() {
if (!shell || !root.isConnected) return;
if (!shellPlaceholder) {
shellPlaceholder = document.createElement("div");
shellPlaceholder.className = "ucc-platform-shell-placeholder";
shell.parentNode.insertBefore(shellPlaceholder, shell);
}
const top = frappeTopOffset();
const rootRect = root.getBoundingClientRect();
const anchorRect = shellPlaceholder.getBoundingClientRect();
const shellHeight = Math.max(58, Math.round(shell.getBoundingClientRect().height || shell.offsetHeight || 58));
const shouldFloat = anchorRect.top <= top && rootRect.bottom > top + shellHeight + 16;
shell.classList.toggle("is-floating", shouldFloat);
root.classList.toggle("has-floating-shell", shouldFloat);
root.style.setProperty("--ucc-dashboard-sticky-top", String(top + shellHeight + 10) + "px");
if (shouldFloat) {
const width = shellCollapsed ? Math.min(108, rootRect.width) : Math.min(1500, rootRect.width);
const left = shellCollapsed ? rootRect.left : rootRect.left + Math.max(0, (rootRect.width - width) / 2);
shell.style.setProperty("--ucc-shell-floating-top", String(top) + "px");
shell.style.setProperty("--ucc-shell-floating-left", String(Math.round(left)) + "px");
shell.style.setProperty("--ucc-shell-floating-width", String(Math.round(width)) + "px");
shellPlaceholder.style.height = String(shellHeight + 10) + "px";
} else {
shell.style.removeProperty("--ucc-shell-floating-top");
shell.style.removeProperty("--ucc-shell-floating-left");
shell.style.removeProperty("--ucc-shell-floating-width");
shellPlaceholder.style.height = "0px";
}
}
if (shellToggle) shellToggle.addEventListener("click", function (event) {
event.preventDefault();
event.stopPropagation();
shellCollapsed = !shellCollapsed;
applyShellState();
requestAnimationFrame(syncFloatingShell);
});
let savedDashboard = "criterion_5";
try { savedDashboard = localStorage.getItem("ucc.dashboard") || savedDashboard; } catch (error) {}
try {
const urlDashboard = new URLSearchParams(location.search).get("dashboard");
if (urlDashboard) savedDashboard = urlDashboard;
} catch (error) {}
if (!["criterion_1", "criterion_2", "criterion_3", "criterion_4", "criterion_5", "criterion_6", "criterion_7"].includes(savedDashboard)) savedDashboard = "criterion_5";
setWorkspace("analytics");
setDashboard(savedDashboard);
applyShellState();
requestAnimationFrame(syncFloatingShell);
document.addEventListener("scroll", syncFloatingShell, true);
window.addEventListener("resize", syncFloatingShell);
if (typeof ResizeObserver !== "undefined") {
const shellResizeObserver = new ResizeObserver(syncFloatingShell);
shellResizeObserver.observe(root);
shellResizeObserver.observe(shell);
}
})();
/* Criterion dashboards are mounted by the shared dashboard engine. */

(function () {
"use strict";
const root = typeof root_element !== "undefined" ? root_element : document;
const app = root ? root.querySelector("#ajaApp") : null;
if (!app || app.dataset.admissionJourneyReady === "1") {
return;
}
app.dataset.admissionJourneyReady = "1";
const MODULE_CONFIG = {
student_journey: {
label: "Student Journey",
apiMethod: "ucc_ask_student_journey",
entityLabel: "student",
entityLabelTitle: "Student",
pinnedLabel: "Pinned student",
findLabel: "Find student",
recentLabel: "Recent students",
searchPlaceholder: "Type name or Applicant ID",
headerTitle: "Ask UCC · Student Journey",
headerSubtitle: "Ask about students, courses, modules, assessments, classes, leave and graduation.",
comingSoon: false
},
recruitment_agent: {
label: "Recruitment Agent",
apiMethod: "ucc_ask_recruitment_agent",
entityLabel: "agent",
entityLabelTitle: "Recruitment Agent",
pinnedLabel: "Pinned agent",
findLabel: "Find recruitment agent",
recentLabel: "Recent agents",
searchPlaceholder: "Type agent, company or contract ID",
headerTitle: "Ask UCC · Recruitment Agent",
headerSubtitle: "Ask about agent profiles, contracts, expiry, recruitment performance, ratings and renewal.",
comingSoon: false
},
quality_action: {
label: "Quality Action",
apiMethod: "ucc_ask_quality_action",
entityLabel: "quality action",
entityLabelTitle: "Quality Action",
pinnedLabel: "Pinned Quality Action",
findLabel: "Find Quality Action",
recentLabel: "Recent Quality Actions",
searchPlaceholder: "Type Quality Action ID or subject",
headerTitle: "Ask UCC · Quality Action",
headerSubtitle: "Ask about findings, root causes, actions, assignments, due dates, closure readiness and quality review.",
comingSoon: false
},
hr_assistant: {
label: "HR",
entityLabel: "employee",
entityLabelTitle: "Employee",
comingSoon: true
}
};
function activeModuleConfig() {
return MODULE_CONFIG[state.activeModule] || MODULE_CONFIG.student_journey;
}
const moduleSelect = root.querySelector("#ajaModuleSelect");
const moduleStatus = root.querySelector("#ajaModuleStatus");
const pinnedLabel = root.querySelector("#ajaPinnedLabel");
const findLabel = root.querySelector("#ajaFindLabel");
const recentLabel = root.querySelector("#ajaRecentLabel");
const headerTitle = root.querySelector("#ajaHeaderTitle");
const headerSubtitle = root.querySelector("#ajaHeaderSubtitle");
const comingSoon = root.querySelector("#ajaComingSoon");
const chat = root.querySelector("#ajaChat");
const questionInput = root.querySelector("#ajaQuestion");
const sendButton = root.querySelector("#ajaSend");
const printButton = root.querySelector("#ajaPrint");
const statusElement = root.querySelector("#ajaStatus");
const currentStudentElement = root.querySelector("#ajaCurrentStudent .aja-current-value");
const suggestionsContainer = root.querySelector("#ajaSuggestions");
const categorySelect = root.querySelector("#ajaQuestionCategory");
const categoryButtons = root.querySelector("#ajaQuestionCategoryButtons");
const clearChatButton = root.querySelector("#ajaClearChat");
const controlledQuestions = root.querySelector("#ajaControlledQuestions");
const studentSearch = root.querySelector("#ajaStudentSearch");
const studentMatches = root.querySelector("#ajaStudentMatches");
const studentPager = root.querySelector("#ajaStudentPager");
const courseFilter = root.querySelector("#ajaCourseFilter");
const recentStudents = root.querySelector("#ajaRecentStudents");
const changeStudentButton = root.querySelector("#ajaChangeStudent");
const resetContextButton = root.querySelector("#ajaResetContext");
const exportCsvButton = root.querySelector("#ajaExportCsv");
const diagnosticsButton = root.querySelector("#ajaDiagnostics");
const apiButton = root.querySelector("#ajaApiButton");
const apiModal = root.querySelector("#ajaApiModal");
const apiKeyInput = root.querySelector("#ajaApiKeyInput");
const apiCancel = root.querySelector("#ajaApiCancel");
const apiSkip = root.querySelector("#ajaApiSkip");
const apiConnect = root.querySelector("#ajaApiConnect");
let pendingFreeQuestion = "";
const state = {
activeModule: "student_journey",
moduleRecords: null,
loading: false,
studentApplicant: "",
studentName: "",
history: [],
studentRollRows: null,
lastQuestion: "",
recentStudents: [],
lastResult: null,
lastVisualRows: [],
lastExportSections: [],
searchPage: 1,
searchPageSize: 8
};
function safeArray(value) {
return Array.isArray(value) ? value : [];
}
function cleanText(value) {
return String(value === null || value === undefined ? "" : value)
.replace(/\s+/g, " ")
.trim();
}
function formatDate(value) {
if (!value) return "";
const text = String(value).trim();
let match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$/);
if (!match) {
match = text.match(/^(\d{1,2})[-\/]([0-9]{1,2})[-\/](\d{4})$/);
if (!match) return text;
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
return String(Number(match[1])).padStart(2, "0") + " " + months[Number(match[2]) - 1] + " " + match[3];
}
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
return String(Number(match[3])).padStart(2, "0") + " " + months[Number(match[2]) - 1] + " " + match[1];
}
function formatDatesInText(value) {
return String(value === null || value === undefined ? "" : value).replace(
/\b(\d{4}-\d{2}-\d{2})(?:[T ][0-9:.+-Z]+)?\b/g,
function (matched) {
return formatDate(matched.slice(0, 10));
}
);
}
function displayValue(value) {
if (value === null || value === undefined || value === "") {
return "Not recorded";
}
if (value && typeof value === "object" && !Array.isArray(value)) {
return formatDatesInText(
value.text || value.label || value.name || "Not recorded"
);
}
if (typeof value === "string") {
return formatDatesInText(value);
}
return String(value);
}
function setStatus(text, loading) {
if (statusElement) {
statusElement.textContent = text || "Ready";
}
const catStatus = root.querySelector("#ajaCatStatus");
if (catStatus) {
catStatus.classList.toggle("is-working", Boolean(loading));
}
}
function updateSuggestionState() {
if (!suggestionsContainer) {
return;
}
suggestionsContainer
.querySelectorAll(".aja-suggestion")
.forEach(function (button) {
button.disabled = false;
button.title = state.studentApplicant
? "Ask about " + (state.studentName || state.studentApplicant)
: "Select a student first";
});
}
function updateCurrentStudent() {
if (!currentStudentElement) return;
if (!state.studentApplicant) {
currentStudentElement.textContent = "Not selected";
return;
}
currentStudentElement.textContent =
(state.studentName || state.studentApplicant) +
" (" + state.studentApplicant + ")";
}
function uniqueStudentsFromRoll() {
if (state.activeModule === "recruitment_agent") {
return safeArray(state.moduleRecords).map(function (row) {
return {
id: cleanText(row.name),
name: cleanText(row.party_name) || cleanText(row.name),
course: cleanText(row.personal_id) || "Agent Contract"
};
}).filter(function (item) {
return Boolean(item.id);
}).sort(function (a, b) {
return a.name.localeCompare(b.name);
});
}
if (state.activeModule === "quality_action") {
return safeArray(state.moduleRecords).map(function (row) {
return {
id: cleanText(row.name),
name: cleanText(row.custom_subject) || cleanText(row.name),
course: "Quality Action"
};
}).filter(function (item) {
return Boolean(item.id);
}).sort(function (a, b) {
return a.name.localeCompare(b.name);
});
}
const map = new Map();
safeArray(state.studentRollRows).forEach(function (row) {
const id = cleanText(row.student_applicant_id);
const name = cleanText(row.student_name);
if (!id || map.has(id)) return;
map.set(id, {
id: id,
name: name || id,
course: cleanText(row.course)
});
});
return Array.from(map.values()).sort(function (a, b) {
return a.name.localeCompare(b.name);
});
}
function availableCourses() {
const courses = new Set();
if (state.activeModule !== "student_journey") {
return [];
}
safeArray(state.studentRollRows).forEach(function (row) {
const course = cleanText(row.course);
if (course) courses.add(course);
});
return Array.from(courses).sort(function (a, b) {
return a.localeCompare(b);
});
}
function renderCourseFilter() {
if (!courseFilter) return;
const selected = courseFilter.value || "";
courseFilter.innerHTML = '<option value="">All courses</option>';
availableCourses().forEach(function (course) {
const option = document.createElement("option");
option.value = course;
option.textContent = course;
courseFilter.appendChild(option);
});
if (selected && availableCourses().includes(selected)) {
courseFilter.value = selected;
}
}
function rememberStudent(id, name) {
if (!id) return;
state.recentStudents = state.recentStudents.filter(function (item) {
return item.id !== id;
});
state.recentStudents.unshift({ id: id, name: name || id });
state.recentStudents = state.recentStudents.slice(0, 5);
saveRecentStudents();
renderRecentStudents();
}
function loadRecentStudents() {
try {
const value = JSON.parse(
window.localStorage.getItem("uccAiRecent_" + state.activeModule) || "[]"
);
state.recentStudents = Array.isArray(value) ? value : [];
} catch (error) {
state.recentStudents = [];
}
}
function saveRecentStudents() {
try {
window.localStorage.setItem(
"uccAiRecent_" + state.activeModule,
JSON.stringify(state.recentStudents)
);
} catch (error) {
console.warn("Could not save recent students", error);
}
}
function removeRecentStudent(id) {
state.recentStudents = state.recentStudents.filter(function (item) {
return item.id !== id;
});
saveRecentStudents();
renderRecentStudents();
}
function renderRecentStudents() {
if (!recentStudents) return;
recentStudents.innerHTML = "";
state.recentStudents.forEach(function (item) {
const row = document.createElement("div");
row.className = "aja-recent-row";
const button = document.createElement("button");
button.type = "button";
button.className = "aja-recent-button";
button.textContent = item.name;
button.dataset.studentApplicant = item.id;
button.dataset.studentName = item.name;
const remove = document.createElement("button");
remove.type = "button";
remove.className = "aja-recent-remove";
remove.textContent = "×";
remove.title = "Remove from recent students";
remove.setAttribute("aria-label", "Remove " + item.name);
remove.dataset.removeStudent = item.id;
row.appendChild(button);
row.appendChild(remove);
recentStudents.appendChild(row);
});
}
function selectStudent(id, name) {
state.studentApplicant = id || "";
state.studentName = name || id || "";
updateCurrentStudent();
updateSuggestionState();
rememberStudent(state.studentApplicant, state.studentName);
}
function renderStudentMatches(query) {
if (!studentMatches) return;
studentMatches.innerHTML = "";
if (studentPager) {
studentPager.innerHTML = "";
}
const value = cleanText(query).toLowerCase();
const selectedCourse = courseFilter
? cleanText(courseFilter.value)
: "";
if (!value && !selectedCourse) return;
if (state.activeModule === "student_journey" && !state.studentRollRows) {
const loading = document.createElement("div");
loading.className = "aja-search-loading";
loading.textContent = "Loading students...";
studentMatches.appendChild(loading);
return;
}
const filtered = uniqueStudentsFromRoll()
.filter(function (item) {
const matchesText = (
!value
|| item.name.toLowerCase().includes(value)
|| item.id.toLowerCase().includes(value)
);
const matchesCourse = (
state.activeModule !== "student_journey"
|| !selectedCourse
|| cleanText(item.course) === selectedCourse
);
return matchesText && matchesCourse;
});
const total = filtered.length;
const pageSize = state.searchPageSize;
const totalPages = Math.max(1, Math.ceil(total / pageSize));
if (state.searchPage > totalPages) {
state.searchPage = totalPages;
}
const startIndex = (state.searchPage - 1) * pageSize;
const pageItems = filtered.slice(startIndex, startIndex + pageSize);
if (!pageItems.length) {
const empty = document.createElement("div");
empty.className = "aja-search-empty";
empty.textContent = "No matching " + activeModuleConfig().entityLabel + " records.";
studentMatches.appendChild(empty);
}
pageItems.forEach(function (item) {
const button = document.createElement("button");
button.type = "button";
button.className = "aja-student-match";
button.dataset.studentApplicant = item.id;
button.dataset.studentName = item.name;
const strong = document.createElement("strong");
strong.textContent = item.name;
const meta = document.createElement("span");
meta.textContent = item.id + " | " + item.course;
button.appendChild(strong);
button.appendChild(meta);
studentMatches.appendChild(button);
});
if (studentPager && total) {
const count = document.createElement("span");
count.className = "aja-pager-count";
count.textContent =
String(startIndex + 1)
+ "-"
+ String(Math.min(startIndex + pageSize, total))
+ " of "
+ String(total);
const controls = document.createElement("div");
controls.className = "aja-pager-controls";
const prev = document.createElement("button");
prev.type = "button";
prev.className = "aja-pager-button";
prev.textContent = "‹";
prev.disabled = state.searchPage <= 1;
prev.dataset.pageAction = "prev";
const next = document.createElement("button");
next.type = "button";
next.className = "aja-pager-button";
next.textContent = "›";
next.disabled = state.searchPage >= totalPages;
next.dataset.pageAction = "next";
controls.appendChild(prev);
controls.appendChild(next);
studentPager.appendChild(count);
studentPager.appendChild(controls);
}
}
function csvEscape(value) {
const text = String(value === null || value === undefined ? "" : value);
return '"' + text.replace(/"/g, '""') + '"';
}
function exportLastResultCsv() {
const sections = safeArray(state.lastExportSections);
if (!sections.length) {
frappe.show_alert({
message: "Run a question with a table or summary before exporting.",
indicator: "orange"
});
return;
}
const lines = [];
sections.forEach(function (section, sectionIndex) {
if (sectionIndex) lines.push("");
lines.push(csvEscape(section.title || "Admission Journey Export"));
safeArray(section.rows).forEach(function (row) {
lines.push(safeArray(row).map(csvEscape).join(","));
});
});
const csv = "\uFEFF" + lines.join("\r\n");
const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
const url = window.URL.createObjectURL(blob);
const link = document.createElement("a");
const studentPart = cleanText(state.studentName || "cohort")
.replace(/[^a-z0-9]+/gi, "-")
.replace(/^-+|-+$/g, "")
.toLowerCase();
link.style.display = "none";
link.href = url;
link.download = "admission-journey-" + (studentPart || "export") + ".csv";
document.body.appendChild(link);
link.click();
window.setTimeout(function () {
document.body.removeChild(link);
window.URL.revokeObjectURL(url);
}, 1000);
frappe.show_alert({
message: "CSV export prepared.",
indicator: "green"
});
}
function scrollBottom() {
window.requestAnimationFrame(function () {
chat.scrollTop = chat.scrollHeight;
});
}
function addUserMessage(text) {
const wrapper = document.createElement("div");
wrapper.className = "aja-message aja-message-user";
const bubble = document.createElement("div");
bubble.className = "aja-user-bubble";
bubble.textContent = text;
wrapper.appendChild(bubble);
chat.appendChild(wrapper);
scrollBottom();
}
function createAssistantBubble() {
const wrapper = document.createElement("div");
wrapper.className = "aja-message aja-message-assistant";
const bubble = document.createElement("div");
bubble.className = "aja-assistant-bubble";
const header = document.createElement("div");
header.className = "aja-assistant-header";
const avatar = document.createElement("div");
avatar.className = "aja-avatar";
avatar.textContent = "AI";
const title = document.createElement("span");
title.textContent =
activeModuleConfig().headerTitle
|| activeModuleConfig().label
|| "UCC AI Assistant";
const content = document.createElement("div");
content.className = "aja-assistant-content";
header.appendChild(avatar);
header.appendChild(title);
bubble.appendChild(header);
bubble.appendChild(content);
wrapper.appendChild(bubble);
chat.appendChild(wrapper);
scrollBottom();
return wrapper;
}
function addLoadingMessage() {
const wrapper = createAssistantBubble();
const content = wrapper.querySelector(".aja-assistant-content");
content.innerHTML = '<div class="aja-loading">Checking ERPNext records...</div>';
return wrapper;
}
function buildUrl(source) {
if (!source || !source.doctype || !source.name) return "";
const slug =
frappe.router && typeof frappe.router.slug === "function"
? frappe.router.slug(source.doctype)
: String(source.doctype)
.toLowerCase()
.replace(/[^a-z0-9]+/g, "-")
.replace(/^-+|-+$/g, "");
return window.location.origin + "/app/" + slug + "/" + encodeURIComponent(source.name);
}
function renderSummary(container, visual) {
const grid = document.createElement("div");
grid.className = "aja-summary-grid";
safeArray(visual.items).forEach(function (item) {
const card = document.createElement("div");
card.className = "aja-summary-card";
const label = document.createElement("div");
label.className = "aja-summary-label";
label.textContent = item.label || "";
const value = document.createElement("div");
value.className = "aja-summary-value";
value.textContent = displayValue(item.value);
card.appendChild(label);
card.appendChild(value);
grid.appendChild(card);
});
container.appendChild(grid);
}
function renderTable(container, visual) {
const wrap = document.createElement("div");
wrap.className = "aja-table-wrap";
const table = document.createElement("table");
table.className = "aja-table";
const thead = document.createElement("thead");
const headRow = document.createElement("tr");
safeArray(visual.columns).forEach(function (column) {
const th = document.createElement("th");
th.textContent = column;
headRow.appendChild(th);
});
thead.appendChild(headRow);
table.appendChild(thead);
const tbody = document.createElement("tbody");
safeArray(visual.rows).forEach(function (row) {
const tr = document.createElement("tr");
safeArray(row).forEach(function (value) {
const td = document.createElement("td");
if (
value
&& typeof value === "object"
&& !Array.isArray(value)
&& value.doctype
&& value.name
) {
const link = document.createElement("a");
link.className = "aja-record-link";
link.href = "/app/"
+ frappe.router.slug(value.doctype)
+ "/"
+ encodeURIComponent(value.name);
link.target = "_blank";
link.rel = "noopener noreferrer";
link.textContent = displayValue(value);
link.title = "Open " + value.doctype + " " + value.name;
td.appendChild(link);
} else {
td.textContent = displayValue(value);
}
tr.appendChild(td);
});
tbody.appendChild(tr);
});
table.appendChild(tbody);
wrap.appendChild(table);
container.appendChild(wrap);
}
function renderSources(container, sources) {
const seen = new Set();
const wrapper = document.createElement("div");
wrapper.className = "aja-source-links";
safeArray(sources).forEach(function (source) {
if (!source || !source.doctype || !source.name) return;
const key = source.doctype + "::" + source.name;
if (seen.has(key)) return;
seen.add(key);
const url = buildUrl(source);
if (!url) return;
const link = document.createElement("a");
link.className = "aja-source-link";
link.href = url;
link.target = "_blank";
link.rel = "noopener noreferrer";
link.title = source.label || source.name;
link.textContent = "Source: " + (source.short_label || source.label || source.name);
wrapper.appendChild(link);
});
if (wrapper.children.length) {
container.appendChild(wrapper);
}
}
function renderTimeline(container, visual) {
const timeline = document.createElement("div");
timeline.className = "aja-timeline";
safeArray(visual.items).forEach(function (item) {
const row = document.createElement("div");
row.className = "aja-timeline-item";
const marker = document.createElement("div");
marker.className = "aja-timeline-marker";
const body = document.createElement("div");
body.className = "aja-timeline-body";
const date = document.createElement("div");
date.className = "aja-timeline-date";
date.textContent = item.date || "Not recorded";
const title = document.createElement("div");
title.className = "aja-timeline-title";
title.textContent = item.title || "";
const description = document.createElement("div");
description.className = "aja-timeline-description";
description.textContent = item.description || "";
body.appendChild(date);
body.appendChild(title);
body.appendChild(description);
row.appendChild(marker);
row.appendChild(body);
timeline.appendChild(row);
});
container.appendChild(timeline);
}
function renderResponse(result) {
state.lastResult = result || null;
state.lastVisualRows = [];
state.lastExportSections = [];
const wrapper = createAssistantBubble();
const content = wrapper.querySelector(".aja-assistant-content");
const answer = document.createElement("div");
answer.className = "aja-answer";
answer.textContent = formatDatesInText(result.answer || "No answer was returned.");
const outOfScope = (
result.confidence === "Not applicable"
|| cleanText(result.answer).toLowerCase().includes("outside the admission journey scope")
|| cleanText(result.answer).toLowerCase().includes("not an admission journey question")
);
if (outOfScope) {
wrapper.classList.add("aja-message-out-of-scope");
answer.innerHTML =
'<span class="aja-out-scope-icon">!</span>'
+ '<span>'
+ frappe.utils.escape_html(
formatDatesInText(result.answer || "This question is outside the Admission Journey scope.")
)
+ '</span>';
}
content.appendChild(answer);
safeArray(result.warnings).forEach(function (warning) {
const box = document.createElement("div");
box.className = "aja-warning";
box.textContent = "Warning: " + formatDatesInText(warning);
content.appendChild(box);
});
safeArray(result.visuals).forEach(function (visual) {
const section = document.createElement("section");
section.className = "aja-visual";
const title = document.createElement("div");
title.className = "aja-visual-title";
title.textContent = visual.title || "Student information";
section.appendChild(title);
if (visual.type === "table" || visual.type === "timeline_table") {
const tableRows = [safeArray(visual.columns)].concat(safeArray(visual.rows));
state.lastVisualRows = tableRows;
state.lastExportSections.push({
title: visual.title || "Table",
rows: tableRows
});
} else if (visual.type === "summary") {
state.lastExportSections.push({
title: visual.title || "Summary",
rows: [["Field", "Value"]].concat(
safeArray(visual.items).map(function (item) {
return [item.label || "", displayValue(item.value)];
})
)
});
}
if (visual.type === "summary") {
renderSummary(section, visual);
} else if (visual.type === "table" || visual.type === "timeline_table") {
renderTable(section, visual);
} else if (visual.type === "timeline") {
renderTimeline(section, visual);
}
content.appendChild(section);
});
renderSources(content, result.sources || result.source_links);
if (result.confidence) {
const confidence = document.createElement("div");
confidence.className = "aja-confidence";
confidence.textContent = "Confidence: " + result.confidence;
content.appendChild(confidence);
}
if (result.diagnostics && Object.keys(result.diagnostics).length) {
const details = document.createElement("details");
details.className = "aja-diagnostic-details";
const summary = document.createElement("summary");
summary.textContent = "Diagnostic details";
const pre = document.createElement("pre");
pre.textContent = JSON.stringify(result.diagnostics, null, 2);
details.appendChild(summary);
details.appendChild(pre);
content.appendChild(details);
}
if (result.ai_used) {
const note = document.createElement("div");
note.className = "aja-ai-note";
note.textContent = "OpenAI interpreted the question. ERPNext supplied the facts.";
content.appendChild(note);
}
if (result.student_applicant || result.agent_contract) {
state.studentApplicant =
result.student_applicant || result.agent_contract;
state.studentName =
result.student_name || result.agent_name || state.studentApplicant;
updateCurrentStudent();
}
scrollBottom();
}
function renderCandidateSelection(result, originalQuestion) {
const wrapper = createAssistantBubble();
const content = wrapper.querySelector(".aja-assistant-content");
const answer = document.createElement("div");
answer.className = "aja-answer";
answer.textContent = result.answer || "More than one student matches. Select the correct student below.";
content.appendChild(answer);
const list = document.createElement("div");
list.className = "aja-candidate-list";
safeArray(result.candidates).forEach(function (candidate) {
const button = document.createElement("button");
button.type = "button";
button.className = "aja-candidate";
button.dataset.studentApplicant = candidate.student_applicant || "";
button.dataset.studentName = candidate.student_name || "";
button.dataset.question = originalQuestion;
const strong = document.createElement("strong");
strong.textContent = candidate.student_name || candidate.student_applicant;
const detail = document.createElement("span");
detail.textContent = [
candidate.student_applicant,
candidate.program,
candidate.student_type
].filter(Boolean).join(" | ");
button.appendChild(strong);
button.appendChild(detail);
list.appendChild(button);
});
content.appendChild(list);
scrollBottom();
}
async function loadRecruitmentAgents() {
if (state.moduleRecords) {
return state.moduleRecords;
}
try {
const response = await frappe.call({
method: "frappe.client.get_list",
args: {
doctype: "Agent Contract",
fields: ["name", "party_name", "personal_id"],
filters: [],
order_by: "modified desc",
limit_page_length: 500
},
freeze: false
});
state.moduleRecords = response && Array.isArray(response.message)
? response.message
: [];
} catch (error) {
console.warn("Recruitment agents could not be loaded", error);
state.moduleRecords = [];
}
return state.moduleRecords;
}
async function loadQualityActions() {
if (state.moduleRecords) {
return state.moduleRecords;
}
try {
const response = await frappe.call({
method: "frappe.client.get_list",
args: {
doctype: "Quality Action",
fields: ["name", "custom_subject", "modified"],
filters: [],
order_by: "modified desc",
limit_page_length: 1000
},
freeze: false
});
state.moduleRecords = response && Array.isArray(response.message)
? response.message
: [];
} catch (error) {
console.warn("Quality Actions could not be loaded", error);
state.moduleRecords = [];
}
return state.moduleRecords;
}
async function loadActiveModuleData() {
if (state.activeModule === "recruitment_agent") {
return loadRecruitmentAgents();
}
if (state.activeModule === "student_journey") {
return loadStudentRollReport();
}
if (state.activeModule === "quality_action") {
return loadQualityActions();
}
return [];
}
async function loadStudentRollReport() {
if (state.studentRollRows) {
return state.studentRollRows;
}
try {
const response = await frappe.call({
method: "frappe.desk.query_report.run",
args: {
report_name: "Student Roll",
filters: {
from_date: "2000-01-01",
to_date: "2100-12-31"
},
ignore_prepared_report: true,
are_default_filters: false
},
freeze: false
});
const message = response ? response.message : null;
state.studentRollRows =
message && Array.isArray(message.result)
? message.result
: [];
} catch (error) {
console.warn("Student Roll report could not be loaded", error);
state.studentRollRows = [];
}
renderCourseFilter();
return state.studentRollRows;
}
async function sendQuestion(question, selectedApplicant, showUserMessage) {
const text = cleanText(question);
if (!text || state.loading) return;
state.loading = true;
state.lastQuestion = text;
sendButton.disabled = true;
setStatus("Checking records", true);
if (showUserMessage !== false) {
addUserMessage(text);
state.history.push({ role: "user", content: text });
}
const loadingMessage = addLoadingMessage();
try {
await loadActiveModuleData();
const moduleConfig = activeModuleConfig();
const selectedRecord = (
selectedApplicant === "__GLOBAL__"
? ""
: (selectedApplicant || state.studentApplicant || "")
);
const requestArgs = {
question: text,
conversation: JSON.stringify(state.history.slice(-20))
};
try {
const sessionKey = window.sessionStorage.getItem("uccAiOpenAIKey") || "";
if (sessionKey) requestArgs.openai_api_key = sessionKey;
} catch (error) {
}
if (state.activeModule === "student_journey") {
requestArgs.student_applicant = selectedRecord;
requestArgs.student_roll_rows = JSON.stringify(state.studentRollRows || []);
} else if (state.activeModule === "recruitment_agent") {
requestArgs.agent_contract = selectedRecord;
} else if (state.activeModule === "quality_action") {
requestArgs.quality_action = selectedRecord;
}
const response = await frappe.call({
method: moduleConfig.apiMethod,
args: requestArgs,
freeze: false
});
loadingMessage.remove();
const result = response && response.message ? response.message : response;
if (result && result.status === "choose_student") {
renderCandidateSelection(result, text);
return;
}
renderResponse(result || {
status: "error",
answer: "No response was returned.",
warnings: [],
visuals: [],
sources: []
});
state.history.push({
role: "assistant",
content: result && result.answer ? result.answer : ""
});
} catch (error) {
loadingMessage.remove();
console.error("Admission Journey Assistant error", error);
renderResponse({
status: "error",
answer: "Unable to retrieve the information.",
warnings: ["Open the browser console for the exact ERPNext error."],
visuals: [],
sources: []
});
} finally {
state.loading = false;
sendButton.disabled = false;
setStatus("Ready", false);
questionInput.focus();
}
}
function resetChatPanel() {
if (!chat) return;
chat.innerHTML = "";
if (comingSoon) {
comingSoon.hidden = true;
comingSoon.innerHTML = "";
chat.appendChild(comingSoon);
}
const welcome = document.createElement("div");
welcome.className = "aja-welcome";
const avatar = document.createElement("div");
avatar.className = "aja-avatar";
avatar.textContent = "AI";
const content = document.createElement("div");
const title = document.createElement("strong");
title.textContent = "Ready to review";
const paragraph = document.createElement("p");
paragraph.textContent = "Select a record, then choose a guided question.";
const example = document.createElement("div");
example.className = "aja-example";
example.textContent = "ERPNext evidence, tables, warnings and AI interpretation will appear here.";
content.appendChild(title);
content.appendChild(paragraph);
content.appendChild(example);
welcome.appendChild(avatar);
welcome.appendChild(content);
chat.appendChild(welcome);
state.history = [];
state.lastQuestion = "";
state.lastResult = null;
state.lastVisualRows = [];
state.lastExportSections = [];
}
function closeApiModal() {
if (apiModal) apiModal.hidden = true;
}
function proceedFreeQuestion(useStoredKey) {
const question = cleanText(pendingFreeQuestion || (questionInput ? questionInput.value : ""));
pendingFreeQuestion = "";
closeApiModal();
if (!question) return;
if (questionInput) questionInput.value = "";
sendQuestion(question, "", true);
}
sendButton.addEventListener("click", function () {
const question = questionInput.value.trim();
if (!question) return;
let hasSessionKey = false;
try {
hasSessionKey = Boolean(window.sessionStorage.getItem("uccAiOpenAIKey"));
} catch (error) {}
if (hasSessionKey || !apiModal) {
questionInput.value = "";
sendQuestion(question, "", true);
return;
}
pendingFreeQuestion = question;
apiModal.hidden = false;
if (apiKeyInput) apiKeyInput.focus();
});
if (apiButton) {
apiButton.addEventListener("click", function () {
pendingFreeQuestion = "";
if (apiModal) apiModal.hidden = false;
if (apiKeyInput) apiKeyInput.focus();
});
}
if (clearChatButton) {
clearChatButton.addEventListener("click", function () {
resetChatPanel();
setStatus("Ready", false);
});
}
if (apiCancel) apiCancel.addEventListener("click", function () {
pendingFreeQuestion = "";
closeApiModal();
});
if (apiSkip) apiSkip.addEventListener("click", function () {
proceedFreeQuestion(false);
});
if (apiConnect) apiConnect.addEventListener("click", function () {
const key = cleanText(apiKeyInput ? apiKeyInput.value : "");
if (!key) {
if (apiKeyInput) apiKeyInput.focus();
return;
}
try {
window.sessionStorage.setItem("uccAiOpenAIKey", key);
} catch (error) {}
if (apiKeyInput) apiKeyInput.value = "";
proceedFreeQuestion(true);
});
function blockGlobalSearch(event) {
const path = event.composedPath ? event.composedPath() : [];
if (!path.includes(questionInput)) return;
event.stopPropagation();
if (event.key === "Enter" && !event.shiftKey) {
event.preventDefault();
sendButton.click();
}
}
["keydown", "keypress", "keyup"].forEach(function (eventName) {
app.addEventListener(eventName, blockGlobalSearch, true);
});
if (studentSearch) {
["click", "mousedown", "keydown", "keyup", "input"].forEach(function (eventName) {
studentSearch.addEventListener(eventName, function (event) {
event.stopPropagation();
});
});
studentSearch.addEventListener("input", function () {
state.searchPage = 1;
renderStudentMatches(studentSearch.value);
});
}
if (courseFilter) {
courseFilter.addEventListener("change", function (event) {
event.stopPropagation();
state.searchPage = 1;
renderStudentMatches(studentSearch ? studentSearch.value : "");
});
}
if (studentPager) {
studentPager.addEventListener("click", function (event) {
const button = event.target.closest(".aja-pager-button");
if (!button) return;
event.preventDefault();
event.stopPropagation();
if (button.dataset.pageAction === "prev" && state.searchPage > 1) {
state.searchPage = state.searchPage - 1;
}
if (button.dataset.pageAction === "next") {
state.searchPage = state.searchPage + 1;
}
renderStudentMatches(studentSearch ? studentSearch.value : "");
});
}
if (studentMatches) {
studentMatches.addEventListener("pointerdown", function (event) {
const button = event.target.closest(".aja-student-match");
if (!button) return;
event.preventDefault();
event.stopPropagation();
selectStudent(
button.dataset.studentApplicant,
button.dataset.studentName
);
studentMatches.innerHTML = "";
studentSearch.value = "";
questionInput.focus();
});
}
if (recentStudents) {
recentStudents.addEventListener("click", function (event) {
const removeButton = event.target.closest(".aja-recent-remove");
if (removeButton) {
event.preventDefault();
event.stopPropagation();
removeRecentStudent(removeButton.dataset.removeStudent || "");
return;
}
const button = event.target.closest(".aja-recent-button");
if (!button) return;
selectStudent(
button.dataset.studentApplicant,
button.dataset.studentName
);
});
}
if (changeStudentButton) {
changeStudentButton.addEventListener("click", function () {
studentSearch.focus();
});
}
if (resetContextButton) {
resetContextButton.addEventListener("click", function () {
state.studentApplicant = "";
state.studentName = "";
state.history = [];
updateCurrentStudent();
setStatus("Context reset", false);
});
}
if (exportCsvButton) {
exportCsvButton.addEventListener("click", exportLastResultCsv);
}
if (diagnosticsButton) {
diagnosticsButton.addEventListener("click", function () {
if (!state.studentApplicant) {
setStatus("Select a student first", false);
return;
}
sendQuestion(
"Show admin diagnostics for this student",
state.studentApplicant,
true
);
});
}
loadRecentStudents();
renderRecentStudents();
printButton.addEventListener("click", function () {
window.print();
});
const studentQuestionMap = {
profile: [
["Student profile", "Show this student's profile"],
["Course", "What course is this student in?"],
["Nationality", "What is this student's nationality?"],
["Commencement", "When did this student start?"],
["Completion", "When is this student completing the course?"]
],
journey: [
["Full timeline", "Show this student's journey"],
["Current module", "Which module is this student in right now?"],
["Class and group", "Show this student's class and student group"],
["Current leave", "Is this student on leave now?"]
],
academic: [
["All results", "Show all this student's results and grades"],
["Module completion", "Has this student finished all modules?"],
["Graduation status", "Has this student graduated?"],
["Results and grades", "Show all this student\'s results and grades"]
],
attendance: [
["Attendance summary", "Show this student's attendance"],
["Current leave", "Is this student on leave now?"],
["Leave history", "Show this student's leave records"]
],
finance: [
["Payment status", "Show this student's fee and payment status"],
["Outstanding fees", "Does this student have outstanding fees?"],
["Invoices", "Show this student's invoices"],
["FPS status", "What is this student's FPS status?"]
],
graduation: [
["Readiness", "Is this student ready to graduate?"],
["Risk summary", "Show this student's risk summary"],
["Follow-up actions", "What follow-up actions are needed for this student?"],
["Admission documents", "Show this student's attached admission documents"]
],
cohort: [
["Cohort dashboard", "Show the cohort dashboard"],
["Class today", "Who are the students in class today?"],
["Graduating this month", "Who is graduating this month?"],
["Graduated months ago", "Who graduated 6 months ago?"],
["Leave count", "How many students are on leave from 15 to 30 August 2026?"]
]
};
const recruitmentQuestionMap = {
profile: [
["Agent profile", "Show this agent's profile"],
["Contract status", "Is this agent's contract active?"],
["Contract dates", "Show this agent's contract dates"]
],
journey: [
["Agent journey", "Show this agent's complete journey"],
["Latest contract", "Show this agent's latest contract"],
["Expiry", "When does this agent's contract expire?"]
],
academic: [
["Students recruited", "How many students did this agent recruit?"],
["Recruitment list", "Show students recruited by this agent"]
],
attendance: [
["Latest rating", "What is this agent's latest rating?"],
["Rating threshold", "Does this agent meet the minimum rating?"]
],
finance: [
["Revenue contribution", "What revenue came from this agent?"],
["Commission status", "Show this agent's commission status"]
],
graduation: [
["Renewal readiness", "Should this agent's contract be renewed?"],
["Compliance issues", "Show this agent's compliance issues"],
["Risk summary", "Show this agent's risk summary"]
],
cohort: [
["Active agents", "How many recruitment agents have active contracts?"],
["Expiring contracts", "Which agent contracts are expiring soon?"]
]
};
const qualityActionQuestionMap = {
profile: [
["Quality Action overview", "Show this Quality Action"],
["Problem", "What is the problem?"],
["Current status", "What is the current status?"]
],
journey: [
["Root cause and resolution", "Show the root cause and resolution"],
["Action taken", "What action has been taken?"],
["Assigned person", "Who is assigned?"]
],
academic: [
["Due date", "When is it due?"],
["Overdue check", "Is it overdue?"],
["Completion status", "What is the current status?"]
],
attendance: [
["Closure readiness", "Is this Quality Action ready for closure?"],
["Quality review", "Run a quality review of the root cause and action taken"],
["Root-cause review", "Assess the root cause and resolution"]
],
finance: [
["Open Quality Actions", "Show all open Quality Actions"],
["Overdue Quality Actions", "Show overdue Quality Actions"]
],
graduation: [
["NC findings", "Show NC findings"],
["OFI findings", "Show OFI findings"]
],
cohort: [
["All open actions", "Show all open Quality Actions"],
["All overdue actions", "Show overdue Quality Actions"],
["All NC findings", "Show NC findings"],
["All OFI findings", "Show OFI findings"]
]
};
function renderCategoryButtons() {
if (!categoryButtons || !categorySelect) return;
categoryButtons.innerHTML = "";
Array.from(categorySelect.options).forEach(function (option) {
const button = document.createElement("button");
button.type = "button";
button.className = "aja-category-button";
button.dataset.value = option.value;
button.textContent = option.textContent;
if (option.value === categorySelect.value) {
button.classList.add("active");
}
button.addEventListener("click", function () {
categorySelect.value = option.value;
categorySelect.dispatchEvent(new Event("change", { bubbles: true }));
});
categoryButtons.appendChild(button);
});
}
function renderControlledQuestions() {
if (!controlledQuestions || !categorySelect) {
return;
}
renderCategoryButtons();
controlledQuestions.innerHTML = "";
const category = categorySelect.value || "profile";
const questionMap = state.activeModule === "recruitment_agent"
? recruitmentQuestionMap
: (
state.activeModule === "quality_action"
? qualityActionQuestionMap
: studentQuestionMap
);
const questions = questionMap[category] || [];
questions.forEach(function (item) {
const button = document.createElement("button");
button.type = "button";
button.className = "aja-suggestion";
button.dataset.question = item[1];
button.textContent = item[0];
controlledQuestions.appendChild(button);
});
}
if (categorySelect) {
categorySelect.addEventListener("change", renderControlledQuestions);
}
suggestionsContainer.addEventListener("click", function (event) {
const button = event.target.closest(".aja-suggestion");
if (!button) return;
const question = button.dataset.question || button.textContent.trim();
const isCohortQuestion = (
categorySelect
&& categorySelect.value === "cohort"
);
if (isCohortQuestion) {
sendQuestion(question, "__GLOBAL__", true);
return;
}
if (state.studentApplicant) {
sendQuestion(question, state.studentApplicant, true);
return;
}
const moduleConfig = activeModuleConfig();
questionInput.value = "";
questionInput.placeholder =
"Enter or select a " + moduleConfig.entityLabel + " first";
questionInput.focus();
setStatus("Select a " + moduleConfig.entityLabel + " first", false);
});
function resetModuleContext() {
state.studentApplicant = "";
state.studentName = "";
state.history = [];
state.lastResult = null;
state.lastVisualRows = [];
state.lastExportSections = [];
state.searchPage = 1;
state.moduleRecords = null;
if (studentSearch) studentSearch.value = "";
if (studentMatches) studentMatches.innerHTML = "";
if (studentPager) studentPager.innerHTML = "";
updateCurrentStudent();
}
function renderCategoryOptions() {
if (!categorySelect) return;
const options = state.activeModule === "recruitment_agent"
? [
["profile", "Profile and Contract"],
["journey", "Agent Journey"],
["academic", "Recruitment Performance"],
["attendance", "Ratings"],
["finance", "Revenue and Commission"],
["graduation", "Compliance and Renewal"],
["cohort", "Agent Portfolio"]
]
: (
state.activeModule === "quality_action"
? [
["profile", "Overview"],
["journey", "Root Cause and Action"],
["academic", "Status and Due Dates"],
["attendance", "Review and Closure"],
["finance", "Open and Overdue"],
["graduation", "Finding Types"],
["cohort", "Quality Action Portfolio"]
]
: [
["profile", "Profile"],
["journey", "Student Journey"],
["academic", "Academic and Results"],
["attendance", "Attendance and Leave"],
["finance", "Fees and Payments"],
["graduation", "Graduation and Risk"],
["cohort", "Cohort Questions"]
]
);
categorySelect.innerHTML = "";
options.forEach(function (item) {
const option = document.createElement("option");
option.value = item[0];
option.textContent = item[1];
categorySelect.appendChild(option);
});
}
async function applyModule(moduleId) {
state.activeModule = moduleId || "student_journey";
resetModuleContext();
const config = activeModuleConfig();
if (pinnedLabel) pinnedLabel.textContent = config.pinnedLabel || "Pinned record";
if (findLabel) findLabel.textContent = config.findLabel || "Find record";
if (recentLabel) recentLabel.textContent = config.recentLabel || "Recent records";
if (studentSearch) studentSearch.placeholder = config.searchPlaceholder || "Type to search";
if (headerTitle) headerTitle.textContent = config.headerTitle || config.label;
if (headerSubtitle) headerSubtitle.textContent = config.headerSubtitle || "";
if (moduleStatus) {
moduleStatus.textContent = config.comingSoon
? config.label + " is coming soon."
: config.label + " is active.";
}
if (courseFilter) {
courseFilter.hidden = state.activeModule !== "student_journey";
}
if (comingSoon) {
comingSoon.hidden = !config.comingSoon;
comingSoon.textContent = config.comingSoon
? config.label + " is planned for a future version."
: "";
}
if (questionInput) questionInput.disabled = Boolean(config.comingSoon);
if (sendButton) sendButton.disabled = Boolean(config.comingSoon);
if (suggestionsContainer) suggestionsContainer.hidden = Boolean(config.comingSoon);
renderCategoryOptions();
renderControlledQuestions();
if (!config.comingSoon) {
setStatus("Loading " + config.entityLabel + " records", true);
await loadActiveModuleData();
renderCourseFilter();
setStatus("Ready", false);
} else {
setStatus("Coming soon", false);
}
}
if (moduleSelect) {
moduleSelect.addEventListener("change", function () {
applyModule(moduleSelect.value);
});
}
renderControlledQuestions();
applyModule("student_journey");
updateCurrentStudent();
updateSuggestionState();
})();
(function(){
"use strict";
const root=typeof root_element!=="undefined"
?root_element.querySelector("#uccIntelligencePlatform")
:document.querySelector("#uccIntelligencePlatform");
if(!root||root.dataset.v110Ready==="1")return;
root.dataset.v110Ready="1";
const STORAGE_KEY="ucc-intelligence-platform-v1.2.0-view";
const $=(selector,scope=root)=>scope.querySelector(selector);
const $$=(selector,scope=root)=>Array.from(scope.querySelectorAll(selector));
function notify(message,indicator="blue"){
if(window.frappe&&frappe.show_alert)frappe.show_alert({message,indicator},5);
else console.info("[UCC]",message);
}
function visiblePanel(){
return $$(".panel-view").find(panel=>!panel.classList.contains("hidden")&&panel.offsetParent!==null)
|| $$(".panel-view").find(panel=>!panel.classList.contains("hidden"));
}
function activeTable(){
const panel=visiblePanel()||root;
return $$("table",panel).find(table=>table.offsetParent!==null)||$("table",panel);
}
const csvCell=UCCShared.csvCell;
function tableToCsv(table){return UCCShared.tableToCsv(table);}
function download(name,content,type="text/csv;charset=utf-8"){return UCCShared.download(name,content,type);}
function exportCurrentTable(){
const table=activeTable();
if(!table){notify("No visible table to export.","orange");return}
download("ucc-current-table.csv",tableToCsv(table));
}
function exportExceptions(){
const panel=visiblePanel()||root;
const candidate=$$("table",panel).find(table=>/exception|gap|risk|attention/i.test(table.closest(".panel")?.innerText||""));
if(!candidate){notify("No visible exception table in this view.","orange");return}
download("ucc-current-exceptions.csv",tableToCsv(candidate));
}
function selectedState(){
const selected={};
const activeMain=$(".tabs [data-tab].active");
const activeLocal=$(".section-local-tabs [data-local-tab].active");
const activeWorkspace=$("[data-ucc-workspace].is-active");
if(activeMain)selected.tab=activeMain.dataset.tab;
if(activeLocal)selected.localTab=activeLocal.dataset.localTab;
if(activeWorkspace)selected.workspace=activeWorkspace.dataset.uccWorkspace;
selected.filters={};
$$("[data-filter]").forEach(el=>selected.filters[el.dataset.filter]=el.value);
return selected;
}
function saveState(){
try{localStorage.setItem(STORAGE_KEY,JSON.stringify(selectedState()))}catch(e){console.warn("[UCC] state persistence unavailable",e)}
}
function copyFilteredLink(){
const state=selectedState(),url=new URL(location.href);
if(state.tab)url.searchParams.set("ucc_tab",state.tab);
if(state.localTab)url.searchParams.set("ucc_subpage",state.localTab);
Object.entries(state.filters).forEach(([key,value])=>{if(value)url.searchParams.set("ucc_"+key,value);else url.searchParams.delete("ucc_"+key)});
const value=url.toString();
const copy=navigator.clipboard?.writeText?navigator.clipboard.writeText(value):Promise.reject();
copy.then(()=>notify("Filtered link copied.","green")).catch(()=>{
const input=document.createElement("textarea");input.value=value;document.body.appendChild(input);input.select();document.execCommand("copy");input.remove();notify("Filtered link copied.","green")
});
}
root.addEventListener("click",event=>{
const action=event.target.closest("[data-universal-action]")?.dataset.universalAction;
if(action==="export-table")exportCurrentTable();
if(action==="export-exceptions")exportExceptions();
if(action==="copy-link")copyFilteredLink();
if(event.target.closest("[data-tab],[data-local-tab],[data-ucc-workspace]"))setTimeout(saveState,20);
});
root.addEventListener("change",event=>{if(event.target.matches("[data-filter],select,input"))saveState()});
function restoreState(){
let stored={};
try{stored=JSON.parse(localStorage.getItem(STORAGE_KEY)||"{}")}catch{}
const url=new URL(location.href);
const tab=url.searchParams.get("ucc_tab")||stored.tab;
const localTab=url.searchParams.get("ucc_subpage")||stored.localTab;
const workspace=stored.workspace;
if(workspace)$(`[data-ucc-workspace="${CSS.escape(workspace)}"]`)?.click();
if(tab)$(`[data-tab="${CSS.escape(tab)}"]`)?.click();
setTimeout(()=>{if(localTab)$(`[data-local-tab="${CSS.escape(localTab)}"]`)?.click()},80);
$$("[data-filter]").forEach(el=>{
const value=url.searchParams.get("ucc_"+el.dataset.filter)??stored.filters?.[el.dataset.filter];
if(value!==undefined&&value!==null&&Array.from(el.options||[]).some(o=>o.value===value))el.value=value;
});
}
function ensureChartToggles(){
$$("[data-chart]").forEach(chart=>{
const panel=chart.closest(".panel");if(!panel)return;
chart.classList.add("ucc-clickable-result");
const key=chart.dataset.chart;
if(panel.querySelector("[data-card-toggle]"))return;
const table=$(`[data-table="${CSS.escape(key)}"]`)?.closest(".table-wrap");
if(!table)return;
const head=$(".panel-head",panel)||$("h2",panel)?.parentElement;
if(!head||$(`[data-auto-toggle="${CSS.escape(key)}"]`,panel))return;
const wrap=document.createElement("div");
wrap.className="mini-toggle";wrap.dataset.autoToggle=key;
wrap.innerHTML='<button type="button" class="active" data-auto-view="diagram">Diagram</button><button type="button" data-auto-view="table">Table</button>';
head.appendChild(wrap);
table.classList.add("ucc-hidden");
wrap.addEventListener("click",event=>{
const button=event.target.closest("[data-auto-view]");if(!button)return;
$$("button",wrap).forEach(x=>x.classList.toggle("active",x===button));
chart.classList.toggle("ucc-hidden",button.dataset.autoView==="table");
table.classList.toggle("ucc-hidden",button.dataset.autoView==="diagram");
});
});
}
function classifyEmptyStates(){
$$("[data-table] tr td:only-child,.empty-state,.source-empty").forEach(node=>{
const text=node.textContent.toLowerCase();
let type="no-data",title="No matching data";
if(/permission|not permitted|403/.test(text)){type="permission";title="Permission denied"}
else if(/unavailable|missing doctype|source not/.test(text)){type="unavailable";title="Source unavailable"}
else if(/unsupported|missing field|unknown column/.test(text)){type="unsupported";title="Unsupported or missing fields"}
if(node.closest(".ucc-empty-state"))return;
node.classList.add("ucc-empty-state");node.dataset.state=type;
if(!node.querySelector("strong"))node.innerHTML="<strong>"+title+"</strong>"+node.innerHTML;
});
}
function makeCountsClickable(){
$$("[data-kpi],[data-new-kpi],.kpis strong").forEach(node=>{
node.classList.add("ucc-clickable-result");node.tabIndex=0;
const activate=()=>{
const card=node.closest("article"),label=card?.querySelector("span")?.textContent||"Result";
const panel=visiblePanel(),table=panel&&$("table",panel);
if(table){table.scrollIntoView({behavior:"smooth",block:"center"});notify(label+": review the visible drill-down table.","blue")}
};
node.addEventListener("click",activate);
node.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" ")activate()});
});
}
function makeTableRowsDrillable(){
$$("tbody tr").forEach(row=>{
if(row.dataset.v110Drill==="1")return;row.dataset.v110Drill="1";
row.classList.add("ucc-clickable-result");
row.addEventListener("dblclick",()=>row.querySelector("a.open-record-link")?.click());
});
}
const observer=new MutationObserver(()=>{ensureChartToggles();classifyEmptyStates();makeCountsClickable();makeTableRowsDrillable()});
observer.observe(root,{childList:true,subtree:true});
setTimeout(()=>{restoreState();ensureChartToggles();classifyEmptyStates();makeCountsClickable();makeTableRowsDrillable()},250);
})();
/* Criterion 4 now uses the shared response adapter and chart plugin registry. */

/* UCC placeholder dashboard tab controls */
(function () {
"use strict";

const root = typeof root_element !== "undefined"
? root_element.querySelector("#uccIntelligencePlatform")
: document.querySelector("#uccIntelligencePlatform");

if (!root || root.dataset.placeholderControlsReady === "1") return;
root.dataset.placeholderControlsReady = "1";

root.addEventListener("click", function (event) {
const tab = event.target.closest("[data-ucc-placeholder-tab]");
if (!tab) return;
const dashboard = tab.closest("[data-dashboard-panel]");
if (!dashboard) return;
const key = tab.dataset.uccPlaceholderTab;
dashboard.querySelectorAll("[data-ucc-placeholder-tab]").forEach(function (button) {
button.classList.toggle("is-active", button === tab);
});
dashboard.querySelectorAll("[data-ucc-placeholder-panel]").forEach(function (panel) {
const active = panel.dataset.uccPlaceholderPanel === key;
panel.hidden = !active;
panel.classList.toggle("is-active", active);
});
});
})();
/* UCC unified dashboard engine v2.0.1 */
(function(){
"use strict";
const platform=typeof root_element!=="undefined"?root_element.querySelector("#uccIntelligencePlatform"):document.querySelector("#uccIntelligencePlatform");
if(!platform||platform.dataset.liveFoundationReady==="1")return;
platform.dataset.liveFoundationReady="1";
const CONFIG={"criterion_1":{"number":"1","title":"Leadership and Strategic Planning","description":"Live, permission-aware analytics foundation for leadership, governance and strategic planning. Source and metric availability is resolved from ERPNext permissions.","subcriteria":[["1.1.1","Leadership and Corporate Governance"],["1.2.1","Strategic Planning"]],"sections":{"overview":{"title":"Overview","charts":[{"id":"criterion_1-overview-targets","title":"Target Gap Summary","type":"bar"},{"id":"criterion_1-overview-sources","title":"Source Availability","type":"donut"}]},"1.1":{"title":"Leadership and Corporate Governance","charts":[{"id":"criterion_1-11-coverage","title":"Leadership and Corporate Governance Control Coverage","type":"bar"},{"id":"criterion_1-11-status","title":"Leadership and Corporate Governance Status Distribution","type":"donut"}]},"1.2":{"title":"Strategic Planning","charts":[{"id":"criterion_1-12-coverage","title":"Strategic Planning Control Coverage","type":"bar"},{"id":"criterion_1-12-status","title":"Strategic Planning Status Distribution","type":"donut"}]},"1.1.1":{"title":"Leadership and Corporate Governance","charts":[{"id":"criterion_1-11-coverage","title":"Leadership and Corporate Governance Control Coverage","type":"bar"},{"id":"criterion_1-11-status","title":"Leadership and Corporate Governance Status Distribution","type":"donut"}]},"1.2.1":{"title":"Strategic Planning","charts":[{"id":"criterion_1-12-coverage","title":"Strategic Planning Control Coverage","type":"bar"},{"id":"criterion_1-12-status","title":"Strategic Planning Status Distribution","type":"donut"}]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_1","defaultSection":"1.1.1","apiSections":{"overview":"1.1.1","1.1.1":"1.1.1","1.2.1":"1.2.1","quality":"1.1.1","sources":"1.1.1"},"panelMap":{"overview":"overview","1.1.1":"1.1.1","1.2.1":"1.2.1","sources":"sources","quality":"sources"},"filters":[["academic_year","Academic Year",["All Academic Years","2026","2025"]],["student_group","Module Class Details",["All Module Classes"]],["program","Course",["All Courses"]],{"key":"month","label":"Month","type":"month"}]},"criterion_2":{"number":"2","title":"Corporate Administration","description":"Live, permission-aware analytics foundation for human resources, communication, knowledge management and feedback. Unsupported fields are shown explicitly.","subcriteria":[["2.1.1","Staff Selection and Management"],["2.1.2","Staff Training and Development"],["2.2.1","Internal and External Communication"],["2.3.1","Data and Information Management"],["2.3.2","Knowledge Management"],["2.4.1","Feedback Management"],["2.4.2","Student Satisfaction Survey"],["2.4.3","Staff Satisfaction Survey"]],"sections":{"overview":{"title":"Overview","charts":[{"id":"criterion_2-overview-targets","title":"Target Gap Summary","type":"bar"},{"id":"criterion_2-overview-sources","title":"Source Availability","type":"donut"}]},"2.1":{"title":"Human Resource","charts":[{"id":"criterion_2-21-coverage","title":"Human Resource Control Coverage","type":"bar"},{"id":"criterion_2-21-status","title":"Human Resource Status Distribution","type":"donut"}]},"2.2":{"title":"Communication","charts":[{"id":"criterion_2-22-coverage","title":"Communication Control Coverage","type":"bar"},{"id":"criterion_2-22-status","title":"Communication Status Distribution","type":"donut"}]},"2.3":{"title":"Data, Information and Knowledge Management","charts":[{"id":"criterion_2-23-coverage","title":"Data, Information and Knowledge Management Control Coverage","type":"bar"},{"id":"criterion_2-23-status","title":"Data, Information and Knowledge Management Status Distribution","type":"donut"}]},"2.4":{"title":"Feedback Management","charts":[{"id":"criterion_2-24-coverage","title":"Feedback Management Control Coverage","type":"bar"},{"id":"criterion_2-24-status","title":"Feedback Management Status Distribution","type":"donut"}]},"2.1.1":{"title":"Human Resource","charts":[{"id":"criterion_2-21-coverage","title":"Human Resource Control Coverage","type":"bar"},{"id":"criterion_2-21-status","title":"Human Resource Status Distribution","type":"donut"}]},"2.1.2":{"title":"Staff Training and Development","charts":[{"id":"criterion_2-21-coverage","title":"Human Resource Control Coverage","type":"bar"},{"id":"criterion_2-21-status","title":"Human Resource Status Distribution","type":"donut"}]},"2.2.1":{"title":"Communication","charts":[{"id":"criterion_2-22-coverage","title":"Communication Control Coverage","type":"bar"},{"id":"criterion_2-22-status","title":"Communication Status Distribution","type":"donut"}]},"2.3.1":{"title":"Data, Information and Knowledge Management","charts":[{"id":"criterion_2-23-coverage","title":"Data, Information and Knowledge Management Control Coverage","type":"bar"},{"id":"criterion_2-23-status","title":"Data, Information and Knowledge Management Status Distribution","type":"donut"}]},"2.3.2":{"title":"Knowledge Management","charts":[{"id":"criterion_2-23-coverage","title":"Data, Information and Knowledge Management Control Coverage","type":"bar"},{"id":"criterion_2-23-status","title":"Data, Information and Knowledge Management Status Distribution","type":"donut"}]},"2.4.1":{"title":"Feedback Management","charts":[{"id":"criterion_2-24-coverage","title":"Feedback Management Control Coverage","type":"bar"},{"id":"criterion_2-24-status","title":"Feedback Management Status Distribution","type":"donut"}]},"2.4.2":{"title":"Student Satisfaction Survey","charts":[{"id":"criterion_2-24-coverage","title":"Feedback Management Control Coverage","type":"bar"},{"id":"criterion_2-24-status","title":"Feedback Management Status Distribution","type":"donut"}]},"2.4.3":{"title":"Staff Satisfaction Survey","charts":[{"id":"criterion_2-24-coverage","title":"Feedback Management Control Coverage","type":"bar"},{"id":"criterion_2-24-status","title":"Feedback Management Status Distribution","type":"donut"}]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_2","defaultSection":"2.1.1","apiSections":{"overview":"2.1.1","2.1.1":"2.1.1","2.1.2":"2.1.2","2.2.1":"2.2.1","2.3.1":"2.3.1","2.3.2":"2.3.2","2.4.1":"2.4.1","2.4.2":"2.4.2","2.4.3":"2.4.3","quality":"2.1.1","sources":"2.1.1"},"panelMap":{"overview":"overview","2.1.1":"2.1.1","2.1.2":"2.1.2","2.2.1":"2.2.1","2.3.1":"2.3.1","2.3.2":"2.3.2","2.4.1":"2.4.1","2.4.2":"2.4.2","2.4.3":"2.4.3","sources":"sources","quality":"sources"},"filters":[["academic_year","Academic Year",["All Academic Years","2026","2025"]],["student_group","Module Class Details",["All Module Classes"]],["program","Course",["All Courses"]],{"key":"month","label":"Month","type":"month"}]},"criterion_3":{"number":"3","title":"External Recruitment Agents","description":"Policy-aligned live analytics foundation for agent selection, appointment, onboarding, performance evaluation, renewal and offboarding. Unsupported fields are shown explicitly.","policy_set":[{"code":"PPD-SES-SL-3.1.1","version":"1.2","title":"Selection and Appointment of External Recruitment Agents","updated":"15 January 2026"},{"code":"PPD-SES-SL-3.2.1","version":"1.2","title":"Management and Evaluation of Recruitment Agents","updated":"15 January 2026"}],"subcriteria":[["3.1.1","Selection and Appointment"],["3.2.1","Management and Evaluation"]],"filters":[["review_year","Review Year",["All Review Years","2026","2025"]],["agent_status","Agent Status",["All Agent Statuses","Active","Pending","Inactive"]],["market","Market / Region",["All Markets","Southeast Asia","South Asia","Greater China","Other"]],["renewal_cycle","Renewal Cycle",["All Renewal Cycles","June","December"]]],"sections":{"overview":{"title":"Criterion 3 Overview","charts":[{"id":"c3-overview-lifecycle","title":"Agent Lifecycle Coverage","type":"lifecycle"},{"id":"c3-overview-policy","title":"Policy Control Coverage","type":"donut"},{"id":"c3-overview-health","title":"Agent Control Health","type":"radar"},{"id":"c3-overview-renewal","title":"Renewal and Evaluation Trend","type":"trend"},{"id":"c3-overview-exceptions","title":"Open Exception Profile","type":"bar"}]},"3.1.1":{"title":"Selection and Appointment of External Recruitment Agents","charts":[{"id":"c311-identification","title":"Identification Pathways","type":"donut"},{"id":"c311-screening","title":"Selection and Screening Funnel","type":"funnel"},{"id":"c311-weighting","title":"Selection Criteria Weighting","type":"radar"},{"id":"c311-score","title":"Selection Score Distribution","type":"bar"},{"id":"c311-approval","title":"Approval and Background Check","type":"lifecycle"},{"id":"c311-contract","title":"Contract and NDA Readiness","type":"matrix"},{"id":"c311-listing","title":"Agent Listing and Status","type":"donut"}]},"3.2.1":{"title":"Management and Evaluation of Recruitment Agents","charts":[{"id":"c321-onboarding","title":"Agent Onboarding Funnel","type":"funnel"},{"id":"c321-training","title":"Training Coverage","type":"radar"},{"id":"c321-service","title":"Service Delivery Controls","type":"matrix"},{"id":"c321-evaluation","title":"Performance Evaluation Distribution","type":"bar"},{"id":"c321-renewal","title":"Renewal Checkpoint Flow","type":"lifecycle"},{"id":"c321-complaints","title":"Complaints and Breaches","type":"donut"},{"id":"c321-offboarding","title":"Offboarding and Exit Security","type":"flow"}]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_3","defaultSection":"3.1.1","apiSections":{"overview":"3.1.1","3.1.1":"3.1.1","3.2.1":"3.2.1","quality":"3.1.1","sources":"3.1.1"},"panelMap":{"overview":"overview","3.1.1":"3.1.1","3.2.1":"3.2.1","sources":"sources","quality":"sources"}},"criterion_4":{"number":"4","title":"Student Protection and Support Services","description":"Live, permission-aware analytics for admissions, contracts, fees, student movement, refunds, student support, conduct and attendance.","subcriteria":[["4.1.1","Pre-Course Counselling, Selection and Admissions"],["4.2.1","Student Contract"],["4.2.2","Fee Collection and Fee Protection Scheme"],["4.3.1","Course Transfer, Deferment and Withdrawal"],["4.4.1","Refund"],["4.5.1","Student Support Services"],["4.6.1","Student Conduct and Attendance"]],"filters":[["academic_year","Academic Year",["All Academic Years"]],["program","Programme",["All Programmes"]],["intake","Intake",["All Intakes"]],["status","Status",["All Statuses"]],["nationality","Country / Nationality",["All Countries"]],["agent","Recruitment Agent",["All Agents"]]],"sections":{"overview":{"title":"Overview","charts":[]},"4.1.1":{"title":"Pre-Course Counselling, Selection and Admissions","charts":[]},"4.2.1":{"title":"Student Contract","charts":[]},"4.2.2":{"title":"Fee Collection and Fee Protection Scheme","charts":[]},"4.3.1":{"title":"Course Transfer, Deferment and Withdrawal","charts":[]},"4.4.1":{"title":"Refund","charts":[]},"4.5.1":{"title":"Student Support Services","charts":[]},"4.6.1":{"title":"Student Conduct and Attendance","charts":[]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_4","defaultSection":"4.1.1","apiSections":{"overview":"4.1.1","4.1.1":"4.1.1","4.2.1":"4.2.1","4.2.2":"4.2.2","4.3.1":"4.3.1","4.4.1":"4.4.1","4.5.1":"4.5.1","4.6.1":"4.6.1","quality":"4.1.1","sources":"4.1.1"},"panelMap":{"overview":"overview","4.1.1":"4.1.1","4.2.1":"4.2.1","4.2.2":"4.2.2","4.3.1":"4.3.1","4.4.1":"4.4.1","4.5.1":"4.5.1","4.6.1":"4.6.1","sources":"sources","quality":"sources"}},"criterion_5":{"number":"5","title":"Academic Systems and Processes","description":"Live, permission-aware analytics for course design, review, planning, delivery, partnerships, student feedback, learning support and assessment.","subcriteria":[["5.1.1","Course Design and Development"],["5.1.2","Course Review"],["5.2.1","Course Planning"],["5.2.2","Course Delivery"],["5.3.1","Partnership Management"],["5.4","Student Feedback and Learning Support"],["5.5","Assessment"]],"sections":{"overview":{"title":"Overview","charts":[{"id":"c5-overview-readiness","title":"Academic System Readiness","type":"bar","description":"Compares the live academic-system metrics returned for the selected Criterion 5 area.","i":0},{"id":"c5-overview-availability","title":"Source Availability","type":"donut","description":"Shows readable sources, source issues, readable metrics and metric issues.","i":1},{"id":"c5-overview-health","title":"Criterion 5 System Health","type":"matrix","description":"Summarises available metrics, unavailable metrics, sources and exceptions.","i":2},{"id":"c5-overview-exceptions","title":"Criterion 5 Exception Profile","type":"funnel","description":"Highlights live exceptions that require academic or data-quality follow-up.","i":3}]},"5.1.1":{"title":"Course Design and Development","charts":[{"id":"c5-511-coverage","title":"Course Design Control Coverage","type":"bar","description":"Compares course proposal, module design, programme mapping and assessment-plan evidence.","i":0},{"id":"c5-511-status","title":"Course Design Status Distribution","type":"donut","description":"Shows available design metrics, source readiness and exceptions.","i":1},{"id":"c5-511-readiness","title":"Course Design Evidence Readiness","type":"radar","description":"Compares readiness across the main course design and development controls.","i":2},{"id":"c5-511-gaps","title":"Course Design Gap Profile","type":"funnel","description":"Highlights course design controls that require follow-up.","i":3}]},"5.1.2":{"title":"Course Review","charts":[{"id":"c5-512-coverage","title":"Course Review Control Coverage","type":"bar","description":"Compares module review, course review, approval and recommendation evidence.","i":0},{"id":"c5-512-status","title":"Course Review Status Distribution","type":"donut","description":"Shows review source and metric readiness.","i":1},{"id":"c5-512-cycle","title":"Course Review Lifecycle","type":"lifecycle","description":"Follows review evidence from recorded through approval and recommendation follow-up.","i":2},{"id":"c5-512-gaps","title":"Review Exception Profile","type":"funnel","description":"Highlights overdue or incomplete review controls.","i":3}]},"5.2.1":{"title":"Course Planning","charts":[{"id":"c5-521-coverage","title":"Course Planning Control Coverage","type":"bar","description":"Compares intake, module class, schedule and student-contract planning evidence.","i":0},{"id":"c5-521-status","title":"Course Planning Status Distribution","type":"donut","description":"Shows planning source and metric readiness.","i":1},{"id":"c5-521-flow","title":"Planning Readiness Flow","type":"lifecycle","description":"Follows planning evidence from intake through class, schedule and contract readiness.","i":2},{"id":"c5-521-gaps","title":"Planning Exception Profile","type":"funnel","description":"Highlights incomplete planning controls requiring follow-up.","i":3}]},"5.2.2":{"title":"Course Delivery","charts":[{"id":"c5-522-coverage","title":"Course Delivery Control Coverage","type":"bar","description":"Compares schedules, attendance, observations and sign-off evidence.","i":0},{"id":"c5-522-status","title":"Course Delivery Status Distribution","type":"donut","description":"Shows delivery source and metric readiness.","i":1},{"id":"c5-522-readiness","title":"Delivery Evidence Readiness","type":"radar","description":"Compares attendance, observation and sign-off evidence across delivery controls.","i":2},{"id":"c5-522-gaps","title":"Delivery Exception Profile","type":"funnel","description":"Highlights delivery controls requiring follow-up.","i":3}]},"5.3.1":{"title":"Partnerships","charts":[{"id":"c5-531-coverage","title":"Partnership Control Coverage","type":"bar","description":"Compares agreement, monitoring, evaluation and provider-rating evidence.","i":0},{"id":"c5-531-status","title":"Partnership Status Distribution","type":"donut","description":"Shows partnership source and metric readiness.","i":1},{"id":"c5-531-risk","title":"Partnership Risk Profile","type":"funnel","description":"Highlights expiry, NDA and threshold risks requiring follow-up.","i":2},{"id":"c5-531-readiness","title":"Partnership Evidence Readiness","type":"matrix","description":"Grids readiness across partnership management controls.","i":3}]},"5.4":{"title":"Student Feedback and Learning Support","charts":[{"id":"c5-54-coverage","title":"Student Feedback Control Coverage","type":"bar","description":"Compares survey, score and attendance-risk evidence.","i":0},{"id":"c5-54-status","title":"Student Feedback Status Distribution","type":"donut","description":"Shows feedback source and metric readiness.","i":1},{"id":"c5-54-readiness","title":"Feedback Evidence Readiness","type":"radar","description":"Compares survey and learning-support evidence across key controls.","i":2},{"id":"c5-54-gaps","title":"Feedback Exception Profile","type":"funnel","description":"Highlights feedback controls requiring follow-up.","i":3}]},"5.5":{"title":"Assessment","charts":[{"id":"c5-55-coverage","title":"Assessment Control Coverage","type":"bar","description":"Compares assessment plans, control fields, results, grades and scores.","i":0},{"id":"c5-55-status","title":"Assessment Status Distribution","type":"donut","description":"Shows assessment source and metric readiness.","i":1},{"id":"c5-55-readiness","title":"Assessment Evidence Readiness","type":"radar","description":"Compares readiness across assessment planning and result controls.","i":2},{"id":"c5-55-gaps","title":"Assessment Exception Profile","type":"funnel","description":"Highlights assessment controls requiring correction or follow-up.","i":3}]},"quality":{"title":"Sources and Data Quality","charts":[]},"sources":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_5","defaultSection":"5.1.1","apiSections":{"overview":"5.1.1","5.1.1":"5.1.1","5.1.2":"5.1.2","5.2.1":"5.2.1","5.2.2":"5.2.2","5.3.1":"5.3.1","5.4":"5.4","5.5":"5.5","quality":"5.1.1","sources":"5.1.1"},"panelMap":{"overview":"overview","5.1.1":"5.1.1","5.1.2":"5.1.2","5.2.1":"5.2.1","5.2.2":"5.2.2","5.3.1":"5.3.1","5.4":"5.4","5.5":"5.5","sources":"sources","quality":"sources"},"filters":[["year","Academic Year",["All Academic Years"]],["student_group","Module Class Details",["All Module Classes"]],["program","Course",["All Courses"]],["status","Status",["All Statuses"]]]},"criterion_6":{"number":"6","title":"Quality Assurance, Innovation and Continual Improvement","description":"Policy-aligned live analytics foundation for audits, management review, innovation, providers, risk and business continuity. Unsupported fields are shown explicitly.","policy_set":[{"code":"PPD-SGL-SQ-6.1.1","version":"1.2","title":"Internal Assessment and Quality Audits","updated":"15 January 2026"},{"code":"PPD-SGL-SQ-6.2.1","version":"1.3","title":"Management Review","updated":"10 April 2026"},{"code":"PPD-SGL-SQ-6.3.1","version":"1.2","title":"Innovation and Continual Improvement","updated":"15 January 2026"},{"code":"PPD-OE-FN-6.4.1","version":"1.2","title":"Provider's Accreditation and Evaluation","updated":"15 January 2026"},{"code":"PPD-SGL-SQ-6.5.3","version":"1.2","title":"Hazard Identification and Risk Assessment","updated":"15 January 2026"}],"subcriteria":[["6.1.1","Internal Assessment and Quality Audits"],["6.2.1","Management Review"],["6.3.1","Innovation and Continual Improvement"],["6.4.1","Provider Accreditation and Evaluation"],["6.5.3","Hazard Identification and Risk Assessment"]],"filters":[["review_year","Review Year",["All Review Years","2026","2025"]],["department","Department",["All Departments","SGL / SQ","Academic","Student Services","Finance"]],["quality_area","Quality Area",["All Quality Areas","Audit","Management Review","Innovation","Providers","Risk"]],["month","Month",["All Months","January 2026","April 2026","July 2026","December 2026"]]],"sections":{"overview":{"title":"Criterion 6 Overview","charts":[{"id":"c6-overview-cycle","title":"Quality Management Cycle","type":"lifecycle"},{"id":"c6-overview-policy","title":"Policy Evidence Coverage","type":"donut"},{"id":"c6-overview-health","title":"Quality System Health","type":"radar"},{"id":"c6-overview-calendar","title":"Quality Calendar Completion","type":"trend"},{"id":"c6-overview-actions","title":"Action Status","type":"bar"},{"id":"c6-overview-readiness","title":"Source Readiness","type":"matrix"}]},"6.1.1":{"title":"Internal Assessment and Quality Audits","charts":[{"id":"c611-programme","title":"Annual Audit Programme","type":"donut"},{"id":"c611-scope","title":"Audit Scope Coverage","type":"radar"},{"id":"c611-lifecycle","title":"Audit Lifecycle","type":"funnel"},{"id":"c611-auditors","title":"Auditor Qualification and Independence","type":"matrix"},{"id":"c611-findings","title":"Audit Findings by Severity","type":"bar"},{"id":"c611-cap","title":"Corrective Action Closure","type":"trend"}]},"6.2.1":{"title":"Management Review","charts":[{"id":"c621-thesis","title":"THESIS Review Coverage","type":"radar"},{"id":"c621-preparation","title":"Management Review Preparation","type":"funnel"},{"id":"c621-inputs","title":"Review Input Completeness","type":"matrix"},{"id":"c621-outputs","title":"Review Outputs","type":"donut"},{"id":"c621-ageing","title":"Action Ageing","type":"bar"},{"id":"c621-effectiveness","title":"Action Effectiveness","type":"trend"}]},"6.3.1":{"title":"Innovation and Continual Improvement","charts":[{"id":"c631-types","title":"Innovation Type Mix","type":"donut"},{"id":"c631-lifecycle","title":"Improvement Initiative Lifecycle","type":"funnel"},{"id":"c631-investment","title":"Innovation Performance Categories","type":"radar"},{"id":"c631-qipi","title":"QIPI Outcome Trend","type":"trend"},{"id":"c631-impact","title":"Before and After Impact","type":"gauge"},{"id":"c631-status","title":"Improvement Action Status","type":"matrix"}]},"6.4.1":{"title":"Provider's Accreditation and Evaluation","charts":[{"id":"c641-tier","title":"Provider Tier Profile","type":"donut"},{"id":"c641-screening","title":"Provider Accreditation Funnel","type":"funnel"},{"id":"c641-package","title":"Compliance Package","type":"matrix"},{"id":"c641-delivery","title":"Service Delivery and Purchase Controls","type":"lifecycle"},{"id":"c641-rating","title":"Provider Rating Weighting","type":"radar"},{"id":"c641-outcomes","title":"Provider Evaluation Outcomes","type":"donut"}]},"6.5.3":{"title":"Hazard Identification and Risk Assessment","charts":[{"id":"c653-reporting","title":"Hazard Reporting Funnel","type":"funnel"},{"id":"c653-levels","title":"Risk Level Distribution","type":"donut"},{"id":"c653-matrix","title":"5×5 Risk Matrix","type":"risk-matrix"},{"id":"c653-treatment","title":"Risk Treatment Lifecycle","type":"lifecycle"},{"id":"c653-residual","title":"Residual Risk Trend","type":"trend"},{"id":"c653-bcdr","title":"Business Continuity Readiness","type":"radar"}]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_6","defaultSection":"6.1.1","apiSections":{"overview":"6.1.1","6.1.1":"6.1.1","6.2.1":"6.2.1","6.3.1":"6.3.1","6.4.1":"6.4.1","6.5.3":"6.5.3","quality":"6.1.1","sources":"6.1.1"},"panelMap":{"overview":"overview","6.1.1":"6.1.1","6.2.1":"6.2.1","6.3.1":"6.3.1","6.4.1":"6.4.1","6.5.3":"6.5.3","sources":"sources","quality":"sources"}},"criterion_7":{"number":"7","title":"Performance Outcomes","description":"Live, permission-aware analytics foundation for outcome measurement, target achievement and stakeholder performance. Unsupported fields are shown explicitly.","subcriteria":[["7.1.1","Measurement of Outcomes"]],"sections":{"overview":{"title":"Overview","charts":[{"id":"criterion_7-overview-targets","title":"Target Gap Summary","type":"bar"},{"id":"criterion_7-overview-sources","title":"Source Availability","type":"donut"}]},"7.1":{"title":"Measurement of Outcomes","charts":[{"id":"criterion_7-71-coverage","title":"Measurement of Outcomes Control Coverage","type":"bar"},{"id":"criterion_7-71-status","title":"Measurement of Outcomes Status Distribution","type":"donut"}]},"7.1.1":{"title":"Measurement of Outcomes","charts":[{"id":"criterion_7-71-coverage","title":"Measurement of Outcomes Control Coverage","type":"bar"},{"id":"criterion_7-71-status","title":"Measurement of Outcomes Status Distribution","type":"donut"}]},"sources":{"title":"Sources and Data Quality","charts":[]},"quality":{"title":"Sources and Data Quality","charts":[]}},"apiMethod":"ucc_analytics_criterion_7","defaultSection":"7.1.1","apiSections":{"overview":"7.1.1","7.1.1":"7.1.1","quality":"7.1.1","sources":"7.1.1"},"panelMap":{"overview":"overview","7.1.1":"7.1.1","sources":"sources","quality":"sources"},"filters":[["academic_year","Academic Year",["All Academic Years","2026","2025"]],["student_group","Module Class Details",["All Module Classes"]],["program","Course",["All Courses"]],{"key":"month","label":"Month","type":"month"}]}};
const LIVE_VISUAL_EXPANSION={"criterion_1":{"overview":[{"id":"v190-c1-overview-01","title":"Governance and Strategy Metric Profile","type":"bar","description":"Compares key governance and strategic planning metrics side by side for this criterion.","i":0},{"id":"v190-c1-overview-02","title":"Live Source Availability","type":"donut","description":"Shows what share of the underlying DocTypes and fields are currently readable.","i":1},{"id":"v190-c1-overview-06","title":"Evidence Readiness Matrix","type":"matrix","description":"Grids evidence completeness against each governance and strategy control area.","i":5},{"id":"v190-c1-overview-08","title":"Leadership Responsibility Coverage","type":"trend","description":"Tracks over time how many leadership roles have clearly assigned responsibilities.","i":7},{"id":"v190-c1-overview-17","title":"Governance Risk Exposure","type":"bar","description":"Compares governance risk exposure across the areas this criterion covers.","i":16},{"id":"v190-c1-overview-20","title":"Evidence Completeness","type":"lifecycle","description":"Follows evidence records from missing through to fully documented and verified.","i":19},{"id":"v190-c1-overview-27","title":"Target Achievement Gauge","type":"funnel","description":"Tracks strategic targets from set through to fully achieved.","i":26},{"id":"v190-c1-overview-28","title":"Overall Criterion Readiness","type":"lifecycle","description":"Summarises how ready Criterion 1 is overall, from raw data through to verified evidence.","i":27}],"1.1.1":[{"id":"v190-c1-111-01","title":"Governance Control Coverage","type":"bar","description":"Compares how many governance controls are in place across different control areas.","i":0},{"id":"v190-c1-111-02","title":"Governance Status Distribution","type":"donut","description":"Shows the current status mix of governance records, from open to resolved.","i":1},{"id":"v190-c1-111-03","title":"Leadership and Role Readiness","type":"funnel","description":"Tracks leadership roles from defined through to fully staffed and ready.","i":2},{"id":"v190-c1-111-04","title":"Policy and Review Lifecycle","type":"lifecycle","description":"Follows a governance policy from drafted through approval to its next review.","i":3},{"id":"v190-c1-111-05","title":"Governance Evidence Matrix","type":"radar","description":"Compares evidence strength across the different governance control areas.","i":4},{"id":"v190-c1-111-06","title":"Governance Action Completion","type":"matrix","description":"Grids governance action completion against each responsible area or owner.","i":5},{"id":"v190-c1-111-15","title":"Policy Approval Status","type":"gauge","description":"Gauges what share of governance policies have completed formal approval.","i":14},{"id":"v190-c1-111-19","title":"Conflict and Independence Controls","type":"funnel","description":"Tracks conflict-of-interest declarations from required through to confirmed and cleared.","i":18},{"id":"v190-c1-111-22","title":"Governance Records Readiness","type":"matrix","description":"Grids how ready governance records are for audit against each control area.","i":21},{"id":"v190-c1-111-27","title":"Governance Source Readiness","type":"funnel","description":"Tracks the underlying governance data sources from unread through to fully readable.","i":26},{"id":"v190-c1-111-28","title":"Governance Metric Readiness","type":"lifecycle","description":"Follows governance metrics from unavailable through to fully calculated and ready.","i":27}],"1.2.1":[{"id":"v190-c1-121-01","title":"Strategic Planning Control Coverage","type":"bar","description":"Compares how many strategic planning controls are documented across each planning area.","i":0},{"id":"v190-c1-121-02","title":"Strategic Objective Status","type":"donut","description":"Shows the current status mix of strategic objectives, from drafted to achieved.","i":1},{"id":"v190-c1-121-03","title":"Strategic Target Readiness","type":"funnel","description":"Tracks strategic targets from set through to having a measurable result recorded.","i":2},{"id":"v190-c1-121-04","title":"Plan-to-Review Lifecycle","type":"lifecycle","description":"Follows a strategic plan from drafted through implementation to its formal review.","i":3},{"id":"v190-c1-121-06","title":"Strategic Action Completion","type":"matrix","description":"Grids strategic action completion against each objective or planning area.","i":5},{"id":"v190-c1-121-09","title":"Target versus Actual Profile","type":"bar","description":"Compares planned targets against actual results across strategic objectives.","i":8},{"id":"v190-c1-121-10","title":"Milestone Completion","type":"donut","description":"Shows what share of strategic plan milestones have been completed on time.","i":9},{"id":"v190-c1-121-16","title":"Planning Evidence Completeness","type":"trend","description":"Tracks how complete the supporting evidence for strategic planning has been over time.","i":15},{"id":"v190-c1-121-22","title":"Objective Ownership Coverage","type":"matrix","description":"Grids strategic objectives against whether each one has a clearly named owner.","i":21},{"id":"v190-c1-121-27","title":"Strategy Source Readiness","type":"funnel","description":"Tracks the underlying strategic planning data sources from unread through to readable.","i":26},{"id":"v190-c1-121-28","title":"Strategy Metric Readiness","type":"lifecycle","description":"Follows strategic planning metrics from unavailable through to fully calculated and ready.","i":27}]},"criterion_2":{"overview":[{"id":"v190-c2-overview-01","title":"Corporate Administration Metric Profile","type":"bar","description":"Compares key corporate administration metrics side by side for this criterion.","i":0},{"id":"v190-c2-overview-02","title":"Live Source Availability","type":"donut","description":"Shows what share of the underlying DocTypes and fields are currently readable.","i":1},{"id":"v190-c2-overview-03","title":"Administration System Health","type":"funnel","description":"Tracks how administration records move from raised to fully resolved across the system.","i":2},{"id":"v190-c2-overview-04","title":"People-to-Feedback Lifecycle","type":"lifecycle","description":"Maps the stages a people record passes through on its way to feedback closure.","i":3},{"id":"v190-c2-overview-05","title":"Corporate Exception Funnel","type":"radar","description":"Highlights where corporate administration exceptions are concentrated across different areas.","i":4},{"id":"v190-c2-overview-06","title":"Evidence Readiness Matrix","type":"matrix","description":"Grids evidence completeness against each corporate administration control area.","i":5}],"2.1.1":[{"id":"v190-c2-211-01","title":"Staff Selection and Management Coverage","type":"bar","description":"Compares how many staff selection and management controls are covered across each area.","i":0},{"id":"v190-c2-211-02","title":"Staff Lifecycle Status","type":"donut","description":"Shows the current status mix of staff records, from onboarding to exit.","i":1},{"id":"v190-c2-211-04","title":"Workforce Control Readiness","type":"lifecycle","description":"Follows workforce controls from unverified through to fully in place and ready.","i":3}],"2.1.2":[{"id":"v190-c2-212-01","title":"Training and Development Coverage","type":"bar","description":"Compares how many staff have documented training and development coverage.","i":0},{"id":"v190-c2-212-02","title":"Training Status Distribution","type":"donut","description":"Shows the current status mix of staff training records, from planned to completed.","i":1},{"id":"v190-c2-212-11","title":"Development Action Completion","type":"funnel","description":"Tracks development actions from identified through to closed out.","i":10}],"2.2.1":[{"id":"v190-c2-221-01","title":"Communication Control Coverage","type":"bar","description":"Compares how many communication controls are documented across internal and external channels.","i":0},{"id":"v190-c2-221-02","title":"Communication Status Distribution","type":"donut","description":"Shows the current status mix of communication records, from draft to published.","i":1},{"id":"v190-c2-221-11","title":"Communication Record Completeness","type":"funnel","description":"Tracks what share of communication records are fully and correctly documented.","i":10}],"2.3.1":[{"id":"v190-c2-231-01","title":"Data Management Control Coverage","type":"bar","description":"Compares how many data management controls are in place across this area.","i":0},{"id":"v190-c2-231-02","title":"Data Control Status","type":"donut","description":"Shows the current status mix of data control records, from open to resolved.","i":1},{"id":"v190-c2-231-04","title":"Data Quality Readiness","type":"lifecycle","description":"Follows data quality checks from unverified through to confirmed clean.","i":3}],"2.3.2":[{"id":"v190-c2-232-01","title":"Knowledge Management Coverage","type":"bar","description":"Compares how many knowledge management controls are covered across this area.","i":0},{"id":"v190-c2-232-02","title":"Knowledge Asset Status","type":"donut","description":"Shows the current status mix of knowledge assets, from draft to published.","i":1},{"id":"v190-c2-232-04","title":"Knowledge Repository Readiness","type":"lifecycle","description":"Follows the knowledge repository from incomplete through to confirmed ready.","i":3}],"2.4.1":[{"id":"v190-c2-241-01","title":"Feedback Management Coverage","type":"bar","description":"Compares how many feedback management controls are covered across this area.","i":0},{"id":"v190-c2-241-02","title":"Feedback Status Distribution","type":"donut","description":"Shows the current status mix of feedback records, from received to closed.","i":1},{"id":"v190-c2-241-11","title":"Improvement Action Linkage","type":"funnel","description":"Tracks improvement actions raised from feedback through to implementation.","i":10}],"2.4.2":[{"id":"v190-c2-242-01","title":"Student Survey Coverage","type":"bar","description":"Compares how many student satisfaction surveys have documented coverage.","i":0},{"id":"v190-c2-242-02","title":"Student Survey Status","type":"donut","description":"Shows the current status mix of student surveys, from open to completed.","i":1},{"id":"v190-c2-242-04","title":"Student Satisfaction Readiness","type":"lifecycle","description":"Follows student satisfaction readiness from unverified through to confirmed complete.","i":3}],"2.4.3":[{"id":"v190-c2-243-01","title":"Staff Survey Coverage","type":"bar","description":"Compares how many staff satisfaction surveys have documented coverage.","i":0},{"id":"v190-c2-243-02","title":"Staff Survey Status","type":"donut","description":"Shows the current status mix of staff surveys, from open to completed.","i":1},{"id":"v190-c2-243-04","title":"Staff Satisfaction Readiness","type":"lifecycle","description":"Follows staff satisfaction readiness from unverified through to confirmed complete.","i":3}]},"criterion_3":{"overview":[{"id":"v190-c3-overview-01","title":"Agent Lifecycle Coverage","type":"bar","description":"Compares agent lifecycle stages side by side across all recruitment agents.","i":0},{"id":"v190-c3-overview-02","title":"Policy Control Coverage","type":"donut","description":"Shows what share of agent-related policy controls are currently in place.","i":1},{"id":"v190-c3-overview-05","title":"Open Exception Profile","type":"radar","description":"Highlights where open exceptions are concentrated across agent management areas.","i":4},{"id":"v190-c3-overview-06","title":"Source Readiness","type":"matrix","description":"Grids source readiness against each area this criterion covers.","i":5},{"id":"v190-c3-overview-07","title":"Agent Portfolio Status","type":"gauge","description":"Gauges how the current agent portfolio is distributed by status.","i":6},{"id":"v190-c3-overview-10","title":"Agent NDA Coverage","type":"donut","description":"Shows the share of agents with a completed NDA on file.","i":9},{"id":"v190-c3-overview-20","title":"Agent Evidence Completeness","type":"lifecycle","description":"Follows agent evidence records from incomplete through to fully documented.","i":19},{"id":"v190-c3-overview-28","title":"Agent Target Achievement","type":"lifecycle","description":"Tracks agents from recruitment target set through to achieved.","i":27}],"3.1.1":[{"id":"v190-c3-311-01","title":"Identification Pathways","type":"bar","description":"Compares how agent candidates were identified across each sourcing pathway.","i":0},{"id":"v190-c3-311-02","title":"Selection and Screening Funnel","type":"donut","description":"Tracks candidate agents from initial screening through to selection.","i":1},{"id":"v190-c3-311-05","title":"Approval and Background Check","type":"radar","description":"Follows candidate agents from approval through to a completed background check.","i":4},{"id":"v190-c3-311-06","title":"Contract and NDA Readiness","type":"matrix","description":"Gauges how ready contract and NDA documentation is for new agents.","i":5},{"id":"v190-c3-311-07","title":"Agent Listing and Status","type":"gauge","description":"Gauges how the current agent listing is distributed by status.","i":6},{"id":"v190-c3-311-12","title":"Due-Diligence Evidence","type":"lifecycle","description":"Follows due-diligence evidence from missing through to fully documented.","i":11},{"id":"v190-c3-311-15","title":"Selection Rating Completeness","type":"gauge","description":"Gauges what share of candidate agents have a completed selection rating.","i":14},{"id":"v190-c3-311-20","title":"Contract Signature Coverage","type":"lifecycle","description":"Gauges what share of agent contracts have a completed signature.","i":19},{"id":"v190-c3-311-22","title":"NDA Completion Status","type":"matrix","description":"Gauges what share of required agent NDAs have been completed.","i":21},{"id":"v190-c3-311-27","title":"Selection Source Readiness","type":"funnel","description":"Tracks the underlying selection data sources from unread through to readable.","i":26},{"id":"v190-c3-311-28","title":"Selection Metric Readiness","type":"lifecycle","description":"Follows selection metrics from unavailable through to fully calculated and ready.","i":27}],"3.2.1":[{"id":"v190-c3-321-01","title":"Agent Onboarding Funnel","type":"bar","description":"Tracks agents from onboarding start through to onboarding completion.","i":0},{"id":"v190-c3-321-02","title":"Training Coverage","type":"donut","description":"Shows what share of active agents have completed required training.","i":1},{"id":"v190-c3-321-03","title":"Service Delivery Controls","type":"funnel","description":"Gauges how many service delivery controls are in place for active agents.","i":2},{"id":"v190-c3-321-04","title":"Performance Evaluation Distribution","type":"lifecycle","description":"Shows how agent performance evaluations are distributed across ratings.","i":3},{"id":"v190-c3-321-06","title":"Complaints and Breaches","type":"matrix","description":"Grids complaints and breaches against each responsible agent.","i":5},{"id":"v190-c3-321-15","title":"Contract Renewal Coverage","type":"gauge","description":"Gauges what share of agent contracts have been renewed on time.","i":14},{"id":"v190-c3-321-17","title":"Provider Rating Outcomes","type":"bar","description":"Compares agent performance against their provider rating outcomes.","i":16},{"id":"v190-c3-321-22","title":"Monitoring Record Coverage","type":"matrix","description":"Grids monitoring record coverage against each active agent.","i":21},{"id":"v190-c3-321-26","title":"Offboarding Completion","type":"donut","description":"Shows what share of agent offboarding processes have been completed.","i":25},{"id":"v190-c3-321-27","title":"Evaluation Source Readiness","type":"funnel","description":"Tracks the underlying evaluation data sources from unread through to readable.","i":26},{"id":"v190-c3-321-28","title":"Evaluation Metric Readiness","type":"lifecycle","description":"Follows evaluation metrics from unavailable through to fully calculated and ready.","i":27}]},"criterion_4":{"overview":[{"id":"c4-overview-flow","title":"Student Protection Control Flow","type":"lifecycle","description":"Follows the principal student-protection controls from admission through attendance and support.","i":0},{"id":"c4-overview-exceptions","title":"Open Exception Profile","type":"ladder","description":"Highlights the live Criterion 4 exceptions requiring follow-up.","i":1},{"id":"c4-overview-readiness","title":"Student Control Readiness","type":"radar","description":"Compares readiness across the main student protection and support controls.","i":2}],"4.1.1":[{"id":"c411-applicants-year","title":"No. of Student Applicants per Year","type":"admission-line","description":"Counts all Student Applicant records grouped by academic year.","dataKey":"applicants_by_year","metricId":"c411-applicants-total"},{"id":"c411-enrolled-year","title":"No. of Enrolled Students per Year","type":"admission-line","description":"Counts Student Applicant records with application status Admitted, grouped by academic year.","dataKey":"enrolled_by_year","metricId":"c411-enrolled-admitted"},{"id":"c411-applicants-country","title":"Applicants per Country","type":"admission-column","description":"Counts Student Applicant records grouped by nationality or country.","dataKey":"applicants_by_country","metricId":"c411-applicants-total"},{"id":"c411-counselling-duration","title":"Duration from Counselling to Admission","type":"admission-line","description":"Average calendar days from pre-course counselling to student signature, grouped by applicant academic year.","dataKey":"counselling_to_admission","metricId":"c411-enrolled-admitted"},{"id":"c411-popular-programmes","title":"Popular Courses of Full Qualification","type":"admission-column","description":"Counts Student Applicant records grouped by programme.","dataKey":"programmes","metricId":"c411-applicants-total"},{"id":"c411-students-agent","title":"Number of Students per Agent","type":"donut","description":"Counts Student Applicant records grouped by recruitment agent, following the supplied Metabase calculation.","dataKey":"agents","metricId":"c411-applicants-total"}],"4.2.1":[{"id":"c4-421-contract","title":"Student Contract Lifecycle","type":"lifecycle","description":"Follows contract preparation, signature, invoicing and full execution.","i":0},{"id":"c4-421-readiness","title":"Student Contract Readiness","type":"radar","description":"Compares the evidence required for an executed student contract.","i":1},{"id":"c4-421-aging","title":"Contract Follow-up Ladder","type":"ladder","description":"Prioritises contract cases requiring follow-up.","i":2}],"4.2.2":[{"id":"c4-422-reconciliation","title":"Fee and FPS Reconciliation","type":"reconciliation","description":"Reconciles invoices, payments, FPS records and fee-protection controls.","i":0},{"id":"c4-422-flow","title":"Fee and FPS Processing Flow","type":"lifecycle","description":"Follows fee processing from invoice through protection and reconciliation.","i":1},{"id":"c4-422-exceptions","title":"Fee-Control Exception Profile","type":"ladder","description":"Shows fee and protection issues requiring review.","i":2}],"4.3.1":[{"id":"c4-431-decision","title":"Course Movement Decision Path","type":"decision","description":"Shows transfer, deferment and withdrawal cases by decision path.","i":0},{"id":"c4-431-mix","title":"Course Movement Request Mix","type":"donut","description":"Compares the current mix of student movement requests.","i":1},{"id":"c4-431-timing","title":"Movement Processing Timeliness","type":"ladder","description":"Prioritises movement cases according to processing status.","i":2}],"4.4.1":[{"id":"c4-441-decision","title":"Refund Decision Path","type":"decision","description":"Shows refund requests from eligibility through approval and payment.","i":0},{"id":"c4-441-outcomes","title":"Refund Request Outcomes","type":"funnel","description":"Tracks refund requests through completion.","i":1},{"id":"c4-441-aging","title":"Refund Follow-up Ladder","type":"ladder","description":"Prioritises open and overdue refund cases.","i":2}],"4.5.1":[{"id":"c4-451-network","title":"Student Support Service Network","type":"network","description":"Maps the live channels and records supporting student interventions.","i":0},{"id":"c4-451-channels","title":"Student Support Channel Mix","type":"donut","description":"Compares support activity across the available channels.","i":1},{"id":"c4-451-followup","title":"Student Support Follow-up Flow","type":"ladder","description":"Shows follow-up controls from service coverage through outcome review.","i":2}],"4.6.1":[{"id":"c4-461-lifecycle","title":"Attendance Intervention Lifecycle","type":"lifecycle","description":"Follows attendance records through risk identification and intervention.","i":0},{"id":"c4-461-risk","title":"Attendance Risk Profile","type":"radar","description":"Compares attendance, leave, warning and intervention evidence.","i":1},{"id":"c4-461-response","title":"Attendance Intervention Response","type":"ladder","description":"Shows intervention controls in follow-up order.","i":2}]},"criterion_5":{"overview":[{"id":"c5-overview-readiness","title":"Academic System Readiness","type":"bar","description":"Compares the live academic-system metrics returned for the selected Criterion 5 area.","i":0},{"id":"c5-overview-availability","title":"Source Availability","type":"donut","description":"Shows readable sources, source issues, readable metrics and metric issues.","i":1},{"id":"c5-overview-health","title":"Criterion 5 System Health","type":"matrix","description":"Summarises available metrics, unavailable metrics, sources and exceptions.","i":2},{"id":"c5-overview-exceptions","title":"Criterion 5 Exception Profile","type":"funnel","description":"Highlights live exceptions that require academic or data-quality follow-up.","i":3}],"5.1.1":[{"id":"c5-511-coverage","title":"Course Design Control Coverage","type":"bar","description":"Compares course proposal, module design, programme mapping and assessment-plan evidence.","i":0},{"id":"c5-511-status","title":"Course Design Status Distribution","type":"donut","description":"Shows available design metrics, source readiness and exceptions.","i":1},{"id":"c5-511-readiness","title":"Course Design Evidence Readiness","type":"radar","description":"Compares readiness across the main course design and development controls.","i":2},{"id":"c5-511-gaps","title":"Course Design Gap Profile","type":"funnel","description":"Highlights course design controls that require follow-up.","i":3}],"5.1.2":[{"id":"c5-512-coverage","title":"Course Review Control Coverage","type":"bar","description":"Compares module review, course review, approval and recommendation evidence.","i":0},{"id":"c5-512-status","title":"Course Review Status Distribution","type":"donut","description":"Shows review source and metric readiness.","i":1},{"id":"c5-512-cycle","title":"Course Review Lifecycle","type":"lifecycle","description":"Follows review evidence from recorded through approval and recommendation follow-up.","i":2},{"id":"c5-512-gaps","title":"Review Exception Profile","type":"funnel","description":"Highlights overdue or incomplete review controls.","i":3}],"5.2.1":[{"id":"c5-521-coverage","title":"Course Planning Control Coverage","type":"bar","description":"Compares intake, module class, schedule and student-contract planning evidence.","i":0},{"id":"c5-521-status","title":"Course Planning Status Distribution","type":"donut","description":"Shows planning source and metric readiness.","i":1},{"id":"c5-521-flow","title":"Planning Readiness Flow","type":"lifecycle","description":"Follows planning evidence from intake through class, schedule and contract readiness.","i":2},{"id":"c5-521-gaps","title":"Planning Exception Profile","type":"funnel","description":"Highlights incomplete planning controls requiring follow-up.","i":3}],"5.2.2":[{"id":"c5-522-coverage","title":"Course Delivery Control Coverage","type":"bar","description":"Compares schedules, attendance, observations and sign-off evidence.","i":0},{"id":"c5-522-status","title":"Course Delivery Status Distribution","type":"donut","description":"Shows delivery source and metric readiness.","i":1},{"id":"c5-522-readiness","title":"Delivery Evidence Readiness","type":"radar","description":"Compares attendance, observation and sign-off evidence across delivery controls.","i":2},{"id":"c5-522-gaps","title":"Delivery Exception Profile","type":"funnel","description":"Highlights delivery controls requiring follow-up.","i":3}],"5.3.1":[{"id":"c5-531-coverage","title":"Partnership Control Coverage","type":"bar","description":"Compares agreement, monitoring, evaluation and provider-rating evidence.","i":0},{"id":"c5-531-status","title":"Partnership Status Distribution","type":"donut","description":"Shows partnership source and metric readiness.","i":1},{"id":"c5-531-risk","title":"Partnership Risk Profile","type":"funnel","description":"Highlights expiry, NDA and threshold risks requiring follow-up.","i":2},{"id":"c5-531-readiness","title":"Partnership Evidence Readiness","type":"matrix","description":"Grids readiness across partnership management controls.","i":3}],"5.4":[{"id":"c5-54-coverage","title":"Student Feedback Control Coverage","type":"bar","description":"Compares survey, score and attendance-risk evidence.","i":0},{"id":"c5-54-status","title":"Student Feedback Status Distribution","type":"donut","description":"Shows feedback source and metric readiness.","i":1},{"id":"c5-54-readiness","title":"Feedback Evidence Readiness","type":"radar","description":"Compares survey and learning-support evidence across key controls.","i":2},{"id":"c5-54-gaps","title":"Feedback Exception Profile","type":"funnel","description":"Highlights feedback controls requiring follow-up.","i":3}],"5.5":[{"id":"c5-55-coverage","title":"Assessment Control Coverage","type":"bar","description":"Compares assessment plans, control fields, results, grades and scores.","i":0},{"id":"c5-55-status","title":"Assessment Status Distribution","type":"donut","description":"Shows assessment source and metric readiness.","i":1},{"id":"c5-55-readiness","title":"Assessment Evidence Readiness","type":"radar","description":"Compares readiness across assessment planning and result controls.","i":2},{"id":"c5-55-gaps","title":"Assessment Exception Profile","type":"funnel","description":"Highlights assessment controls requiring correction or follow-up.","i":3}]},"criterion_6":{"overview":[{"id":"v190-c6-overview-02","title":"Policy Evidence Coverage","type":"donut","description":"Shows what share of quality policies have documented supporting evidence.","i":1},{"id":"v190-c6-overview-04","title":"Quality Calendar Completion","type":"lifecycle","description":"Gauges how much of the planned quality calendar has been completed.","i":3},{"id":"v190-c6-overview-06","title":"Source Readiness","type":"matrix","description":"Grids source readiness against each quality assurance area this criterion covers.","i":5},{"id":"v190-c6-overview-14","title":"Quality Evidence Completeness","type":"matrix","description":"Follows quality evidence records from incomplete through to fully documented.","i":13},{"id":"v190-c6-overview-16","title":"Overall Criterion Readiness","type":"trend","description":"Summarises how ready Criterion 6 is overall, from raw data through to verified evidence.","i":15}],"6.1.1":[{"id":"v190-c6-611-01","title":"Annual Audit Programme","type":"bar","description":"Compares planned audits against the annual audit programme.","i":0},{"id":"v190-c6-611-02","title":"Audit Scope Coverage","type":"donut","description":"Shows how audit scope is distributed across the areas covered.","i":1},{"id":"v190-c6-611-05","title":"Audit Findings by Severity","type":"radar","description":"Compares audit findings by severity across recent audits.","i":4},{"id":"v190-c6-611-06","title":"Corrective Action Closure","type":"matrix","description":"Grids corrective action closure against each audit finding raised.","i":5},{"id":"v190-c6-611-16","title":"Audit Source Readiness","type":"trend","description":"Tracks the underlying audit data sources from unread through to fully readable.","i":15}],"6.2.1":[{"id":"v190-c6-621-01","title":"THESIS Review Coverage","type":"bar","description":"Compares THESIS review inputs covered against the required agenda items.","i":0},{"id":"v190-c6-621-03","title":"Review Input Completeness","type":"funnel","description":"Follows management review input completeness from partial through to full.","i":2},{"id":"v190-c6-621-04","title":"Review Outputs","type":"lifecycle","description":"Follows management review outputs from raised through to implemented.","i":3},{"id":"v190-c6-621-07","title":"Review Status Distribution","type":"gauge","description":"Shows how management review meetings are distributed across their status.","i":6},{"id":"v190-c6-621-16","title":"Management Review Source Readiness","type":"trend","description":"Tracks the underlying management review data sources from unread through to readable.","i":15}],"6.3.1":[{"id":"v190-c6-631-01","title":"Innovation Type Mix","type":"bar","description":"Compares how innovation initiatives are distributed across their type.","i":0},{"id":"v190-c6-631-02","title":"Improvement Initiative Lifecycle","type":"donut","description":"Follows an improvement initiative from proposed through to implemented.","i":1},{"id":"v190-c6-631-06","title":"Improvement Action Status","type":"matrix","description":"Grids improvement action status against each initiative raised.","i":5},{"id":"v190-c6-631-08","title":"Implementation Progress","type":"trend","description":"Tracks how much implementation progress has been made across initiatives.","i":7},{"id":"v190-c6-631-16","title":"Innovation Source Readiness","type":"trend","description":"Tracks the underlying innovation data sources from unread through to readable.","i":15}],"6.4.1":[{"id":"v190-c6-641-01","title":"Provider Tier Profile","type":"bar","description":"Compares how providers are distributed across their accreditation tier.","i":0},{"id":"v190-c6-641-02","title":"Provider Accreditation Funnel","type":"donut","description":"Tracks providers from application through to accreditation approval.","i":1},{"id":"v190-c6-641-06","title":"Provider Evaluation Outcomes","type":"matrix","description":"Shows what share of provider evaluations resulted in a positive outcome.","i":5},{"id":"v190-c6-641-11","title":"Rating Completeness","type":"funnel","description":"Gauges what share of provider ratings have been fully completed.","i":10},{"id":"v190-c6-641-16","title":"Provider Source Readiness","type":"trend","description":"Tracks the underlying provider data sources from unread through to readable.","i":15}],"6.5.3":[{"id":"v190-c6-653-01","title":"Hazard Reporting Funnel","type":"bar","description":"Tracks hazards from reported through to fully assessed.","i":0},{"id":"v190-c6-653-02","title":"Risk Level Distribution","type":"donut","description":"Shows how identified risks are distributed across severity levels.","i":1},{"id":"v190-c6-653-03","title":"5×5 Risk Matrix","type":"funnel","description":"Grids likelihood against impact across the full 5x5 risk matrix.","i":2},{"id":"v190-c6-653-07","title":"Risk Assessment Coverage","type":"gauge","description":"Compares how many risk assessments have been completed across areas.","i":6},{"id":"v190-c6-653-16","title":"Risk Source Readiness","type":"trend","description":"Tracks the underlying risk data sources from unread through to fully readable.","i":15}]},"criterion_7":{"overview":[{"id":"v190-c7-overview-02","title":"Live Source Availability","type":"donut","description":"Shows what share of the underlying DocTypes and fields are currently readable.","i":1},{"id":"v190-c7-overview-06","title":"Outcome Evidence Readiness","type":"matrix","description":"Grids evidence completeness against each outcome area this criterion covers.","i":5},{"id":"v190-c7-overview-08","title":"Target Availability","type":"trend","description":"Tracks how many indicators have a defined target over recent periods.","i":7},{"id":"v190-c7-overview-09","title":"Actual Result Availability","type":"bar","description":"Compares how many indicators have an actual result recorded.","i":8},{"id":"v190-c7-overview-10","title":"Target Achievement","type":"donut","description":"Shows the share of indicators that have achieved their set target.","i":9},{"id":"v190-c7-overview-11","title":"Target Variance","type":"funnel","description":"Tracks the variance between target and actual results across indicators.","i":10},{"id":"v190-c7-overview-14","title":"Outcome Review Status","type":"matrix","description":"Grids outcome review status against each area being measured.","i":13},{"id":"v190-c7-overview-28","title":"Underperforming Indicators","type":"lifecycle","description":"Follows underperforming indicators from flagged through to addressed.","i":27},{"id":"v190-c7-overview-29","title":"Missing Measurements","type":"radar","description":"Compares where measurements are missing across tracked indicators.","i":28},{"id":"v190-c7-overview-34","title":"Outcome Action Status","type":"donut","description":"Shows the status mix of actions raised against underperforming outcomes.","i":33},{"id":"v190-c7-overview-35","title":"Outcome Source Readiness","type":"funnel","description":"Tracks the underlying outcome data sources from unread through to readable.","i":34},{"id":"v190-c7-overview-40","title":"Overall Criterion Readiness","type":"trend","description":"Summarises how ready Criterion 7 is overall, from raw data through to verified evidence.","i":39}],"7.1.1":[{"id":"v190-c7-711-01","title":"Measurement Control Coverage","type":"bar","description":"Compares how many measurement controls are documented across outcome areas.","i":0},{"id":"v190-c7-711-02","title":"Measurement Status Distribution","type":"donut","description":"Shows the current status mix of outcome measurements, from open to resolved.","i":1},{"id":"v190-c7-711-03","title":"Indicator Definition Coverage","type":"funnel","description":"Tracks how many indicators have a complete, documented definition.","i":2},{"id":"v190-c7-711-04","title":"Indicator Ownership Coverage","type":"lifecycle","description":"Compares how many indicators have a clearly assigned owner.","i":3},{"id":"v190-c7-711-05","title":"Target Definition Coverage","type":"radar","description":"Compares how many indicators have a documented target definition.","i":4},{"id":"v190-c7-711-06","title":"Actual Result Coverage","type":"matrix","description":"Grids actual result coverage against each defined indicator.","i":5},{"id":"v190-c7-711-08","title":"Target Achievement Gauge","type":"trend","description":"Gauges what share of indicators have achieved their set target.","i":7},{"id":"v190-c7-711-09","title":"Target Variance Profile","type":"bar","description":"Compares target-versus-actual variance across defined indicators.","i":8},{"id":"v190-c7-711-12","title":"Benchmark Readiness","type":"lifecycle","description":"Gauges how ready indicators are for benchmark comparison.","i":11},{"id":"v190-c7-711-14","title":"Underperformance Profile","type":"matrix","description":"Grids underperformance against each indicator falling short of target.","i":13},{"id":"v190-c7-711-15","title":"Missing Result Profile","type":"gauge","description":"Gauges what share of indicators are missing a recorded result.","i":14},{"id":"v190-c7-711-16","title":"Review Completion","type":"trend","description":"Gauges how many scheduled outcome reviews have been completed.","i":15},{"id":"v190-c7-711-17","title":"Improvement Action Coverage","type":"bar","description":"Compares how many underperforming outcomes have a linked improvement action.","i":16},{"id":"v190-c7-711-31","title":"Measurement Source Readiness","type":"gauge","description":"Gauges how readable the underlying measurement data sources currently are.","i":30},{"id":"v190-c7-711-32","title":"Measurement Metric Readiness","type":"trend","description":"Tracks how ready measurement metrics are, from unavailable to calculated.","i":31},{"id":"v190-c7-711-36","title":"Outcome Action Closure","type":"lifecycle","description":"Follows outcome actions from raised through to formally closed.","i":35},{"id":"v190-c7-711-37","title":"Evidence Completeness","type":"radar","description":"Tracks how complete supporting evidence is across measured outcomes.","i":36},{"id":"v190-c7-711-38","title":"Data Quality Profile","type":"matrix","description":"Grids data quality checks against each outcome measurement area.","i":37}]}};
window.UCCLiveVisualDefinitions=LIVE_VISUAL_EXPANSION;
Object.keys(LIVE_VISUAL_EXPANSION).forEach(function(criterion){const config=CONFIG[criterion];if(!config)return;Object.keys(LIVE_VISUAL_EXPANSION[criterion]).forEach(function(section){config.sections[section]=config.sections[section]||{title:section,charts:[]};config.sections[section].charts=LIVE_VISUAL_EXPANSION[criterion][section];});});
function esc(value){return String(value==null?"":value).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");}

function normaliseFilterDefinition(raw){
if(Array.isArray(raw))return{key:raw[0],label:raw[1],options:Array.isArray(raw[2])?raw[2]:[],type:raw[0]==="month"?"month":"select"};
return{key:raw?.key||"filter",label:raw?.label||raw?.key||"Filter",options:Array.isArray(raw?.options)?raw.options:[],type:raw?.type||"text",placeholder:raw?.placeholder||""};
}
function filterMarkup(raw,index,criterionId){
const filter=normaliseFilterDefinition(raw),id=`ucc-${criterionId}-${filter.key}-${index}`;
if(filter.type==="month")return`<div><label for="${esc(id)}">${esc(filter.label)}</label><input id="${esc(id)}" data-demo-filter="${esc(filter.key)}" type="month"></div>`;
if(filter.type==="select"&&filter.options.length){
const options=filter.options.map((option,optionIndex)=>{const label=Array.isArray(option)?option[1]:option;const value=Array.isArray(option)?option[0]:(optionIndex===0?"":option);return`<option value="${esc(value)}">${esc(label)}</option>`;}).join("");
return`<div><label for="${esc(id)}">${esc(filter.label)}</label><select id="${esc(id)}" data-demo-filter="${esc(filter.key)}">${options}</select></div>`;
}
return`<div><label for="${esc(id)}">${esc(filter.label)}</label><input id="${esc(id)}" data-demo-filter="${esc(filter.key)}" type="text" placeholder="${esc(filter.placeholder||`All ${filter.label}`)}"></div>`;
}
function analyticsPanelMarkup(criterionId,key,title){
const isOverview=key==="overview",code=isOverview?"OVERVIEW":key;
return`<section class="panel-view${isOverview?"":" hidden"}" data-demo-panel="${esc(key)}"><div class="section-heading"><div><div class="section-code">${esc(code)}</div><h2>${esc(title)}</h2><p>Permission-aware live evidence, visual analysis and management questions.</p></div></div><div class="ucc-section-visual-anchor" data-live-anchor="${esc(key)}"></div><article class="panel ucc-shared-panel ucc-management-panel"><div class="panel-head"><h2>Management Questions and Data-Based Answers</h2></div><div class="table-wrap"><table class="qa-table"><thead><tr><th>Criterion</th><th>Question</th><th>Answer</th><th>Source / Calculation</th><th>Status</th></tr></thead><tbody data-demo-qa="${esc(criterionId+":"+key)}"></tbody></table></div></article></section>`;
}
function sourcesQualityPanelMarkup(criterionId){
return`<section class="panel-view hidden ucc-sources-quality-panel" data-demo-panel="sources"><div class="ucc-sources-quality-grid"><article class="panel ucc-shared-panel"><div class="panel-head"><div><h2>Source Availability</h2><p class="panel-subtitle">Resolved against the signed-in user's permissions.</p></div></div><div class="table-wrap"><table><thead><tr><th>Resolved DocType</th><th>Source key</th><th>Status</th><th>Records</th></tr></thead><tbody data-demo-sources="${esc(criterionId)}"></tbody></table></div></article><article class="panel ucc-shared-panel"><div class="panel-head"><div><h2>Data Quality Checks</h2><p class="panel-subtitle">Unavailable sources, permissions and unsupported fields are shown explicitly.</p></div></div><div class="table-wrap"><table><thead><tr><th>Check</th><th>Source</th><th>Status</th><th>Detail</th></tr></thead><tbody data-demo-quality="${esc(criterionId)}"></tbody></table></div></article></div></section>`;
}
function dashboardShellMarkup(criterionId,config){
const filters=(config.filters||[]).map((filter,index)=>filterMarkup(filter,index,criterionId)).join("");
const tabs=[['overview','Overview']].concat(config.subcriteria||[]).concat([['sources','Sources & Data Quality']]);
const tabMarkup=tabs.map((item,index)=>`<button type="button" class="${index===0?"active":""}" data-demo-tab="${esc(item[0])}">${esc(item[0]==="overview"||item[0]==="sources"?item[1]:item[0]+" "+item[1])}</button>`).join("");
const panels=[analyticsPanelMarkup(criterionId,'overview',config.sections?.overview?.title||'Overview')].concat((config.subcriteria||[]).map(item=>analyticsPanelMarkup(criterionId,item[0],item[1]))).join("")+sourcesQualityPanelMarkup(criterionId);
return`<div class="ucc-unified-dashboard"><div class="loading-overlay hidden" data-demo-loading-overlay><div class="loading-card"><div class="spinner"></div><strong data-demo-loading-title>Loading Criterion ${esc(config.number)}</strong><div class="progress-track"><div class="progress-fill" data-demo-progress-fill></div></div><div class="progress-text"><span data-demo-progress-value>0%</span> · <span>Permission-aware sources</span></div></div></div><header class="hero ucc-shared-hero ucc-standard-criterion-hero"><div class="hero-copy"><span class="ucc-criterion-kicker">EDUTRUST CRITERION ${esc(config.number)}</span><h1>Criterion ${esc(config.number)} · ${esc(config.title)}</h1><p>${esc(config.description)}</p></div><div class="hero-action-card ucc-shared-action-card ucc-standard-hero-actions" aria-label="Criterion ${esc(config.number)} analytics actions"><button type="button" class="primary-btn" data-demo-action="refresh">Refresh</button><button type="button" data-demo-action="export-qa">Export Q&amp;A CSV</button><button type="button" data-demo-action="export-exceptions">Export Exceptions CSV</button><button type="button" data-demo-action="diagnostics">Diagnostics Log (<span data-demo-log-count>0</span>)</button></div></header><div class="sticky-navigation"><section class="controls ucc-shared-controls"><div class="control-grid">${filters}</div></section><nav class="tabs ucc-shared-tabs" data-demo-tabs aria-label="Criterion ${esc(config.number)} sections">${tabMarkup}</nav></div><div class="ucc-criterion-notice ucc-readiness-strip" data-demo-readiness data-status="loading"><div class="ucc-criterion-notice-copy"><strong data-demo-readiness-title>Loading Criterion ${esc(config.number)} analytics…</strong><span data-demo-readiness-copy>Current-user permissions and live sources are being checked.</span></div><div class="ucc-readiness-actions"><button type="button" class="ucc-readiness-detail" data-demo-action="readiness">View readiness</button><button type="button" class="ucc-notice-dismiss" data-demo-action="dismiss-readiness" aria-label="Dismiss Criterion ${esc(config.number)} readiness notification" title="Dismiss">×</button></div></div><section class="kpis ucc-shared-kpis" data-demo-kpis></section><div class="ucc-unified-panel-stack">${panels}</div></div>`;
}
function mountUnifiedDashboards(){
platform.querySelectorAll('[data-dashboard-panel]').forEach(function(dashboard){
const criterionId=dashboard.dataset.dashboardPanel,criterionConfig=CONFIG[criterionId];
if(!criterionConfig)return;
dashboard.classList.add('ucc-criterion-dashboard','ucc-demo-dashboard');
dashboard.classList.remove('ucc-c4-dashboard','ucc-c5-v41');
dashboard.dataset.demoDashboard=criterionId;
dashboard.dataset.demoActiveTab='overview';
dashboard.dataset.dashboardArchitecture='shared-v2';
dashboard.innerHTML=dashboardShellMarkup(criterionId,criterionConfig);
});
}
function finiteNumber(value,fallback=0){const number=Number(value);return Number.isFinite(number)?number:fallback;}
function normaliseApiMessage(response){
let message=response&&response.message!==undefined?response.message:response;
for(let depth=0;depth<3;depth++){
if(typeof message==="string"){
try{message=JSON.parse(message);}catch(error){break;}
continue;
}
if(message&&typeof message==="object"&&!message.ok&&message.message&&typeof message.message==="object"){
message=message.message;
continue;
}
break;
}
return message;
}
function apiErrorMessage(error){
if(!error)return"Analytics request failed.";
if(typeof error==="string")return error;
if(error.message)return String(error.message);
if(error._server_messages){
try{
const messages=JSON.parse(error._server_messages);
if(Array.isArray(messages)&&messages.length){
const parsed=JSON.parse(messages[0]);
return parsed.message||String(messages[0]);
}
}catch(parseError){}
}
return error.exc_type||error.statusText||"Analytics request failed.";
}
function csvCell(value){const text=String(value==null?"":value);return/[",\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;}
function download(name,content,type="text/csv;charset=utf-8"){const blob=new Blob(["\ufeff",content],{type});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);}
function statusBadge(status){const raw=String(status||"available"),label=raw.replaceAll("_"," ");const cls=/risk|error|denied|unavailable|failed/i.test(raw)?"risk":/warn|unsupported|partial|pending|overdue/i.test(raw)?"warning":"good";return`<span class="ucc-demo-status ${cls}">${esc(label)}</span>`;}
function activeSection(dashboard){return dashboard.dataset.demoActiveTab||"overview";}
function sectionDefinition(config,tab){const key=(config.panelMap&&config.panelMap[tab])||tab;return config.sections[tab]||config.sections[key]||config.sections.overview;}
function liveChartCardMarkup(chart){
return`<article class="panel ucc-shared-panel ucc-demo-visual-card ucc-live-generated-card ucc-standard-functional-card" data-demo-card="${esc(chart.id)}"><div class="panel-head ucc-card-header"><div class="ucc-card-heading-copy"><h2>${esc(chart.title)}</h2><p class="ucc-card-description">${esc(chart.description||"Permission-aware live metrics.")}</p></div><div class="mini-toggle ucc-card-view-toggle" data-demo-view-toggle="${esc(chart.id)}"><button type="button" class="active" data-demo-view="diagram">Diagram</button><button type="button" data-demo-view="table">Table</button></div></div><div class="chart ucc-demo-chart" data-demo-chart="${esc(chart.id)}" data-demo-chart-title="${esc(chart.title)}" data-demo-chart-type="${esc(chart.type||"bar")}"></div><div class="table-wrap hidden" data-demo-chart-table="${esc(chart.id)}"><table><thead><tr><th>Metric</th><th>Live value</th><th>Status</th></tr></thead><tbody data-demo-chart-table-body="${esc(chart.id)}"></tbody></table></div><button type="button" data-demo-drill="${esc(chart.id)}">View underlying records</button></article>`;
}
function panelInsertPoint(panel){
return Array.from(panel.children).find(function(child){return/Management Questions and Data-Based Answers/i.test(child.textContent||"");})||null;
}
function ensureLiveSectionCards(dashboard,config,sectionKey){
const definitions=LIVE_VISUAL_EXPANSION[dashboard.dataset.demoDashboard]||{};
if(!sectionKey||!definitions[sectionKey])return;
const panelKey=(config.panelMap&&config.panelMap[sectionKey])||sectionKey;
if(panelKey==="quality"||panelKey==="sources")return;
const panel=dashboard.querySelector(`[data-demo-panel="${CSS.escape(panelKey)}"]`);
if(!panel)return;
let grid=panel.querySelector(`:scope > .ucc-live-expanded-grid[data-live-section="${CSS.escape(sectionKey)}"]`);
if(!grid){
grid=document.createElement("div");
grid.className="grid2 ucc-live-expanded-grid";
grid.dataset.liveSection=sectionKey;
panel.insertBefore(grid,panelInsertPoint(panel));
}
if(!grid.dataset.liveCardsMounted){
grid.innerHTML=(definitions[sectionKey]||[]).filter(function(chart){return chart.enabled!==false;}).map(liveChartCardMarkup).join("");
grid.dataset.liveCardsMounted="1";
}
}
function ensureLiveVisualCards(dashboard,config){
const definitions=LIVE_VISUAL_EXPANSION[dashboard.dataset.demoDashboard]||{};
dashboard.querySelectorAll(".ucc-demo-visual-card:not(.ucc-live-generated-card)").forEach(function(card){
card.hidden=true;
card.classList.add("ucc-live-base-card");
});
if(!dashboard.classList.contains("ucc-hidden"))ensureLiveSectionCards(dashboard,config,activeSection(dashboard));
}
function syncLiveSectionVisibility(dashboard,tab){
dashboard.querySelectorAll("[data-live-section]").forEach(function(grid){
grid.hidden=grid.dataset.liveSection!==tab;
});
}
function chartMax(rows){return Math.max.apply(null,rows.map(row=>finiteNumber(row[1],0)).concat([1]));}
function renderBars(node,rows){const max=chartMax(rows);node.innerHTML=`<div class="ucc-demo-bars">${rows.map(function(row){return`<div class="ucc-demo-bar"><label>${esc(row[0])}</label><div><i style="width:${Math.max(4,finiteNumber(row[1],0)/max*100)}%"></i></div><strong>${row[1]}${max<=100?"%":""}</strong></div>`;}).join("")}</div>`;}
function renderDonut(node,rows){const total=rows.reduce((sum,row)=>sum+finiteNumber(row[1],0),0)||1;let cursor=0;const stops=rows.map(function(row,index){const start=cursor/total*360;cursor+=finiteNumber(row[1],0);const end=cursor/total*360;return`var(--ucc-chart-${index%6}) ${start}deg ${end}deg`;}).join(",");node.innerHTML=`<div class="ucc-demo-donut-layout"><div class="ucc-demo-donut" style="background:conic-gradient(${stops})"><span>${total}</span><small>Total</small></div><div class="ucc-demo-legend">${rows.map(function(row,index){return`<div><i style="background:var(--ucc-chart-${index%6})"></i><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>`;}).join("")}</div></div>`;}
function renderFunnel(node,rows){const max=chartMax(rows);node.innerHTML=`<div class="ucc-demo-funnel">${rows.map(function(row,index){const width=Math.max(38,finiteNumber(row[1],0)/max*100);return`<div class="ucc-demo-funnel-stage" style="width:${width}%"><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>`;}).join("")}</div>`;}
function renderLifecycle(node,rows){node.innerHTML=`<div class="ucc-demo-lifecycle">${rows.map(function(row,index){return`<div class="ucc-demo-life-step"><i>${index+1}</i><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>${index<rows.length-1?'<b aria-hidden="true">→</b>':""}`;}).join("")}</div>`;}
function renderMatrix(node,rows){const max=chartMax(rows);node.innerHTML=`<div class="ucc-demo-matrix">${rows.map(function(row){const level=Math.max(.18,finiteNumber(row[1],0)/max);return`<div style="--ucc-intensity:${level}"><span>${esc(row[0])}</span><strong>${row[1]}${max<=100?"%":""}</strong></div>`;}).join("")}</div>`;}
function renderRadar(node,rows){const size=320,cx=160,cy=160,radius=105,count=Math.max(rows.length,3),max=chartMax(rows);const points=rows.map(function(row,index){const angle=-Math.PI/2+index*2*Math.PI/count,r=radius*(finiteNumber(row[1],0)/max);return[cx+Math.cos(angle)*r,cy+Math.sin(angle)*r];});const axes=rows.map(function(row,index){const angle=-Math.PI/2+index*2*Math.PI/count,x=cx+Math.cos(angle)*radius,y=cy+Math.sin(angle)*radius,lx=cx+Math.cos(angle)*(radius+28),ly=cy+Math.sin(angle)*(radius+28);return`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"></line><text x="${lx}" y="${ly}" text-anchor="middle">${esc(row[0])}</text>`;}).join("");node.innerHTML=`<div class="ucc-demo-radar"><svg viewBox="0 0 ${size} ${size}" role="img" aria-label="Radar diagram"><circle cx="${cx}" cy="${cy}" r="${radius}"></circle><circle cx="${cx}" cy="${cy}" r="${radius*.66}"></circle><circle cx="${cx}" cy="${cy}" r="${radius*.33}"></circle>${axes}<polygon points="${points.map(point=>point.join(",")).join(" ")}"></polygon></svg><div class="ucc-demo-radar-values">${rows.map(row=>`<span>${esc(row[0])}: <strong>${row[1]}</strong></span>`).join("")}</div></div>`;}
function renderTrend(node,rows){const width=560,height=250,pad=38,max=chartMax(rows),step=(width-pad*2)/Math.max(1,rows.length-1);const points=rows.map(function(row,index){return[pad+index*step,height-pad-(finiteNumber(row[1],0)/max)*(height-pad*2)];});node.innerHTML=`<div class="ucc-demo-trend"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trend diagram"><line class="axis" x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"></line><polyline points="${points.map(p=>p.join(",")).join(" ")}"></polyline>${points.map(function(p,index){return`<circle cx="${p[0]}" cy="${p[1]}" r="5"></circle><text x="${p[0]}" y="${height-12}" text-anchor="middle">${esc(rows[index][0])}</text><text class="value" x="${p[0]}" y="${p[1]-10}" text-anchor="middle">${rows[index][1]}</text>`;}).join("")}</svg></div>`;}
function renderGauge(node,rows){const current=finiteNumber(rows[0]?.[1],0),reference=finiteNumber(rows[1]?.[1],current||1),percentage=reference?Math.max(0,Math.min(100,current/reference*100)):0;node.innerHTML=`<div class="ucc-demo-gauge-layout"><div class="ucc-demo-gauge" style="--ucc-gauge:${percentage*1.8}deg"><div><strong>${current}</strong><span>Current</span></div></div><div class="ucc-demo-gauge-copy"><span>Reference metric</span><strong>${reference}</strong><small>${current>=reference?"At or above reference":"Difference "+Math.max(0,reference-current)}</small></div></div>`;}
function renderAdmissionLine(node,rows){
const width=720,height=300,pad={top:32,right:24,bottom:62,left:52},max=Math.max.apply(null,rows.map(row=>finiteNumber(row[1],0)).concat([1])),plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom,step=rows.length>1?plotW/(rows.length-1):0;
const points=rows.map((row,index)=>[pad.left+index*step,pad.top+plotH-(finiteNumber(row[1],0)/max)*plotH]);
const grid=[];for(let i=0;i<=5;i++){const y=pad.top+(plotH/5)*i,value=Math.round(max-(max/5)*i);grid.push(`<line class="grid" x1="${pad.left}" y1="${y}" x2="${width-pad.right}" y2="${y}"></line><text class="axis-label" x="${pad.left-10}" y="${y+4}" text-anchor="end">${value}</text>`);}
node.innerHTML=`<div class="ucc-admission-svg"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(node.dataset.demoChartTitle||"Admission trend")}">${grid.join("")}<line class="axis" x1="${pad.left}" y1="${height-pad.bottom}" x2="${width-pad.right}" y2="${height-pad.bottom}"></line><polyline class="series" points="${points.map(point=>point.join(",")).join(" ")}"></polyline>${points.map((point,index)=>`<circle class="point" cx="${point[0]}" cy="${point[1]}" r="5"></circle><text class="value" x="${point[0]}" y="${point[1]-12}" text-anchor="middle">${rows[index][1]}</text><text class="x-label" x="${point[0]}" y="${height-25}" text-anchor="middle">${esc(rows[index][0])}</text>`).join("")}</svg></div>`;
}
function renderAdmissionColumns(node,rows){
const width=720,height=320,pad={top:28,right:24,bottom:92,left:52},max=Math.max.apply(null,rows.map(row=>finiteNumber(row[1],0)).concat([1])),plotW=width-pad.left-pad.right,plotH=height-pad.top-pad.bottom,gap=12,barW=Math.max(12,(plotW-gap*Math.max(0,rows.length-1))/Math.max(1,rows.length));
const grid=[];for(let i=0;i<=5;i++){const y=pad.top+(plotH/5)*i,value=Math.round(max-(max/5)*i);grid.push(`<line class="grid" x1="${pad.left}" y1="${y}" x2="${width-pad.right}" y2="${y}"></line><text class="axis-label" x="${pad.left-10}" y="${y+4}" text-anchor="end">${value}</text>`);}
node.innerHTML=`<div class="ucc-admission-svg"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(node.dataset.demoChartTitle||"Admission comparison")}">${grid.join("")}<line class="axis" x1="${pad.left}" y1="${height-pad.bottom}" x2="${width-pad.right}" y2="${height-pad.bottom}"></line>${rows.map((row,index)=>{const value=finiteNumber(row[1],0),x=pad.left+index*(barW+gap),barH=(value/max)*plotH,y=pad.top+plotH-barH;return`<rect class="column" x="${x}" y="${y}" width="${barW}" height="${barH}" rx="4"></rect><text class="value" x="${x+barW/2}" y="${Math.max(16,y-9)}" text-anchor="middle">${value}</text><text class="x-label rotated" transform="translate(${x+barW/2},${height-pad.bottom+18}) rotate(-38)" text-anchor="end">${esc(row[0])}</text>`;}).join("")}</svg></div>`;
}
function renderRiskMatrix(node,chart){const values=chart.values||[],likelihood=["Rare","Remote","Occasional","Frequent","Almost Certain"],severity=["Catastrophic","Major","Moderate","Minor","Negligible"];node.innerHTML=`<div class="ucc-demo-risk-matrix"><div class="corner">Severity × Likelihood</div>${likelihood.map(x=>`<div class="head">${x}</div>`).join("")}${severity.map(function(label,row){return`<div class="side">${label}</div>${likelihood.map(function(_,col){const value=values[row*5+col]||0,level=value>=15?"high":value>=4?"medium":"low";return`<div class="${level}"><strong>${value}</strong></div>`;}).join("")}`;}).join("")}</div>`;}
function renderDecision(node,rows){const root=rows[0]||["Decision",0],branches=rows.slice(1);node.innerHTML=`<div class="ucc-plugin-decision"><div class="ucc-plugin-decision-root"><span>${esc(root[0])}</span><strong>${root[1]}</strong></div><div class="ucc-plugin-decision-branches">${branches.map(row=>`<div><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>`).join("")}</div></div>`;}
function renderNetwork(node,rows){const centre=rows[0]||["Network",0],nodes=rows.slice(1);node.innerHTML=`<div class="ucc-plugin-network"><div class="ucc-plugin-network-centre"><span>${esc(centre[0])}</span><strong>${centre[1]}</strong></div><div class="ucc-plugin-network-nodes">${nodes.map(row=>`<div><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>`).join("")}</div></div>`;}
function renderReconciliation(node,rows){node.innerHTML=`<div class="ucc-plugin-reconciliation">${rows.map((row,index)=>`<div><i>${index+1}</i><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>${index<rows.length-1?'<b aria-hidden="true">⇄</b>':""}`).join("")}</div>`;}
function renderLadder(node,rows){node.innerHTML=`<div class="ucc-plugin-ladder">${rows.map((row,index)=>`<div style="--ucc-step:${index}"><i>${index+1}</i><span>${esc(row[0])}</span><strong>${row[1]}</strong></div>`).join("")}</div>`;}
const CHART_PLUGINS=new Map();
function registerChartPlugin(type,renderer){if(type&&typeof renderer==="function")CHART_PLUGINS.set(String(type),renderer);}
registerChartPlugin("bar",(node,rows)=>renderBars(node,rows));
registerChartPlugin("donut",(node,rows)=>renderDonut(node,rows));
registerChartPlugin("funnel",(node,rows)=>renderFunnel(node,rows));
registerChartPlugin("lifecycle",(node,rows)=>renderLifecycle(node,rows));
registerChartPlugin("flow",(node,rows)=>renderLifecycle(node,rows));
registerChartPlugin("matrix",(node,rows)=>renderMatrix(node,rows));
registerChartPlugin("radar",(node,rows)=>renderRadar(node,rows));
registerChartPlugin("trend",(node,rows)=>renderTrend(node,rows));
registerChartPlugin("gauge",(node,rows)=>renderGauge(node,rows));
registerChartPlugin("admission-line",(node,rows)=>renderAdmissionLine(node,rows));
registerChartPlugin("admission-column",(node,rows)=>renderAdmissionColumns(node,rows));
registerChartPlugin("decision",(node,rows)=>renderDecision(node,rows));
registerChartPlugin("network",(node,rows)=>renderNetwork(node,rows));
registerChartPlugin("reconciliation",(node,rows)=>renderReconciliation(node,rows));
registerChartPlugin("ladder",(node,rows)=>renderLadder(node,rows));
registerChartPlugin("risk-matrix",(node,rows,chart)=>{const seed=rows.map(row=>Math.max(0,Math.round(row[1]))),values=[];for(let i=0;i<25;i++)values.push(seed.length?seed[i%seed.length]:0);renderRiskMatrix(node,{...chart,values});});
function renderChart(node,chart,rows){const type=chart.type||"bar",renderer=CHART_PLUGINS.get(type)||CHART_PLUGINS.get("bar");return renderer(node,rows,chart);}
window.UCCChartPlugins=Object.freeze({register:registerChartPlugin,has:type=>CHART_PLUGINS.has(type),types:()=>Array.from(CHART_PLUGINS.keys())});


const RESPONSE_ADAPTERS=new Map();
function registerResponseAdapter(criterionId,adapter){if(criterionId&&typeof adapter==="function")RESPONSE_ADAPTERS.set(criterionId,adapter);}
function summaryFromRows(rows){const list=Array.isArray(rows)?rows:[],available=list.filter(item=>item&&item.status==="available").length,total=list.length;return{available,total,issues:Math.max(0,total-available)};}
function baseResponseAdapter(message,context){const raw=message&&typeof message==="object"?message:{};const metrics=Array.isArray(raw.metrics)?raw.metrics:[],sources=Array.isArray(raw.sources)?raw.sources:[];return{...raw,ok:raw.ok===true,meta:{...(raw.meta||{}),subcriterion:raw.meta?.subcriterion||context.subcriterion},metrics,sources,questions:Array.isArray(raw.questions)?raw.questions:(Array.isArray(raw.qa)?raw.qa:[]),exceptions:Array.isArray(raw.exceptions)?raw.exceptions:[],data_quality:Array.isArray(raw.data_quality)?raw.data_quality:(Array.isArray(raw.quality)?raw.quality:[]),source_summary:raw.source_summary||summaryFromRows(sources),metric_summary:raw.metric_summary||summaryFromRows(metrics)};}
registerResponseAdapter("criterion_4",function(message,context){const adapted=baseResponseAdapter(message,context);adapted.questions=adapted.questions.length?adapted.questions:(Array.isArray(message?.management_questions)?message.management_questions:[]);adapted.data_quality=adapted.data_quality.length?adapted.data_quality:(Array.isArray(message?.quality_checks)?message.quality_checks:[]);return adapted;});
function adaptApiResponse(config,dashboard,payload,message){const criterionId=dashboard.dataset.demoDashboard,adapter=RESPONSE_ADAPTERS.get(criterionId)||baseResponseAdapter;return adapter(message,{criterionId,config,payload,subcriterion:payload.subcriterion});}


const STATE=new Map();
const SAFE_COMPLEX_TYPES=new Set(["donut","funnel","trend"]);
function dashboardState(dashboard){if(!STATE.has(dashboard))STATE.set(dashboard,{loading:false,result:null,error:null,logs:[],lastSection:""});return STATE.get(dashboard);}
function logEvent(dashboard,level,event,detail){const state=dashboardState(dashboard);state.logs.push({time:new Date().toISOString(),level,event,detail:String(detail||"")});if(state.logs.length>500)state.logs.shift();const count=dashboard.querySelector("[data-demo-log-count]");if(count)count.textContent=String(state.logs.length);}
function selectedFilterObject(dashboard){const output={};dashboard.querySelectorAll("[data-demo-filter]").forEach(input=>{if(input.value)output[input.dataset.demoFilter]=input.value;});return output;}
function apiSection(config,dashboard,tab){const state=dashboardState(dashboard);if(tab==="quality"||tab==="sources")return state.lastSection||config.defaultSection;const mapped=config.apiSections&&config.apiSections[tab];if(mapped&&tab!=="overview")state.lastSection=mapped;return mapped||state.lastSection||config.defaultSection;}
function callApi(config,dashboard,action="summary",extra={}){
return new Promise((resolve,reject)=>{
if(!(window.frappe&&frappe.call)){reject(new Error("Frappe API client is unavailable."));return;}
const payload={action,subcriterion:apiSection(config,dashboard,activeSection(dashboard)),filters:selectedFilterObject(dashboard),page_size:100};
Object.keys(extra||{}).forEach(key=>payload[key]=extra[key]);
logEvent(dashboard,"INFO","api_request",`${config.apiMethod} · ${payload.subcriterion} · ${action}`);
frappe.call({
method:config.apiMethod,
args:{payload:JSON.stringify(payload)},
callback(response){
const rawMessage=normaliseApiMessage(response);
const message=adaptApiResponse(config,dashboard,payload,rawMessage);
if(message&&message.ok){
logEvent(dashboard,"INFO","api_success",`${message.source_summary?.available||0}/${message.source_summary?.total||0} sources · ${message.metric_summary?.available||0}/${message.metric_summary?.total||0} metrics`);
resolve(message);
return;
}
const detail=message&&message.message?message.message:"Analytics response did not contain ok=true.";
logEvent(dashboard,"ERROR","api_invalid_response",detail);
reject(new Error(detail));
},
error(error){
const detail=apiErrorMessage(error);
logEvent(dashboard,"ERROR","api_error",detail);
reject(new Error(detail));
}
});
});
}
function setLoading(dashboard,active,progress=0,task="Loading live analytics"){const overlay=dashboard.querySelector("[data-demo-loading-overlay]");if(overlay)overlay.classList.toggle("hidden",!active);const title=dashboard.querySelector("[data-demo-loading-title]")||dashboard.querySelector("[data-demo-loading-overlay] strong");if(title)title.textContent=task;const fill=dashboard.querySelector("[data-demo-progress-fill]");if(fill)fill.style.width=Math.max(0,Math.min(100,progress))+"%";const value=dashboard.querySelector("[data-demo-progress-value]");if(value)value.textContent=Math.round(progress)+"%";const note=dashboard.querySelector("[data-demo-loading-overlay] .progress-text span:last-child");if(note)note.textContent="Permission-aware sources";}
function metricValue(metric){if(!metric||metric.status!=="available")return"—";const value=metric.value==null?0:metric.value;if(metric.unit==="SGD")return"SGD "+Number(value).toLocaleString();if(metric.unit==="rating")return String(value)+"/5";if(metric.unit==="percent")return String(value)+"%";return Number(value).toLocaleString();}
const DOCTYPE_DISPLAY_NAMES=Object.freeze({"Supplier Rating":"Provider Rating","Student Admission UCC":"Shortlisted Applicants","Student Group":"Module Class Details","Module Class Details":"Module Class Details","Student Batch Name":"Student Intake No","Student Intake No":"Student Intake No","Program":"Course","Course":"Module"});
function displayDoctypeName(doctype){return DOCTYPE_DISPLAY_NAMES[doctype]||doctype||"Source";}
function doctypeListRoute(doctype){return"/app/"+String(doctype||"").trim().toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");}
function metricById(result,metricId){return(result?.metrics||[]).find(item=>item.id===metricId)||null;}
function sourceCalculation(question,metric){
if(question?.source_logic)return question.source_logic;
if(question?.source)return question.source;
if(!metric)return"Live API calculation";
const fields=(metric.resolved_fields||[]).filter(Boolean);
const source=metric.doctype||metric.source||"Live source";
return fields.length?`${source}.${fields.join(" / ")}`:`${source} · ${metric.unit||"records"} calculation`;
}
function extendedQuestionRows(result,tab){
const base=(result?.questions||[]).map(row=>({...row}));
const used=new Set(base.map(row=>row.metric_id).filter(Boolean));
(result?.metrics||[]).forEach(metric=>{
if(!metric?.id||used.has(metric.id))return;
const available=metric.status==="available";
const count=Number(metric.record_count??metric.total??0);
base.push({
id:"extended-"+metric.id,
criterion:result?.meta?.subcriterion||result?.policy?.criterion||tab,
question:`What is the current ${String(metric.label||"metric").toLowerCase()}?`,
answer:available?`${metricValue(metric)} from ${count.toLocaleString()} matching record(s).`:`Unavailable: ${metric.message||String(metric.status||"required source or field is unavailable").replaceAll("_"," ")}`,
metric_id:metric.id,
status:metric.status||"unavailable",
confidence:available?"Live":"Unavailable",
doctype:metric.doctype||"",
source_logic:sourceCalculation(null,metric),
record_count:count
});
});
return base;
}
function metricRows(result,chartIndex,chart){
if(chart?.dataKey){
const grouped=result?.admission_intelligence?.charts?.[chart.dataKey];
if(Array.isArray(grouped))return grouped.map(item=>[item.label,finiteNumber(item.value,0),null,true]);
}
const metrics=(result?.metrics||[]).filter(item=>item.status==="available");
const title=String(chart?.title||"").toLowerCase();
const first=metrics[0]||null;
if(/source availability|evidence readiness|source readiness/.test(title)){
const ss=result?.source_summary||{},ms=result?.metric_summary||{};
return[
["Available sources",finiteNumber(ss.available,0),first,true],
["Source issues",finiteNumber(ss.issues,0),first,true],
["Available metrics",finiteNumber(ms.available,0),first,true],
["Metric issues",finiteNumber(ms.issues,0),first,true]
];
}
if(/status distribution|system health|control health|readiness/.test(title)&&metrics.length){
const unavailable=(result?.metrics||[]).filter(item=>item.status!=="available").length;
return[
["Available",metrics.length,metrics[0],true],
["Unavailable",unavailable,metrics[0],true],
["Sources",finiteNumber(result?.source_summary?.available,0),metrics[0],true],
["Exceptions",(result?.exceptions||[]).length,metrics[0],true]
];
}
if(/exception|gap|risk profile/.test(title)){
const exceptionMetrics=(result?.exceptions||[]).filter(item=>item.status==="available");
if(exceptionMetrics.length)return exceptionMetrics.slice(0,5).map(item=>[item.label,finiteNumber(item.value,0),item]);
}
if(!metrics.length)return[];
const size=Math.min(5,metrics.length),start=(chartIndex*size)%metrics.length,rows=[];
for(let i=0;i<size;i++){const metric=metrics[(start+i)%metrics.length];rows.push([metric.label,finiteNumber(metric.value,0),metric]);}
return rows;
}
function chartForLive(node,chart,rows){
node.dataset.visualRenderAttempted="1";
if(!rows.length){node.innerHTML='<div class="ucc-live-empty"><strong>No live metric is readable for this section</strong><span>Open Source Mapping Report to see the exact DocType, permission or field issue.</span><button type="button" data-ucc-open-mapping>Source mapping report</button></div>';return;}
const pairs=rows.map(row=>[row[0],finiteNumber(row[1],0)]).filter(row=>Number.isFinite(row[1]));
if(!pairs.length){node.innerHTML='<div class="ucc-live-empty"><strong>The returned metrics are not numeric</strong><span>The visual was stopped before an invalid SVG path could be produced.</span><button type="button" data-ucc-open-mapping>Source mapping report</button></div>';return;}
try{
return renderChart(node,chart,pairs);
}catch(error){
node.dataset.visualRenderError=error&&error.message?error.message:String(error);
node.innerHTML='<div class="ucc-visual-diagnostic"><strong>Visual data could not be rendered</strong><span>'+esc(node.dataset.visualRenderError)+' Open Source Mapping Report to check the mapped DocTypes and fields.</span><button type="button" data-ucc-open-mapping>Source mapping report</button></div>';
}
}
function renderLiveChartCard(dashboard, chart, index, result) {
    const chartNode = dashboard.querySelector(
        `[data-demo-chart="${CSS.escape(chart.id)}"]`
    );

    const card = chartNode?.closest("[data-demo-card]");

    if (!card) return;

    const heading = card.querySelector("h2");
    const description = card.querySelector(".ucc-card-description");

    if (heading) {
        heading.textContent = chart.title || "Live visual";
    }

    if (description) {
        description.textContent =
            chart.description || "Permission-aware live metrics.";
    }

    card._liveCardPending = {
        chart: chart,
        index: index,
        result: result
    };

    card.dataset.liveCardRendered = "";
}
function renderLiveChartCardNow(card){
if(!card||!card._liveCardPending||card.dataset.liveCardRendered==="1")return;
const{chart,index,result}=card._liveCardPending;
const rows=metricRows(result,index,chart),chartNode=card.querySelector("[data-demo-chart]"),tableBody=card.querySelector("[data-demo-chart-table-body]");
if(chartNode){chartNode.dataset.demoChartTitle=chart.title;chartNode.dataset.demoChartType=chart.type||"bar";chartForLive(chartNode,chart,rows);}
if(tableBody){
tableBody.innerHTML=rows.length?rows.map(row=>{const metric=row[2],synthetic=row[3]===true,value=synthetic?Number(row[1]||0).toLocaleString():metric?metricValue(metric):Number(row[1]||0).toLocaleString(),status=metric?.status||"available";return`<tr><td>${esc(row[0])}</td><td>${esc(value)}</td><td>${statusBadge(status)}</td></tr>`;}).join(""):'<tr><td colspan="3">No available metric for this visual.</td></tr>';
}
card.dataset.liveCardRendered="1";
}
function renderKpis(dashboard,config,result){const mount=dashboard.querySelector("[data-demo-kpis]");if(!mount)return;
if(dashboard.dataset.demoDashboard==="criterion_4"&&result?.meta?.subcriterion==="4.1.1"&&Array.isArray(result?.admission_intelligence?.kpis)){
const kpis=result.admission_intelligence.kpis;
mount.innerHTML=kpis.map(item=>{const suffix=item.unit==="percent"?"%":"";return`<article class="ucc-admission-kpi"><span>${esc(item.label)}</span><strong>${Number(item.value||0).toLocaleString(undefined,{maximumFractionDigits:2})}${suffix}</strong><small>Student Applicant · live calculation</small></article>`;}).join("");
return;
}
const metrics=(result?.metrics||[]),rows=metrics.slice(0,6);while(rows.length<6)rows.push(null);mount.innerHTML=rows.map((metric,index)=>{if(metric)return`<article><span>${esc(metric.label)}</span><strong>${esc(metricValue(metric))}</strong><small>${esc(metric.doctype||metric.source||"Live metric")} · ${esc(metric.status.replaceAll("_"," "))}</small></article>`;const summary=index%2===0?result?.source_summary:result?.metric_summary;return`<article><span>${index%2===0?"Sources available":"Metrics available"}</span><strong>${summary?summary.available+"/"+summary.total:"—"}</strong><small>Permission-aware readiness</small></article>`;}).join("");}
function renderQa(dashboard,result,tab){
const target=dashboard.querySelector(`[data-demo-qa="${CSS.escape(dashboard.dataset.demoDashboard+":"+((dashboardState(dashboard).lastPanel)||tab))}"]`)||dashboard.querySelector("[data-demo-panel]:not(.hidden) [data-demo-qa]");
if(!target)return;
const rows=extendedQuestionRows(result,tab);
target.innerHTML=rows.length?rows.map(row=>{
const metric=metricById(result,row.metric_id);
const available=(metric?.status||row.status)==="available";
const count=Number(metric?.record_count??metric?.total??row.record_count??0);
const doctype=metric?.doctype||row.doctype||"";
const answerAction=available&&row.metric_id
?`<button type="button" class="record-link ucc-qa-action" data-live-qa-records="${esc(row.metric_id)}" data-live-qa-title="${esc(row.question||metric?.label||"Matching records")}">View ${count.toLocaleString()} matching record${count===1?"":"s"} ↗</button>`
:"";
const sourceAction=doctype
?`<button type="button" class="source-doctype-link ucc-qa-action" data-live-source-doctype="${esc(doctype)}">Open ${esc(displayDoctypeName(doctype))} list ↗</button>`
:'<span class="source-unavailable">No readable source list</span>';
return`<tr><td>${esc(row.criterion||result?.meta?.subcriterion||result?.policy?.policy||tab)}</td><td>${esc(row.question)}</td><td><div>${esc(row.answer)}</div>${answerAction}</td><td><div>${esc(sourceCalculation(row,metric))}</div>${sourceAction}</td><td>${statusBadge(row.status)}</td></tr>`;
}).join(""):'<tr><td colspan="5">No management questions are configured for this section.</td></tr>';
}
function renderSources(dashboard,result){
const target=dashboard.querySelector(`[data-demo-sources="${CSS.escape(dashboard.dataset.demoDashboard)}"]`);
if(!target)return;
const rows=result?.sources||[];
target.innerHTML=rows.length?rows.map(row=>{
const doctype=row.doctype||"";
const sourceName=doctype||row.candidates?.join(" / ")||row.key;
const action=doctype?`<button type="button" class="source-doctype-link ucc-qa-action" data-live-source-doctype="${esc(doctype)}">Open ${esc(displayDoctypeName(doctype))} list ↗</button>`:"";
return`<tr><td><div>${esc(sourceName)}</div>${action}</td><td>${esc(row.key||"Source")}</td><td>${statusBadge(row.status)} ${esc(row.message||"")}</td><td>${Number(row.count||0).toLocaleString()}</td></tr>`;
}).join(""):'<tr><td colspan="4">No source definitions returned.</td></tr>';
}
function renderQuality(dashboard,result){const target=dashboard.querySelector(`[data-demo-quality="${CSS.escape(dashboard.dataset.demoDashboard)}"]`);if(!target)return;const rows=result?.data_quality||[];target.innerHTML=rows.length?rows.map(row=>`<tr><td>${esc(row.check)}</td><td>${esc(row.source)}</td><td>${statusBadge(row.status)}</td><td>${esc(row.detail)}</td></tr>`).join(""):'<tr><td>Live source and metric checks</td><td>0</td><td>'+statusBadge("available")+'</td><td>No readiness issue returned.</td></tr>';}
function renderReadiness(dashboard,config,result){const notice=dashboard.querySelector("[data-demo-readiness]"),title=dashboard.querySelector("[data-demo-readiness-title]"),copy=dashboard.querySelector("[data-demo-readiness-copy]");if(!result){if(notice)notice.dataset.status="loading";if(title)title.textContent=`Loading Criterion ${config.number} analytics…`;if(copy)copy.textContent="Waiting for the live data connection and current-user permission checks.";return;}const ss=result.source_summary||{},ms=result.metric_summary||{},sA=ss.available||0,sT=ss.total||0,mA=ms.available||0,mT=ms.total||0,issues=Math.max(0,sT-sA)+Math.max(0,mT-mA);if(notice)notice.dataset.status=issues?"warning":"available";if(title)title.textContent=`Criterion ${config.number} live analytics active${issues?" with limitations":""}.`;if(copy)copy.textContent=`Live data connected · ${sA} of ${sT} sources available · ${mA} of ${mT} metrics available${issues?` · ${issues} item${issues===1?"":"s"} need review`:""}`;}
function renderError(dashboard,config,error){const notice=dashboard.querySelector("[data-demo-readiness]"),title=dashboard.querySelector("[data-demo-readiness-title]"),copy=dashboard.querySelector("[data-demo-readiness-copy]");if(notice)notice.dataset.status="error";if(title)title.textContent=`Criterion ${config.number} live API unavailable.`;if(copy)copy.textContent=error.message||String(error);const mount=dashboard.querySelector("[data-demo-kpis]");if(mount)mount.innerHTML=`<article><span>API status</span><strong>Unavailable</strong><small>${esc(error.message||error)}</small></article>`;}
function updateDashboardIdentity(dashboard,config,tab){
const isAdmission=dashboard.dataset.demoDashboard==="criterion_4"&&tab==="4.1.1";
dashboard.classList.toggle("ucc-admission-intelligence",isAdmission);
const kicker=dashboard.querySelector(".ucc-criterion-kicker"),heading=dashboard.querySelector(".hero-copy h1"),description=dashboard.querySelector(".hero-copy p");
if(isAdmission){if(kicker)kicker.textContent="EDUTRUST CRITERION 4.1.1";if(heading)heading.textContent="Admission Intelligence";if(description)description.textContent="Live admission analytics for applicants, approvals, enrolment conversion, programmes, countries, agents and counselling duration.";}
else{if(kicker)kicker.textContent=`EDUTRUST CRITERION ${config.number}`;if(heading)heading.textContent=`Criterion ${config.number} · ${config.title}`;if(description)description.textContent=config.description;}
const panelHeading=dashboard.querySelector(`[data-demo-panel="${CSS.escape((config.panelMap&&config.panelMap[tab])||tab)}"] .ucc-management-panel .panel-head h2`);
if(panelHeading)panelHeading.textContent=isAdmission?"Admissions Insights and Data-Based Answers":"Management Questions and Data-Based Answers";
}
function renderDashboard(dashboard){const config=CONFIG[dashboard.dataset.demoDashboard],state=dashboardState(dashboard),result=state.result;if(!config)return;const tab=activeSection(dashboard);updateDashboardIdentity(dashboard,config,tab);if(state.error&&!result){renderError(dashboard,config,state.error);return;}const section=sectionDefinition(config,tab),liveDefinitions=(LIVE_VISUAL_EXPANSION[dashboard.dataset.demoDashboard]?.[tab]||section?.charts||[]);renderKpis(dashboard,config,result);liveDefinitions.forEach((chart,index)=>renderLiveChartCard(dashboard,chart,chart.i??index,result));dashboard.querySelectorAll(`[data-live-section="${CSS.escape(tab)}"] [data-demo-card]`).forEach(renderLiveChartCardNow);renderQa(dashboard,result,tab);renderSources(dashboard,result);renderQuality(dashboard,result);renderReadiness(dashboard,config,result);}
async function loadLive(dashboard,force=false){const config=CONFIG[dashboard.dataset.demoDashboard],state=dashboardState(dashboard),section=apiSection(config,dashboard,activeSection(dashboard));ensureLiveSectionCards(dashboard,config,activeSection(dashboard));if(state.loading)return;if(!force&&state.result&&state.result.meta?.subcriterion===section){renderDashboard(dashboard);return;}state.loading=true;state.error=null;setLoading(dashboard,true,15,`Loading ${section}`);try{const result=await callApi(config,dashboard,"summary");setLoading(dashboard,true,80,"Rendering live analytics");state.result=result;state.error=null;renderDashboard(dashboard);setLoading(dashboard,true,100,"Live analytics ready");setTimeout(()=>setLoading(dashboard,false),150);}catch(error){state.error=error;logEvent(dashboard,"ERROR","api_failure",error.message||error);renderDashboard(dashboard);setLoading(dashboard,false);}finally{state.loading=false;}}
function showTab(dashboard,tab){const config=CONFIG[dashboard.dataset.demoDashboard];dashboard.dataset.demoActiveTab=tab;dashboard.querySelectorAll("[data-demo-tab]").forEach(button=>button.classList.toggle("active",button.dataset.demoTab===tab));const panelKey=(config.panelMap&&config.panelMap[tab])||tab;dashboardState(dashboard).lastPanel=panelKey;dashboard.querySelectorAll("[data-demo-panel]").forEach(panel=>panel.classList.toggle("hidden",panel.dataset.demoPanel!==panelKey));ensureLiveSectionCards(dashboard,config,tab);syncLiveSectionVisibility(dashboard,tab);if(tab!=="quality"&&tab!=="sources")loadLive(dashboard);else renderDashboard(dashboard);}
function allQaRows(result){return extendedQuestionRows(result,result?.meta?.subcriterion||"section").map(row=>[row.criterion,row.question,row.answer,sourceCalculation(row,metricById(result,row.metric_id)),row.status]);}
function allExceptionRows(result){return(result?.exceptions||[]).map(row=>[row.id,row.label,metricValue(row),row.status,row.doctype||row.source]);}
function ensureModal(){let modal=platform.querySelector("[data-demo-modal]");if(modal)return modal;modal=document.createElement("div");modal.className="ucc-demo-modal";modal.dataset.demoModal="1";modal.hidden=true;modal.innerHTML=`<div class="ucc-demo-modal-card"><header><div><strong data-demo-modal-title>Analytics details</strong><span>Permission-aware live data</span></div><button type="button" data-demo-modal-close aria-label="Close">×</button></header><div class="ucc-demo-modal-body" data-demo-modal-body></div></div>`;platform.appendChild(modal);modal.querySelector("[data-demo-modal-close]").addEventListener("click",()=>modal.hidden=true);modal.addEventListener("click",event=>{if(event.target===modal)modal.hidden=true;});return modal;}
function openModal(title,body){const modal=ensureModal();modal.querySelector("[data-demo-modal-title]").textContent=title;modal.querySelector("[data-demo-modal-body]").innerHTML=body;modal.hidden=false;}
function tableFromRows(rows){if(!rows||!rows.length)return'<div class="ucc-live-empty"><strong>No matching records</strong><span>The source is readable but no records matched the current filter.</span></div>';const columns=Array.from(new Set(rows.flatMap(row=>Object.keys(row))));return`<div class="table-wrap"><table><thead><tr>${columns.map(col=>`<th>${esc(col)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(col=>`<td>${esc(row[col])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;}
async function openMetricRecords(config,dashboard,metric,title){
if(!metric){openModal("Live records","No available metric is mapped to this result.");return;}
openModal("Loading live records",`<div class="ucc-demo-modal-note">${esc(title||metric.label)}</div>`);
try{
const response=await callApi(config,dashboard,"drilldown",{metric_id:metric.id,page:1,page_size:100});
openModal(title||metric.label,`<div class="ucc-demo-modal-note"><strong>${esc(response.drilldown?.total||0)} matching record(s)</strong><br>${esc(response.drilldown?.doctype||metric.doctype||"")}</div>${tableFromRows(response.drilldown?.rows||[])}`);
}catch(error){openModal("Drill-down unavailable",esc(error.message||error));}
}
async function openRecords(config,chartId,dashboard){
const result=dashboardState(dashboard).result,tab=activeSection(dashboard),section=sectionDefinition(config,tab),definitions=(LIVE_VISUAL_EXPANSION[dashboard.dataset.demoDashboard]?.[tab]||section?.charts||[]),index=Math.max(0,definitions.findIndex(item=>item.id===chartId)),chart=definitions[index];
if(/readiness|source availability|status distribution|system health|control health/i.test(chart?.title||"")){openReadiness(config,dashboard);return;}
const rows=metricRows(result,index,chart),metric=chart?.metricId?metricById(result,chart.metricId):rows.find(row=>row[2])?.[2];
return openMetricRecords(config,dashboard,metric,metric?.label||chart?.title||"Live records");
}
function openReadiness(config,dashboard){
const result=dashboardState(dashboard).result;
if(!result){openModal("Readiness","The live API has not returned a result.");return;}
const policy=result.policy||{},sources=result.sources||[],metrics=result.metrics||[];
openModal(`Criterion ${config.number} readiness`,`<div class="ucc-demo-modal-note"><strong>Criterion ${config.number} data readiness</strong><br>Source and metric status reflects the current user's permissions.</div><div class="grid2"><section><h3>Sources</h3><div class="table-wrap"><table><thead><tr><th>Source</th><th>Records</th><th>Status</th></tr></thead><tbody>${sources.map(row=>{const doctype=row.doctype||"";const action=doctype?`<button type="button" class="source-doctype-link ucc-qa-action" data-live-source-doctype="${esc(doctype)}">Open ${esc(displayDoctypeName(doctype))} list ↗</button>`:"";return`<tr><td><div>${esc(doctype||row.candidates?.join(" / ")||row.key)}</div>${action}</td><td>${row.count||0}</td><td>${statusBadge(row.status)}</td></tr>`;}).join("")}</tbody></table></div></section><section><h3>Metrics</h3><div class="table-wrap"><table><thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead><tbody>${metrics.map(item=>`<tr><td>${esc(item.label)}</td><td>${esc(metricValue(item))}</td><td>${statusBadge(item.status)}</td></tr>`).join("")}</tbody></table></div></section></div>`);
}
function showDiagnostics(config,dashboard){const state=dashboardState(dashboard),result=state.result,logs=state.logs;openModal(`Criterion ${config.number} diagnostics`,`<div class="table-wrap"><table><thead><tr><th>Time</th><th>Level</th><th>Event</th><th>Detail</th></tr></thead><tbody>${logs.map(row=>`<tr><td>${esc(row.time)}</td><td>${statusBadge(row.level)}</td><td>${esc(row.event)}</td><td>${esc(row.detail)}</td></tr>`).join("")||'<tr><td colspan="4">No diagnostic events.</td></tr>'}</tbody></table></div><div class="ucc-demo-modal-note">API: ${esc(config.apiMethod)} · Section: ${esc(result?.meta?.subcriterion||apiSection(config,dashboard,activeSection(dashboard)))}</div>`);}
async function handleAction(dashboard,action){const config=CONFIG[dashboard.dataset.demoDashboard],state=dashboardState(dashboard),result=state.result;if(action==="dismiss-readiness"){const notice=dashboard.querySelector("[data-demo-readiness]");if(notice){notice.dataset.dismissed="1";notice.hidden=true;}return;}if(action==="refresh")await loadLive(dashboard,true);if(action==="export-qa"){const rows=[["Section","Question","Answer","Source","Status"],...allQaRows(result)];download(`criterion_${config.number}_live_qa.csv`,rows.map(row=>row.map(csvCell).join(",")).join("\n"));}if(action==="export-exceptions"){const rows=[["Metric","Label","Value","Status","Source"],...allExceptionRows(result)];download(`criterion_${config.number}_live_exceptions.csv`,rows.map(row=>row.map(csvCell).join(",")).join("\n"));}if(action==="export-table"){const rows=[["Metric","Value","Unit","Status","Source"],...(result?.metrics||[]).map(item=>[item.label,item.value,item.unit,item.status,item.doctype||item.source])];download(`criterion_${config.number}_${result?.meta?.subcriterion||"section"}_live_metrics.csv`,rows.map(row=>row.map(csvCell).join(",")).join("\n"));}if(action==="copy-link"){const url=new URL(location.href);url.searchParams.set("dashboard",dashboard.dataset.demoDashboard);url.searchParams.set("live_tab",activeSection(dashboard));navigator.clipboard?.writeText(url.toString()).catch(()=>{});}if(action==="diagnostics")showDiagnostics(config,dashboard);if(action==="readiness")openReadiness(config,dashboard);}
mountUnifiedDashboards();
platform.querySelectorAll("[data-demo-dashboard]").forEach(function(dashboard){const config=CONFIG[dashboard.dataset.demoDashboard];if(!config)return;ensureLiveVisualCards(dashboard,config);syncLiveSectionVisibility(dashboard,"overview");dashboard.dataset.liveApi="1";dashboard.querySelectorAll("[data-demo-tab]").forEach(button=>button.addEventListener("click",()=>showTab(dashboard,button.dataset.demoTab)));dashboard.querySelectorAll("[data-demo-filter]").forEach(input=>input.addEventListener("change",()=>loadLive(dashboard,true)));dashboard.addEventListener("ucc:live-tool-action",function(event){const action=event.detail&&event.detail.action;const mapped=action==="export-current"?"export-table":action;if(mapped)handleAction(dashboard,mapped);});dashboard.addEventListener("click",function(event){
const sourceButton=event.target.closest("[data-live-source-doctype]");
if(sourceButton){
event.preventDefault();
event.stopPropagation();
const doctype=sourceButton.dataset.liveSourceDoctype;
if(doctype)window.open(doctypeListRoute(doctype),"_blank","noopener");
return;
}
const questionButton=event.target.closest("[data-live-qa-records]");
if(questionButton){
event.preventDefault();
event.stopPropagation();
const metric=metricById(dashboardState(dashboard).result,questionButton.dataset.liveQaRecords);
openMetricRecords(config,dashboard,metric,questionButton.dataset.liveQaTitle||metric?.label||"Matching records");
return;
}
const actionButton=event.target.closest("[data-demo-action]");
if(actionButton){event.preventDefault();event.stopPropagation();handleAction(dashboard,actionButton.dataset.demoAction);return;}
const drill=event.target.closest("[data-demo-drill]");
if(drill){event.preventDefault();openRecords(config,drill.dataset.demoDrill,dashboard);return;}
const viewButton=event.target.closest("[data-demo-view]");
if(viewButton){const card=viewButton.closest("[data-demo-card]");if(!card)return;renderLiveChartCardNow(card);card.querySelectorAll("[data-demo-view]").forEach(button=>button.classList.toggle("active",button===viewButton));const diagram=card.querySelector("[data-demo-chart]"),table=card.querySelector("[data-demo-chart-table]");if(diagram)diagram.classList.toggle("hidden",viewButton.dataset.demoView!=="diagram");if(table)table.classList.toggle("hidden",viewButton.dataset.demoView!=="table");}
});dashboard.dataset.demoActiveTab="overview";dashboard.querySelectorAll("[data-demo-panel]").forEach(panel=>panel.classList.toggle("hidden",panel.dataset.demoPanel!=="overview"));if(!dashboard.classList.contains("ucc-hidden"))loadLive(dashboard);else renderReadiness(dashboard,config,null);});platform.addEventListener("ucc:dashboard-change",event=>{const id=event.detail&&event.detail.dashboard;if(!id)return;const dashboard=platform.querySelector(`[data-demo-dashboard="${CSS.escape(id)}"]`);if(dashboard)loadLive(dashboard);});
platform.addEventListener("click",function(event){
const sourceButton=event.target.closest("[data-live-source-doctype]");
if(!sourceButton||sourceButton.closest("[data-demo-dashboard]"))return;
event.preventDefault();
const doctype=sourceButton.dataset.liveSourceDoctype;
if(doctype)window.open(doctypeListRoute(doctype),"_blank","noopener");
});
window.UCCLiveAnalytics=Object.freeze({config:CONFIG,registerResponseAdapter:registerResponseAdapter,registerChartPlugin:registerChartPlugin,refresh:function(criterion){const dashboard=platform.querySelector(`[data-demo-dashboard="${CSS.escape(criterion)}"]`);if(dashboard)return loadLive(dashboard,true);},showTab:function(criterion,tab){const dashboard=platform.querySelector(`[data-demo-dashboard="${CSS.escape(criterion)}"]`);if(dashboard)showTab(dashboard,tab);}});
})();
/* UCC DIAGRAM EXPLORER v1.9.9 */
(function (global) {
"use strict";

const platformRoot = typeof root_element !== "undefined"
? root_element.querySelector("#uccIntelligencePlatform")
: document.querySelector("#uccIntelligencePlatform");

if (!platformRoot || platformRoot.dataset.exploreReady === "1") return;
platformRoot.dataset.exploreReady = "1";

const exploreRoot = platformRoot.querySelector("[data-ucc-explore]");
if (!exploreRoot) return;

const listNode = exploreRoot.querySelector("[data-ucc-explore-list]");
const searchNode = exploreRoot.querySelector("[data-ucc-explore-search]");
const sectionNode = exploreRoot.querySelector("[data-ucc-explore-section]");
const typeNode = exploreRoot.querySelector("[data-ucc-explore-type]");
const resultNode = exploreRoot.querySelector("[data-ucc-explore-result-count]");
const clearButton = exploreRoot.querySelector("[data-ucc-explore-clear]");
const dashboardSelect = platformRoot.querySelector("#uccDashboardSelect");
const workspaceButtons = Array.from(platformRoot.querySelectorAll("[data-ucc-workspace]"));

const parentTabMap = Object.freeze({});

let entries = [];
let lastExploreScroll = 0;
let highlightedCard = null;

const returnButton = document.createElement("button");
returnButton.type = "button";
returnButton.className = "ucc-explore-return";
returnButton.textContent = "← Back to Explore";
returnButton.hidden = true;
platformRoot.appendChild(returnButton);

function text(value) {
return String(value == null ? "" : value).replace(/\s+/g, " ").trim();
}

function titleFrom(node) {
const card = node.closest("article, .panel");
const heading = card ? card.querySelector("h2,h3") : null;
return text(heading ? heading.textContent : node.dataset.chart || node.dataset.c4Visual || "Untitled visual");
}

function sectionLabel(entry) {
if (entry.kind === "demo") {
const button = platformRoot.querySelector(`[data-dashboard-panel="${CSS.escape(entry.dashboard)}"] [data-demo-tab="${CSS.escape(entry.panel || "overview")}"]`);
return text(button ? button.textContent : entry.panel || "Live foundation");
}
const button = platformRoot.querySelector(`[data-tab="${CSS.escape(parentTabMap[entry.panel] || entry.panel || "overview")}"]`);
const local = entry.panel && entry.panel !== (parentTabMap[entry.panel] || entry.panel)
? platformRoot.querySelector(`[data-section="${CSS.escape(entry.panel)}"]`)
: null;
return text(local ? local.textContent : button ? button.textContent : entry.panel || "Criterion 5");
}

function inferType(id, title) {
const value = `${id} ${title}`.toLowerCase();
const rules = [
["network", ["network"]],
["timeline", ["timeline", "trend", "aging", "recency"]],
["funnel", ["funnel", "flow", "lifecycle", "cycle"]],
["donut", ["donut", "ring", "orbit"]],
["heatmap", ["heatmap", "matrix"]],
["bubble", ["bubble", "constellation"]],
["radial", ["radial", "radar"]],
["decision", ["decision"]],
["ladder", ["ladder"]],
["reconciliation", ["reconciliation"]]
];
for (const [type, terms] of rules) {
if (terms.some(term => value.includes(term))) return type;
}
return "chart";
}

function sourceHint(node) {
const card = node.closest("article, .panel");
if (!card) return "Configured live source";
const sourceLink = card.querySelector(".source-doctype-link,.source-link,[data-source]");
return text(sourceLink ? sourceLink.textContent : "Configured live source");
}

function createEntry(node, dashboard, kind) {
const id = kind === "c4" ? node.dataset.c4Visual : kind === "demo" ? node.dataset.demoChart : node.dataset.chart;
if (!id) return null;
const panelNode = kind === "demo" ? node.closest("[data-demo-panel]") : node.closest("[data-panel]");
const title = kind === "demo" ? text(node.dataset.demoChartTitle || titleFrom(node)) : titleFrom(node);
const entry = {
key: `${dashboard}:${kind}:${id}`,id,kind,dashboard,node,title,
panel: kind === "demo" ? panelNode?.dataset.demoPanel || "overview" : panelNode?.dataset.panel || "overview",
c511Panel: "",
localPanel: node.closest("[data-local-panel]")?.dataset.localPanel || "",
type: kind === "demo" ? node.dataset.demoChartType || "live-foundation" : inferType(id, title),
source: kind === "demo" ? "Permission-aware live API foundation" : sourceHint(node),
description: ""
};
entry.section = sectionLabel(entry);
return entry;
}

function buildRegistry() {
const registry = new Map();

Object.entries(global.UCCLiveVisualDefinitions || {}).forEach(([dashboard, sections]) => {
Object.entries(sections || {}).forEach(([panel, definitions]) => {
(definitions || []).forEach(definition => {
if (definition.enabled === false) return;
const entry = {
key: `${dashboard}:demo:${definition.id}`,
id: definition.id,
kind: "demo",
dashboard,
node: platformRoot.querySelector(`[data-demo-chart="${CSS.escape(definition.id)}"]`),
title: text(definition.title),
panel,
c511Panel: "",
localPanel: "",
type: definition.type || inferType(definition.id, definition.title),
source: "Permission-aware live API metrics",
description: text(definition.description || "")
};
entry.section = sectionLabel(entry);
if (!registry.has(entry.key)) registry.set(entry.key, entry);
});
});
});

entries = Array.from(registry.values()).sort((a, b) =>
a.section.localeCompare(b.section) || a.title.localeCompare(b.title)
);

["criterion_1", "criterion_2", "criterion_3", "criterion_4", "criterion_5", "criterion_6", "criterion_7"].forEach(dashboard => {
const count = exploreRoot.querySelector(`[data-ucc-explore-count="${dashboard}"]`);
if (count) count.textContent = String(entries.filter(entry => entry.dashboard === dashboard).length);
});
}

function currentDashboard() {
return dashboardSelect ? dashboardSelect.value : "criterion_5";
}

function fillFilters() {
const dashboard = currentDashboard();
const dashboardEntries = entries.filter(entry => entry.dashboard === dashboard);
const previousSection = sectionNode.value;
const previousType = typeNode.value;
const sections = Array.from(new Set(dashboardEntries.map(entry => entry.section))).sort();
const types = Array.from(new Set(dashboardEntries.map(entry => entry.type))).sort();

sectionNode.innerHTML = '<option value="">All sections</option>' +
sections.map(value => `<option value="${value.replace(/"/g, "&quot;")}">${value}</option>`).join("");
typeNode.innerHTML = '<option value="">All visual types</option>' +
types.map(value => `<option value="${value.replace(/"/g, "&quot;")}">${value}</option>`).join("");

if (sections.includes(previousSection)) sectionNode.value = previousSection;
if (types.includes(previousType)) typeNode.value = previousType;
}

function filteredEntries() {
const dashboard = currentDashboard();
const query = text(searchNode.value).toLowerCase();
return entries.filter(entry =>
entry.dashboard === dashboard &&
(!query || `${entry.title} ${entry.section} ${entry.type} ${entry.source}`.toLowerCase().includes(query)) &&
(!sectionNode.value || entry.section === sectionNode.value) &&
(!typeNode.value || entry.type === typeNode.value)
);
}

function renderList() {
const dashboard = currentDashboard();
const liveDashboard = dashboard === "criterion_4" || dashboard === "criterion_5";
const rows = filteredEntries();
resultNode.textContent = `${rows.length} live diagram${rows.length === 1 ? "" : "s"}`;

const grouped = rows.reduce((result, entry) => {
(result[entry.section] ||= []).push(entry);
return result;
}, {});

listNode.innerHTML = Object.entries(grouped).map(([section, sectionEntries]) => `
<section class="ucc-explore-group">
<h2>${section}</h2>
${sectionEntries.map(entry => `
<button type="button" class="ucc-explore-item" data-ucc-explore-entry="${entry.key}">
<span>
<strong>${entry.title}</strong>
${entry.description ? `<small>${entry.description}</small>` : ""}
<small>${entry.source}</small>
</span>
<em>${entry.type}</em>
</button>
`).join("")}
</section>
`).join("") || '<div class="ucc-explore-empty">No diagrams match the current search and filters.</div>';
}

function chooseDashboard(dashboard) {
if (!dashboardSelect) return;
dashboardSelect.value = dashboard;
dashboardSelect.dispatchEvent(new Event("change", { bubbles: true }));
}

function resolveEntryNode(entry) {
if (entry.node && entry.node.isConnected) return entry.node;
if (entry.kind === "demo") {
entry.node = platformRoot.querySelector(`[data-demo-chart="${CSS.escape(entry.id)}"]`);
}
return entry.node || null;
}

function revealNestedViews(entry) {
const node = resolveEntryNode(entry);
if (entry.kind === "demo") {
window.UCCLiveAnalytics?.showTab(entry.dashboard, entry.panel || "overview");
node?.closest("[data-demo-card]")?.querySelector('[data-demo-view="diagram"]')?.click();
return;
}
if (entry.localPanel) {
const panel = node?.closest("[data-panel]");
const button = panel ? panel.querySelector(
`[data-local-tab="${CSS.escape(entry.localPanel)}"]`
) : null;
if (button) button.click();
}
const card = node?.closest("article, .panel");
if (card) {
const diagramButton = card.querySelector('[data-card-view="diagram"]');
if (diagramButton) diagramButton.click();
}
}

function highlightEntry(entry, attempt = 0) {
const node = resolveEntryNode(entry);
if (!node) {
if (attempt < 24) setTimeout(() => highlightEntry(entry, attempt + 1), 250);
else if (window.frappe && frappe.show_alert) frappe.show_alert({ message: "The selected visual could not be mounted. Open Source Mapping Report for details.", indicator: "orange" });
return;
}
if (highlightedCard) highlightedCard.classList.remove("ucc-explore-highlight");
highlightedCard = node.closest("article, .panel") || node;
highlightedCard.classList.add("ucc-explore-highlight");
highlightedCard.scrollIntoView({ behavior: "smooth", block: "center" });
setTimeout(() => highlightedCard?.classList.remove("ucc-explore-highlight"), 4200);
returnButton.hidden = false;
}

function openLiveEntry(entry) {
lastExploreScroll = Math.max(
Number(window.scrollY || 0),
Number(document.documentElement?.scrollTop || 0)
);
platformRoot.querySelector('[data-ucc-workspace="analytics"]')?.click();
chooseDashboard(entry.dashboard);

const finish = () => {
revealNestedViews(entry);
setTimeout(() => {
revealNestedViews(entry);
highlightEntry(entry);
window.dispatchEvent(new Event("resize"));
}, 220);
};

if (entry.kind === "demo") {
window.UCCLiveAnalytics?.showTab(entry.dashboard, entry.panel || "overview");
setTimeout(finish, 120);
} else {
setTimeout(finish, 120);
}
}

listNode.addEventListener("click", event => {
const switchButton = event.target.closest("[data-ucc-explore-switch]");
if (switchButton) {
chooseDashboard(switchButton.dataset.uccExploreSwitch);
fillFilters();
renderList();
return;
}
const button = event.target.closest("[data-ucc-explore-entry]");
if (!button) return;
const entry = entries.find(item => item.key === button.dataset.uccExploreEntry);
if (entry) openLiveEntry(entry);
});

function resetFilters() {
searchNode.value = "";
sectionNode.value = "";
typeNode.value = "";
renderList();
}

searchNode.addEventListener("input", renderList);
sectionNode.addEventListener("change", renderList);
typeNode.addEventListener("change", renderList);
["pointerdown", "mousedown", "click", "keydown", "keyup", "keypress", "focus", "focusin"].forEach(function (eventName) {
searchNode.addEventListener(eventName, function (event) {
event.stopPropagation();
if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
});
});
searchNode.addEventListener("keydown", function (event) {
if (event.key === "Escape") {
event.preventDefault();
resetFilters();
searchNode.focus();
}
});
clearButton.addEventListener("pointerdown", function (event) {
event.stopPropagation();
});
clearButton.addEventListener("click", function (event) {
event.preventDefault();
event.stopPropagation();
resetFilters();
searchNode.focus();
});

dashboardSelect?.addEventListener("change", () => {
fillFilters();
renderList();
});

workspaceButtons.forEach(button => {
button.addEventListener("click", () => {
if (button.dataset.uccWorkspace === "explore") {
returnButton.hidden = true;
setTimeout(() => window.scrollTo({ top: lastExploreScroll, behavior: "smooth" }), 0);
}
});
});

returnButton.addEventListener("click", () => {
platformRoot.querySelector('[data-ucc-workspace="explore"]')?.click();
});

buildRegistry();
fillFilters();
renderList();

global.UCCExplore = Object.freeze({
entries: () => entries.slice(),
openEntry: keyOrEntry => {
const entry = typeof keyOrEntry === "string" ? entries.find(item => item.key === keyOrEntry) : keyOrEntry;
if (entry) openLiveEntry(entry);
},
openNavigator: dashboard => {
if (dashboard) chooseDashboard(dashboard);
platformRoot.querySelector('[data-ucc-workspace="explore"]')?.click();
setTimeout(() => searchNode?.focus(), 80);
},
rebuild: () => {
buildRegistry();
fillFilters();
renderList();
}
});
})(window);
/* UCC universal visual diagnostics v1.9.9 */
(function (global) {
"use strict";

const platform = typeof root_element !== "undefined"
? root_element.querySelector("#uccIntelligencePlatform")
: document.querySelector("#uccIntelligencePlatform");

if (!platform || platform.dataset.universalVisualDiagnosticsReady === "1") return;
platform.dataset.universalVisualDiagnosticsReady = "1";

const expectedCounts = Object.freeze(Object.fromEntries(Object.entries(global.UCCLiveVisualDefinitions || {}).map(([criterion, sections]) => [criterion, Object.values(sections || {}).reduce((total, definitions) => total + (definitions || []).filter(item => item.enabled !== false).length, 0)])));
const criterionLabels = Object.freeze({
criterion_1: "Criterion 1",
criterion_2: "Criterion 2",
criterion_3: "Criterion 3",
criterion_4: "Criterion 4",
criterion_5: "Criterion 5",
criterion_6: "Criterion 6",
criterion_7: "Criterion 7"
});
const issues = [];
const blankFirstSeen = new WeakMap();
let lastMappingResult = null;

function clean(value) {
return String(value == null ? "" : value).replace(/\s+/g, " ").trim();
}
function esc(value) {
return String(value == null ? "" : value)
.replaceAll("&", "&amp;")
.replaceAll("<", "&lt;")
.replaceAll(">", "&gt;")
.replaceAll('"', "&quot;");
}
function notify(message, indicator) {
if (global.frappe && frappe.show_alert) frappe.show_alert({ message, indicator: indicator || "blue" });
}
function registry() {
return global.UCCExplore && typeof global.UCCExplore.entries === "function"
? global.UCCExplore.entries()
: [];
}
function updateExploreCounts() {
Object.keys(expectedCounts).forEach(dashboard => {
const countNode = platform.querySelector('[data-ucc-explore-count="' + dashboard + '"]');
if (countNode) countNode.textContent = String(registry().filter(entry => entry.dashboard === dashboard).length);
});
}

document.addEventListener("keydown", event => {
if (event.key === "Escape") closeSourceMapping();
});

const mappingDialog = document.createElement("section");
mappingDialog.className = "ucc-source-mapping-dialog";
mappingDialog.hidden = true;
mappingDialog.setAttribute("role", "dialog");
mappingDialog.setAttribute("aria-modal", "true");
mappingDialog.setAttribute("aria-label", "Source mapping report");
mappingDialog.innerHTML = '<div class="ucc-source-mapping-card"><header><div><h2>Source Mapping Report</h2><p>Installed DocTypes, readable fallbacks, metadata, detected fields and visual rendering issues for the signed-in user.</p></div><div class="ucc-source-mapping-actions"><button type="button" data-source-mapping-copy>Copy report</button><button type="button" data-source-mapping-close aria-label="Close">×</button></div></header><div class="ucc-source-mapping-body" data-source-mapping-body><div class="ucc-visual-diagnostic"><strong>Loading source diagnostics…</strong><span>The report checks only approved UCC source candidates.</span></div></div></div>';
platform.appendChild(mappingDialog);
const mappingBody = mappingDialog.querySelector("[data-source-mapping-body]");

function statusClass(status) {
if (["available", "resolved"].includes(status)) return "ucc-source-status-good";
if (["fallback", "permission_denied", "field_mismatch"].includes(status)) return "ucc-source-status-warning";
return "ucc-source-status-risk";
}
function visualCountSummary() {
return Object.keys(expectedCounts).map(dashboard => {
const actual = registry().filter(entry => entry.dashboard === dashboard).length;
return { dashboard, actual, expected: expectedCounts[dashboard], status: actual === expectedCounts[dashboard] ? "available" : "count_mismatch" };
});
}
function normaliseSourceRows(result) {
const groups = Array.isArray(result?.source_groups) ? result.source_groups : [];
if (groups.length) return groups;
return (result?.sources || []).map(source => ({
key: source.key || source.doctype,
label: source.label || source.doctype,
candidates: source.candidates || [source.doctype],
resolved_doctype: source.resolved_doctype || (source.readable ? source.doctype : ""),
status: source.status || (source.readable ? "available" : source.exists ? "permission_denied" : "unavailable"),
detail: source.detail || source.error || "",
attempts: source.attempts || []
}));
}
function renderMapping(result) {
lastMappingResult = result || {};
const rows = normaliseSourceRows(result);
const countRows = visualCountSummary();
const unresolved = rows.filter(row => !["available", "fallback", "resolved"].includes(row.status)).length;
const fallbacks = rows.filter(row => row.status === "fallback").length;
const issueRows = issues.slice(-50);
mappingBody.innerHTML = `
<div class="ucc-source-mapping-summary">
<span>${rows.length} approved source groups</span>
<span>${unresolved} unresolved</span>
<span>${fallbacks} fallbacks used</span>
<span>${issueRows.length} visual issues detected</span>
</div>
<h3>Visual catalogue</h3>
<div class="table-wrap"><table><thead><tr><th>Criterion</th><th>Expected</th><th>Detected</th><th>Status</th></tr></thead><tbody>${countRows.map(row => `<tr><td>${esc(criterionLabels[row.dashboard])}</td><td>${row.expected}</td><td>${row.actual}</td><td class="${statusClass(row.status)}">${row.status === "available" ? "Complete" : "Count mismatch"}</td></tr>`).join("")}</tbody></table></div>
<h3>Approved DocType mapping</h3>
<div class="table-wrap"><table><thead><tr><th>Source key</th><th>Approved candidates</th><th>Resolved DocType</th><th>Status</th><th>Detected fields</th><th>Diagnostic detail</th></tr></thead><tbody>${rows.length ? rows.map(row => {
const rowAttempts = row.attempts || [];
const attempts = rowAttempts.map(item => `${item.doctype || "Candidate"}: ${item.status || item.stage || "checked"}${item.message ? " (" + item.message + ")" : ""}`).join("; ");
const resolvedAttempt = rowAttempts.find(item => item.doctype === row.resolved_doctype) || rowAttempts.find(item => (item.fields || []).length) || {};
const detectedFields = Array.isArray(resolvedAttempt.fields) ? resolvedAttempt.fields : [];
const fieldCount = Number(resolvedAttempt.field_count || detectedFields.length || 0);
const fieldCell = fieldCount
? `<details class="ucc-source-field-list"><summary>${fieldCount} fields</summary><small>${esc(detectedFields.join(", ") || "Field names were not returned")}</small></details>`
: "No fields detected";
return `<tr><td>${esc(row.label || row.key)}</td><td>${esc((row.candidates || []).join(" → "))}</td><td>${esc(row.resolved_doctype || row.doctype || "Not resolved")}</td><td class="${statusClass(row.status)}">${esc(row.status || "unknown")}</td><td>${fieldCell}</td><td>${esc(row.detail || row.message || attempts || "No additional detail")}</td></tr>`;
}).join("") : '<tr><td colspan="6">No source diagnostics were returned.</td></tr>'}</tbody></table></div>
<h3>Visual rendering issues in this browser session</h3>
<div class="table-wrap"><table><thead><tr><th>Time</th><th>Criterion</th><th>Section</th><th>Visual</th><th>Reason</th></tr></thead><tbody>${issueRows.length ? issueRows.map(row => `<tr><td>${esc(row.time)}</td><td>${esc(row.dashboard)}</td><td>${esc(row.panel)}</td><td>${esc(row.visual)}</td><td>${esc(row.reason)}</td></tr>`).join("") : '<tr><td colspan="5">No invalid or blank visual has been detected in the current browser session.</td></tr>'}</tbody></table></div>`;
}
function renderMappingError(error) {
lastMappingResult = null;
mappingBody.innerHTML = '<div class="ucc-visual-diagnostic"><strong>Source diagnostics could not be loaded</strong><span>' + esc(error?.message || error || "Unknown API error") + '</span></div>';
}
function openSourceMapping(dashboard) {
lastMappingResult = null;
mappingDialog.hidden = false;
mappingBody.innerHTML = '<div class="ucc-visual-diagnostic"><strong>Loading source diagnostics…</strong><span>Checking approved DocType candidates, metadata access and current-user readability.</span></div>';
if (!(global.frappe && typeof frappe.call === "function")) {
renderMappingError("frappe.call is unavailable on this page.");
return;
}
frappe.call({
method: "ucc_shared_diagnostics",
args: { payload: JSON.stringify({ dashboard: dashboard || "" }) },
callback: response => renderMapping(response?.message || response || {}),
error: error => renderMappingError(error)
});
}
function closeSourceMapping() {
mappingDialog.hidden = true;
}
function copySourceMapping() {
if (!lastMappingResult) {
notify("The source mapping report has not finished loading.", "orange");
return;
}
const report = JSON.stringify({
platform_version: "2.0.1",
source_mapping: lastMappingResult,
visual_catalogue: visualCountSummary(),
visual_issues: issues.slice()
}, null, 2);
const task = navigator.clipboard?.writeText
? navigator.clipboard.writeText(report)
: Promise.reject(new Error("Clipboard unavailable"));
task.then(() => notify("Source mapping report copied.", "green"))
.catch(() => window.prompt("Copy the source mapping report", report));
}
mappingDialog.addEventListener("click", event => {
if (event.target.closest("[data-source-mapping-copy]")) {
event.preventDefault();
copySourceMapping();
return;
}
if (event.target === mappingDialog || event.target.closest("[data-source-mapping-close]")) closeSourceMapping();
});
platform.addEventListener("ucc:open-source-mapping", event => openSourceMapping(event.detail?.dashboard || ""));
platform.addEventListener("click", event => {
const button = event.target.closest("[data-ucc-open-mapping]");
if (!button) return;
event.preventDefault();
event.stopPropagation();
openSourceMapping(button.closest("[data-dashboard-panel]")?.dataset.dashboardPanel || button.closest("[data-demo-dashboard]")?.dataset.demoDashboard || "");
});

function visualIdentity(node) {
return node.dataset.chart || node.dataset.demoChart || "unknown-visual";
}
function visualPanel(node) {
return node.closest("[data-demo-panel]")?.dataset.demoPanel || node.closest("[data-panel]")?.dataset.panel || "overview";
}
function visualDashboard(node) {
return node.closest("[data-dashboard-panel]")?.dataset.dashboardPanel || "unknown";
}
function recordIssue(node, reason) {
const signature = visualDashboard(node) + "|" + visualPanel(node) + "|" + visualIdentity(node) + "|" + reason;
if (issues.some(item => item.signature === signature)) return;
issues.push({
signature,
time: new Date().toISOString(),
dashboard: visualDashboard(node),
panel: visualPanel(node),
visual: visualIdentity(node),
reason
});
}
function diagnosticMarkup(reason) {
return '<div class="ucc-visual-diagnostic"><strong>Visual could not be rendered</strong><span>' + esc(reason) + ' Open Source Mapping Report to see missing DocTypes, permissions, candidate fallbacks and field checks.</span><button type="button" data-ucc-open-mapping>Source mapping report</button></div>';
}
function invalidSvgReason(node) {
const candidates = node.querySelectorAll("svg [d],svg [points],svg [transform],svg [x],svg [y],svg [cx],svg [cy],svg [r],svg [width],svg [height]");
for (const element of candidates) {
for (const attribute of element.getAttributeNames()) {
const value = element.getAttribute(attribute) || "";
if (/NaN|undefined|Infinity/i.test(value)) return "Invalid SVG " + attribute + '="' + value.slice(0, 120) + '".';
}
}
return "";
}
function isLoading(node) {
const dashboard = node.closest("[data-demo-dashboard],[data-dashboard-panel]");
const liveOverlay = dashboard?.querySelector("[data-demo-loading-overlay]:not(.hidden),[data-loading-overlay]:not(.hidden)");
return Boolean(liveOverlay || node.querySelector(".loading,.spinner,[data-loading]"));
}
function meaningfulVisual(node) {
if (node.querySelector("svg,canvas,img,.ucc-demo-bars,.ucc-live-empty,.empty-state,.ucc-visual-diagnostic")) return true;
return clean(node.textContent).length > 12;
}
function deferredUnrendered(node) {
// Click-to-render charts are intentionally empty until the user opens the Diagram view. Don't flag them as failed renders.
const demoCard = node.closest("[data-demo-card]");
if (demoCard) return demoCard.dataset.liveCardRendered !== "1";
return node.dataset.c5Deferred === "1";
}
function scanVisuals() {
const now = Date.now();
platform.querySelectorAll("[data-chart],[data-demo-chart]").forEach(node => {
if (!node.isConnected || node.getClientRects().length === 0 || isLoading(node) || deferredUnrendered(node)) return;
const invalid = invalidSvgReason(node);
if (invalid) {
recordIssue(node, invalid);
node.dataset.visualGuardReplaced = "invalid-svg";
node.innerHTML = diagnosticMarkup(invalid);
return;
}
if (meaningfulVisual(node)) {
blankFirstSeen.delete(node);
return;
}
const firstSeen = blankFirstSeen.get(node) || now;
blankFirstSeen.set(node, firstSeen);
if (now - firstSeen < 20000) return;
const reason = "The diagram area remained blank after the section finished loading.";
recordIssue(node, reason);
node.dataset.visualGuardReplaced = "blank";
node.innerHTML = diagnosticMarkup(reason);
});
}

updateExploreCounts();
setTimeout(updateExploreCounts, 300);
setTimeout(scanVisuals, 1800);
setInterval(scanVisuals, 3500);
platform.addEventListener("click", event => {
if (event.target.closest("[data-demo-tab],[data-tab],[data-demo-view],[data-card-view]")) {
setTimeout(scanVisuals, 1200);
}
});

const observer = new MutationObserver(mutations => {
if (mutations.some(mutation => mutation.addedNodes.length)) {
setTimeout(updateExploreCounts, 80);
setTimeout(scanVisuals, 900);
}
});
observer.observe(platform, { childList: true, subtree: true });

global.UCCVisualDiagnostics = Object.freeze({
issues: () => issues.slice(),
scan: scanVisuals,
openSourceMapping,
expectedCounts
});
})(window);

/* Source readability and functional-card styling are handled by the shared dashboard engine. */
