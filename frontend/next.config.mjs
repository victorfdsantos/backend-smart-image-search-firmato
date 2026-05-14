const nextConfig = {
  // Enables standalone build for minimal Docker image
  output: "standalone",

  // Proxy /api/* → backend. Works in dev and in any cloud deployment.
  async rewrites() {
    const apiBase = process.env.API_BASE ?? "http://localhost:8000";
    return [
      {
        source:      "/api/:path*",
        destination: `${apiBase}/:path*`,
      },
    ];
  },

  images: {
    remotePatterns: [
      // App Service default domain
      {
        protocol: "https",
        hostname: "*.azurewebsites.net",
      },
      // Local development
      {
        protocol: "http",
        hostname: "localhost",
      },
      // Custom domain — ajuste conforme necessário
      // { protocol: "https", hostname: "yourdomain.com" },
    ],
  },
};

export default nextConfig;
