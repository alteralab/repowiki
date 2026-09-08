import { createMDX } from 'fumadocs-mdx/next';
const withMDX = createMDX();
/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  trailingSlash: true,
  reactStrictMode: true,
  // file:// attempt (research 17): relative asset prefix. Next docs say assetPrefix should be an absolute URL or path; try anyway.
  assetPrefix: './',
};
export default withMDX(config);
