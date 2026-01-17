# Chatbot Knowledge Base Monitor

Automated monitoring system for chatbot knowledge base file processing status. Detects failures, captures screenshots, triggers retries, and sends notifications to Lark.

## Features

- Automated login and navigation to admin panel
- Failure detection with visual confirmation (screenshots)
- Automatic retry trigger for failed items
- Lark notification with detailed reports
- Scheduled execution via macOS launchd (daily at 9:20 AM)
- Comprehensive logging with rotation
- Secure credential management

## Requirements

- macOS
- Python 3.10+
- Internet connection

## Installation

1. Clone or download this project:
```bash
cd /path/to/chatbot-kb-monitor
```

2. Run the setup script:
```bash
./scripts/setup.sh
```

3. Configure your credentials:
```bash
nano config/secrets.yaml
```

Add your credentials:
```yaml
credentials:
  username: "your_email@example.com"
  password: "your_password"

lark:
  webhook_url: "https://open.larksuite.com/open-apis/bot/v2/hook/..."
```

## Usage

### Manual Run

To run the monitor manually:
```bash
./scripts/run_monitor.sh
```

View logs:
```bash
tail -f logs/monitor.log
```

### Scheduled Run (Launchd)

Install the launchd agent for automatic daily execution:
```bash
./scripts/install_launchd.sh install
```

Check status:
```bash
./scripts/install_launchd.sh status
```

Uninstall:
```bash
./scripts/install_launchd.sh uninstall
```

## Project Structure

```
chatbot-kb-monitor/
├── config/
│   ├── config.example.yaml      # Configuration template
│   ├── config.yaml              # Main configuration
│   ├── secrets.example.yaml     # Secrets template
│   └── secrets.yaml             # Your credentials (not in git)
├── src/
│   ├── main.py                  # Entry point
│   ├── automation/
│   │   ├── browser_controller.py  # Playwright browser automation
│   │   ├── kb_monitor.py          # Core monitoring logic
│   │   └── retry_handler.py       # Retry logic with backoff
│   ├── notifications/
│   │   └── lark_notifier.py       # Lark webhook integration
│   └── utils/
│       ├── config_loader.py       # Configuration management
│       └── logger.py              # Logging setup
├── screenshots/                  # Screenshots storage
├── logs/                         # Log files
├── scripts/
│   ├── setup.sh                  # Installation script
│   ├── run_monitor.sh            # Manual run script
│   └── install_launchd.sh        # Launchd management
├── launchd/
│   └── com.chatbot.kbmonitor.plist  # macOS launchd config
├── requirements.txt
├── .gitignore
└── README.md
```

## Configuration

### Main Config (config/config.yaml)

Main application settings:
- Browser options (headless mode, timeouts)
- Monitoring settings (URL, KB name, navigation text)
- Failure detection patterns
- Retry settings
- Logging configuration

### Secrets (config/secrets.yaml)

Sensitive data (never commit this):
```yaml
credentials:
  username: "support@sparticle.com"
  password: "your_password"

lark:
  webhook_url: "https://open.larksuite.com/open-apis/bot/v2/hook/..."
```

## Workflow

1. **Login**: Browser opens and logs into admin.gbase.ai
2. **Navigate**: Clicks through to the KB files page
3. **Scan**: Identifies all items with failure status
4. **Capture**: Takes screenshots of failures and error details
5. **Retry**: Triggers retry for all failed items
6. **Notify**: Sends summary to Lark webhook

## Troubleshooting

### Setup Issues

**Playwright browsers not installed:**
```bash
source venv/bin/activate
playwright install chromium
```

**Dependencies not found:**
```bash
./scripts/setup.sh
```

### Runtime Issues

**Selectors not matching:**
- Check the actual page structure using browser dev tools
- Update selectors in `browser_controller.py` or use text-based navigation

**Login fails:**
- Verify credentials in `secrets.yaml`
- Check if the URL has changed
- Try running with `headless: false` to see the browser

**Launchd not running:**
- Check file paths in plist are absolute and correct
- View launchd logs: `tail -f logs/launchd.err`
- Test manually first: `./scripts/run_monitor.sh`

**Lark notification not received:**
- Verify webhook URL is correct
- Check if URL matches Lark region (open.larksuite.com vs open.feishu.cn)
- Check webhook is not expired

### Debugging

Enable debug logging in `config/config.yaml`:
```yaml
logging:
  level: "DEBUG"
```

Run with visible browser (edit config):
```yaml
browser:
  headless: false
```

## Security

- `secrets.yaml` is excluded from git
- File permissions set to 600 for secrets
- Sensitive data is redacted from logs
- Credentials are never displayed in error messages

## License

MIT License - See LICENSE file for details
