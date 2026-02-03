# AAU Grade Tracker Bot 🎓

An intelligent Telegram bot that automatically tracks and notifies Addis Ababa University students about their grade updates from the AAU portal.

## ✨ Features

- **🔔 Real-time Notifications**: Get instant alerts when new grades are posted
- **📊 Grade Tracking**: View all your grades organized by year and semester
- **🔄 Smart Refresh**: Manual grade refresh with intelligent caching (30-min cooldown)
- **👥 Group Intelligence**: Efficient background checking using random canary selection
- **🔐 Secure Storage**: Encrypted password storage using industry-standard cryptography
- **⏰ Smart Scheduling**: Automatic checks every 30 minutes (skips portal maintenance hours: midnight-6 AM)
- **📈 Detailed Analytics**: Track assessment breakdowns and semester summaries
- **🛡️ Resilient**: Automatic retry logic for portal downtime with exponential backoff

## 🚀 Quick Start

### For Students

1. **Start the bot**: Send `/start` to the bot
2. **Register**: Enter your University ID and portal password
3. **Select Department**: Choose your department code
4. **Done!**: The bot will automatically track your grades

### Available Commands

- `/start` - Register or view your dashboard
- `/my_data` - View and update your credentials
- `/check_grades` - Check grades for a specific year
- `/refresh` - Force refresh from portal (30-min cooldown)

## 🛠️ Deployment (Render Free Tier)

### Prerequisites

- GitHub account
- [Render](https://render.com) account (free tier)
- [Neon](https://neon.tech) PostgreSQL database (free tier)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### Environment Variables

Create an environment group called `aau-bot-secrets` in Render with:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=your_neon_postgresql_url
ENCRYPTION_KEY=random_32_character_string
WEBHOOK_URL=https://your-bot.onrender.com
CRON_SECRET=your_secret_token
ADMIN_IDS=comma_separated_telegram_ids
```

### Deployment Steps

1. **Push to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin your-repo-url
   git push -u origin main
   ```

2. **Deploy on Render**:
   - Go to Render Dashboard
   - Click **New +** → **Blueprint**
   - Connect your GitHub repository
   - Render will automatically read `render.yaml` and create the service

3. **Set up Free Cron Jobs** (on [cron-job.org](https://cron-job.org)):
   - **Job 1 - Heartbeat** (Every 5 minutes):
     - URL: `https://your-bot.onrender.com/health`
     - Purpose: Keeps the bot awake
   
   - **Job 2 - Grade Checker** (Every 30 minutes):
     - URL: `https://your-bot.onrender.com/api/cron-check?token=YOUR_CRON_SECRET`
     - Purpose: Triggers automatic grade checks

### Database Setup

Run the database initialization:
```bash
python init_db.py
```

## 🏗️ Architecture

### Tech Stack

- **Bot Framework**: aiogram 3.x (async Telegram bot framework)
- **Database**: PostgreSQL (via Neon) with SQLAlchemy ORM
- **Web Server**: aiohttp (for webhooks)
- **Security**: Cryptography library for password encryption
- **Parsing**: BeautifulSoup4 for portal HTML parsing

### Project Structure

```
.
├── bot/
│   └── handlers.py          # Telegram command handlers
├── database/
│   ├── connection.py        # Database connection setup
│   └── models.py            # SQLAlchemy models
├── portal/
│   ├── login_client.py      # AAU portal authentication
│   └── parser.py            # HTML parsing logic
├── services/
│   ├── user_service.py      # User management
│   ├── grade_service.py     # Grade tracking logic
│   ├── credential_service.py # Password encryption
│   └── notification_service.py # Telegram notifications
├── workers/
│   └── tasks.py             # Background grade checking
├── main.py                  # Application entry point
├── init_db.py              # Database initialization
├── render.yaml             # Render deployment config
└── requirements.txt        # Python dependencies
```

## 🔒 Security

- **Password Encryption**: All portal passwords are encrypted using Fernet (symmetric encryption)
- **Secure Storage**: Encryption keys are stored as environment variables
- **No Plaintext**: Passwords are never logged or stored in plaintext
- **Session Management**: Portal sessions are properly closed to prevent leaks

## 📊 How It Works

### Background Checking (Efficient & Fair)

1. **Group Deduplication**: Students are grouped by (Campus, Department, Year, Semester)
2. **Random Canary Selection**: For each group, a random student is selected as the "canary"
3. **Conditional Sync**: 
   - If the canary has new grades → Check all students in the group
   - If no changes → Skip the group (saves 90% of portal requests)
4. **Maintenance Sync**: Full sync every 24 hours to keep "Released for X students" counts accurate

### Retry Logic

- **Portal Down**: 3 automatic retries with delays of 2, 5, and 10 minutes
- **Bad Credentials**: Immediate notification, no retries
- **Maintenance Hours**: Automatically skips checks between midnight and 6 AM

## 🎯 Admin Features

Admins can control the service using:

- `/admin` - View admin dashboard
- `/start_service` - Enable automatic grade checking
- `/stop_service` - Disable automatic grade checking

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

For issues or questions, please open an issue on GitHub.

---