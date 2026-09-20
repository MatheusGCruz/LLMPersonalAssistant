const fs = require('fs');
const os = require('os');
const path = require('path');
const TelegramBot = require('node-telegram-bot-api');
const { config } = require('./config');
const { buildEndpoint, matchRoute } = require('./routes');

const token = config.token;
if (!token) {
  console.error('[bot] BOT_TOKEN is not set in the environment; cannot start');
  process.exit(1);
}

const bot = new TelegramBot(token, { polling: true });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function download(route, url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.fetchTimeoutMs);
  const endpoint = buildEndpoint(route, url);
  console.log(`[bot] download start | route="${route.name || route.endpoint}" url="${url}" endpoint="${endpoint}" timeout=${config.fetchTimeoutMs}ms`);
  const started = Date.now();
  try {
    const response = await fetch(endpoint, {
      method: route.method || 'GET',
      redirect: 'follow',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`endpoint answered with status ${response.status}`);
    }
    const disposition = response.headers.get('content-disposition') || '';
    const filename = parseContentDisposition(disposition) || baseName(route, url);
    const buffer = Buffer.from(await response.arrayBuffer());
    console.log(`[bot] download done | route="${route.name || route.endpoint}" status=${response.status} bytes=${buffer.length} filename="${filename}" took=${Date.now() - started}ms`);
    return { buffer, filename };
  } catch (err) {
    console.error(`[bot] download failed | route="${route.name || route.endpoint}" url="${url}" runtime=${Date.now() - started}ms`, err.message);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function sanitizeFilename(name) {
  return String(name || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9._-]+/g, '')
    .replace(/^\.+|\.+$/g, '')
    .slice(0, 80) || 'audio';
}

async function sendAudio(chatId, buffer, route, filename) {
  const baseName = sanitizeFilename(filename) || route.name || 'audio';
  const filePath = path.join(os.tmpdir(), `${baseName}_${Date.now()}.mp3`);
  fs.writeFileSync(filePath, buffer);
  const started = Date.now();
  try {
    await bot.sendAudio(chatId, fs.createReadStream(filePath), {
      filename: `${baseName || route.name || 'audio'}.mp3`,
      contentType: 'audio/mpeg',
      title: route.audio_title || 'YouTube Audio',
      performer: route.audio_performer || 'Telegram',
      caption: route.caption || '',
    });
    console.log(`[bot] audio sent | chat=${chatId} bytes=${buffer.length} took=${Date.now() - started}ms`);
  } catch (err) {
    console.error(`[bot] audio send failed | chat=${chatId}`, err.message);
    throw err;
  } finally {
    fs.unlink(filePath, () => {});
  }
}

async function handleRoute(chatId, route, url) {
  const messages = (route.intermediary_messages || []).filter((m) => m);
  const [first, ...rest] = messages;
  console.log(`[bot] handleRoute start | chat=${chatId} route="${route.name || 'unnamed'}" url="${url}" intermediary=${messages.length}`);
  try {
    await bot.sendMessage(chatId, first || 'Processando...');
    const { buffer, filename } = await download(route, url);
    for (const message of rest) {
      await bot.sendMessage(chatId, message);
      await sleep(config.delayMs);
    }
    await sendAudio(chatId, buffer, route, filename);
    console.log(`[bot] handleRoute done | chat=${chatId} route="${route.name || 'unnamed'}" totalBytes=${buffer.length}`);
  } catch (err) {
    console.error(`[bot] route "${route.name || url}" failed:`, err.message);
    try {
      await bot.sendMessage(chatId, route.error_message || 'Nao consegui completar o pedido.');
    } catch (_) {}
  }
}

async function openRouterChat(text) {
  if (!config.openrouterEnabled || !config.openrouterApiKey) {
    console.log(`[bot] openrouter skipped | enabled=${config.openrouterEnabled} hasKey=${Boolean(config.openrouterApiKey)}`);
    return null;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.openrouterTimeoutMs);
  const url = `${config.openrouterBaseUrl.replace(/\/+$/, '')}/chat/completions`;
  console.log(`[bot] openrouter start | model="${config.openrouterModel}" url="${url}" timeout=${config.openrouterTimeoutMs}ms`);
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.openrouterApiKey}`,
      },
      body: JSON.stringify({
        model: config.openrouterModel,
        messages: [{ role: 'user', content: text }],
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`openrouter answered with status ${response.status}`);
    }
    const data = await response.json();
    const content = (((data.choices || [])[0] || {}).message || {}).content;
    if (!content) {
      throw new Error('openrouter response did not include message content');
    }
    console.log(`[bot] openrouter ok | status=${response.status} runtime=${Date.now() - started}ms`);
    return content;
  } catch (err) {
    console.warn(`[bot] openrouter request failed | runtime=${Date.now() - started}ms:`, err.message);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function handleAssistant(chatId, text) {
  const openrouterContent = await openRouterChat(text);
  if (openrouterContent) {
    await bot.sendMessage(chatId, openrouterContent);
    console.log(`[bot] openrouter reply sent | chat=${chatId} chars=${openrouterContent.length}`);
    return;
  }
  if (!config.assistantEnabled || !config.assistantEndpoint) {
    console.log(`[bot] assistant disabled or not configured | chat=${chatId} enabled=${config.assistantEnabled} endpoint=${config.assistantEndpoint}`);
    await bot.sendMessage(chatId, config.fallbackMessage);
    return;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.fetchTimeoutMs);
  console.log(`[bot] assistant start | chat=${chatId} endpoint=${config.assistantEndpoint} timeout=${config.fetchTimeoutMs}ms`);
  const started = Date.now();
  try {
    const response = await fetch(config.assistantEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`assistant answered with status ${response.status}`);
    }
    const data = await response.json();
    const content = data.content || data.result || 'Sem resposta.';
    console.log(`[bot] assistant ok | chat=${chatId} status=${response.status} runtime=${Date.now() - started}ms`);
    await bot.sendMessage(chatId, content);
    console.log(`[bot] assistant reply sent | chat=${chatId} chars=${content.length}`);
  } catch (err) {
    console.error(`[bot] assistant request failed | chat=${chatId} runtime=${Date.now() - started}ms:`, err.message);
    try {
      await bot.sendMessage(chatId, 'Erro ao consultar o assistente.');
    } catch (_) {}
  } finally {
    clearTimeout(timer);
  }
}

bot.on('message', async (msg) => {
  const text = ((msg && msg.text) || '').trim();
  if (!text) {
    return;
  }
  const chatId = msg.chat.id;
  const sender = msg.from ? `@${msg.from.username || msg.from.first_name}` : 'unknown';
  console.log(`[bot] message received | chat=${chatId} sender=${sender} text="${text}"`);
  const hit = matchRoute(text, config.routes);
  if (hit) {
    console.log(`[bot] message routed | chat=${chatId} route="${hit.route.name}" url="${hit.url}"`);
    return handleRoute(chatId, hit.route, hit.url);
  }
  console.log(`[bot] message -> assistant | chat=${chatId}`);
  return handleAssistant(chatId, text);
});

bot.on('polling_error', (err) => console.error('[bot] polling error:', err.message));

console.log('[bot] Telegram bot started');