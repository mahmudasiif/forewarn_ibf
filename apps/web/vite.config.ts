import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

/**
 * Where the CCM model machine lives. Override with CCM_UPSTREAM_URL in .env
 * when the VM moves.
 */
const CCM_UPSTREAM = process.env.CCM_UPSTREAM_URL ?? "http://10.71.1.102:8088";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    host: true,
    port: 5173,

    // Files are edited on Windows and reach the container through a bind mount,
    // where filesystem change events do not propagate. Without polling the dev
    // server never notices an edit and keeps serving the previous build.
    watch: { usePolling: true, interval: 300 },

    proxy: {
      // The portal's own API.
      "/api": {
        target: "http://api:8000",
        changeOrigin: true,
      },

      /**
       * The CCM model screen, so `/ccm/` behaves in development exactly as it
       * will behind nginx in production — same origin, same path, no env
       * differences between the two.
       *
       * Two entries are needed, not one. The CCM dashboard was built to sit at
       * the root of its own server, so its page asks for `/websockify` as an
       * absolute path. Proxying only `/ccm` would send that request to the
       * portal instead of the model machine, and the screen would stay blank.
       *
       * `ws: true` matters on both: the model screen is a live VNC stream
       * carried over a WebSocket, not a normal page.
       */
      "/ccm": {
        target: CCM_UPSTREAM,
        changeOrigin: true,
        ws: true,
        rewrite: (routePath) => routePath.replace(/^\/ccm/, ""),
      },
      "/websockify": {
        target: CCM_UPSTREAM,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
