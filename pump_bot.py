import asyncio
import websockets
import requests
import json
import logging
import base58
import ssl
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.transaction import Transaction
from solana.system_program import transfer
from solana.publickey import PublicKey
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants
API_KEY = os.getenv("API_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")  # Base58-encoded private key
TESTNET_RPC = "https://api.mainnet-beta.solana.com"
BASE_URL = "https://pumpportal.fun/api/trade"  # Mainnet API endpoint
WEBSOCKET_URI = "wss://pumpportal.fun/api/data"  # Mainnet WebSocket endpoint
MAX_SPENT_USD = 10
SOL_PRICE_USD = 25  # Example SOL price
SPENDING_LIMIT_SOL = MAX_SPENT_USD / SOL_PRICE_USD
MIN_TRADE_AMOUNT = 0.01
MAX_TRADE_AMOUNT = 0.01

# Function to decode the private key from Base58
def get_private_key():
    try:
        # Decode the private key from Base58 to bytes
        return base58.b58decode(WALLET_PRIVATE_KEY)
    except Exception as e:
        logging.error("Failed to decode the private key. Ensure it's Base58 encoded.")
        raise e

# Solana client for mainnet
solana_client = Client(TESTNET_RPC)

# Subscribe and trade logic
async def subscribe_and_trade(target_account):
    total_spent_sol = 0

    # Disable SSL verification for WebSocket connection
    ssl_context = ssl._create_unverified_context()

    while total_spent_sol < SPENDING_LIMIT_SOL:
        try:
            async with websockets.connect(WEBSOCKET_URI, ssl=ssl_context) as websocket:
                # Subscribe to trades from the target account
                payload = {
                    "method": "subscribeAccountTrade",
                    "keys": [target_account]
                }
                await websocket.send(json.dumps(payload))
                logging.info(f"Subscribed to trades for account: {target_account}")

                async for message in websocket:
                    trade_data = json.loads(message)
                    logging.info(f"Received trade data: {trade_data}")

                    # Check if the message contains trade details
                    if 'solAmount' not in trade_data or 'txType' not in trade_data:
                        logging.warning("Received non-trade data or incomplete trade data. Skipping.")
                        continue

                    # Extract trade details
                    token_mint = trade_data.get("mint")
                    action = trade_data.get("txType")  # buy or sell
                    amount = float(trade_data.get("solAmount"))  # Amount in SOL

                    # Ensure trade is within constraints
                    if MIN_TRADE_AMOUNT <= amount <= MAX_TRADE_AMOUNT:
                        if total_spent_sol + amount > SPENDING_LIMIT_SOL:
                            logging.info("Spending limit reached. Stopping bot.")
                            return

                        # Log trade initiation
                        logging.info(f"Initiating trade: Action={action}, Mint={token_mint}, Amount={amount} SOL")

                        # Execute the trade
                        execute_trade(action, token_mint, amount)

                        # Update total spent
                        total_spent_sol += amount

                        # Log trade completion
                        logging.info(f"Trade completed. Total spent: {total_spent_sol} SOL")
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            await asyncio.sleep(5)


def execute_trade(action, token_mint, amount):
    try:
        private_key = get_private_key()  # Fetch the private key directly from .env
        keypair = Keypair.from_secret_key(private_key)
        payload = {
            "action": action,
            "mint": token_mint,
            "amount": amount,
            "denominatedInSol": "true",
            "slippage": 1,
            "priorityFee": 0.005,
            "pool": "pump"
        }
        headers = {"Content-Type": "application/json"}

        # Send the trade request
        logging.info(f"Sending trade request: {payload}")
        response = requests.post(f"{BASE_URL}?api-key={API_KEY}", json=payload, headers=headers)
        response_data = response.json()

        if response.status_code == 200:
            logging.info(f"Trade successful: {response_data}")
        else:
            logging.error(f"Trade failed: {response_data}")
    except Exception as e:
        logging.error(f"Error executing trade: {e}")

# Main function
if __name__ == "__main__":
    # Decode private wallet key and initialize Keypair
    private_wallet_keypair = Keypair.from_secret_key(get_private_key())

    # Run the trading bot
    target_account = "DyRxGT7xgYn6ZGN9hmtUBAQ1FQWEGyaXQ7ZVkdH2yiQt"  # Replace with the account to monitor
    asyncio.run(subscribe_and_trade(target_account))
