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
      if (regex.test(text)) {
        const url = (text.match(/https?:\/\/\S+/i) || [text.trim()])[0];
        return { route, url };
      }
    } catch (err) {
      console.error(`[bot] invalid pattern for route "${route.name}":`, err.message);
    }
  }
  return null;
}

module.exports = { buildEndpoint, matchRoute };