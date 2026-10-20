/*
 * Create text layers in the active PSD from an Atlas map-marker table.
 * This is the reverse of psd_text_extract.jsx.
 *
 * Input: a .lua file in the format written by psd_text_extract.jsx or atlas_coords_dump.py
 *
 *     TransAllianceEast_Forever = {
 *         { "A", 20001, 13, 93 }, -- Orange
 *         { "1", 10001, 350, 74.5 }, -- Alliance
 *         ...
 *     },
 *
 * - The file next to the PSD with the same name is used; otherwise you are asked to pick one.
 * - The table named like the PSD is used; otherwise the first table in the file.
 * - 1st element : text of the layer
 * - 3rd / 4th   : X / Y of the text's top-left corner in px (bounds without effects),
 *                 the same convention psd_text_extract.jsx exports
 * - The marker tag, either the trailing comment or a 7th string field, sets the text colour.
 *
 * The layers are put in one group (GROUP_NAME). Running the script again replaces that group.
 * The whole import is a single history step, so one undo removes it.
 */

#target photoshop

app.bringToFront();

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
var GROUP_NAME = "Atlas markers (generated)";
var FONT = "ArialMT";          // PostScript name, e.g. "Arial-BoldMT", "FrizQuadrataTT"
var FONT_SIZE = 12;            // px
var DEFAULT_COLOR = [255, 255, 255];

// Same values as ATLAS_FONT_COLORS in Atlas/Data/Constants.lua (0-1 x 255)
var COLORS = {
  White    : [255, 255, 255],
  Yellow   : [255, 255, 0],
  Green    : [0, 255, 0],
  Red      : [255, 0, 0],
  Orange   : [255, 209, 0],
  Purple   : [186, 102, 255],
  Blue     : [102, 102, 255],
  Alliance : [123, 171, 224],
  Horde    : [218, 105, 85],
  Neutral  : [254, 229, 112]
};

// ---------------------------------------------------------------------------

function init() {
  if (app.documents.length === 0) {
    alert("Please open a file", "TextImport Error", true);
    return;
  }

  var doc = app.activeDocument;
  var baseName = getBaseName(doc);
  var file = findInputFile(doc, baseName);
  if (!file) {
    return;
  }

  var text = readFile(file);
  if (text === null) {
    alert("Unable to read:\n" + Folder.decode(file.fsName), "TextImport Error", true);
    return;
  }

  var table = pickTable(parseTables(text), baseName);
  if (!table || table.entries.length === 0) {
    alert("No entries found in:\n" + Folder.decode(file.fsName), "TextImport Error", true);
    return;
  }

  // Shared with main() through globals, because suspendHistory takes a string
  IMPORT_DOC = doc;
  IMPORT_ENTRIES = table.entries;
  doc.suspendHistory("Import Atlas markers", "main()");

  alert("Created " + table.entries.length + " text layers from table '" + table.name + "'\nin group '" + GROUP_NAME + "'.", "TextImport");
}

var IMPORT_DOC = null;
var IMPORT_ENTRIES = null;

function main() {
  var doc = IMPORT_DOC;
  var entries = IMPORT_ENTRIES;

  var previousRuler = app.preferences.rulerUnits;
  var previousType = app.preferences.typeUnits;
  app.preferences.rulerUnits = Units.PIXELS;
  app.preferences.typeUnits = TypeUnits.PIXELS;

  try {
    removeGroup(doc, GROUP_NAME);
    var group = doc.layerSets.add();
    group.name = GROUP_NAME;

    // layers are added on top, so go backwards to keep the file order in the Layers panel
    for (var i = entries.length - 1; i >= 0; i--) {
      addTextLayer(doc, group, entries[i]);
    }
  } finally {
    app.preferences.rulerUnits = previousRuler;
    app.preferences.typeUnits = previousType;
  }
}

function addTextLayer(doc, group, e) {
  var layer = group.artLayers.add();
  layer.kind = LayerKind.TEXT;
  layer.name = e.text + " (" + e.id + ")";

  var ti = layer.textItem;
  ti.kind = TextType.POINTTEXT;
  ti.contents = e.text;
  try {
    ti.font = FONT;
  } catch (err) {
    ;
  }
  ti.size = FONT_SIZE;
  ti.color = makeColor(COLORS[e.tag] || DEFAULT_COLOR);
  ti.position = [e.x, e.y + FONT_SIZE];

  // Move so the bounds without effects start exactly at (x, y), matching psd_text_extract.jsx
  doc.activeLayer = layer;
  var b = getBoundsNoEffects(layer);
  layer.translate(new UnitValue(e.x - b.left, "px"), new UnitValue(e.y - b.top, "px"));
}

function makeColor(rgb) {
  var c = new SolidColor();
  c.rgb.red = rgb[0];
  c.rgb.green = rgb[1];
  c.rgb.blue = rgb[2];
  return c;
}

function removeGroup(doc, name) {
  for (var i = doc.layerSets.length - 1; i >= 0; i--) {
    if (doc.layerSets[i].name == name) {
      doc.layerSets[i].remove();
    }
  }
}

// Same as in psd_text_extract.jsx
function getBoundsNoEffects(layer) {
  try {
    var ref = new ActionReference();
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    var bounds = executeActionGet(ref).getObjectValue(stringIDToTypeID("boundsNoEffects"));
    return {
      left : bounds.getUnitDoubleValue(charIDToTypeID("Left")),
      top : bounds.getUnitDoubleValue(charIDToTypeID("Top "))
    };
  } catch (e) {
    var b = layer.bounds;
    return { left : b[0].as("px"), top : b[1].as("px") };
  }
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function getBaseName(doc) {
  try {
    return decodeURI(doc.fullName.name).replace(/\.[^.\/\\]*$/, "");
  } catch (e) {
    return decodeURI(doc.name).replace(/\.[^.\/\\]*$/, "");
  }
}

function findInputFile(doc, baseName) {
  try {
    var f = new File(doc.fullName.path + "/" + baseName + ".lua");
    if (f.exists) {
      return f;
    }
  } catch (e) {
    ;
  }
  return File.openDialog("Select the .lua coords file for " + baseName, "Lua:*.lua");
}

function readFile(file) {
  file.encoding = "UTF-8";
  if (!file.open("r")) {
    return null;
  }
  var s = file.read();
  file.close();
  return s;
}

// Returns [{ name, entries: [{ text, id, x, y, tag }] }]
function parseTables(text) {
  var lines = text.split(/\r\n|\r|\n/);
  var tables = [];
  var current = null;
  var header = /^\s*([A-Za-z_][\w]*)\s*=\s*\{\s*$/;
  var row = /^\s*\{\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)(.*)$/;

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var h = header.exec(line);
    if (h) {
      current = { name : h[1], entries : [] };
      tables.push(current);
      continue;
    }

    var m = row.exec(line);
    if (!m) {
      continue;
    }
    if (!current) {
      current = { name : "", entries : [] };
      tables.push(current);
    }
    current.entries.push({
      text : unquote(m[1]),
      id : parseInt(m[2], 10),
      x : parseFloat(m[3]),
      y : parseFloat(m[4]),
      tag : findTag(m[5])
    });
  }
  return tables;
}

// Marker tag: 7th string field ( ..., nil, nil, "Blue" } ) or a trailing comment ( -- Blue )
function findTag(rest) {
  var field = /"(\w+)"\s*\}/.exec(rest);
  if (field) {
    return field[1];
  }
  var comment = /--\s*(\w+)/.exec(rest);
  if (comment) {
    var word = comment[1];
    // psd_text_extract style comments are lower case ("-- yellow")
    return word.charAt(0).toUpperCase() + word.substring(1);
  }
  return null;
}

function unquote(s) {
  if (/^["']/.test(s)) {
    return s.substring(1, s.length - 1).replace(/\\(.)/g, "$1");
  }
  return s;
}

function pickTable(tables, baseName) {
  for (var i = 0; i < tables.length; i++) {
    if (tables[i].name == baseName) {
      return tables[i];
    }
  }
  return tables.length > 0 ? tables[0] : null;
}

init();
