(function () {
  var params = new URLSearchParams(window.location.search);
  var episodeId = params.get("episode") || "";
  var t = Number(params.get("t") || 0);
  if (t > 100000) t = Math.floor(t / 1000);
  if (t < 0 || !isFinite(t)) t = 0;

  var titleEl = document.getElementById("listen-title");
  var metaEl = document.getElementById("listen-meta");
  var statusEl = document.getElementById("listen-status");
  var audio = document.getElementById("clip-audio");

  function clock(sec) {
    sec = Math.max(0, Math.floor(sec));
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var pad = function (n) {
      return n < 10 ? "0" + n : String(n);
    };
    return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
  }

  function seekAndPlay() {
    if (!isFinite(audio.duration) || audio.duration === 0) return;
    var start = Math.min(t, Math.max(0, audio.duration - 0.25));
    try {
      audio.currentTime = start;
    } catch (err) {}
    statusEl.textContent = "Playing from " + clock(start);
    var play = audio.play();
    if (play && play.catch) {
      play.catch(function () {
        statusEl.textContent =
          "Ready at " + clock(start) + " — press play if the browser blocked autoplay.";
      });
    }
  }

  if (!episodeId) {
    titleEl.textContent = "Missing episode";
    statusEl.textContent = "This link has no episode id.";
    return;
  }

  fetch("/api/clip?episode=" + encodeURIComponent(episodeId))
    .then(function (res) {
      if (!res.ok) throw new Error("Episode not found");
      return res.json();
    })
    .then(function (data) {
      titleEl.textContent = data.episode_title || "Episode";
      metaEl.textContent = [data.podcast_title, data.podcast_author]
        .filter(Boolean)
        .join(" · ");
      document.title = (data.episode_title || "Clip") + " · Transcript Search";
      if (!data.audio_url) {
        statusEl.textContent = "No audio file is stored for this episode.";
        return;
      }
      audio.addEventListener("loadedmetadata", seekAndPlay);
      audio.addEventListener("canplay", function onCanPlay() {
        audio.removeEventListener("canplay", onCanPlay);
        seekAndPlay();
      });
      audio.src = data.audio_url;
      audio.load();
    })
    .catch(function (err) {
      titleEl.textContent = "Could not open clip";
      statusEl.textContent = err.message || "Lookup failed.";
    });
})();
