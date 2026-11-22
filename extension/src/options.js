const DEFAULTS = { gateUrl: "http://127.0.0.1:8787", apiKey: "", failOpen: false };
const $ = (id) => document.getElementById(id);

chrome.storage.local.get(Object.keys(DEFAULTS)).then((stored) => {
  const s = { ...DEFAULTS, ...stored };
  $("gateUrl").value = s.gateUrl;
  $("apiKey").value = s.apiKey;
  $("failOpen").checked = s.failOpen;
});

$("save").addEventListener("click", async () => {
  const gateUrl = $("gateUrl").value.trim() || DEFAULTS.gateUrl;
  const origin = new URL(gateUrl).origin + "/*";
  const local = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/\*$/.test(origin);
  if (!local && !(await chrome.permissions.request({ origins: [origin] }))) {
    $("status").textContent = "ต้องอนุญาตให้เข้าถึง " + origin;
    return;
  }
  await chrome.storage.local.set({ gateUrl, apiKey: $("apiKey").value, failOpen: $("failOpen").checked });
  $("status").textContent = "บันทึกแล้ว";
});
