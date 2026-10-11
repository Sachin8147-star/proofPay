/** @type {import('next').NextConfig} */
export default { reactStrictMode: true, webpack: (c) => { c.resolve.fallback = { ...c.resolve.fallback, "pino-pretty": false, encoding: false }; return c; } };
