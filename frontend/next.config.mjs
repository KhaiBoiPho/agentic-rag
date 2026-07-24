/** @type {import('next').NextConfig} */
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  // SSE responses must not be gzip'd/buffered, so we disable Next's built-in
  // compression entirely (it applies to every route, and there is no
  // per-route opt-out). The reverse proxy in front (if any) must also avoid
  // buffering — see rewrites() below, which forwards /api/* to the backend
  // and relies on the backend's own no-transform / no-buffering headers.
  compress: false,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
