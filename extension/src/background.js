/* Calls your FirmAlways Gate from the extension's background worker, so the
 * chat site's page never sees the Gate address or key. */
const DEFAULTS = { gateUrl: "http://127.0.0.1:8787", apiKey: "", failOpen: false };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "preview") return false;
  (async () => {
    const { gateUrl, apiKey, failOpen } = await settings();
    try {
      const headers = { "Content-Type": "application/json" };
      if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
      const response = await fetch(gateUrl.replace(/\/+$/, "") + "/v1/firmalways/preview", {
        method: "POST",
        headers,
        body: JSON.stringify({ text: message.text }),
      });
      if (!response.ok) throw new Error(`Gate returned ${response.status}`);
      sendResponse({ ok: true, preview: await response.json() });
    } catch (error) {
      sendResponse({ ok: false, failOpen, error: String(error) });
    }
  })();
  return true; // keep the channel open for the async response
});
