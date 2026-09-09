/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The shared types package lives outside this app's directory.
  transpilePackages: ["@atlas/shared-types"],
  eslint: { ignoreDuringBuilds: false },
};

export default nextConfig;
