const path = require('path');
const crypto = require('crypto');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const cookieParser = require('cookie-parser');

const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const Database = require('better-sqlite3');
const { Resend } = require('resend');
require('dotenv').config();

const app = express();
const PORT = Number(process.env.PORT || 5000);
const APP_ORIGIN = process.env.APP_ORIGIN || 'http://localhost:5173';
const APP_ORIGINS = (process.env.APP_ORIGINS || `${APP_ORIGIN},http://localhost:5174`)
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(64).toString('hex');
const JWT_EXPIRES_IN = '1h';
const OTP_SECRET = process.env.OTP_SECRET || crypto.randomBytes(64).toString('hex');
const RESEND_API_KEY = process.env.RESEND_API_KEY || '';
const RESEND_FROM = process.env.RESEND_FROM || 'onboarding@resend.dev';
const LOGIN_EMAIL = (process.env.LOGIN_EMAIL || 'saif.hlaimi@gmail.com').trim().toLowerCase();
const LOGIN_PASSWORD = process.env.LOGIN_PASSWORD || 'SS123.123.###@@@Account_';
const DASHBOARD_URL = process.env.DASHBOARD_URL || 'http://localhost:5173';
const TRUST_PROXY = process.env.TRUST_PROXY || '1';

const OTP_TTL_MS = 10 * 60 * 1000;
const LOGIN_LOCK_WINDOW_MS = 10 * 60 * 1000;
const MAX_LOGIN_FAILURES = 5;
const MAX_BODY_FIELD_LENGTH = 256;

const resend = RESEND_API_KEY ? new Resend(RESEND_API_KEY) : null;
const dbPath = process.env.AUTH_DB_PATH || path.join(__dirname, 'auth.db');
const db = new Database(dbPath);
const loginFailureMap = new Map();

app.set('trust proxy', TRUST_PROXY);

function buildEncryptionConfig() {
  const parsed = new Map();
  const keyList = String(process.env.DATA_ENCRYPTION_KEYS || '').trim();

  if (keyList) {
    for (const part of keyList.split(',')) {
      const [rawId, rawMaterial] = part.split(':');
      const keyId = String(rawId || '').trim();
      const material = String(rawMaterial || '').trim();
      if (!keyId || !material) continue;
      const key = /^[a-fA-F0-9]{64}$/.test(material)
        ? Buffer.from(material, 'hex')
        : crypto.createHash('sha256').update(material).digest();
      parsed.set(keyId, key);
    }
  }

  if (!parsed.size) {
    parsed.set('v1', crypto.createHash('sha256').update(OTP_SECRET).digest());
  }

  const activeId = process.env.ACTIVE_ENCRYPTION_KEY_ID && parsed.has(process.env.ACTIVE_ENCRYPTION_KEY_ID)
    ? process.env.ACTIVE_ENCRYPTION_KEY_ID
    : Array.from(parsed.keys())[0];

  return { keyMap: parsed, activeId };
}

const encryptionConfig = buildEncryptionConfig();

function getEncryptionKey(keyId) {
  return encryptionConfig.keyMap.get(keyId);
}

function encryptSensitive(plaintext) {
  const keyId = encryptionConfig.activeId;
  const key = getEncryptionKey(keyId);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from('users.email', 'utf8'));
  const encrypted = Buffer.concat([cipher.update(String(plaintext), 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${keyId}.${iv.toString('hex')}.${tag.toString('hex')}.${encrypted.toString('hex')}`;
}

function decryptSensitive(ciphertext) {
  if (!ciphertext || typeof ciphertext !== 'string') return '';
  const parts = ciphertext.split('.');
  if (parts.length !== 4) return '';
  const [keyId, ivHex, tagHex, dataHex] = parts;
  const key = getEncryptionKey(keyId);
  if (!key) return '';

  try {
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(ivHex, 'hex'));
    decipher.setAAD(Buffer.from('users.email', 'utf8'));
    decipher.setAuthTag(Buffer.from(tagHex, 'hex'));
    const decrypted = Buffer.concat([
      decipher.update(Buffer.from(dataHex, 'hex')),
      decipher.final(),
    ]);
    return decrypted.toString('utf8');
  } catch {
    return '';
  }
}

function normalizeEmail(value) {
  return String(value || '').trim().toLowerCase();
}

function hashEmailLookup(email) {
  return crypto.createHash('sha256').update(normalizeEmail(email)).digest('hex');
}

function sanitizeText(value, maxLen = MAX_BODY_FIELD_LENGTH) {
  return String(value || '')
    .replace(/[\u0000-\u001F\u007F]/g, '')
    .trim()
    .slice(0, maxLen);
}

function validateEmail(value) {
  const email = normalizeEmail(value);
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function getClientIp(req) {
  const forwarded = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  const base = forwarded || req.ip || req.socket?.remoteAddress || 'unknown';
  return sanitizeText(base, 80);
}

function getUserAgent(req) {
  return sanitizeText(req.headers['user-agent'] || 'unknown-agent', 180);
}

function getClientFingerprint(req, challengeId = '') {
  const ip = getClientIp(req);
  const userAgent = getUserAgent(req);
  return crypto
    .createHmac('sha256', OTP_SECRET)
    .update(`${ip}:${userAgent}:${challengeId}`)
    .digest('hex');
}

function getLoginLockKey(email, req) {
  return `${email}:${getClientIp(req)}`;
}

function checkLoginLock(lockKey) {
  const item = loginFailureMap.get(lockKey);
  if (!item) return false;
  if (item.lockedUntil && item.lockedUntil > Date.now()) return true;
  if (item.lockedUntil && item.lockedUntil <= Date.now()) {
    loginFailureMap.delete(lockKey);
  }
  return false;
}

function markLoginFailure(lockKey) {
  const now = Date.now();
  const item = loginFailureMap.get(lockKey) || { failures: 0, lockedUntil: 0, firstAt: now };
  if (now - item.firstAt > LOGIN_LOCK_WINDOW_MS) {
    item.failures = 0;
    item.firstAt = now;
  }
  item.failures += 1;
  if (item.failures >= MAX_LOGIN_FAILURES) {
    item.lockedUntil = now + LOGIN_LOCK_WINDOW_MS;
  }
  loginFailureMap.set(lockKey, item);
}

function clearLoginFailure(lockKey) {
  loginFailureMap.delete(lockKey);
}

function hashOtp(otp, challengeId) {
  return crypto.createHmac('sha256', OTP_SECRET).update(`${challengeId}:${otp}`).digest('hex');
}

function safeEqualHex(a, b) {
  try {
    const aa = Buffer.from(a, 'hex');
    const bb = Buffer.from(b, 'hex');
    if (aa.length !== bb.length) return false;
    return crypto.timingSafeEqual(aa, bb);
  } catch {
    return false;
  }
}

function generateOtp() {
  return String(crypto.randomInt(100000, 1000000));
}

function issueToken(payload) {
  return jwt.sign(payload, JWT_SECRET, {
    algorithm: 'HS256',
    expiresIn: JWT_EXPIRES_IN,
    issuer: 'twinforge-auth',
    audience: 'twinforge-ui',
  });
}

function getUserEmail(userRow) {
  const decrypted = decryptSensitive(userRow.email_enc || '');
  if (decrypted && validateEmail(decrypted)) return normalizeEmail(decrypted);
  if (userRow.email && userRow.email.includes('@')) return normalizeEmail(userRow.email);
  return '';
}

function authMiddleware(req, res, next) {
  const bearer = String(req.headers.authorization || '');
  const headerToken = bearer.startsWith('Bearer ') ? bearer.slice(7).trim() : '';
  const cookieToken = req.cookies.auth_token;
  const token = headerToken || cookieToken;

  if (!token) {
    return res.status(401).json({ error: 'Authentication required' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET, {
      algorithms: ['HS256'],
      issuer: 'twinforge-auth',
      audience: 'twinforge-ui',
    });
    req.user = decoded;
    return next();
  } catch {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}



function applySchemaMigrations() {
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS otp_challenges (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      otp_hash TEXT NOT NULL,
      client_fingerprint TEXT,
      expires_at INTEGER NOT NULL,
      attempts_left INTEGER NOT NULL,
      used INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
  `);

  const userColumns = db.prepare('PRAGMA table_info(users)').all();
  if (!userColumns.some((column) => column.name === 'email_hash')) {
    db.exec('ALTER TABLE users ADD COLUMN email_hash TEXT');
  }
  if (!userColumns.some((column) => column.name === 'email_enc')) {
    db.exec('ALTER TABLE users ADD COLUMN email_enc TEXT');
  }
  if (!userColumns.some((column) => column.name === 'enc_key_id')) {
    db.exec('ALTER TABLE users ADD COLUMN enc_key_id TEXT');
  }

  const otpColumns = db.prepare('PRAGMA table_info(otp_challenges)').all();
  if (!otpColumns.some((column) => column.name === 'client_fingerprint')) {
    db.exec('ALTER TABLE otp_challenges ADD COLUMN client_fingerprint TEXT');
  }

  db.exec('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_hash ON users(email_hash) WHERE email_hash IS NOT NULL');
}

function migrateSensitiveUsers() {
  const rows = db.prepare('SELECT id, email, email_hash, email_enc, enc_key_id FROM users').all();
  const updateStmt = db.prepare('UPDATE users SET email = ?, email_hash = ?, email_enc = ?, enc_key_id = ? WHERE id = ?');

  const tx = db.transaction((records) => {
    for (const row of records) {
      const plaintext = normalizeEmail(row.email || decryptSensitive(row.email_enc));
      if (!validateEmail(plaintext)) continue;
      const emailHash = hashEmailLookup(plaintext);
      const emailEnc = row.email_enc || encryptSensitive(plaintext);
      updateStmt.run(emailHash, emailHash, emailEnc, encryptionConfig.activeId, row.id);
    }
  });

  tx(rows);
}

applySchemaMigrations();
migrateSensitiveUsers();

const selectUserByEmailStmt = db.prepare('SELECT id, email, email_hash, email_enc, password_hash FROM users WHERE email_hash = ? OR email = ?');
const insertUserStmt = db.prepare('INSERT INTO users (email, email_hash, email_enc, enc_key_id, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)');
const insertOtpStmt = db.prepare('INSERT INTO otp_challenges (id, user_id, otp_hash, client_fingerprint, expires_at, attempts_left, used, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)');
const selectOtpStmt = db.prepare('SELECT id, user_id, otp_hash, client_fingerprint, expires_at, attempts_left, used FROM otp_challenges WHERE id = ?');
const updateOtpAttemptStmt = db.prepare('UPDATE otp_challenges SET attempts_left = ? WHERE id = ?');
const markOtpUsedStmt = db.prepare('UPDATE otp_challenges SET used = 1 WHERE id = ?');
const pruneOtpStmt = db.prepare('DELETE FROM otp_challenges WHERE used = 1 OR expires_at < ?');
const selectUserByIdStmt = db.prepare('SELECT id, email, email_hash, email_enc FROM users WHERE id = ?');

function seedUserIfMissing() {
  const emailHash = hashEmailLookup(LOGIN_EMAIL);
  const existing = selectUserByEmailStmt.get(emailHash, emailHash);
  if (existing) return;

  const hash = bcrypt.hashSync(LOGIN_PASSWORD, 13);
  const encryptedEmail = encryptSensitive(LOGIN_EMAIL);
  insertUserStmt.run(emailHash, emailHash, encryptedEmail, encryptionConfig.activeId, hash, Date.now());
}

seedUserIfMissing();

app.use(helmet({ crossOriginResourcePolicy: { policy: 'cross-origin' } }));
app.use(cors({
  origin: '*',
  credentials: false,
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));
app.use(express.json({ limit: '32kb' }));
app.use(cookieParser());

app.use((_req, res, next) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Pragma', 'no-cache');
  next();
});



app.get('/health', (_req, res) => {
  res.json({ status: 'ok', service: 'auth-backend' });
});

app.post('/auth/register', async (req, res) => {
  const email = normalizeEmail(sanitizeText(req.body?.email, 120));
  const password = sanitizeText(req.body?.password, 128);
  const honeypot = sanitizeText(req.body?.website, 32);

  if (honeypot) {
    return res.status(400).json({ error: 'Invalid request payload' });
  }

  if (!validateEmail(email)) {
    return res.status(400).json({ error: 'Please enter a valid email address.' });
  }

  if (password.length < 12) {
    return res.status(400).json({ error: 'Password must be at least 12 characters.' });
  }

  const emailHash = hashEmailLookup(email);
  const existing = selectUserByEmailStmt.get(emailHash, emailHash);
  if (existing) {
    return res.status(409).json({ error: 'An account with this email already exists.' });
  }

  try {
    const hash = await bcrypt.hash(password, 12);
    const encryptedEmail = encryptSensitive(email);
    insertUserStmt.run(emailHash, emailHash, encryptedEmail, encryptionConfig.activeId, hash, Date.now());
    console.log(`[Register] New account created for hash: ${emailHash.slice(0, 8)}...`);
    return res.status(201).json({ message: 'Account created! You can now sign in.' });
  } catch (err) {
    console.error('[Register] Error creating account:', err?.message || err);
    return res.status(500).json({ error: 'Failed to create account. Please try again.' });
  }
});

app.post('/auth/login', async (req, res) => {
  const email = normalizeEmail(sanitizeText(req.body?.email, 120));
  const password = sanitizeText(req.body?.password, 128);
  const honeypot = sanitizeText(req.body?.website, 32);

  if (honeypot) {
    return res.status(400).json({ error: 'Invalid request payload' });
  }

  const lockKey = getLoginLockKey(email, req);
  if (checkLoginLock(lockKey)) {
    return res.status(429).json({ error: 'Too many failed attempts. Try again later.' });
  }

  if (!validateEmail(email) || password.length < 12) {
    markLoginFailure(lockKey);
    return res.status(400).json({ error: 'Invalid credentials format' });
  }

  const emailHash = hashEmailLookup(email);
  const user = selectUserByEmailStmt.get(emailHash, emailHash);
  if (!user) {
    markLoginFailure(lockKey);
    return res.status(401).json({ error: 'Invalid email or password' });
  }

  const passOk = await bcrypt.compare(password, user.password_hash);
  if (!passOk) {
    markLoginFailure(lockKey);
    return res.status(401).json({ error: 'Invalid email or password' });
  }

  clearLoginFailure(lockKey);

  const userEmail = getUserEmail(user);
  if (!userEmail) {
    return res.status(500).json({ error: 'User account error' });
  }

  const token = issueToken({
    sub: String(user.id),
    email: userEmail,
    role: 'user',
  });

  res.cookie('auth_token', token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    maxAge: 60 * 60 * 1000,
    path: '/',
  });

  console.log(`[Login] Successful login for hash: ${emailHash.slice(0, 8)}...`);
  return res.json({
    expiresIn: 3600,
    redirectTo: DASHBOARD_URL,
  });
});

app.get('/auth/me', authMiddleware, (req, res) => {
  return res.json({
    user: {
      id: req.user.sub,
      email: req.user.email,
      role: req.user.role,
    },
  });
});

app.post('/auth/logout', (_req, res) => {
  res.clearCookie('auth_token', {
    httpOnly: true,
    sameSite: 'strict',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
  });
  return res.json({ ok: true });
});

app.listen(PORT, () => {
  console.log(`Auth backend running on http://localhost:${PORT}`);
});
