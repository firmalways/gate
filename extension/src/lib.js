/* FirmAlways Gate browser extension — pure logic shared by the content script and the tests.
 *
 * Masking happens per tab: the same value always gets the same placeholder in a
 * tab, even across several pastes, so a conversation stays consistent. The
 * mapping lives only in the tab's memory and disappears when the tab closes.
 */
(function (root) {
  "use strict";

  function createState() {
    return { byKey: new Map(), byToken: new Map(), counters: new Map() };
  }

  function normalize(type, value) {
    let v = String(value).replace(/[\s\-.()+ ]/g, "").toLowerCase();
    v = v.replace(/[๐-๙]/g, (d) => String("๐๑๒๓๔๕๖๗๘๙".indexOf(d)));
    if (type === "PHONE" && v.startsWith("66")) v = "0" + v.slice(2);
    return type + ":" + v;
  }

  /** Gate reports offsets in Unicode code points; JavaScript strings index UTF-16 units. */
  function codePointToUnitIndex(text) {
    const index = [];
    let unit = 0;
    for (const ch of text) {
      index.push(unit);
      unit += ch.length;
    }
    index.push(unit);
    return index;
  }

  /** Mask `text` using Gate preview `entities` ({type, start, end, action}). Returns the masked text. */
  function applyMasking(text, entities, state) {
    const units = codePointToUnitIndex(text);
    const toMask = entities
      .filter((e) => e.action === "mask")
      .map((e) => ({ type: e.type, start: units[e.start], end: units[e.end] }))
      .sort((a, b) => a.start - b.start);
    let out = "";
    let pos = 0;
    for (const e of toMask) {
      if (e.start === undefined || e.end === undefined) throw new Error("entity offsets outside the pasted text");
      if (e.start < pos) continue; // overlapping entities are resolved by Gate; skip defensively
      const value = text.slice(e.start, e.end);
      const key = normalize(e.type, value);
      let token = state.byKey.get(key);
      if (!token) {
        const n = (state.counters.get(e.type) || 0) + 1;
        state.counters.set(e.type, n);
        token = `${e.type}_${n}`;
        state.byKey.set(key, token);
        state.byToken.set(token, value);
      }
      out += text.slice(pos, e.start) + `«${token}»`;
      pos = e.end;
    }
    return out + text.slice(pos);
  }

  /** Replace known «TOKEN» placeholders with the original values (for display only). */
  function restoreText(text, state) {
    if (!state.byToken.size || text.indexOf("«") === -1) return text;
    return text.replace(/«\s*([A-Z][A-Z0-9_]*_[0-9]+)\s*»/g, (match, token) =>
      state.byToken.has(token) ? state.byToken.get(token) : match
    );
  }

  /** Decide what to do with a pasted text given the Gate preview result. */
  function decide(preview) {
    if (!preview || typeof preview !== "object") return { action: "error" };
    if (preview.blocked_types && preview.blocked_types.length) {
      return { action: "block", types: preview.blocked_types.slice() };
    }
    const masked = (preview.entities || []).filter((e) => e.action === "mask");
    return { action: masked.length ? "mask" : "pass", count: masked.length };
  }

  const api = { createState, normalize, applyMasking, restoreText, decide };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FirmAlwaysGate = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
