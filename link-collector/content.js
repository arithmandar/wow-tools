// Chrome's context menu API doesn't expose the link text, so capture it on right-click.
document.addEventListener(
  "contextmenu",
  (e) => {
    const a = e.target.closest && e.target.closest("a[href]");
    const text = a ? (a.innerText || a.textContent || a.title || "").trim().replace(/\s+/g, " ") : "";
    chrome.runtime.sendMessage({ type: "linkText", text });
  },
  true
);
