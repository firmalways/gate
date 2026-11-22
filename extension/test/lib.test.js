const test = require("node:test");
const assert = require("node:assert/strict");
const lib = require("../src/lib.js");

const text = "นายสมชาย ใจดี บัตร 1101700203611 โทร 081-234-5678";
const entities = [
  { type: "PERSON", start: 3, end: 13, action: "mask" },
  { type: "THAI_NATIONAL_ID", start: 19, end: 32, action: "mask" },
  { type: "PHONE", start: 37, end: 49, action: "mask" },
];

test("masks with tab-wide numbering and restores for display", () => {
  const state = lib.createState();
  const masked = lib.applyMasking(text, entities, state);
  assert.equal(masked, "นาย«PERSON_1» บัตร «THAI_NATIONAL_ID_1» โทร «PHONE_1»");
  assert.equal(lib.restoreText("เรียนคุณ«PERSON_1» โทร « PHONE_1 »", state), "เรียนคุณสมชาย ใจดี โทร 081-234-5678");
});

test("second paste reuses placeholders and numbers new values", () => {
  const state = lib.createState();
  lib.applyMasking(text, entities, state);
  const second = "โทร 0812345678 หรือ 0899999999";
  const masked = lib.applyMasking(second, [
    { type: "PHONE", start: 4, end: 14, action: "mask" },
    { type: "PHONE", start: 20, end: 30, action: "mask" },
  ], state);
  assert.equal(masked, "โทร «PHONE_1» หรือ «PHONE_2»");
});

test("allow actions and unknown tokens are left alone", () => {
  const state = lib.createState();
  assert.equal(lib.applyMasking("a@example.com", [{ type: "EMAIL", start: 0, end: 13, action: "allow" }], state), "a@example.com");
  assert.equal(lib.restoreText("«EMAIL_9»", state), "«EMAIL_9»");
});

test("decide", () => {
  assert.deepEqual(lib.decide({ blocked_types: ["SECRET"], entities: [] }), { action: "block", types: ["SECRET"] });
  assert.deepEqual(lib.decide({ blocked_types: [], entities: entities }), { action: "mask", count: 3 });
  assert.deepEqual(lib.decide({ blocked_types: [], entities: [] }), { action: "pass", count: 0 });
  assert.deepEqual(lib.decide(null), { action: "error" });
});

test("normalize phone prefixes and Thai digits", () => {
  assert.equal(lib.normalize("PHONE", "+66 81 234 5678"), lib.normalize("PHONE", "081-234-5678"));
  assert.equal(lib.normalize("THAI_NATIONAL_ID", "๑๑๐๑๗๐๐๒๐๓๖๑๑"), lib.normalize("THAI_NATIONAL_ID", "1101700203611"));
});

test("code point offsets from Gate are converted (emoji before an entity)", () => {
  const state = lib.createState();
  const pasted = "😀😀 โทร 0812345678";
  // Python (Gate) counts each emoji as 1 code point: the phone is at 7..17.
  assert.equal(lib.applyMasking(pasted, [{ type: "PHONE", start: 7, end: 17, action: "mask" }], state), "😀😀 โทร «PHONE_1»");
});

test("out-of-range offsets fail instead of masking the wrong text", () => {
  assert.throws(() => lib.applyMasking("abc", [{ type: "PHONE", start: 1, end: 9, action: "mask" }], lib.createState()));
});
