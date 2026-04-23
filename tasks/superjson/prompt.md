# superjson

## Overview

**superjson** is a TypeScript library comprising 2,995 lines of code organized across 19 source modules, designed to provide robust serialization and deserialization capabilities. The library implements 5 core classes and exports 36 module-level functions, offering a comprehensive API surface for handling complex data transformations. Built with TypeScript for full type safety, superjson leverages the modern ES module system for dependency management and code organization, enabling seamless integration into contemporary JavaScript and TypeScript projects.

The library's architecture is structured around a modular design pattern, with functionality distributed across 19 discrete source modules that each handle specific aspects of the serialization pipeline. This modular approach facilitates maintainability, testability, and allows consumers to understand and extend individual components without navigating monolithic code structures. The 5 primary classes serve as the foundational abstractions for core operations, while the 36 module-level functions provide both high-level convenience APIs and lower-level utilities for fine-grained control over serialization behavior.

Development and quality assurance are supported through vitest, a modern test runner optimized for TypeScript and ES module environments. This testing infrastructure ensures code reliability and enables rapid iteration during development cycles. The combination of TypeScript's static type system, modular organization, and comprehensive test coverage positions superjson as a production-ready solution for applications requiring sophisticated data serialization workflows.

# Natural Language Instructions

## Implementation Constraints

- All source files must be created in `/home/ubuntu/workspace` with no subdirectories unless explicitly required
- Do NOT run any package manager commands; all dependencies are pre-configured
- Use exact function signatures provided; do not modify parameter names, types, defaults, or return types
- Implement all required tested symbols including private helpers (prefixed with underscore)
- Write in TypeScript with proper type annotations
- Follow the test evidence to understand expected behavior
- Maintain module exports exactly as specified in the EXACT API section

## Behavioral Requirements

### Core Type System & Utilities

1. Create `types.ts` defining all type aliases and interfaces:
   - `TypedArrayConstructor` and `TypedArray` types for typed array support
   - `Class` interface for class constructors
   - `PrimitiveJSONValue` and `JSONValue` types for JSON serialization
   - `SuperJSONValue` and `SuperJSONResult` interfaces with properties: `json`, `meta`, `values`, `referentialEqualities`, `v`
   - `JSONArray` and `JSONObject` interfaces
   - `SerializableJSONValue` type
   - `SuperJSONArray` and `SuperJSONObject` interfaces
   - `StringifiedPath` type for path stringification
   - `MinimisedTree<T>` generic type for tree structures
   - `ReferentialEqualityAnnotations` type for tracking object references
   - `PrimitiveTypeAnnotation` and `TypeAnnotation` types for type metadata
   - `Path` type for object paths

2. Create `util.ts` with utility functions:
   - `find(record, predicate)` - finds first matching value in record
   - `forEach(record, run)` - iterates over record key-value pairs
   - `includes(arr, value)` - checks if array includes value
   - `findArr(record, predicate)` - finds first matching value in array

3. Create `is.ts` with type guard functions:
   - `isUndefined(payload)` - returns true if payload is undefined
   - `isNull(payload)` - returns true if payload is null
   - `isPlainObject(payload)` - returns true if plain object (including null-prototype objects)
   - `isEmptyObject(payload)` - returns true if empty plain object
   - `isArray(payload)` - returns true if array
   - `isString(payload)` - returns true if string
   - `isNumber(payload)` - returns true if number (excluding NaN)
   - `isBoolean(payload)` - returns true if boolean
   - `isRegExp(payload)` - returns true if RegExp
   - `isMap(payload)` - returns true if Map
   - `isSet(payload)` - returns true if Set
   - `isSymbol(payload)` - returns true if symbol
   - `isDate(payload)` - returns true if valid Date (not Invalid Date)
   - `isError(payload)` - returns true if Error instance
   - `isNaNValue(payload)` - returns true if NaN
   - `isPrimitive(payload)` - returns true if boolean, null, undefined, number, string, or symbol
   - `isBigint(payload)` - returns true if bigint
   - `isInfinite(payload)` - returns true if Infinity or -Infinity
   - `isTypedArray(payload)` - returns true if typed array (Int8Array, Uint8Array, etc.)
   - `isURL(payload)` - returns true if URL instance

### Path Stringification

4. Create `pathstringifier.ts` with path handling:
   - `escapeKey(key)` - escapes dots in keys by prefixing with backslash
   - `stringifyPath(path)` - converts path array to escaped string representation
   - `parsePath(string, legacyPaths)` - parses escaped string back to path array
     - When `legacyPaths` is true, use legacy escape handling
     - When false, use strict escape validation (reject invalid escapes like `\a`)
     - Handle double backslashes (`\\`) as literal backslashes

### Registry System

5. Create `registry.ts` with generic Registry class:
   - Constructor accepts `generateIdentifier` function
   - `register(value, identifier?)` - registers value with auto-generated or provided identifier
   - `clear()` - clears all registered values
   - `getIdentifier(value)` - returns identifier for registered value
   - `getValue(identifier)` - returns value for identifier
   - Uses internal `kv` DoubleIndexedKV for bidirectional lookup

6. Create `class-registry.ts` with ClassRegistry extending Registry:
   - Constructor initializes with class name generator
   - `register(value, options?)` - accepts Class and optional RegisterOptions or string identifier
   - `RegisterOptions` interface with `identifier?: string` and `allowProps?: string[]`
   - `getAllowedProps(value)` - returns allowed property names for class or undefined
   - Stores `classToAllowedProps` mapping for property filtering

7. Create `custom-transformer-registry.ts` with CustomTransformerRegistry:
   - `CustomTransfomer<I, O>` interface with:
     - `name?: string` - transformer identifier
     - `isApplicable?: (v: any) => v is I` - type guard for applicability
     - `serialize?: (v: I) => O` - converts value to serializable form
     - `deserialize?: (v: O) => I` - converts back from serialized form
   - `transfomers` record storing transformers by name
   - `register(transformer)` - registers custom transformer
   - `findApplicable(v)` - finds first applicable transformer for value
   - `findByName(name)` - finds transformer by name

8. Create `double-indexed-kv.ts` with DoubleIndexedKV class:
   - Generic class with `K` and `V` type parameters
   - `keyToValue` and `valueToKey` maps for bidirectional lookup
   - `set(key, value)` - stores bidirectional mapping
   - `getByKey(key)` - retrieves value by key
   - `getByValue(value)` - retrieves key by value
   - `clear()` - clears all mappings

### Value Access & Transformation

9. Create `accessDeep.ts` with deep object access:
   - `getDeep(object, path)` - retrieves value at path in nested object/array/map/set
   - `setDeep(object, path, mapper)` - sets value at path using mapper function
     - Supports nested Maps, Sets, arrays, and plain objects
     - Mapper receives current value and returns new value
     - Modifies object in place

10. Create `transformer.ts` with value transformation:
    - `isInstanceOfRegisteredClass(potentialClass, superJson)` - checks if value is registered class instance
    - `transformValue(value, superJson)` - transforms value to serializable form with type annotation
      - Returns `{ value, type }` or undefined if no transformation needed
      - Handles custom transformers, registered classes, special types (Date, Map, Set, etc.)
    - `untransformValue(json, type, superJson)` - reverses transformation using type annotation

### Path Annotation & Application

11. Create `plainer.ts` with annotation application:
    - `applyValueAnnotations(plain, annotations, version, superJson)` - applies type annotations to deserialized values
      - Reconstructs typed values (Date, Map, Set, BigInt, etc.) from plain JSON
      - Uses version for backward compatibility
      - Recursively processes nested structures
    - `applyReferentialEqualityAnnotations(plain, annotations, version)` - applies referential equality metadata
      - Restores object references marked as equal
      - Prevents prototype pollution by rejecting `__proto__`, `prototype`, `constructor` in paths
    - `generateReferentialEqualityAnnotations(identities, dedupe)` - generates referential equality metadata
      - Tracks which objects are identical references
      - Returns undefined if no referential equalities or dedupe is false

### Tree Walking & Serialization

12. Create `walker.ts` with tree walking:
    - `walker(object, identities, superJson, dedupe, path, objectsInThisPath, seenObjects)` - recursively walks object tree
      - Returns `{ transformedValue, annotations }` result
      - Tracks object identities in `identities` Map for deduplication
      - Prevents circular reference infinite loops using `seenObjects`
      - Transforms values using `transformValue`
      - Builds annotation tree for type reconstruction
      - Handles Maps and Sets with special annotation format
      - When dedupe is true, tracks referential equalities

### Main SuperJSON Class

13. Create `index.ts` with SuperJSON class and module exports:
    - SuperJSON class with:
      - `dedupe: boolean` property (default false)
      - `classRegistry: ClassRegistry` instance
      - `symbolRegistry: Registry<Symbol>` instance
      - `customTransformerRegistry: CustomTransformerRegistry` instance
      - `allowedErrorProps: string[]` array
      - `defaultInstance` static property (singleton instance)
      - Constructor accepting `{ dedupe?: boolean }` options
    
    - Instance methods:
      - `serialize(object)` - converts SuperJSONValue to SuperJSONResult
        - Calls walker to transform object tree
        - Returns result with json, meta (containing values and referentialEqualities), and v (version)
        - Omits meta if no transformations needed
      - `deserialize(payload, options?)` - converts SuperJSONResult back to original value
        - Accepts optional `{ inPlace?: boolean }` options
        - Applies value annotations and referential equality annotations
        - Returns reconstructed value
      - `stringify(object)` - serializes to JSON string (calls serialize then JSON.stringify)
      - `parse(string)` - deserializes from JSON string (calls JSON.parse then deserialize)
      - `registerClass(v, options?)` - registers class for serialization
        - Accepts Class and optional RegisterOptions or string identifier
        - Stores in classRegistry
      - `registerSymbol(v, identifier?)` - registers Symbol with optional identifier
        - Stores in symbolRegistry
      - `registerCustom(transformer, name)` - registers custom transformer
        - Accepts transformer without name property and name string
        - Stores in customTransformerRegistry
      - `allowErrorProps(...props)` - adds property names to allowedErrorProps
        - Allows those properties to be serialized on Error instances
    
    - Static methods bound to defaultInstance:
      - `serialize`, `deserialize`, `stringify`, `parse`
      - `registerClass`, `registerSymbol`, `registerCustom`, `allowErrorProps`
    
    - Module-level exports:
      - `serialize`, `deserialize`, `stringify`, `parse` functions
      - `registerClass`, `registerCustom`, `registerSymbol`, `allowErrorProps` functions
      - All type definitions and interfaces

### Test Files

14. Create test files matching the module structure:
    - `accessDeep.test.ts` - tests for getDeep and setDeep
    - `is.test.ts` - tests for type guards
    - `pathstringifier.test.ts` - tests for path escaping and parsing
    - `registry.test.ts` - tests for Registry class
    - `transformer.test.ts` - tests for value transformation
    - `index.test.ts` - tests for SuperJSON class and integration
    - `plainer.spec.ts` - tests for annotation application

## Implementation Order

1. Start with `types.ts` - all type definitions
2. Create `util.ts` - utility functions
3. Create `is.ts` - type guards (depends on types)
4. Create `pathstringifier.ts` - path handling
5. Create `double-indexed-kv.ts` - bidirectional map
6. Create `registry.ts` - generic registry (depends on double-indexed-kv)
7. Create `class-registry.ts` - class registry (depends on registry)
8. Create `custom-transformer-registry.ts` - custom transformer registry
9. Create `accessDeep.ts` - deep access utilities
10. Create `transformer.ts` - value transformation (depends on is, types, class-registry, custom-transformer-registry)
11. Create `plainer.ts` - annotation application (depends on transformer, pathstringifier)
12. Create `walker.ts` - tree walking (depends on transformer, plainer)
13. Create `index.ts` - main SuperJSON class (depends on all above)
14. Create test files as needed

## Required Tested Symbols

The hidden tests import or access every symbol listed here. Implement all of them.

- `function setDeep(object: any,
  path: (string | number)[],
  mapper: (v: any) => any): any`
- `function ClassRegistry.constructor()`
- `function ClassRegistry.register(value: Class, options?: string | RegisterOptions): void`
- `RegisterOptions.allowProps: string[]`
- `function CustomTransformerRegistry.register(transformer: CustomTransfomer<I, O>)`
- `CustomTransfomer.name: string`
- `CustomTransfomer.isApplicable: (v: any) => v is I`
- `CustomTransfomer.serialize: (v: I) => O`
- `CustomTransfomer.deserialize: (v: O) => I`
- `function DoubleIndexedKV.set(key: K, value: V)`
- `function DoubleIndexedKV.clear()`
- `class SuperJSON`
- `SuperJSON.dedupe: boolean`
- `SuperJSON.serialize`
- `SuperJSON.deserialize`
- `SuperJSON.stringify`
- `SuperJSON.parse`
- `SuperJSON.registerClass`
- `SuperJSON.registerSymbol`
- `SuperJSON.registerCustom`
- `SuperJSON.allowErrorProps`
- `function SuperJSON.constructor({
    dedupe = false,
  }: {
    dedupe?: boolean;
  } = {})`
- `function SuperJSON.serialize(object: SuperJSONValue): SuperJSONResult`
- `function SuperJSON.deserialize(payload: SuperJSONResult, options?: { inPlace?: boolean }): T`
- `function SuperJSON.stringify(object: SuperJSONValue): string`
- `function SuperJSON.parse(string: string): T`
- `function SuperJSON.registerClass(v: Class, options?: RegisterOptions | string)`
- `function SuperJSON.registerSymbol(v: Symbol, identifier?: string)`
- `function SuperJSON.registerCustom(transformer: Omit<CustomTransfomer<I, O>, 'name'>,
    name: string)`
- `function SuperJSON.allowErrorProps(...props: string[])`
- `serialize`
- `deserialize`
- `stringify`
- `parse`
- `registerClass`
- `registerCustom`
- `registerSymbol`
- `allowErrorProps`
- `function isUndefined(payload: any): payload is undefined`
- `function isNull(payload: any): payload is null`
- `function isPlainObject(payload: any): payload is { [key: string]: any }`
- `function isArray(payload: any): payload is any[]`
- `function isString(payload: any): payload is string`
- `function isNumber(payload: any): payload is number`
- `function isBoolean(payload: any): payload is boolean`
- `function isRegExp(payload: any): payload is RegExp`
- `function isMap(payload: any): payload is Map<any, any>`
- `function isSet(payload: any): payload is Set<any>`
- `function isSymbol(payload: any): payload is symbol`
- `function isDate(payload: any): payload is Date`
- `function isPrimitive(payload: any): payload is boolean | null | undefined | number | string | symbol`
- `function isTypedArray(payload: any): payload is TypedArray`
- `function isURL(payload: any): payload is URL`
- `function escapeKey(key: string)`
- `function parsePath(string: StringifiedPath, legacyPaths: boolean)`
- `function walker(object: any,
  identities: Map<any, any[][]>,
  superJson: SuperJSON,
  dedupe: boolean,
  path: any[] = [],
  objectsInThisPath: any[] = [],
  seenObjects = new Map<unknown, Result>()): Result`
- `class Registry`
- `function Registry.constructor(private readonly generateIdentifier: (v: T) => string)`
- `function Registry.register(value: T, identifier?: string): void`
- `function Registry.clear(): void`
- `function Registry.getIdentifier(value: T)`
- `function Registry.getValue(identifier: string)`
- `interface Class`
- `interface JSONValue`
- `interface SuperJSONValue`
- `interface SuperJSONResult`
- `SuperJSONResult.json: JSONValue`
- `SuperJSONResult.meta: {`
- `SuperJSONResult.values: MinimisedTree<TypeAnnotation>`
- `SuperJSONResult.referentialEqualities: ReferentialEqualityAnnotations`
- `SuperJSONResult.v: number`
- `function forEach(record: Record<string, T>,
  run: (v: T, key: string) => void)`

## Environment Configuration

### Runtime

Node.js (TypeScript)

Node version requirement: `>=16`

### Workspace

- Put the implementation directly under `/home/ubuntu/workspace`.
- Do NOT run `npm install`, `npx`, or any package manager commands. All dependencies and testing infrastructure are pre-configured and handled automatically.
- Your shell may start in a different current directory, so use absolute paths.
- Hidden tests import the solution from: `accessDeep.test.ts`, `accessDeep.ts`, `class-registry.ts`, `custom-transformer-registry.ts`, `double-indexed-kv.ts`, `index.test.ts`, `index.ts`, `is.test.ts`, `is.ts`, `pathstringifier.test.ts`, `pathstringifier.ts`, `plainer.spec.ts`, `plainer.ts`, `registry.test.ts`, `registry.ts`, `transformer.test.ts`, `transformer.ts`, `types.ts`, `util.ts`.

### Dependencies

The following npm packages are used:
```
copy-anything
```


## Project Directory Structure

```
workspace/
├── package.json
├── tsconfig.json
├── accessDeep.test.ts
├── accessDeep.ts
├── class-registry.ts
├── custom-transformer-registry.ts
├── double-indexed-kv.ts
├── index.test.ts
├── index.ts
├── is.test.ts
├── is.ts
├── pathstringifier.test.ts
├── pathstringifier.ts
├── plainer.spec.ts
├── plainer.ts
├── registry.test.ts
├── registry.ts
├── transformer.test.ts
├── transformer.ts
├── types.ts
├── util.ts
```

## API Usage Guide

### 1. Module Import

```typescript
import { getDeep, setDeep, ClassRegistry, RegisterOptions, CustomTransformerRegistry, CustomTransfomer, DoubleIndexedKV, SuperJSON, serialize, deserialize, stringify, parse, registerClass, registerCustom, registerSymbol, allowErrorProps, TypedArrayConstructor, TypedArray, isUndefined, isNull, isPlainObject, isEmptyObject, isArray, isString, isNumber, isBoolean, isRegExp, isMap, isSet, isSymbol, isDate, isError, isNaNValue, isPrimitive, isBigint, isInfinite, isTypedArray, isURL, StringifiedPath, escapeKey, stringifyPath, parsePath, MinimisedTree, ReferentialEqualityAnnotations, applyValueAnnotations, applyReferentialEqualityAnnotations, generateReferentialEqualityAnnotations, walker, Registry, PrimitiveTypeAnnotation, TypeAnnotation, isInstanceOfRegisteredClass, transformValue, untransformValue, Class, PrimitiveJSONValue, JSONValue, JSONArray, JSONObject, SerializableJSONValue, SuperJSONValue, SuperJSONArray, SuperJSONObject, SuperJSONResult, find, forEach, includes, findArr } from './accessDeep.test';
```

### 2. `ClassRegistry` Class

**Extends:** `Registry`

```typescript
class ClassRegistry extends Registry {
}
```

**Class Variables:**
- `classToAllowedProps`


```typescript
constructor()
```


```typescript
register(value: Class, options?: string | RegisterOptions): void
```

**Parameters:**
- `value: Class`
- `options: string | RegisterOptions`

**Returns:** `void`


```typescript
getAllowedProps(value: Class): string[] | undefined
```

**Parameters:**
- `value: Class`

**Returns:** `string[] | undefined`

### 3. `CustomTransformerRegistry` Class

```typescript
class CustomTransformerRegistry {
}
```

**Class Variables:**
- `transfomers: Record<string, CustomTransfomer<any, any>>`


```typescript
register(transformer: CustomTransfomer<I, O>)
```

**Parameters:**
- `transformer: CustomTransfomer<I, O>`


```typescript
findApplicable(v: T)
```

**Parameters:**
- `v: T`


```typescript
findByName(name: string)
```

**Parameters:**
- `name: string`

### 4. `DoubleIndexedKV` Class

```typescript
class DoubleIndexedKV {
}
```

**Class Variables:**
- `keyToValue`
- `valueToKey`


```typescript
set(key: K, value: V)
```

**Parameters:**
- `key: K`
- `value: V`


```typescript
getByKey(key: K): V | undefined
```

**Parameters:**
- `key: K`

**Returns:** `V | undefined`


```typescript
getByValue(value: V): K | undefined
```

**Parameters:**
- `value: V`

**Returns:** `K | undefined`


```typescript
clear()
```

### 5. `SuperJSON` Class

```typescript
class SuperJSON {
}
```

**Class Variables:**
- `dedupe: boolean`
- `classRegistry`
- `symbolRegistry`
- `customTransformerRegistry`
- `allowedErrorProps: string[]`
- `defaultInstance`
- `serialize`
- `deserialize`
- `stringify`
- `parse`
- `registerClass`
- `registerSymbol`
- `registerCustom`
- `allowErrorProps`


```typescript
constructor({
    dedupe = false,
  }: {
    dedupe?: boolean;
  } = {})
```

**Parameters:**
- `{
    dedupe = false,
  }: {
    dedupe?: boolean;
  } = {}`


```typescript
serialize(object: SuperJSONValue): SuperJSONResult
```

**Parameters:**
- `object: SuperJSONValue`

**Returns:** `SuperJSONResult`


```typescript
deserialize(payload: SuperJSONResult, options?: { inPlace?: boolean }): T
```

**Parameters:**
- `payload: SuperJSONResult`
- `options: { inPlace?: boolean }`

**Returns:** `T`


```typescript
stringify(object: SuperJSONValue): string
```

**Parameters:**
- `object: SuperJSONValue`

**Returns:** `string`


```typescript
parse(string: string): T
```

**Parameters:**
- `string: string`

**Returns:** `T`


```typescript
registerClass(v: Class, options?: RegisterOptions | string)
```

**Parameters:**
- `v: Class`
- `options: RegisterOptions | string`


```typescript
registerSymbol(v: Symbol, identifier?: string)
```

**Parameters:**
- `v: Symbol`
- `identifier: string`


```typescript
registerCustom(transformer: Omit<CustomTransfomer<I, O>, 'name'>,
    name: string)
```

**Parameters:**
- `transformer: Omit<CustomTransfomer<I, O>, 'name'>`
- `name: string`


```typescript
allowErrorProps(...props: string[])
```

**Parameters:**
- `...props: string[]`

### 6. `Registry` Class

```typescript
class Registry {
}
```

**Class Variables:**
- `kv`


```typescript
constructor(private readonly generateIdentifier: (v: T) => string)
```

**Parameters:**
- `private readonly generateIdentifier: (v: T) => string`


```typescript
register(value: T, identifier?: string): void
```

**Parameters:**
- `value: T`
- `identifier: string`

**Returns:** `void`


```typescript
clear(): void
```

**Returns:** `void`


```typescript
getIdentifier(value: T)
```

**Parameters:**
- `value: T`


```typescript
getValue(identifier: string)
```

**Parameters:**
- `identifier: string`

### 7. `RegisterOptions` Interface

```typescript
export interface RegisterOptions {
  identifier?: string;
  allowProps?: string[];
}
```

**Members:**
- `identifier: string`
- `allowProps: string[]`

### 8. `CustomTransfomer` Interface

```typescript
export interface CustomTransfomer {
  name?: string;
  isApplicable?: (v: any) => v is I;
  serialize?: (v: I) => O;
  deserialize?: (v: O) => I;
}
```

**Members:**
- `name: string`
- `isApplicable: (v: any) => v is I`
- `serialize: (v: I) => O`
- `deserialize: (v: O) => I`

### 9. `TypedArrayConstructor` Type Alias

```typescript
export type TypedArrayConstructor = ...;
```

### 10. `TypedArray` Type Alias

```typescript
export type TypedArray = ...;
```

### 11. `StringifiedPath` Type Alias

```typescript
export type StringifiedPath = ...;
```

### 12. `MinimisedTree` Type Alias

```typescript
export type MinimisedTree = ...;
```

### 13. `ReferentialEqualityAnnotations` Type Alias

```typescript
export type ReferentialEqualityAnnotations = ...;
```

### 14. `PrimitiveTypeAnnotation` Type Alias

```typescript
export type PrimitiveTypeAnnotation = ...;
```

### 15. `TypeAnnotation` Type Alias

```typescript
export type TypeAnnotation = ...;
```

### 16. `Class` Type Alias

```typescript
export type Class = ...;
```

### 17. `PrimitiveJSONValue` Type Alias

```typescript
export type PrimitiveJSONValue = ...;
```

### 18. `JSONValue` Type Alias

```typescript
export type JSONValue = ...;
```

### 19. `JSONArray` Interface

```typescript
export interface JSONArray {
}
```

### 20. `JSONObject` Interface

```typescript
export interface JSONObject {
}
```

### 21. `SerializableJSONValue` Type Alias

```typescript
export type SerializableJSONValue = ...;
```

### 22. `SuperJSONValue` Type Alias

```typescript
export type SuperJSONValue = ...;
```

### 23. `SuperJSONArray` Interface

```typescript
export interface SuperJSONArray {
}
```

### 24. `SuperJSONObject` Interface

```typescript
export interface SuperJSONObject {
}
```

### 25. `SuperJSONResult` Interface

```typescript
export interface SuperJSONResult {
  json?: JSONValue;
  meta?: {;
  values?: MinimisedTree<TypeAnnotation>;
  referentialEqualities?: ReferentialEqualityAnnotations;
  v?: number;
}
```

**Members:**
- `json: JSONValue`
- `meta: {`
- `values: MinimisedTree<TypeAnnotation>`
- `referentialEqualities: ReferentialEqualityAnnotations`
- `v: number`

### 26. `getDeep` Function

```typescript
export function getDeep(object: object, path: (string | number)[]): object
```

**Parameters:**
- `object: object`
- `path: (string | number)[]`

**Returns:** `object`

### 27. `setDeep` Function

```typescript
export function setDeep(object: any,
  path: (string | number)[],
  mapper: (v: any) => any): any
```

**Parameters:**
- `object: any`
- `path: (string | number)[]`
- `mapper: (v: any) = > any`

**Returns:** `any`

### 28. `isUndefined` Function

```typescript
export function isUndefined(payload: any): payload is undefined
```

**Parameters:**
- `payload: any`

**Returns:** `payload is undefined`

### 29. `isNull` Function

```typescript
export function isNull(payload: any): payload is null
```

**Parameters:**
- `payload: any`

**Returns:** `payload is null`

### 30. `isPlainObject` Function

```typescript
export function isPlainObject(payload: any): payload is { [key: string]: any }
```

**Parameters:**
- `payload: any`

**Returns:** `payload is { [key: string]: any }`

### 31. `isEmptyObject` Function

```typescript
export function isEmptyObject(payload: any): payload is {}
```

**Parameters:**
- `payload: any`

**Returns:** `payload is {}`

### 32. `isArray` Function

```typescript
export function isArray(payload: any): payload is any[]
```

**Parameters:**
- `payload: any`

**Returns:** `payload is any[]`

### 33. `isString` Function

```typescript
export function isString(payload: any): payload is string
```

**Parameters:**
- `payload: any`

**Returns:** `payload is string`

### 34. `isNumber` Function

```typescript
export function isNumber(payload: any): payload is number
```

**Parameters:**
- `payload: any`

**Returns:** `payload is number`

### 35. `isBoolean` Function

```typescript
export function isBoolean(payload: any): payload is boolean
```

**Parameters:**
- `payload: any`

**Returns:** `payload is boolean`

### 36. `isRegExp` Function

```typescript
export function isRegExp(payload: any): payload is RegExp
```

**Parameters:**
- `payload: any`

**Returns:** `payload is RegExp`

### 37. `isMap` Function

```typescript
export function isMap(payload: any): payload is Map<any, any>
```

**Parameters:**
- `payload: any`

**Returns:** `payload is Map<any, any>`

### 38. `isSet` Function

```typescript
export function isSet(payload: any): payload is Set<any>
```

**Parameters:**
- `payload: any`

**Returns:** `payload is Set<any>`

### 39. `isSymbol` Function

```typescript
export function isSymbol(payload: any): payload is symbol
```

**Parameters:**
- `payload: any`

**Returns:** `payload is symbol`

### 40. `isDate` Function

```typescript
export function isDate(payload: any): payload is Date
```

**Parameters:**
- `payload: any`

**Returns:** `payload is Date`

### 41. `isError` Function

```typescript
export function isError(payload: any): payload is Error
```

**Parameters:**
- `payload: any`

**Returns:** `payload is Error`

### 42. `isNaNValue` Function

```typescript
export function isNaNValue(payload: any): payload is typeof NaN
```

**Parameters:**
- `payload: any`

**Returns:** `payload is typeof NaN`

### 43. `isPrimitive` Function

```typescript
export function isPrimitive(payload: any): payload is boolean | null | undefined | number | string | symbol
```

**Parameters:**
- `payload: any`

**Returns:** `payload is boolean | null | undefined | number | string | symbol`

### 44. `isBigint` Function

```typescript
export function isBigint(payload: any): payload is bigint
```

**Parameters:**
- `payload: any`

**Returns:** `payload is bigint`

### 45. `isInfinite` Function

```typescript
export function isInfinite(payload: any): payload is number
```

**Parameters:**
- `payload: any`

**Returns:** `payload is number`

### 46. `isTypedArray` Function

```typescript
export function isTypedArray(payload: any): payload is TypedArray
```

**Parameters:**
- `payload: any`

**Returns:** `payload is TypedArray`

### 47. `isURL` Function

```typescript
export function isURL(payload: any): payload is URL
```

**Parameters:**
- `payload: any`

**Returns:** `payload is URL`

### 48. `escapeKey` Function

```typescript
export function escapeKey(key: string)
```

**Parameters:**
- `key: string`

### 49. `stringifyPath` Function

```typescript
export function stringifyPath(path: Path): StringifiedPath
```

**Parameters:**
- `path: Path`

**Returns:** `StringifiedPath`

### 50. `parsePath` Function

```typescript
export function parsePath(string: StringifiedPath, legacyPaths: boolean)
```

**Parameters:**
- `string: StringifiedPath`
- `legacyPaths: boolean`

### 51. `applyValueAnnotations` Function

```typescript
export function applyValueAnnotations(plain: any,
  annotations: MinimisedTree<TypeAnnotation>,
  version: number,
  superJson: SuperJSON)
```

**Parameters:**
- `plain: any`
- `annotations: MinimisedTree<TypeAnnotation>`
- `version: number`
- `superJson: SuperJSON`

### 52. `applyReferentialEqualityAnnotations` Function

```typescript
export function applyReferentialEqualityAnnotations(plain: any,
  annotations: ReferentialEqualityAnnotations,
  version: number)
```

**Parameters:**
- `plain: any`
- `annotations: ReferentialEqualityAnnotations`
- `version: number`

### 53. `generateReferentialEqualityAnnotations` Function

```typescript
export function generateReferentialEqualityAnnotations(identitites: Map<any, any[][]>,
  dedupe: boolean): ReferentialEqualityAnnotations | undefined
```

**Parameters:**
- `identitites: Map<any, any[][]>`
- `dedupe: boolean`

**Returns:** `ReferentialEqualityAnnotations | undefined`

### 54. `walker` Function

```typescript
export function walker(object: any,
  identities: Map<any, any[][]>,
  superJson: SuperJSON,
  dedupe: boolean,
  path: any[] = [],
  objectsInThisPath: any[] = [],
  seenObjects = new Map<unknown, Result>()): Result
```

**Parameters:**
- `object: any`
- `identities: Map<any, any[][]>`
- `superJson: SuperJSON`
- `dedupe: boolean`
- `path: any[] = []`
- `objectsInThisPath: any[] = []`
- `seenObjects = new Map<unknown, Result>()`

**Returns:** `Result`

### 55. `isInstanceOfRegisteredClass` Function

```typescript
export function isInstanceOfRegisteredClass(potentialClass: any,
  superJson: SuperJSON): potentialClass is any
```

**Parameters:**
- `potentialClass: any`
- `superJson: SuperJSON`

**Returns:** `potentialClass is any`

### 56. `transformValue` Function

```typescript
export function transformValue(value: any,
  superJson: SuperJSON): { value: any; type: TypeAnnotation } | undefined
```

**Parameters:**
- `value: any`
- `superJson: SuperJSON`

**Returns:** `{ value: any; type: TypeAnnotation } | undefined`

### 57. `untransformValue` Function

```typescript
export function untransformValue(json: any,
  type: TypeAnnotation,
  superJson: SuperJSON)
```

**Parameters:**
- `json: any`
- `type: TypeAnnotation`
- `superJson: SuperJSON`

### 58. `find` Function

```typescript
export function find(record: Record<string, T>,
  predicate: (v: T) => boolean): T | undefined
```

**Parameters:**
- `record: Record<string, T>`
- `predicate: (v: T) = > boolean`

**Returns:** `T | undefined`

### 59. `forEach` Function

```typescript
export function forEach(record: Record<string, T>,
  run: (v: T, key: string) => void)
```

**Parameters:**
- `record: Record<string, T>`
- `run: (v: T, key: string) = > void`

### 60. `includes` Function

```typescript
export function includes(arr: T[], value: T)
```

**Parameters:**
- `arr: T[]`
- `value: T`

### 61. `findArr` Function

```typescript
export function findArr(record: T[],
  predicate: (v: T) => boolean): T | undefined
```

**Parameters:**
- `record: T[]`
- `predicate: (v: T) = > boolean`

**Returns:** `T | undefined`

### 62. Constants and Configuration

```typescript
export const serialize = SuperJSON.serialize;
export const deserialize = SuperJSON.deserialize;
export const stringify = SuperJSON.stringify;
export const parse = SuperJSON.parse;
export const registerClass = SuperJSON.registerClass;
export const registerCustom = SuperJSON.registerCustom;
export const registerSymbol = SuperJSON.registerSymbol;
export const allowErrorProps = SuperJSON.allowErrorProps;
```

## Implementation Notes

### Note 1: setDeep Function Behavior with Nested Collections
The `setDeep(object: any, path: (string | number)[], mapper: (v: any) => any)` function navigates through nested structures using numeric indices for Map and Set entries. When the path includes numeric indices, it accesses Map/Set entries by position (e.g., `['a', 0, 0, 0]` accesses the first key of the first entry in a Map). The `mapper` function transforms the value at the final path location. For Maps, numeric indices access entries as `[key, value]` pairs; for Sets, numeric indices access elements by position.

### Note 2: SuperJSON Instance Constructor and Configuration
The `SuperJSON` constructor accepts an optional configuration object with a `dedupe` boolean property (defaults to `false`). Each SuperJSON instance maintains independent registries: `classRegistry`, `symbolRegistry`, and `customTransformerRegistry`. Instances do not share registration state—registering a class in one instance does not affect other instances.

### Note 3: Class Registration with allowProps
The `registerClass(v: Class, options?: RegisterOptions | string)` method accepts either a string identifier or a `RegisterOptions` object. The `RegisterOptions` interface includes an optional `allowProps` array of strings that specifies which properties of the class should be serialized. When a class is registered, only properties listed in `allowProps` (or all enumerable properties if `allowProps` is not specified) are included during serialization.

### Note 4: Error Property Allowlisting
The `allowErrorProps(...props: string[])` method accepts variadic string arguments to specify which Error object properties should be serialized. By default, Error properties like `stack` are excluded from serialization. Multiple calls to `allowErrorProps` accumulate allowed properties. The `allowedErrorProps` array on the SuperJSON instance stores these allowed property names.

### Note 5: Serialization Result Structure
The `serialize(object: SuperJSONValue)` method returns a `SuperJSONResult` object with optional properties: `json` (the serialized value), `meta` (containing `v` for version, `values` for type annotations, and `referentialEqualities` for deduplication). If no special types or metadata are needed, the `meta` property may be absent. The `json` property contains the JSON-serializable representation.

### Note 6: Deserialization with inPlace Option
The `deserialize(payload: SuperJSONResult, options?: { inPlace?: boolean })` method accepts an optional `inPlace` boolean flag. When `inPlace` is true, the deserialization modifies the input object directly; otherwise, it creates new objects. The method uses the `meta` information to reconstruct typed values from their JSON representations.

### Note 7: Type Checking Predicates
Type guard functions (`isUndefined`, `isNull`, `isArray`, `isString`, `isNumber`, `isBoolean`, `isRegExp`, `isDate`, `isSymbol`, `isMap`, `isSet`, `isError`, `isPlainObject`, `isPrimitive`, `isBigint`, `isNaNValue`, `isInfinite`, `isTypedArray`, `isURL`) use TypeScript's `is` keyword for type narrowing. `isDate` returns false for invalid dates (e.g., `new Date('_')`). `isPrimitive` returns true only for boolean, null, undefined, number, string, and symbol—not for NaN or objects. `isPlainObject` returns true for objects created with `{}` or `Object.create(null)`.

### Note 8: Path Escaping and Parsing
The `escapeKey(key: string)` function escapes dots in property names by prefixing them with backslashes. The `parsePath(string: StringifiedPath, legacyPaths: boolean)` function parses escaped paths back into arrays. When `legacyPaths` is false, invalid escape sequences (e.g., `\a` without a following dot) throw errors. When `legacyPaths` is true, more lenient parsing rules apply. The `stringifyPath(path: Path)` function converts path arrays into escaped string representations.

### Note 9: Registry Base Class Behavior
The `Registry` class is a generic base that stores key-value pairs using a `DoubleIndexedKV` structure. It requires a `generateIdentifier` function in the constructor that converts values to string identifiers. Methods include `register(value: T, identifier?: string)`, `getIdentifier(value: T)`, `getValue(identifier: string)`, and `clear()`. The `ClassRegistry` extends `Registry` and adds `classToAllowedProps` mapping and `getAllowedProps(value: Class)` method.

### Note 10: Custom Transformer Registration
The `registerCustom(transformer: Omit<CustomTransfomer<I, O>, 'name'>, name: string)` method registers custom serialization/deserialization logic. The `CustomTransfomer` interface includes optional `isApplicable` (type guard), `serialize` (I → O), and `deserialize` (O → I) methods. The `CustomTransformerRegistry` stores transformers by name and provides `findApplicable(v: T)` to locate applicable transformers and `findByName(name: string)` for lookup.

### Note 11: Referential Equality and Deduplication
When `dedupe` is true, SuperJSON tracks object identity and generates `referentialEqualityAnnotations` to represent shared references. The `generateReferentialEqualityAnnotations(identities: Map<any, any[][]>, dedupe: boolean)` function creates annotations only when deduplication is enabled. The `applyReferentialEqualityAnnotations` function reconstructs shared references during deserialization. Prototype pollution is prevented by rejecting paths containing `__proto__`, `prototype`, or `constructor.prototype`.

### Note 12: Walker Function for Transformation
The `walker(object: any, identities: Map<any, any[][]>, superJson: SuperJSON, dedupe: boolean, path?: any[], objectsInThisPath?: any[], seenObjects?: Map<unknown, Result>)` function recursively traverses objects and applies transformations. It returns a `Result` object with `transformedValue` (the serialized form) and `annotations` (type metadata). Maps are transformed to arrays of `[key, value]` pairs with annotations, and RegExp objects are converted to strings with regexp annotations.

### Note 13: Stringify and Parse Convenience Methods
The `stringify(object: SuperJSONValue)` method combines `serialize()` and `JSON.stringify()` into a single operation, returning a JSON string. The `parse(string: string)` method combines `JSON.parse()` and `deserialize()`, returning the reconstructed typed value. These methods provide a simpler API for common serialization workflows.

### Note 14: Prototype Pollution Protection
Deserialization explicitly rejects property paths containing `__proto__`, `prototype`, or `constructor.prototype` to prevent prototype pollution attacks. Attempting to deserialize such paths throws an error with a descriptive message. This protection applies to the `referentialEqualities` metadata during `applyReferentialEqualityAnnotations`.

### Note 15: Accessor Properties and Class Serialization
When serializing class instances, only own enumerable properties are included by default, not accessor properties (getters). If a class is registered with `allowProps`, only those specified properties are serialized. Private fields and getter-only properties are excluded unless explicitly listed in `allowProps`.