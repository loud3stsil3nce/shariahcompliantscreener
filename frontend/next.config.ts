import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backendHost = process.env.BACKEND_URL || 'http://shariahscreener:8001';
    return [
      {
        source: '/api/:path*',
        destination: `${backendHost}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
