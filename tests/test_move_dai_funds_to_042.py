import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain


def test_move_dai_funds_to_042(yvdai_030, yvdai_042, dai_strategy, gov, dai, dai_whale):
    # hack :)
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
    dai.transfer(yvdai_042, Wei("1000 ether"), {"from": dai_whale})
    assert strategy.valueOfInvestment() > prev_value

    strategy.harvest({"from": gov})

    total_gain = yvdai_030.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert yvdai_030.strategies(strategy).dict()["totalLoss"] == 0

    yvdai_030.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    assert yvdai_030.strategies(strategy).dict()["totalGain"] - total_gain < Wei(
        "1 ether"
    )
    assert yvdai_030.strategies(strategy).dict()["totalLoss"] == 0
    assert yvdai_030.strategies(strategy).dict()["totalDebt"] == 0
