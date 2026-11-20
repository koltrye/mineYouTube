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
function duration(seconds) {
  const mins = Math.floor((seconds || 0) / 60);
  return `${mins}:${String((seconds || 0) % 60).padStart(2, "0")}`;
}
function card(v) {
  return `<a class="video-card" href="#/watch/${v.id}">
    <div class="thumb">${v.thumbnail_url ? `<img src="${esc(v.thumbnail_url)}" alt="">` : `<span class="thumb-fallback">▶</span>`}<span class="duration">${duration(v.duration_seconds)}</span></div>
    <div class="card-info">${avatar(v.owner.display_name)}
      <div><h3>${esc(v.title)}</h3><div class="meta">${esc(v.owner.display_name)}<br>${Number(v.views).toLocaleString()} views</div></div>
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
async function renderSubscriptions() {
  if (!token()) return openAuth();
  app.innerHTML = "<p>Loading subscriptions…</p>";
  try {
    const videos = await api("/api/subscriptions");
    app.innerHTML = `<h1>Latest from your subscriptions</h1><div class="video-grid">${videos.map(card).join("") || "<p>New videos from channels you follow will appear here.</p>"}</div>`;
  } catch (e) { app.innerHTML = `<p>${esc(e.message)}</p>`; }
}
async function renderWatch(id) {
  app.innerHTML = "<p>Loading…</p>";
  try {
    const v = await api(`/api/videos/${id}`);
    const comments = await api(`/api/videos/${id}/comments`);
    let related = [];
    try { related = (await api("/api/videos")).filter(item => item.id !== v.id).slice(0, 8); }
    catch (e) { console.error("Could not load recommendations", e); }
    const viewer = JSON.parse(localStorage.getItem("user") || "null");
    const isOwner = viewer?.id === v.owner.id;
    app.innerHTML = `<div class="watch-layout">
      <section>
        <video class="player" src="${esc(v.video_url)}" controls autoplay></video>
        <h1 class="watch-title">${esc(v.title)}</h1>
        <div class="watch-actions">
          <a href="#/channel/${esc(v.owner.username)}" class="avatar" title="${esc(v.owner.display_name)}">${esc(v.owner.display_name[0]?.toUpperCase())}</a>
          <a class="channel-name" href="#/channel/${esc(v.owner.username)}">${esc(v.owner.display_name)}</a>
          <button id="likeButton" class="action-pill ${v.liked ? "liked" : ""}">👍 <span>${v.likes}</span></button>
          ${token() ? '<button id="saveButton" class="action-pill">▣ Save</button>' : ""}
          ${isOwner && v.visibility === "private" ? '<button id="permissionButton" class="action-pill">Share privately</button>' : ""}
          <button id="reportButton" class="action-pill">⚑ Report</button>
        </div>
        <div class="description"><b>${Number(v.views).toLocaleString()} views</b><br>${esc(v.description)}</div>
        <section class="comments"><h3>${comments.length} Comments</h3>
          <form id="commentForm" class="comment-form"><input name="text" placeholder="Add a comment…" required><button class="primary">Comment</button></form>
          <div id="commentList">${comments.map(c => `<div class="comment">${avatar(c.user.display_name)}<div><b>${esc(c.user.display_name)}</b><p>${esc(c.text)}</p></div></div>`).join("")}</div>
        </section>
      </section>
      <aside class="related"><h3>Up next</h3>${related.map(card).join("") || "<p>No other videos yet.</p>"}</aside>
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
      if (reason) {
        try {
          await api(`/api/videos/${id}/report`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({reason}) });
          alert("Report submitted");
        } catch (e) { alert(e.message); }
      }
    };
    const saveButton = document.getElementById("saveButton");
    if (saveButton) saveButton.onclick = async () => {
      try {
        const viewer = JSON.parse(localStorage.getItem("user") || "null");
        const channel = await api(`/api/channels/${encodeURIComponent(viewer.username)}`);
        let playlists = channel.playlists;
        if (!playlists.length) {
          const title = prompt("Name your new playlist");
          if (!title?.trim()) return;
          const playlist = await api("/api/playlists", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({title})});
          playlists = [playlist];
        } else {
          const options = playlists.map((item, index) => `${index + 1}. ${item.title}`).join("\n");
          const choice = Number(prompt(`Save to which playlist?\n${options}\nEnter its number`));
          if (!Number.isInteger(choice) || choice < 1 || choice > playlists.length) return;
          playlists = [playlists[choice - 1]];
        }
        await api(`/api/playlists/${playlists[0].id}/videos`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({video_id:Number(id)})});
        alert("Added to playlist");
      } catch (e) { alert(e.message); }
    };
    const permissionButton = document.getElementById("permissionButton");
    if (permissionButton) permissionButton.onclick = async () => {
      const username = prompt("Grant access to which username?");
      if (!username?.trim()) return;
      try {
        await api(`/api/videos/${id}/permissions`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({username:username.trim()})});
        alert("Private video access granted");
      } catch (e) { alert(e.message); }
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
  if (!username) {
    const user = JSON.parse(localStorage.getItem("user") || "null");
    if (!user) return openAuth();
    username = user.username;
  }
  app.innerHTML = "<p>Loading…</p>";
  try {
    const data = await api(`/api/channels/${encodeURIComponent(username)}`);
    app.innerHTML = `<div class="channel-header">
      ${avatar(data.channel.display_name)}
      <div><h1>${esc(data.channel.display_name)}</h1><div class="meta">@${esc(data.channel.username)} · ${data.subscriber_count} subscribers</div></div>
      <button id="subscribeButton" class="primary">${data.subscribed ? "Subscribed" : "Subscribe"}</button>
    </div>
    <div class="channel-tabs"><button class="channel-tab selected" data-tab="videos">Videos</button><button class="channel-tab" data-tab="playlists">Playlists</button></div>
    <div id="channelContent" class="video-grid">${data.videos.map(card).join("") || "<p>This channel has no videos.</p>"}</div>`;
    const ownChannel = JSON.parse(localStorage.getItem("user") || "null")?.username === username;
    const subscribeButton = document.getElementById("subscribeButton");
    if (ownChannel) subscribeButton.hidden = true;
    subscribeButton.onclick = async () => {
      if (!token()) return openAuth();
      try {
        const result = await api(`/api/channels/${encodeURIComponent(username)}/subscribe`, {method:"POST"});
        subscribeButton.textContent = result.subscribed ? "Subscribed" : "Subscribe";
      } catch (e) { alert(e.message); }
    };
    document.querySelectorAll(".channel-tab").forEach(button => button.onclick = async () => {
      document.querySelectorAll(".channel-tab").forEach(tab => tab.classList.toggle("selected", tab === button));
      const content = document.getElementById("channelContent");
      if (button.dataset.tab === "videos") {
        content.classList.add("video-grid");
        content.innerHTML = data.videos.map(card).join("") || "<p>This channel has no videos.</p>";
      }
      else {
        content.classList.remove("video-grid");
        content.innerHTML = `<div class="playlist-list">${data.playlists.map(p => `<a class="playlist-card" href="#/playlist/${p.id}"><span class="playlist-cover">♫</span><b>${esc(p.title)}</b><small>${p.video_count} videos</small></a>`).join("") || "<p>No playlists yet.</p>"}</div>${ownChannel ? '<button id="newPlaylist" class="primary">Create playlist</button>' : ""}`;
        if (ownChannel) document.getElementById("newPlaylist").onclick = async () => {
          const title = prompt("Playlist name");
          if (!title?.trim()) return;
          try {
            await api("/api/playlists", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({title})});
            renderChannel(username);
          } catch (e) { alert(e.message); }
        };
      }
    });
  } catch (e) { app.innerHTML = "<h2>Channel not found</h2>"; }
}
async function renderPlaylist(id) {
  app.innerHTML = "<p>Loading playlist…</p>";
  try {
    const playlist = await api(`/api/playlists/${id}`);
    app.innerHTML = `<header class="playlist-header"><p>Playlist · ${esc(playlist.owner.display_name)}</p><h1>${esc(playlist.title)}</h1><p>${esc(playlist.description)}</p><span>${playlist.video_count} videos · ${esc(playlist.visibility)}</span></header><div class="video-grid">${playlist.videos.map(card).join("") || "<p>This playlist is empty.</p>"}</div>`;
  } catch (e) { app.innerHTML = "<h2>Playlist unavailable</h2>"; }
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
  else if (hash === "/channel") renderChannel("");
  else if (hash.startsWith("/playlist/")) renderPlaylist(hash.split("/")[2]);
  else if (hash === "/subscriptions") renderSubscriptions();
  else if (hash === "/moderation") renderModeration();
  else renderFeed();
}

const authDialog = document.getElementById("authDialog");
const uploadDialog = document.getElementById("uploadDialog");
let registerMode = false;
function openAuth() {
  if (!authDialog.open) authDialog.showModal();
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
    route();
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
  xhr.upload.onload = () => {
    document.querySelector("#uploadProgress span").textContent = "Processing video…";
  };
  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) { uploadDialog.close(); form.reset(); location.hash = "#/"; route(); }
    else alert(xhr.responseText);
  };
  xhr.onerror = () => alert("Upload failed. Check your connection and try again.");
  xhr.send(new FormData(form));
};
document.getElementById("searchForm").onsubmit = e => {
  e.preventDefault();
  renderFeed(document.getElementById("searchInput").value);
};
window.addEventListener("hashchange", route);
updateUser();
route();
