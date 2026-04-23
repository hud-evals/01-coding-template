# citty

## Overview

**citty** is a lightweight TypeScript utility library comprising 950 lines of code organized across 10 source modules. The library exports a single class alongside 15 module-level functions, providing a focused set of utilities for developers working in modern JavaScript environments. Built with TypeScript for full type safety and compiled to ES modules, citty is designed to be integrated into projects that leverage contemporary module systems and tooling.

The codebase is validated and tested using vitest, a modern test runner optimized for TypeScript and ES module workflows. With a minimal surface area of just one class and a collection of pure functional exports, citty maintains a lean architecture that prioritizes simplicity and composability. The 10-module structure allows for logical separation of concerns while keeping the overall package footprint small and maintainable.

This library targets developers seeking reliable, type-safe utility functions without the overhead of larger frameworks or utility suites. The ES module-first approach ensures compatibility with contemporary bundlers and runtime environments that support native module syntax.

# Natural Language Instructions for Rebuilding the Citty Library

## Implementation Constraints

- All source files must be created directly in `/home/ubuntu/workspace` with no subdirectories
- Do NOT run any package manager commands; all dependencies are pre-configured
- Use exact function signatures and type definitions provided in the EXACT API section
- Implement all 15 module-level functions and 1 class with all required properties
- All private helper functions must be prefixed with underscore (e.g., `_c`, `_showUsage`)
- Write pure TypeScript with no JavaScript; leverage TypeScript's type system fully
- Ensure all 85 test cases pass by implementing exact behaviors described in test evidence

## Behavioral Requirements

### Color Functions (_color.ts)
1. Create a private helper function `_c(code: number, reset?: number)` that returns a function wrapping text with ANSI color codes
2. Export color functions (`bold`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `gray`, `underline`) using `_c` with appropriate ANSI codes
3. Use `@__PURE__` comments to mark color functions as pure for tree-shaking

### Argument Parsing (_parser.ts)
4. Implement `parseRawArgs(args: string[] = [], opts: ParseOptions = {})` to parse raw command-line arguments into an `Argv` object
5. Support `ParseOptions.boolean` array to treat specified flags as booleans (no value consumption)
6. Support `ParseOptions.string` array to treat specified flags as strings (consume next token as value)
7. Support `ParseOptions.alias` record mapping argument names to arrays of alias strings
8. Support `ParseOptions.default` record providing default values for arguments
9. Coerce string values `"true"` and `"false"` to boolean `true` and `false` for boolean-type arguments
10. Return empty string `""` for string-type arguments without a value
11. Normalize camelCase and kebab-case argument names (e.g., `--user-name` and `--userName` both resolve to the same key)
12. Collect positional arguments in the `_` array property of the result

### Utilities (_utils.ts)
13. Implement `toArray(val: any)` to convert any value to an array (wrap non-arrays, return arrays as-is)
14. Implement `formatLineColumns(lines: string[][], linePrefix = "")` to format a 2D array of strings as aligned columns with optional line prefix
15. Implement `resolveValue(input: Resolvable<T>)` to resolve a value that may be a plain value, function, or async function, returning `T | Promise<T>`

### Error Handling (types.ts)
16. Create `CLIError` class extending `Error` with optional `code: string | undefined` property
17. Constructor accepts `message: string` and optional `code?: string` parameters

### Argument Definition and Parsing (args.ts)
18. Define `ArgType` as union of `"string" | "boolean" | "enum" | "positional"`
19. Define `_ArgDef` as base interface with optional `description: string` and `alias?: string`
20. Define `BooleanArgDef` with `type: "boolean"` and optional `default: boolean`
21. Define `StringArgDef` with `type: "string"` and optional `default: string`
22. Define `EnumArgDef` with `type: "enum"`, required `options: string[]`, and optional `default: string`
23. Define `PositionalArgDef` with `type: "positional"` and optional `default: string`
24. Define `ArgDef` as union of all argument definition types
25. Define `ArgsDef` as record mapping argument names to `ArgDef` values
26. Define `Arg` as resolved argument definition with `name: string` and `type: ArgType`
27. Define `ParsedArgs<T>` as record with parsed argument values plus `_: string[]` for positional args
28. Implement `resolveArgs(argsDef: ArgsDef)` to convert `ArgsDef` to array of `Arg` objects
29. Implement `parseArgs(rawArgs: string[], argsDef: ArgsDef)` to parse raw arguments using argument definitions
30. Support argument aliases in parsing (resolve both primary name and aliases)
31. Handle camelCase/kebab-case normalization in argument definitions

### Command Definition (command.ts)
32. Define `CommandMeta` interface with optional properties: `name?: string`, `version?: string`, `description?: string`, `hidden?: boolean`, `alias?: string | string[]`
33. Define `SubCommandsDef` as record mapping subcommand names to `CommandDef` values
34. Define `CommandDef<T = any>` with optional properties:
    - `meta?: CommandMeta | (() => CommandMeta | Promise<CommandMeta>)`
    - `args?: ArgsDef`
    - `subCommands?: SubCommandsDef`
    - `default?: string` (name of default subcommand)
    - `setup?: (ctx: CommandContext) => void | Promise<void>`
    - `cleanup?: (ctx: CommandContext) => void | Promise<void>`
    - `run?: (ctx: CommandContext) => unknown | Promise<unknown>`
35. Define `CommandContext<T = any>` with properties: `args: ParsedArgs<T>`, `data?: any`, `command: CommandDef<T>`, `parent?: CommandDef<T>`
36. Implement `defineCommand(def: CommandDef<T>)` to return the command definition as-is (identity function for type safety)

### Command Execution (command.ts)
37. Define `RunCommandOptions` interface with optional properties: `rawArgs?: string[]`, `data?: any`, `showUsage?: boolean`
38. Implement `runCommand(cmd: CommandDef<T>, opts: RunCommandOptions)` as async function returning `Promise<{ result: unknown }>`
39. Throw `CLIError` with message "Unknown command" when a subcommand is specified but not found
40. Throw `CLIError` with message matching `/Cannot specify both 'run' and 'default'/` when both `run` and `default` are defined
41. Throw `CLIError` with message matching `/Default sub command .* not found in subCommands/` when `default` references non-existent subcommand
42. Execute `setup` hook before running command logic
43. Execute `cleanup` hook after running command logic
44. Parse arguments using `parseArgs` with the command's `ArgsDef`
45. If command has `subCommands` and no `run` method, resolve and execute the appropriate subcommand
46. If command has `default` subcommand and no explicit subcommand in args, execute the default subcommand
47. If command has `run` method, execute it with parsed arguments and context
48. Return object with `result` property containing the return value from `run` hook

### Subcommand Resolution (command.ts)
49. Implement `resolveSubCommand(cmd: CommandDef<T>, rawArgs: string[], parent?: CommandDef<T>)` as async function
50. Return tuple `[CommandDef<T>, CommandDef<T>?]` where first element is resolved subcommand and second is parent
51. Match subcommand by direct key first, then by alias (prefer exact match over alias)
52. Support single string alias and array of aliases in `meta.alias`
53. Handle parent command's string/enum arguments that consume tokens before subcommand name
54. Skip boolean arguments when looking for subcommand (they don't consume next token)
55. Recursively resolve nested subcommands

### Main Entry Point (main.ts)
56. Define `RunMainOptions` interface with optional properties: `rawArgs?: string[]`, `showUsage?: typeof _showUsage`
57. Implement `runMain(cmd: CommandDef<T>, opts: RunMainOptions = {})` as async function
58. Check for `--help` or `-h` flags and show usage if present (unless user defined `help` arg)
59. Check for `--version` or `-v` flags and show version if present (unless user defined `version` arg)
60. Show usage instead of version if version is not specified but `--version` flag is used
61. Support custom `showUsage` function via `RunMainOptions.showUsage`
62. Default `rawArgs` to empty array if not provided
63. Call `runCommand` with parsed options
64. Implement `createMain(cmd: CommandDef<T>)` to return a function that calls `runMain` with the command

### Usage Rendering (usage.ts)
65. Implement `showUsage(cmd: CommandDef<T>, parent?: CommandDef<T>)` as async function that logs rendered usage
66. Implement `renderUsage(cmd: CommandDef<T>, parent?: CommandDef<T>)` as async function returning formatted usage string
67. Include command name and description in usage output
68. List all arguments with their types and descriptions
69. List all subcommands with their names, aliases, and descriptions
70. Format subcommand aliases as comma-separated list (e.g., "install, i, add")
71. Hide subcommands marked with `hidden: true`
72. Use color functions for formatting (bold for headers, etc.)
73. Use `formatLineColumns` for aligned output

### Plugin System (plugin.ts)
74. Define `CittyPlugin` as object with optional properties for extending commands
75. Define `Resolvable<T>` as `T | (() => T) | (() => Promise<T>)`
76. Implement `defineCittyPlugin(plugin: Resolvable<CittyPlugin>)` to return the plugin as-is (identity function)
77. Implement `resolvePlugins(plugins: Resolvable<CittyPlugin>[])` as async function
78. Resolve each plugin by calling if function, awaiting if promise
79. Return array of resolved `CittyPlugin` objects

### Type Definitions (types.ts)
80. Define `Awaitable<T>` as `T | Promise<T>`
81. Export all type definitions for public API

### Module Exports (index.ts)
82. Export all public functions, classes, and types from appropriate modules
83. Ensure all required tested symbols are exported

### Implementation Details
84. Use `process.argv.slice(2)` as default raw args in `runMain` when not provided
85. Implement proper async/await handling throughout for all async operations
86. Preserve argument order and handle edge cases (empty strings, special characters)
87. Support both `--flag=value` and `--flag value` syntax for arguments
88. Implement proper error messages that match test expectations exactly

## Required Tested Symbols

The hidden tests import or access every symbol listed here. Implement all of them.

- `function parseRawArgs(args: string[] = [],
  opts: ParseOptions = {},): Argv<T>`
- `ParseOptions.boolean: string[]`
- `ParseOptions.string: string[]`
- `ParseOptions.alias: Record<string, string[]>`
- `ParseOptions.default: Record<string, any>`
- `class CLIError`
- `CLIError.code: string | undefined`
- `function toArray(val: any)`
- `function formatLineColumns(lines: string[][], linePrefix = "")`
- `function resolveValue(input: Resolvable<T>): T | Promise<T>`
- `function parseArgs(rawArgs: string[],
  argsDef: ArgsDef,): ParsedArgs<T>`
- `function defineCommand(def: CommandDef<T>,): CommandDef<T>`
- `async function runCommand(cmd: CommandDef<T>,
  opts: RunCommandOptions,): Promise<{ result: unknown }>`
- `async function resolveSubCommand(cmd: CommandDef<T>,
  rawArgs: string[],
  parent?: CommandDef<T>,): Promise<[CommandDef<T>, CommandDef<T>?]>`
- `RunCommandOptions.rawArgs: string[]`
- `RunCommandOptions.showUsage: boolean`
- `async function runMain(cmd: CommandDef<T>,
  opts: RunMainOptions = {},)`
- `function createMain(cmd: CommandDef<T>,): (opts?: RunMainOptions) => Promise<void>`
- `RunMainOptions.rawArgs: string[]`
- `RunMainOptions.showUsage: typeof _showUsage`
- `function defineCittyPlugin(plugin: Resolvable<CittyPlugin>): Resolvable<CittyPlugin>`
- `async function resolvePlugins(plugins: Resolvable<CittyPlugin>[]): Promise<CittyPlugin[]>`
- `interface ArgsDef`
- `CommandMeta.name: string`
- `CommandMeta.version: string`
- `CommandMeta.description: string`
- `CommandMeta.hidden: boolean`
- `CommandMeta.alias: string | string[]`
- `interface Resolvable`
- `async function showUsage(cmd: CommandDef<T>,
  parent?: CommandDef<T>,)`
- `async function renderUsage(cmd: CommandDef<T>,
  parent?: CommandDef<T>,)`

## Environment Configuration

### Runtime

Node.js (TypeScript)

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Do NOT run `npm install`, `npx`, or any package manager commands. All dependencies and testing infrastructure are pre-configured and handled automatically.
- Your shell may start in a different current directory, so use absolute paths.
- Hidden tests import the solution from: `_color.ts`, `_parser.ts`, `_utils.ts`, `args.ts`, `command.ts`, `index.ts`, `main.ts`, `plugin.ts`, `types.ts`, `usage.ts`.

### Dependencies

No runtime dependencies were detected.


## Project Directory Structure

```
workspace/
├── package.json
├── tsconfig.json
├── _color.ts
├── _parser.ts
├── _utils.ts
├── args.ts
├── command.ts
├── index.ts
├── main.ts
├── plugin.ts
├── types.ts
├── usage.ts
```

## API Usage Guide

### 1. Module Import

```typescript
import { bold, red, green, yellow, blue, magenta, cyan, gray, underline, ParseOptions, parseRawArgs, CLIError, toArray, formatLineColumns, resolveValue, parseArgs, resolveArgs, RunCommandOptions, defineCommand, runCommand, resolveSubCommand, RunMainOptions, runMain, createMain, defineCittyPlugin, resolvePlugins, ArgType, _ArgDef, BooleanArgDef, StringArgDef, EnumArgDef, PositionalArgDef, ArgDef, ArgsDef, Arg, ParsedArgs, CommandMeta, SubCommandsDef, CommandDef, CommandContext, CittyPlugin, Awaitable, Resolvable, showUsage, renderUsage } from './_color';
```

### 2. `CLIError` Class

**Extends:** `Error`

```typescript
class CLIError extends Error {
}
```

**Class Variables:**
- `code: string | undefined`


```typescript
constructor(message: string, code?: string)
```

**Parameters:**
- `message: string`
- `code: string`

### 3. `ParseOptions` Interface

```typescript
export interface ParseOptions {
  boolean?: string[];
  string?: string[];
  alias?: Record<string, string[]>;
  default?: Record<string, any>;
}
```

**Members:**
- `boolean: string[]`
- `string: string[]`
- `alias: Record<string, string[]>`
- `default: Record<string, any>`

### 4. `RunCommandOptions` Interface

```typescript
export interface RunCommandOptions {
  rawArgs?: string[];
  data?: any;
  showUsage?: boolean;
}
```

**Members:**
- `rawArgs: string[]`
- `data: any`
- `showUsage: boolean`

### 5. `RunMainOptions` Interface

```typescript
export interface RunMainOptions {
  rawArgs?: string[];
  showUsage?: typeof _showUsage;
}
```

**Members:**
- `rawArgs: string[]`
- `showUsage: typeof _showUsage`

### 6. `ArgType` Type Alias

```typescript
export type ArgType = ...;
```

### 7. `_ArgDef` Type Alias

```typescript
export type _ArgDef = ...;
```

### 8. `BooleanArgDef` Type Alias

```typescript
export type BooleanArgDef = ...;
```

### 9. `StringArgDef` Type Alias

```typescript
export type StringArgDef = ...;
```

### 10. `EnumArgDef` Type Alias

```typescript
export type EnumArgDef = ...;
```

### 11. `PositionalArgDef` Type Alias

```typescript
export type PositionalArgDef = ...;
```

### 12. `ArgDef` Type Alias

```typescript
export type ArgDef = ...;
```

### 13. `ArgsDef` Type Alias

```typescript
export type ArgsDef = ...;
```

### 14. `Arg` Type Alias

```typescript
export type Arg = ...;
```

### 15. `ParsedArgs` Type Alias

```typescript
export type ParsedArgs = ...;
```

### 16. `CommandMeta` Interface

```typescript
export interface CommandMeta {
  name?: string;
  version?: string;
  description?: string;
  hidden?: boolean;
  alias?: string | string[];
}
```

**Members:**
- `name: string`
- `version: string`
- `description: string`
- `hidden: boolean`
- `alias: string | string[]`

### 17. `SubCommandsDef` Type Alias

```typescript
export type SubCommandsDef = ...;
```

### 18. `CommandDef` Type Alias

```typescript
export type CommandDef = ...;
```

### 19. `CommandContext` Type Alias

```typescript
export type CommandContext = ...;
```

### 20. `CittyPlugin` Type Alias

```typescript
export type CittyPlugin = ...;
```

### 21. `Awaitable` Type Alias

```typescript
export type Awaitable = ...;
```

### 22. `Resolvable` Type Alias

```typescript
export type Resolvable = ...;
```

### 23. `parseRawArgs` Function

```typescript
export function parseRawArgs(args: string[] = [],
  opts: ParseOptions = {},): Argv<T>
```

**Parameters:**
- `args: string[] = []`
- `opts: ParseOptions = {}`

**Returns:** `Argv<T>`

### 24. `toArray` Function

```typescript
export function toArray(val: any)
```

**Parameters:**
- `val: any`

### 25. `formatLineColumns` Function

```typescript
export function formatLineColumns(lines: string[][], linePrefix = "")
```

**Parameters:**
- `lines: string[][]`
- `linePrefix = ""`

### 26. `resolveValue` Function

```typescript
export function resolveValue(input: Resolvable<T>): T | Promise<T>
```

**Parameters:**
- `input: Resolvable<T>`

**Returns:** `T | Promise<T>`

### 27. `parseArgs` Function

```typescript
export function parseArgs(rawArgs: string[],
  argsDef: ArgsDef,): ParsedArgs<T>
```

**Parameters:**
- `rawArgs: string[]`
- `argsDef: ArgsDef`

**Returns:** `ParsedArgs<T>`

### 28. `resolveArgs` Function

```typescript
export function resolveArgs(argsDef: ArgsDef): Arg[]
```

**Parameters:**
- `argsDef: ArgsDef`

**Returns:** `Arg[]`

### 29. `defineCommand` Function

```typescript
export function defineCommand(def: CommandDef<T>,): CommandDef<T>
```

**Parameters:**
- `def: CommandDef<T>`

**Returns:** `CommandDef<T>`

### 30. `runCommand` Function

```typescript
export async function runCommand(cmd: CommandDef<T>,
  opts: RunCommandOptions,): Promise<{ result: unknown }>
```

**Parameters:**
- `cmd: CommandDef<T>`
- `opts: RunCommandOptions`

**Returns:** `Promise<{ result: unknown }>`

### 31. `resolveSubCommand` Function

```typescript
export async function resolveSubCommand(cmd: CommandDef<T>,
  rawArgs: string[],
  parent?: CommandDef<T>,): Promise<[CommandDef<T>, CommandDef<T>?]>
```

**Parameters:**
- `cmd: CommandDef<T>`
- `rawArgs: string[]`
- `parent: CommandDef<T>`

**Returns:** `Promise<[CommandDef<T>, CommandDef<T>?]>`

### 32. `runMain` Function

```typescript
export async function runMain(cmd: CommandDef<T>,
  opts: RunMainOptions = {},)
```

**Parameters:**
- `cmd: CommandDef<T>`
- `opts: RunMainOptions = {}`

### 33. `createMain` Function

```typescript
export function createMain(cmd: CommandDef<T>,): (opts?: RunMainOptions) => Promise<void>
```

**Parameters:**
- `cmd: CommandDef<T>`

**Returns:** `(opts?: RunMainOptions) => Promise<void>`

### 34. `defineCittyPlugin` Function

```typescript
export function defineCittyPlugin(plugin: Resolvable<CittyPlugin>): Resolvable<CittyPlugin>
```

**Parameters:**
- `plugin: Resolvable<CittyPlugin>`

**Returns:** `Resolvable<CittyPlugin>`

### 35. `resolvePlugins` Function

```typescript
export async function resolvePlugins(plugins: Resolvable<CittyPlugin>[]): Promise<CittyPlugin[]>
```

**Parameters:**
- `plugins: Resolvable<CittyPlugin>[]`

**Returns:** `Promise<CittyPlugin[]>`

### 36. `showUsage` Function

```typescript
export async function showUsage(cmd: CommandDef<T>,
  parent?: CommandDef<T>,)
```

**Parameters:**
- `cmd: CommandDef<T>`
- `parent: CommandDef<T>`

### 37. `renderUsage` Function

```typescript
export async function renderUsage(cmd: CommandDef<T>,
  parent?: CommandDef<T>,)
```

**Parameters:**
- `cmd: CommandDef<T>`
- `parent: CommandDef<T>`

### 38. Constants and Configuration

```typescript
export const bold = /* @__PURE__ */ _c(1, 22);
export const red = /* @__PURE__ */ _c(31);
export const green = /* @__PURE__ */ _c(32);
export const yellow = /* @__PURE__ */ _c(33);
export const blue = /* @__PURE__ */ _c(34);
export const magenta = /* @__PURE__ */ _c(35);
export const cyan = /* @__PURE__ */ _c(36);
export const gray = /* @__PURE__ */ _c(90);
export const underline = /* @__PURE__ */ _c(4, 24);
```

## Implementation Notes

### Note 1: Argument Parsing with Case Conversion
The `parseArgs()` function normalizes argument names between camelCase and kebab-case formats. When an `ArgsDef` defines a key as `"user-name"`, it accepts `--userName` from raw arguments, and vice versa. The parsed result uses the key name as defined in the definition object. The `parseRawArgs()` function provides lower-level parsing with `ParseOptions` supporting `string`, `boolean`, `alias`, and `default` fields.

### Note 2: Boolean Argument Coercion
Boolean arguments accept explicit string values `"true"` and `"false"` which are coerced to their boolean equivalents. The string `"true"` becomes `true` and `"false"` becomes `false`. This coercion respects explicit `--flag=false` syntax even when a default value of `true` is specified, allowing defaults to be overridden.

### Note 3: String Arguments Without Values
When a string-type argument is provided without a value (e.g., `--nightly` with no following value), it defaults to an empty string `""` rather than `true` or `undefined`. This distinguishes string arguments from boolean flags.

### Note 4: Command Definition and Execution
Commands are defined using `defineCommand()` which accepts a `CommandDef` object. The `runCommand()` function executes a command with `RunCommandOptions` including optional `rawArgs`, `data`, and `showUsage` flag. The `runMain()` function is the primary entry point that handles built-in flags (`--help`, `-h`, `--version`, `-v`) and delegates to `runCommand()`.

### Note 5: Built-in Help and Version Flags
The `--help` and `-h` flags trigger usage display via `renderUsage()`. The `--version` and `-v` flags display the version from `meta.version`. If no version is specified, usage is shown instead with an error message. A custom `showUsage` function can be provided to `runMain()` to override default usage rendering.

### Note 6: Built-in Flag Conflicts with User Arguments
User-defined arguments can claim the `-h` and `-v` short aliases. When `-h` is claimed by a user argument (e.g., `--host`), the full `--help` flag still works. Similarly, when `-v` is claimed (e.g., `--verbose`), the full `--version` flag still works. If a user defines a `help` or `version` argument directly, the built-in behavior is disabled entirely for that flag.

### Note 7: Sub-command Resolution and Aliases
Sub-commands are resolved by key name first, then by alias. The `meta.alias` field accepts either a single string or an array of strings. Aliases are checked after direct key matches, so a sub-command key `"i"` takes precedence over another sub-command's alias `"i"`. The `resolveSubCommand()` function returns a tuple of `[subCommand, parentCommand?]`.

### Note 8: Sub-command Aliases in Usage Output
When rendering usage with `renderUsage()`, sub-command aliases are displayed alongside the command name in the format `"name, alias1, alias2"`. Both single-string and array-of-strings alias formats are supported.

### Note 9: Nested Sub-commands and Parent Arguments
Parent commands can have arguments that are parsed before sub-command resolution. String, enum, and positional arguments in the parent consume tokens appropriately. Boolean arguments in the parent do not consume the next token, allowing it to be interpreted as a sub-command name. Parent arguments can use aliases (e.g., `-n` for `--name`), and the `=` syntax (e.g., `--name=value`) is supported.

### Note 10: Default Sub-command Behavior
A command can specify a `default` sub-command key. When no sub-command is explicitly provided in `rawArgs`, the default is invoked. If both `default` and `run` are specified on the same command, an error is thrown. If `default` references a non-existent sub-command key, an error is thrown. Remaining arguments after the default sub-command name are passed to that sub-command.

### Note 11: Command Lifecycle Hooks
Commands support `setup()`, `run()`, and `cleanup()` lifecycle methods. These are called in sequence during command execution, receiving a context object with parsed `args`.

### Note 12: Async Meta and Plugins
The `meta` field in `CommandDef` can be either a synchronous object or an async function returning a promise. The `defineCittyPlugin()` and `resolvePlugins()` functions support `Resolvable<CittyPlugin>` types, allowing plugins to be defined as promises or functions.

### Note 13: createMain Factory Function
The `createMain()` function accepts a `CommandDef` and returns a function that accepts optional `RunMainOptions`. This allows pre-defining a command and creating a reusable entry point function.

### Note 14: Positional Arguments
Arguments with `type: "positional"` are captured in the parsed args object by their defined name. They are distinct from the `_` array which collects unmatched tokens.

### Note 15: Enum Arguments
Enum-type arguments accept an `options` array defining allowed values. They consume the next token as their value, similar to string arguments, and are used in parent-child command resolution.