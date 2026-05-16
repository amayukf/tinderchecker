import httpx
import sys

def set_webhook(bot_token: str, vercel_domain: str):
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    webhook_url = f"https://{vercel_domain}/api/webhook"
    
    print(f"Setting webhook to: {webhook_url}")
    response = httpx.post(url, json={"url": webhook_url})
    
    if response.status_code == 200:
        print("✅ Webhook set successfully!")
        print(response.json())
    else:
        print("❌ Failed to set webhook:")
        print(response.text)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python set_webhook.py <YOUR_BOT_TOKEN> <YOUR_VERCEL_DOMAIN>")
        print("Example: python set_webhook.py 1234:ABCD my-tinder-bot.vercel.app")
        sys.exit(1)
        
    set_webhook(sys.argv[1], sys.argv[2])
