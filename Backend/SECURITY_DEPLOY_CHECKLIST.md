# Security Deployment Checklist (Docker + Cloudflare)

## 1) Network & Access Gate
- Expose only the login frontend publicly.
- Keep backend (`5000`), dashboard (`8001`), and orchestrator (`8002`) private inside Docker network.
- Put Cloudflare Tunnel in front of the frontend only.
- Deny direct origin IP access at firewall level.

## 2) HTTPS / TLS
- Enforce HTTPS-only traffic (Cloudflare `Always Use HTTPS`).
- Enable HSTS at edge and origin.
- Use `Secure` cookies in production (`NODE_ENV=production`).
- Never allow plain HTTP in production.

## 3) Secret Management
- Store secrets in Docker secrets / cloud secret manager (not git):
  - `JWT_SECRET`
  - `OTP_SECRET`
  - `RESEND_API_KEY`
  - `DATA_ENCRYPTION_KEYS`
  - `ACTIVE_ENCRYPTION_KEY_ID`
- Rotate secrets on schedule.

## 4) Encryption at Rest (Implemented)
- Email is stored encrypted (`email_enc`) and indexed via SHA-256 lookup hash (`email_hash`).
- Ciphertext contains key id, enabling key rotation compatibility.

## 5) Key Rotation Procedure
1. Add new key to `DATA_ENCRYPTION_KEYS` (keep old key present).
2. Set `ACTIVE_ENCRYPTION_KEY_ID` to new key id.
3. Restart backend and run controlled user re-encryption migration job.
4. Remove old key only after all rows are re-encrypted and verified.

## 6) Auth Gate (Implemented)
- Dashboard server validates backend session (`/auth/me`) before serving pages/APIs/websockets.
- Unauthenticated requests are redirected to login.
- API requests without auth receive `401`.

## 7) Abuse Protection
- Keep rate limits enabled.
- Keep brute-force lockout enabled.
- Keep OTP context binding enabled.
- Keep honeypot field enabled.

## 8) Monitoring & Alerts
- Track 401/403/429 spikes.
- Track failed OTP/login attempts.
- Alert on unusual authentication volume by IP/User-Agent.

## 9) Production Hardening
- Set strict CORS origins (`APP_ORIGINS`).
- Run services with non-root users in Docker.
- Use read-only filesystem where possible.
- Keep dependency scans and patch cadence active.
