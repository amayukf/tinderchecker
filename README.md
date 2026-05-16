# Tinder Profile Analyzer - Telegram Bot

A production-ready Telegram bot that analyzes Tinder profile information using publicly available metadata.

## 🏗️ Architecture

- **Backend Framework:** FastAPI for healthchecks, background task execution, and REST endpoints.
- **Telegram Client:** `aiogram` v3 for async and efficient Telegram Bot API communication.
- **Database:** SQLite via `aiosqlite` and `SQLAlchemy` (Async) to log queries and rate-limit.
- **Data Scraping:** `httpx` + `BeautifulSoup4` to fetch OpenGraph metadata from public Tinder URLs.
- **Containerization:** Fully Dockerized setup via `docker-compose`.

## 📁 Folder Structure

```text
tinder/
├── app/
│   ├── __init__.py         # Package root
│   ├── main.py             # FastAPI entrypoint and Bot startup
│   ├── bot.py              # Telegram bot logic and handlers
│   ├── config.py           # Pydantic environment configuration
│   ├── database.py         # SQLAlchemy async engine and session
│   ├── models.py           # Database models (QueryLog)
│   ├── tinder_client.py    # Logic to fetch and parse Tinder data
├── data/                   # Persistent SQLite storage volume
├── Dockerfile              # Container definition
├── docker-compose.yml      # Orchestration definition
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
└── README.md               # Documentation
```

## 🚀 Deployment Guide

1. Clone or copy this repository to your server.
2. Rename `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor
   nano .env
   ```
3. Insert your `TELEGRAM_BOT_TOKEN` obtained from [@BotFather](https://t.me/botfather).
4. Build and start the container:
   ```bash
   docker-compose up -d --build
   ```
5. View logs to verify it is running successfully:
   ```bash
   docker-compose logs -f
   ```

## ⚠️ Important Limitations & Privacy Disclosures

To respect privacy laws, follow the Tinder Terms of Service, and stay within legitimate boundaries, this bot **only accesses publicly available OpenGraph metadata** through Tinder web links (`https://tinder.com/@username`).

Here are the strict limitations:

### 1. Impossible to Obtain Legitimately
- **Last Active Status:** Tinder removed the `last_active` field from its API globally years ago to protect user privacy. It simply does not exist in any accessible way.
- **Exact Distance / Location:** Cannot be calculated without an authenticated user session matching with the profile or being located near them.
- **Account Creation Date:** Tinder does not expose this to anyone (even via authenticated API) except the account holder directly in GDPR data exports.

### 2. Requires User Authorization (Authenticated API)
- **Verified Badge Status:** Requires an authenticated session payload to determine `is_verified`.
- **Photos Count & Full Gallery:** A public web profile generally only reveals the primary photo via OG tags. The complete gallery array requires an authenticated session.
- **Hidden / Private Profiles:** If a user disables "Show me on Tinder" or customizes their web profile visibility, even basic metadata will be hidden or return a 404.

### 3. What IS Available (Publicly)
- Profile Existence (Validating 200 vs 404 response).
- Public Display Name.
- Age (If explicitly shared on the web profile).
- Primary Profile Photo (via `og:image`).
- Bio Snippet (via `og:description`).

## 🛡️ Security & Compliance
- **Abuse Prevention:** Implemented an in-memory 10-second rate limit per user to prevent API spamming. (Production systems can replace this with Redis).
- **No Unauthorized Endpoints:** The bot only performs basic HTTP GET requests to public URLs and never bypasses authentication or uses stolen session tokens.
- **Error Handling:** Gracefully handles non-existent users, unexpected HTML payloads, and timeout issues without crashing.
