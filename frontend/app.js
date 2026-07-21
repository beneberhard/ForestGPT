const API = window.location.origin;
const speciesRowCount = 9;
const thinningCount = 4;
const defaultSimulationStartYear = 2026;

let map;
let standLayer;
let standLayersById = new Map();
let selectedStandId = null;
let lastRunId = null;
let chatSessionId = null;
let lastOutputs = [];
let lastDiagnostics = [];
let thinningKeys = new Set();
let resultsTableCollapsed = false;
let observationsVisible = false;
let savedSimulationRuns = [];

const $ = (id) => document.getElementById(id);

function value(id) {
  return $(id)?.value?.trim() ?? "";
}

function numberValue(id) {
  const raw = value(id);
  return raw === "" ? null : Number(raw);
}

function normalizeSpeciesName(name) {
  const aliases = {
    beech: "Fagus sylvatica",
    buche: "Fagus sylvatica",
    "european beech": "Fagus sylvatica",
    "fagus sylvatica": "Fagus sylvatica",
    "douglas fir": "Pseudotsuga menziesii",
    douglasie: "Pseudotsuga menziesii",
    "pseudotsuga menziesii": "Pseudotsuga menziesii",
    fir: "Abies alba",
    "silver fir": "Abies alba",
    tanne: "Abies alba",
    "abies alba": "Abies alba",
    larch: "Larix decidua",
    laerche: "Larix decidua",
    "lärche": "Larix decidua",
    "larix decidua": "Larix decidua",
    oak: "Quercus robur",
    eiche: "Quercus robur",
    "quercus robur": "Quercus robur",
    pine: "Pinus sylvestris",
    "scots pine": "Pinus sylvestris",
    kiefer: "Pinus sylvestris",
    "pinus sylvestris": "Pinus sylvestris",
    spruce: "Picea abies",
    "norway spruce": "Picea abies",
    "picea abies": "Picea abies",
  };
  return aliases[String(name).trim().toLowerCase()] || String(name).trim();
}

function outputSpeciesLabel(species, cohort) {
  const base = normalizeSpeciesName(species);
  return cohort ? `${base} | ${cohort}` : base;
}

function apiPath(path) {
  return `${API}${path}`;
}

async function request(path, options = {}) {
  const response = await fetch(apiPath(path), {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const detail = data?.detail || data || response.statusText;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return data;
}

async function uploadRequest(path, formData) {
  const response = await fetch(apiPath(path), {
    method: "POST",
    body: formData,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const detail = data?.detail || data || response.statusText;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return data;
}

function initMap() {
  map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
    zoomAnimation: false,
  }).setView([48.1, 11.5], 7);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    keepBuffer: 4,
    attribution: "&copy; OpenStreetMap contributors",
  });
  tiles.on("tileerror", (event) => {
    console.warn("OSM tile failed to load", event.coords);
  });
  tiles.addTo(map);
  standLayer = L.geoJSON(null, {
    renderer: L.canvas({ padding: 0.5 }),
    style: (feature) => standStyle(feature?.properties?.id),
    onEachFeature: (feature, layer) => {
      const props = feature.properties || {};
      layer.bindPopup(`<strong>${props.name || `Stand ${props.id}`}</strong><br>${props.species || ""}`, {
        autoPan: false,
      });
      layer.on("click", () => selectStand(props.id));
    },
  }).addTo(map);
  map.whenReady(() => {
    requestAnimationFrame(refreshMapLayout);
  });
  setTimeout(refreshMapLayout, 150);
  setTimeout(refreshMapLayout, 600);
  window.addEventListener("resize", refreshMapLayout);
}

function refreshMapLayout() {
  if (!map) return;
  map.invalidateSize({ pan: false });
}

function buildSpeciesRows() {
  const container = $("speciesRows");
  container.innerHTML = "";
  const header = document.createElement("div");
  header.className = "table-row";
  ["", "Species", "Cohort", "Yield table", "Planted", "Age", "Top h", "Share", "N/ha", "Mean h", "DBH"].forEach((label) => {
    const cell = document.createElement("div");
    cell.className = "table-head";
    cell.textContent = label;
    header.appendChild(cell);
  });
  container.appendChild(header);

  for (let i = 1; i <= speciesRowCount; i += 1) {
    const row = document.createElement("div");
    row.className = "table-row";
    row.innerHTML = `
      <div class="row-number">${i}</div>
      <input id="species_${i}" data-mirror="${i}" />
      <input id="cohort_${i}" data-mirror="${i}" value="${i === 1 ? "30y" : ""}" />
      <input id="yield_${i}" placeholder="optional" />
      <input id="planted_${i}" type="number" min="0" max="9999" placeholder="year" />
      <input id="age_${i}" type="number" min="0" />
      <input id="top_height_${i}" type="number" min="0" step="0.1" />
      <input id="share_${i}" type="number" min="0" max="1" step="0.01" />
      <input id="stems_${i}" type="number" min="1" />
      <input id="height_${i}" type="number" min="0" step="0.1" />
      <input id="dbh_${i}" type="number" min="0" step="0.1" />
    `;
    container.appendChild(row);
  }
}

function buildThinningRows() {
  const container = $("thinningRows");
  container.innerHTML = "";
  const header = document.createElement("div");
  header.className = "table-row";
  ["", "Species", "Cohort", "Yr 1", "Rem. 1", "Yr 2", "Rem. 2", "Yr 3", "Rem. 3", "Yr 4", "Rem. 4"].forEach((label) => {
    const cell = document.createElement("div");
    cell.className = "table-head";
    cell.textContent = label;
    header.appendChild(cell);
  });
  container.appendChild(header);

  const yearRow = document.createElement("div");
  yearRow.className = "table-row";
  yearRow.innerHTML = `<div></div><div></div><div></div>${Array.from({ length: thinningCount }, (_, index) => `
    <input id="thin_year_${index + 1}" type="number" min="1" />
    <div class="readonly-cell">%</div>
  `).join("")}`;
  container.appendChild(yearRow);

  for (let i = 1; i <= speciesRowCount; i += 1) {
    const row = document.createElement("div");
    row.className = "table-row";
    row.innerHTML = `
      <div class="row-number">${i}</div>
      <div id="thin_species_${i}" class="readonly-cell"></div>
      <div id="thin_cohort_${i}" class="readonly-cell"></div>
      ${Array.from({ length: thinningCount }, (_, index) => `
        <div></div>
        <input id="thin_percent_${i}_${index + 1}" type="number" min="0" max="100" step="0.1" />
      `).join("")}
    `;
    container.appendChild(row);
  }
}

function bindMirrors() {
  for (let i = 1; i <= speciesRowCount; i += 1) {
    ["species", "cohort"].forEach((field) => {
      $(`${field}_${i}`).addEventListener("input", syncThinningLabels);
    });
    $(`cohort_${i}`).addEventListener("input", () => {
      $(`cohort_${i}`).dataset.autoPlanted = "0";
    });
    $(`planted_${i}`).addEventListener("input", () => {
      updateCohortFromPlantedYear(i);
      syncThinningLabels();
    });
  }
  syncThinningLabels();
}

function updateCohortFromPlantedYear(row) {
  const plantedYear = numberValue(`planted_${row}`);
  const cohortNode = $(`cohort_${row}`);
  const isAuto = cohortNode.dataset.autoPlanted === "1";
  if (plantedYear === null) {
    if (isAuto) {
      cohortNode.value = "";
      cohortNode.dataset.autoPlanted = "0";
    }
    return;
  }
  if (!cohortNode.value || isAuto) {
    cohortNode.value = String(defaultSimulationStartYear - plantedYear);
    cohortNode.dataset.autoPlanted = "1";
  }
}

function syncThinningLabels() {
  for (let i = 1; i <= speciesRowCount; i += 1) {
    $(`thin_species_${i}`).textContent = value(`species_${i}`);
    $(`thin_cohort_${i}`).textContent = value(`cohort_${i}`);
  }
}

function speciesEntries() {
  const entries = [];
  const stock = numberValue("stockingDegree");
  for (let i = 1; i <= speciesRowCount; i += 1) {
    const species = value(`species_${i}`);
    const plantedYear = numberValue(`planted_${i}`);
    const age = numberValue(`age_${i}`);
    const topHeight = numberValue(`top_height_${i}`);
    const stems = numberValue(`stems_${i}`);
    const height = numberValue(`height_${i}`);
    const dbh = numberValue(`dbh_${i}`);
    const active = species && [plantedYear, age, topHeight, stems, height, dbh].some((item) => item !== null);
    if (!active) continue;
    const entry = clean({
      species,
      cohort_label: value(`cohort_${i}`),
      yield_table_id: value(`yield_${i}`),
      planted_year: plantedYear,
      age_years: age,
      top_height_m: topHeight,
      stocking_degree: stock,
      share: numberValue(`share_${i}`),
      stems_per_ha: stems,
      mean_height_m: height,
      mean_dbh_cm: dbh,
    });
    entries.push(entry);
  }
  return entries;
}

function thinningSchedule() {
  const schedule = [];
  for (let row = 1; row <= speciesRowCount; row += 1) {
    const species = value(`species_${row}`);
    if (!species) continue;
    for (let thin = 1; thin <= thinningCount; thin += 1) {
      const percent = numberValue(`thin_percent_${row}_${thin}`);
      const year = numberValue(`thin_year_${thin}`);
      if (percent === null) continue;
      if (year === null) throw new Error(`Enter year for thinning ${thin}.`);
      schedule.push(clean({
        species,
        cohort_label: value(`cohort_${row}`),
        year,
        removal_fraction: percent / 100,
      }));
    }
  }
  return schedule;
}

function clean(object) {
  return Object.fromEntries(
    Object.entries(object).filter(([, value]) => value !== "" && value !== null && value !== undefined)
  );
}

function buildPayload() {
  const entries = speciesEntries();
  if (!entries.length) throw new Error("Enter at least one species row.");
  const fieldInput = clean({
    altitude: numberValue("altitude"),
    soil_moisture: value("soilMoisture"),
    site_fertility: numberValue("siteFertility"),
    horizon_years: numberValue("horizon"),
    species_entries: entries,
    thinning_schedule: thinningSchedule(),
  });
  const standId = numberValue("standId");
  return clean({
    stand_id: standId,
    simulator: "r3pg",
    input_mode: "field",
    field_input: fieldInput,
  });
}

function setInputValue(id, value) {
  const node = $(id);
  if (!node) return;
  node.value = value === null || value === undefined ? "" : value;
}

function plantedYearFromValue(value) {
  if (value === null || value === undefined || value === "") return "";
  const match = String(value).match(/^\d{4}/);
  return match ? match[0] : value;
}

function resetSimulationInputs() {
  ["altitude", "soilMoisture", "siteFertility", "horizon", "stockingDegree"].forEach((id) => setInputValue(id, ""));
  for (let i = 1; i <= speciesRowCount; i += 1) {
    ["species", "cohort", "yield", "planted", "age", "top_height", "share", "stems", "height", "dbh"].forEach((field) => {
      setInputValue(`${field}_${i}`, "");
    });
    $(`cohort_${i}`).dataset.autoPlanted = "0";
  }
  setInputValue("cohort_1", "30y");
  for (let thin = 1; thin <= thinningCount; thin += 1) {
    setInputValue(`thin_year_${thin}`, "");
  }
  for (let row = 1; row <= speciesRowCount; row += 1) {
    for (let thin = 1; thin <= thinningCount; thin += 1) {
      setInputValue(`thin_percent_${row}_${thin}`, "");
    }
  }
  syncThinningLabels();
}

function applyFieldInputToForm(fieldInput = {}) {
  resetSimulationInputs();
  setInputValue("altitude", fieldInput.altitude);
  setInputValue("soilMoisture", fieldInput.soil_moisture);
  setInputValue("siteFertility", fieldInput.site_fertility);
  setInputValue("horizon", fieldInput.horizon_years);

  const entries = fieldInput.species_entries || [];
  entries.slice(0, speciesRowCount).forEach((entry, index) => {
    const row = index + 1;
    setInputValue(`species_${row}`, entry.species);
    setInputValue(`cohort_${row}`, entry.cohort_label);
    setInputValue(`yield_${row}`, entry.yield_table_id);
    setInputValue(`planted_${row}`, entry.planted_year ?? plantedYearFromValue(entry.planted));
    updateCohortFromPlantedYear(row);
    setInputValue(`age_${row}`, entry.age_years ?? entry.initial_age_years);
    setInputValue(`top_height_${row}`, entry.top_height_m);
    setInputValue(`share_${row}`, entry.share);
    setInputValue(`stems_${row}`, entry.stems_per_ha);
    setInputValue(`height_${row}`, entry.mean_height_m);
    setInputValue(`dbh_${row}`, entry.mean_dbh_cm);
  });

  const stock = entries.find((entry) => entry.stocking_degree !== undefined)?.stocking_degree;
  setInputValue("stockingDegree", stock);
  syncThinningLabels();
  applyThinningScheduleToForm(fieldInput.thinning_schedule || []);
}

function applyThinningScheduleToForm(schedule) {
  const years = [...new Set(schedule.map((item) => item.year).filter((year) => year !== null && year !== undefined))]
    .sort((a, b) => Number(a) - Number(b))
    .slice(0, thinningCount);
  years.forEach((year, index) => {
    setInputValue(`thin_year_${index + 1}`, year);
  });

  schedule.forEach((item) => {
    const column = years.findIndex((year) => Number(year) === Number(item.year)) + 1;
    if (!column) return;
    for (let row = 1; row <= speciesRowCount; row += 1) {
      const speciesMatches = value(`species_${row}`) === (item.species || "");
      const cohortMatches = (value(`cohort_${row}`) || "") === (item.cohort_label || "");
      if (speciesMatches && cohortMatches) {
        setInputValue(`thin_percent_${row}_${column}`, Number(item.removal_fraction || 0) * 100);
        return;
      }
    }
  });
}

async function saveStand() {
  const standId = numberValue("standId");
  if (standId === null) throw new Error("Enter a Stand ID before saving.");

  const firstEntry = speciesEntries()[0] || {};
  const payload = clean({
    id: standId,
    name: value("standName") || `Stand ${standId}`,
    species: firstEntry.species || value("species_1"),
    age_years: firstEntry.age_years || numberValue("age_1"),
    properties: { source: "frontend_panel" },
  });

  try {
    const stand = await request("/stands", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    selectedStandId = stand.id;
    setStatus(`Stand ${stand.id} saved`);
  } catch (error) {
    if (!String(error.message).includes("already exists")) throw error;
    const stand = await request(`/stands/${standId}`, {
      method: "PATCH",
      body: JSON.stringify(clean({
        name: payload.name,
        species: payload.species,
        age_years: payload.age_years,
        properties: payload.properties,
      })),
    });
    selectedStandId = stand.id;
    setStatus(`Stand ${stand.id} updated`);
  }
  await loadStands();
  await loadSimulationRunsForStand(stand.id);
}

async function linkStandGeometry() {
  const standId = numberValue("standId");
  if (standId === null) throw new Error("Enter the saved Stand ID before linking geometry.");
  const sourceTable = value("geometrySourceTable");
  const sourceId = value("geometrySourceId");
  if (!sourceTable || !sourceId) throw new Error("Enter source table and feature ID.");

  const stand = await request(`/stands/${standId}/link-geometry`, {
    method: "POST",
    body: JSON.stringify(clean({
      source_table: sourceTable,
      source_id: sourceId,
      source_id_column: value("geometrySourceIdColumn") || "id",
      geometry_column: value("geometryColumn") || "geom",
    })),
  });
  selectedStandId = stand.id;
  setStatus(`Geometry linked to stand ${stand.id}`);
  await loadStands();
  await selectStand(stand.id);
}

async function loadStands() {
  const [stands, geojson] = await Promise.all([
    request("/stands"),
    request("/stands/geojson"),
  ]);
  standLayer.clearLayers();
  standLayersById = new Map();
  standLayer.addData(geojson);
  standLayer.eachLayer((layer) => {
    const id = layer.feature?.properties?.id;
    if (id !== undefined && id !== null) {
      standLayersById.set(Number(id), layer);
    }
  });
  renderStandList(stands);
  if (selectedStandId && standLayersById.has(Number(selectedStandId))) {
    zoomToStand(selectedStandId);
  }
}

function renderStandList(stands) {
  const list = $("standList");
  list.innerHTML = "";
  if (!stands.length) {
    list.innerHTML = `<div class="message">No stands stored yet.</div>`;
    return;
  }
  stands.forEach((stand) => {
    const hasGeometry = standLayersById.has(Number(stand.id));
    const item = document.createElement("div");
    item.className = `stand-item ${stand.id === selectedStandId ? "active" : ""} ${hasGeometry ? "has-geometry" : "no-geometry"}`;
    item.dataset.standId = stand.id;
    item.title = hasGeometry ? "Zoom to stand geometry" : "No geometry stored for this stand";
    item.innerHTML = `
      <button class="stand-remove" type="button" aria-label="Remove stand ${stand.id}" title="Remove stand">x</button>
      <strong>${stand.name || `Stand ${stand.id}`}</strong>
      <span>ID ${stand.id}${stand.species ? ` - ${stand.species}` : ""}${stand.age_years ? ` - ${stand.age_years}y` : ""}</span>
      <em>${hasGeometry ? "geometry" : "no geometry"}</em>
    `;
    item.addEventListener("click", () => selectStand(stand.id));
    item.querySelector(".stand-remove").addEventListener("click", (event) => {
      event.stopPropagation();
      removeStand(stand.id, stand.name);
    });
    list.appendChild(item);
  });
}

async function removeStand(id, name) {
  const label = name || `Stand ${id}`;
  if (!window.confirm(`Remove ${label}?`)) {
    return;
  }
  try {
    await request(`/stands/${id}`, { method: "DELETE" });
    if (Number(selectedStandId) === Number(id)) {
      selectedStandId = null;
      $("standId").value = "";
      $("standInfo").classList.add("collapsed");
    }
    setStatus(`${label} removed.`);
    await loadStands();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function selectStand(id) {
  selectedStandId = Number(id);
  $("standId").value = id;
  renderStandListFromDom();
  zoomToStand(id);
  showStandInfo(id);
  loadSimulationRunsForStand(id).catch(showRunHistoryError);
  if (observationsVisible) {
    loadObservations(id);
  }
}

function renderStandListFromDom() {
  document.querySelectorAll(".stand-item").forEach((node) => node.classList.remove("active"));
  const items = [...document.querySelectorAll(".stand-item")];
  items.forEach((node) => {
    if (Number(node.dataset.standId) === Number(selectedStandId)) {
      node.classList.add("active");
    }
  });
}

function zoomToStand(id) {
  const layer = standLayersById.get(Number(id));
  refreshMapLayout();
  standLayer.setStyle((feature) => standStyle(feature?.properties?.id));
  if (!layer) {
    setStatus("Selected stand has no geometry.");
    return;
  }
  layer.setStyle({ color: "#1f5fbf", weight: 3, fillOpacity: 0.28 });
  layer.bringToFront();
  const bounds = layer.getBounds?.();
  if (bounds?.isValid()) {
    const panelWidth = document.querySelector(".panel-left")?.getBoundingClientRect().width || 0;
    map.fitBounds(bounds, {
      paddingTopLeft: [panelWidth + 72, 72],
      paddingBottomRight: [72, 72],
      maxZoom: 17,
      animate: false,
    });
  }
  setTimeout(() => layer.openPopup(), 250);
}

async function showStandInfo(id) {
  const panel = $("standInfo");
  const body = $("standInfoBody");
  panel.classList.remove("collapsed");
  body.innerHTML = `<div class="message">Loading spatial information...</div>`;
  try {
    const data = await request(`/stands/${id}/spatial-summary`);
    body.innerHTML = renderStandInfo(data);
  } catch (error) {
    body.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
  }
}

async function toggleObservationsPanel() {
  if (!selectedStandId) {
    setStatus("Select a stand first.");
    return;
  }
  observationsVisible = !observationsVisible;
  $("observationsPanel").classList.toggle("collapsed", !observationsVisible);
  if (observationsVisible) {
    $("observationDate").value = new Date().toISOString().slice(0, 10);
    await loadObservations(selectedStandId);
  }
}

async function loadObservations(standId) {
  const list = $("observationsList");
  list.innerHTML = `<div class="message">Loading observations...</div>`;
  try {
    const observations = await request(`/stands/${standId}/observations`);
    if (!observations.length) {
      list.innerHTML = `<div class="message">No field observations yet.</div>`;
      return;
    }
    list.innerHTML = observations.map(renderObservation).join("");
  } catch (error) {
    list.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
  }
}

function renderObservation(observation) {
  const date = observation.observed_at ? new Date(observation.observed_at).toLocaleDateString() : "";
  const meta = [date, observation.category, observation.observer].filter(Boolean).join(" - ");
  return `
    <div class="observation-item">
      <strong>${escapeHtml(meta || "Observation")}</strong>
      <span>ID ${observation.id}</span>
      <div>${escapeHtml(observation.note).replace(/\n/g, "<br>")}</div>
    </div>
  `;
}

async function saveObservation() {
  if (!selectedStandId) throw new Error("Select a stand first.");
  const note = value("observationNote");
  if (!note) throw new Error("Enter an observation note.");
  const date = value("observationDate");
  await request(`/stands/${selectedStandId}/observations`, {
    method: "POST",
    body: JSON.stringify(clean({
      observed_at: date ? `${date}T12:00:00` : null,
      category: value("observationCategory"),
      observer: value("observationObserver"),
      note,
    })),
  });
  $("observationNote").value = "";
  setStatus("Observation saved");
  await loadObservations(selectedStandId);
}

function renderStandInfo(data) {
  const terrain = data.terrain?.rasters?.[0] || {};
  const altitude = terrain.altitude_m;
  const slope = terrain.slope_deg;
  const aspect = terrain.aspect;
  const ruggedness = terrain.terrain_ruggedness_index_m;
  const geometry = data.geometry || {};
  return `
    <div class="stand-info-grid">
      ${infoCell("Name", data.name)}
      ${infoCell("Species", data.species || "")}
      ${infoCell("Age", data.age_years === null || data.age_years === undefined ? "" : `${data.age_years} years`)}
      ${infoCell("Area", valueWithUnit(geometry.area_ha_geodesic, "ha"))}
      ${infoCell("Perimeter", valueWithUnit(geometry.perimeter_m, "m"))}
      ${infoCell("Centroid", geometry.centroid ? `${formatNullable(geometry.centroid.lat)}, ${formatNullable(geometry.centroid.lon)}` : "")}
      ${infoCell("Altitude", statsRange(altitude, "m"))}
      ${infoCell("Altitude mean", statMeanSd(altitude, "m"))}
      ${infoCell("Slope", statsRange(slope, "deg"))}
      ${infoCell("Slope mean", statMeanSd(slope, "deg"))}
      ${infoCell("Terrain ruggedness", statsRange(ruggedness, "m"))}
      ${infoCell("TRI mean", statMeanSd(ruggedness, "m"))}
      ${infoCell("Aspect", aspect ? `${aspect.dominant_direction} (${formatNullable(aspect.mean_deg)} deg)` : "")}
      ${infoCell("Aspect sd", valueWithUnit(aspect?.sd_deg, "deg"))}
    </div>
  `;
}

function infoCell(label, value) {
  return `<div><strong>${escapeHtml(label)}</strong>${escapeHtml(value || "")}</div>`;
}

function statsRange(stats, unit) {
  if (!stats) return "";
  return `${formatNullable(stats.min)}-${formatNullable(stats.max)} ${unit}`;
}

function statMeanSd(stats, unit) {
  if (!stats) return "";
  return `${formatNullable(stats.mean)} ${unit} (sd ${formatNullable(stats.sd)})`;
}

function valueWithUnit(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return `${formatNullable(value)} ${unit}`;
}

function formatNullable(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return formatNumber(Number(value));
}

function standStyle(id) {
  const active = Number(id) === Number(selectedStandId);
  return {
    color: active ? "#1f5fbf" : "#2f6b45",
    weight: active ? 3 : 2,
    fillOpacity: active ? 0.28 : 0.18,
  };
}

async function previewDefaults() {
  setStatus("Previewing defaults...");
  try {
    const data = await request("/simulation-runs/default-preview", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    $("results").innerHTML = `<pre class="message">${escapeHtml(JSON.stringify(data.completed_parameters, null, 2))}</pre>`;
    setStatus("Defaults ready");
  } catch (error) {
    showError(error);
  }
}

async function previewTables() {
  setStatus("Building r3PG tables...");
  try {
    const data = await request("/simulation-runs/r3pg-tables", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    $("results").innerHTML = `<pre class="message">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
    $("plots").innerHTML = "";
    setStatus("r3PG tables ready");
  } catch (error) {
    showError(error);
  }
}

async function runSimulation() {
  setStatus("Running r3PG...");
  try {
    const data = await request("/simulation-runs", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    lastRunId = data.id;
    selectedStandId = data.stand_id ?? null;
    $("standId").value = data.stand_id ?? "";
    lastOutputs = data.outputs || [];
    lastDiagnostics = data.summary?.diagnostics || [];
    thinningKeys = buildThinningKeys();
    resultsTableCollapsed = false;
    renderOutputs(lastOutputs);
    renderPlots();
    setStatus(`Run ${data.id} completed: ${outputSpeciesNames(lastOutputs).join("; ") || "no species output"}`);
    await loadStands();
    await loadSimulationRunsForStand(data.stand_id);
    setSelectedSimulationRun(data.id);
  } catch (error) {
    showError(error);
  }
}

function outputSpeciesNames(outputs) {
  return [...new Set(
    (outputs || [])
      .map((item) => item.output?.species)
      .filter(Boolean)
  )];
}

async function loadSimulationRunsForStand(standId = numberValue("standId")) {
  const select = $("simulationRunSelect");
  const status = $("runHistoryStatus");
  if (!standId) {
    savedSimulationRuns = [];
    select.innerHTML = `<option value="">Select a saved run</option>`;
    status.textContent = "Select a stand to see saved simulations.";
    return;
  }
  status.classList.remove("error");
  status.textContent = "Loading saved runs...";
  savedSimulationRuns = await request(`/simulation-runs/stand/${standId}`);
  renderSimulationRunSelect();
  status.textContent = savedSimulationRuns.length
    ? `${savedSimulationRuns.length} saved run${savedSimulationRuns.length === 1 ? "" : "s"} for stand ${standId}.`
    : `No saved runs for stand ${standId}.`;
}

function renderSimulationRunSelect() {
  const select = $("simulationRunSelect");
  select.innerHTML = "";
  savedSimulationRuns.forEach((run) => {
    const option = document.createElement("option");
    option.value = run.id;
    option.textContent = simulationRunLabel(run);
    select.appendChild(option);
  });
}

function simulationRunLabel(run) {
  const created = run.created_at ? new Date(run.created_at).toLocaleString() : "";
  const input = run.input_parameters?.field_input || {};
  const entries = input.species_entries || [];
  const species = entries.map((entry) => entry.cohort_label ? `${entry.species} ${entry.cohort_label}` : entry.species).filter(Boolean).join(", ");
  const years = input.horizon_years ? `${input.horizon_years}y` : "";
  return [`Run ${run.id}`, run.status, created, species, years].filter(Boolean).join(" - ");
}

function setSelectedSimulationRun(runId) {
  const select = $("simulationRunSelect");
  if (!select) return;
  [...select.options].forEach((option) => {
    option.selected = Number(option.value) === Number(runId);
  });
}

function selectedSimulationRunIds() {
  return [...($("simulationRunSelect")?.selectedOptions || [])]
    .filter((option) => option.value !== "")
    .map((option) => Number(option.value))
    .filter((runId) => Number.isFinite(runId));
}

function selectedSavedRuns() {
  const runIds = selectedSimulationRunIds();
  return runIds
    .map((runId) => savedSimulationRuns.find((item) => Number(item.id) === Number(runId)))
    .filter(Boolean);
}

function selectedSavedRun() {
  const runId = selectedSimulationRunIds()[0];
  if (!runId) throw new Error("Select a saved simulation run first.");
  const run = savedSimulationRuns.find((item) => Number(item.id) === Number(runId));
  if (!run) throw new Error(`Saved run ${runId} is not loaded. Refresh simulation runs.`);
  return run;
}

function displaySimulationRun(run, message) {
  lastRunId = run.id;
  selectedStandId = run.stand_id ?? selectedStandId;
  setInputValue("standId", run.stand_id);
  applyFieldInputToForm(run.input_parameters?.field_input || {});
  lastOutputs = run.outputs || [];
  lastDiagnostics = run.summary?.diagnostics || [];
  thinningKeys = buildThinningKeys();
  resultsTableCollapsed = false;
  renderOutputs(lastOutputs);
  renderPlots();
  setSelectedSimulationRun(run.id);
  setStatus(message || `Run ${run.id} loaded`);
}

async function loadSelectedSimulationRun() {
  try {
    const run = selectedSavedRun();
    displaySimulationRun(run);
  } catch (error) {
    showRunHistoryError(error);
  }
}

async function rerunSelectedSimulationRun() {
  try {
    const run = selectedSavedRun();
    setStatus(`Rerunning ${run.id}...`);
    const data = await request("/simulation-runs", {
      method: "POST",
      body: JSON.stringify(run.input_parameters),
    });
    lastRunId = data.id;
    await loadSimulationRunsForStand(data.stand_id);
    displaySimulationRun(data, `Run ${data.id} completed from run ${run.id}`);
  } catch (error) {
    showRunHistoryError(error);
  }
}

function useSelectedRunInChat() {
  try {
    const runs = selectedSavedRuns();
    if (!runs.length) throw new Error("Select one or more saved simulation runs first.");
    lastRunId = runs[0].id;
    selectedStandId = runs[0].stand_id ?? selectedStandId;
    setInputValue("standId", runs[0].stand_id);
    const label = runs.map((run) => run.id).join(", ");
    setStatus(`Runs ${label} will be used in chat`);
    $("runHistoryStatus").classList.remove("error");
    $("runHistoryStatus").textContent = `Chat context set to run${runs.length === 1 ? "" : "s"} ${label}.`;
  } catch (error) {
    showRunHistoryError(error);
  }
}

function downloadSelectedSimulationRunCsv() {
  try {
    const run = selectedSavedRun();
    window.location.href = `/simulation-runs/${run.id}/outputs.csv`;
    $("runHistoryStatus").classList.remove("error");
    $("runHistoryStatus").textContent = `Downloading CSV for run ${run.id}.`;
  } catch (error) {
    showRunHistoryError(error);
  }
}

async function deleteSelectedSimulationRun() {
  try {
    const run = selectedSavedRun();
    if (!window.confirm(`Delete simulation run ${run.id}?`)) return;
    await request(`/simulation-runs/${run.id}`, { method: "DELETE" });
    if (Number(lastRunId) === Number(run.id)) {
      lastRunId = null;
      lastOutputs = [];
      lastDiagnostics = [];
      thinningKeys = new Set();
      $("results").innerHTML = "";
      $("plots").innerHTML = "";
    }
    await loadSimulationRunsForStand(run.stand_id || numberValue("standId"));
    setStatus(`Run ${run.id} deleted`);
    $("runHistoryStatus").classList.remove("error");
    $("runHistoryStatus").textContent = `Run ${run.id} deleted.`;
  } catch (error) {
    showRunHistoryError(error);
  }
}

function showRunHistoryError(error) {
  const status = $("runHistoryStatus");
  status.classList.add("error");
  status.textContent = error.message;
  setStatus("Error");
}

function renderOutputs(outputs) {
  if (!outputs.length) {
    $("results").innerHTML = `<div class="message">No outputs returned.</div>`;
    $("plots").innerHTML = "";
    return;
  }
  const rows = outputs.map((item) => item.output || {});
  const preview = rows.slice(0, 80);
  const tableClass = resultsTableCollapsed ? "output-table-wrap collapsed" : "output-table-wrap";
  $("toggleResultsTable").textContent = resultsTableCollapsed ? "Show years" : "Collapse years";
  $("results").innerHTML = `
    <div class="${tableClass}">
      <table class="output-table">
        <thead>
          <tr>
            <th>Year</th><th>Species</th><th>Age</th><th>N/ha</th><th>BA</th><th>DBH</th><th>Mean height</th><th>Vol</th>
          </tr>
        </thead>
        <tbody>
          ${preview.map((row) => `
          <tr class="${thinningKeys.has(`${row.species}::${row.age_years}`) ? "thin-row" : ""}">
            <td>${cell(row.year)}</td>
            <td>${cell(row.species)}</td>
            <td>${cell(row.age_years)}</td>
            <td>${cell(row.stems_per_ha)}</td>
            <td>${cell(row.basal_area_m2_ha)}</td>
            <td>${cell(row.mean_dbh_cm)}</td>
            <td>${cell(row.mean_height_m)}</td>
            <td>${cell(row.standing_volume_m3_ha)}</td>
          </tr>
        `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function buildThinningKeys() {
  const keys = new Set();
  for (let row = 1; row <= speciesRowCount; row += 1) {
    const species = value(`species_${row}`);
    const cohort = value(`cohort_${row}`);
    const age = numberValue(`age_${row}`);
    if (!species || age === null) continue;
    const label = outputSpeciesLabel(species, cohort);
    for (let thin = 1; thin <= thinningCount; thin += 1) {
      const percent = numberValue(`thin_percent_${row}_${thin}`);
      const year = numberValue(`thin_year_${thin}`);
      if (percent !== null && year !== null) {
        keys.add(`${label}::${age + year}`);
      }
    }
  }
  return keys;
}

function renderPlots() {
  const plots = $("plots");
  plots.innerHTML = "";
  if (!$("showGrowthPlots").checked || !lastOutputs.length) return;

  const rows = lastOutputs.map((item) => item.output || {});
  const plotSpecs = [
    ["stems_per_ha", "Stem number", "trees/ha"],
    ["basal_area_m2_ha", "Basal area", "m2/ha"],
    ["mean_dbh_cm", "Mean diameter", "cm"],
    ["mean_height_m", "Mean height", "m"],
    ["standing_volume_m3_ha", "Standing volume", "m3/ha"],
  ];
  plots.innerHTML = `
    <div class="plot-grid">
      ${plotSpecs.map(([field, title, unit]) => lineChart(rows, field, title, unit)).join("")}
      ${lineChart(totalByYear(rows, "standing_volume_m3_ha", "total_volume"), "total_volume", "Total standing volume", "m3/ha")}
    </div>
    ${diagnosticCharts(lastDiagnostics)}
  `;
}

function diagnosticCharts(diagnostics) {
  if (!diagnostics.length) return "";
  const specs = [
    ["stems_start", "Stem number start", "trees/ha"],
    ["mort_stress_sum", "Stress mortality sum", "t/ha/y"],
    ["lai_mean", "Mean leaf area index", "m2/m2"],
    ["lai_max", "Maximum leaf area index", "m2/m2"],
    ["mort_thinn_sum", "Self-thinning sum", "trees/ha/y"],
    ["gamma_n_mean", "Mean gammaN", "factor"],
    ["biom_tree", "Tree biomass", "t/tree"],
    ["canopy_volume_fraction", "Canopy occupancy", "proportion"],
  ];
  return `
    <details class="diagnostics">
      <summary>Diagnostics</summary>
      <div class="plot-grid">
        ${specs.map(([field, title, unit]) => lineChart(diagnostics, field, title, unit)).join("")}
      </div>
    </details>
  `;
}

function lineChart(rows, field, title, unit) {
  const data = rows
    .map((row) => ({
      year: Number(row.year),
      species: row.species || "Total",
      value: row[field] === null || row[field] === undefined ? null : Number(row[field]),
    }))
    .filter((row) => Number.isFinite(row.year) && Number.isFinite(row.value));

  if (!data.length) {
    return `<div class="chart-card"><h3>${escapeHtml(title)}</h3><div class="empty-chart">No data</div></div>`;
  }

  const width = 330;
  const height = 170;
  const pad = { left: 42, right: 12, top: 12, bottom: 28 };
  const years = data.map((row) => row.year);
  const values = data.map((row) => row.value);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const species = [...new Set(data.map((row) => row.species))];
  const colors = chartColors(species);
  const x = (year) => {
    if (maxYear === minYear) return (width - pad.left - pad.right) / 2 + pad.left;
    return pad.left + ((year - minYear) / (maxYear - minYear)) * (width - pad.left - pad.right);
  };
  const y = (value) => {
    if (maxValue === minValue) return (height - pad.top - pad.bottom) / 2 + pad.top;
    return height - pad.bottom - ((value - minValue) / (maxValue - minValue)) * (height - pad.top - pad.bottom);
  };
  const lines = species.map((name) => {
    const points = data
      .filter((row) => row.species === name)
      .sort((a, b) => a.year - b.year)
      .map((row) => `${x(row.year).toFixed(1)},${y(row.value).toFixed(1)}`)
      .join(" ");
    return `<polyline points="${points}" fill="none" stroke="${colors[name]}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" />`;
  }).join("");
  const legend = species.map((name) => `
    <span><i style="background:${colors[name]}"></i>${escapeHtml(name)}</span>
  `).join("");

  return `
    <div class="chart-card">
      <h3>${escapeHtml(title)}</h3>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
        <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" class="axis" />
        <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" class="axis" />
        <text x="${pad.left}" y="${height - 7}" class="axis-label">${minYear}</text>
        <text x="${width - pad.right}" y="${height - 7}" text-anchor="end" class="axis-label">${maxYear}</text>
        <text x="4" y="${pad.top + 8}" class="axis-label">${formatNumber(maxValue)}</text>
        <text x="4" y="${height - pad.bottom}" class="axis-label">${formatNumber(minValue)}</text>
        ${lines}
      </svg>
      <div class="chart-meta">${escapeHtml(unit)}</div>
      <div class="legend">${legend}</div>
    </div>
  `;
}

function totalByYear(rows, sourceField, targetField) {
  const totals = new Map();
  rows.forEach((row) => {
    const year = Number(row.year);
    const value = Number(row[sourceField]);
    if (!Number.isFinite(year) || !Number.isFinite(value)) return;
    totals.set(year, (totals.get(year) || 0) + value);
  });
  return [...totals.entries()].map(([year, value]) => ({ year, species: "Total", [targetField]: value }));
}

function chartColors(speciesLabels) {
  const palette = ["#2f6b45", "#bd7b21", "#9b3f35", "#3568a8", "#6f4a8e", "#4f8f8b", "#b45f06", "#5f6f2a", "#8a4f3d"];
  const baseNames = [];
  speciesLabels.forEach((label) => {
    const base = String(label).split("|", 1)[0].trim();
    if (!baseNames.includes(base)) baseNames.push(base);
  });
  const baseColors = Object.fromEntries(baseNames.map((name, index) => [name, palette[index % palette.length]]));
  return Object.fromEntries(speciesLabels.map((label) => [label, baseColors[String(label).split("|", 1)[0].trim()]]));
}

async function askChat() {
  const question = value("question");
  if (!question) return;
  $("chatAnswer").innerHTML = `<div class="message">Thinking...</div>`;
  try {
    const selectedRunIds = selectedSimulationRunIds();
    const simulationRunIds = selectedRunIds.length ? selectedRunIds : (lastRunId ? [lastRunId] : []);
    const data = await request("/chat", {
      method: "POST",
      body: JSON.stringify(clean({
        question,
        stand_id: numberValue("standId"),
        simulation_run_id: simulationRunIds[0],
        simulation_run_ids: simulationRunIds,
        session_id: chatSessionId,
        top_k: 12,
      })),
    });
    chatSessionId = data.session_id;
    $("chatAnswer").innerHTML = `<div class="message">${escapeHtml(data.answer).replace(/\n/g, "<br>")}</div>`;
  } catch (error) {
    $("chatAnswer").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
  }
}

async function uploadRagDocument() {
  const input = $("ragDocumentFile");
  const file = input.files?.[0];
  if (!file) throw new Error("Choose a document first.");

  const status = $("ragUploadStatus");
  status.classList.remove("error");
  status.textContent = "Uploading and ingesting...";

  const formData = new FormData();
  formData.append("file", file);
  const result = await uploadRequest("/documents/upload-ingest", formData);

  if (result.documents_ingested) {
    status.textContent = `Ingested ${result.file_name}: ${result.chunks_created} chunks created.`;
  } else {
    status.textContent = `${result.file_name} was already in the knowledge base.`;
  }
  input.value = "";
}

function showUploadError(error) {
  const status = $("ragUploadStatus");
  status.classList.add("error");
  status.textContent = error.message;
}

function clearForm() {
  document.querySelectorAll(".panel-left input, .panel-left select, .panel-left textarea").forEach((node) => {
    node.value = "";
  });
  $("cohort_1").value = "30y";
  selectedStandId = null;
  lastRunId = null;
  chatSessionId = null;
  lastOutputs = [];
  lastDiagnostics = [];
  thinningKeys = new Set();
  resultsTableCollapsed = false;
  observationsVisible = false;
  savedSimulationRuns = [];
  syncThinningLabels();
  $("results").innerHTML = "";
  $("plots").innerHTML = "";
  $("chatAnswer").innerHTML = "";
  $("simulationRunSelect").innerHTML = `<option value="">Select a saved run</option>`;
  $("runHistoryStatus").textContent = "";
  $("runHistoryStatus").classList.remove("error");
  $("ragUploadStatus").textContent = "";
  $("ragUploadStatus").classList.remove("error");
  $("standInfo").classList.add("collapsed");
  $("observationsPanel").classList.add("collapsed");
  $("observationsList").innerHTML = "";
  $("toggleResultsTable").textContent = "Collapse years";
  setStatus("");
}

function setStatus(message) {
  $("runStatus").textContent = message;
}

function showError(error) {
  setStatus("Error");
  $("results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
}

function cell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(2);
  return escapeHtml(String(value));
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return "";
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  buildSpeciesRows();
  buildThinningRows();
  bindMirrors();
  $("refreshStands").addEventListener("click", loadStands);
  $("saveStand").addEventListener("click", () => {
    saveStand().catch(showError);
  });
  $("linkGeometry").addEventListener("click", () => {
    linkStandGeometry().catch(showError);
  });
  $("previewDefaults").addEventListener("click", previewDefaults);
  $("previewTables").addEventListener("click", previewTables);
  $("runSimulation").addEventListener("click", runSimulation);
  $("refreshRuns").addEventListener("click", () => {
    loadSimulationRunsForStand().catch(showRunHistoryError);
  });
  $("loadRun").addEventListener("click", loadSelectedSimulationRun);
  $("rerunRun").addEventListener("click", rerunSelectedSimulationRun);
  $("downloadRunCsv").addEventListener("click", downloadSelectedSimulationRunCsv);
  $("useRunInChat").addEventListener("click", useSelectedRunInChat);
  $("deleteRun").addEventListener("click", deleteSelectedSimulationRun);
  $("showGrowthPlots").addEventListener("change", renderPlots);
  $("toggleResultsTable").addEventListener("click", () => {
    if (!lastOutputs.length) return;
    resultsTableCollapsed = !resultsTableCollapsed;
    renderOutputs(lastOutputs);
    renderPlots();
  });
  $("askChat").addEventListener("click", askChat);
  $("uploadRagDocument").addEventListener("click", () => {
    uploadRagDocument().catch(showUploadError);
  });
  $("newChat").addEventListener("click", () => {
    chatSessionId = null;
    $("chatAnswer").innerHTML = "";
  });
  $("collapseStandInfo").addEventListener("click", () => {
    $("standInfo").classList.add("collapsed");
  });
  $("toggleObservations").addEventListener("click", () => {
    toggleObservationsPanel().catch(showError);
  });
  $("saveObservation").addEventListener("click", () => {
    saveObservation().catch(showError);
  });
  $("clearForm").addEventListener("click", clearForm);
  loadStands().catch((error) => {
    $("standList").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
  });
});
