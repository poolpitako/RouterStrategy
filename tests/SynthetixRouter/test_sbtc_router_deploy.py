import pytest
from brownie import chain, Contract, accounts, ZERO_ADDRESS
from eth_abi import encode_single

DUST_THRESHOLD = 10_000


def test_sbtc_router_deploy(SynthetixRouterStrategy, strategist, sbtc, sbtc_whale):

    hedging_vault = Contract("0xcE0F1Ef5aAAB82547acc699d3Ab93c069bb6e547")
    sbtc_vault = Contract("0x8472E9914C0813C4b465927f82E213EA34839173")
    gov = accounts.at(hedging_vault.governance(), True)

    strategy = strategist.deploy(
        SynthetixRouterStrategy,
        hedging_vault,
        sbtc_vault,
        encode_single("bytes32", b"ProxysBTC"),
        "RoutersUSDtosBTC",
    )

    susd_router = Contract(hedging_vault.withdrawalQueue(0))
    hedging_vault.updateStrategyDebtRatio(susd_router, 8_000, {"from": gov})

    susd_router.setMaxLoss(10_000, {"from": gov})
    susd_router.harvest({"from": gov})
    hedging_vault.addStrategy(strategy, 2_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    strategy.harvest({"from": gov})

    assert strategy.balanceOfWant() == 0
    assert sbtc.balanceOf(strategy) > 0

    # deposit sbtc into new strategy
    chain.sleep(3600 * 11)
    chain.mine(1)
    strategy.depositInVault({"from": gov})

    assert strategy.valueOfInvestment() > 0
    assert strategy.balanceOfWant() == 0
    assert sbtc.balanceOf(strategy) == 0


    sbtc.transfer(sbtc_vault, int(sbtc_vault.totalAssets()*.05), {"from": sbtc_whale})
    strategy.manualRemoveFullLiquidity({"from": gov})
    chain.sleep(360 + 1)
    chain.mine(1)
    strategy.harvest({"from": gov})

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
    chain.sleep(360 + 1)
    chain.mine(1)

    assert hedging_vault.strategies(strategy).dict()["totalDebt"] == 0
