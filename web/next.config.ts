import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // Allow class-materials uploads (default is only 1 MB). Note: the live site (Vercel)
    // also caps requests at ~4.5 MB, so the form limits total uploads to ~4 MB and offers a
    // "paste materials as text" fallback for larger decks.
    serverActions: {
      bodySizeLimit: "10mb",
    },
  },
};

export default nextConfig;
