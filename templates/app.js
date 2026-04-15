(function () {
  "use strict";

  const defaultCenter = [20, 0];
  const defaultZoom = 2;

  const HIT_LINE = { color: "#000", weight: 22, opacity: 0, fillOpacity: 0 };

  function initThemeToggle() {
    const root = document.documentElement;
    const btn = document.getElementById("theme-toggle");
    const icon = document.getElementById("theme-toggle-icon");
    if (!btn || !icon) return;

    function apply(theme) {
      if (theme === "light") root.setAttribute("data-theme", "light");
      else root.removeAttribute("data-theme");
      icon.className =
        theme === "light" ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
      btn.setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
      btn.title = theme === "light" ? "Light theme" : "Dark theme";
    }

    let theme = "dark";
    try {
      const saved = localStorage.getItem("theme");
      if (saved === "light" || saved === "dark") theme = saved;
      else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) theme = "light";
    } catch (e) {}
    apply(theme);

    btn.addEventListener("click", function () {
      theme = theme === "light" ? "dark" : "light";
      try {
        localStorage.setItem("theme", theme);
      } catch (e) {}
      apply(theme);
    });
  }

  function createLoader() {
    const elRoot = document.getElementById("app-loader");

    function show() {
      if (!elRoot) return;
      elRoot.classList.remove("is-hidden");
      elRoot.setAttribute("aria-busy", "true");
    }

    function hide() {
      if (!elRoot) return;
      elRoot.classList.add("is-hidden");
      elRoot.setAttribute("aria-busy", "false");
    }

    return { show: show, hide: hide };
  }

  function createTaskTracker(loader) {
    let pending = 0;
    let finished = false;

    function begin() {
      pending++;
    }

    function end() {
      pending = Math.max(0, pending - 1);
      if (pending === 0 && finished && loader) loader.hide();
    }

    function markFinished() {
      finished = true;
      if (pending === 0 && loader) loader.hide();
    }

    return { begin: begin, end: end, markFinished: markFinished };
  }

  function el(tag, props, children) {
    const node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        if (k === "className") node.className = props[k];
        else if (k === "text") node.textContent = props[k];
        else node.setAttribute(k, props[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c) node.appendChild(c);
    });
    return node;
  }

  function palette(i) {
    const colors = ["#3d9cf5", "#6bcf7f", "#f5b03d", "#c678ff", "#ff6b6b", "#4ecdc4"];
    return colors[i % colors.length];
  }

  function setBoundsFromBbox(layerMeta) {
    const b = layerMeta.bbox;
    if (Array.isArray(b) && b.length === 4) {
      layerMeta._bounds = L.latLngBounds([b[1], b[0]], [b[3], b[2]]);
    }
  }

  /** Loose match for QGIS category values vs GeoJSON attribute types (number vs string, etc.). */
  function styleValuesEqual(a, b) {
    if (a === b) return true;
    if (a == null && b == null) return true;
    if (a == null || b == null) return false;
    if (String(a).trim() === String(b).trim()) return true;
    const na = Number(a);
    const nb = Number(b);
    if (!isNaN(na) && !isNaN(nb) && na === nb) return true;
    return false;
  }

  function pickSymbolStyle(style, feature, fallbackColor) {
    if (!style || style.mode === "default") return null;
    if (style.mode === "single") return style.style;
    if (style.mode === "categorized") {
      const f = style.field;
      const v = feature.properties && feature.properties[f];
      const cats = style.categories || [];
      for (let i = 0; i < cats.length; i++) {
        if (styleValuesEqual(cats[i].value, v)) return cats[i].style;
      }
      if (cats.length) return cats[0].style;
      return null;
    }
    if (style.mode === "graduated") {
      const f = style.field;
      const raw = feature.properties && feature.properties[f];
      const num = parseFloat(raw);
      if (isNaN(num)) return null;
      const ranges = style.ranges || [];
      for (let i = 0; i < ranges.length; i++) {
        const r = ranges[i];
        const lo = parseFloat(r.lower);
        const hi = parseFloat(r.upper);
        if (!isNaN(lo) && !isNaN(hi) && num >= lo && num <= hi) return r.style;
      }
      return null;
    }
    return null;
  }

  function pathStyleFromSymbol(s, fallbackColor) {
    if (!s) {
      return {
        color: fallbackColor,
        weight: 2,
        opacity: 0.95,
        fillColor: fallbackColor,
        fillOpacity: 0.2,
      };
    }
    if (s.kind === "line") {
      return {
        color: s.color || fallbackColor,
        weight: s.weight != null ? s.weight : 2,
        opacity: s.opacity != null ? s.opacity : 0.9,
        fillOpacity: 0,
      };
    }
    return {
      color: s.color || fallbackColor,
      weight: s.weight != null ? s.weight : 2,
      opacity: s.opacity != null ? s.opacity : 0.9,
      fillColor: s.fillColor || s.color || fallbackColor,
      fillOpacity: s.fillOpacity != null ? s.fillOpacity : 0.25,
    };
  }

  function circleOptionsFromSymbol(s, fallbackColor) {
    if (!s || s.kind !== "point") {
      return {
        radius: 6,
        color: fallbackColor,
        fillColor: fallbackColor,
        weight: 1,
        opacity: 1,
        fillOpacity: 0.7,
      };
    }
    return {
      radius: s.radius != null ? s.radius : 6,
      color: s.color || fallbackColor,
      fillColor: s.fillColor || s.color || fallbackColor,
      weight: s.weight != null ? s.weight : 1,
      opacity: s.opacity != null ? s.opacity : 1,
      fillOpacity: s.fillOpacity != null ? s.fillOpacity : 0.7,
    };
  }

  function normalizeLayers(manifest) {
    const raw = manifest.layers || [];
    const out = raw.map(function (Lyr, i) {
      const copy = Object.assign({}, Lyr);
      if (!copy.type) copy.type = "vector";
      if (copy.order == null) copy.order = i;
      return copy;
    });
    out.sort(function (a, b) {
      return (a.order || 0) - (b.order || 0);
    });
    return out;
  }

  /**
   * Layers are sorted by manifest `order` ascending (smaller number first). That order matches QGIS-style stacking:
   * smaller `order` = drawn on top in Leaflet (higher z-index band).
   * Each layer gets a fixed z-index band so sub-panes (e.g. vector hit) never sit above another layer's tiles.
   */
  var OVERLAY_Z_BASE = 360;
  var OVERLAY_Z_STEP = 50;

  function overlayPaneZ(layerIndex, subOffset) {
    return OVERLAY_Z_BASE + layerIndex * OVERLAY_Z_STEP + (subOffset || 0);
  }

  function ensurePane(map, name, zIndex) {
    if (!map.getPane(name)) {
      map.createPane(name);
    }
    const p = map.getPane(name);
    if (p) p.style.zIndex = String(zIndex);
    return name;
  }

  /** Show or hide every Leaflet layer belonging to one story layer (overlay only, not basemap). */
  function setRecordVisible(map, rec, on) {
    (rec.leafletLayers || []).forEach(function (lyr) {
      if (!lyr) return;
      if (on) {
        if (!map.hasLayer(lyr)) lyr.addTo(map);
      } else if (map.hasLayer(lyr)) {
        map.removeLayer(lyr);
      }
    });
  }

  function layerTypeLabel(meta) {
    if (meta.type === "raster") return "Raster";
    if (meta.renderMode === "qgis") return "Vector (tiles + GeoJSON)";
    if (meta.renderMode === "tiles") return meta.type === "raster" ? "Raster (tiles)" : "Vector (tiles)";
    if (meta.renderMode === "image") return meta.type === "raster" ? "Raster (image)" : "Vector (image)";
    return "Vector (GeoJSON)";
  }

  function buildLayerControl(map, layers) {
    const root = document.getElementById("layer-control-root");
    if (!root || !layers.length) return;
    root.removeAttribute("hidden");
    root.innerHTML = "";
    const inner = el("div", { className: "layer-control-inner" });
    const head = el("div", { className: "layer-control-head" });
    const h2 = el("h2", { className: "layer-control-title" });
    const hIcon = document.createElement("i");
    hIcon.className = "bi bi-stack";
    hIcon.setAttribute("aria-hidden", "true");
    h2.appendChild(hIcon);
    h2.appendChild(document.createTextNode(" Layers"));
    const allBtn = el("button", {
      type: "button",
      className: "layer-control-toggle-all",
    });
    head.appendChild(h2);
    head.appendChild(allBtn);
    inner.appendChild(head);
    const ul = el("ul", { className: "layer-control-list" });
    const checkboxes = [];

    function syncAllButtonLabel() {
      const allOn = checkboxes.every(function (c) {
        return c.checked;
      });
      allBtn.innerHTML =
        '<i class="bi ' +
        (allOn ? "bi-eye-slash" : "bi-eye") +
        '" aria-hidden="true"></i><span>' +
        (allOn ? "Hide all" : "Show all") +
        "</span>";
    }

    layers.forEach(function (rec, idx) {
      const lid = String(rec.meta.id != null ? rec.meta.id : idx);
      const id = "layer-vis-" + idx + "-" + lid.replace(/[^a-zA-Z0-9_-]/g, "_");
      const li = el("li", { className: "layer-control-row" });
      const inp = document.createElement("input");
      inp.type = "checkbox";
      inp.id = id;
      inp.checked = true;
      inp.setAttribute("aria-label", "Show layer: " + (rec.meta.name || "layer"));
      const lab = el("label", { for: id });
      lab.appendChild(document.createTextNode(rec.meta.name || "Layer"));
      li.appendChild(inp);
      li.appendChild(lab);
      ul.appendChild(li);
      checkboxes.push(inp);
      inp.addEventListener("change", function () {
        setRecordVisible(map, rec, inp.checked);
        syncAllButtonLabel();
      });
    });

    inner.appendChild(ul);
    root.appendChild(inner);
    syncAllButtonLabel();

    allBtn.addEventListener("click", function () {
      const allOn = checkboxes.every(function (c) {
        return c.checked;
      });
      const next = !allOn;
      checkboxes.forEach(function (cb, i) {
        cb.checked = next;
        setRecordVisible(map, layers[i], next);
      });
      syncAllButtonLabel();
    });
  }

  /** Basemap dropdown (Leaflet): OSM, Google street, Google satellite — all on low z-index pane under overlays. */
  function setupBasemapSwitcher(map) {
    map.createPane("basemap");
    const bp = map.getPane("basemap");
    if (bp) bp.style.zIndex = "200";

    const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      pane: "basemap",
    });

    const streetLayer = L.tileLayer("https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", {
      maxZoom: 20,
      subdomains: ["0", "1", "2", "3"],
      attribution: '&copy; <a href="https://www.google.com/maps">Google</a>',
      pane: "basemap",
    });

    const satelliteLayer = L.tileLayer("https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", {
      maxZoom: 20,
      subdomains: ["0", "1", "2", "3"],
      attribution: '&copy; <a href="https://www.google.com/maps">Google</a>',
      pane: "basemap",
    });

    const byKey = { osm: osmLayer, street: streetLayer, satellite: satelliteLayer };

    let current = osmLayer;
    osmLayer.addTo(map);

    const root = document.querySelector(".basemap-switcher");
    const menuBtn = document.getElementById("basemapMenuBtn");
    const optionsEl = document.getElementById("basemapOptions");
    const menuThumb = document.getElementById("basemapMenuThumb");
    if (!root || !menuBtn || !optionsEl) return;

    function closeMenu() {
      optionsEl.hidden = true;
      menuBtn.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
      optionsEl.hidden = false;
      menuBtn.setAttribute("aria-expanded", "true");
    }

    function toggleMenu() {
      if (optionsEl.hidden) openMenu();
      else closeMenu();
    }

    function setActiveOption(key) {
      optionsEl.querySelectorAll(".basemap-option").forEach(function (btn) {
        const on = btn.getAttribute("data-basemap") === key;
        btn.classList.toggle("selected", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      const activeBtn = optionsEl.querySelector('[data-basemap="' + key + '"]');
      if (activeBtn && menuThumb) {
        const im = activeBtn.querySelector("img");
        if (im && im.src) menuThumb.src = im.src;
      }
    }

    function selectBasemap(key) {
      const next = byKey[key];
      if (!next) {
        closeMenu();
        return;
      }
      if (next !== current) {
        map.removeLayer(current);
        current = next;
        current.addTo(map);
      }
      setActiveOption(key);
      closeMenu();
    }

    menuBtn.addEventListener("click", function () {
      toggleMenu();
    });

    optionsEl.querySelectorAll(".basemap-option").forEach(function (btn) {
      btn.addEventListener("click", function () {
        selectBasemap(btn.getAttribute("data-basemap"));
      });
    });

    document.addEventListener("click", function (ev) {
      if (!root.contains(ev.target)) closeMenu();
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !optionsEl.hidden) closeMenu();
    });

    setActiveOption("osm");
  }

  function setupLegendToggle() {
    const panel = document.getElementById("map-legend-panel");
    const btn = document.getElementById("legend-toggle-btn");
    if (!panel || !btn) return;
    btn.addEventListener("click", function () {
      panel.classList.toggle("legend-panel--collapsed");
      const collapsed = panel.classList.contains("legend-panel--collapsed");
      panel.style.display = collapsed ? "none" : "flex";
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btn.title = collapsed ? "Show legend" : "Hide legend";
    });
  }

  function renderLegend(spec) {
    const root = document.getElementById("legend-content");
    const panel = document.getElementById("map-legend-panel");
    const toggleWrap = document.getElementById("legend-toggle-wrap");
    const toggleBtn = document.getElementById("legend-toggle-btn");
    if (!root || !panel) return;
    root.innerHTML = "";
    if (!spec || !spec.layers || !spec.layers.length) {
      panel.style.display = "none";
      if (toggleWrap) toggleWrap.hidden = true;
      return;
    }
    if (toggleWrap) toggleWrap.hidden = false;
    const collapsed = panel.classList.contains("legend-panel--collapsed");
    panel.style.display = collapsed ? "none" : "flex";
    if (toggleBtn) {
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      toggleBtn.title = collapsed ? "Show legend" : "Hide legend";
    }
    spec.layers.forEach(function (lg) {
      if (lg && lg.name) {
        root.appendChild(el("div", { className: "legend-layer-name", text: lg.name }));
      }
      const ul = el("ul", { className: "legend-items" });
      const rows = lg.items && lg.items.length ? lg.items : [{ label: lg.name || lg.id || "" }];
      rows.forEach(function (it) {
        const li = el("li", { className: "legend-row" });
        if (it.swatch && it.swatch.type === "ramp") {
          li.className = "legend-row legend-row--ramp";
          const wrap = el("div", { className: "legend-ramp" });
          const maxL = it.swatch.maxLabel != null ? String(it.swatch.maxLabel) : "";
          const minL = it.swatch.minLabel != null ? String(it.swatch.minLabel) : "";
          if (maxL || minL) {
            wrap.setAttribute("aria-label", "Color scale from " + (minL || "?") + " to " + (maxL || "?"));
          }
          const bar = el("span", { className: "legend-ramp-bar", "aria-hidden": "true" });
          bar.style.background = it.swatch.gradient || "transparent";
          const col = el("div", { className: "legend-ramp-labels", "aria-hidden": "true" });
          col.appendChild(el("span", { className: "legend-ramp-value legend-ramp-value--max", text: maxL }));
          col.appendChild(el("span", { className: "legend-ramp-value legend-ramp-value--min", text: minL }));
          wrap.appendChild(bar);
          wrap.appendChild(col);
          li.appendChild(wrap);
          if (it.label) li.appendChild(el("span", { className: "legend-label", text: it.label }));
        } else if (it.swatch) {
          const sw = el("span", { className: "legend-swatch", "aria-hidden": "true" });
          if (it.swatch.type === "fill") {
            sw.style.background = it.swatch.color || "transparent";
            sw.style.borderColor = it.swatch.outline || "transparent";
            if (it.swatch.outlineWidth != null && !isNaN(it.swatch.outlineWidth)) {
              sw.style.borderStyle = "solid";
              sw.style.borderWidth = String(it.swatch.outlineWidth) + "px";
            }
          } else if (it.swatch.type === "line") {
            sw.style.background = "transparent";
            sw.style.borderColor = "transparent";
            sw.style.position = "relative";
            const ln = el("span", { className: "legend-swatch-line", "aria-hidden": "true" });
            ln.style.background = it.swatch.color || "#fff";
            ln.style.height = (it.swatch.width != null ? it.swatch.width : 2) + "px";
            sw.appendChild(ln);
          }
          li.appendChild(sw);
          li.appendChild(el("span", { className: "legend-label", text: it.label || "" }));
        } else {
          li.appendChild(el("span", { className: "legend-icon-spacer", "aria-hidden": "true" }));
          li.appendChild(el("span", { className: "legend-label", text: it.label || "" }));
        }
        ul.appendChild(li);
      });
      root.appendChild(ul);
    });
  }

  /**
   * Parse SLD/SE XML into a Document, or null if invalid.
   * Prefixed tags (sld:, se:) are not visible to getElementsByTagName("ColorMapEntry") in some engines;
   * legend building always uses localName instead.
   */
  function sldParseDocument(xmlText) {
    if (!xmlText || typeof xmlText !== "string") return null;
    let doc = null;
    try {
      doc = new DOMParser().parseFromString(xmlText, "application/xml");
    } catch (e) {
      return null;
    }
    if (!doc || !doc.documentElement) return null;
    if (doc.querySelector("parsererror")) return null;
    return doc;
  }

  function sldDescendantsByLocalName(root, localName) {
    if (!root || !localName) return [];
    return Array.prototype.slice.call(root.getElementsByTagName("*")).filter(function (el) {
      return el.localName === localName;
    });
  }

  function sldRuleLabel(rule) {
    const desc = rule.getElementsByTagName("*");
    for (let i = 0; i < desc.length; i++) {
      const n = desc[i];
      if (n.localName === "Title" || n.localName === "Name") {
        const t = (n.textContent || "").trim();
        if (t) return t;
      }
    }
    return "Rule";
  }

  function sldParamMapForRule(rule) {
    const map = {};
    sldDescendantsByLocalName(rule, "CssParameter").forEach(function (n) {
      const k = n.getAttribute("name");
      if (k) map[k] = (n.textContent || "").trim();
    });
    sldDescendantsByLocalName(rule, "SvgParameter").forEach(function (n) {
      const k = n.getAttribute("name");
      if (k) map[k] = (n.textContent || "").trim();
    });
    return map;
  }

  function sldSwatchFromParams(pm) {
    let fill = pm.fill != null && pm.fill !== "" ? pm.fill : null;
    const fillOpRaw = pm["fill-opacity"];
    const fillOp = fillOpRaw != null && fillOpRaw !== "" ? parseFloat(fillOpRaw) : NaN;
    if (fill && !isNaN(fillOp) && fillOp <= 0) fill = "transparent";
    else if (fill && !isNaN(fillOp) && fillOp < 1) {
      const m = /^#([0-9a-fA-F]{6})$/.exec(fill);
      if (m) {
        const h = m[1];
        const a = Math.round(Math.min(1, Math.max(0, fillOp)) * 255);
        fill = "#" + h + (a < 16 ? "0" : "") + a.toString(16);
      }
    }
    const stroke = pm.stroke != null && pm.stroke !== "" ? pm.stroke : null;
    const strokeW = parseFloat(pm["stroke-width"]);
    if (!fill && !stroke) return null;
    const useFillSwatch = !!fill || (stroke && (isNaN(strokeW) || strokeW > 0));
    if (useFillSwatch && fill !== null) {
      return {
        type: "fill",
        color: fill || "transparent",
        outline: stroke || undefined,
        outlineWidth: !isNaN(strokeW) && strokeW > 0 ? Math.min(strokeW, 6) : undefined,
      };
    }
    return {
      type: "line",
      color: stroke || "#888",
      width: isNaN(strokeW) ? 2 : Math.min(strokeW, 8),
    };
  }

  /** Pretty-print numeric legend bounds from SLD quantities. */
  function formatLegendBound(v) {
    if (v == null || typeof v !== "number" || isNaN(v)) return "";
    if (Math.abs(v - Math.round(v)) < 1e-4) return String(Math.round(v));
    var t = Math.round(v * 100) / 100;
    return String(t);
  }

  /**
   * Build legend rows from raw SLD XML.
   * Raster: ColorMap type "ramp" (and default) → one vertical gradient + min/max;
   *         type "values" or "intervals" → one row per ColorMapEntry (class / bin).
   * Vector: Rule + CssParameter / SvgParameter.
   */
  function buildLegendItemsFromSld(xmlText) {
    const out = [];
    const doc = sldParseDocument(xmlText);
    if (!doc) return out;

    const entries = sldDescendantsByLocalName(doc, "ColorMapEntry");
    if (entries.length) {
      const parsed = [];
      entries.forEach(function (n) {
        const c = n.getAttribute("color");
        const q = n.getAttribute("quantity");
        const lbl = (n.getAttribute("label") || "").trim();
        const v = q != null ? parseFloat(q) : NaN;
        if (!c) return;
        const labelText = lbl || (q != null ? String(q) : "");
        parsed.push({ color: c, value: v, label: labelText });
      });
      if (parsed.length) {
        const colorMapNodes = sldDescendantsByLocalName(doc, "ColorMap");
        const cm = colorMapNodes[0];
        const rawType = cm && cm.getAttribute("type");
        const cmType = rawType ? String(rawType).trim().toLowerCase() : "";
        const isDiscreteRaster = cmType === "values" || cmType === "intervals";

        if (isDiscreteRaster) {
          parsed.sort(function (a, b) {
            if (!isNaN(a.value) && !isNaN(b.value) && a.value !== b.value) return a.value - b.value;
            return String(a.label).localeCompare(String(b.label));
          });
          parsed.forEach(function (p) {
            if (!p.label) return;
            out.push({
              label: p.label,
              swatch: { type: "fill", color: p.color },
            });
          });
          return out;
        }

        const stops = parsed.map(function (p) {
          return { color: p.color, value: p.value };
        });
        const values = parsed.map(function (p) { return p.value; }).filter(function (v) {
          return !isNaN(v);
        });
        const grad = "linear-gradient(to top, " + stops.map(function (s) { return s.color; }).join(", ") + ")";
        const vmin = values.length ? Math.min.apply(null, values) : null;
        const vmax = values.length ? Math.max.apply(null, values) : null;
        out.push({
          swatch: {
            type: "ramp",
            gradient: grad,
            min: vmin,
            max: vmax,
            minLabel: formatLegendBound(vmin),
            maxLabel: formatLegendBound(vmax),
          },
        });
        return out;
      }
    }

    const rules = sldDescendantsByLocalName(doc, "Rule");
    rules.forEach(function (r) {
      const label = sldRuleLabel(r);
      const pm = sldParamMapForRule(r);
      const sw = sldSwatchFromParams(pm);
      if (sw) out.push({ label: label, swatch: sw });
    });
    return out;
  }

  function loadLegend(manifest, tasks) {
    const panel = document.getElementById("map-legend-panel");
    const toggleWrap = document.getElementById("legend-toggle-wrap");
    if (!manifest.legend) {
      if (panel) panel.style.display = "none";
      if (toggleWrap) toggleWrap.hidden = true;
      return;
    }
    if (tasks) tasks.begin();
    fetch(manifest.legend)
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (spec) {
        if (!spec || !spec.layers) return spec;
        // If a layer has an SLD, try to derive legend items from it (for readability).
        const jobs = [];
        spec.layers.forEach(function (lg) {
          if (!lg || !lg.sld) return;
          if (tasks) tasks.begin();
          const j = fetch(lg.sld)
            .then(function (r) { return r.ok ? r.text() : null; })
            .then(function (txt) {
              const items = buildLegendItemsFromSld(txt || "");
              if (items && items.length) {
                // QGIS exports many simple vector styles as a single rule named "Single symbol".
                // In the legend, that label is not useful; show the layer name instead.
                if (
                  items.length === 1 &&
                  items[0] &&
                  items[0].swatch &&
                  items[0].swatch.type !== "ramp" &&
                  typeof items[0].label === "string"
                ) {
                  const low = items[0].label.trim().toLowerCase();
                  if (low === "single symbol" || low === "rule") {
                    items[0].label = lg.name || lg.id || items[0].label;
                  }
                }
                lg.items = items;
              } else {
                lg.items = [{ label: lg.name || lg.id || "" }];
              }
            })
            .catch(function () {
              lg.items = [{ label: lg.name || lg.id || "" }];
            })
            .finally(function () { if (tasks) tasks.end(); });
          jobs.push(j);
        });
        return Promise.all(jobs).then(function () { return spec; });
      })
      .then(renderLegend)
      .catch(function () {
        if (panel) panel.style.display = "none";
        if (toggleWrap) toggleWrap.hidden = true;
      })
      .finally(function () {
        if (tasks) tasks.end();
      });
  }

  function main(manifest) {
    initThemeToggle();
    const loader = createLoader();
    loader.show();
    const tasks = createTaskTracker(loader);

    document.getElementById("story-title").textContent = manifest.title || "Story Map";

    loadLegend(manifest, tasks);
    setupLegendToggle();

    const map = L.map("map", { scrollWheelZoom: true }).setView(defaultCenter, defaultZoom);
    setupBasemapSwitcher(map);

    const layers = [];
    const layerById = {};
    var refitLayerBoundsTimer = null;

    function fitAllLayerBounds() {
      let merged = null;
      layers.forEach(function (rec) {
        const b = rec.meta._bounds;
        if (b && b.isValid()) {
          merged = merged ? merged.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast());
        }
      });
      if (merged && merged.isValid()) {
        map.fitBounds(merged.pad(0.08), { animate: true, duration: 1.2, maxZoom: 16 });
      }
    }

    function scheduleFitAllLayerBounds() {
      if (refitLayerBoundsTimer) clearTimeout(refitLayerBoundsTimer);
      refitLayerBoundsTimer = setTimeout(fitAllLayerBounds, 200);
    }

    const ordered = normalizeLayers(manifest);

    ordered.forEach(function (layerMeta, idx) {
      const zBand = ordered.length - 1 - idx;
      const fallbackColor = palette(idx);
      setBoundsFromBbox(layerMeta);

      // Local XYZ tiles (exported from QGIS) for crisp zooming
      if (layerMeta.renderMode === "tiles" && layerMeta.tilesUrl) {
        const paneName = ensurePane(map, (layerMeta.type === "raster" ? "t-r-" : "t-v-") + layerMeta.id, overlayPaneZ(zBand, 0));
        // Leaflet "overzoom" behavior:
        // - set maxZoom higher than the exported max, but keep maxNativeZoom at exported max
        //   so tiles don't disappear when you zoom in further.
        const nativeMin = layerMeta.minZoom != null ? layerMeta.minZoom : 0;
        const nativeMax = layerMeta.maxZoom != null ? layerMeta.maxZoom : 18;
        const opts = {
          pane: paneName,
          minZoom: 0,
          maxZoom: 20,
          minNativeZoom: nativeMin,
          maxNativeZoom: nativeMax,
          tileSize: layerMeta.tileSize != null ? layerMeta.tileSize : 256,
          opacity: layerMeta.opacity != null ? layerMeta.opacity : 1,
          tms: false,
          keepBuffer: 2,
        };
        if (layerMeta._bounds && layerMeta._bounds.isValid()) {
          opts.bounds = layerMeta._bounds;
        }
        const tileL = L.tileLayer(layerMeta.tilesUrl, opts).addTo(map);
        layers.push({
          meta: layerMeta,
          tileLayer: tileL,
          leafletLayers: [tileL],
        });
        layerById[String(layerMeta.id)] = layers[layers.length - 1];
        return;
      }

      // Static image overlay for both vectors and rasters
      if (layerMeta.renderMode === "image" && layerMeta.image) {
        const paneName = ensurePane(map, (layerMeta.type === "raster" ? "img-r-" : "img-v-") + layerMeta.id, overlayPaneZ(zBand, 0));
        const opts = {
          pane: paneName,
          opacity: layerMeta.opacity != null ? layerMeta.opacity : 1,
          interactive: false,
        };
        if (layerMeta._bounds && layerMeta._bounds.isValid()) {
          // Leaflet uses latlng bounds
          const img = L.imageOverlay(layerMeta.image, layerMeta._bounds, opts).addTo(map);
          layers.push({
            meta: layerMeta,
            tileLayer: null,
            leafletLayers: [img],
          });
          layerById[String(layerMeta.id)] = layers[layers.length - 1];
          return;
        }
        // No bounds means we can't place it
        return;
      }

      if (layerMeta.type === "raster") {
        const paneName = ensurePane(map, "rast-" + layerMeta.id, overlayPaneZ(zBand, 0));
        const url = layerMeta.tilesUrl;
        const opts = {
          pane: paneName,
          minZoom: layerMeta.minZoom != null ? layerMeta.minZoom : 0,
          maxZoom: layerMeta.maxZoom != null ? layerMeta.maxZoom : 18,
          maxNativeZoom: layerMeta.maxZoom != null ? layerMeta.maxZoom : 18,
          opacity: layerMeta.opacity != null ? layerMeta.opacity : 1,
          tms: false,
        };
        if (layerMeta._bounds && layerMeta._bounds.isValid()) {
          opts.bounds = layerMeta._bounds;
        }
        const tileL = L.tileLayer(url, opts).addTo(map);
        layers.push({
          meta: layerMeta,
          tileLayer: tileL,
          leafletLayers: [tileL],
        });
        layerById[String(layerMeta.id)] = layers[layers.length - 1];
        return;
      }

      const styleDef = layerMeta.style;
      const useQgisTiles =
        layerMeta.renderMode === "qgis" && layerMeta.styleTilesUrl && layerMeta.styleTilesUrl.length;

      const leafletLayers = [];

      if (useQgisTiles) {
        const qPane = ensurePane(map, "qv-" + layerMeta.id, overlayPaneZ(zBand, 0));
        const tOpts = {
          pane: qPane,
          minZoom: layerMeta.styleTileMinZoom != null ? layerMeta.styleTileMinZoom : 0,
          maxZoom: layerMeta.styleTileMaxZoom != null ? layerMeta.styleTileMaxZoom : 18,
          maxNativeZoom: layerMeta.styleTileMaxZoom != null ? layerMeta.styleTileMaxZoom : 18,
          opacity: 1,
          tms: false,
        };
        if (layerMeta._bounds && layerMeta._bounds.isValid()) {
          tOpts.bounds = layerMeta._bounds;
        }
        const qTiles = L.tileLayer(layerMeta.styleTilesUrl, tOpts).addTo(map);
        leafletLayers.push(qTiles);
      }

      const hitPane = ensurePane(map, "hit-" + layerMeta.id, overlayPaneZ(zBand, 20));

      const gj = L.geoJSON(null, {
        pane: hitPane,
        style: function (feature) {
          if (useQgisTiles) return HIT_LINE;
          const sym = pickSymbolStyle(styleDef, feature, fallbackColor);
          return pathStyleFromSymbol(sym, fallbackColor);
        },
        pointToLayer: function (feature, latlng) {
          if (useQgisTiles) {
            return L.circleMarker(latlng, {
              pane: hitPane,
              radius: 14,
              color: "#000",
              weight: 1,
              opacity: 0,
              fillOpacity: 0,
            });
          }
          const sym = pickSymbolStyle(styleDef, feature, fallbackColor);
          const o = circleOptionsFromSymbol(sym, fallbackColor);
          o.pane = hitPane;
          return L.circleMarker(latlng, o);
        },
        onEachFeature: function (feature, lyr) {
          const props = feature.properties || {};
          const bits = Object.keys(props)
            .slice(0, 8)
            .map(function (k) {
              return "<strong>" + k + ":</strong> " + String(props[k]);
            });
          if (bits.length) lyr.bindPopup(bits.join("<br/>"));
        },
      }).addTo(map);

      if (layerMeta.file) {
        tasks.begin();
        fetch(layerMeta.file)
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            gj.addData(data);
            const fb = gj.getBounds && gj.getBounds();
            if (fb && fb.isValid()) {
              layerMeta._bounds = fb;
            }
            scheduleFitAllLayerBounds();
          })
          .catch(function () {})
          .finally(function () {
            tasks.end();
          });
      }

      leafletLayers.push(gj);
      layers.push({
        meta: layerMeta,
        tileLayer: null,
        gj: gj,
        leafletLayers: leafletLayers,
      });
      layerById[String(layerMeta.id)] = layers[layers.length - 1];
    });

    buildLayerControl(map, layers);

    // Story sections (side panel)
    function activateSection(sec) {
      if (!sec) return;
      // Intro / no-center sections: fly to overall project extent (merged layer bounds).
      if (!sec.center || !Array.isArray(sec.center) || sec.center.length !== 2) {
        try {
          fitAllLayerBounds();
        } catch (e) {}
        return;
      }
      // Focus point + zoom (ArcGIS-style).
      if (sec.center && Array.isArray(sec.center) && sec.center.length === 2) {
        const lon = parseFloat(sec.center[0]);
        const lat = parseFloat(sec.center[1]);
        const z = sec.zoom != null && !isNaN(sec.zoom) ? Math.max(0, Math.min(20, parseInt(sec.zoom, 10) || 0)) : null;
        if (isFinite(lon) && isFinite(lat)) {
          if (typeof map.flyTo === "function") {
            if (z != null) map.flyTo([lat, lon], z, { animate: true, duration: 1.2 });
            else map.flyTo([lat, lon], map.getZoom(), { animate: true, duration: 1.2 });
          } else {
            if (z != null) map.setView([lat, lon], z, { animate: true });
            else map.panTo([lat, lon], { animate: true });
          }
        }
      }
    }

    function renderStorySections(story) {
      const host = document.getElementById("side-nav");
      if (!host) return;
      host.innerHTML = "";
      const secs = (story && story.sections) ? story.sections.slice() : [];
      if (!secs.length) {
        ordered.forEach(function (m) {
          secs.push({ key: "layer:" + m.id, title: m.name, body: "", layer: m.id, focus: true, showOnly: false, zoom: null });
        });
      }

      // Single-section viewer with next/prev (better UX than long scrolling).
      let idx = 0;
      const viewer = el("div", { className: "story-viewer", role: "region", "aria-label": "Story" });
      const head = el("div", { className: "story-viewer-head" });
      const title = el("h2", { className: "story-viewer-title", text: "" });
      const meta = el("div", { className: "story-viewer-meta", text: "" });
      head.appendChild(title);
      head.appendChild(meta);

      const body = el("div", { className: "story-viewer-body", role: "document" });

      const foot = el("div", { className: "story-viewer-foot" });
      const prevBtn = el("button", { type: "button", className: "story-nav-btn", "aria-label": "Previous section", title: "Previous" });
      prevBtn.innerHTML = '<i class="bi bi-arrow-left" aria-hidden="true"></i><span>Previous</span>';
      const nextBtn = el("button", { type: "button", className: "story-nav-btn", "aria-label": "Next section", title: "Next" });
      nextBtn.innerHTML = '<span>Next</span><i class="bi bi-arrow-right" aria-hidden="true"></i>';
      foot.appendChild(prevBtn);
      foot.appendChild(nextBtn);

      viewer.appendChild(head);
      viewer.appendChild(body);
      viewer.appendChild(foot);
      host.appendChild(viewer);

      function setIdx(next) {
        if (!secs.length) return;
        idx = Math.max(0, Math.min(secs.length - 1, next));
        const s = secs[idx] || {};
        title.textContent = s.title || "";
        meta.textContent = (idx + 1) + " / " + secs.length;
        body.innerHTML = "";
        if (s.body) {
          body.appendChild(el("p", { className: "story-viewer-text", text: s.body }));
        }
        prevBtn.disabled = idx <= 0;
        nextBtn.disabled = idx >= secs.length - 1;
        body.scrollTop = 0;
        activateSection(s);
      }

      prevBtn.addEventListener("click", function () { setIdx(idx - 1); });
      nextBtn.addEventListener("click", function () { setIdx(idx + 1); });

      // Keyboard shortcuts when side panel focused.
      host.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowLeft") {
          ev.preventDefault();
          setIdx(idx - 1);
        } else if (ev.key === "ArrowRight") {
          ev.preventDefault();
          setIdx(idx + 1);
        }
      });
      host.tabIndex = 0;

      setIdx(0);
    }

    function loadStory() {
      if (!manifest.story) {
        try {
          document.body.classList.add("no-story");
        } catch (e) {}
        return;
      }
      tasks.begin();
      fetch(manifest.story)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(renderStorySections)
        .catch(function () { renderStorySections({ sections: [] }); })
        .finally(function () { tasks.end(); });
    }

    loadStory();

    if (layers.length) {
      setTimeout(scheduleFitAllLayerBounds, 400);
    }

    map.invalidateSize();
    window.addEventListener("resize", function () {
      map.invalidateSize();
    });

    // Mark core UI ready; loader will hide once tracked fetches complete.
    setTimeout(function () {
      tasks.markFinished();
    }, 450);
  }

  initThemeToggle();
  const bootLoader = createLoader();
  if (bootLoader) bootLoader.show();

  fetch("manifest.json")
    .then(function (r) {
      if (!r.ok) throw new Error("manifest");
      return r.json();
    })
    .then(main)
    .catch(function () {
      document.getElementById("story-title").textContent = "Story Map (preview)";
      var sub = document.querySelector(".sub");
      if (sub) {
        sub.textContent =
          "Open this folder with a local web server (e.g. python -m http.server) so manifest.json and assets can load.";
      }
      var lp = document.getElementById("map-legend-panel");
      if (lp) lp.style.display = "none";
      var lw = document.getElementById("legend-toggle-wrap");
      if (lw) lw.hidden = true;
      try {
        const l = createLoader();
        if (l) l.hide();
      } catch (e) {}
    });
})();
