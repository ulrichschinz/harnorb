// Leser im Theme der Szene: beim Laden vom Server, danach per Nachricht der Szene (gleicher Ursprung).
import { leserVariablen, setzeVariablen, ladeTheme } from "/static/theme.js";

const anwenden = (t) => setzeVariablen(leserVariablen(t));
ladeTheme().then(anwenden).catch(() => {});
addEventListener("message", (e) => {
  if (e.origin === location.origin && e.data && typeof e.data.theme === "object") anwenden(e.data.theme);
});
