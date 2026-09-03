let dbBinding = null;

export function setDb(d1) {
  dbBinding = d1;
}

export async function ensureSchema() {
  if (!dbBinding) return;
  const cols = [
    "ALTER TABLE users ADD COLUMN referred_by INTEGER",
    "ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN referral_verified INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN query_count INTEGER DEFAULT 0",
  ];
  for (const sql of cols) {
    try { await dbBinding.prepare(sql).run(); } catch (e) {}
  }
}

export async function registerUser(userId, username, fullName, referredBy = null) {
  if (!dbBinding) return { isNew: false };
  try {
    const existing = await dbBinding.prepare("SELECT user_id FROM users WHERE user_id = ?").bind(userId).first();
    if (existing) {
      await dbBinding.prepare("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?")
        .bind(username || null, fullName || null, userId).run();
      return { isNew: false };
    } else {
      const refBy = (referredBy && referredBy !== userId) ? referredBy : null;
      await dbBinding.prepare(
        "INSERT INTO users (user_id, username, full_name, referred_by, referral_verified, referral_count, query_count, created_at) VALUES (?, ?, ?, ?, 0, 0, 0, CURRENT_TIMESTAMP)"
      ).bind(userId, username || null, fullName || null, refBy).run();
      return { isNew: true, referredBy: refBy };
    }
  } catch (err) {
    console.error("registerUser failed:", err);
    return { isNew: false };
  }
}

export async function logQueryAndIncrement(userId, query, status) {
  if (!dbBinding) return;
  try {
    await dbBinding.batch([
      dbBinding.prepare("INSERT INTO query_logs (user_id, username_or_url, status, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)").bind(userId, query, status),
      dbBinding.prepare("UPDATE users SET query_count = query_count + 1 WHERE user_id = ?").bind(userId),
    ]);
  } catch (err) {
    console.error("logQueryAndIncrement failed:", err);
  }
}

export async function tryVerifyReferral(userId) {
  if (!dbBinding) return null;
  try {
    const user = await dbBinding.prepare(
      "SELECT referred_by, referral_verified, query_count FROM users WHERE user_id = ?"
    ).bind(userId).first();

    if (!user || !user.referred_by || user.referral_verified) return null;
    if ((user.query_count || 0) < 1) return null;

    // Return referrer ID — caller should check channel membership then confirm
    return user.referred_by;
  } catch (err) {
    console.error("tryVerifyReferral failed:", err);
    return null;
  }
}

export async function confirmReferral(userId, referrerId) {
  if (!dbBinding) return;
  try {
    await dbBinding.batch([
      dbBinding.prepare("UPDATE users SET referral_verified = 1 WHERE user_id = ?").bind(userId),
      dbBinding.prepare("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?").bind(referrerId),
    ]);
  } catch (err) {
    console.error("confirmReferral failed:", err);
  }
}

export async function getStats() {
  if (!dbBinding) return { userCount: 0, queryCount: 0, totalReferrals: 0, pendingReferrals: 0 };
  try {
    const [uc, qc, tr, pr] = await Promise.all([
      dbBinding.prepare("SELECT COUNT(*) as c FROM users").first("c"),
      dbBinding.prepare("SELECT COUNT(*) as c FROM query_logs").first("c"),
      dbBinding.prepare("SELECT COALESCE(SUM(referral_count), 0) as c FROM users").first("c"),
      dbBinding.prepare("SELECT COUNT(*) as c FROM users WHERE referred_by IS NOT NULL AND referral_verified = 0").first("c"),
    ]);
    return { userCount: uc || 0, queryCount: qc || 0, totalReferrals: tr || 0, pendingReferrals: pr || 0 };
  } catch (err) {
    console.error("getStats failed:", err);
    return { userCount: 0, queryCount: 0, totalReferrals: 0, pendingReferrals: 0 };
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
    return (await dbBinding.prepare("SELECT referral_count FROM users WHERE user_id = ?").bind(userId).first("referral_count")) || 0;
  } catch (err) { return 0; }
}

export async function getAllUsers() {
  if (!dbBinding) return [];
  try {
    const { results } = await dbBinding.prepare(
      "SELECT id, user_id, username, full_name, referral_count, referral_verified, referred_by FROM users ORDER BY id ASC"
    ).all();
    return results || [];
  } catch (err) {
    console.error("getAllUsers failed:", err);
    return [];
  }
}
