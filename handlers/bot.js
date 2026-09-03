import { api } from '../lib/api.js';
import * as db from '../lib/db.js';
import { TinderClient, extractUsername } from '../lib/tinder.js';

const tinderClient = new TinderClient();
const userRateLimit = new Map();
const RATE_LIMIT_SECONDS = 5;

const REQUIRED_CHANNEL = "@N_Notic";
const CHANNEL_URL = "https://t.me/N_Notic";

// ── In-memory caches (saves Telegram API quota for CF free tier) ──
const membershipCache = new Map();  // userId -> { result, ts }
const CACHE_TTL = 600_000; // 10 minutes in ms
let cachedBotUsername = null;

function escapeHtml(text) {
  if (!text) return "";
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function getBotUsername() {
  if (!cachedBotUsername) {
    try {
      const me = await api._request('getMe');
      cachedBotUsername = me.username;
    } catch (e) { cachedBotUsername = "tinderchecker_bot"; }
  }
  return cachedBotUsername;
}

async function checkChannelMembership(userId) {
  const now = Date.now();
  const cached = membershipCache.get(userId);
  if (cached && (now - cached.ts) < CACHE_TTL) return cached.result;

  let isMember = false;
  try {
    const res = await api._request('getChatMember', { chat_id: REQUIRED_CHANNEL, user_id: userId });
    isMember = ['member', 'administrator', 'creator'].includes(res.status);
  } catch (e) {}
  membershipCache.set(userId, { result: isMember, ts: now });
  return isMember;
}

async function sendJoinPrompt(chatId) {
  await api.sendMessage(chatId,
    `🔒 <b>Channel Membership Required!</b>\n\n` +
    `Join our channel first:\n👉 ${CHANNEL_URL}\n\n` +
    `Then tap <b>✅ I've Joined</b>.`,
    {
      reply_markup: {
        inline_keyboard: [
          [{ text: "📢 Join Channel", url: CHANNEL_URL }],
          [{ text: "✅ I've Joined", callback_data: "check_joined" }]
        ]
      },
      disable_web_page_preview: true
    }
  );
}

async function tryVerifyAndNotify(userId) {
  const referrerId = await db.tryVerifyReferral(userId);
  if (!referrerId) return;

  // Anti-fraud: referred user must still be in channel
  membershipCache.delete(userId); // fresh check
  const stillMember = await checkChannelMembership(userId);
  if (!stillMember) return;

  await db.confirmReferral(userId, referrerId);
  try {
    await api.sendMessage(referrerId,
      `🎉 <b>Referral Confirmed!</b>\n\n` +
      `A user you invited just used the bot & is verified as real.\n+1 referral credited! 🏆`
    );
  } catch (e) {}
}

// ── Callback Query Handler ──
export async function handleCallbackQuery(callbackQuery, env) {
  if (!callbackQuery?.from) return;
  const telegramId = callbackQuery.from.id;
  const chatId = callbackQuery.message?.chat?.id;
  const messageId = callbackQuery.message?.message_id;

  if (callbackQuery.data === "check_joined") {
    membershipCache.delete(telegramId); // force fresh check
    const isMember = await checkChannelMembership(telegramId);
    if (isMember) {
      const botUser = await getBotUsername();
      const refLink = `https://t.me/${botUser}?start=ref_${telegramId}`;
      try {
        await api._request('editMessageText', {
          chat_id: chatId, message_id: messageId,
          text: `✅ <b>Verified!</b> You're a member.\n\n🔥 Send any Tinder username to check!\n\n📎 <b>Your referral link:</b>\n<code>${refLink}</code>`,
          parse_mode: 'HTML', disable_web_page_preview: true
        });
      } catch (e) {}
      await api._request('answerCallbackQuery', { callback_query_id: callbackQuery.id, text: "✅ Verified!" });
    } else {
      await api._request('answerCallbackQuery', {
        callback_query_id: callbackQuery.id, text: "❌ You haven't joined yet!", show_alert: true
      });
    }
  }
}

// ── Main Message Handler ──
export default async function handleMessage(message, env) {
  if (!message?.from?.id || !message?.chat) return;

  const telegramId = message.from.id;
  const chatId = message.chat.id;
  const username = message.from.username || null;
  const fullName = [message.from.first_name, message.from.last_name].filter(Boolean).join(" ");
  const text = (message.text || "").trim();

  const ownerIds = (env.OWNER_ID || "").split(",").map(id => id.trim()).filter(Boolean);
  const isAdmin = ownerIds.includes(String(telegramId));

  // ── /start ──
  if (text.startsWith("/start")) {
    let referrerId = null;
    const parts = text.split(" ");
    if (parts[1]?.startsWith("ref_")) {
      const parsed = parseInt(parts[1].replace("ref_", ""), 10);
      if (!isNaN(parsed)) referrerId = parsed;
    }

    await db.registerUser(telegramId, username, fullName, referrerId);

    const isMember = await checkChannelMembership(telegramId);
    if (!isMember) { await sendJoinPrompt(chatId); return; }

    const botUser = await getBotUsername();
    const refLink = `https://t.me/${botUser}?start=ref_${telegramId}`;

    await api.sendMessage(chatId,
      `🔥 <b>Welcome to Tinder DNA Checker!</b> 🔥\n\n` +
      `🎯 Send any Tinder username to check.\n\n` +
      `<i>Examples:</i>  boy  •  @boy  •  tinder.com/@boy\n\n` +
      `📎 <b>Your referral link:</b>\n<code>${refLink}</code>\n` +
      `Invite friends & earn verified referral credits!`,
      { reply_markup: { inline_keyboard: [[{ text: "📢 Channel", url: CHANNEL_URL }]] }, disable_web_page_preview: true }
    );
    return;
  }

  // ── /refer ──
  if (text.startsWith("/refer")) {
    const isMember = await checkChannelMembership(telegramId);
    if (!isMember) { await sendJoinPrompt(chatId); return; }

    const botUser = await getBotUsername();
    const refLink = `https://t.me/${botUser}?start=ref_${telegramId}`;
    const refCount = await db.getReferralCount(telegramId);

    await api.sendMessage(chatId,
      `🔗 <b>Referral Dashboard</b>\n\n` +
      `📎 <b>Your Link:</b>\n<code>${refLink}</code>\n\n` +
      `👥 <b>Verified Referrals:</b> <code>${refCount}</code>\n\n` +
      `ℹ️ Referrals count only after the invited user joins the channel AND uses the bot.`,
      { disable_web_page_preview: true }
    );
    return;
  }

  // ── /debug ──
  if (text.startsWith("/debug")) {
    if (!isAdmin) return;
    await api.sendMessage(chatId,
      `🛠️ <b>Debug</b>\n• Your ID: <code>${telegramId}</code>\n• Owner: <code>${env.OWNER_ID}</code>`
    );
    return;
  }

  // ── /stats ──
  if (text.startsWith("/stats")) {
    if (!isAdmin) return;
    try {
      const stats = await db.getStats();
      const apiHealth = await tinderClient.pingEndpoints();
      const healthText = Object.entries(apiHealth).map(([d, s]) => `  • <code>${d}</code>: ${s}`).join("\n");

      const topRefs = await db.getTopReferrers(5);
      const medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"];
      let topText = "";
      if (topRefs.length) {
        topText = "\n🏆 <b>Top Referrers:</b>\n";
        topRefs.forEach((r, i) => {
          const d = r.username ? `@${r.username}` : `<code>${r.user_id}</code>`;
          topText += `  ${medals[i]} ${d}: <code>${r.referral_count}</code>\n`;
        });
      }

      await api.sendMessage(chatId,
        `⚡ <b>SUPERPOWERS DASHBOARD</b> ⚡\n═══════════════════════════════════════\n\n` +
        `📊 <b>Database:</b>\n  • Users: <code>${stats.userCount}</code>\n  • Queries: <code>${stats.queryCount}</code>\n\n` +
        `🔗 <b>Referrals (Anti-Fraud):</b>\n  • Verified: <code>${stats.totalReferrals}</code>\n  • Pending: <code>${stats.pendingReferrals}</code>\n${topText}\n` +
        `🌐 <b>API Health:</b>\n${healthText}\n\n═══════════════════════════════════════`
      );
    } catch (err) { await api.sendMessage(chatId, `❌ Error: ${escapeHtml(err.message)}`); }
    return;
  }

  // ── /users ──
  if (text.startsWith("/users")) {
    if (!isAdmin) return;
    try {
      const users = await db.getAllUsers();
      if (!users.length) { await api.sendMessage(chatId, "📝 No users yet."); return; }
      let content = "REGISTERED USERS\n" + "=".repeat(30) + "\n\n";
      users.forEach((u, i) => {
        const v = u.referral_verified ? "✅" : (u.referred_by ? "⏳" : "—");
        content += `${i+1}. ${u.full_name||"?"} (@${u.username||"?"}) | ID:${u.user_id} | Refs:${u.referral_count||0} | ${v}\n`;
      });
      const buf = new TextEncoder().encode(content);
      await api.sendDocument(chatId, buf, "users.txt", `✅ <b>Total:</b> <code>${users.length}</code>`);
    } catch (err) { await api.sendMessage(chatId, `❌ Error: ${escapeHtml(err.message)}`); }
    return;
  }

  // ── /broadcast ──
  if (text.startsWith("/broadcast")) {
    if (!isAdmin) return;
    const bMsg = text.replace("/broadcast", "").trim();
    if (!bMsg && !message.reply_to_message) { await api.sendMessage(chatId, "⚠️ Provide a message."); return; }
    const users = await db.getAllUsers();
    let ok = 0, fail = 0;
    for (const u of users) {
      try {
        await api.sendMessage(u.user_id, message.reply_to_message?.text || bMsg);
        ok++;
      } catch (e) { fail++; }
      await new Promise(r => setTimeout(r, 60));
    }
    await api.sendMessage(chatId, `✅ <b>Done!</b> Sent: ${ok} | Failed: ${fail}`);
    return;
  }

  // ── Tinder Query ──
  const isMember = await checkChannelMembership(telegramId);
  if (!isMember) { membershipCache.delete(telegramId); await sendJoinPrompt(chatId); return; }

  await db.registerUser(telegramId, username, fullName);

  const now = Date.now();
  if (userRateLimit.has(telegramId)) {
    const elapsed = (now - userRateLimit.get(telegramId)) / 1000;
    if (elapsed < RATE_LIMIT_SECONDS) {
      await api.sendMessage(chatId, `⏳ Wait ${Math.ceil(RATE_LIMIT_SECONDS - elapsed)}s.`);
      return;
    }
  }
  userRateLimit.set(telegramId, now);

  const tinderUsername = extractUsername(text);
  if (!tinderUsername) { await api.sendMessage(chatId, "❌ Invalid format. Send a Tinder URL or username."); return; }

  const checkingMsg = await api.sendMessage(chatId, `🔍 Analyzing <b>${escapeHtml(tinderUsername)}</b>...`);

  try {
    const data = await tinderClient.getProfileData(tinderUsername);
    const riskInfo = data.risk_analysis || {};
    const SEP = "═══════════════════════════════════════";
    const botUser = await getBotUsername();
    const refLink = `https://t.me/${botUser}?start=ref_${telegramId}`;

    if (data.status === "not_found" || data.is_restricted) {
      const st = data.is_restricted ? "🔴 SHADOWBANNED" : "❌ BANNED / DELETED";
      const report =
        `${SEP}\n💣 Tinder DNA & OSINT Analysis 💥\n${SEP}\n\n` +
        `🔴 Account: <code>${st}</code>\n🛡️ Risk: <b>${riskInfo.badge || '🔴 HIGH RISK'}</b>\n\n` +
        `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🪪 Username: <code>@${escapeHtml(tinderUsername)}</code>\n\n` +
        `${SEP}\n🧪 Analysis Complete\n${SEP}`;

      await db.logQueryAndIncrement(telegramId, tinderUsername, "not_found");
      try { await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id }); } catch (e) {}
      await api.sendMessage(chatId, report, {
        reply_markup: { inline_keyboard: [
          [{ text: "🌹 Open Profile", url: `https://tinder.com/@${tinderUsername}` }],
          [{ text: "📢 Channel", url: CHANNEL_URL }]
        ]}
      });
      // Anti-fraud verify in background
      tryVerifyAndNotify(telegramId).catch(() => {});
      return;
    }

    if (data.status === "error") {
      await db.logQueryAndIncrement(telegramId, tinderUsername, "error");
      try { await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id }); } catch (e) {}
      await api.sendMessage(chatId, "⚠️ Error fetching profile. Try again later.");
      return;
    }

    await db.logQueryAndIncrement(telegramId, tinderUsername, "success");
    // Anti-fraud verify in background
    tryVerifyAndNotify(telegramId).catch(() => {});

    const cdv = data.creation_date || "Unknown";
    const name = escapeHtml(data.name || "Hidden");
    const bd = escapeHtml(data.birth_date || "Hidden");
    const aa = data.account_age || "Not available";
    const aid = data.account_id || "Hidden";
    const vs = data.verified ? "⚙️ Verified" : "⚙️ Not Verified";
    const ad = data.age && data.age !== "Unknown" ? `${data.age} years` : "Unknown";
    const sn = riskInfo.score !== undefined ? riskInfo.score : 100;
    const rl = riskInfo.level || "🟢 Low Risk";

    const report =
      `${SEP}\n🔥 Tinder DNA & OSINT Result ✨\n${SEP}\n\n` +
      `🟢 Account: Active\n🛡️ Risk: <b>${sn}/100</b> (${rl})\n\n` +
      `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n` +
      `🪪 Username: <code>@${escapeHtml(tinderUsername)}</code>\n` +
      `👤 Name: ${name}\n🎂 Birth: ${bd}\n🕒 Age: ${ad}\n` +
      `📸 Photos: ${data.photos_count || 0}\n⏳ Account Age: ${aa}\n` +
      `📆 Registered: ${escapeHtml(cdv)}\n🆔 ID: <code>${aid}</code>\n⚙️ Verified: ${vs}\n\n` +
      `${SEP}\n🧪 Analysis Complete\n${SEP}\n\n` +
      `📎 Invite friends: <code>${refLink}</code>`;

    try { await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id }); } catch (e) {}

    const rm = { inline_keyboard: [
      [{ text: "🌹 Open Profile", url: `https://tinder.com/@${tinderUsername}` }],
      [{ text: "💸 Sell Account", url: "https://t.me/T_ump" }, { text: "📢 Channel", url: CHANNEL_URL }]
    ]};

    if (ownerIds.length && !isAdmin) {
      try {
        await api.sendMessage(ownerIds[0],
          `📊 <b>Query</b>\n• <a href='tg://user?id=${telegramId}'>${escapeHtml(fullName)}</a>\n` +
          `• Profile: @${escapeHtml(tinderUsername)}\n• Risk: ${riskInfo.badge || '🟢'}\n` +
          `• Via: <code>${data.token_status || '?'}</code>`
        );
      } catch (e) {}
    }

    if (data.image_url) {
      try { await api.sendPhoto(chatId, data.image_url, report, { reply_markup: rm }); }
      catch (e) { await api.sendMessage(chatId, report, { reply_markup: rm, disable_web_page_preview: true }); }
    } else {
      await api.sendMessage(chatId, report, { reply_markup: rm, disable_web_page_preview: true });
    }

  } catch (err) {
    console.error("Query failed:", err);
    try { await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id }); } catch (e) {}
    await api.sendMessage(chatId, "⚠️ Failed to check profile. Try again.");
  }
}
