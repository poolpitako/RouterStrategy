import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain


def test_dai_profit_emergency(yvdai_030, yvdai_042, dai_strategy, gov, dai, dai_whale):

    strategy = dai_strategy
    # Move only gen lender funds to the new strat
    strat = Contract(yvdai_030.withdrawalQueue(0))
    strat.harvest({"from": gov})
    print(f"dai balance in vault {dai.balanceOf(yvdai_030)/1e18}")

    strategy.harvest({"from": gov})
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    # Send profit to 042
    prev_value = strategy.valueOfInvestment()
    dai.transfer(yvdai_042, Wei("100_000 ether"), {"from": dai_whale})
    assert strategy.valueOfInvestment() > prev_value

    strategy.setEmergencyExit({"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(3600 * 8)
    chain.mine(1)

    total_gain = yvdai_030.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert yvdai_030.strategies(strategy).dict()["totalLoss"] == 0
    assert strategy.balanceOfWant() < Wei("1 ether")
    assert strategy.valueOfInvestment() < Wei("1 ether")
