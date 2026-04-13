/**
 * A simple math utility library for testing ast-pilot TypeScript support.
 */

export const PI = 3.14159265358979;
export const E = 2.71828182845905;

export function add(a: number, b: number): number {
  return a + b;
}

export function subtract(a: number, b: number): number {
  return a - b;
}

export function multiply(a: number, b: number): number {
  return a * b;
}

export function divide(a: number, b: number): number {
  if (b === 0) throw new Error("Division by zero");
  return a / b;
}

export async function delayedSum(a: number, b: number, ms: number = 10): Promise<number> {
  return new Promise((resolve) => setTimeout(() => resolve(a + b), ms));
}

export class Calculator {
  private history: Array<{ op: string; result: number }> = [];

  add(a: number, b: number): number {
    const result = a + b;
    this.history.push({ op: "add", result });
    return result;
  }

  subtract(a: number, b: number): number {
    const result = a - b;
    this.history.push({ op: "subtract", result });
    return result;
  }

  multiply(a: number, b: number): number {
    const result = a * b;
    this.history.push({ op: "multiply", result });
    return result;
  }

  getHistory(): Array<{ op: string; result: number }> {
    return [...this.history];
  }

  clearHistory(): void {
    this.history = [];
  }
}
