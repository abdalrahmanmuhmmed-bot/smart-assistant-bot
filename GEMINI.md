# Project Instructions: Smart Assistant Bot

## Autonomous Workflow & Zero-Interruption
- Whenever a request is received, implement, test, and deploy end-to-end autonomously.
- Do NOT stop to ask for confirmation or approval on routine coding, testing, debugging, or deployment actions.
- Use `manage.py` for standard operations:
  - `py manage.py test`: Runs unit test suite.
  - `py manage.py deploy "<message>"`: Stages, commits, and pushes changes to GitHub main branch.
  - `py manage.py health`: Checks Render server status.
  - `py manage.py status`: Shows git status and cloud status.

## Deployment Target
- Hosting: Render (auto-deploys upon push to branch `main`).
- Live URL: `https://smart-assistant-bot-1jv0.onrender.com/`

## Bilingual Output Rules (Arabic + English)
- When responding in Arabic, never place an English word inline in an Arabic sentence.
- Always isolate English terms on their own dedicated line.
- Place emojis at the end of Arabic lines.
