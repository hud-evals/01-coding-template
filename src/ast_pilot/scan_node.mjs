#!/usr/bin/env node
/**
 * TypeScript scanner helper — uses the TS compiler API to extract
 * exported symbols, signatures, and test evidence from .ts files.
 *
 * Usage:
 *   node scan_node.mjs --sources src/lib.ts --tests tests/lib.test.ts [--tsconfig tsconfig.json]
 *
 * Outputs JSON to stdout matching the shape expected by node_scanner.py.
 */

import { readFileSync, existsSync } from "node:fs";
import { resolve, basename, relative, extname } from "node:path";
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

// ---------------------------------------------------------------------------
// Lightweight TS-free parsing using regex + line analysis
// (avoids requiring the typescript package to be installed globally)
// ---------------------------------------------------------------------------

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
  let lineCount = lines.length;

  const exportFnRe =
    /^export\s+(async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::\s*(.+?))?(?:\s*\{|$)/;
  const exportConstRe = /^export\s+const\s+([A-Z_][A-Z0-9_]*)\s*(?::\s*\S+)?\s*=\s*(.+)/;
  const exportClassRe = /^export\s+(default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?/;
  const exportDefaultFnRe =
    /^export\s+default\s+(async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::\s*(.+?))?(?:\s*\{|$)/;
  const importRe = /^import\s+(?:type\s+)?(?:\{([^}]+)\}\s+from|(\w+)\s+from)\s+['"]([^'"]+)['"]/;
  const methodRe =
    /^\s+(async\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*(.+?))?(?:\s*\{|$)/;
  const namedExportRe = /^export\s+\{([^}]+)\}/;
  const stringLitRe = /['"](\w[\w.-]{2,})['"]/g;

  let currentClass = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("//") || trimmed.startsWith("/*")) continue;

    // Imports
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
      continue;
    }

    // Named re-exports
    const namedExpMatch = trimmed.match(namedExportRe);
    if (namedExpMatch) {
      namedExpMatch[1].split(",").forEach((s) => {
        const name = s.trim().split(/\s+as\s+/)[0].trim();
        if (name) allExports.push(name);
      });
      continue;
    }

    // Exported class
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
      continue;
    }

    // Close current class heuristic (non-indented non-empty line that isn't a method)
    if (currentClass && !line.startsWith(" ") && !line.startsWith("\t") && trimmed !== "}" && trimmed !== "") {
      if (!trimmed.match(methodRe)) {
        currentClass = null;
      }
    }

    // Class methods
    if (currentClass) {
      const methodMatch = trimmed.match(methodRe);
      if (methodMatch && methodMatch[2] !== "constructor" || (methodMatch && methodMatch[2] === "constructor")) {
        const isAsync = !!methodMatch[1];
        const name = methodMatch[2];
        const rawParams = methodMatch[3] || "";
        const retAnnotation = methodMatch[4] ? methodMatch[4].replace(/\s*\{$/, "").trim() : "";
        const params = parseParams(rawParams);
        currentClass.methods.push({
          name,
          qualname: `${moduleName}.${currentClass.name}.${name}`,
          module: moduleName,
          lineno: i + 1,
          decorators: [],
          params,
          signature_params: rawParams.trim(),
          return_annotation: retAnnotation,
          docstring: "",
          is_async: isAsync,
          is_method: true,
          is_property: false,
          is_staticmethod: trimmed.includes("static "),
          is_classmethod: false,
        });
        continue;
      }
    }

    // Exported default function
    const defFnMatch = trimmed.match(exportDefaultFnRe);
    if (defFnMatch) {
      const isAsync = !!defFnMatch[1];
      const name = defFnMatch[2];
      const rawParams = defFnMatch[3] || "";
      const retAnnotation = defFnMatch[4] ? defFnMatch[4].replace(/\s*\{$/, "").trim() : "";
      functions.push({
        name,
        qualname: `${moduleName}.${name}`,
        module: moduleName,
        lineno: i + 1,
        decorators: [],
        params: parseParams(rawParams),
        signature_params: rawParams.trim(),
        return_annotation: retAnnotation,
        docstring: "",
        is_async: isAsync,
        is_method: false,
        is_property: false,
        is_staticmethod: false,
        is_classmethod: false,
      });
      allExports.push(name);
      continue;
    }

    // Exported function
    const fnMatch = trimmed.match(exportFnRe);
    if (fnMatch) {
      const isAsync = !!fnMatch[1];
      const name = fnMatch[2];
      const rawParams = fnMatch[3] || "";
      const retAnnotation = fnMatch[4] ? fnMatch[4].replace(/\s*\{$/, "").trim() : "";
      functions.push({
        name,
        qualname: `${moduleName}.${name}`,
        module: moduleName,
        lineno: i + 1,
        decorators: [],
        params: parseParams(rawParams),
        signature_params: rawParams.trim(),
        return_annotation: retAnnotation,
        docstring: "",
        is_async: isAsync,
        is_method: false,
        is_property: false,
        is_staticmethod: false,
        is_classmethod: false,
      });
      allExports.push(name);
      continue;
    }

    // Exported constant
    const constMatch = trimmed.match(exportConstRe);
    if (constMatch) {
      let val = constMatch[2].replace(/;$/, "").trim();
      if (val.length > 200) val = val.slice(0, 200) + "...";
      constants.push([constMatch[1], val]);
      allExports.push(constMatch[1]);
      continue;
    }

    // String literals
    let m;
    while ((m = stringLitRe.exec(trimmed)) !== null) {
      if (m[1].length >= 3 && m[1].length <= 60) stringLiterals.add
        ? stringLiterals.push(m[1])
        : stringLiterals.push(m[1]);
    }
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
    string_literals: [...new Set(stringLiterals)].sort(),
    line_count: lineCount,
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
  for (const ch of raw) {
    if (ch === "(" || ch === "<" || ch === "[" || ch === "{") depth++;
    if (ch === ")" || ch === ">" || ch === "]" || ch === "}") depth--;
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

// ---------------------------------------------------------------------------
// Test file scanning
// ---------------------------------------------------------------------------

function scanTestFile(filePath, knownSymbols) {
  const source = readFileSync(filePath, "utf-8");
  const lines = source.split("\n");
  const tests = [];

  const testRe = /(?:it|test)\s*\(\s*['"`](.+?)['"`]/;
  const describeRe = /describe\s*\(\s*['"`](.+?)['"`]/;

  let currentDescribe = "";
  let testStartLine = -1;
  let depth = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    const descMatch = trimmed.match(describeRe);
    if (descMatch) {
      currentDescribe = descMatch[1];
    }

    const testMatch = trimmed.match(testRe);
    if (testMatch) {
      const testName = currentDescribe
        ? `${currentDescribe} > ${testMatch[1]}`
        : testMatch[1];

      const snippetEnd = Math.min(i + 30, lines.length);
      const snippet = lines.slice(i, snippetEnd).join("\n");

      const referenced = new Set();
      for (const sym of knownSymbols) {
        if (snippet.includes(sym)) referenced.add(sym);
      }

      tests.push({
        test_file: filePath,
        test_name: testName.replace(/\s+/g, "_").replace(/[^a-zA-Z0-9_]/g, ""),
        tested_symbols: [...referenced].sort(),
        source_snippet: snippet.slice(0, 1000),
      });
    }
  }

  return tests;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const allSymbols = new Set();
const modules = [];

for (const fp of sourceFiles) {
  if (!existsSync(fp)) {
    console.error(`Source file not found: ${fp}`);
    process.exit(1);
  }
  const mod = scanSourceFile(fp);
  modules.push(mod);
  for (const fn of mod.functions) allSymbols.add(fn.name);
  for (const cls of mod.classes) {
    allSymbols.add(cls.name);
    for (const m of cls.methods) allSymbols.add(m.name);
  }
  for (const [name] of mod.constants) allSymbols.add(name);
}

const allTests = [];
for (const fp of testFiles) {
  if (!existsSync(fp)) {
    console.error(`Test file not found: ${fp}`);
    process.exit(1);
  }
  allTests.push(...scanTestFile(fp, allSymbols));
}

const result = {
  source_files: modules,
  tests: allTests,
  total_loc: modules.reduce((sum, m) => sum + m.line_count, 0),
};

process.stdout.write(JSON.stringify(result, null, 2));
