import { describe, it, expect } from "vitest";
import {
  convertFromGbp,
  formatMoney,
  getBudgetOptions,
  GBP_TO_USD,
} from "@/lib/currency";

describe("currency", () => {
  it("keeps GBP amounts unchanged", () => {
    expect(convertFromGbp(5000, "GBP")).toBe(5000);
  });

  it("converts GBP to USD with the configured rate", () => {
    expect(convertFromGbp(1000, "USD")).toBe(Math.round(1000 * GBP_TO_USD));
  });

  it("formats sterling by default style", () => {
    expect(formatMoney(5000, "GBP")).toMatch(/£5,000/);
  });

  it("formats USD when selected", () => {
    expect(formatMoney(5000, "USD")).toMatch(/\$6,350/);
  });

  it("builds solo-friendly budget bands", () => {
    const gbp = getBudgetOptions("GBP");
    expect(gbp.map((o) => o.value)).toEqual([
      "under-1k",
      "1k-2.5k",
      "2.5k-5k",
      "5k-10k",
      "10k-plus",
    ]);
    expect(gbp[0].label).toContain("£");
    const usd = getBudgetOptions("USD");
    expect(usd[0].label).toContain("$");
  });
});
