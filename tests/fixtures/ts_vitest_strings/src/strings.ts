/**
 * String utility library for testing ast-pilot TypeScript support.
 */

export const DEFAULT_SEPARATOR = ",";

export function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-");
}

export function truncate(text: string, maxLength: number, suffix: string = "..."): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - suffix.length) + suffix;
}

export function splitCSV(line: string, separator: string = DEFAULT_SEPARATOR): string[] {
  return line.split(separator).map((s) => s.trim());
}

export async function reverseAsync(input: string): Promise<string> {
  return input.split("").reverse().join("");
}

export class StringBuilder {
  private parts: string[] = [];

  append(text: string): this {
    this.parts.push(text);
    return this;
  }

  prepend(text: string): this {
    this.parts.unshift(text);
    return this;
  }

  toString(): string {
    return this.parts.join("");
  }

  clear(): void {
    this.parts = [];
  }

  get length(): number {
    return this.parts.reduce((sum, p) => sum + p.length, 0);
  }
}
