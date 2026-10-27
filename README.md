
# TGM Community

A community platform for TGM Education's study-abroad students and prospects. Members join communities, post and chat, track their profile progress, use planning tools, and get guidance from the Amara AI assistant and TGM counsellors.

## Features

- **Member accounts:** sign up and log in
- **Communities:** Slack-style channels with posts, questions and replies
- **Chat and social features:** member-to-member interaction
- **Dashboard:** activity feed, community stats and a profile completion checklist
- **Leaderboard** and **ROI Calculator** (what studying abroad is worth after rent, tax and living costs)
- **Amara AI:** study-abroad assistant powered by Google Gemini, with a custom knowledge base and prompts
- **Counsellors:** counsellor directory, separate counsellor login and a counsellor portal
- **Admin area:** platform administration
- **WhatsApp integration:** TODO (describe what it does, for example notifications or lead capture)
- **Email:** weekly digests and study-abroad updates
- **Lead capture:** leads stored in a local database

## Tech stack

- Python 3.12 and Flask 3.1
- Jinja templates, HTML, CSS and JavaScript on the front end
- `requests` for calling external APIs (Gemini, WhatsApp)
- `python-dotenv` for loading settings from `.env`
- `PyMySQL` for MySQL (used when `DATABASE_URL` is set), otherwise a local SQLite file -- same schema either way

## Project structure

```
.
├── app/
│   ├── app.py                         # application entry point
│   ├── extensions.py                  # shared Flask extensions and setup
│   ├── requirements.txt
│   ├── .env.example                   # template for environment settings
│   ├── blueprints/                    # route modules
│   │   ├── admin.py
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── community.py
│   │   ├── counselor_auth.py
│   │   ├── counselor_portal.py
│   │   ├── counselors.py
│   │   ├── social.py
│   │   └── whatsapp.py
│   ├── services/                      # business logic and integrations
│   │   ├── amara.py                   # Amara AI assistant
│   │   ├── digest.py                  # weekly digest builder
│   │   ├── emailer.py                 # sending email
│   │   ├── gemini.py                  # Gemini API client
│   │   ├── knowledge_supplement.py    # extra knowledge for the assistant
│   │   ├── prompts.py                 # AI prompts
│   │   ├── study_updates.py           # study-abroad updates
│   │   └── whatsapp.py                # WhatsApp client
│   ├── scripts/                       # standalone jobs
│   │   ├── generate_study_abroad_update.py
│   │   └── send_weekly_digest.py
│   ├── data/                          # local runtime files, never committed
│   ├── static/                        # css, fonts, js
│   └── templates/                     # HTML templates
├── global-career-score.html           # Global Career Score page
├── global-career-score.source.html
└── .gitignore
```

## Getting started

### Requirements

- Python 3.12
- MySQL 5.7+ (or MariaDB), only if you set `DATABASE_URL` -- otherwise not needed

### Install

```bash
git clone https://github.com/<org>/<repo>.git
cd <repo>/app
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Copy the example settings file and fill in your own values:

```bash
cp .env.example .env
```

`.env.example` lists every setting the app needs. Expect values for the Flask secret key, the database, the Gemini API key, WhatsApp credentials and email (SMTP) settings. Never commit `.env`.

### Run locally

```bash
python app.py
```

TODO: confirm this is the correct start command and the port it runs on.

## Scheduled jobs

Run these from the `app` folder (TODO: confirm the exact commands and how they are scheduled, for example cron):

```bash
python scripts/generate_study_abroad_update.py
python scripts/send_weekly_digest.py
```

## Deployment

- Hosted on: TODO (server, domain)
- Served with: TODO (for example Gunicorn behind Nginx, managed by systemd)
- Deploy process: TODO (for example GitHub Actions on push to `main`)

## Security notes

- Secrets live only in `.env` and in the files under `app/data/`. They are never committed.
- Everything in `app/static` is public. Never put keys or tokens there.
- Do not commit `.venv`, `__pycache__`, `.pyc` files or database files.

## Contributing

1. Create a branch from `main`.
2. Make and test your changes locally.
3. Open a pull request with a clear description.

## Contact

TODO: the person or team who owns the platform.
