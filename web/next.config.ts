import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // Allow class-materials uploads. Two limits must BOTH be raised or the upload is
    // truncated ("Unexpected end of form"):
    //   • serverActions.bodySizeLimit — the server-action body cap (default 1 MB)
    //   • proxyClientMaxBodySize     — the proxy.ts (auth middleware) body cap (default 10 MB)
    // Locally we allow big decks. NOTE: the live site (Vercel) still hard-caps requests at
    // ~4.5 MB regardless of these values, so for the deployed site keep total uploads small
    // or use the "paste materials as text" box for large decks.
    serverActions: {
      bodySizeLimit: "50mb",
    },
    proxyClientMaxBodySize: "50mb",
  },
};

export default nextConfig;
