// Pure pass-through proxy for the bot (optional - the bot already works on its own Koyeb URL).
// Returns the origin Response untouched, so the body is streamed without any JavaScript CPU work.
const ORIGIN = "https://YOUR-APP-NAME.koyeb.app";   // <- your Koyeb public URL, no trailing slash

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = new Request(ORIGIN + url.pathname + url.search, request); // keeps method + Range header
    return fetch(target, { cf: { cacheTtl: 0, cacheEverything: false } });   // do NOT wrap/transform the response
  },
};
