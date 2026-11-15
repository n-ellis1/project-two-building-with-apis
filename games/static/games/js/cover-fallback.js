// Cover fallback: when a remote cover fails to load, show the local placeholder.
// Only images marked with data-cover-placeholder are handled. The marker and srcset
// are removed before src changes, so a failed placeholder is never retried.
// Width, height and alt are left untouched.
(function () {
  function useFallback(img) {
    var placeholder = img.getAttribute("data-cover-placeholder");
    img.removeAttribute("data-cover-placeholder");
    img.removeAttribute("srcset");
    img.src = placeholder;
  }

  // Image errors don't bubble, so one capture-phase listener on document sees them all.
  document.addEventListener(
    "error",
    function (event) {
      var img = event.target;
      if (img instanceof HTMLImageElement && img.hasAttribute("data-cover-placeholder")) {
        useFallback(img);
      }
    },
    true
  );

  // This script is deferred, so a cover can fail before the listener exists.
  // A broken image is complete with no natural width; a lazy image that hasn't
  // started loading isn't complete, so it's left for the listener.
  var marked = document.querySelectorAll("img[data-cover-placeholder]");
  for (var i = 0; i < marked.length; i++) {
    if (marked[i].complete && marked[i].naturalWidth === 0) {
      useFallback(marked[i]);
    }
  }
})();
