const SAVE = "lc-save";
const EXPORT = "lc-export";
const CLEAR = "lc-clear";

// Latest right-clicked link text per tab (service worker may restart, so use session storage).
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "linkText" && sender.tab) {
    chrome.storage.session.set({ ["text_" + sender.tab.id]: msg.text });
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: SAVE, title: "Save link text + URL", contexts: ["link"] });
  chrome.contextMenus.create({ id: EXPORT, title: "Export saved links to text file", contexts: ["link", "page"] });
  chrome.contextMenus.create({ id: CLEAR, title: "Clear saved links", contexts: ["link", "page"] });
});

function clean(s) {
  return (s || "").replace(/[\t\r\n]+/g, " ").trim();
}

function setBadge(n) {
  chrome.action.setBadgeText({ text: n ? String(n) : "" });
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === SAVE) {
    const key = "text_" + tab.id;
    const stored = await chrome.storage.session.get(key);
    const text = clean(stored[key] || info.selectionText || info.linkUrl);
    const { links = [] } = await chrome.storage.local.get("links");
    links.push({ text, url: info.linkUrl });
    await chrome.storage.local.set({ links });
    setBadge(links.length);
  } else if (info.menuItemId === EXPORT) {
    const { links = [] } = await chrome.storage.local.get("links");
    if (!links.length) return;
    const body = links.map((l) => `${l.text}\t${l.url}`).join("\n") + "\n";
    const url = "data:text/plain;charset=utf-8," + encodeURIComponent(body);
    chrome.downloads.download({ url, filename: "links.txt", conflictAction: "uniquify" });
  } else if (info.menuItemId === CLEAR) {
    await chrome.storage.local.set({ links: [] });
    setBadge(0);
  }
});

chrome.storage.local.get("links").then(({ links = [] }) => setBadge(links.length));
