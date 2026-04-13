import { describe, it, expect } from "vitest";
import { slugify, truncate, splitCSV, reverseAsync, StringBuilder, DEFAULT_SEPARATOR } from "../src/strings";

describe("slugify", () => {
  it("converts to lowercase kebab", () => {
    expect(slugify("Hello World")).toBe("hello-world");
  });

  it("removes special characters", () => {
    expect(slugify("foo@bar!baz")).toBe("foobarbaz");
  });

  it("collapses multiple dashes", () => {
    expect(slugify("a -- b")).toBe("a-b");
  });
});

describe("truncate", () => {
  it("returns short strings unchanged", () => {
    expect(truncate("hi", 10)).toBe("hi");
  });

  it("truncates long strings with default suffix", () => {
    expect(truncate("hello world", 8)).toBe("hello...");
  });

  it("uses custom suffix", () => {
    expect(truncate("hello world", 8, "~")).toBe("hello w~");
  });
});

describe("splitCSV", () => {
  it("splits by comma by default", () => {
    expect(splitCSV("a, b, c")).toEqual(["a", "b", "c"]);
  });

  it("uses custom separator", () => {
    expect(splitCSV("a|b|c", "|")).toEqual(["a", "b", "c"]);
  });
});

describe("reverseAsync", () => {
  it("reverses a string", async () => {
    expect(await reverseAsync("abc")).toBe("cba");
  });
});

describe("StringBuilder", () => {
  it("appends text", () => {
    const sb = new StringBuilder();
    sb.append("hello").append(" world");
    expect(sb.toString()).toBe("hello world");
  });

  it("prepends text", () => {
    const sb = new StringBuilder();
    sb.append("world");
    sb.prepend("hello ");
    expect(sb.toString()).toBe("hello world");
  });

  it("tracks length", () => {
    const sb = new StringBuilder();
    sb.append("abc");
    expect(sb.length).toBe(3);
  });

  it("clears content", () => {
    const sb = new StringBuilder();
    sb.append("test");
    sb.clear();
    expect(sb.toString()).toBe("");
    expect(sb.length).toBe(0);
  });
});

describe("constants", () => {
  it("exports DEFAULT_SEPARATOR", () => {
    expect(DEFAULT_SEPARATOR).toBe(",");
  });
});
