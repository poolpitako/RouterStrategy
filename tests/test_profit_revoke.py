import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain


def test_profit_revoke(yvweth_032, yvweth_042, unique_strategy, gov, weth, weth_whale):

    strategy = unique_strategy
    strategy.harvest({"from": gov})
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    # Send profit to 042
    prev_value = strategy.valueOfInvestment()
    weth.transfer(yvweth_042, Wei("10 ether"), {"from": weth_whale})
    assert strategy.valueOfInvestment() > prev_value

    yvweth_032.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})
    chain.sleep(3600 * 8)
    chain.mine(1)

    total_gain = yvweth_032.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert yvweth_032.strategies(strategy).dict()["totalLoss"] == 0
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() < Wei("0.001 ether")  # there might be dust
