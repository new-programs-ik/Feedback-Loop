"""Every test run starts cut off from the real services.

The worker loads `ratings_module_build_kit/.env` when it is imported, and on a developer's machine
that file holds the PRODUCTION database, the real Claude key, the Vimeo token and the Slack token.
Until 23 September 2026 one endpoint test ran a real, paid Claude analysis and several reached the
production database, because nothing stopped them.

`config.load_env()` never overwrites a value that is already set. pytest imports this file before
any test module, so setting harmless values here means the real ones are never loaded during a
test run. A test that needs a database, the Claude API, Vimeo or Slack fakes it; one that forgets
fails at once instead of touching production.
"""
import os

os.environ["DATABASE_URL"] = "postgresql://tests:tests@127.0.0.1:9/never"   # a closed local port
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-tests-not-a-real-key"
for _name in ("VIMEO_ACCESS_TOKEN", "SLACK_BOT_TOKEN", "UPLEVEL_COOKIE", "WORKER_API_KEY",
              "RATINGS_SHEET_ID", "GOOGLE_SA_JSON", "GOOGLE_SA_JSON_FILE"):
    os.environ[_name] = ""
