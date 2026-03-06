import { DuckViewer } from "./duck_viewer.js";

const socket = io();

const viewers = {
    left: new DuckViewer(document.getElementById("viewer-left")),
    right: new DuckViewer(document.getElementById("viewer-right")),
};

function setPlaceholder(side, isVisible) {
    const el = document.getElementById(`placeholder-${side}`);
    el.style.display = isVisible ? "flex" : "none";
}

function setUid(side, uid) {
    const el = document.getElementById(`uid-${side}`);
    el.textContent = uid ? `UID: ${uid}` : "";
}

function renderInfo(side, duck) {
    const info = document.getElementById(`info-${side}`);

    if (!duck) {
        info.innerHTML = "";
        return;
    }

    const adjectives = Array.isArray(duck.adjectives)
        ? duck.adjectives.join(", ")
        : "";

    const s = duck.stats || {};
    info.innerHTML = `
    <div class="row"><span class="label">Assembler</span> ${duck.assembler ?? ""}</div>
    <div class="row"><span class="label">Name</span> ${duck.name ?? ""}</div>
    <div class="row"><span class="label">Adjectives</span> ${adjectives}</div>
    <div class="row"><span class="label">Bio</span> ${duck.bio ?? ""}</div>

    <div class="stats">
      <div class="stat"><div class="k">Strength</div><div class="v">${s.strength ?? "—"}</div></div>
      <div class="stat"><div class="k">Health</div><div class="v">${s.health ?? "—"}</div></div>
      <div class="stat"><div class="k">Focus</div><div class="v">${s.focus ?? "—"}</div></div>
      <div class="stat"><div class="k">Intelligence</div><div class="v">${s.intelligence ?? "—"}</div></div>
      <div class="stat"><div class="k">Kindness</div><div class="v">${s.kindness ?? "—"}</div></div>
    </div>
  `;
}

async function handlePortalUpdate({ side, uid, duck }) {
    if (!side || !viewers[side]) return;

    setPlaceholder(side, false);
    setUid(side, uid);
    renderInfo(side, duck);

    await viewers[side].showDuck(duck);
}

function handlePortalClear({ side }) {
    if (!side || !viewers[side]) return;

    viewers[side].clearDuck();
    setUid(side, "");
    renderInfo(side, null);
    setPlaceholder(side, true);
}

socket.on("portal_update", handlePortalUpdate);
socket.on("portal_clear", handlePortalClear);

// Optional: show connection status in console
socket.on("connect", () => console.log("Socket connected"));
socket.on("disconnect", () => console.log("Socket disconnected"));
