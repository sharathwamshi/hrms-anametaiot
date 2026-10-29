import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");

function ruleFor(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = styles.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`));
  assert.ok(match, `Expected a CSS rule for ${selector}`);
  return match[1];
}

test("regularization note wraps long tokens and preserves line breaks", () => {
  const noteStyle = ruleFor(".att-regularization-note");
  assert.match(noteStyle, /overflow-wrap:\s*anywhere\s*;/);
  assert.match(noteStyle, /word-break:\s*normal\s*;/);
  assert.match(noteStyle, /white-space:\s*pre-wrap\s*;/);
  assert.match(noteStyle, /max-width:\s*100%\s*;/);
  assert.match(noteStyle, /min-width:\s*0\s*;/);
});

test("regularization container is constrained to its modal content width", () => {
  const containerStyle = ruleFor(".att-regularization-box");
  assert.match(containerStyle, /max-width:\s*100%\s*;/);
  assert.match(containerStyle, /min-width:\s*0\s*;/);

  const modalStyle = ruleFor(".modal-box");
  assert.match(modalStyle, /max-width:\s*92vw\s*;/);
});
