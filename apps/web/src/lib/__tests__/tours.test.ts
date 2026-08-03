import { describe, expect, it } from "vitest";

import { TOURS, getTour, pageTourFor, walkthroughFor } from "../tours";

describe("tour registry", () => {
  it("has unique tour ids", () => {
    const ids = TOURS.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("page tours declare a route and keep 3 to 6 steps", () => {
    for (const tour of TOURS.filter((t) => t.kind === "page")) {
      expect(tour.route, tour.id).toBeTruthy();
      expect(tour.steps.length, tour.id).toBeGreaterThanOrEqual(3);
      expect(tour.steps.length, tour.id).toBeLessThanOrEqual(6);
    }
  });

  it("registers exactly one page tour per route", () => {
    const routes = TOURS.filter((t) => t.kind === "page").map((t) => t.route);
    expect(new Set(routes).size).toBe(routes.length);
  });

  it("walkthrough steps each declare their route", () => {
    for (const tour of TOURS.filter((t) => t.kind === "walkthrough")) {
      for (const step of tour.steps) {
        expect(step.route, `${tour.id}: ${step.title}`).toMatch(/^\//);
      }
    }
  });

  it("walkthroughs exist for the three product roles", () => {
    for (const role of ["applicant", "employer", "admin"]) {
      const tour = walkthroughFor(role);
      expect(tour, role).not.toBeNull();
      expect(tour!.steps.length).toBeGreaterThanOrEqual(4);
    }
    expect(walkthroughFor("institution")).toBeNull();
  });

  it("every step has an anchor, a title, and a body in the plain voice", () => {
    for (const tour of TOURS) {
      for (const step of tour.steps) {
        const where = `${tour.id}: ${step.title}`;
        expect(step.anchor.length, where).toBeGreaterThan(0);
        expect(step.title.length, where).toBeGreaterThan(0);
        expect(step.body.length, where).toBeGreaterThan(0);
        // Voice: no em dashes, no exclamation marks, no hype register.
        expect(step.title + step.body, where).not.toMatch(/[—!]/);
        expect((step.title + " " + step.body).toLowerCase(), where).not.toMatch(
          /seamless|effortless|leverage|empower|unlock|delve|robust|supercharge/,
        );
      }
    }
  });

  it("lookups resolve", () => {
    expect(pageTourFor("/applicant/matches")?.id).toBe("page-applicant-matches");
    expect(pageTourFor("/nowhere")).toBeNull();
    expect(getTour("walkthrough-admin")?.kind).toBe("walkthrough");
  });
});
