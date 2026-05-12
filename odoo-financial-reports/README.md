# Odoo Financial Reports

READ-ONLY discovery and reporting tool for Odoo.

---

## Purpose

Connects to an Odoo instance and produces structured reports on its accounting data.
**No data is ever written, modified, or deleted.**

Current phase: **Phase 1 — Discovery** (this repo)
Next phase: Phase 2 — Financial Reports (not yet started)

---

## Safety Guarantees

The client (`src/odoo_client.py`) enforces a hard block on all write operations:

**Forbidden methods (will raise `PermissionError`):**
- `create`, `write`, `unlink`, `copy`, `copy_data`
- `create_multi`, `write_multi`, `browse_write`
- `toggle_active`, `archive`, `unarchive`
- `load`, `import_data`
- Any method starting with: `action_`, `button_`, `do_`, `set_`

**Allowed methods only:**
- `search`, `read`, `search_read`, `search_count`
- `fields_get`, `name_search`, `name_get`, `default_get`

---

## Setup

**1. Create and activate a virtual environment**

```bash
# Linux / macOS
python -m venv venv && source venv/bin/activate

# Windows
python -m venv venv && .\venv\Scripts\activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure credentials**

Copy `.env.example` to `.env` (or edit the existing `.env`) and fill in your credentials:

```env
ODOO_URL=https://yourcompany.odoo.com
ODOO_USERNAME=you@example.com
ODOO_API_KEY=your_api_key_here

# Leave ODOO_DB empty to let the tool auto-detect it
ODOO_DB=
```

> **API key vs password**: Odoo 14+ supports API keys (Settings → Technical → API Keys).
> For older versions, use your regular password.

**4. Run the discovery**

```bash
python -m src.discovery
```

Outputs are written to `output/discovery/`:
- `discovery_<timestamp>.json` — full raw data
- `SUMMARY.md` — human-readable summary with Phase 2 recommendations

---

## Troubleshooting

### "Database not detected"
The tool tried several strategies to find the database name automatically.
If all fail:
1. Open `https://<your-odoo-url>/web/database/selector` in a browser
2. Check the **Database** field on the Odoo login screen
3. Ask your Odoo administrator for the database name
4. Set `ODOO_DB=<name>` in your `.env` file and re-run

### "Authentication failed"
- Verify `ODOO_USERNAME` is your full login email
- For Odoo 14+: generate an API key under Settings → Technical → API Keys and use it as `ODOO_API_KEY`
- For older Odoo: use your regular login password as `ODOO_API_KEY`
- Make sure your user has access to the accounting module

### "Connection refused" / "Connection error"
- Check that `ODOO_URL` has no trailing slash (correct: `https://x.odoo.com`)
- Check that `ODOO_URL` includes the protocol (`https://`)
- Verify the Odoo server is reachable from your network

---

## Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Discovery — auto-detect DB, version, modules, structure | **Current** |
| Phase 2 | Financial Reports — P&L, Balance Sheet, AR/AP, etc. | Planned |
