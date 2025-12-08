---
description: How to schedule the contact sync to run daily on Windows
---

# Schedule Daily Contact Sync

Follow these steps to configure Windows Task Scheduler to run the `sync_contacts` command automatically every day.

## Prerequisites

- **Python Path**: Ensure you know the path to your Python executable.
  - Detected: `C:\Python312\python.exe`
- **Project Path**: `c:\Users\riaan\source\repos\Vossie`

## Step-by-Step Guide

1. **Open Task Scheduler**
   - Press `Win + R`, type `taskschd.msc`, and press Enter.

2. **Create Basic Task**
   - In the **Actions** pane (right side), click **Create Basic Task...**.

3. **Name and Description**
   - **Name**: `Vossie Contact Sync`
   - **Description**: `Runs python manage.py sync_contacts daily to update local contact table.`
   - Click **Next**.

4. **Trigger**
   - Select **Daily**.
   - Click **Next**.
   - Set the **Start** time (e.g., `03:00:00` AM) when server load is low.
   - Click **Next**.

5. **Action**
   - Select **Start a program**.
   - Click **Next**.

6. **Start a Program Configuration**
   - **Program/script**: `C:\Python312\python.exe`
     *(Or your specific virtualenv python path if different)*
   - **Add arguments**: `manage.py sync_contacts`
   - **Start in**: `c:\Users\riaan\source\repos\Vossie`
   - Click **Next**.

7. **Finish**
   - Review the summary.
   - Click **Finish**.

## Verify the Task

1. Find `Vossie Contact Sync` in the list (click "Task Scheduler Library" on the left if you don't see it).
2. Right-click the task and select **Run**.
3. It should open a terminal window briefly (or run in background) and execute the sync.
4. Check the `Contact` table or logs to confirm it ran.

## Troubleshooting

- **Permissions**: If the task fails, right-click the task > **Properties** > **General** and select **Run with highest privileges**.
- **Hidden Window**: To run it completely silently, you can select **Run whether user is logged on or not** in Properties (requires saving credentials).
