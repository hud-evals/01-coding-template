#!/usr/bin/env node
/**
 * TypeScript scanner helper.
 *
 * This stays dependency-free on purpose: we avoid requiring the project's
 * TypeScript compiler at scan time, but still try to capture the public API
 * surface the prompt renderer needs.
 */

import { readFileSync, existsSync } from "node:fs";
import { resolve, basename, extname, dirname } from "node:path";
import { parseArgs } from "node:util";

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

const { values } = parseArgs({
  options: {
    sources: { type: "string", multiple: true, default: [] },
    tests: { type: "string", multiple: true, default: [] },
    tsconfig: { type: "string", default: "" },
    root: { type: "string", default: process.cwd() },
  },
  strict: false,
  allowPositionals: true,
});

const sourceFiles = (values.sources || []).map((p) => resolve(p));
const testFiles = (values.tests || []).map((p) => resolve(p));
const root = resolve(values.root || process.cwd());

const LOOKAHEAD_LINES = 40;
const CLASS_MEMBER_MODIFIERS = new Set([
  "public",
  "private",
  "protected",
  "readonly",
  "static",
  "abstract",
  "override",
  "declare",
  "async",
]);
const LOCAL_IMPORT_EXTENSIONS = [".ts", ".mts", ".js", ".mjs"];

// ---------------------------------------------------------------------------
// Lightweight TS-free parsing helpers
// ---------------------------------------------------------------------------

function skipWhitespace(text, start = 0) {
  let idx = start;
  while (idx < text.length && /\s/.test(text[idx])) idx += 1;
  return idx;
}

function readIdentifier(text, start = 0) {
  const idx = skipWhitespace(text, start);
  const match = text.slice(idx).match(/^[A-Za-z_$][A-Za-z0-9_$]*/);
  if (!match) return null;
  return {
    value: match[0],
    end: idx + match[0].length,
  };
}

function readBalanced(text, start, openChar, closeChar) {
  if (text[start] !== openChar) return null;
  let depth = 0;
  let quote = null;
  let escaped = false;

  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      continue;
    }

    if (ch === openChar) {
      depth += 1;
      continue;
    }
    if (ch === closeChar) {
      depth -= 1;
      if (depth === 0) {
        return {
          value: text.slice(start + 1, i),
          end: i + 1,
        };
      }
    }
  }

  return null;
}

function readUntilTopLevel(text, start, shouldStop) {
  let parenDepth = 0;
  let bracketDepth = 0;
  let braceDepth = 0;
  let angleDepth = 0;
  let quote = null;
  let escaped = false;

  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1] || "";

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      const lineBreak = text.indexOf("\n", i);
      if (lineBreak === -1) {
        break;
      }
      i = lineBreak;
      continue;
    }

    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      continue;
    }

    const isTopLevel = (
      parenDepth === 0 &&
      bracketDepth === 0 &&
      braceDepth === 0 &&
      angleDepth === 0
    );
    if (isTopLevel && shouldStop(text, i)) {
      return {
        value: text.slice(start, i).trim(),
        end: i,
      };
    }

    if (ch === "(") parenDepth += 1;
    else if (ch === ")") parenDepth = Math.max(0, parenDepth - 1);
    else if (ch === "[") bracketDepth += 1;
    else if (ch === "]") bracketDepth = Math.max(0, bracketDepth - 1);
    else if (ch === "{") braceDepth += 1;
    else if (ch === "}") braceDepth = Math.max(0, braceDepth - 1);
    else if (ch === "<") angleDepth += 1;
    else if (ch === ">" && text[i - 1] !== "=") angleDepth = Math.max(0, angleDepth - 1);
  }

  return {
    value: text.slice(start).trim(),
    end: text.length,
  };
}

function readForwardChunk(lines, startIndex, maxLines = LOOKAHEAD_LINES) {
  return lines.slice(startIndex, Math.min(lines.length, startIndex + maxLines)).join("\n");
}

function consumedLineCount(text, endIndex) {
  return Math.max(1, text.slice(0, endIndex).split("\n").length);
}

function truncateValue(value, maxChars = 200) {
  const trimmed = value.replace(/\s+/g, " ").trim();
  if (trimmed.length <= maxChars) return trimmed;
  return `${trimmed.slice(0, maxChars)}...`;
}

function createFunctionInfo({
  name,
  qualname,
  module,
  lineno,
  paramsRaw,
  returnAnnotation,
  isAsync = false,
  isMethod = false,
  isStatic = false,
}) {
  return {
    name,
    qualname,
    module,
    lineno,
    decorators: [],
    params: parseParams(paramsRaw),
    signature_params: paramsRaw.trim(),
    return_annotation: returnAnnotation.trim(),
    docstring: "",
    is_async: isAsync,
    is_method: isMethod,
    is_property: false,
    is_staticmethod: isStatic,
    is_classmethod: false,
  };
}

function readFunctionTail(text, start, { arrow }) {
  let idx = skipWhitespace(text, start);
  let returnAnnotation = "";

  if (text[idx] === ":") {
    const stop = readUntilTopLevel(
      text,
      idx + 1,
      (src, pos) => arrow ? src.startsWith("=>", pos) : src[pos] === "{" || src[pos] === ";"
    );
    returnAnnotation = stop.value;
    idx = stop.end;
  }

  idx = skipWhitespace(text, idx);
  if (arrow) {
    if (!text.startsWith("=>", idx)) return null;
    idx += 2;
  } else if (text[idx] === "{") {
    idx += 1;
  } else if (text[idx] === ";") {
    idx += 1;
  } else {
    return null;
  }

  return { returnAnnotation, end: idx };
}

function parseExportedFunction(lines, startIndex, moduleName) {
  const text = readForwardChunk(lines, startIndex);
  const match = text.match(/^export\s+(default\s+)?(?:(async)\s+)?function\s+/);
  if (!match) return null;

  let idx = match[0].length;
  const nameInfo = readIdentifier(text, idx);
  if (!nameInfo) return null;
  const name = nameInfo.value;
  idx = skipWhitespace(text, nameInfo.end);

  if (text[idx] === "<") {
    const typeParams = readBalanced(text, idx, "<", ">");
    if (!typeParams) return null;
    idx = skipWhitespace(text, typeParams.end);
  }

  if (text[idx] !== "(") return null;
  const params = readBalanced(text, idx, "(", ")");
  if (!params) return null;

  const tail = readFunctionTail(text, params.end, { arrow: false });
  if (!tail) return null;

  return {
    functionInfo: createFunctionInfo({
      name,
      qualname: `${moduleName}.${name}`,
      module: moduleName,
      lineno: startIndex + 1,
      paramsRaw: params.value,
      returnAnnotation: tail.returnAnnotation,
      isAsync: !!match[2],
    }),
    consumedLines: consumedLineCount(text, tail.end),
    isDefault: !!match[1],
  };
}

function parseExportedConst(lines, startIndex, moduleName) {
  const text = readForwardChunk(lines, startIndex);
  const match = text.match(/^export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)/);
  if (!match) return null;

  const name = match[1];
  let idx = skipWhitespace(text, match[0].length);
  let annotation = "";

  if (text[idx] === ":") {
    const typeChunk = readUntilTopLevel(text, idx + 1, (src, pos) => src[pos] === "=");
    annotation = typeChunk.value;
    idx = typeChunk.end;
  }

  idx = skipWhitespace(text, idx);
  if (text[idx] !== "=") return null;
  idx = skipWhitespace(text, idx + 1);

  let isAsync = false;
  if (text.startsWith("async", idx) && !/[A-Za-z0-9_$]/.test(text[idx + 5] || "")) {
    isAsync = true;
    idx = skipWhitespace(text, idx + 5);
  }

  if (text[idx] === "<") {
    const typeParams = readBalanced(text, idx, "<", ">");
    if (!typeParams) return null;
    idx = skipWhitespace(text, typeParams.end);
  }

  if (text[idx] === "(") {
    const params = readBalanced(text, idx, "(", ")");
    if (params) {
      const tail = readFunctionTail(text, params.end, { arrow: true });
      if (tail) {
        return {
          kind: "function",
          functionInfo: createFunctionInfo({
            name,
            qualname: `${moduleName}.${name}`,
            module: moduleName,
            lineno: startIndex + 1,
            paramsRaw: params.value,
            returnAnnotation: tail.returnAnnotation,
            isAsync,
          }),
          consumedLines: consumedLineCount(text, tail.end),
        };
      }
    }
  }

  const valueChunk = readUntilTopLevel(text, idx, (src, pos) => src[pos] === ";");
  const end = valueChunk.end < text.length ? valueChunk.end + 1 : valueChunk.end;
  return {
    kind: "constant",
    name,
    value: truncateValue(valueChunk.value || text.slice(idx)),
    annotation: annotation.trim(),
    consumedLines: consumedLineCount(text, end),
  };
}

function parseClassMethod(lines, startIndex, moduleName, className) {
  const text = readForwardChunk(lines, startIndex);
  let idx = 0;
  let isAsync = false;
  let isStatic = false;

  while (true) {
    const token = readIdentifier(text, idx);
    if (!token || !CLASS_MEMBER_MODIFIERS.has(token.value)) break;
    if (token.value === "async") isAsync = true;
    if (token.value === "static") isStatic = true;
    idx = skipWhitespace(text, token.end);
  }

  const nameInfo = readIdentifier(text, idx);
  if (!nameInfo) return null;
  const name = nameInfo.value;
  idx = skipWhitespace(text, nameInfo.end);

  if (text[idx] === "?") {
    idx = skipWhitespace(text, idx + 1);
  }

  if (text[idx] === ":" || text[idx] === "=" || text[idx] === ";" || text[idx] === "[") {
    return null;
  }

  if (text[idx] === "<") {
    const typeParams = readBalanced(text, idx, "<", ">");
    if (!typeParams) return null;
    idx = skipWhitespace(text, typeParams.end);
  }

  if (text[idx] !== "(") return null;
  const params = readBalanced(text, idx, "(", ")");
  if (!params) return null;

  const tail = readFunctionTail(text, params.end, { arrow: false });
  if (!tail) return null;

  return {
    functionInfo: createFunctionInfo({
      name,
      qualname: `${moduleName}.${className}.${name}`,
      module: moduleName,
      lineno: startIndex + 1,
      paramsRaw: params.value,
      returnAnnotation: tail.returnAnnotation,
      isAsync,
      isMethod: true,
      isStatic,
    }),
    consumedLines: consumedLineCount(text, tail.end),
  };
}

function parseClassField(lines, startIndex) {
  const text = readForwardChunk(lines, startIndex);
  let idx = 0;

  while (true) {
    const token = readIdentifier(text, idx);
    if (!token || !CLASS_MEMBER_MODIFIERS.has(token.value)) break;
    idx = skipWhitespace(text, token.end);
  }

  const nameInfo = readIdentifier(text, idx);
  if (!nameInfo) return null;
  const name = nameInfo.value;
  idx = skipWhitespace(text, nameInfo.end);

  if (text[idx] === "?") {
    idx = skipWhitespace(text, idx + 1);
  }

  if (text[idx] === "<" || text[idx] === "(" || text[idx] === "[") {
    return null;
  }

  let annotation = "";
  if (text[idx] === ":") {
    const typeChunk = readUntilTopLevel(
      text,
      idx + 1,
      (src, pos) => src[pos] === "=" || src[pos] === ";"
    );
    annotation = typeChunk.value.trim();
    idx = typeChunk.end;
  }

  idx = skipWhitespace(text, idx);
  if (text[idx] === "=") {
    const valueChunk = readUntilTopLevel(text, idx + 1, (src, pos) => src[pos] === ";");
    const end = valueChunk.end < text.length ? valueChunk.end + 1 : valueChunk.end;
    return {
      name,
      annotation,
      consumedLines: consumedLineCount(text, end),
    };
  }

  if (text[idx] === ";") {
    return {
      name,
      annotation,
      consumedLines: consumedLineCount(text, idx + 1),
    };
  }

  return null;
}

function braceDelta(line) {
  let delta = 0;
  let quote = null;
  let escaped = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    const next = line[i + 1] || "";

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      break;
    }

    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      continue;
    }

    if (ch === "{") delta += 1;
    else if (ch === "}") delta -= 1;
  }

  return delta;
}

function delimiterDelta(line) {
  let paren = 0;
  let brace = 0;
  let quote = null;
  let escaped = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    const next = line[i + 1] || "";

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === "/" && next === "/") {
      break;
    }

    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      continue;
    }

    if (ch === "(") paren += 1;
    else if (ch === ")") paren -= 1;
    else if (ch === "{") brace += 1;
    else if (ch === "}") brace -= 1;
  }

  return { paren, brace };
}

function scanSourceFile(filePath) {
  const source = readFileSync(filePath, "utf-8");
  const lines = source.split("\n");
  const moduleName = basename(filePath).replace(extname(filePath), "");

  const functions = [];
  const classes = [];
  const constants = [];
  const imports = [];
  const fromImports = [];
  const stringLiterals = [];
  const allExports = [];
  const interfaces = [];

  const exportClassRe = /^export\s+(default\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)(?:\s+extends\s+([A-Za-z_$][A-Za-z0-9_$]*))?/;
  const importRe = /^import\s+(?:type\s+)?(?:\{([^}]+)\}\s+from|([A-Za-z_$][A-Za-z0-9_$]*)\s+from)\s+['"]([^'"]+)['"]/;
  const namedExportRe = /^export\s+\{([^}]+)\}/;
  const exportInterfaceRe = /^export\s+interface\s+([A-Za-z_$][A-Za-z0-9_$]*)/;
  const exportTypeRe = /^export\s+type\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:<[^>]*>)?\s*=/;
  const stringLitRe = /['"](\w[\w.-]{2,})['"]/g;

  let currentClass = null;
  let classDepth = 0;
  let defaultExport = "";

  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("//") || trimmed.startsWith("/*")) {
      if (currentClass) {
        classDepth += braceDelta(line);
        if (classDepth <= 0) {
          currentClass = null;
          classDepth = 0;
        }
      }
      i += 1;
      continue;
    }

    if (!currentClass) {
      const impMatch = trimmed.match(importRe);
      if (impMatch) {
        const names = impMatch[1]
          ? impMatch[1].split(",").map((s) => s.trim().split(/\s+as\s+/)[0].trim()).filter(Boolean)
          : impMatch[2]
            ? [impMatch[2]]
            : [];
        const mod = impMatch[3];
        if (names.length) fromImports.push([mod, names]);
        else imports.push(mod);
        i += 1;
        continue;
      }

      const namedExpMatch = trimmed.match(namedExportRe);
      if (namedExpMatch) {
        namedExpMatch[1].split(",").forEach((s) => {
          const name = s.trim().split(/\s+as\s+/)[0].trim();
          if (name) allExports.push(name);
        });
        i += 1;
        continue;
      }

      const ifaceMatch = trimmed.match(exportInterfaceRe);
      if (ifaceMatch) {
        const ifaceName = ifaceMatch[1];
        allExports.push(ifaceName);
        const members = [];
        let depth = 0;
        for (let j = i; j < lines.length; j += 1) {
          depth += braceDelta(lines[j]);
          if (j > i) {
            const memberLine = lines[j].trim();
            const memberMatch = memberLine.match(/^(\w+)\??(?:\s*:\s*(.+?))?[;,]?\s*$/);
            if (memberMatch && depth >= 1) {
              members.push([memberMatch[1], (memberMatch[2] || "").replace(/;$/, "").trim()]);
            }
          }
          if (depth <= 0 && j > i) {
            i = j + 1;
            break;
          }
        }
        interfaces.push({
          name: ifaceName,
          module: moduleName,
          lineno: i + 1,
          members,
          is_type_alias: false,
        });
        continue;
      }

      const typeAliasMatch = trimmed.match(exportTypeRe);
      if (typeAliasMatch) {
        const typeName = typeAliasMatch[1];
        allExports.push(typeName);
        interfaces.push({
          name: typeName,
          module: moduleName,
          lineno: i + 1,
          members: [],
          is_type_alias: true,
        });
        i += 1;
        continue;
      }

      const classMatch = trimmed.match(exportClassRe);
      if (classMatch) {
        currentClass = {
          name: classMatch[2],
          qualname: `${moduleName}.${classMatch[2]}`,
          module: moduleName,
          lineno: i + 1,
          bases: classMatch[3] ? [classMatch[3]] : [],
          decorators: [],
          docstring: "",
          methods: [],
          class_variables: [],
        };
        classes.push(currentClass);
        allExports.push(classMatch[2]);
        if (classMatch[1]) {
          defaultExport = classMatch[2];
        }
        classDepth = Math.max(1, braceDelta(line));
        i += 1;
        continue;
      }

      const exportedFn = parseExportedFunction(lines, i, moduleName);
      if (exportedFn) {
        functions.push(exportedFn.functionInfo);
        allExports.push(exportedFn.functionInfo.name);
        if (exportedFn.isDefault) {
          defaultExport = exportedFn.functionInfo.name;
        }
        i += exportedFn.consumedLines;
        continue;
      }

      const exportedConst = parseExportedConst(lines, i, moduleName);
      if (exportedConst) {
        if (exportedConst.kind === "function") {
          functions.push(exportedConst.functionInfo);
          allExports.push(exportedConst.functionInfo.name);
        } else {
          constants.push([exportedConst.name, exportedConst.value]);
          allExports.push(exportedConst.name);
        }
        i += exportedConst.consumedLines;
        continue;
      }
    } else if (classDepth === 1) {
      const method = parseClassMethod(lines, i, moduleName, currentClass.name);
      if (method) {
        currentClass.methods.push(method.functionInfo);
        for (let j = 0; j < method.consumedLines; j += 1) {
          classDepth += braceDelta(lines[i + j] || "");
        }
        if (classDepth <= 0) {
          currentClass = null;
          classDepth = 0;
        }
        i += method.consumedLines;
        continue;
      }

      const field = parseClassField(lines, i);
      if (field) {
        currentClass.class_variables.push([field.name, field.annotation]);
        for (let j = 0; j < field.consumedLines; j += 1) {
          classDepth += braceDelta(lines[i + j] || "");
        }
        if (classDepth <= 0) {
          currentClass = null;
          classDepth = 0;
        }
        i += field.consumedLines;
        continue;
      }
    }

    let match;
    while ((match = stringLitRe.exec(trimmed)) !== null) {
      if (match[1].length >= 3 && match[1].length <= 60) {
        stringLiterals.push(match[1]);
      }
    }

    if (currentClass) {
      classDepth += braceDelta(line);
      if (classDepth <= 0) {
        currentClass = null;
        classDepth = 0;
      }
    }

    i += 1;
  }

  return {
    path: filePath,
    module_name: moduleName,
    docstring: "",
    imports,
    from_imports: fromImports,
    all_exports: [...new Set(allExports)],
    constants,
    functions,
    classes,
    interfaces,
    string_literals: [...new Set(stringLiterals)].sort(),
    line_count: lines.length,
    default_export: defaultExport,
  };
}

function parseParams(raw) {
  if (!raw.trim()) return [];
  const parts = splitParams(raw);
  return parts.map((part) => {
    part = part.trim();
    const optionalMatch = part.match(/^(\w+)\??(?:\s*:\s*(.+?))?(?:\s*=\s*(.+))?$/);
    if (optionalMatch) {
      return {
        name: optionalMatch[1],
        annotation: (optionalMatch[2] || "").trim(),
        default: (optionalMatch[3] || "").trim(),
      };
    }
    const simpleMatch = part.match(/^(\w+)(?:\s*:\s*(.+?))?(?:\s*=\s*(.+))?$/);
    if (simpleMatch) {
      return {
        name: simpleMatch[1],
        annotation: (simpleMatch[2] || "").trim(),
        default: (simpleMatch[3] || "").trim(),
      };
    }
    return { name: part, annotation: "", default: "" };
  });
}

function splitParams(raw) {
  const result = [];
  let depth = 0;
  let current = "";

  for (let i = 0; i < raw.length; i += 1) {
    const ch = raw[i];
    const prev = raw[i - 1] || "";

    if (ch === "(" || ch === "<" || ch === "[" || ch === "{") depth += 1;
    if (ch === ")" || ch === "]" || ch === "}") depth -= 1;
    if (ch === ">" && prev !== "=") depth -= 1;

    if (ch === "," && depth === 0) {
      result.push(current);
      current = "";
    } else {
      current += ch;
    }
  }

  if (current.trim()) result.push(current);
  return result;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasIdentifier(text, name) {
  return new RegExp(`(^|[^A-Za-z0-9_$])${escapeRegExp(name)}([^A-Za-z0-9_$]|$)`).test(text);
}

function collectModuleSymbolNames(mod) {
  const names = new Set(mod.all_exports || []);
  for (const fn of mod.functions || []) names.add(fn.name);
  for (const cls of mod.classes || []) {
    names.add(cls.name);
    for (const method of cls.methods || []) names.add(method.name);
    for (const [name] of cls.class_variables || []) names.add(name);
  }
  for (const iface of mod.interfaces || []) {
    names.add(iface.name);
    for (const [name] of iface.members || []) names.add(name);
  }
  for (const [name] of mod.constants || []) names.add(name);
  return names;
}

function buildModuleLookup(modules) {
  const byPath = new Map();
  for (const mod of modules) {
    byPath.set(resolve(mod.path), {
      ...mod,
      export_names: collectModuleSymbolNames(mod),
    });
  }
  return byPath;
}

function resolveLocalModule(specifier, fromFile, moduleLookup) {
  if (!specifier.startsWith("./") && !specifier.startsWith("../")) {
    return null;
  }

  const base = resolve(dirname(fromFile), specifier);
  const candidates = new Set([base]);
  for (const ext of LOCAL_IMPORT_EXTENSIONS) {
    candidates.add(base + ext);
    candidates.add(resolve(base, `index${ext}`));
  }

  if (base.endsWith(".js")) candidates.add(base.slice(0, -3) + ".ts");
  if (base.endsWith(".mjs")) candidates.add(base.slice(0, -4) + ".mts");

  for (const candidate of candidates) {
    const resolvedCandidate = resolve(candidate);
    if (moduleLookup.has(resolvedCandidate)) {
      return resolvedCandidate;
    }
  }

  return null;
}

function parseNamedBindings(raw) {
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const [imported, local] = entry.split(/\s+as\s+/).map((part) => part.trim());
      return {
        imported,
        local: local || imported,
      };
    });
}

function extractImportMaps(source, filePath, moduleLookup, knownSymbols) {
  const namedImports = new Map();
  const namespaceImports = new Map();

  const importLines = source.match(/^\s*import[\s\S]*?from\s+['"][^'"]+['"]\s*;?\s*$/gm) || [];
  for (const line of importLines) {
    const clauseMatch = line.match(/^\s*import\s+([\s\S]+?)\s+from\s+['"]([^'"]+)['"]/);
    if (!clauseMatch) continue;

    const clause = clauseMatch[1].trim();
    const specifier = clauseMatch[2];
    const resolved = resolveLocalModule(specifier, filePath, moduleLookup);
    if (!resolved) continue;

    const mod = moduleLookup.get(resolved);
    if (!mod) continue;

    if (clause.startsWith("* as ")) {
      const alias = clause.slice(5).trim();
      namespaceImports.set(alias, mod.export_names);
      continue;
    }

    if (clause.startsWith("{")) {
      const named = parseNamedBindings(clause.slice(1, clause.lastIndexOf("}")));
      for (const binding of named) {
        namedImports.set(binding.local, binding.imported);
      }
      continue;
    }

    const parts = clause.split(",");
    const defaultImport = parts[0]?.trim();
    if (defaultImport) {
      const importedName = mod.default_export || (knownSymbols.has(defaultImport) ? defaultImport : "");
      if (importedName) {
        namedImports.set(defaultImport, importedName);
      }
    }

    const namedPart = parts.slice(1).join(",").trim();
    if (namedPart.startsWith("{")) {
      const named = parseNamedBindings(namedPart.slice(1, namedPart.lastIndexOf("}")));
      for (const binding of named) {
        namedImports.set(binding.local, binding.imported);
      }
    }
  }

  return { namedImports, namespaceImports };
}

function findEachTestName(lines, startIndex) {
  for (let i = startIndex; i < Math.min(lines.length, startIndex + LOOKAHEAD_LINES); i += 1) {
    const match = lines[i].match(/\)\s*\(\s*['"`](.+?)['"`]/);
    if (match) {
      return match[1];
    }
  }
  return "";
}

function extractTestSnippet(lines, startIndex) {
  const snippetLines = [];
  let parenDepth = 0;
  let braceDepth = 0;
  let endIndex = startIndex;

  for (let i = startIndex; i < Math.min(lines.length, startIndex + 200); i += 1) {
    snippetLines.push(lines[i]);
    const delta = delimiterDelta(lines[i]);
    parenDepth += delta.paren;
    braceDepth += delta.brace;
    endIndex = i;

    if (i > startIndex && parenDepth <= 0 && braceDepth <= 0) {
      break;
    }
  }

  return {
    snippet: snippetLines.join("\n"),
    endIndex,
  };
}

function collectReferencedSymbols(text, namedImports, namespaceImports, knownSymbols) {
  const referenced = new Set();

  for (const [alias, imported] of namedImports.entries()) {
    if (hasIdentifier(text, alias)) {
      referenced.add(imported);
    }
  }

  for (const [alias, exportNames] of namespaceImports.entries()) {
    const memberRe = new RegExp(`\\b${escapeRegExp(alias)}\\.([A-Za-z_$][A-Za-z0-9_$]*)`, "g");
    for (const match of text.matchAll(memberRe)) {
      if (exportNames.has(match[1])) {
        referenced.add(match[1]);
      }
    }

    const spyRe = new RegExp(`\\b${escapeRegExp(alias)}\\b[^\\n]*?["'\`]([A-Za-z_$][A-Za-z0-9_$]*)["'\`]`, "g");
    for (const match of text.matchAll(spyRe)) {
      if (exportNames.has(match[1])) {
        referenced.add(match[1]);
      }
    }
  }

  for (const sym of knownSymbols) {
    if (hasIdentifier(text, sym)) {
      referenced.add(sym);
    }
  }

  return referenced;
}

// ---------------------------------------------------------------------------
// Test file scanning
// ---------------------------------------------------------------------------

function scanTestFile(filePath, knownSymbols, moduleLookup) {
  const source = readFileSync(filePath, "utf-8");
  const lines = source.split("\n");
  const tests = [];

  const { namedImports, namespaceImports } = extractImportMaps(source, filePath, moduleLookup, knownSymbols);
  const fileLevelReferenced = collectReferencedSymbols(
    source,
    namedImports,
    namespaceImports,
    knownSymbols
  );

  const directTestRe = /(?:it|test)(?:\.\w+)*\s*\(\s*['"`](.+?)['"`]/;
  const eachTestRe = /(?:it|test)\.each\s*\(/;
  const describeRe = /describe\s*\(\s*['"`](.+?)['"`]/;

  let currentDescribe = "";

  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    const trimmed = line.trim();

    const descMatch = trimmed.match(describeRe);
    if (descMatch) {
      currentDescribe = descMatch[1];
    }

    let testName = "";
    const directMatch = trimmed.match(directTestRe);
    if (directMatch) {
      testName = directMatch[1];
    } else if (eachTestRe.test(trimmed)) {
      testName = findEachTestName(lines, i);
    }

    if (!testName) {
      i += 1;
      continue;
    }

    const fullName = currentDescribe ? `${currentDescribe} > ${testName}` : testName;
    const { snippet, endIndex } = extractTestSnippet(lines, i);
    const referenced = new Set(fileLevelReferenced);
    for (const sym of collectReferencedSymbols(snippet, namedImports, namespaceImports, knownSymbols)) {
      referenced.add(sym);
    }

    tests.push({
      test_file: filePath,
      test_name: fullName.replace(/\s+/g, "_").replace(/[^a-zA-Z0-9_]/g, ""),
      tested_symbols: [...referenced].sort(),
      source_snippet: snippet.slice(0, 1000),
    });
    i = endIndex + 1;
  }

  return tests;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const modules = [];
for (const fp of sourceFiles) {
  if (!existsSync(fp)) {
    console.error(`Source file not found: ${fp}`);
    process.exit(1);
  }
  modules.push(scanSourceFile(fp));
}

const moduleLookup = buildModuleLookup(modules);
const allSymbols = new Set();
for (const mod of modules) {
  for (const name of collectModuleSymbolNames(mod)) {
    allSymbols.add(name);
  }
}

const allTests = [];
for (const fp of testFiles) {
  if (!existsSync(fp)) {
    console.error(`Test file not found: ${fp}`);
    process.exit(1);
  }
  allTests.push(...scanTestFile(fp, allSymbols, moduleLookup));
}

const result = {
  source_files: modules,
  tests: allTests,
  total_loc: modules.reduce((sum, m) => sum + m.line_count, 0),
};

process.stdout.write(JSON.stringify(result, null, 2));
