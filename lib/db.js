let dbBinding = null;

export function setDb(d1) {
  dbBinding = d1;
}

export async function ensureSchema() {
  if (!dbBinding) return;
  try {
    // Add referral columns if they don't exist
    await dbBinding.prepare(`ALTER TABLE users ADD COLUMN referred_by INTEGER`).run();
  } catch (e) {} // column already exists
  try {
    await dbBinding.prepare(`ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0`).run();
  } catch (e) {} // column already exists
}

export async function registerUser(userId, username, fullName, referredBy = null) {
  if (!dbBinding) return;
  try {
    // Check if user already exists
    const existing = await dbBinding.prepare("SELECT user_id FROM users WHERE user_id = ?").bind(userId).first();
    
    if (existing) {
      // Update existing user
      await dbBinding.prepare(`
        UPDATE users SET username = ?, full_name = ? WHERE user_id = ?
      `).bind(username || null, fullName || null, userId).run();
    } else {
      // Insert new user with referral info
      await dbBinding.prepare(`
        INSERT INTO users (user_id, username, full_name, referred_by, referral_count, created_at)
        VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
      `).bind(userId, username || null, fullName || null, referredBy || null).run();
      
      // Credit the referrer
      if (referredBy && referredBy !== userId) {
        await dbBinding.prepare(`
          UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?
        `).bind(referredBy).run();
      }
      
      return { isNew: true, referredBy };
    }
    return { isNew: false };
  } catch (err) {
    console.error("registerUser failed:", err);
    return { isNew: false };
  }
}

export async function logQuery(userId, query, status) {
  if (!dbBinding) return;
  try {
    await dbBinding.prepare(`
      INSERT INTO query_logs (user_id, username_or_url, status, created_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP);
    `).bind(userId, query, status).run();
  } catch (err) {
    console.error("logQuery failed:", err);
  }
}

export async function getStats() {
  if (!dbBinding) return { userCount: 0, queryCount: 0, totalReferrals: 0 };
  try {
    const userCountRes = await dbBinding.prepare("SELECT COUNT(*) as count FROM users").first("count");
    const queryCountRes = await dbBinding.prepare("SELECT COUNT(*) as count FROM query_logs").first("count");
    const totalReferralsRes = await dbBinding.prepare("SELECT COALESCE(SUM(referral_count), 0) as total FROM users").first("total");
    return {
      userCount: userCountRes || 0,
      queryCount: queryCountRes || 0,
      totalReferrals: totalReferralsRes || 0
    };
  } catch (err) {
    console.error("getStats failed:", err);
    return { userCount: 0, queryCount: 0, totalReferrals: 0 };
  }
}

export async function getTopReferrers(limit = 5) {
  if (!dbBinding) return [];
  try {
    const { results } = await dbBinding.prepare(
      "SELECT user_id, username, referral_count FROM users WHERE referral_count > 0 ORDER BY referral_count DESC LIMIT ?"
    ).bind(limit).all();
    return results || [];
  } catch (err) {
    console.error("getTopReferrers failed:", err);
    return [];
  }
}

export async function getReferralCount(userId) {
  if (!dbBinding) return 0;
  try {
    const res = await dbBinding.prepare("SELECT referral_count FROM users WHERE user_id = ?").bind(userId).first("referral_count");
    return res || 0;
  } catch (err) {
    console.error("getReferralCount failed:", err);
    return 0;
  }
}

export async function getAllUsers() {
  if (!dbBinding) return [];
  try {
    const { results } = await dbBinding.prepare("SELECT id, user_id, username, full_name, referral_count FROM users ORDER BY id ASC").all();
    return results || [];
  } catch (err) {
    console.error("getAllUsers failed:", err);
    return [];
  }
}
