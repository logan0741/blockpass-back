import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/contracts", tags=["contracts"])

UNIT_SECONDS = {
    "일": 24 * 60 * 60,
    "시간": 60 * 60,
    "분": 60,
}


class RefundRule(BaseModel):
    period: int = Field(..., gt=0)
    unit: str
    refund_percent: int = Field(..., ge=0, le=100)


class RefundPolicyPayload(BaseModel):
    pass_name: str
    price_eth: str | None = None
    duration_value: int = Field(..., gt=0)
    duration_unit: str
    refund_rules: list[RefundRule]
    terms: str | None = None


def _sanitize_contract_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", " ", name).title().replace(" ", "")
    if not base:
        return "TrustGymPolicy"
    if base[0].isdigit():
        return f"TrustGym{base}"
    return base


def _eth_to_wei(value: str) -> int:
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="Invalid ETH amount") from exc
    if decimal_value <= 0:
        raise HTTPException(status_code=400, detail="ETH amount must be positive")
    wei = int((decimal_value * Decimal(10**18)).to_integral_value())
    return wei


def _build_solidity(payload: RefundPolicyPayload) -> str:
    if payload.duration_unit not in UNIT_SECONDS:
        raise HTTPException(status_code=400, detail="Invalid duration unit")

    if not payload.refund_rules:
        raise HTTPException(status_code=400, detail="Refund rules required")

    duration_seconds = payload.duration_value * UNIT_SECONDS[payload.duration_unit]
    contract_name = _sanitize_contract_name(payload.pass_name)
    price_wei = _eth_to_wei(payload.price_eth or "0.01")

    thresholds = []
    for rule in payload.refund_rules:
        if rule.unit not in UNIT_SECONDS:
            raise HTTPException(status_code=400, detail="Invalid refund rule unit")
        thresholds.append(
            (
                rule.period * UNIT_SECONDS[rule.unit],
                rule.refund_percent,
            )
        )

    thresholds.sort(key=lambda item: item[0])
    threshold_values = ", ".join(str(item[0]) for item in thresholds)
    refund_values = ", ".join(str(item[1]) for item in thresholds)

    return f'''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

contract {contract_name} is ERC721 {{
    using Counters for Counters.Counter;
    Counters.Counter private _tokenIds;

    address public owner;
    uint256 public subscriptionPrice = {price_wei};
    uint256 public duration = {duration_seconds};

    uint256[] public refundThresholds = [{threshold_values}];
    uint256[] public refundPercents = [{refund_values}];

    struct Subscription {{
        uint256 startTimestamp;
        uint256 pricePaid;
    }}

    mapping(uint256 => Subscription) public subscriptions;
    uint256 public gymStatus = 0;

    mapping(uint256 => bool) public hasVoted;
    uint256 public panicVotes;
    uint256 public activeMembers;

    constructor() ERC721("{payload.pass_name}", "BPASS") {{
        owner = msg.sender;
    }}

    function register() public payable {{
        require(msg.value == subscriptionPrice, "Send exact ETH amount");
        require(gymStatus == 0, "Gym is closed");

        _tokenIds.increment();
        uint256 newItemId = _tokenIds.current();

        _mint(msg.sender, newItemId);

        subscriptions[newItemId] = Subscription({{
            startTimestamp: block.timestamp,
            pricePaid: msg.value
        }});

        activeMembers++;
    }}

    function _calculateRefund(uint256 tokenId) internal view returns (uint256) {{
        Subscription memory sub = subscriptions[tokenId];
        uint256 elapsedTime = block.timestamp - sub.startTimestamp;

        for (uint256 i = 0; i < refundThresholds.length; i++) {{
            if (elapsedTime <= refundThresholds[i]) {{
                return (sub.pricePaid * refundPercents[i]) / 100;
            }}
        }}

        return 0;
    }}

    function quit(uint256 tokenId) public {{
        require(ownerOf(tokenId) == msg.sender, "Not your ticket");
        require(gymStatus == 0, "Gym is bankrupt. Use emergencyWithdraw");

        uint256 refundAmount = _calculateRefund(tokenId);

        delete subscriptions[tokenId];
        _burn(tokenId);
        activeMembers--;

        if (refundAmount > 0) {{
            (bool success, ) = msg.sender.call{{value: refundAmount}}("");
            require(success, "Transfer failed");
        }}
    }}

    function votePanic(uint256 tokenId) public {{
        require(ownerOf(tokenId) == msg.sender, "Not your ticket");
        require(!hasVoted[tokenId], "Already voted");
        require(gymStatus == 0, "Already status 1");

        hasVoted[tokenId] = true;
        panicVotes++;

        if (panicVotes * 2 > activeMembers) {{
            gymStatus = 1;
        }}
    }}

    function emergencyWithdraw(uint256 tokenId) public {{
        require(gymStatus == 1, "Gym is not bankrupt yet");
        require(ownerOf(tokenId) == msg.sender, "Not your ticket");

        uint256 refundAmount = _calculateRefund(tokenId);

        if (address(this).balance < refundAmount) {{
            refundAmount = address(this).balance;
        }}

        delete subscriptions[tokenId];
        _burn(tokenId);
        if (activeMembers > 0) activeMembers--;

        if (refundAmount > 0) {{
            (bool success, ) = msg.sender.call{{value: refundAmount}}("");
            require(success, "Transfer failed");
        }}
    }}

    function ownerWithdraw(uint256 amount) public {{
        require(msg.sender == owner, "Only owner");
        require(gymStatus == 0, "Bankrupt! Funds locked.");
        require(address(this).balance >= amount, "Not enough funds");

        (bool success, ) = owner.call{{value: amount}}("");
        require(success, "Transfer failed");
    }}

    function checkRefundStatus(uint256 tokenId) public view returns (string memory status, uint256 amount) {{
        uint256 calcAmount = _calculateRefund(tokenId);

        if (gymStatus == 1) {{
            return ("Bankrupt Mode (Status 1)", calcAmount);
        }} else {{
            return ("Normal Mode (Status 0)", calcAmount);
        }}
    }}
}}
'''


@router.post("/solidity")
def generate_solidity(payload: RefundPolicyPayload) -> dict:
    return {"solidity": _build_solidity(payload)}
