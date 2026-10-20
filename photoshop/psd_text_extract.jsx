/*
 * Export the visible text layers of the active PSD as an Atlas map-marker table.
 *
 * Output is saved next to the PSD, using the same name with a .lua extension:
 *
 *     BlackrockMountainEnt = {
 *         { "A", 10001, 271, 182 },
 *         ...
 *     },
 *
 * Table name  : PSD file name without extension
 * 1st element : text of the layer
 * 2nd element : sequence number, starting from 10001, assigned after sorting
 * 3rd / 4th   : X / Y of the text's top-left corner in px, from the document's top-left
 * comment     : name of the text color (e.g. -- blue), to tell apart layers with the same text
 *
 * Based on https://github.com/pivanov/photoshop-scripts (Export All Text Layers)
 */

//@target photoshop

app.bringToFront();

var START_ID = 10001;
var INDENT = "    ";

var data = [];

function init() {
  if (app.documents.length === 0) {
    alert("Please open a file", "TextExport Error", true);
    return;
  }

  var active = app.activeDocument;
  var source = getSourceFile(active);
  var batch = false;

  // Batch needs a saved document, since the folder comes from its path
  if (source) {
    batch = confirm(
      "Process all PSD files in this folder?\n" + Folder.decode(source.parent.fsName) +
      "\n\nYes: every .psd in the folder\nNo: only the active document (" + decodeURI(source.name) + ")",
      true, "TextExport");
  }

  if (!batch) {
    var saved = exportDocument(active);
    if (saved) {
      alert("Saved " + saved.count + " entries to:\n" + Folder.decode(saved.file.fsName), "TextExport");
    }
    return;
  }

  var files = source.parent.getFiles("*.psd");
  var report = [];
  var previousDialogs = app.displayDialogs;
  app.displayDialogs = DialogModes.NO;

  for (var i = 0; i < files.length; i++) {
    if (!(files[i] instanceof File)) {
      continue;
    }

    var wasOpen = findOpenDocument(files[i]);
    var doc = wasOpen;

    try {
      if (!doc) {
        doc = app.open(files[i]);
      }
      var result = exportDocument(doc, true);
      report.push(decodeURI(files[i].name) + ": " + (result ? result.count + " entries" : "failed"));
    } catch (e) {
      report.push(decodeURI(files[i].name) + ": error - " + e);
    }

    if (doc && !wasOpen) {
      doc.close(SaveOptions.DONOTSAVECHANGES);
    }
  }

  app.displayDialogs = previousDialogs;
  app.activeDocument = active;
  alert(report.join("\n"), "TextExport - batch done");
}

function findOpenDocument(file) {
  for (var i = 0; i < app.documents.length; i++) {
    try {
      if (app.documents[i].fullName.fsName == file.fsName) {
        return app.documents[i];
      }
    } catch (e) {
      ;
    }
  }
  return null;
}

// Collects, sorts and saves one document. Returns { file, count }, or null if nothing was saved.
function exportDocument(doc, silent) {
  data = [];
  app.activeDocument = doc;
  collectText(doc);
  applyCanvasScale(doc);
  data.sort(compareEntries);
  return saveResults(doc, silent);
}

// The maps are designed at 512x512; a 1024x1024 canvas is exported at half size.
function applyCanvasScale(doc) {
  var w = Math.round(doc.width.as("px"));
  var h = Math.round(doc.height.as("px"));

  if (w != 1024 || h != 1024) {
    return;
  }

  for (var i = 0; i < data.length; i++) {
    data[i].x = Math.round(data[i].x / 2 * 10) / 10;
    data[i].y = Math.round(data[i].y / 2 * 10) / 10;
  }
}

function collectText(el) {
  var layers = el.layers;

  for (var i = 0; i < layers.length; i++) {
    var layer = layers[i];

    if (!layer.visible) {
      continue;
    }

    if (layer.typename == "LayerSet") {
      collectText(layer);
    } else if (layer.kind == LayerKind.TEXT && layer.textItem.contents) {
      var text = trim(String(layer.textItem.contents));
      if (text === "") {
        continue;
      }

      try {
        var b = getBoundsNoEffects(layer);
        data.push({
          text : text,
          x : Math.round(b.left),
          y : Math.round(b.top),
          color : getColorName(layer)
        });
      } catch (e) {
        ;
      }
    }
  }
}

// Bounds without layer effects (stroke, glow, shadow), matching the X/Y shown in the
// Properties panel. Falls back to layer.bounds if the descriptor is unavailable.
function getBoundsNoEffects(layer) {
  try {
    var previous = app.activeDocument.activeLayer;
    app.activeDocument.activeLayer = layer;

    var ref = new ActionReference();
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    var bounds = executeActionGet(ref).getObjectValue(stringIDToTypeID("boundsNoEffects"));

    app.activeDocument.activeLayer = previous;

    return {
      left : bounds.getUnitDoubleValue(charIDToTypeID("Left")),
      top : bounds.getUnitDoubleValue(charIDToTypeID("Top "))
    };
  } catch (e) {
    var b = layer.bounds;
    return { left : b[0].as("px"), top : b[1].as("px") };
  }
}

// Name of the text color, e.g. "blue". Returns "" if the color can't be read (e.g. mixed styles).
function getColorName(layer) {
  try {
    var c = layer.textItem.color.rgb;
    return nameFromRgb(c.red, c.green, c.blue);
  } catch (e) {
    return "";
  }
}

function nameFromRgb(r, g, b) {
  var max = Math.max(r, g, b);
  var min = Math.min(r, g, b);
  var l = (max + min) / 510;
  var d = max - min;
  var s = d === 0 ? 0 : d / (255 - Math.abs(max + min - 255));

  if (l < 0.12) {
    return "black";
  }
  if (l > 0.92 && s < 0.5) {
    return "white";
  }
  if (s < 0.15) {
    return "gray";
  }

  var h;
  if (max == r) {
    h = ((g - b) / d) % 6;
  } else if (max == g) {
    h = (b - r) / d + 2;
  } else {
    h = (r - g) / d + 4;
  }
  h = (h * 60 + 360) % 360;

  if (h >= 15 && h < 45 && l < 0.4) {
    return "brown";
  }
  if (h < 15 || h >= 345) {
    return "red";
  }
  if (h < 45) {
    return "orange";
  }
  if (h < 70) {
    return "yellow";
  }
  if (h < 165) {
    return "green";
  }
  if (h < 195) {
    return "cyan";
  }
  if (h < 255) {
    return "blue";
  }
  if (h < 290) {
    return "purple";
  }
  if (h < 345) {
    return "pink";
  }
  return "red";
}

function trim(s) {
  return s.replace(/^\s+|\s+$/g, "");
}

// Sort order: letters (A, B, ...), then numbers (1, 2, 1', 2'), then anything else.
function sortKey(text) {
  var m = /^(\d+)(.*)$/.exec(text);
  if (m) {
    return { group : 1, num : parseInt(m[1], 10), rest : m[2] };
  }
  if (/^[A-Za-z]/.test(text)) {
    return { group : 0, num : 0, rest : text.toLowerCase() };
  }
  return { group : 2, num : 0, rest : text };
}

function compareEntries(a, b) {
  var ka = sortKey(a.text);
  var kb = sortKey(b.text);

  if (ka.group != kb.group) {
    return ka.group - kb.group;
  }
  if (ka.num != kb.num) {
    return ka.num - kb.num;
  }
  if (ka.rest.length != kb.rest.length) {
    return ka.rest.length - kb.rest.length;
  }
  return ka.rest < kb.rest ? -1 : (ka.rest > kb.rest ? 1 : 0);
}

// Photoshop auto-converts quotes/primes to typographic characters; map them back to ASCII.
function normalizeText(s) {
  return s
    .replace(/[\u2018\u2019\u201A\u201B\u2032\u00B4\u0060]/g, "'")
    .replace(/[\u201C\u201D\u201E\u201F\u2033]/g, '"')
    .replace(/[\u2010-\u2015]/g, "-");
}

function luaString(s) {
  return '"' + normalizeText(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/[\r\n]+/g, " ") + '"';
}

// Returns the PSD file, or null when the document has never been saved.
function getSourceFile(doc) {
  try {
    return doc.fullName;
  } catch (e) {
    return null;
  }
}

function saveResults(doc, silent) {
  var source = getSourceFile(doc);
  var outputFile;
  var tableName;

  if (source) {
    var baseName = decodeURI(source.name).replace(/\.[^.\/\\]*$/, "");
    tableName = baseName;
    outputFile = new File(source.path + "/" + baseName + ".lua");
  } else {
    // Unsaved document: ask where to put the result
    outputFile = File.saveDialog("Please select a file to save the results", "Lua:*.lua");
    if (outputFile == null) {
      return null;
    }
    tableName = decodeURI(outputFile.name).replace(/\.[^.\/\\]*$/, "");
  }

  outputFile.encoding = "UTF-8";
  outputFile.linefeed = ($.os.search(/windows/i) != -1 ? "windows" : "macintosh");

  if (!outputFile.open("w", "TEXT", "????")) {
    if (!silent) {
      alert("Unable to write:\n" + Folder.decode(outputFile.fsName), "TextExport Error", true);
    }
    return null;
  }

  outputFile.writeln(INDENT + tableName + " = {");
  for (var i = 0; i < data.length; i++) {
    var d = data[i];
    outputFile.writeln(INDENT + INDENT + "{ " + luaString(d.text) + ", " + (START_ID + i) + ", " + d.x + ", " + d.y + " }," + (d.color ? " -- " + d.color : ""));
  }
  outputFile.writeln(INDENT + "},");

  outputFile.close();

  return { file : outputFile, count : data.length };
}

init();
