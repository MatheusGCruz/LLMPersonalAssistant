function buildEndpoint(route, url) {
  if (route.endpoint && route.endpoint.includes('{url}')) {
    return route.endpoint.split('{url}').join(encodeURIComponent(url));
  }
  if (route.param) {
    const separator = route.endpoint.includes('?') ? '&' : '?';
    return `${route.endpoint}${separator}${route.param}=${encodeURIComponent(url)}`;
  }
  return route.endpoint;
}

function matchRoute(text, routes) {
  for (const route of routes) {
    try {
      const regex = new RegExp(route.pattern, 'i');
      const match = regex.exec(text);
      if (!match) continue;
      const fullUrl = (text.match(/https?:\/\/\S+/i) || [text.trim()])[0];
      let url = fullUrl;
      if (match[0]) {
        const prefix = match[0];
        const idx = fullUrl.toLowerCase().indexOf(prefix.toLowerCase());
        if (idx >= 0) {
          url = fullUrl.slice(idx + prefix.length).split(/[&#]/)[0];
        }
      }
      console.log(`[bot] route matched | route="${route.name}" fullUrl="${fullUrl}" paramValue="${url}"`);
      return { route, url };
    } catch (err) {
      console.error(`[bot] invalid pattern for route "${route.name}":`, err.message);
    }
  }
  return null;
}

module.exports = { buildEndpoint, matchRoute };