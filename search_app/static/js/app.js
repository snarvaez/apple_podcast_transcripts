$(function () {
  var $form = $("#search-form");
  var $input = $("#q");
  var $results = $("#results");
  var $status = $("#status");
  var BAG_KEY = "podcast-clip-bag";
  var bag = loadBag();

  var ICON_COPY =
    '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 16V6a2 2 0 0 1 2-2h10" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
  var ICON_PLUS =
    '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var ICON_CHECK =
    '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function badgeHtml(types) {
    return (types || [])
      .map(function (type) {
        return '<span class="badge ' + type + '">' + type + "</span>";
      })
      .join("");
  }

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function formatClock(ms) {
    if (ms == null || ms === "") return "";
    var total = Math.max(0, Math.floor(Number(ms) / 1000));
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
  }

  function listenHref(episodeId, startMs) {
    if (!episodeId) return "";
    var u = new URL("/listen", window.location.origin);
    u.searchParams.set("episode", episodeId);
    if (startMs != null && startMs !== "") {
      u.searchParams.set("t", String(Math.floor(Number(startMs) / 1000)));
    }
    return u.toString();
  }

  function shareSeconds(startMs) {
    if (startMs == null || startMs === "") return 0;
    return Math.max(0, Math.floor(Number(startMs) / 1000));
  }

  function nativeHref(episode, startMs) {
    var sec = shareSeconds(startMs);
    var yt =
      (episode && episode.youtube_video_id) ||
      (function () {
        try {
          var u = episode && episode.episode_url;
          if (u && u.indexOf("youtube.com/watch") >= 0) {
            return new URL(u).searchParams.get("v");
          }
        } catch (err) {}
        return "";
      })();
    if (yt) {
      return "https://www.youtube.com/watch?v=" + yt + "&t=" + sec + "s";
    }
    if (episode && episode.spotify_episode_id) {
      return (
        "https://open.spotify.com/episode/" +
        episode.spotify_episode_id +
        "?t=" +
        sec
      );
    }
    if (episode && episode.apple_track_id) {
      var collection = episode.itunes_id || "1500452446";
      return (
        "https://podcasts.apple.com/us/podcast/id" +
        collection +
        "?i=" +
        episode.apple_track_id +
        "&t=" +
        sec
      );
    }
    return listenHref(episode && episode.episode_id, startMs);
  }

  function timestampHref(episodeId, startMs, fallbackUrl) {
    return listenHref(episodeId, startMs) || fallbackUrl || "";
  }

  bag = bag.map(function (item) {
    var eid = item.episode_id || String(item.id || "").split(":")[0];
    item.episode_id = eid;
    item.href = nativeHref(item, item.start_ms) || listenHref(eid, item.start_ms);
    return item;
  });
  saveBag();

  function plainSnippet(html) {
    return $("<div>")
      .html(html || "")
      .text()
      .replace(/\s+/g, " ")
      .trim();
  }

  function clipId(episode, snippet) {
    return [episode.episode_id, snippet.chunk_index, snippet.start_ms].join(":");
  }

  function makeClip(show, episode, snippet) {
    return {
      id: clipId(episode, snippet),
      episode_id: episode.episode_id,
      podcast_title: show.podcast_title,
      episode_title: episode.episode_title,
      text: plainSnippet(snippet.snippet_html),
      start_ms: snippet.start_ms,
      href: nativeHref(episode, snippet.start_ms),
      spotify_episode_id: episode.spotify_episode_id,
      apple_track_id: episode.apple_track_id,
      itunes_id: episode.itunes_id,
      youtube_video_id: episode.youtube_video_id,
      audio_url: snippet.audio_url || episode.audio_url || "",
    };
  }

  function formatClip(item) {
    var href =
      item.href || listenHref(item.episode_id, item.start_ms) || "";
    var lines = [];
    if (href) lines.push(href);
    if (item.podcast_title) lines.push(item.podcast_title);
    if (item.episode_title) lines.push(item.episode_title);
    if (item.start_ms != null && item.start_ms !== "") {
      lines.push("At " + formatClock(item.start_ms));
    }
    if (item.text) lines.push(item.text);
    return lines.join("\n");
  }

  function formatBag(items) {
    return items
      .map(function (item, i) {
        return i + 1 + ".\n" + formatClip(item);
      })
      .join("\n\n");
  }

  function loadBag() {
    try {
      var raw = window.localStorage.getItem(BAG_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function saveBag() {
    try {
      window.localStorage.setItem(BAG_KEY, JSON.stringify(bag));
    } catch (err) {}
  }

  function inBag(id) {
    return bag.some(function (item) {
      return item.id === id;
    });
  }

  function copyText(text, $btn) {
    function mark() {
      if (!$btn || !$btn.length) return;
      $btn.addClass("is-copied");
      if ($btn.is("#bag-copy")) {
        var prev = $btn.text();
        $btn.text("Copied");
        setTimeout(function () {
          $btn.text(prev).removeClass("is-copied");
        }, 1400);
      } else {
        setTimeout(function () {
          $btn.removeClass("is-copied");
        }, 1400);
      }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(mark).catch(function () {
        fallbackCopy(text);
        mark();
      });
      return;
    }
    fallbackCopy(text);
    mark();
  }

  function fallbackCopy(text) {
    var $ta = $("<textarea>")
      .css({ position: "fixed", left: "-9999px" })
      .val(text)
      .appendTo("body");
    $ta[0].select();
    try {
      document.execCommand("copy");
    } catch (err) {}
    $ta.remove();
  }

  function renderBag() {
    $("#bag-count").text(bag.length);
    var $list = $("#bag-list").empty();
    $("#bag-empty").toggle(bag.length === 0);
    $("#bag-copy, #bag-clear").prop("disabled", bag.length === 0);
    bag.forEach(function (item) {
      var $li = $('<li class="bag-item"></li>');
      $li.append($('<div class="show-name"></div>').text(item.podcast_title || ""));
      $li.append($('<div class="ep-name"></div>').text(item.episode_title || ""));
      if (item.start_ms != null && item.start_ms !== "") {
        $li.append($("<div></div>").text("At " + formatClock(item.start_ms)));
      }
      $li.append($('<p class="clip-text"></p>').text(item.text || ""));
      if (item.href) {
        $li.append(
          $('<a class="clip-link"></a>')
            .attr({ href: item.href, target: "_blank", rel: "noopener" })
            .text(item.href)
        );
      }
      $li.append(
        $('<button type="button" class="remove">Remove</button>').attr(
          "data-id",
          item.id
        )
      );
      $list.append($li);
    });
    $results.find(".add-clip").each(function () {
      var id = $(this).data("id");
      $(this)
        .toggleClass("is-on", inBag(id))
        .attr("title", inBag(id) ? "Remove from bag" : "Add to bag")
        .html(inBag(id) ? ICON_CHECK : ICON_PLUS);
    });
  }

  function playFrom(startMs, audioUrl, title, href) {
    if (href && href.indexOf("youtube.com") >= 0) {
      window.open(href, "_blank", "noopener");
      return;
    }
    if (audioUrl) {
      var audio = document.getElementById("player-audio");
      $("#player").removeAttr("hidden");
      $("#player-title").text(title || "Episode");
      $("#player-time").text("from " + formatClock(startMs));
      var seek = function () {
        try {
          audio.currentTime = Number(startMs) / 1000;
        } catch (err) {}
        audio.removeEventListener("loadedmetadata", seek);
      };
      audio.addEventListener("loadedmetadata", seek);
      if (audio.getAttribute("src") !== audioUrl) {
        audio.src = audioUrl;
      } else if (audio.readyState >= 1) {
        seek();
      }
      var playPromise = audio.play();
      if (playPromise && playPromise.catch) {
        playPromise.catch(function () {
          if (href) window.open(href, "_blank", "noopener");
        });
      }
      return;
    }
    if (href) window.open(href, "_blank", "noopener");
  }

  function render(payload) {
    $results.empty();
    var podcasts = payload.podcasts || [];
    if (!payload.query) {
      $status.attr("hidden", true);
      return;
    }
    if (!podcasts.length) {
      $status.attr("hidden", true);
      if (payload.warnings && payload.warnings.length) {
        $results.append(
          $('<p class="error"></p>').text(payload.warnings.join(" "))
        );
        return;
      }
      $results.append(
        '<p class="empty">No matching episodes for “' +
          $("<div>").text(payload.query).html() +
          '”.</p>'
      );
      return;
    }
    var episodeCount = podcasts.reduce(function (n, show) {
      return n + (show.episodes || []).length;
    }, 0);
    $status
      .text(
        episodeCount +
          " episode" +
          (episodeCount === 1 ? "" : "s") +
          " across " +
          podcasts.length +
          " podcast" +
          (podcasts.length === 1 ? "" : "s") +
          (payload.mode ? " · " + payload.mode : "")
      )
      .removeAttr("hidden");

    podcasts.forEach(function (show) {
      var $show = $('<section class="show"></section>');
      $show.append(
        '<div class="show-head"><h2></h2><span class="author"></span></div>'
      );
      $show.find("h2").text(show.podcast_title);
      $show.find(".author").text(show.podcast_author || "");
      (show.episodes || []).forEach(function (episode) {
        var $ep = $('<article class="episode"></article>');
        var title = $("<h3></h3>");
        if (episode.episode_url) {
          title.append(
            $("<a></a>")
              .attr({ href: episode.episode_url, target: "_blank", rel: "noopener" })
              .text(episode.episode_title)
          );
        } else {
          title.text(episode.episode_title);
        }
        $ep.append(title);
        var date = episode.published_at
          ? episode.published_at.slice(0, 10)
          : "";
        $ep.append(
          $('<div class="meta"></div>')
            .append(date ? $("<span></span>").text(date) : "")
            .append($(badgeHtml(episode.match_types)))
        );
        (episode.snippets || []).forEach(function (snippet) {
          var clip = makeClip(show, episode, snippet);
          var $row = $('<div class="snippet-row"></div>');
          $row.append($('<p class="snippet"></p>').html(snippet.snippet_html));
          if (snippet.start_ms != null && snippet.start_ms !== "") {
            var isYt = (clip.href || "").indexOf("youtube.com") >= 0;
            var $play = $('<button type="button" class="play-at"></button>')
              .text((isYt ? "Watch " : "Play ") + formatClock(snippet.start_ms))
              .attr({
                "data-start": snippet.start_ms,
                "data-audio": clip.audio_url,
                "data-title": episode.episode_title,
                "data-href": clip.href,
              });
            $row.append($play);
          }
          var $copy = $('<button type="button" class="icon-btn copy-clip"></button>')
            .attr({
              title: "Copy playable timestamp link",
              type: "button",
              "data-episode": clip.episode_id || "",
              "data-start": clip.start_ms,
              "data-href": clip.href,
            })
            .html(ICON_COPY);
          $copy.data("clip", clip);
          $row.append($copy);
          var $add = $('<button type="button" class="icon-btn add-clip"></button>')
            .attr({
              title: inBag(clip.id) ? "Remove from bag" : "Add to bag",
              "data-id": clip.id,
            })
            .toggleClass("is-on", inBag(clip.id))
            .html(inBag(clip.id) ? ICON_CHECK : ICON_PLUS);
          $add.data("clip", clip);
          $row.append($add);
          $ep.append($row);
        });
        $show.append($ep);
      });
      $results.append($show);
    });
  }

  $results.on("click", ".play-at", function () {
    playFrom(
      $(this).data("start"),
      $(this).data("audio"),
      $(this).data("title"),
      $(this).data("href")
    );
  });

  $results.on("click", ".copy-clip", function () {
    var $btn = $(this).closest(".copy-clip");
    var clip = $btn.data("clip") || {};
    clip.episode_id = clip.episode_id || $btn.attr("data-episode");
    if (clip.start_ms == null || clip.start_ms === "") {
      clip.start_ms = $btn.attr("data-start");
    }
    clip.href =
      nativeHref(clip, clip.start_ms) ||
      $btn.attr("data-href") ||
      listenHref(clip.episode_id, clip.start_ms) ||
      clip.href;
    copyText(formatClip(clip), $btn);
  });

  $results.on("click", ".add-clip", function () {
    var clip = $(this).data("clip");
    if (!clip) return;
    if (inBag(clip.id)) {
      bag = bag.filter(function (item) {
        return item.id !== clip.id;
      });
    } else {
      bag.push(clip);
    }
    saveBag();
    renderBag();
  });

  $("#bag-toggle").on("click", function () {
    var open = !$("#bag-panel").prop("hidden");
    $("#bag-panel").prop("hidden", open);
    $(this).attr("aria-expanded", open ? "false" : "true");
  });

  $("#bag-copy").on("click", function () {
    if (!bag.length) return;
    copyText(formatBag(bag), $(this));
  });

  $("#bag-clear").on("click", function () {
    bag = [];
    saveBag();
    renderBag();
  });

  $("#bag-list").on("click", ".remove", function () {
    var id = $(this).attr("data-id");
    bag = bag.filter(function (item) {
      return item.id !== id;
    });
    saveBag();
    renderBag();
  });

  function runSearch(query) {
    query = $.trim(query || "");
    $input.val(query);
    if (!query) {
      $results.empty();
      $status.attr("hidden", true);
      return;
    }
    $status.text("Searching… keyword + semantic ranking.").removeAttr("hidden");
    if (runSearch._xhr && runSearch._xhr.readyState !== 4) {
      runSearch._xhr.abort();
    }
    runSearch._xhr = $.ajax({
      url: "/api/search",
      data: { q: query },
      dataType: "json",
      timeout: 60000,
    })
      .done(function (payload) {
        render(payload);
        renderBag();
        if (payload.warnings && payload.warnings.length && payload.podcasts && payload.podcasts.length) {
          $status.append(" · " + payload.warnings.join(" "));
        }
      })
      .fail(function (xhr, status) {
        if (status === "abort") {
          return;
        }
        var message =
          (xhr.responseJSON && xhr.responseJSON.error) ||
          (status === "timeout"
            ? "Atlas keyword search took too long. Retry in a moment."
            : "Search failed. Check MongoDB Atlas connectivity and indexes.");
        $status.attr("hidden", true);
        $results.html('<p class="error"></p>').find(".error").text(message);
      });
  }

  $form.on("submit", function (event) {
    event.preventDefault();
    runSearch($input.val());
  });

  $("#sample-queries").on("click", ".chip", function () {
    runSearch($(this).data("query"));
  });

  renderBag();

  var params = new URLSearchParams(window.location.search);
  if (params.get("q")) {
    runSearch(params.get("q"));
  }
});
