require('dotenv').config();

const DEFAULT_ROUTES = [
  {
    name: 'youtube_mp3',
    pattern: 'https?://(www\\.)?youtube\\.com/watch\\?v=',
    intermediary_messages: ['Baixando....', 'Convertendo para MP3...'],
    endpoint: 'http://host.docker.internal:3021/mp3',
    method: 'GET',
    param: 'url',
    filename: 'audio.mp3',
    audio_title: 'YouTube Audio',
    error_message: 'Nao consegui baixar esse video.',
  },
];

function parseIntValue(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseRoutes() {
  const raw = process.env.BOT_ROUTES;
  if (!raw) {
    return DEFAULT_ROUTES;
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) {
      console.warn('[bot] BOT_ROUTES is not a non-empty JSON list; using defaults');
      return DEFAULT_ROUTES;
    }
    return parsed;
  } catch (err) {
    console.warn('[bot] BOT_ROUTES is not valid JSON; using defaults:', err.message);
    return DEFAULT_ROUTES;
  }
}

const config = {
  token: process.env.BOT_TOKEN || '',
  assistantEnabled: String(process.env.BOT_ASSISTANT_ENABLED ?? 'true') === 'true',
  assistantEndpoint: process.env.BOT_ASSISTANT_ENDPOINT || 'http://localhost:8000/assistant',
  fetchTimeoutMs: parseIntValue(process.env.BOT_FETCH_TIMEOUT_MS, 180000),
  delayMs: parseIntValue(process.env.BOT_INTERMEDIARY_DELAY_MS, 1200),
  fallbackMessage: process.env.BOT_FALLBACK_MESSAGE || 'Desculpe, nao entendi.',
  routes: parseRoutes(),
};

module.exports = { config, DEFAULT_ROUTES };