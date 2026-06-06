import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/auth": "http://gateway-service:8080",
      "/predict": "http://gateway-service:8080",
      "/train": "http://gateway-service:8080",
      "/initBaseModel": "http://gateway-service:8080",
      "/activate": "http://gateway-service:8080",
      "/models": "http://gateway-service:8080",
      "/training-runs": "http://gateway-service:8080",
      "/user": "http://gateway-service:8080",
    },
  },
});
