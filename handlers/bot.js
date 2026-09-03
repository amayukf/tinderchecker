import { api } from '../lib/api.js';
import * as db from '../lib/db.js';
import { TinderClient, extractUsername } from '../lib/tinder.js';

const tinderClient = new TinderClient();
const userRateLimit = new Map();
const RATE_LIMIT_SECONDS = 5;

const REQUIRED_CHANNEL = "@N_Notic";
const CHANNEL_URL = "https://t.me/N_Notic";

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function checkChannelMembership(userId) {
  try {
    const result = await api._request('getChatMember', {
      chat_id: REQUIRED_CHANNEL,
      user_id: userId
    });
    return ['member', 'administrator', 'creator'].includes(result.status);
  } catch (err) {
    console.error("Channel membership check failed:", err);
    return false;
  }
}

async function sendJoinPrompt(chatId) {
  await api.sendMessage(chatId,
    `🔒 <b>Channel Membership Required!</b>\n\n` +
    `To use this bot, you must first join our channel:\n` +
    `👉 ${CHANNEL_URL}\n\n` +
    `After joining, tap <b>✅ I've Joined</b> below.`,
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

// Handle callback queries (e.g. "I've Joined" button)
export async function handleCallbackQuery(callbackQuery, env) {
  if (!callbackQuery || !callbackQuery.from) return;

  const data = callbackQuery.data;
  const telegramId = callbackQuery.from.id;
  const chatId = callbackQuery.message?.chat?.id;
  const messageId = callbackQuery.message?.message_id;

  if (data === "check_joined") {
    const isMember = await checkChannelMembership(telegramId);
    if (isMember) {
      // Edit the original message
      try {
        await api._request('editMessageText', {
          chat_id: chatId,
          message_id: messageId,
          text: `✅ <b>Verified!</b> You are now a member.\n\n🔥 Send me any Tinder username to start checking profiles!`,
          parse_mode: 'HTML'
        });
      } catch (e) {}
      await api._request('answerCallbackQuery', {
        callback_query_id: callbackQuery.id,
        text: "✅ Verified! You can now use the bot."
      });
    } else {
      await api._request('answerCallbackQuery', {
        callback_query_id: callbackQuery.id,
        text: "❌ You haven't joined yet! Please join the channel first.",
        show_alert: true
      });
    }
  }
}

export default async function handleMessage(message, env) {
  if (!message || !message.from || !message.chat) {
    return;
  }

  const telegramId = message.from.id;
  const chatId = message.chat.id;
  const username = message.from.username || null;
  const firstName = message.from.first_name || "";
  const lastName = message.from.last_name || "";
  const fullName = [firstName, lastName].filter(Boolean).join(" ");
  const text = (message.text || "").trim();

  const ownerIds = (env.OWNER_ID || "")
    .split(",")
    .map(id => id.trim())
    .filter(Boolean);

  const isAdmin = ownerIds.includes(String(telegramId));

  // 1. Process CMD_START
  if (text.startsWith("/start")) {
    // Extract referral ID from deep link
    let referrerId = null;
    const parts = text.split(" ");
    if (parts.length > 1 && parts[1].startsWith("ref_")) {
      try {
        referrerId = parseInt(parts[1].replace("ref_", ""), 10);
        if (isNaN(referrerId)) referrerId = null;
      } catch (e) {}
    }

    const regResult = await db.registerUser(telegramId, username, fullName, referrerId);
    
    // Notify referrer if this is a new user
    if (regResult && regResult.isNew && regResult.referredBy) {
      try {
        await api.sendMessage(regResult.referredBy,
          `🎉 <b>New Referral!</b>\n\n` +
          `<a href='tg://user?id=${telegramId}'>${escapeHtml(fullName || 'Someone')}</a> ` +
          `joined using your referral link!\n` +
          `Use /refer to see your total referrals.`
        );
      } catch (e) {}
    }

    // Check channel membership
    const isMember = await checkChannelMembership(telegramId);
    if (!isMember) {
      await sendJoinPrompt(chatId);
      return;
    }

    // Get bot username for referral link
    let botUsername = "tinderchecker_bot";
    try {
      const me = await api._request('getMe');
      botUsername = me.username;
    } catch (e) {}
    
    const referralLink = `https://t.me/${botUsername}?start=ref_${telegramId}`;
    
    const welcomeText = 
      `🔥 <b>Welcome to Premium Tinder OSINT & DNA Checker!</b> 🔥\n\n` +
      `🎯 Send me any Tinder username to inspect status, account age & OSINT risk score.\n\n` +
      `<i>Examples:</i>\n` +
      `• boy\n` +
      `• @boy\n` +
      `• tinder.com/@boy\n\n` +
      `📎 <b>Your Referral Link:</b>\n<code>${referralLink}</code>\n` +
      `Share it & earn referral credits!`;

    await api.sendMessage(chatId, welcomeText, {
      reply_markup: {
        inline_keyboard: [[{ text: "📢 Join Channel", url: CHANNEL_URL }]]
      },
      disable_web_page_preview: true
    });
    return;
  }

  // 2. Owner-only: CMD_DEBUG
  if (text.startsWith("/debug")) {
    if (!isAdmin) return;
    const isOwner = String(telegramId) === ownerIds[0];
    const status = isOwner ? "✅ Owner" : "❌ User";
    await api.sendMessage(chatId, 
      `🛠️ <b>Debug Info:</b>\n` +
      `• Your ID: <code>${telegramId}</code>\n` +
      `• Owner ID in config: <code>${env.OWNER_ID}</code>\n` +
      `• Match: ${status}`
    );
    return;
  }

  // 3. CMD_REFER - anyone can use
  if (text.startsWith("/refer")) {
    const isMember = await checkChannelMembership(telegramId);
    if (!isMember) {
      await sendJoinPrompt(chatId);
      return;
    }

    let botUsername = "tinderchecker_bot";
    try {
      const me = await api._request('getMe');
      botUsername = me.username;
    } catch (e) {}
    
    const referralLink = `https://t.me/${botUsername}?start=ref_${telegramId}`;
    const referralCount = await db.getReferralCount(telegramId);

    await api.sendMessage(chatId,
      `🔗 <b>Your Referral Dashboard</b>\n\n` +
      `📎 <b>Your Link:</b>\n<code>${referralLink}</code>\n\n` +
      `👥 <b>Total Referrals:</b> <code>${referralCount}</code>\n\n` +
      `Share your link — every new user who joins counts towards your referrals!`,
      { disable_web_page_preview: true }
    );
    return;
  }

  // 4. Owner-only: CMD_STATS
  if (text.startsWith("/stats")) {
    if (!isAdmin) return;
    try {
      const stats = await db.getStats();
      const apiHealth = await tinderClient.pingEndpoints();
      const healthText = Object.entries(apiHealth)
        .map(([domain, status]) => `• <code>${domain}</code>: ${status}`)
        .join("\n");

      const topReferrers = await db.getTopReferrers(5);
      let topRefText = "";
      if (topReferrers.length) {
        const medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"];
        topRefText = "\n🏆 <b>Top Referrers:</b>\n";
        topReferrers.forEach((r, i) => {
          const display = r.username ? `@${r.username}` : `<code>${r.user_id}</code>`;
          topRefText += `${medals[i]} ${display}: <code>${r.referral_count}</code> referrals\n`;
        });
      }

      const statsReport = 
        `⚡ <b>TINDER BOT SUPERPOWERS DASHBOARD</b> ⚡\n` +
        `═══════════════════════════════════════\n\n` +
        `📊 <b>Telemetry & Database (Cloudflare D1):</b>\n` +
        `• Total Users: <code>${stats.userCount}</code>\n` +
        `• Total Queries Run: <code>${stats.queryCount}</code>\n\n` +
        `🔗 <b>Referral System:</b>\n` +
        `• Total Referrals: <code>${stats.totalReferrals}</code>\n` +
        `${topRefText}\n` +
        `🌐 <b>API Health Matrix (Multi-Failover):</b>\n` +
        `${healthText}\n\n` +
        `═══════════════════════════════════════`;

      await api.sendMessage(chatId, statsReport);
    } catch (err) {
      await api.sendMessage(chatId, `❌ DB Error: ${escapeHtml(err.message)}`);
    }
    return;
  }

  // 5. Owner-only: CMD_USERS
  if (text.startsWith("/users")) {
    if (!isAdmin) return;
    try {
      const users = await db.getAllUsers();
      if (!users.length) {
        await api.sendMessage(chatId, "📝 No users registered yet.");
        return;
      }

      let fileContent = "👥 TINDER BOT REGISTERED USERS\n" + "=".repeat(30) + "\n\n";
      users.forEach((u, i) => {
        const uName = u.username || "No Username";
        const fName = u.full_name || "Unknown";
        const refCount = u.referral_count || 0;
        fileContent += `${i + 1}. ${fName} (@${uName}) | ID: ${u.user_id} | Referrals: ${refCount}\n`;
      });

      const encoder = new TextEncoder();
      const buffer = encoder.encode(fileContent);
      
      await api.sendDocument(chatId, buffer, "users_list.txt", 
        `✅ <b>Total Users Found:</b> <code>${users.length}</code>\n\nFull user list generated successfully.`
      );
    } catch (err) {
      await api.sendMessage(chatId, `❌ Error exporting list: ${escapeHtml(err.message)}`);
    }
    return;
  }

  // 6. Owner-only: CMD_BROADCAST
  if (text.startsWith("/broadcast")) {
    if (!isAdmin) return;
    const broadcastMsg = text.replace("/broadcast", "").trim();
    const replyMsg = message.reply_to_message;

    if (!broadcastMsg && !replyMsg) {
      await api.sendMessage(chatId, "⚠️ Please provide a message or reply to a message to broadcast.");
      return;
    }

    await api.sendMessage(chatId, "📢 <b>Starting broadcast...</b>");
    const users = await db.getAllUsers();

    let successCount = 0;
    let failedCount = 0;

    for (const u of users) {
      try {
        if (replyMsg) {
          if (replyMsg.photo) {
            const photoId = replyMsg.photo[replyMsg.photo.length - 1].file_id;
            await api.sendPhoto(u.user_id, photoId, replyMsg.caption || "");
          } else {
            await api.sendMessage(u.user_id, replyMsg.text || "");
          }
        } else {
          await api.sendMessage(u.user_id, broadcastMsg);
        }
        successCount++;
      } catch (err) {
        failedCount++;
      }
      await new Promise(r => setTimeout(r, 60));
    }

    try {
      await api.sendMessage(chatId, 
        `✅ <b>Broadcast Finished!</b>\n\n` +
        `• Targeted: ${users.length}\n` +
        `• Success: ${successCount}\n` +
        `• Failed: ${failedCount}`
      );
    } catch (err) {}
    return;
  }

  // 7. Generic Tinder checker query handling
  // Force channel membership on every query
  const isMember = await checkChannelMembership(telegramId);
  if (!isMember) {
    await sendJoinPrompt(chatId);
    return;
  }

  await db.registerUser(telegramId, username, fullName);

  const now = Date.now();
  if (userRateLimit.has(telegramId)) {
    const lastRequest = userRateLimit.get(telegramId);
    const elapsedSeconds = (now - lastRequest) / 1000;
    if (elapsedSeconds < RATE_LIMIT_SECONDS) {
      const remaining = Math.ceil(RATE_LIMIT_SECONDS - elapsedSeconds);
      await api.sendMessage(chatId, `⏳ Please wait ${remaining} seconds before sending another request.`);
      return;
    }
  }
  userRateLimit.set(telegramId, now);

  const tinderUsername = extractUsername(text);
  if (!tinderUsername) {
    await api.sendMessage(chatId, "❌ Invalid format. Please send a valid Tinder URL or username.");
    return;
  }

  const checkingMsg = await api.sendMessage(chatId, `🔍 Analyzing profile for <b>${escapeHtml(tinderUsername)}</b>...`);

  try {
    const data = await tinderClient.getProfileData(tinderUsername);
    const riskInfo = data.risk_analysis || {};
    const SEP = "═══════════════════════════════════════";

    if (data.status === "not_found" || data.is_restricted) {
      const statusText = data.is_restricted ? "🔴 SHADOWBANNED" : "❌ BANNED / DELETED";
      const report = 
        `${SEP}\n` +
        `💣 Tinder DNA & OSINT Analysis 💥\n` +
        `${SEP}\n\n` +
        `🔴 Account: <code>${statusText}</code>\n` +
        `🛡️ Risk Rating: <b>${riskInfo.badge || '🔴 HIGH RISK'}</b>\n\n` +
        `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n` +
        `🪪 Username: <code>@${escapeHtml(tinderUsername)}</code>\n\n` +
        `${SEP}\n` +
        `🧪 Analysis Complete\n` +
        `${SEP}`;

      await db.logQuery(telegramId, tinderUsername, "not_found");
      
      try {
        await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id });
      } catch (e) {}

      await api.sendMessage(chatId, report, {
        reply_markup: {
          inline_keyboard: [
            [{ text: "🌹 Open Profile", url: `https://tinder.com/@${tinderUsername}` }],
            [{ text: "📢 Join Channel", url: CHANNEL_URL }]
          ]
        }
      });

      if (ownerIds.length && !isAdmin) {
        try {
          const nameClean = escapeHtml(fullName || "Unknown");
          const userClean = escapeHtml(username || "No Username");
          const primaryOwner = ownerIds[0];
          
          const logText = 
            `📊 <b>Bot Query (Inactive Profile)</b>\n\n` +
            `• <b>User:</b> <a href='tg://user?id=${telegramId}'>${nameClean}</a>\n` +
            `• <b>Username:</b> @${userClean}\n` +
            `• <b>User ID:</b> <code>${telegramId}</code>\n` +
            `• <b>Language:</b> 🌐 <code>${escapeHtml(message.from.language_code || 'Unknown')}</code>\n` +
            `• <b>Telegram Premium:</b> ${message.from.is_premium ? "👑 Yes" : "❌ No"}\n` +
            `• <b>Queried Profile:</b> @${escapeHtml(tinderUsername)}\n` +
            `• <b>Status:</b> ❌ Profile not active/Banned`;
          
          await api.sendMessage(primaryOwner, logText);
        } catch (e) {}
      }
      return;
    }

    if (data.status === "error") {
      await db.logQuery(telegramId, tinderUsername, "error");
      try {
        await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id });
      } catch (e) {}
      await api.sendMessage(chatId, "⚠️ An error occurred while fetching the profile. Please try again later.");
      return;
    }

    await db.logQuery(telegramId, tinderUsername, "success");

    const creationDateVal = data.creation_date || "Unknown";
    const photosCount = data.photos_count || 0;
    const ageValue = data.age;
    const name = escapeHtml(data.name || "Hidden");
    const birthDate = escapeHtml(data.birth_date || "Hidden");
    const accountAge = data.account_age || "Not available";
    const accountId = data.account_id || "Hidden";
    const verifiedStr = data.verified ? "⚙️ Verified" : "⚙️ Not Verified";
    const ageDisplay = ageValue && ageValue !== "Unknown" ? `${ageValue} years` : "Unknown";

    const scoreNum = riskInfo.score !== undefined ? riskInfo.score : 100;
    const riskLevel = riskInfo.level || "🟢 Low Risk";

    const report = 
      `${SEP}\n` +
      `🔥 Tinder DNA & OSINT Result ✨\n` +
      `${SEP}\n\n` +
      `🟢 Account Status: Active Account\n` +
      `🛡️ Risk Score: <b>${scoreNum}/100</b> (${riskLevel})\n\n` +
      `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n` +
      `🪪 Username: <code>@${escapeHtml(tinderUsername)}</code>\n` +
      `👤 Display Name: ${name}\n` +
      `🎂 Birth Date: ${birthDate}\n` +
      `🕒 User Age: ${ageDisplay}\n` +
      `📸 Photos: ${photosCount}\n` +
      `⏳ Account Age: ${accountAge}\n` +
      `📆 Registration: ${escapeHtml(creationDateVal)}\n` +
      `🆔 Account ID: <code>${accountId}</code>\n` +
      `⚙️ Verification: ${verifiedStr}\n\n` +
      `${SEP}\n` +
      `🧪 Analysis Complete\n` +
      `${SEP}`;

    try {
      await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id });
    } catch (e) {}

    const replyMarkup = {
      inline_keyboard: [
        [{ text: "🌹 Open Profile", url: `https://tinder.com/@${tinderUsername}` }],
        [
          { text: "💸 Sell This Account", url: "https://t.me/T_ump" },
          { text: "📢 Join Channel", url: CHANNEL_URL }
        ]
      ]
    };

    if (ownerIds.length && !isAdmin) {
      try {
        const nameClean = escapeHtml(fullName || "Unknown");
        const userClean = escapeHtml(username || "No Username");
        const primaryOwner = ownerIds[0];
        const statusLog = data.is_restricted ? "⚠️ Limited Account" : "✅ Active Account";
        
        const logText = 
          `📊 <b>New Bot Query (Success)!</b>\n\n` +
          `• <b>User:</b> <a href='tg://user?id=${telegramId}'>${nameClean}</a>\n` +
          `• <b>Username:</b> @${userClean}\n` +
          `• <b>User ID:</b> <code>${telegramId}</code>\n` +
          `• <b>Language:</b> 🌐 <code>${escapeHtml(message.from.language_code || 'Unknown')}</code>\n` +
          `• <b>Telegram Premium:</b> ${message.from.is_premium ? "👑 Yes" : "❌ No"}\n` +
          `• <b>Queried Profile:</b> @${escapeHtml(tinderUsername)}\n` +
          `• <b>Upstream Provider:</b> ⚙️ <code>${data.token_status || 'Unknown'}</code>\n` +
          `• <b>Status:</b> ${statusLog}`;

        await api.sendMessage(primaryOwner, logText);
      } catch (e) {}
    }

    if (data.image_url) {
      try {
        await api.sendPhoto(chatId, data.image_url, report, { reply_markup: replyMarkup });
      } catch (err) {
        await api.sendMessage(chatId, report, { reply_markup: replyMarkup, disable_web_page_preview: true });
      }
    } else {
      await api.sendMessage(chatId, report, { reply_markup: replyMarkup, disable_web_page_preview: true });
    }

  } catch (err) {
    console.error("Tinder validation check failed:", err);
    await db.logQuery(telegramId, tinderUsername, "error");
    try {
      await api._request('deleteMessage', { chat_id: chatId, message_id: checkingMsg.message_id });
    } catch (e) {}
    await api.sendMessage(chatId, "⚠️ Failed to parse tinder profile. Please verify username and retry.");
  }
}
