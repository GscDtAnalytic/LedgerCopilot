/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Server Components by default; Client Components only where there is interaction
  //.
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
