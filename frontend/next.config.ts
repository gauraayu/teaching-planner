import type { NextConfig } from 'next'

// In development (and optionally in production) every /api/* call is proxied to FastAPI,
// so the browser talks to one origin and no CORS setup is needed.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${API_PROXY_TARGET}/api/:path*` }]
  },
}

export default nextConfig
