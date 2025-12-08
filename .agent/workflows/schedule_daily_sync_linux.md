---
description: How to schedule the contact sync to run daily on Linux (Ubuntu) using cron
---

# Schedule Daily Contact Sync (Linux/Ubuntu)

Follow these steps to configure a cron job to run the `sync_contacts` command automatically every day.

## Prerequisites

- **Project Path**: Ensure you know the absolute path to your project.
  - Example: `/home/ubuntu/Vossie` or `/var/www/Vossie`
- **Virtual Environment**: Ensure you know the path to your virtual environment's Python executable.
  - Example: `/home/ubuntu/Vossie/.venv/bin/python`

## Step-by-Step Guide

1. **Open Crontab**
   Open the crontab editor for the user who owns the project files (e.g., `ubuntu` or `www-data`):

   ```bash
   crontab -e
   ```

2. **Add the Cron Entry**
   Add a new line at the bottom of the file to run the command daily (e.g., at 3:00 AM).

   **Format:**
   `Minute Hour Day Month Weekday Command`

   **Example Entry:**

   ```cron
   0 3 * * * cd /path/to/vossie && /path/to/venv/bin/python manage.py sync_contacts >> /path/to/vossie/logs/cron_sync.log 2>&1
   ```

   **Replace paths with your actual paths:**
   - `/path/to/vossie`: Your project root directory.
   - `/path/to/venv/bin/python`: Your virtual environment python executable.
   - `/path/to/vossie/logs/cron_sync.log`: Path to a log file (ensure the directory exists).

3. **Save and Exit**
   - If using `nano` (default), press `Ctrl+O` to save, `Enter` to confirm, then `Ctrl+X` to exit.
   - You should see the message: `crontab: installing new crontab`.

## Verify the Job

1. **List Cron Jobs**
   Verify the job was saved correctly:

   ```bash
   crontab -l
   ```

2. **Test Manually**
   Run the exact command you added to crontab in your terminal to ensure permissions and paths are correct:

   ```bash
   cd /path/to/vossie && /path/to/venv/bin/python manage.py sync_contacts
   ```

## Troubleshooting

- **Permissions**: Ensure the user running the cron job has write access to the database (if SQLite) or network access to the Fabric DB.
- **Environment Variables**: Cron jobs run with a minimal environment. If your project relies on specific environment variables (like those in `.env`), ensuring `cd /path/to/vossie` works helps if you are using `python-dotenv`.
  - Alternatively, you can source the environment variables in the cron command:

    ```cron
    0 3 * * * export $(cat /path/to/vossie/.env | xargs) && cd /path/to/vossie && ...
    ```
