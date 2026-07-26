// Music Recommender Studio · Serverless Cloud Backend Controller
const IS_LOCAL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const CLOUD_API_URL = IS_LOCAL ? "/api/recommend" : "https://ujyf3ifvh65rsds7j4x27huhdm0hcinp.lambda-url.us-east-1.on.aws";

document.addEventListener("DOMContentLoaded", () => {
  // Classic Account Mode Elements
  const form = document.getElementById("rec-form");
  const input = document.getElementById("username-input");
  const submitBtn = document.getElementById("submit-button");
  const userTags = document.querySelectorAll(".user-tag");
  const usernameModeContainer = document.getElementById("username-mode-container");

  // Mode Toggle Switcher
  const modeBtnUser = document.getElementById("mode-btn-user");
  const modeBtnCustom = document.getElementById("mode-btn-custom");

  // Custom Studio Mixer Elements
  const customMixerContainer = document.getElementById("custom-mixer-container");
  const artistAutoInput = document.getElementById("artist-auto-input");
  const autocompleteDropdown = document.getElementById("autocomplete-dropdown");
  const pillsStage = document.getElementById("pills-stage");
  const mixerCount = document.getElementById("mixer-count");
  const clearMixerBtn = document.getElementById("clear-mixer-btn");
  const generateCustomBtn = document.getElementById("generate-custom-btn");

  // Output Elements
  const logStream = document.getElementById("log-stream");
  const dashboard = document.getElementById("results-dashboard");
  const displayUsername = document.getElementById("display-username");
  const execMs = document.getElementById("exec-ms");
  const matchCount = document.getElementById("match-count");
  const pillsContainer = document.getElementById("sampled-pills-container");
  const recsGrid = document.getElementById("recommendations-grid");

  // Custom Mixer State
  let customProfile = []; // Array of { name: str, rating: num }
  let autocompleteTimeout = null;
  let focusedIndex = -1;

  // --- 1. MODE TOGGLE LOGIC ---
  modeBtnUser.addEventListener("click", () => {
    modeBtnUser.classList.add("active-mode");
    modeBtnCustom.classList.remove("active-mode");
    usernameModeContainer.style.display = "block";
    customMixerContainer.style.display = "none";
  });

  modeBtnCustom.addEventListener("click", () => {
    modeBtnCustom.classList.add("active-mode");
    modeBtnUser.classList.remove("active-mode");
    usernameModeContainer.style.display = "none";
    customMixerContainer.style.display = "block";
    artistAutoInput.focus();
  });

  // --- 2. CLASSIC USER PRESETS & SUBMIT ---
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

  // --- 3. AUTOCOMPLETE & CUSTOM MIXER LOGIC ---
  artistAutoInput.addEventListener("input", (e) => {
    const query = e.target.value.trim();
    focusedIndex = -1;
    if (!query || query.length < 2) {
      autocompleteDropdown.style.display = "none";
      return;
    }

    if (autocompleteTimeout) clearTimeout(autocompleteTimeout);
    autocompleteTimeout = setTimeout(() => fetchAutocomplete(query), 160);
  });

  artistAutoInput.addEventListener("keydown", (e) => {
    const items = autocompleteDropdown.querySelectorAll(".autocomplete-item");
    if (e.key === "Enter") {
      e.preventDefault();
      if (items && items.length > 0 && focusedIndex >= 0 && focusedIndex < items.length) {
        items[focusedIndex].click();
      } else if (e.target.value.trim().length >= 2) {
        addArtistToMixer(e.target.value.trim(), 5.0);
        artistAutoInput.value = "";
        autocompleteDropdown.style.display = "none";
      }
      return;
    }
    if (!items || items.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusedIndex = (focusedIndex + 1) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusedIndex = (focusedIndex - 1 + items.length) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "Escape") {
      autocompleteDropdown.style.display = "none";
    }
  });

  function updateFocusedItem(items) {
    items.forEach((item, idx) => {
      if (idx === focusedIndex) {
        item.classList.add("focused");
        item.scrollIntoView({ block: "nearest" });
      } else {
        item.classList.remove("focused");
      }
    });
  }

  document.addEventListener("click", (e) => {
    if (!artistAutoInput.contains(e.target) && !autocompleteDropdown.contains(e.target)) {
      autocompleteDropdown.style.display = "none";
    }
  });

  async function fetchAutocomplete(query) {
    try {
      const res = await fetch(`${CLOUD_API_URL}/?autocomplete=${encodeURIComponent(query)}`);
      if (!res.ok) return;
      const data = await res.json();
      renderAutocompleteDropdown(data.matches || []);
    } catch (err) {
      console.warn("Autocomplete lookup failed:", err);
    }
  }

  function renderAutocompleteDropdown(matches) {
    autocompleteDropdown.innerHTML = "";
    if (matches.length === 0) {
      autocompleteDropdown.style.display = "none";
      return;
    }

    matches.forEach(name => {
      const li = document.createElement("li");
      li.className = "autocomplete-item";
      li.textContent = name;
      li.addEventListener("click", () => {
        addArtistToMixer(name, 5.0);
        artistAutoInput.value = "";
        autocompleteDropdown.style.display = "none";
        artistAutoInput.focus();
      });
      autocompleteDropdown.appendChild(li);
    });

    autocompleteDropdown.style.display = "block";
  }

  function addArtistToMixer(name, defaultRating = 5.0) {
    if (!customProfile.some(a => a.name.toLowerCase() === name.toLowerCase())) {
      customProfile.push({ name: name, rating: defaultRating });
      renderMixerStage();
    }
  }

  function renderMixerStage() {
    pillsStage.innerHTML = "";
    const count = customProfile.length;

    if (count === 0) {
      pillsStage.innerHTML = `<div id="empty-stage-msg" style="color: var(--term-dim); font-style: italic; font-size: 0.9rem;">No artists added yet! Use the box above to search and select favorite bands or artists you dislike.</div>`;
      mixerCount.textContent = `0 / 5 Artists Added (Add ≥ 5 for precision!)`;
      mixerCount.style.color = "var(--term-amber)";
      clearMixerBtn.style.display = "none";
      generateCustomBtn.disabled = true;
      generateCustomBtn.style.opacity = "0.5";
      generateCustomBtn.style.cursor = "not-allowed";
      return;
    }

    clearMixerBtn.style.display = "inline-block";
    generateCustomBtn.disabled = false;
    generateCustomBtn.style.opacity = "1";
    generateCustomBtn.style.cursor = "pointer";

    if (count >= 5) {
      mixerCount.textContent = `${count} Artists Loaded (⚡ Optimal Acoustic Triangulation!)`;
      mixerCount.style.color = "var(--term-green)";
      generateCustomBtn.style.background = "var(--term-green)";
      generateCustomBtn.style.color = "var(--bg-terminal)";
    } else {
      mixerCount.textContent = `${count} / 5 Artists Added (Add ${5 - count} more for optimal precision!)`;
      mixerCount.style.color = "var(--term-amber)";
      generateCustomBtn.style.background = "var(--bg-terminal)";
      generateCustomBtn.style.color = "var(--term-green)";
    }

    customProfile.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = `artist-pill-card ${item.rating < 0 ? "negative-card" : ""}`;
      
      const icon = item.rating >= 4 ? "🔥" : item.rating > 0 ? "👍" : item.rating === -3 ? "👎" : "🚫";
      card.innerHTML = `
        <div class="artist-pill-name">${icon} ${escapeHtml(item.name)}</div>
        <div class="rating-btn-group">
          <button type="button" class="rating-btn ${item.rating === 5 ? 'active-rating-pos' : ''}" data-rating="5">🔥 +5 Love</button>
          <button type="button" class="rating-btn ${item.rating === 3 ? 'active-rating-pos' : ''}" data-rating="3">👍 +3 Like</button>
          <button type="button" class="rating-btn ${item.rating === -3 ? 'active-rating-neg' : ''}" data-rating="-3">👎 -3 Dislike</button>
          <button type="button" class="rating-btn ${item.rating === -5 ? 'active-rating-neg' : ''}" data-rating="-5">🚫 -5 Ban</button>
          <button type="button" class="remove-artist-btn" title="Remove Artist" aria-label="Remove Artist">❌</button>
        </div>
      `;

      // Rating click events
      const ratingButtons = card.querySelectorAll(".rating-btn");
      ratingButtons.forEach(btn => {
        btn.addEventListener("click", () => {
          customProfile[idx].rating = parseFloat(btn.getAttribute("data-rating"));
          renderMixerStage();
        });
      });

      // Remove button event
      const removeBtn = card.querySelector(".remove-artist-btn");
      removeBtn.addEventListener("click", () => {
        customProfile.splice(idx, 1);
        renderMixerStage();
      });

      pillsStage.appendChild(card);
    });
  }

  clearMixerBtn.addEventListener("click", () => {
    customProfile = [];
    renderMixerStage();
  });

  generateCustomBtn.addEventListener("click", () => {
    if (customProfile.length > 0) {
      triggerCustomPrediction();
    }
  });

  // --- 4. PREDICTION EXECUTORS ---
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
    showStatus("🔎", `Looking up music listening history for '${username}' on ListenBrainz...`);

    try {
      const startTime = performance.now();
      const response = await fetch(`${CLOUD_API_URL}/?username=${encodeURIComponent(username)}`);
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        if (response.status === 404) {
          throw new Error(errData.error || `Could not find listening history for user '${username}'.`);
        } else {
          throw new Error(errData.error || `Server error during recommendation processing (${response.status}).`);
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

  async function triggerCustomPrediction() {
    dashboard.classList.remove("visible");
    clearStatus();
    generateCustomBtn.disabled = true;
    showStatus("🎛️", `Compiling custom acoustic vector (${customProfile.length} active faders)...`);

    try {
      const startTime = performance.now();
      // Format as ?artists=Daft Punk:5,Black Sabbath:-5
      const paramString = customProfile.map(a => `${a.name}:${a.rating}`).join(",");
      const response = await fetch(`${CLOUD_API_URL}/?artists=${encodeURIComponent(paramString)}&username=${encodeURIComponent('Studio Custom Mixer')}`);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || `Server error during custom recommendation processing.`);
      }

      const data = await response.json();
      const elapsed = Math.round(performance.now() - startTime);
      const catalogSize = data.total_catalog_artists ? `${data.total_catalog_artists.toLocaleString()} live` : "dynamic";
      
      showStatus("🧬", `Projecting linear algebra matrix fold-in across ${catalogSize} item embeddings...`);
      if (customProfile.some(a => a.rating < 0)) {
        showStatus("🛡️", `Applying vector cosine similarity damping to penalize disliked acoustic genres!`);
      }
      showStatus("✨", `Success! Discovered your customized Top-10 lineup in ${data.execution_time_ms || elapsed} ms.`);
      renderDashboard(data);
    } catch (err) {
      console.error(err);
      clearStatus();
      showStatus("❌", err.message, true);
    } finally {
      generateCustomBtn.disabled = false;
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
      pillsContainer.textContent = "No active play records found in community dictionary.";
    } else {
      pillsContainer.innerHTML = samples.map(item => {
        if (item.rating_type === 'negative' || item.plays < 0) {
          return `<span style="color: #ff5555; font-weight: 600;">🚫 ${escapeHtml(item.name)} (${item.plays} ban)</span>`;
        } else if (item.rating_type === 'positive') {
          return `<span style="color: var(--term-green); font-weight: 600;">🔥 ${escapeHtml(item.name)} (${item.plays} wt)</span>`;
        } else {
          return `<span>🎵 ${escapeHtml(item.name)} (${item.plays} plays)</span>`;
        }
      }).join(" <span style='color: var(--term-dim);'>·</span> ");
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
