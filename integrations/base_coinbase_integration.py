"""
Garcar Enterprise — Base (Coinbase) Integration
On-chain revenue settlement via Coinbase Developer Platform (CDP) SDK + AgentKit.
Chain: Base Mainnet (Chain ID 8453)
"""
import os
from cdp import CdpClient
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

# USDC contract on Base Mainnet
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_CHAIN_ID = "base-mainnet"

class GarcarBaseIntegration:
    def __init__(self):
        self.cdp = CdpClient(
            api_key_id=os.environ["COINBASE_CDP_API_KEY"],
            api_key_secret=os.environ["COINBASE_CDP_API_SECRET"]
        )
        self.wallet_address = os.environ["GARCAR_WALLET_ADDRESS"]

    async def get_usdc_balance(self) -> float:
        """Returns USDC balance on Base for the Garcar treasury wallet."""
        account = await self.cdp.evm.get_account(self.wallet_address)
        balances = await account.list_balances()
        for b in balances:
            if b.asset.contract_address == USDC_BASE:
                return float(b.amount)
        return 0.0

    async def send_usdc(self, to_address: str, amount_usdc: float, memo: str = "") -> str:
        """Send USDC on Base — used for autonomous revenue distribution."""
        account = await self.cdp.evm.get_account(self.wallet_address)
        tx = await account.send_transaction(
            network=BASE_CHAIN_ID,
            to=to_address,
            value=0,
            data=self._encode_usdc_transfer(to_address, int(amount_usdc * 1_000_000))
        )
        await bus.emit("base.usdc_sent", {
            "to": to_address,
            "amount": amount_usdc,
            "tx_hash": tx.transaction_hash,
            "memo": memo
        }, agents=["RevenueOpsAgent"])
        return tx.transaction_hash

    async def settle_stripe_payment(self, stripe_event: dict) -> dict:
        """Bridge: Stripe payment confirmation → Base USDC settlement record."""
        amount = stripe_event["amount"] / 100  # cents → dollars
        tx_hash = await self.send_usdc(
            to_address=self.wallet_address,  # Self-custody: record in treasury
            amount_usdc=amount,
            memo=f"stripe:{stripe_event['payment_intent']}"
        )
        return {"settled": True, "tx_hash": tx_hash, "amount_usdc": amount}

    def _encode_usdc_transfer(self, to: str, amount_micro: int) -> str:
        # ERC-20 transfer(address,uint256) selector = 0xa9059cbb
        padded_to = to[2:].zfill(64)
        padded_amount = hex(amount_micro)[2:].zfill(64)
        return f"0xa9059cbb{padded_to}{padded_amount}"

base = GarcarBaseIntegration()
