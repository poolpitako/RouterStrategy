import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain


def test_yvault_shares_conversion(unique_strategy, gov, weth, weth_whale, RELATIVE_APPROX):

    strategy = unique_strategy
    strategy.harvest({"from": gov})
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    strategy.setMaxLoss(0, {"from": gov})
    strategy.withdrawFromYVault(10 * 1e18, {"from": gov})

    assert strategy.balanceOfWant() == 10 * (10 ** 18)
    assert pytest.approx(strategy.balanceOfWant(), rel=RELATIVE_APPROX) == 10 * (10 ** 18)
