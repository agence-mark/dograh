import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

import { REDIRECTIONS } from "./src/lib/redirections";

const nextConfig: NextConfig = {
  /* config options here */
  output: 'standalone',
  experimental: {
    serverSourceMaps: true,
  },
  // [.mark] U10 / S4 : le widget (script, polices) se charge depuis la page d'un autre site : lisible de partout, sans
  // identifiants. Les polices portent un nom versionné (Switzer-400.woff2) : elles se gardent un an.
  async headers() {
    const ouvert = [
      { key: "Access-Control-Allow-Origin", value: "*" },
      { key: "Cross-Origin-Resource-Policy", value: "cross-origin" },
    ];
    return [
      { source: "/embed/:path*", headers: ouvert },
      { source: "/embed/fonts/:path*", headers: [...ouvert, { key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
    ];
  },
  // [.mark] La table unique des anciennes adresses (src/lib/redirections.ts).
  async redirects() {
    return REDIRECTIONS.map((r) => ({ ...r, permanent: false }));
  },
};

export default withSentryConfig(nextConfig, {
  // For all available options, see:
  // https://www.npmjs.com/package/@sentry/webpack-plugin#options

  org: "dograh",
  project: "javascript-nextjs",

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,

  // For all available options, see:
  // https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/

  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,

  // Route browser requests to Sentry through a Next.js rewrite to circumvent ad-blockers.
  // This can increase your server load as well as your hosting bill.
  // Note: Check that the configured route will not match with your Next.js middleware, otherwise reporting of client-
  // side errors will fail.
  tunnelRoute: "/monitoring",

  webpack: {
    // Automatically tree-shake Sentry logger statements to reduce bundle size
    treeshake: {
      removeDebugLogging: true,
    },

    // Enables automatic instrumentation of Vercel Cron Monitors. (Does not yet work with App Router route handlers.)
    // See the following for more information:
    // https://docs.sentry.io/product/crons/
    // https://vercel.com/docs/cron-jobs
    automaticVercelMonitors: true,
  },
});
