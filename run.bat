@echo off
REM Demo mode: seeds 3 demo logins and sample emails. Opens on http://127.0.0.1:5055
set GAI_SEED_DEMO=1
set PORT=5055
python -m gai.app
