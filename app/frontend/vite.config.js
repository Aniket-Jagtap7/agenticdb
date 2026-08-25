import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],

    server: {
        host: "0.0.0.0",
        port: 5173,
        strictPort: true,

        proxy: {
            "/chat": {
                target: "ws://127.0.0.1:8001",
                ws: true,
                changeOrigin: true,
            },

            "/admin": {
                target: "ws://127.0.0.1:8001",
                ws: true,
                changeOrigin: true,
            },
        },
    },

    preview: {
        host: "0.0.0.0",
        port: 4173,
        strictPort: true,
    },
});