import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain


def test_move_funds_to_042(
    yvweth_032, yvweth_042, unique_strategy, gov, weth, weth_whale
):

    strategy = unique_strategy
    print(strategy.name())

    strategy.harvest({"from": gov})
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    # Send profit to 042
    prev_value = strategy.valueOfInvestment()
    weth.transfer(yvweth_042, Wei("10 ether"), {"from": weth_whale})
    assert strategy.valueOfInvestment() > prev_value

    strategy.harvest({"from": gov})
    chain.sleep(3600 * 11)
    chain.mine(1)

    total_gain = yvweth_032.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert yvweth_032.strategies(strategy).dict()["totalLoss"] == 0

    yvweth_032.revokeStrategy(strategy, {"from": gov})
    tx = strategy.harvest({"from": gov})
    total_gain += tx.events["Harvested"]["profit"]
    chain.sleep(3600 * 8)
    chain.mine(1)

    assert yvweth_032.strategies(strategy).dict()["totalGain"] == total_gain
    assert yvweth_032.strategies(strategy).dict()["totalLoss"] == 0
    assert yvweth_032.strategies(strategy).dict()["totalDebt"] == 0
