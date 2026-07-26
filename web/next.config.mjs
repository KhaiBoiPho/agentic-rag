/** @type {import('next').NextConfig} */

// Where /api/* is forwarded. In Docker this is http://app:8000 (set via the
// API_PROXY_TARGET build arg / env); in local dev it defaults to localhost.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,

  // CRITICAL: the backend streams SSE with `no-transform`. Next's default gzip
  // buffers responses and breaks token-by-token streaming, so disable it. The
  // rewrite below forwards the raw stream to the backend untouched.
  compress: false,

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${API_PROXY_TARGET}/health`,
      },
    ];
  },
};

export default nextConfig;
