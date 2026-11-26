// HarnoRb als installierbare App (PWA). Bewusst ohne Zwischenspeicher: Die Oberfläche lebt vom
// lokalen Server, und alte Stände im Cache haben schon einmal Fehler verdeckt.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
