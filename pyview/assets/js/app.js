// We import the CSS which is extracted to its own file by esbuild.
// Remove this line if you add a your own CSS build pipeline (e.g postcss).
//import "../css/app.css";

// If you want to use Phoenix channels, run `mix help phx.gen.channel`
// to get started and then uncomment the line below.
// import "./user_socket.js"

// You can include dependencies in two ways.
//
// The simplest option is to put them in assets/vendor and
// import them using relative paths:
//
//     import "./vendor/some-package.js"
//
// Alternatively, you can `npm install some-package` and import
// them using a path starting with the package name:
//
//     import "some-package"
//

// Include phoenix_html to handle method=PUT/DELETE in forms and buttons.
import "phoenix_html";
// Establish Phoenix Socket and LiveView configuration.
import { Socket } from "phoenix";
import { LiveSocket } from "phoenix_live_view";
import NProgress from "nprogress";

let Hooks = window.Hooks ?? {};
let Uploaders = window.Uploaders ?? {};

let scrollAt = () => {
  let scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
  let scrollHeight =
    document.documentElement.scrollHeight || document.body.scrollHeight;
  let clientHeight = document.documentElement.clientHeight;

  return (scrollTop / (scrollHeight - clientHeight)) * 100;
};

Hooks.InfiniteScroll = {
  page() {
    return this.el.dataset.page;
  },
  mounted() {
    this.pending = this.page();
    window.addEventListener("scroll", (e) => {
      if (this.pending == this.page() && scrollAt() > 90) {
        this.pending = this.page() + 1;
        this.pushEvent("load-more", {});
      }
    });
  },
  updated() {
    this.pending = this.page();
  },
};

// Provide default S3 uploader if not already defined
// Users can override by setting window.Uploaders.S3 before this script loads
if (!Uploaders.S3) {
  Uploaders.S3 = function (entries, onViewError) {
    entries.forEach((entry) => {
      let formData = new FormData();
      let { url, fields } = entry.meta;

      // Add all fields from presigned POST
      Object.entries(fields).forEach(([key, val]) =>
        formData.append(key, val)
      );
      formData.append("file", entry.file);

      let xhr = new XMLHttpRequest();
      onViewError(() => xhr.abort());

      xhr.onload = () => {
        if (xhr.status === 204 || xhr.status === 200) {
          entry.progress(100);
        } else {
          entry.error(`S3 upload failed with status ${xhr.status}`);
        }
      };
      xhr.onerror = () => entry.error("Network error during upload");

      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          let percent = Math.round((event.loaded / event.total) * 100);
          if (percent < 100) {
            entry.progress(percent);
          }
        }
      });

      xhr.open("POST", url, true);
      xhr.send(formData);
    });
  };
}

let csrfToken = document
  .querySelector("meta[name='csrf-token']")
  .getAttribute("content");
let liveSocket = new LiveSocket("/live", Socket, {
  hooks: Hooks,
  params: { _csrf_token: csrfToken },
  uploaders: Uploaders,
});

// Show progress bar on live navigation and form submits
//topbar.config({ barColors: { 0: "#29d" }, shadowColor: "rgba(0, 0, 0, .3)" });
window.addEventListener("phx:page-loading-start", (info) => NProgress.start());
window.addEventListener("phx:page-loading-stop", (info) => NProgress.done());

// connect if there are any LiveViews on the page
liveSocket.connect();

// expose liveSocket on window for web console debug logs and latency simulation:
// >> liveSocket.enableDebug()
// >> liveSocket.enableLatencySim(1000)  // enabled for duration of browser session
// >> liveSocket.disableLatencySim()
window.liveSocket = liveSocket;
