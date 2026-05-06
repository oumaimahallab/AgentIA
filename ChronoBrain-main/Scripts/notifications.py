# scripts/notifications.py
import requests
import json
import os

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")

def send_summary_notification(results):
    """Sends a single summary report to Teams"""
    success_list = [res for res in results if "✅" in res]
    error_list = [res for res in results if "❌" in res]

    summary_text = f"🏁 **ChronoBrain Pipeline Report**\n\n"
    summary_text += f"**Total processed:** {len(results)}\n"
    summary_text += f"**Success:** {len(success_list)} ✅\n"
    summary_text += f"**Errors:** {len(error_list)} ❌\n\n"

    if error_list:
        summary_text += "⚠️ **Details on Errors:**\n"
        for err in error_list:
            summary_text += f"- {err}\n"
    else:
        summary_text += "🌟 All videos transcribed successfully!"

    payload = {"text": summary_text}
    
    try:
        requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send summary: {e}")