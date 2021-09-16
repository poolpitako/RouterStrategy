import pytest
from brownie import chain, Contract, accounts, ZERO_ADDRESS, Wei
from eth_abi import encode_single

DUST_THRESHOLD = 10_000


def test_sbtc_router_deploy_with_profit(
    SynthetixRouterStrategy, strategist, sbtc, sbtc_whale
):

    hedging_vault = Contract("0xcE0F1Ef5aAAB82547acc699d3Ab93c069bb6e547")
    sbtc_vault = Contract("0x8472E9914C0813C4b465927f82E213EA34839173")
    gov = accounts.at(hedging_vault.governance(), True)

    strategy = strategist.deploy(
        SynthetixRouterStrategy,
        hedging_vault,
        sbtc_vault,
        "RoutersUSDtosBTC",
        encode_single("bytes32", b"ProxysBTC"),
        100,
    )

    susd_router = Contract(hedging_vault.withdrawalQueue(0))
    hedging_vault.updateStrategyDebtRatio(susd_router, 8_000, {"from": gov})

    susd_router.setMaxLoss(10_000, {"from": gov})
    susd_router.harvest({"from": gov})
    hedging_vault.addStrategy(strategy, 2_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    tx = strategy.harvest({"from": gov})
    print(f"First harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    # There needs to be a buffer
    assert strategy.balanceOfWant() > 0

    # Even though we can't move the funds, sbtc should be already in the strategy
    assert sbtc.balanceOf(strategy) > 0

    # Buffer should be 1% of debt aprox
    total_debt = hedging_vault.strategies(strategy).dict()["totalDebt"] / 1e18
    assert total_debt * 0.009 < strategy.balanceOfWant() / 1e18
    assert total_debt * 0.02 > strategy.balanceOfWant() / 1e18
    balance_of_want_before = strategy.balanceOfWant()
    # deposit sbtc into new strategy
    chain.sleep(3600 * 11)
    chain.mine(1)
    strategy.depositInVault({"from": gov})

    assert strategy.valueOfInvestment() > 0
    assert strategy.balanceOfWant() == balance_of_want_before
    assert sbtc.balanceOf(strategy) == 0

    sbtc.transfer(
        sbtc_vault, int(sbtc_vault.totalAssets() * 0.05), {"from": sbtc_whale}
    )
    capital_to_withdraw = (
        strategy.estimatedTotalAssets()
        - hedging_vault.strategies(strategy).dict()["totalDebt"]
    )

    # Should this touch the buffer or not?
    strategy.manualRemoveLiquidity(capital_to_withdraw, {"from": gov})

    # Check that we withdrew enough sUSD
    assert abs(strategy.balanceOfWant() - capital_to_withdraw) < Wei("1 ether")
    assert sbtc.balanceOf(strategy) == 0

    chain.sleep(360 + 1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print(f"Second harvest {tx.events['Harvested']}")

    assert tx.events["Harvested"]["loss"] == 0
    assert hedging_vault.strategies(strategy).dict()["totalLoss"] == 0

    hedging_vault.revokeStrategy(strategy, {"from": gov})
    chain.sleep(360 + 1)
    chain.mine(1)

    strategy.manualRemoveFullLiquidity({"from": gov})

    assert strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(strategy) < DUST_THRESHOLD

    chain.sleep(360 + 1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print(f"Third harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    chain.sleep(360 + 1)
    chain.mine(1)

    assert hedging_vault.strategies(strategy).dict()["totalDebt"] == 0


def test_sbtc_router_deploy_with_loss(
    SynthetixRouterStrategy, strategist, sbtc, sbtc_whale, susd, susd_whale
):

    hedging_vault = Contract("0xcE0F1Ef5aAAB82547acc699d3Ab93c069bb6e547")
    sbtc_vault = Contract("0x8472E9914C0813C4b465927f82E213EA34839173")
    gov = accounts.at(hedging_vault.governance(), True)

    strategy = strategist.deploy(
        SynthetixRouterStrategy,
        hedging_vault,
        sbtc_vault,
        "RoutersUSDtosBTC",
        encode_single("bytes32", b"ProxysBTC"),
        100,
    )

    susd.approve(hedging_vault, 2 ** 256 - 1, {"from": susd_whale})
    susd_router = Contract(hedging_vault.withdrawalQueue(0))
    hedging_vault.updateStrategyDebtRatio(susd_router, 8_000, {"from": gov})

    susd_router.setMaxLoss(10_000, {"from": gov})
    susd_router.harvest({"from": gov})
    hedging_vault.addStrategy(strategy, 2_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    susd.transfer(hedging_vault, susd.balanceOf(susd_whale), {"from": susd_whale})

    tx = strategy.harvest({"from": gov})
    print(f"First harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    # There needs to be a buffer
    assert strategy.balanceOfWant() > 0

    # Even though we can't move the funds, sbtc should be already in the strategy
    assert sbtc.balanceOf(strategy) > 0

    # Buffer should be 1% of debt aprox
    total_debt = hedging_vault.strategies(strategy).dict()["totalDebt"] / 1e18
    assert total_debt * 0.009 < strategy.balanceOfWant() / 1e18
    assert total_debt * 0.02 > strategy.balanceOfWant() / 1e18
    balance_of_want_before = strategy.balanceOfWant()
    # deposit sbtc into new strategy
    chain.sleep(3600 * 11)
    chain.mine(1)
    strategy.depositInVault({"from": gov})

    assert strategy.valueOfInvestment() > 0
    assert strategy.balanceOfWant() == balance_of_want_before
    assert sbtc.balanceOf(strategy) == 0

    # Should this touch the buffer or not?
    strategy.manualRemoveLiquidity(strategy.estimatedTotalAssets(), {"from": gov})

    # Check that we withdrew enough sUSD
    assert sbtc.balanceOf(strategy) == 0

    chain.sleep(360 + 1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print(f"Second harvest {tx.events['Harvested']}")

    # loss due to the exchange fees
    assert (
        tx.events["Harvested"]["loss"]
        > strategy.estimatedTotalAssets() * 0.25 / 100 * 2
    )
    assert (
        tx.events["Harvested"]["loss"]
        <= strategy.estimatedTotalAssets() * 0.32 / 100 * 2
    )
    assert (
        hedging_vault.strategies(strategy).dict()["totalLoss"]
        > strategy.estimatedTotalAssets() * 0.25 / 100 * 2
    )
    assert (
        hedging_vault.strategies(strategy).dict()["totalLoss"]
        <= strategy.estimatedTotalAssets() * 0.32 / 100 * 2
    )

    hedging_vault.revokeStrategy(strategy, {"from": gov})
    chain.sleep(360 + 1)
    chain.mine(1)

    strategy.manualRemoveFullLiquidity({"from": gov})

    assert strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(strategy) < DUST_THRESHOLD

    chain.sleep(360 + 1)
    chain.mine(1)
    tx = strategy.harvest({"from": gov})
    print(f"Third harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] > 0

    chain.sleep(360 + 1)
    chain.mine(1)

    assert hedging_vault.strategies(strategy).dict()["totalDebt"] < Wei("1 ether")
