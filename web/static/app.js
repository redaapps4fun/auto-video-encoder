/* Auto Video Encoder - Headless Web UI */

let metadata = {};
let config = {};
let engineRunning = false;
let saveTimer = null;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function pathKey(path) {
  return path.join(".");
}

function getNested(obj, path, fallback = "") {
  let node = obj;
  for (const key of path) {
    if (node == null || typeof node !== "object" || !(key in node)) {
      return fallback;
    }
    node = node[key];
  }
  return node ?? fallback;
}

function setNested(obj, path, value) {
  let node = obj;
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    if (!(key in node) || typeof node[key] !== "object") {
      node[key] = {};
    }
    node = node[key];
  }
  node[path[path.length - 1]] = value;
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg || d).join(", ") : res.statusText;
    throw new Error(msg || "Request failed");
  }
  return data;
}

function addField(container, spec) {
  const row = document.createElement("div");
  row.className = "form-grid field-row";
  row.dataset.path = pathKey(spec.path);
  if (spec.showWhen) {
    row.dataset.showWhen = spec.showWhen;
  }

  const label = document.createElement("label");
  label.textContent = spec.label;
  label.htmlFor = `field-${pathKey(spec.path)}`;
  row.appendChild(label);

  let input;
  const id = `field-${pathKey(spec.path)}`;

  if (spec.type === "select") {
    input = document.createElement("select");
    input.id = id;
    const options = resolveOptions(spec.options);
    for (const opt of options) {
      const el = document.createElement("option");
      if (typeof opt === "object") {
        el.value = opt.value;
        el.textContent = opt.label;
      } else {
        el.value = opt;
        el.textContent = opt || "(empty)";
      }
      input.appendChild(el);
    }
  } else if (spec.type === "checkbox") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    label.remove();
    row.className = "field-row";
    row.appendChild(input);
    const text = document.createElement("span");
    text.textContent = spec.label;
    row.appendChild(text);
  } else if (spec.type === "range") {
    const wrap = document.createElement("div");
    wrap.className = "input-row";
    input = document.createElement("input");
    input.type = "range";
    input.id = id;
    input.min = spec.min ?? 0;
    input.max = spec.max ?? 100;
    input.step = spec.step ?? 1;
    const num = document.createElement("input");
    num.type = "number";
    num.min = input.min;
    num.max = input.max;
    num.step = input.step;
    num.style.width = "4.5rem";
    num.dataset.sync = id;
    input.addEventListener("input", () => { num.value = input.value; });
    num.addEventListener("input", () => { input.value = num.value; updateConfigFromForm(); });
    wrap.appendChild(input);
    wrap.appendChild(num);
    row.appendChild(wrap);
    container.appendChild(row);
    input.addEventListener("change", updateConfigFromForm);
    return row;
  } else {
    input = document.createElement("input");
    input.type = spec.type || "text";
    input.id = id;
    if (spec.min != null) input.min = spec.min;
    if (spec.max != null) input.max = spec.max;
    if (spec.step != null) input.step = spec.step;
    if (spec.placeholder) input.placeholder = spec.placeholder;
  }

  row.appendChild(input);
  container.appendChild(row);
  input.addEventListener("change", () => {
    updateConfigFromForm();
    updateConditionalVisibility();
  });
  return row;
}

function resolveOptions(key) {
  if (Array.isArray(key)) return key;
  if (key === "abr_presets") {
    return Object.entries(metadata.abr_presets).map(([name, p]) => ({
      value: name,
      label: `${name}  (${p.width}x${p.height} @ ${p.vb} kbps)`,
    })).concat([{ value: "Custom", label: "Custom" }]);
  }
  if (key === "crf_presets") {
    return Object.entries(metadata.crf_presets).map(([label, val]) => ({
      value: String(val),
      label,
    })).concat([{ value: "custom", label: "Custom" }]);
  }
  if (key === "crf_resolution") {
    return [{ value: "Source", label: "Source (no resize)" }]
      .concat(Object.entries(metadata.abr_presets).map(([name, p]) => ({
        value: name,
        label: `${name}  (${p.width}x${p.height})`,
      })))
      .concat([{ value: "Custom", label: "Custom" }]);
  }
  if (key === "simple_encoders") return metadata.simple_encoders;
  if (key === "crf_audio_encoders") {
    return [
      { value: "av_aac", label: "AAC (av_aac)" },
      { value: "mp3", label: "MP3" },
      { value: "opus", label: "Opus" },
      { value: "ac3", label: "AC3" },
      { value: "copy", label: "Copy (passthrough)" },
    ];
  }
  return metadata[key] || [];
}

function buildAbrFields() {
  const container = $("#abr-fields");
  container.innerHTML = "";
  addField(container, { label: "Resolution Preset", path: ["abr", "preset"], type: "select", options: "abr_presets" });
  addField(container, { label: "Custom Width", path: ["abr", "custom_width"], type: "number", min: 128, max: 15360, showWhen: "abr-custom" });
  addField(container, { label: "Custom Height", path: ["abr", "custom_height"], type: "number", min: 128, max: 8640, showWhen: "abr-custom" });
  addField(container, { label: "Custom Video Bitrate", path: ["abr", "custom_vb"], type: "number", min: 50, max: 100000, showWhen: "abr-custom" });
  addField(container, { label: "Encoder", path: ["abr", "encoder"], type: "select", options: "simple_encoders" });
  addField(container, { label: "Audio Bitrate (kbps)", path: ["abr", "audio_bitrate"], type: "number", min: 32, max: 640 });
}

function buildCrfFields() {
  const container = $("#crf-fields");
  container.innerHTML = "";
  addField(container, { label: "Quality (CRF)", path: ["crf", "quality_preset"], type: "select", options: "crf_presets" });
  addField(container, { label: "Custom CRF Value", path: ["crf", "quality"], type: "range", min: 0, max: 51, step: 1, showWhen: "crf-custom" });
  addField(container, { label: "Encoder", path: ["crf", "encoder"], type: "select", options: "simple_encoders" });
  addField(container, { label: "Output Resolution", path: ["crf", "resolution_preset"], type: "select", options: "crf_resolution" });
  addField(container, { label: "Custom Width", path: ["crf", "custom_width"], type: "number", min: 128, max: 15360, showWhen: "crf-res-custom" });
  addField(container, { label: "Custom Height", path: ["crf", "custom_height"], type: "number", min: 128, max: 8640, showWhen: "crf-res-custom" });
  addField(container, { label: "Audio Encoder", path: ["crf", "audio_encoder"], type: "select", options: "crf_audio_encoders" });
  addField(container, { label: "Audio Bitrate (kbps)", path: ["crf", "audio_bitrate"], type: "number", min: 32, max: 640 });
}

const ADVANCED_SCHEMA = {
  Video: [
    { label: "Encoder", path: ["advanced", "video", "encoder"], type: "select", options: "all_encoders" },
    { label: "Rate Control", path: ["advanced", "video", "rate_control"], type: "select", options: ["quality", "bitrate"] },
    { label: "Quality (CRF)", path: ["advanced", "video", "quality"], type: "number", min: 0, max: 51, step: 0.1 },
    { label: "Video Bitrate (kbps)", path: ["advanced", "video", "vb"], type: "number", min: 50, max: 100000 },
    { label: "Encoder Preset", path: ["advanced", "video", "encoder_preset"], type: "text", placeholder: "e.g. medium, slow, fast" },
    { label: "Encoder Tune", path: ["advanced", "video", "encoder_tune"], type: "text", placeholder: "e.g. film, animation, grain" },
    { label: "Encoder Profile", path: ["advanced", "video", "encoder_profile"], type: "text", placeholder: "e.g. main, high" },
    { label: "Encoder Level", path: ["advanced", "video", "encoder_level"], type: "text", placeholder: "e.g. 4.0, 5.1" },
    { label: "Multi-pass", path: ["advanced", "video", "multi_pass"], type: "checkbox" },
    { label: "Turbo first pass", path: ["advanced", "video", "turbo"], type: "checkbox" },
    { label: "Framerate", path: ["advanced", "video", "framerate"], type: "select", options: "framerate_select" },
    { label: "Framerate Mode", path: ["advanced", "video", "framerate_mode"], type: "select", options: ["vfr", "cfr", "pfr"] },
    { label: "Extra Encoder Opts", path: ["advanced", "video", "encopts"], type: "text", placeholder: "key=value:key=value" },
    { label: "HW Decoding", path: ["advanced", "video", "hw_decoding"], type: "select", options: "hw_decoding_options" },
    { label: "HDR Metadata", path: ["advanced", "video", "hdr_metadata"], type: "select", options: "hdr_metadata_options" },
  ],
  Audio: [
    { label: "Audio Encoder", path: ["advanced", "audio", "encoder"], type: "select", options: "audio_encoders" },
    { label: "Audio Bitrate (kbps)", path: ["advanced", "audio", "bitrate"], type: "number", min: 16, max: 1536 },
    { label: "Audio Quality", path: ["advanced", "audio", "quality"], type: "number", min: -1, max: 10, step: 0.1 },
    { label: "Mixdown", path: ["advanced", "audio", "mixdown"], type: "select", options: "mixdowns" },
    { label: "Sample Rate", path: ["advanced", "audio", "samplerate"], type: "select", options: "sample_rate_select" },
    { label: "DRC", path: ["advanced", "audio", "drc"], type: "number", min: 0, max: 4, step: 0.1 },
    { label: "Gain (dB)", path: ["advanced", "audio", "gain"], type: "number", min: -20, max: 20, step: 0.1 },
    { label: "Audio Tracks", path: ["advanced", "audio", "tracks"], type: "text", placeholder: "e.g. 1 or 1,2,3" },
    { label: "Language List", path: ["advanced", "audio", "lang_list"], type: "text", placeholder: "e.g. eng,jpn" },
    { label: "Preserve track names", path: ["advanced", "audio", "keep_names"], type: "checkbox" },
  ],
  Picture: [
    { label: "Width", path: ["advanced", "picture", "width"], type: "number", min: 0, max: 15360 },
    { label: "Height", path: ["advanced", "picture", "height"], type: "number", min: 0, max: 8640 },
    { label: "Max Width", path: ["advanced", "picture", "max_width"], type: "number", min: 0, max: 15360 },
    { label: "Max Height", path: ["advanced", "picture", "max_height"], type: "number", min: 0, max: 8640 },
    { label: "Anamorphic", path: ["advanced", "picture", "anamorphic"], type: "select", options: "anamorphic_modes" },
    { label: "Modulus", path: ["advanced", "picture", "modulus"], type: "select", options: [2, 4, 8, 16] },
    { label: "Crop Mode", path: ["advanced", "picture", "crop_mode"], type: "select", options: "crop_modes" },
    { label: "Custom Crop", path: ["advanced", "picture", "crop"], type: "text", placeholder: "top:bottom:left:right" },
    { label: "Color Range", path: ["advanced", "picture", "color_range"], type: "select", options: "color_ranges" },
    { label: "Color Matrix", path: ["advanced", "picture", "color_matrix"], type: "select", options: "color_matrices" },
    { label: "Rotation", path: ["advanced", "picture", "rotate"], type: "select", options: [0, 90, 180, 270] },
    { label: "Horizontal flip", path: ["advanced", "picture", "hflip"], type: "checkbox" },
  ],
  Filters: [
    { label: "Deinterlace", path: ["advanced", "filters", "deinterlace"], type: "select", options: "deinterlace_types" },
    { label: "Deinterlace Preset", path: ["advanced", "filters", "deinterlace_preset"], type: "text" },
    { label: "Comb Detect", path: ["advanced", "filters", "comb_detect"], type: "select", options: "comb_detect_modes" },
    { label: "Detelecine", path: ["advanced", "filters", "detelecine"], type: "checkbox" },
    { label: "Denoise", path: ["advanced", "filters", "denoise"], type: "select", options: "denoise_types" },
    { label: "Denoise Strength", path: ["advanced", "filters", "denoise_strength"], type: "select", options: "denoise_strengths" },
    { label: "Denoise Tune", path: ["advanced", "filters", "denoise_tune"], type: "select", options: "nlmeans_tunes" },
    { label: "Chroma Smooth", path: ["advanced", "filters", "chroma_smooth"], type: "select", options: "chroma_smooth_strengths" },
    { label: "Chroma Smooth Tune", path: ["advanced", "filters", "chroma_smooth_tune"], type: "text" },
    { label: "Sharpen", path: ["advanced", "filters", "sharpen"], type: "select", options: "sharpen_types" },
    { label: "Sharpen Strength", path: ["advanced", "filters", "sharpen_strength"], type: "select", options: "sharpen_strengths" },
    { label: "Sharpen Tune", path: ["advanced", "filters", "sharpen_tune"], type: "text" },
    { label: "Deblock", path: ["advanced", "filters", "deblock"], type: "select", options: "deblock_strengths" },
    { label: "Deblock Tune", path: ["advanced", "filters", "deblock_tune"], type: "select", options: "deblock_tunes" },
    { label: "Grayscale", path: ["advanced", "filters", "grayscale"], type: "checkbox" },
    { label: "Colorspace", path: ["advanced", "filters", "colorspace"], type: "select", options: "colorspace_presets" },
  ],
  Subtitles: [
    { label: "Subtitle Tracks", path: ["advanced", "subtitles", "tracks"], type: "text" },
    { label: "Language List", path: ["advanced", "subtitles", "lang_list"], type: "text" },
    { label: "All Subtitles", path: ["advanced", "subtitles", "all"], type: "checkbox" },
    { label: "First Only", path: ["advanced", "subtitles", "first_only"], type: "checkbox" },
    { label: "Burn-in", path: ["advanced", "subtitles", "burn"], type: "text" },
    { label: "Default Track", path: ["advanced", "subtitles", "default"], type: "number", min: -1, max: 99 },
    { label: "Forced", path: ["advanced", "subtitles", "forced"], type: "text" },
    { label: "SRT File", path: ["advanced", "subtitles", "srt_file"], type: "text" },
    { label: "SRT Offset", path: ["advanced", "subtitles", "srt_offset"], type: "text" },
    { label: "SRT Language", path: ["advanced", "subtitles", "srt_lang"], type: "text" },
    { label: "SRT Codeset", path: ["advanced", "subtitles", "srt_codeset"], type: "text" },
    { label: "SRT Burn", path: ["advanced", "subtitles", "srt_burn"], type: "checkbox" },
    { label: "SRT Default", path: ["advanced", "subtitles", "srt_default"], type: "checkbox" },
    { label: "SSA File", path: ["advanced", "subtitles", "ssa_file"], type: "text" },
    { label: "SSA Offset", path: ["advanced", "subtitles", "ssa_offset"], type: "text" },
    { label: "SSA Language", path: ["advanced", "subtitles", "ssa_lang"], type: "text" },
    { label: "SSA Burn", path: ["advanced", "subtitles", "ssa_burn"], type: "checkbox" },
    { label: "SSA Default", path: ["advanced", "subtitles", "ssa_default"], type: "checkbox" },
    { label: "Keep Names", path: ["advanced", "subtitles", "keep_names"], type: "checkbox" },
  ],
  Container: [
    { label: "Container Format", path: ["advanced", "container", "format"], type: "select", options: "container_formats" },
    { label: "Chapters", path: ["advanced", "container", "chapters"], type: "checkbox" },
    { label: "Optimize (MP4)", path: ["advanced", "container", "optimize"], type: "checkbox" },
    { label: "iPod Atom (MP4)", path: ["advanced", "container", "ipod_atom"], type: "checkbox" },
    { label: "Align A/V", path: ["advanced", "container", "align_av"], type: "checkbox" },
    { label: "Keep Metadata", path: ["advanced", "container", "keep_metadata"], type: "checkbox" },
    { label: "Inline Params", path: ["advanced", "container", "inline_params"], type: "checkbox" },
  ],
};

function buildAdvancedFields() {
  metadata.framerate_select = ["", ...metadata.framerates.filter((f) => f !== "Same as source")];
  metadata.sample_rate_select = metadata.sample_rates.map((r) => (r === "Auto" ? "auto" : r));

  const tabsEl = $("#advanced-tabs");
  const panelsEl = $("#advanced-panels");
  tabsEl.innerHTML = "";
  panelsEl.innerHTML = "";

  Object.entries(ADVANCED_SCHEMA).forEach(([name, fields], idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `tab-btn${idx === 0 ? " active" : ""}`;
    btn.textContent = name;
    btn.dataset.tab = name;
    btn.addEventListener("click", () => {
      $$(".tab-btn").forEach((b) => b.classList.remove("active"));
      $$(".adv-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#adv-panel-${name}`).classList.add("active");
    });
    tabsEl.appendChild(btn);

    const panel = document.createElement("div");
    panel.id = `adv-panel-${name}`;
    panel.className = `adv-panel${idx === 0 ? " active" : ""}`;
    const grid = document.createElement("div");
    grid.className = "form-grid";
    panel.appendChild(grid);
    fields.forEach((spec) => addField(grid, spec));
    panelsEl.appendChild(panel);
  });
}

function fieldInput(path) {
  return $(`#field-${pathKey(path)}`);
}

function loadConfigToForm() {
  $$("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    let val = config[key];
    if (key === "video_extensions" && Array.isArray(val)) {
      val = val.join(" ");
    }
    if (el.type === "checkbox") {
      el.checked = !!val;
    } else {
      el.value = val ?? "";
    }
  });

  setField(["abr", "preset"], config.abr?.preset ?? "720p");
  setField(["abr", "custom_width"], config.abr?.custom_width ?? 1280);
  setField(["abr", "custom_height"], config.abr?.custom_height ?? 720);
  setField(["abr", "custom_vb"], config.abr?.custom_vb ?? 1000);
  setField(["abr", "encoder"], config.abr?.encoder ?? "nvenc_h265");
  setField(["abr", "audio_bitrate"], config.abr?.audio_bitrate ?? 128);

  const crfQuality = config.crf?.quality ?? 22;
  let crfPreset = "custom";
  for (const [label, val] of Object.entries(metadata.crf_presets || {})) {
    if (val === crfQuality) {
      crfPreset = String(val);
      break;
    }
  }
  setField(["crf", "quality_preset"], crfPreset);
  setField(["crf", "quality"], crfQuality);
  setField(["crf", "encoder"], config.crf?.encoder ?? "nvenc_h265");
  setField(["crf", "resolution_preset"], config.crf?.resolution_preset ?? "720p");
  setField(["crf", "custom_width"], config.crf?.custom_width ?? 1280);
  setField(["crf", "custom_height"], config.crf?.custom_height ?? 720);
  setField(["crf", "audio_encoder"], config.crf?.audio_encoder ?? "av_aac");
  setField(["crf", "audio_bitrate"], config.crf?.audio_bitrate ?? 128);

  for (const fields of Object.values(ADVANCED_SCHEMA)) {
    for (const spec of fields) {
      let val = getNested(config, spec.path, spec.type === "checkbox" ? false : "");
      if (spec.path.join(".") === "advanced.video.framerate") {
        val = val || "";
      }
      if (spec.path.join(".") === "advanced.video.hw_decoding") {
        val = val || "off";
      }
      if (spec.path.join(".") === "advanced.video.hdr_metadata") {
        val = val || "off";
      }
      if (spec.path.join(".") === "advanced.audio.quality" && (val === null || val === undefined)) {
        val = -1;
      }
      if (spec.path.join(".") === "advanced.subtitles.default" && (val === null || val === undefined)) {
        val = -1;
      }
      setField(spec.path, val);
    }
  }

  $("#encoding_mode").value = config.encoding_mode || "abr";
  updateModePanels();
  updateConditionalVisibility();
  updateAdvancedRateControl();
}

function setField(path, value) {
  const el = fieldInput(path);
  if (!el) return;
  if (el.type === "checkbox") {
    el.checked = !!value;
  } else {
    el.value = value ?? "";
  }
  const sync = document.querySelector(`input[data-sync="${el.id}"]`);
  if (sync) sync.value = el.value;
}

function readConfigFromForm() {
  const out = JSON.parse(JSON.stringify(config));

  $$("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (el.type === "checkbox") {
      out[key] = el.checked;
    } else if (key === "video_extensions") {
      out[key] = el.value.trim().split(/\s+/).filter(Boolean).map((e) => e.toLowerCase());
    } else {
      out[key] = el.value;
    }
  });

  out.encoding_mode = $("#encoding_mode").value;
  out.abr = {
    preset: getField(["abr", "preset"]),
    encoder: getField(["abr", "encoder"]),
    custom_width: numField(["abr", "custom_width"], 1280),
    custom_height: numField(["abr", "custom_height"], 720),
    custom_vb: numField(["abr", "custom_vb"], 1000),
    audio_bitrate: numField(["abr", "audio_bitrate"], 128),
  };

  const crfPreset = getField(["crf", "quality_preset"]);
  out.crf = {
    quality: crfPreset === "custom" ? numField(["crf", "quality"], 22) : Number(crfPreset),
    encoder: getField(["crf", "encoder"]),
    resolution_preset: getField(["crf", "resolution_preset"]),
    custom_width: numField(["crf", "custom_width"], 1280),
    custom_height: numField(["crf", "custom_height"], 720),
    audio_encoder: getField(["crf", "audio_encoder"]),
    audio_bitrate: numField(["crf", "audio_bitrate"], 128),
  };

  out.advanced = out.advanced || {};
  for (const fields of Object.values(ADVANCED_SCHEMA)) {
    for (const spec of fields) {
      let val;
      const el = fieldInput(spec.path);
      if (!el) continue;
      if (spec.type === "checkbox") {
        val = el.checked;
      } else if (spec.type === "number" || spec.type === "range") {
        val = el.value === "" ? null : Number(el.value);
      } else {
        val = el.value;
      }
      if (spec.path.join(".") === "advanced.video.framerate" && val === "") val = "";
      if (spec.path.join(".") === "advanced.video.hw_decoding" && val === "off") val = "";
      if (spec.path.join(".") === "advanced.video.hdr_metadata" && val === "off") val = "";
      if (spec.path.join(".") === "advanced.audio.quality" && (val === -1 || val === null)) val = null;
      if (spec.path.join(".") === "advanced.subtitles.default" && (val === -1 || val === null)) val = null;
      if (spec.path.join(".") === "advanced.picture.max_width" && !val) val = null;
      if (spec.path.join(".") === "advanced.picture.max_height" && !val) val = null;
      if (spec.path.join(".") === "advanced.picture.rotate") val = Number(val);
      if (spec.path.join(".") === "advanced.picture.modulus") val = Number(val);
      setNested(out, spec.path, val);
    }
  }

  return out;
}

function getField(path) {
  const el = fieldInput(path);
  return el ? el.value : "";
}

function numField(path, fallback) {
  const el = fieldInput(path);
  const n = Number(el?.value);
  return Number.isFinite(n) ? n : fallback;
}

function updateConfigFromForm() {
  config = readConfigFromForm();
}

function updateModePanels() {
  const mode = $("#encoding_mode").value;
  $("#panel-abr").classList.toggle("hidden", mode !== "abr");
  $("#panel-crf").classList.toggle("hidden", mode !== "crf");
  $("#panel-advanced").classList.toggle("hidden", mode !== "advanced");
}

function updateConditionalVisibility() {
  const abrPreset = getField(["abr", "preset"]);
  $$('[data-show-when="abr-custom"]').forEach((row) => {
    row.classList.toggle("hidden", abrPreset !== "Custom");
  });

  const crfPreset = getField(["crf", "quality_preset"]);
  $$('[data-show-when="crf-custom"]').forEach((row) => {
    row.classList.toggle("hidden", crfPreset !== "custom");
  });

  const crfRes = getField(["crf", "resolution_preset"]);
  $$('[data-show-when="crf-res-custom"]').forEach((row) => {
    row.classList.toggle("hidden", crfRes !== "Custom");
  });
}

function updateAdvancedRateControl() {
  const rc = getField(["advanced", "video", "rate_control"]);
  const q = fieldInput(["advanced", "video", "quality"]);
  const vb = fieldInput(["advanced", "video", "vb"]);
  if (q) q.disabled = rc !== "quality";
  if (vb) vb.disabled = rc === "quality";
}

function setEngineRunning(running) {
  engineRunning = running;
  $("#btn-start").disabled = running;
  $("#btn-stop").disabled = !running;
  $("#btn-save").disabled = running;
}

function appendLog(line) {
  const view = $("#log-view");
  view.textContent += line + "\n";
  view.scrollTop = view.scrollHeight;
}

function updateStats(stats) {
  $("#stats-line").textContent =
    `Processed: ${stats.total}   Encoded: ${stats.encoded}   Copied: ${stats.copied}   Skipped: ${stats.skipped}   Queued: ${stats.queued}`;
}

function updateToolsStatus(status) {
  const el = $("#tools-status");
  const hb = status.handbrake_ok ? `<span class="ok">HandBrakeCLI OK</span>` : `<span class="bad">HandBrakeCLI missing</span>`;
  const ff = status.ffprobe_ok ? `<span class="ok">ffprobe OK</span>` : `<span class="bad">ffprobe missing</span>`;
  el.innerHTML = `${hb} &nbsp;|&nbsp; ${ff}`;
  $("#btn-dl-hb").disabled = !status.handbrake_downloadable;
}

async function refreshToolsStatus() {
  const status = await api("GET", "/api/tools/status");
  updateToolsStatus(status);
  return status;
}

async function saveConfig() {
  const statusEl = $("#save-status");
  statusEl.className = "save-status";
  statusEl.textContent = "Saving...";
  try {
    updateConfigFromForm();
    await api("PUT", "/api/config", config);
    statusEl.textContent = "Config saved.";
    statusEl.classList.add("ok");
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.classList.add("err");
  }
}

function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/events`);

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") {
      $("#log-view").textContent = (msg.logs || []).join("\n") + (msg.logs?.length ? "\n" : "");
      updateStats(msg.stats || {});
      $("#status-line").textContent = `Status: ${msg.status || "Ready"}`;
      $("#progress-line").value = msg.progress || "";
      setEngineRunning(!!msg.running);
    } else if (msg.type === "log") {
      appendLog(msg.message);
      $("#status-line").textContent = `Status: ${msg.message.replace(/^\[[^\]]+\]\s*/, "")}`;
    } else if (msg.type === "stats") {
      updateStats(msg.stats);
    } else if (msg.type === "progress") {
      $("#progress-line").value = msg.progress || "";
    } else if (msg.type === "state") {
      /* state updates handled via engine event */
    } else if (msg.type === "engine") {
      setEngineRunning(!!msg.running);
    } else if (msg.type === "error") {
      appendLog(`ERROR: ${msg.message}`);
    } else if (msg.type === "download") {
      if (msg.status === "complete") {
        refreshToolsStatus().then((s) => {
          $("#handbrake_cli").value = s.handbrake_path || "";
          $("#ffprobe").value = s.ffprobe_path || "";
        });
      }
    }
  };

  ws.onclose = () => {
    setTimeout(connectWebSocket, 2000);
  };
}

async function init() {
  metadata = await api("GET", "/api/metadata");
  config = await api("GET", "/api/config");

  buildAbrFields();
  buildCrfFields();
  buildAdvancedFields();
  loadConfigToForm();

  await refreshToolsStatus();

  $("#encoding_mode").addEventListener("change", () => {
    updateModePanels();
    updateConfigFromForm();
  });

  fieldInput(["advanced", "video", "rate_control"])?.addEventListener("change", () => {
    updateAdvancedRateControl();
    updateConfigFromForm();
  });

  $("#btn-save").addEventListener("click", saveConfig);
  $("#btn-clear-log").addEventListener("click", () => { $("#log-view").textContent = ""; });

  $("#btn-start").addEventListener("click", async () => {
    try {
      await saveConfig();
      await api("POST", "/api/engine/start");
      setEngineRunning(true);
    } catch (err) {
      $("#save-status").textContent = err.message;
      $("#save-status").className = "save-status err";
    }
  });

  $("#btn-stop").addEventListener("click", async () => {
    try {
      await api("POST", "/api/engine/stop");
    } catch (err) {
      $("#save-status").textContent = err.message;
      $("#save-status").className = "save-status err";
    }
  });

  $("#btn-dl-hb").addEventListener("click", async () => {
    try {
      await api("POST", "/api/tools/download", { tool: "handbrake" });
    } catch (err) {
      appendLog(`Download error: ${err.message}`);
    }
  });

  $("#btn-dl-ff").addEventListener("click", async () => {
    try {
      await api("POST", "/api/tools/download", { tool: "ffprobe" });
    } catch (err) {
      appendLog(`Download error: ${err.message}`);
    }
  });

  $$("[data-key]").forEach((el) => {
    el.addEventListener("change", updateConfigFromForm);
  });

  connectWebSocket();
}

init().catch((err) => {
  $("#save-status").textContent = `Failed to load: ${err.message}`;
  $("#save-status").className = "save-status err";
});
