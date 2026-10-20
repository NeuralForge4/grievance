# Grievance AI: one product (website + backend + AI)

Landing page, official login and the prioritised-email dashboard, all served by one Flask app at one address.

## Run on Windows
```
pip install -r requirements.txt
run.bat
```
Open **http://127.0.0.1:5055** (demo logins: admin@gov.in / Admin@123, health@gov.in / Health@123, pwd@gov.in / Pwd@123).
Mac/Linux: `sh run.sh`. If the saved model was built with a different scikit-learn, it retrains itself automatically on first start.

## Turn on the real AI (Claude or Google Gemini)
The AI is OFF by default. Choose one provider and put its key in your own terminal, never in code or chat.

**Google Gemini (Windows):**
```
set GEMINI_API_KEY=your-gemini-api-key
set GAI_PROVIDER=gemini
set GAI_LLM=1
set GAI_LLM_MODEL=gemini-2.5-flash
run.bat
```

**Google Gemini (Mac/Linux):**
```
export GEMINI_API_KEY="your-gemini-api-key"
export GAI_PROVIDER=gemini
export GAI_LLM=1
export GAI_LLM_MODEL=gemini-2.5-flash
sh run.sh
```
Get a Gemini API key from https://aistudio.google.com/apikey.

**Claude (Windows):**
```
set ANTHROPIC_API_KEY=your-key
set GAI_PROVIDER=claude
set GAI_LLM=1
set GAI_LLM_MODEL=claude-haiku-5-5
run.bat
```
For Mac/Linux, use `export` instead of `set` for each variable, then run `sh run.sh`.

How it decides: the selected AI reads the email (personal details are masked first) -> safety rules can raise priority -> the local trained model cross-checks -> disagreements, low confidence and emails that try to instruct the AI go to **Needs human review**. If the AI service is down, the local model takes over automatically.
Privacy: with `GAI_LLM=1`, masked email text is sent to your selected provider (Google or Anthropic). Get your department's approval first (DPDP Act 2023). Without it, nothing leaves your server. Keep API keys private and do not commit them to source control.

## Real users (replace demo logins)
```
python -m gai.manage add-user rao@dept.gov.in "A. Rao" --role officer --dept "Health Department"
python -m gai.manage list-users
```
Do not run with GAI_SEED_DEMO in production (use `python -m gai.app`, set GAI_SECRET and GAI_HTTPS=1 behind HTTPS).

## Collect real emails
```
set IMAP_HOST=imap.gmail.com
set IMAP_USER=grievances@yourdept.gov.in
set IMAP_PASS=app-password
python -m gai.collector
```

## Fix the accuracy problem with REAL data
1. Officers use the dashboard: every priority they change or confirm is saved as a verified label.
2. `python -m gai.retrain` retrains the local model with those real emails (masked).
3. `python -m gai.evaluate your_labelled.csv` measures accuracy on your own labelled emails (template: data/labelled_template.csv). Aim for Critical emails missed = 0 before relying on it.

## Tests
`python -m pytest -q tests` (26 tests). The Claude path is tested with a simulated AI service; test it once with a real key and a few emails of your own.
The model accuracy table is measured on SYNTHETIC emails only (see models/metrics.json).
