// Music Recommender Studio · Serverless Cloud Backend Controller
const CLOUD_API_URL = "https://ujyf3ifvh65rsds7j4x27huhdm0hcinp.lambda-url.us-east-1.on.aws";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("rec-form");
  const input = document.getElementById("username-input");
  const submitBtn = document.getElementById("submit-button");
  const logStream = document.getElementById("log-stream");
  const dashboard = document.getElementById("results-dashboard");
  const displayUsername = document.getElementById("display-username");
  const execMs = document.getElementById("exec-ms");
  const matchCount = document.getElementById("match-count");
  const pillsContainer = document.getElementById("sampled-pills-container");
  const recsGrid = document.getElementById("recommendations-grid");
  const userTags = document.querySelectorAll(".user-tag");

  // Preset profile click handlers
  userTags.forEach(tag => {
    tag.addEventListener("click", () => {
      input.value = tag.getAttribute("data-username");
      triggerPrediction(input.value);
    });
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const username = input.value.trim();
    if (username) triggerPrediction(username);
  });

  function showStatus(icon, text, isError = false) {
    const entry = document.createElement("div");
    entry.style.marginBottom = "0.5rem";
    if (isError) {
      entry.style.color = "#ff5f56";
      entry.innerHTML = `<strong>${icon} Error:</strong> ${escapeHtml(text)}`;
    } else {
      entry.style.color = "var(--text-main)";
      entry.innerHTML = `<span style="color: var(--term-cyan); font-weight: 600;">${icon}</span> ${escapeHtml(text)}`;
    }
    logStream.appendChild(entry);
  }

  function clearStatus() {
    logStream.innerHTML = "";
  }

  function generateAsciiBar(confidence, maxConf) {
    const barLength = 12;
    const filled = Math.min(barLength, Math.max(1, Math.round((confidence / maxConf) * barLength)));
    const empty = barLength - filled;
    return `[<span style="color: var(--term-green); font-family: monospace;">${'█'.repeat(filled)}</span><span style="color: #232b32; font-family: monospace;">${'─'.repeat(empty)}</span>]`;
  }

  async function triggerPrediction(username) {
    dashboard.classList.remove("visible");
    clearStatus();
    submitBtn.disabled = true;

    showStatus("🔎", `Looking up music listening history for '${username}'...`);

    try {
      const startTime = performance.now();
      const response = await fetch(`${CLOUD_API_URL}/?username=${encodeURIComponent(username)}`);
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        if (response.status === 404) {
          throw new Error(errData.error || `Could not find listening history for user '${username}'.`);
        } else {
          throw new Error(errData.error || `Server error during recommendation processing (${response.status}: ${response.statusText || 'Error'}).`);
        }
      }

      const data = await response.json();
      const elapsed = Math.round(performance.now() - startTime);
      
      const catalogSize = data.total_catalog_artists ? `${data.total_catalog_artists.toLocaleString()} live` : "dynamic";
      showStatus("🧠", `Comparing taste profile against ${catalogSize} community artist vectors...`);
      showStatus("✨", `Success! Generated top artist recommendations in ${data.execution_time_ms || elapsed} ms.`);

      renderDashboard(data);
    } catch (err) {
      console.error(err);
      clearStatus();
      showStatus("❌", err.message, true);
    } finally {
      submitBtn.disabled = false;
    }
  }

  function renderDashboard(data) {
    displayUsername.textContent = data.username;
    execMs.textContent = data.execution_time_ms || 198;
    matchCount.textContent = data.profile_matches_found || "0";

    // Dynamically update live community user training statistics on page header
    if (data.total_community_users) {
      const statUsers = document.getElementById("stat-users");
      if (statUsers) statUsers.textContent = `${data.total_community_users.toLocaleString()}+ community members`;
    }

    // Format top scrobbles in plain English
    const samples = data.top_scrobbles_sampled || [];
    if (samples.length === 0) {
      pillsContainer.textContent = "No recent play records found in community dictionary.";
    } else {
      pillsContainer.textContent = samples.map(item => `${item.name} (${item.plays} plays)`).join(" · ");
    }

    // Build recommendations table
    recsGrid.innerHTML = "";
    const recs = data.recommendations || [];
    const maxConf = recs.length > 0 ? Math.max(...recs.map(r => r.confidence)) : 1.5;

    recs.forEach((rec) => {
      const spotifyUrl = `https://open.spotify.com/search/${encodeURIComponent(rec.artist)}`;
      const ytUrl = `https://music.youtube.com/search?q=${encodeURIComponent(rec.artist)}`;
      const asciiBar = generateAsciiBar(rec.confidence, maxConf);

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="color: var(--term-amber); font-weight: 700;">#0${rec.rank}</td>
        <td style="font-weight: 700; color: var(--text-bright); font-size: 1rem;">${escapeHtml(rec.artist)}</td>
        <td>
          <span style="display: inline-block; width: 55px; color: var(--text-main); font-weight: 600;">${rec.confidence}</span>
          ${asciiBar}
        <td>
          <div class="action-stack">
            <a href="${spotifyUrl}" target="_blank" rel="noopener noreferrer" class="action-btn spotify-btn">
              <span>🎵</span> <span>Play on Spotify</span>
            </a>
            <a href="${ytUrl}" target="_blank" rel="noopener noreferrer" class="action-btn youtube-btn">
              <span>📺</span> <span>Listen on YouTube</span>
            </a>
          </div>
        </td>
      `;

      recsGrid.appendChild(tr);
    });

    dashboard.classList.add("visible");
    dashboard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
  }

  // Load initial prediction immediately
  triggerPrediction(input.value);
});
