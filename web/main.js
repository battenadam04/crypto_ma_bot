(function () {
  var cfg = window.FATHOM || {};
  var checkout = cfg.checkoutUrl || "#";
  var free = cfg.freeChannelUrl || "";

  document.querySelectorAll("[data-checkout]").forEach(function (el) {
    el.setAttribute("href", checkout);
    if (checkout.indexOf("http") === 0) {
      el.setAttribute("target", "_blank");
      el.setAttribute("rel", "noopener noreferrer");
    }
  });

  document.querySelectorAll("[data-free]").forEach(function (el) {
    if (free) {
      el.setAttribute("href", free);
      el.setAttribute("target", "_blank");
      el.setAttribute("rel", "noopener noreferrer");
      el.textContent = "Free teaser channel";
    }
  });

  var year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());
})();
