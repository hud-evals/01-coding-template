import { describe, it, expect } from "vitest";
import { add, subtract, multiply, divide, delayedSum, Calculator, PI, E } from "../src/mathlib";

describe("arithmetic functions", () => {
  it("adds two numbers", () => {
    expect(add(2, 3)).toBe(5);
    expect(add(-1, 1)).toBe(0);
  });

  it("subtracts two numbers", () => {
    expect(subtract(10, 3)).toBe(7);
    expect(subtract(0, 5)).toBe(-5);
  });

  it("multiplies two numbers", () => {
    expect(multiply(4, 5)).toBe(20);
    expect(multiply(-2, 3)).toBe(-6);
  });

  it("divides two numbers", () => {
    expect(divide(10, 2)).toBe(5);
    expect(divide(7, 2)).toBe(3.5);
  });

  it("throws on division by zero", () => {
    expect(() => divide(1, 0)).toThrow("Division by zero");
  });

  it("computes delayed sum", async () => {
    const result = await delayedSum(3, 4, 1);
    expect(result).toBe(7);
  });
});

describe("constants", () => {
  it("exports PI", () => {
    expect(PI).toBeCloseTo(3.14159, 4);
  });

  it("exports E", () => {
    expect(E).toBeCloseTo(2.71828, 4);
  });
});

describe("Calculator class", () => {
  it("adds and tracks history", () => {
    const calc = new Calculator();
    expect(calc.add(2, 3)).toBe(5);
    expect(calc.getHistory()).toEqual([{ op: "add", result: 5 }]);
  });

  it("supports multiple operations", () => {
    const calc = new Calculator();
    calc.add(1, 2);
    calc.subtract(10, 5);
    calc.multiply(3, 4);
    expect(calc.getHistory()).toHaveLength(3);
  });

  it("clears history", () => {
    const calc = new Calculator();
    calc.add(1, 1);
    calc.clearHistory();
    expect(calc.getHistory()).toHaveLength(0);
  });
});
