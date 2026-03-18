import json
import os
from dataclasses import asdict
from usage_parser import AccountUsage, UsageData, UsageSection

STORAGE_FILE = "accounts_usage.json"

def _account_usage_to_dict(account: AccountUsage) -> dict:
    return asdict(account)

def _dict_to_account_usage(data: dict) -> AccountUsage:
    # Reconstruct UsageData and UsageSection objects
    usage_dict = data.get("usage", {})
    sections = []
    for sec_data in usage_dict.get("sections", []):
        sections.append(UsageSection(**sec_data))
    
    usage_data = UsageData(
        sections=sections,
        raw_text=usage_dict.get("raw_text", ""),
        error=usage_dict.get("error")
    )
    
    return AccountUsage(
        email=data.get("email", "Unknown"),
        usage=usage_data,
        last_updated=data.get("last_updated", ""),
        is_active=data.get("is_active", False)
    )

def load_all_accounts() -> dict[str, AccountUsage]:
    if not os.path.exists(STORAGE_FILE):
        return {}
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            return {k: _dict_to_account_usage(v) for k, v in raw_data.items()}
    except Exception as e:
        print(f"Error loading accounts: {e}")
        return {}

def save_account(account: AccountUsage):
    accounts = load_all_accounts()
    accounts[account.email] = account
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: _account_usage_to_dict(v) for k, v in accounts.items()}, f, indent=2)
    except Exception as e:
        print(f"Error saving account: {e}")
