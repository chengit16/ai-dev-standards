/** @description 本机开发使用同源代理，验收时允许传入独立 API 端口。 */
import react from "@vitejs/plugin-react";
import UnoCSS from "unocss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [UnoCSS(), react()],
  build: {
    rollupOptions: {
      output: {
        // 独立缓存 React 核心，页面改动不必重新加载这部分。
        manualChunks(id) {
          if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id))
            return "react-runtime";
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.STARTER_API_TARGET ?? "http://127.0.0.1:8000",
      },
    },
  },
});
