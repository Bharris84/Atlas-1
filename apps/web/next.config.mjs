/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // @atlas/shared-types is a source-only workspace package: its entry point is
  // a .ts file, so it must be transpiled rather than consumed as built JS.
  transpilePackages: ["@atlas/shared-types"],
  // Next 16 blocks cross-origin requests to dev resources by default. The e2e
  // suite drives the app over 127.0.0.1 while the dev server binds localhost,
  // which Next treats as cross-origin — without this, client components never
  // hydrate and every interactive page renders an empty shell.
  // Development only; it has no effect on a production build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
