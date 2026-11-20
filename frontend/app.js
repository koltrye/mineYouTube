const app = document.getElementById("app");
const token = () => localStorage.getItem("token");
const headers = () => token() ? { Authorization: `Bearer ${token()}` } : {};
async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  if (!res.ok) throw new Error(await res.text().catch(() => "Request failed"));
  return res.json();
}
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
function avatar(name) { return `<div class="avatar">${esc(name?.[0]?.toUpperCase() || "U")}</div>`; }
function card(v) {
  return `<a class="video-card" href="#/watch/${v.id}">
    <div class="thumb">${v.thumbnail_url ? `<img src="${esc(v.thumbnail_url)}" alt="">` : `<span class="thumb-fallback">▶</span>`}</div>
    <div class="card-info">${avatar(v.owner.display_name)}
      <div><h3>${esc(v.title)}</h3><div class="meta">${esc(v.owner.display_name)}<br>${v.views} views</div></div>
    </div>
  </a>`;
}
async function renderFeed(q = "") {
  app.innerHTML = `<div class="video-grid">Loading…</div>`;
  try {
    const videos = await api(`/api/videos${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    app.innerHTML = `<div class="video-grid">${videos.map(card).join("") || "<p>No videos found.</p>"}</div>`;
  } catch (e) { app.innerHTML = `<p>${esc(e.message)}</p>`; }
}
async function renderWatch(id) {
  app.innerHTML = "<p>Loading…</p>";
  try {
    const v = await api(`/api/videos/${id}`);
    const comments = await api(`/api/videos/${id}/comments`);
    app.innerHTML = `<div class="watch-layout">
      <section>
        <video class="player" src="${esc(v.video_url)}" controls autoplay></video>
        <h1 class="watch-title">${esc(v.title)}</h1>
        <div class="watch-actions">
          <a href="#/channel/${esc(v.owner.username)}" class="avatar" title="${esc(v.owner.display_name)}">${esc(v.owner.display_name[0]?.toUpperCase())}</a>
          <button id="likeButton" class="action-pill ${v.liked ? "liked" : ""}">👍 <span>${v.likes}</span></button>
          <button id="reportButton" class="action-pill">⚑ Report</button>
        </div>
        <div class="description"><b>${v.views} views</b><br>${esc(v.description)}</div>
        <section class="comments"><h3>${comments.length} Comments</h3>
          <form id="commentForm" class="comment-form"><input name="text" placeholder="Add a comment…" required><button class="primary">Comment</button></form>
          <div id="commentList">${comments.map(c => `<div class="comment">${avatar(c.user.display_name)}<div><b>${esc(c.user.display_name)}</b><p>${esc(c.text)}</p></div></div>`).join("")}</div>
        </section>
      </section>
      <aside></aside>
    </div>`;
    document.getElementById("likeButton").onclick = async () => {
      if (!token()) return openAuth();
      const data = await api(`/api/videos/${id}/like`, { method:"POST" });
      const button = document.getElementById("likeButton");
      button.classList.toggle("liked", data.liked);
      button.querySelector("span").textContent = data.likes;
    };
    document.getElementById("reportButton").onclick = async () => {
      if (!token()) return openAuth();
      const reason = prompt("Why are you reporting this video?");
      if (reason) await api(`/api/videos/${id}/report`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({reason}) });
    };
    document.getElementById("commentForm").onsubmit = async e => {
      e.preventDefault();
      if (!token()) return openAuth();
      const input = e.currentTarget.elements.text;
      const c = await api(`/api/videos/${id}/comments`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text:input.value}) });
      document.getElementById("commentList").insertAdjacentHTML("afterbegin", `<div class="comment">${avatar(c.user.display_name)}<div><b>${esc(c.user.display_name)}</b><p>${esc(c.text)}</p></div></div>`);
      input.value = "";
    };
  } catch (e) { app.innerHTML = "<h2>Video unavailable</h2>"; }
}
async function renderChannel(username) {
  app.innerHTML = "<p>Loading…</p>";
  try {
    const data = await api(`/api/channels/${encodeURIComponent(username)}`);
    app.innerHTML = `<div class="channel-header">
      ${avatar(data.channel.display_name)}
      <div><h1>${esc(data.channel.display_name)}</h1><div class="meta">@${esc(data.channel.username)} · ${data.subscriber_count} subscribers</div></div>
      <button id="subscribeButton" class="primary">${data.subscribed ? "Subscribed" : "Subscribe"}</button>
    </div><div class="video-grid">${data.videos.map(card).join("") || "<p>This channel has no videos.</p>"}</div>`;
    document.getElementById("subscribeButton").onclick = async () => {
      if (!token()) return openAuth();
      const result = await api(`/api/channels/${encodeURIComponent(username)}/subscribe`, {method:"POST"});
      document.getElementById("subscribeButton").textContent = result.subscribed ? "Subscribed" : "Subscribe";
    };
  } catch (e) { app.innerHTML = "<h2>Channel not found</h2>"; }
}
async function renderModeration() {
  if (!token()) return openAuth();
  app.innerHTML = "<p>Loading reports…</p>";
  try {
    const reports = await api("/api/moderation/reports");
    app.innerHTML = `<h1>Moderation</h1>${reports.map(r => `
      <div class="description" style="margin:12px 0">
        <b>${esc(r.video.title)}</b><br>${esc(r.reason)}
        <button class="action-pill" data-video="${r.video.id}" style="float:right">Hide video</button>
      </div>`).join("") || "<p>No unresolved reports.</p>"}`;
    document.querySelectorAll("[data-video]").forEach(button => button.onclick = async () => {
      await api(`/api/moderation/videos/${button.dataset.video}/hide`, {method:"POST"});
      button.closest(".description").remove();
    });
  } catch (e) { app.innerHTML = `<h2>Moderator access required</h2><p>${esc(e.message)}</p>`; }
}
function route() {
  const hash = location.hash.slice(1) || "/";
  if (hash.startsWith("/watch/")) renderWatch(hash.split("/")[2]);
  else if (hash.startsWith("/channel/")) renderChannel(decodeURIComponent(hash.split("/")[2]));
  else if (hash === "/moderation") renderModeration();
  else renderFeed();
}

const authDialog = document.getElementById("authDialog");
const uploadDialog = document.getElementById("uploadDialog");
let registerMode = false;
function openAuth() {
  authDialog.showModal();
  document.getElementById("authTitle").textContent = registerMode ? "Create account" : "Sign in";
  document.getElementById("registerFields").hidden = !registerMode;
}
document.getElementById("authButton").onclick = () => openAuth();
document.getElementById("closeAuth").onclick = () => authDialog.close();
document.getElementById("authSwitch").onclick = () => { registerMode = !registerMode; openAuth(); };
document.getElementById("authForm").onsubmit = async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget));
  try {
    const result = await api(`/api/auth/${registerMode ? "register" : "login"}`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data) });
    localStorage.setItem("token", result.token);
    localStorage.setItem("user", JSON.stringify(result.user));
    authDialog.close();
    updateUser();
  } catch (e) { alert(e.message); }
};
function updateUser() {
  const user = JSON.parse(localStorage.getItem("user") || "null");
  const button = document.getElementById("authButton");
  button.textContent = user ? user.display_name : "Sign in";
  button.onclick = () => { if (user) { if(confirm("Sign out?")) { localStorage.clear(); updateUser(); route(); } } else openAuth(); };
}
document.getElementById("uploadTop").onclick = () => { if(!token()) openAuth(); else uploadDialog.showModal(); };
document.getElementById("closeUpload").onclick = () => uploadDialog.close();
document.getElementById("uploadForm").onsubmit = e => {
  e.preventDefault();
  const form = e.currentTarget;
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/videos/upload");
  xhr.setRequestHeader("Authorization", `Bearer ${token()}`);
  xhr.upload.onprogress = event => {
    if (!event.lengthComputable) return;
    const percent = Math.round(event.loaded / event.total * 100);
    document.getElementById("uploadProgress").hidden = false;
    const progress = document.querySelector("#uploadProgress progress");
    progress.value = percent;
    progress.nextElementSibling.textContent = `${percent}%`;
  };
  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) { uploadDialog.close(); form.reset(); location.hash = "#/"; route(); }
    else alert(xhr.responseText);
  };
  xhr.send(new FormData(form));
};
document.getElementById("searchForm").onsubmit = e => {
  e.preventDefault();
  renderFeed(document.getElementById("searchInput").value);
};
window.addEventListener("hashchange", route);
updateUser();
route();
