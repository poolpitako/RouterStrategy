import pytest
from brownie import chain, Contract, accounts, ZERO_ADDRESS, Wei, reverts
from eth_abi import encode_single

DUST_THRESHOLD = 100_000


def test_deposit_and_withdraw_wo_profit(susd_whale):
    old_router_strat = Contract("0x4a4A5549F4B2eF519ca9abA38f4e2d13c23e32B7")
    sbtc_router = Contract("0x86fd69EDDcc0d185fC2678aA02Aeae67f614b76e")
    hedging_vault = Contract(sbtc_router.vault())
    sbtc_vault = Contract(sbtc_router.yVault())

    susd = Contract(sbtc_router.want())
    sbtc = Contract(sbtc_vault.token())
    gov = accounts.at(hedging_vault.governance(), True)

    hedging_vault.migrateStrategy(old_router_strat, sbtc_router, {"from": gov})

    susd.approve(hedging_vault, 2 ** 256 - 1, {"from": susd_whale})

    prev_assets = sbtc_router.estimatedTotalAssets()
    susd_to_deposit = (
        30_000 * 1e18
        if susd.balanceOf(susd_whale) > 30_000 * 1e18
        else susd.balanceOf(susd_whale)
    )

    assert susd_to_deposit > 0

    hedging_vault.deposit(susd_to_deposit, {"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"First harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    new_assets = sbtc_router.estimatedTotalAssets()

    assert new_assets < (susd_to_deposit + prev_assets)
    assert new_assets > (susd_to_deposit + prev_assets) * 0.9

    chain.sleep(3600 + 1)
    chain.mine(1)

    prev_sbtc_balance = sbtc_vault.totalAssets()
    sbtc_router.depositInVault({"from": gov})
    after_sbtc_balance = sbtc_vault.totalAssets()

    assert after_sbtc_balance > prev_sbtc_balance

    chain.sleep(3600 + 1)
    chain.mine(1)

    with reverts():
        hedging_vault.withdraw(susd_to_deposit, {"from": susd_whale})

    chain.sleep(3600 + 1)
    chain.mine(1)
    sbtc_router.setMaxLoss(100, {"from": gov})
    sbtc_router.manualRemoveLiquidity(
        hedging_vault.balanceOf(susd_whale) * hedging_vault.pricePerShare() / 1e18,
        {"from": gov},
    )

    chain.sleep(3600 + 1)
    chain.mine(1)

    prev_hedge_assets = hedging_vault.totalAssets()
    hedging_vault.withdraw(
        hedging_vault.balanceOf(susd_whale), susd_whale, 100, {"from": susd_whale}
    )
    after_hedge_assets = hedging_vault.totalAssets()

    assert prev_hedge_assets > after_hedge_assets


def test_deposit_and_withdraw_w_profit(susd_whale, sbtc_whale):
    old_router_strat = Contract("0x4a4A5549F4B2eF519ca9abA38f4e2d13c23e32B7")
    sbtc_router = Contract("0x86fd69EDDcc0d185fC2678aA02Aeae67f614b76e")
    hedging_vault = Contract(sbtc_router.vault())
    sbtc_vault = Contract(sbtc_router.yVault())

    susd = Contract(sbtc_router.want())
    sbtc = Contract(sbtc_vault.token())
    gov = accounts.at(hedging_vault.governance(), True)

    hedging_vault.migrateStrategy(old_router_strat, sbtc_router, {"from": gov})

    susd.approve(hedging_vault, 2 ** 256 - 1, {"from": susd_whale})

    prev_assets = sbtc_router.estimatedTotalAssets()
    susd_to_deposit = (
        30_000 * 1e18
        if susd.balanceOf(susd_whale) > 30_000 * 1e18
        else susd.balanceOf(susd_whale)
    )

    assert susd_to_deposit > 0

    hedging_vault.deposit(susd_to_deposit, {"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"First harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    new_assets = sbtc_router.estimatedTotalAssets()

    assert new_assets < (susd_to_deposit + prev_assets)
    assert new_assets > (susd_to_deposit + prev_assets) * 0.9

    chain.sleep(3600 + 1)
    chain.mine(1)

    prev_sbtc_balance = sbtc_vault.totalAssets()
    sbtc_router.depositInVault({"from": gov})
    after_sbtc_balance = sbtc_vault.totalAssets()

    assert after_sbtc_balance > prev_sbtc_balance

    chain.sleep(3600 + 1)
    chain.mine(1)

    # produce profit
    sbtc.transfer(sbtc_vault, sbtc.balanceOf(sbtc_whale), {"from": sbtc_whale})

    chain.sleep(3600 + 1)
    chain.mine(1)
    sbtc_router.manualRemoveLiquidity(
        hedging_vault.balanceOf(susd_whale) * hedging_vault.pricePerShare() / 1e18,
        {"from": gov},
    )

    chain.sleep(3600 + 1)
    chain.mine(1)

    prev_hedge_assets = hedging_vault.totalAssets()
    hedging_vault.withdraw({"from": susd_whale})
    after_hedge_assets = hedging_vault.totalAssets()

    assert prev_hedge_assets > after_hedge_assets


def test_deposit_harvest_and_revert_withdraw(susd_whale, sbtc_whale):
    old_router_strat = Contract("0x4a4A5549F4B2eF519ca9abA38f4e2d13c23e32B7")
    sbtc_router = Contract("0x86fd69EDDcc0d185fC2678aA02Aeae67f614b76e")
    hedging_vault = Contract(sbtc_router.vault())
    sbtc_vault = Contract(sbtc_router.yVault())

    susd = Contract(sbtc_router.want())
    sbtc = Contract(sbtc_vault.token())
    gov = accounts.at(hedging_vault.governance(), True)

    hedging_vault.migrateStrategy(old_router_strat, sbtc_router, {"from": gov})

    susd.approve(hedging_vault, 2 ** 256 - 1, {"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    sbtc_router.setMaxLoss(100, {"from": gov})
    sbtc_router.manualRemoveLiquidity(
        abs(
            sbtc_router.estimatedTotalAssets()
            - hedging_vault.strategies(sbtc_router)["totalDebt"]
        ),
        {"from": gov},
    )

    chain.sleep(3600 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"Zero harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] == 0

    chain.sleep(360 + 1)
    chain.mine(1)

    prev_assets = sbtc_router.estimatedTotalAssets()

    susd_to_deposit = (
        30_000 * 1e18
        if susd.balanceOf(susd_whale) > 30_000 * 1e18
        else susd.balanceOf(susd_whale)
    )

    assert susd_to_deposit > 0

    hedging_vault.deposit(susd_to_deposit, {"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"First harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["profit"] == 0

    new_assets = sbtc_router.estimatedTotalAssets()

    assert new_assets > (susd_to_deposit * 0.95 + prev_assets)

    chain.sleep(3600 + 1)
    chain.mine(1)

    prev_sbtc_balance = sbtc_vault.totalAssets()
    sbtc_router.depositInVault({"from": gov})
    after_sbtc_balance = sbtc_vault.totalAssets()

    assert after_sbtc_balance > prev_sbtc_balance

    chain.sleep(3600 + 1)
    chain.mine(1)
    # converts from sbtc to susd
    sbtc_router.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(3600 + 1)
    chain.mine(1)

    # converts from susd to sbtc
    tx = sbtc_router.harvest({"from": gov})

    print(f"Second harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] > 0

    prev_hedge_assets = hedging_vault.totalAssets()
    # money has just been exchange for synth so we need to wait 6 min to withdraw
    with reverts():
        hedging_vault.withdraw({"from": susd_whale})

    chain.sleep(3600 + 1)
    chain.mine(1)

    # converts from sbtc to susd so it is free to withdraw
    sbtc_router.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(3600 + 1)
    chain.mine(1)

    hedging_vault.withdraw(
        hedging_vault.balanceOf(susd_whale), susd_whale, 100, {"from": susd_whale}
    )
    after_hedge_assets = hedging_vault.totalAssets()

    assert prev_hedge_assets > after_hedge_assets
