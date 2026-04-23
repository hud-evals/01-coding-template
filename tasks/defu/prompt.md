# defu

## Overview

**defu** is a lightweight TypeScript utility library comprising 200 lines of code organized across 3 source modules. The library exports 2 module-level functions and contains no class definitions, following a functional programming paradigm. Built with CommonJS module system support, defu is designed for minimal overhead while providing focused utility functionality. The codebase is validated through a comprehensive test suite executed via vitest, ensuring reliability across its compact implementation.

The library's architecture emphasizes simplicity and composability through pure functions rather than object-oriented abstractions. With only 2 exported functions distributed across 3 modules, defu maintains a narrow API surface that prioritizes clarity and ease of integration. The CommonJS module system ensures broad compatibility with existing Node.js ecosystems and build tooling that may not yet support ES modules. All functionality is implemented at the module level, allowing direct function imports without instantiation overhead.

Testing infrastructure leverages vitest as the test runner, providing fast, modern test execution with TypeScript support out of the box. The 200-line implementation size indicates a focused library designed to solve specific problems without unnecessary abstraction layers or feature bloat, making it suitable for projects requiring lean dependencies with predictable behavior.

## Natural Language Instructions

### Implementation Constraints
- All source files must be created in `/home/ubuntu/workspace` with no subdirectories
- Do NOT run any package manager commands; dependencies are pre-configured
- Write all code in TypeScript with strict type safety
- Maintain exact function signatures as specified in the EXACT API section
- The library uses CommonJS module system
- Total implementation should be approximately 200 lines across 3 modules

### Behavioral Requirements

1. **isPlainObject function** must return `true` for plain objects (including `{}`, objects with properties, Proxies wrapping plain objects) and `false` for all non-plain-object values (primitives, functions, null, custom class instances, Date, RegExp, Arrays, etc.)

2. **createDefu function** must accept an optional `Merger` callback parameter and return a `DefuFunction` that merges objects with the following behavior:
   - Takes multiple object arguments and merges them from right to left (defaults first, then overrides)
   - Only copies properties from defaults if they don't exist or are `null` in the target object
   - Recursively merges nested plain objects
   - Concatenates arrays by default (unless custom merger or arrayFn overrides this)
   - Avoids merging objects with custom constructors (Date, RegExp, custom classes, etc.)
   - Protects against prototype pollution by ignoring `constructor` and `__proto__` keys
   - Ignores inherited enumerable properties from Object.prototype
   - Handles non-object arguments gracefully by treating them as empty objects

3. **defu constant** must be the result of calling `createDefu()` with no arguments, typed as a `DefuInstance`

4. **DefuInstance interface** must have optional properties:
   - `source?: Source | IgnoredInput` - stores the source object for the instance
   - `fn?: DefuFn` - a custom function merger for handling specific properties
   - `arrayFn?: DefuFn` - a custom function merger specifically for array properties

5. **defuFn constant** must be a pre-configured instance created via `createDefu()` with a merger that treats function values as "ignored" inputs—when a property value is a function in the first argument, it takes precedence and the corresponding default is skipped

6. **defuArrayFn constant** must be a pre-configured instance created via `createDefu()` with a merger that treats function values as "ignored" inputs specifically for array handling—functions in the first argument take precedence over array defaults

7. **Merger callback type** must accept parameters `(obj: any, key: string, val: any, namespace?: string): boolean | void` where:
   - `obj` is the target object being merged into
   - `key` is the property name
   - `val` is the value from the defaults
   - `namespace` is the current nested path (dot-separated)
   - Return `true` to indicate the merger handled the merge, `false`/`undefined` to use default behavior

8. **DefuFn type** must be a function signature `(obj: any, key: string, val: any) => boolean | void` for custom property merging

9. **Input type** must represent valid objects that can be merged (plain objects)

10. **IgnoredInput type** must represent values that should be skipped during merging (non-plain-objects, null, undefined, etc.)

11. **MergeArrays type** must represent the array concatenation behavior in the type system

12. **Merge type** must represent the recursive object merging behavior in the type system

13. **Type inference** must correctly handle:
    - Union types when merging objects with different property types
    - Array element type unions when concatenating arrays
    - Nested object merging with proper type composition
    - Multiple argument merging with correct type accumulation

14. **Namespace tracking** in custom mergers must build dot-separated paths for nested objects (e.g., "foo.bar.baz" for deeply nested properties)

15. **Array handling** must concatenate arrays by default, but respect custom `arrayFn` mergers if provided on the DefuInstance

16. **Null handling** must treat `null` values as "missing" and fill them in from defaults, matching the behavior of `undefined`

17. **Non-object handling** must gracefully ignore non-object arguments in multi-argument merge chains, treating them as if they weren't passed

## Required Tested Symbols

The hidden tests import or access every symbol listed here. Implement all of them.

- `function isPlainObject(value: unknown): boolean`
- `function createDefu(merger?: Merger): DefuFunction`
- `defu`
- `defuFn`
- `defuArrayFn`
- `DefuInstance.fn: DefuFn`

## Environment Configuration

### Runtime

Node.js (TypeScript)

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Do NOT run `npm install`, `npx`, or any package manager commands. All dependencies and testing infrastructure are pre-configured and handled automatically.
- Your shell may start in a different current directory, so use absolute paths.
- Hidden tests import the solution from: `_utils.ts`, `defu.ts`, `types.ts`.

### Dependencies

No runtime dependencies were detected.


## Project Directory Structure

```
workspace/
├── package.json
├── tsconfig.json
├── _utils.ts
├── defu.ts
├── types.ts
```

## API Usage Guide

### 1. Module Import

```typescript
import { isPlainObject, createDefu, defu, defuFn, defuArrayFn, Input, IgnoredInput, Merger, DefuFn, DefuInstance, MergeArrays, Merge } from './_utils';
```

### 2. `Input` Type Alias

```typescript
export type Input = ...;
```

### 3. `IgnoredInput` Type Alias

```typescript
export type IgnoredInput = ...;
```

### 4. `Merger` Type Alias

```typescript
export type Merger = ...;
```

### 5. `DefuFn` Type Alias

```typescript
export type DefuFn = ...;
```

### 6. `DefuInstance` Interface

```typescript
export interface DefuInstance {
  source?: Source | IgnoredInput;
  fn?: DefuFn;
  arrayFn?: DefuFn;
}
```

**Members:**
- `source: Source | IgnoredInput`
- `fn: DefuFn`
- `arrayFn: DefuFn`

### 7. `MergeArrays` Type Alias

```typescript
export type MergeArrays = ...;
```

### 8. `Merge` Type Alias

```typescript
export type Merge = ...;
```

### 9. `isPlainObject` Function

```typescript
export function isPlainObject(value: unknown): boolean
```

**Parameters:**
- `value: unknown`

**Returns:** `boolean`

### 10. `createDefu` Function

```typescript
export function createDefu(merger?: Merger): DefuFunction
```

**Parameters:**
- `merger: Merger`

**Returns:** `DefuFunction`

### 11. Constants and Configuration

```typescript
export const defu = createDefu() as DefuInstance;
export const defuFn = createDefu((object, key, currentValue) => { if (object[key] !== undefined && typeof currentValue === "function") { object[key] = currentValue(object[key]); return true; } });
export const defuArrayFn = createDefu((object, key, currentValue) => { if (Array.isArray(object[key]) && typeof currentValue === "function") { object[key] = currentValue(object[key]); return true; } });
```

## Implementation Notes

### Note 1: Core Merge Behavior
`defu()` performs a shallow-to-deep recursive merge where properties from the first object take precedence. Only missing properties (or properties with `null` or `undefined` values) are filled in from subsequent objects. The function accepts multiple objects as arguments and merges them left-to-right, with leftmost values winning.

### Note 2: Array Concatenation
By default, `defu()` concatenates arrays rather than replacing them. When merging objects with array properties, arrays from all objects are combined into a single array in the result.

### Note 3: Plain Object Detection
`isPlainObject()` returns `true` only for plain objects (including Proxies wrapping plain objects) and `false` for all primitives, functions, `null`, and objects with custom constructors (like `Date`, `RegExp`, or user-defined classes).

### Note 4: Non-Plain Object Handling
Objects with custom constructors (e.g., `Date`, `RegExp`, class instances) are treated as atomic values and are not recursively merged. The first object's value is preserved without attempting to merge properties.

### Note 5: Prototype Pollution Protection
The implementation protects against prototype pollution by ignoring `constructor` and `__proto__` properties during merging. Inherited enumerable properties from `Object.prototype` are also ignored.

### Note 6: Non-Object Arguments
Non-object arguments (primitives, `null`, `undefined`, functions) are silently skipped during multi-argument merges. Only plain objects contribute to the final result.

### Note 7: Custom Merger Functions
`createDefu(merger)` accepts an optional `Merger` callback that intercepts property assignments. The callback receives `(object, key, currentValue, namespace?)` and returns `true` to indicate the property was handled, preventing default merge behavior. The `namespace` parameter tracks the nested path (e.g., `"foo.bar"`).

### Note 8: defuFn Behavior
`defuFn` is a pre-configured instance that treats function values specially: if a property in the first object is a function and the corresponding property in defaults is not a function, the function is called with the default value as an argument, and the result replaces the property.

### Note 9: defuArrayFn Behavior
`defuArrayFn` is a pre-configured instance that treats function values specially only when the corresponding property in defaults is an array. If so, the function is called with the array as an argument, and the result replaces the property.

### Note 10: Type Inference
The TypeScript types correctly infer union types for properties that differ across merged objects. Multi-argument merges produce types that combine all property types from all input objects, allowing partial objects and `undefined` in the merge chain.