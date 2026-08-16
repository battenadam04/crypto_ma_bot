# Business portfolio — standalone extract

The portfolio site lives on orphan branch:

**`cursor/business-portfolio-standalone-d97d`**

Clone it alone:

```bash
git clone --single-branch --branch cursor/business-portfolio-standalone-d97d \
  https://github.com/battenadam04/crypto_ma_bot.git business-portfolio
cd business-portfolio
npm install
cp .env.example .env
npm run db:setup
npm run dev
```

## Move to a new GitHub repository

The Cursor GitHub App for this agent can only write to `crypto_ma_bot` and cannot create repos.

1. Create an empty public repo (e.g. `business-portfolio`) with **no** README/license.
2. Grant the Cursor GitHub App access to that repo.
3. Reply in the agent chat with the new repo URL so it can push `main`.

Or push yourself:

```bash
cd business-portfolio
gh repo create battenadam04/business-portfolio --public --source=. --remote=origin --push
```

## Do not merge

Do **not** merge `cursor/business-portfolio-standalone-d97d` (or this notes branch) into `master` — that would replace the trading bot with the website.

Previous mixed history PR: #8 (`cursor/portfolio-site-f7bf`).
