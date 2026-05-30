import type { NextConfig } from "next";
import path from "node:path";

const LOADER = path.resolve(__dirname, 'src/visual-edits/component-tagger-loader.js');
const BACKEND_LAYER_REGEX = /src[\\/]backend[\\/]services[\\/]processing[\\/]layers/;
const AWS_HANDLER_IDENTIFIER = /confusion-matrix-layer[\\/]aws-lambda-handler/;
const ENABLE_VISUAL_EDITS_TAGGER = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
      {
        protocol: 'http',
        hostname: '**',
      },
    ],
  },
  outputFileTracingRoot: path.resolve(__dirname),
  typescript: {
    ignoreBuildErrors: true,
  },
  experimental: {
    // Clerk middleware causes uploads to pass through Next's proxy path.
    // The default proxy body limit is 10 MB, which breaks mid-sized PDFs
    // before our route-level validation can run.
    proxyClientMaxBodySize: 100 * 1024 * 1024,
  },
  ...(ENABLE_VISUAL_EDITS_TAGGER
    ? {
        turbopack: {
          rules: {
            "*.{jsx,tsx}": {
              loaders: [LOADER],
            },
          },
        },
      }
    : {}),
  webpack: (config, { isServer, webpack }) => {
    config.externals = config.externals || [];
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@": path.resolve(__dirname, "src"),
    };

    config.externals.push({
      "@aws-sdk/client-s3": "commonjs @aws-sdk/client-s3",
      "@aws-sdk/s3-request-presigner": "commonjs @aws-sdk/s3-request-presigner",
    });

    config.externals.push(function (options: { request?: string }, callback: (err?: Error, result?: string) => void) {
      if (options.request && AWS_HANDLER_IDENTIFIER.test(options.request)) {
        return callback(undefined, `commonjs ${options.request}`);
      }
      callback();
    });

    if (!isServer) {
      config.plugins.push(
        new webpack.IgnorePlugin({
          resourceRegExp: BACKEND_LAYER_REGEX,
        })
      );
    }

    return config;
  }
};

export default nextConfig;
// Orchids restart: 1762558684288
