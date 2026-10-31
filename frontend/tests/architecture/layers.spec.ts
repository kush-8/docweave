import { readdirSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { expect, test } from "@playwright/test";

import { readView, viewHref } from "../../src/routing/workbench";

test("technical layers only import their permitted dependencies", () => {
  const source = resolve("src");
  const dependencies: Record<string, string[]> = {
    app: ["pages", "styles"],
    pages: ["components", "layouts", "hooks", "routing", "data"],
    layouts: ["components", "routing"],
    components: ["components", "routing", "data"],
    hooks: ["hooks", "routing"],
    routing: ["routing"],
    data: ["data"],
  };
  const violations: string[] = [];
  for (const file of readdirSync(source, { recursive: true }).map(String).filter((file) => /\.tsx?$/.test(file))) {
    const filename = resolve(source, file);
    const layer = file.split(/[\\/]/)[0];
    for (const entry of readFileSync(filename, "utf8").matchAll(/\b(?:from\s+|import\s*(?:\(\s*)?)["']([^"']+)["']/g)) {
      const specifier = entry[1];
      if (!specifier.startsWith("@/") && !specifier.startsWith(".")) continue;
      const target = specifier.startsWith("@/") ? resolve(source, specifier.slice(2)) : resolve(dirname(filename), specifier);
      const targetLayer = relative(source, target).split(/[\\/]/)[0];
      if (layer !== targetLayer && !dependencies[layer]?.includes(targetLayer)) violations.push(`${file} imports ${specifier}`);
    }
  }
  expect(violations).toEqual([]);
});

test("route parsing preserves project, conversation and exact evidence IDs", () => {
  expect(readView("")).toEqual({ project: "", conversation: "new", citation: null, turn: null });
  expect(readView(viewHref("c1", "s1", "p1", "t1"))).toEqual({ project: "p1", conversation: "c1", citation: "s1", turn: "t1" });
});
