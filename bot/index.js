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
  try {
    const response = await fetch(buildEndpoint(route, url), {
      method: route.method || 'GET',
      redirect: 'follow',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`endpoint answered with status ${response.status}`);
    }
    return Buffer.from(await response.arrayBuffer());
  } finally {
    clearTimeout(timer);
  }
}

async function sendAudio(chatId, buffer, route) {
  const filePath = path.join(os.tmpdir(), `${route.name || 'audio'}_${Date.now()}.mp3`);
  fs.writeFileSync(filePath, buffer);
  try {
    await bot.sendAudio(chatId, fs.createReadStream(filePath), {
      filename: path.basename(filePath),
      contentType: 'audio/mpeg',
      title: route.audio_title || 'YouTube Audio',
      performer: route.audio_performer || 'Telegram',
      caption: route.caption || '',
    });
  } finally {
    fs.unlink(filePath, () => {});
  }
}

async function handleRoute(chatId, route, url) {
  const messages = (route.intermediary_messages || []).filter((m) => m);
  const [first, ...rest] = messages;
  try {
    await bot.sendMessage(chatId, first || 'Processando...');
    const buffer = await download(route, url);
    for (const message of rest) {
      await bot.sendMessage(chatId, message);
      await sleep(config.delayMs);
    }
    await sendAudio(chatId, buffer, route);
  } catch (err) {
    console.error(`[bot] route "${route.name || url}" failed:`, err.message);
    try {
      await bot.sendMessage(chatId, route.error_message || 'Nao consegui completar o pedido.');
    } catch (_) {}
  }
}

async function handleAssistant(chatId, text) {
  if (!config.assistantEnabled || !config.assistantEndpoint) {
    await bot.sendMessage(chatId, config.fallbackMessage);
    return;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.fetchTimeoutMs);
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
    await bot.sendMessage(chatId, content);
  } catch (err) {
    console.error('[bot] assistant request failed:', err.message);
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
  const hit = matchRoute(text, config.routes);
  if (hit) {
    return handleRoute(chatId, hit.route, hit.url);
  }
  return handleAssistant(chatId, text);
});

bot.on('polling_error', (err) => console.error('[bot] polling error:', err.message));

console.log('[bot] Telegram bot started');