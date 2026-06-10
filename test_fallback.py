import asyncio
from app.tinder_client import TinderClient

async def main():
    client = TinderClient()
    # Test with a known profile (replace with a real one if you have it)
    username = "john"
    print(f"Testing username: {username}")
    result = await client.get_profile_data(username)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
