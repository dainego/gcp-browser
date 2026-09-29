const state = {
    storageId: "",
    storageLabel: "",
    storages: [],
    buckets: [],
    bucket: "",
    prefix: "",
    rootPrefix: "",
    history: [],
    items: [],
    selected: null,
    sort: "name",
    direction: "asc",

    // Persistent tree state.
    // Each key is a folder prefix and stores its children plus expansion state.
    treeNodes: new Map(),
    treeLoaded: new Set(),
    treeExpanded: new Set(),
};

document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    bindEvents();

    try {
        await loadConfig();
        await loadFolder("");
    } catch (error) {
        showFatalError(error);
    }
});

function initTheme() {
    const savedTheme = localStorage.getItem("gcs-browser-theme") || "light";
    applyTheme(savedTheme);

    document.querySelectorAll(".theme-button").forEach((button) => {
        button.addEventListener("click", () => {
            applyTheme(button.dataset.theme);
        });
    });
}

function applyTheme(theme) {
    const validThemes = ["light", "dark", "premium"];

    if (!validThemes.includes(theme)) {
        theme = "light";
    }

    document.documentElement.dataset.theme = theme;
    localStorage.setItem("gcs-browser-theme", theme);

    document.querySelectorAll(".theme-button").forEach((button) => {
        const active = button.dataset.theme === theme;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
    });
}

function bindEvents() {
    document.getElementById("storageSelect").addEventListener("change", async (event) => {
        await switchStorage(event.target.value);
    });

    document.getElementById("bucketSelect").addEventListener("change", async (event) => {
        await switchBucket(event.target.value);
    });

    document.getElementById("homeButton").addEventListener("click", async () => {
        state.history = [];
        await loadFolder("");
    });

    document.getElementById("backButton").addEventListener("click", goBack);

    document.getElementById("sortSelect").addEventListener("change", async (event) => {
        state.sort = event.target.value;
        await loadFolder(state.prefix, false);
    });

    document.getElementById("directionButton").addEventListener("click", async () => {
        state.direction = state.direction === "asc" ? "desc" : "asc";
        document.getElementById("directionButton").textContent =
            state.direction === "asc" ? "↑" : "↓";
        await loadFolder(state.prefix, false);
    });

    document.getElementById("globalSearch").addEventListener("keydown", async (event) => {
        if (event.key === "Enter") {
            await globalSearch(event.target.value);
        }
    });

    document.getElementById("folderSearch").addEventListener("input", (event) => {
        renderTree(event.target.value);
    });

    document.querySelectorAll(".tab").forEach((button) => {
        button.addEventListener("click", () => {
            activateTab(button.dataset.tab);
        });
    });
}

async function loadConfig() {
    const response = await fetch("/api/config");

    if (!response.ok) {
        throw new Error(`Error cargando configuración: HTTP ${response.status}`);
    }

    const data = await response.json();
    state.storages = data.storages || [];

    if (!state.storages.length) {
        throw new Error("No hay Storage configurados.");
    }

    const savedStorage = localStorage.getItem("gcs-browser-storage");
    const storage =
        state.storages.find(item => item.id === savedStorage) ||
        state.storages[0];

    state.storageId = storage.id;
    state.storageLabel = storage.label;
    state.buckets = storage.buckets || [];

    const savedBucket = localStorage.getItem(
        `gcs-browser-bucket:${state.storageId}`
    );

    state.bucket =
        state.buckets.includes(savedBucket)
            ? savedBucket
            : state.buckets[0];

    renderStorageSelector();
    renderBucketSelector();
    await loadBucketConfig();
}

function renderStorageSelector() {
    const select = document.getElementById("storageSelect");

    select.innerHTML = state.storages.map(storage => `
        <option value="${escapeHtml(storage.id)}" ${storage.id === state.storageId ? "selected" : ""}>
            ${escapeHtml(storage.label)}
        </option>
    `).join("");
}

function renderBucketSelector() {
    const select = document.getElementById("bucketSelect");

    select.innerHTML = state.buckets.map(bucket => `
        <option value="${escapeHtml(bucket)}" ${bucket === state.bucket ? "selected" : ""}>
            ${escapeHtml(bucket)}
        </option>
    `).join("");
}

async function loadBucketConfig() {
    const params = new URLSearchParams({
        storage_id: state.storageId,
        bucket: state.bucket,
    });

    const response = await fetch(`/api/bucket-config?${params.toString()}`);

    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Error cargando bucket: HTTP ${response.status}`);
    }

    const data = await response.json();
    state.rootPrefix = data.root_prefix || "";

    document.getElementById("bucketName").textContent =
        `${state.storageLabel} · ${state.bucket}`;
}

async function switchStorage(storageId) {
    const storage = state.storages.find(item => item.id === storageId);
    if (!storage) return;

    state.storageId = storage.id;
    state.storageLabel = storage.label;
    state.buckets = storage.buckets || [];

    const savedBucket = localStorage.getItem(
        `gcs-browser-bucket:${state.storageId}`
    );

    state.bucket =
        state.buckets.includes(savedBucket)
            ? savedBucket
            : state.buckets[0];

    localStorage.setItem("gcs-browser-storage", state.storageId);

    resetTreeState();
    state.history = [];
    renderStorageSelector();
    renderBucketSelector();

    await loadBucketConfig();
    await loadFolder("", false);
}

async function switchBucket(bucket) {
    if (!state.buckets.includes(bucket)) return;

    state.bucket = bucket;

    localStorage.setItem(
        `gcs-browser-bucket:${state.storageId}`,
        state.bucket
    );

    resetTreeState();
    state.history = [];
    renderBucketSelector();

    await loadBucketConfig();
    await loadFolder("", false);
}

function resetTreeState() {
    state.treeNodes = new Map();
    state.treeLoaded = new Set();
    state.treeExpanded = new Set();
    state.treeExpanded.add(normalizePrefix(state.rootPrefix));
}

function normalizePrefix(prefix) {
    prefix = (prefix || "").replace(/^\/+/, "");

    if (prefix && !prefix.endsWith("/")) {
        prefix += "/";
    }

    return prefix;
}

async function loadFolder(prefix = "", pushHistory = true) {
    prefix = normalizePrefix(prefix);

    if (pushHistory && prefix !== state.prefix) {
        state.history.push(state.prefix);
    }

    const params = new URLSearchParams({
        storage_id: state.storageId,
        bucket: state.bucket,
        prefix,
        sort: state.sort,
        direction: state.direction,
    });

    const response = await fetch(`/api/objects?${params.toString()}`);

    if (!response.ok) {
        throw new Error(`Error cargando carpeta: HTTP ${response.status}`);
    }

    const data = await response.json();

    state.prefix = data.prefix || prefix;
    state.items = data.items || [];
    state.selected = null;

    // Cache the folder's immediate children for the tree.
    cacheTreeFolder(state.prefix, data.folders || []);

    // Make the complete path to the selected folder visible.
    expandPathTo(state.prefix);

    renderBreadcrumb();
    renderTree();
    renderFiles();
    clearSelection();

    document.getElementById("backButton").disabled =
        !state.prefix || state.prefix === state.rootPrefix;
}

async function loadTreeChildren(prefix) {
    prefix = normalizePrefix(prefix);

    if (state.treeLoaded.has(prefix)) {
        return state.treeNodes.get(prefix) || [];
    }

    const params = new URLSearchParams({
        prefix,
        sort: "name",
        direction: "asc",
    });

    const response = await fetch(`/api/objects?${params.toString()}`);

    if (!response.ok) {
        throw new Error(`Error cargando subcarpetas: HTTP ${response.status}`);
    }

    const data = await response.json();
    cacheTreeFolder(prefix, data.folders || []);

    return state.treeNodes.get(prefix) || [];
}

function cacheTreeFolder(prefix, folders) {
    prefix = normalizePrefix(prefix);

    const children = folders
        .filter(folder => folder.is_folder)
        .map(folder => ({
            name: normalizePrefix(folder.name),
            label: folder.relative_name || folder.name,
        }))
        .sort((a, b) => a.label.localeCompare(b.label));

    state.treeNodes.set(prefix, children);
    state.treeLoaded.add(prefix);
}

function expandPathTo(prefix) {
    prefix = normalizePrefix(prefix);

    state.treeExpanded.add("");

    if (state.rootPrefix) {
        state.treeExpanded.add(normalizePrefix(state.rootPrefix));
    }

    let current = state.rootPrefix;
    const relative = state.rootPrefix && prefix.startsWith(state.rootPrefix)
        ? prefix.slice(state.rootPrefix.length)
        : prefix;

    const parts = relative.replace(/^\/+|\/+$/g, "")
        ? relative.replace(/^\/+|\/+$/g, "").split("/")
        : [];

    for (const part of parts) {
        current = normalizePrefix(current + part);
        state.treeExpanded.add(current);
    }
}

async function toggleTreeFolder(prefix) {
    prefix = normalizePrefix(prefix);

    if (state.treeExpanded.has(prefix)) {
        state.treeExpanded.delete(prefix);
        renderTree();
        return;
    }

    state.treeExpanded.add(prefix);

    try {
        await loadTreeChildren(prefix);
        renderTree();
    } catch (error) {
        console.error(error);
        state.treeExpanded.delete(prefix);
        renderTree();
    }
}

function renderBreadcrumb() {
    const container = document.getElementById("breadcrumb");
    container.innerHTML = "";

    const rootButton = document.createElement("button");
    rootButton.className = "breadcrumb-item";
    rootButton.textContent = state.bucket;
    rootButton.addEventListener("click", async () => {
        state.history = [];
        await loadFolder("");
    });
    container.appendChild(rootButton);

    const root = state.rootPrefix.replace(/\/$/, "");
    const current = state.prefix.replace(/\/$/, "");

    let relative = current;

    if (root && relative.startsWith(root)) {
        relative = relative.slice(root.length).replace(/^\/+/, "");
    }

    const parts = relative ? relative.split("/") : [];
    let accumulated = state.rootPrefix;

    if (state.rootPrefix) {
        const rootPart = document.createElement("span");
        rootPart.className = "breadcrumb-separator";
        rootPart.textContent = "/";
        container.appendChild(rootPart);

        const rootPrefixButton = document.createElement("button");
        rootPrefixButton.className = "breadcrumb-item";
        rootPrefixButton.textContent = root;
        rootPrefixButton.addEventListener("click", async () => {
            await loadFolder(state.rootPrefix);
        });
        container.appendChild(rootPrefixButton);
    }

    parts.forEach((part) => {
        if (!part) return;

        accumulated += part + "/";

        const separator = document.createElement("span");
        separator.className = "breadcrumb-separator";
        separator.textContent = "/";
        container.appendChild(separator);

        const button = document.createElement("button");
        button.className = "breadcrumb-item";
        button.textContent = part;

        const target = accumulated;
        button.addEventListener("click", async () => {
            await loadFolder(target);
        });

        container.appendChild(button);
    });

    document.getElementById("currentPath").textContent =
        state.prefix || "/";
}

function renderTree(filter = "") {
    const tree = document.getElementById("tree");
    tree.innerHTML = "";

    const filterText = (filter || "").trim().toLowerCase();

    const root = document.createElement("div");
    root.className = "tree-node root-node";

    root.innerHTML = `
        <span class="tree-toggle empty"></span>
        <span class="tree-icon">🪣</span>
        <span class="tree-label">${escapeHtml(state.bucket)}</span>
    `;

    root.addEventListener("click", async () => {
        state.history = [];
        await loadFolder("", false);
    });

    tree.appendChild(root);

    const rootPrefix = normalizePrefix(state.rootPrefix);

    if (!state.treeLoaded.has(rootPrefix)) {
        // Load the root children asynchronously. The root itself is always visible.
        loadTreeChildren(rootPrefix)
            .then(() => renderTree(filterText))
            .catch(error => console.error(error));
        return;
    }

    const rootChildren = state.treeNodes.get(rootPrefix) || [];

    rootChildren.forEach(child => {
        renderTreeNode(tree, child, 0, filterText);
    });
}

function renderTreeNode(container, node, depth, filterText = "") {
    const prefix = normalizePrefix(node.name);
    const expanded = state.treeExpanded.has(prefix);
    const active = normalizePrefix(state.prefix) === prefix;

    const row = document.createElement("div");
    row.className = "tree-node folder-node" + (active ? " active" : "");
    row.style.paddingLeft = `${8 + depth * 16}px`;

    const hasKnownChildren =
        state.treeLoaded.has(prefix)
            ? (state.treeNodes.get(prefix) || []).length > 0
            : true;

    row.innerHTML = `
        <button
            class="tree-toggle ${hasKnownChildren ? "" : "empty"}"
            aria-label="${expanded ? "Contraer" : "Expandir"}"
            type="button"
        >${hasKnownChildren ? (expanded ? "▼" : "▶") : ""}</button>
        <span class="tree-icon">📁</span>
        <span class="tree-label">${escapeHtml(node.label)}</span>
    `;

    const toggle = row.querySelector(".tree-toggle");

    toggle.addEventListener("click", async (event) => {
        event.stopPropagation();

        if (!hasKnownChildren) return;

        await toggleTreeFolder(prefix);
    });

    row.addEventListener("click", async (event) => {
        if (event.target === toggle) return;

        await loadFolder(prefix);
    });

    container.appendChild(row);

    if (!expanded) return;

    if (!state.treeLoaded.has(prefix)) {
        const loading = document.createElement("div");
        loading.className = "tree-loading";
        loading.style.paddingLeft = `${28 + depth * 16}px`;
        loading.textContent = "Cargando...";
        container.appendChild(loading);

        loadTreeChildren(prefix)
            .then(() => renderTree(filterText))
            .catch(error => {
                console.error(error);
                renderTree(filterText);
            });

        return;
    }

    const children = state.treeNodes.get(prefix) || [];

    children
        .filter(child => {
            if (!filterText) return true;

            // Keep a branch if either the folder itself or one of its descendants
            // is a possible match. Loaded descendants are checked recursively.
            return treeNodeMatchesFilter(child, filterText);
        })
        .forEach(child => {
            renderTreeNode(container, child, depth + 1, filterText);
        });
}

function treeNodeMatchesFilter(node, filterText) {
    if (node.label.toLowerCase().includes(filterText)) {
        return true;
    }

    const children = state.treeNodes.get(normalizePrefix(node.name)) || [];

    return children.some(child => treeNodeMatchesFilter(child, filterText));
}

function renderFiles() {
    const container = document.getElementById("filesTable");
    container.innerHTML = "";

    const items = state.items || [];

    document.getElementById("itemCount").textContent =
        `${items.length} elemento${items.length === 1 ? "" : "s"}`;

    if (!items.length) {
        container.innerHTML = `
            <div class="empty-state">
                Esta carpeta no contiene archivos ni subcarpetas.
            </div>
        `;
        return;
    }

    const header = document.createElement("div");
    header.className = "file-row file-header";
    header.innerHTML = `
        <div>Nombre</div>
        <div>Tamaño</div>
        <div>Modificado</div>
        <div>Tipo</div>
    `;
    container.appendChild(header);

    items.forEach((item) => {
        const row = document.createElement("div");
        row.className = "file-row";

        const isFolder = item.is_folder;

        row.innerHTML = `
            <div class="file-name">
                <span class="file-icon">${isFolder ? "📁" : "📄"}</span>
                <span>${escapeHtml(item.relative_name || item.name)}</span>
            </div>
            <div>${isFolder ? "—" : formatBytes(item.size)}</div>
            <div>${isFolder ? "—" : formatDate(item.updated)}</div>
            <div>${isFolder ? "Carpeta" : escapeHtml(item.content_type || "Archivo")}</div>
        `;

        row.addEventListener("click", async () => {
            if (isFolder) {
                await loadFolder(item.name);
            } else {
                await selectFile(item);
            }
        });

        container.appendChild(row);
    });
}

async function selectFile(item) {
    state.selected = item;

    document.getElementById("detailsEmpty").classList.add("hidden");
    document.getElementById("detailsContent").classList.remove("hidden");
    document.getElementById("selectedObject").textContent = item.name;

    activateTab("metadata");
    await renderMetadata();
}

function clearSelection() {
    document.getElementById("detailsEmpty").classList.remove("hidden");
    document.getElementById("detailsContent").classList.add("hidden");
    document.getElementById("selectedObject").textContent =
        "Ningún archivo seleccionado";
}

async function activateTab(tab) {
    document.querySelectorAll(".tab").forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === tab);
    });

    document.querySelectorAll(".tab-content").forEach((content) => {
        content.classList.add("hidden");
    });

    const content = document.getElementById(
        `tab${tab.charAt(0).toUpperCase()}${tab.slice(1)}`
    );

    if (content) {
        content.classList.remove("hidden");
    }

    if (!state.selected) return;

    if (tab === "metadata") await renderMetadata();
    if (tab === "schema") await renderSchema();
    if (tab === "stats") await renderStats();
    if (tab === "preview") await renderPreview();
}

async function renderMetadata() {
    const container = document.getElementById("tabMetadata");
    container.innerHTML = "Cargando...";

    const data = await fetchJson(
        `/api/object?storage_id=${encodeURIComponent(state.storageId)}&bucket=${encodeURIComponent(state.bucket)}&name=${encodeURIComponent(state.selected.name)}`
    );

    container.innerHTML = metadataTable(data);
}

async function renderSchema() {
    const container = document.getElementById("tabSchema");
    container.innerHTML = "Cargando...";

    try {
        const data = await fetchJson(
            `/api/schema?storage_id=${encodeURIComponent(state.storageId)}&bucket=${encodeURIComponent(state.bucket)}&name=${encodeURIComponent(state.selected.name)}`
        );

        container.innerHTML = `
            <div class="stats-line">
                ${data.num_rows.toLocaleString()} filas ·
                ${data.num_columns} columnas ·
                ${data.num_row_groups} row groups
            </div>
            <div class="schema-table">
                ${data.columns.map(column => `
                    <div class="schema-row">
                        <div>${escapeHtml(column.name)}</div>
                        <div>${escapeHtml(column.type)}</div>
                        <div>${column.nullable ? "nullable" : "required"}</div>
                    </div>
                `).join("")}
            </div>
        `;
    } catch (error) {
        container.innerHTML = errorBox(error.message);
    }
}

async function renderStats() {
    const container = document.getElementById("tabStats");
    container.innerHTML = "Cargando...";

    try {
        const data = await fetchJson(
            `/api/stats?storage_id=${encodeURIComponent(state.storageId)}&bucket=${encodeURIComponent(state.bucket)}&name=${encodeURIComponent(state.selected.name)}`
        );

        container.innerHTML = metadataTable(data);
    } catch (error) {
        container.innerHTML = errorBox(error.message);
    }
}

async function renderPreview() {
    const container = document.getElementById("tabPreview");
    container.innerHTML = "Cargando preview...";

    try {
        const data = await fetchJson(
            `/api/preview?storage_id=${encodeURIComponent(state.storageId)}&bucket=${encodeURIComponent(state.bucket)}&name=${encodeURIComponent(state.selected.name)}&limit=100`
        );

        if (!data.rows.length) {
            container.innerHTML = `<div class="empty-state">No hay filas para mostrar.</div>`;
            return;
        }

        const columns = data.columns;

        container.innerHTML = `
            <div class="preview-note">${escapeHtml(data.note || "")}</div>
            <div class="preview-table-wrapper">
                <table class="preview-table">
                    <thead>
                        <tr>
                            ${columns.map(c => `<th>${escapeHtml(c)}</th>`).join("")}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.rows.map(row => `
                            <tr>
                                ${columns.map(c => `<td>${escapeHtml(formatCell(row[c]))}</td>`).join("")}
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    } catch (error) {
        container.innerHTML = errorBox(error.message);
    }
}

async function globalSearch(query) {
    query = (query || "").trim();

    if (!query) {
        await loadFolder(state.prefix, false);
        return;
    }

    const response = await fetch(
        `/api/search?storage_id=${encodeURIComponent(state.storageId)}&bucket=${encodeURIComponent(state.bucket)}&q=${encodeURIComponent(query)}&prefix=${encodeURIComponent(state.prefix)}`
    );

    if (!response.ok) {
        throw new Error(`Error en búsqueda: HTTP ${response.status}`);
    }

    const data = await response.json();

    state.items = data.results || [];
    state.selected = null;

    renderFiles();
    clearSelection();
}

async function goBack() {
    if (state.history.length) {
        const previous = state.history.pop();
        await loadFolder(previous, false);
        return;
    }

    if (state.prefix && state.prefix !== state.rootPrefix) {
        const parent = parentPrefix(state.prefix);
        await loadFolder(parent, false);
    }
}

function parentPrefix(prefix) {
    prefix = normalizePrefix(prefix).replace(/\/$/, "");

    if (!prefix) return "";

    if (state.rootPrefix) {
        const root = state.rootPrefix.replace(/\/$/, "");

        if (prefix === root) return "";

        if (prefix.startsWith(root + "/")) {
            const relative = prefix.slice(root.length + 1);
            const parts = relative.split("/");
            parts.pop();

            return parts.length
                ? `${root}/${parts.join("/")}/`
                : state.rootPrefix;
        }
    }

    const parts = prefix.split("/");
    parts.pop();

    return parts.length ? `${parts.join("/")}/` : "";
}

async function fetchJson(url) {
    const response = await fetch(url);

    if (!response.ok) {
        let message = `HTTP ${response.status}`;

        try {
            const body = await response.json();
            message = body.detail || message;
        } catch (_) {}

        throw new Error(message);
    }

    return response.json();
}

function metadataTable(data) {
    return `
        <div class="metadata-grid">
            ${Object.entries(data).map(([key, value]) => `
                <div class="metadata-key">${escapeHtml(key)}</div>
                <div class="metadata-value">${escapeHtml(formatCell(value))}</div>
            `).join("")}
        </div>
    `;
}

function errorBox(message) {
    return `<div class="error-box">${escapeHtml(message)}</div>`;
}

function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return "—";

    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;

    return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function formatDate(value) {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return value;

    return date.toLocaleString("es-AR");
}

function formatCell(value) {
    if (value === null || value === undefined) return "";

    if (typeof value === "object") {
        return JSON.stringify(value);
    }

    return String(value);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function showFatalError(error) {
    console.error(error);

    document.getElementById("tree").innerHTML =
        errorBox(error.message);

    document.getElementById("filesTable").innerHTML =
        errorBox(error.message);
}
