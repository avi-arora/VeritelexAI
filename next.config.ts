import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Cloud Run container (see Dockerfile).
  output: "standalone",
  // The FastAPI service lives in ./backend and is deployed separately.
  outputFileTracingExcludes: {
    "/*": ["backend/**/*"],
  },
  poweredByHeader: false,
};

export default nextConfig;
