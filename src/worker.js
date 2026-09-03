import { setDb, ensureSchema } from '../lib/db.js';
import { setApi, TelegramApi } from '../lib/api.js';
import handleMessage, { handleCallbackQuery } from '../handlers/bot.js';

export default {
  async fetch(request, env, ctx) {
    // 1. Diagnostics check / health check
    if (request.method !== 'POST') {
      return new Response('Tinder Checker Telegram Bot is running.', {
        status: 200,
        headers: { 'Content-Type': 'text/plain' }
      });
    }

    try {
      // 2. Initialize environment config and binding managers
      setDb(env.DB);

      if (!env.TELEGRAM_BOT_TOKEN) {
        return new Response('Missing TELEGRAM_BOT_TOKEN configuration in Worker environment.', { status: 500 });
      }
      
      const apiInstance = new TelegramApi(env.TELEGRAM_BOT_TOKEN.trim());
      setApi(apiInstance);

      // Ensure DB schema has referral columns
      ctx.waitUntil(ensureSchema());

      // 3. Process webhook update payload
      const update = await request.json();

      if (update.message) {
        ctx.waitUntil(handleMessage(update.message, env));
      } else if (update.callback_query) {
        ctx.waitUntil(handleCallbackQuery(update.callback_query, env));
      }

      // Return 200 OK to Telegram immediately
      return new Response('OK', { status: 200 });
    } catch (err) {
      console.error('Error handling Telegram webhook:', err);
      return new Response('Error Handled', { status: 200 });
    }
  }
};
