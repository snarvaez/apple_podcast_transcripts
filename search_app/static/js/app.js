$(function () {
  var $form = $("#search-form");
  var $input = $("#q");
  var $results = $("#results");
  var $status = $("#status");

  function badgeHtml(types) {
    return (types || [])
      .map(function (type) {
        return '<span class="badge ' + type + '">' + type + "</span>";
      })
      .join("");
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
          $ep.append($('<p class="snippet"></p>').html(snippet.snippet_html));
        });
        $show.append($ep);
      });
      $results.append($show);
    });
  }

  function runSearch(query) {
    query = $.trim(query || "");
    $input.val(query);
    if (!query) {
      $results.empty();
      $status.attr("hidden", true);
      return;
    }
    $status.text("Searching…").removeAttr("hidden");
    $.ajax({
      url: "/api/search",
      data: { q: query },
      dataType: "json",
    })
      .done(render)
      .fail(function (xhr) {
        var message =
          (xhr.responseJSON && xhr.responseJSON.error) ||
          "Search failed. Check MongoDB Atlas connectivity and indexes.";
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

  var params = new URLSearchParams(window.location.search);
  if (params.get("q")) {
    runSearch(params.get("q"));
  }
});
