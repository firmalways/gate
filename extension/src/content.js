/* FirmAlways Gate content script for AI chat sites.
 *
 * 1. Paste: the pasted text is sent to your local Gate (/v1/firmalways/preview)
 *    through the background worker. Personal data is replaced with «TYPE_N»
 *    before it reaches the chat box; blocked data (secrets, PDPA s.26) is not
 *    pasted at all.
 * 2. Display: placeholders shown on the page are replaced with the real values
 *    for you only. Editable fields are never touched, so what you send stays masked.
 *
 * Typed (not pasted) text is not inspected in this version.
 */
(function () {
  "use strict";
  const lib = globalThis.FirmAlwaysGate;
  const state = lib.createState();
  const MAX_PASTE = 200000;

  function toast(message, kind) {
    const el = document.createElement("div");
    el.textContent = message;
    el.setAttribute("data-firmalways-toast", kind || "info");
    Object.assign(el.style, {
      position: "fixed", right: "16px", bottom: "16px", zIndex: 2147483647, maxWidth: "360px",
      padding: "10px 14px", borderRadius: "8px", font: "14px/1.4 system-ui, sans-serif", color: "#fff",
      background: kind === "block" ? "#b42318" : kind === "error" ? "#7a2e0e" : "#155eef",
      boxShadow: "0 4px 16px rgba(0,0,0,.25)",
    });
    document.documentElement.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  function isEditable(node) {
    const el = node && (node.nodeType === 1 ? node : node.parentElement);
    return !!(el && el.closest && el.closest('textarea, input, [contenteditable=""], [contenteditable="true"]'));
  }

  function insertText(target, text) {
    target.focus();
    if (document.execCommand && document.execCommand("insertText", false, text)) return;
    if ("value" in target) {
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? target.value.length;
      target.value = target.value.slice(0, start) + text + target.value.slice(end);
      target.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  document.addEventListener(
    "paste",
    (event) => {
      const target = event.target;
      if (!isEditable(target)) return;
      const text = event.clipboardData && event.clipboardData.getData("text/plain");
      if (!text) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (text.length > MAX_PASTE) {
        toast("FirmAlways Gate: ข้อความยาวเกินกว่าจะตรวจได้ จึงไม่ได้วาง", "block");
        return;
      }
      chrome.runtime.sendMessage({ type: "preview", text }, (reply) => {
        if (chrome.runtime.lastError || !reply || !reply.ok) {
          if (reply && reply.failOpen) {
            insertText(target, text);
            toast("FirmAlways Gate ไม่ทำงาน — วางข้อความเดิมโดยไม่ตรวจ (ตั้งค่า fail-open)", "error");
          } else {
            toast("FirmAlways Gate ไม่ทำงาน จึงไม่ได้วางข้อความ (ตรวจสอบ Gate หรือหน้าตั้งค่า)", "error");
          }
          return;
        }
        const decision = lib.decide(reply.preview);
        if (decision.action === "block") {
          toast("FirmAlways Gate บล็อกการวาง: พบ " + decision.types.join(", "), "block");
        } else if (decision.action === "mask") {
          insertText(target, lib.applyMasking(text, reply.preview.entities, state));
          toast(`FirmAlways Gate ซ่อนข้อมูลส่วนบุคคล ${decision.count} รายการก่อนวาง`, "info");
        } else if (decision.action === "pass") {
          insertText(target, text);
        } else {
          toast("FirmAlways Gate ตอบกลับไม่ถูกต้อง จึงไม่ได้วางข้อความ", "error");
        }
      });
    },
    true
  );

  function restoreNode(node) {
    if (node.nodeType === 3) {
      if (!isEditable(node)) {
        const restored = lib.restoreText(node.nodeValue, state);
        if (restored !== node.nodeValue) node.nodeValue = restored;
      }
      return;
    }
    if (node.nodeType !== 1 || isEditable(node)) return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(restoreNode);
  }

  new MutationObserver((mutations) => {
    if (!state.byToken.size) return;
    for (const m of mutations) {
      if (m.type === "characterData") restoreNode(m.target);
      m.addedNodes.forEach(restoreNode);
    }
  }).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
})();
