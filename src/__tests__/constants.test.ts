import { describe, it, expect } from "vitest";
import {
  SITE_CONFIG,
  NAV_LINKS,
  BUDGET_OPTIONS,
  TIMELINE_OPTIONS,
  FIRST_TIME_OFFER,
} from "@/lib/constants";

describe("SITE_CONFIG", () => {
  it("has required properties", () => {
    expect(SITE_CONFIG.name).toBe("Adam Batten");
    expect(SITE_CONFIG.title).toBeDefined();
    expect(SITE_CONFIG.description).toBeDefined();
    expect(SITE_CONFIG.keywords).toBeInstanceOf(Array);
    expect(SITE_CONFIG.keywords.length).toBeGreaterThan(0);
  });
});

describe("NAV_LINKS", () => {
  it("contains expected navigation items", () => {
    expect(NAV_LINKS.length).toBe(6);
    const labels = NAV_LINKS.map((l) => l.label);
    expect(labels).toContain("Home");
    expect(labels).toContain("Portfolio");
    expect(labels).toContain("Services");
    expect(labels).toContain("About");
    expect(labels).toContain("Contact");
    expect(labels).toContain("Portal");
  });

  it("all links have href starting with /", () => {
    NAV_LINKS.forEach((link) => {
      expect(link.href).toMatch(/^\//);
    });
  });
});

describe("BUDGET_OPTIONS", () => {
  it("contains budget ranges", () => {
    expect(BUDGET_OPTIONS.length).toBeGreaterThan(0);
    BUDGET_OPTIONS.forEach((opt) => {
      expect(opt.value).toBeDefined();
      expect(opt.label).toBeDefined();
    });
  });
});

describe("TIMELINE_OPTIONS", () => {
  it("contains timeline options", () => {
    expect(TIMELINE_OPTIONS.length).toBeGreaterThan(0);
    TIMELINE_OPTIONS.forEach((opt) => {
      expect(opt.value).toBeDefined();
      expect(opt.label).toBeDefined();
    });
  });
});

describe("FIRST_TIME_OFFER", () => {
  it("has discount info", () => {
    expect(FIRST_TIME_OFFER.code).toBe("WELCOME20");
    expect(FIRST_TIME_OFFER.discount).toBe(20);
    expect(FIRST_TIME_OFFER.title).toBeDefined();
    expect(FIRST_TIME_OFFER.description).toBeDefined();
  });
});
