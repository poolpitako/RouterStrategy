import pytest
from brownie import chain, Contract, accounts, ZERO_ADDRESS, Wei, reverts
from eth_abi import encode_single

DUST_THRESHOLD = 10_000


def test_deposit_and_withdraw_wo_profit(
    synth_strategy, susd_vault, sbtc_vault, sbtc, susd_whale
):
    sbtc_router = synth_strategy
    hedging_vault = susd_vault

    susd = Contract(sbtc_router.want())
    gov = accounts.at(hedging_vault.governance(), True)

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


def test_deposit_and_withdraw_w_profit(
    synth_strategy, susd_vault, sbtc_vault, sbtc, susd_whale, sbtc_whale
):
    sbtc_router = synth_strategy
    hedging_vault = susd_vault

    susd = Contract(sbtc_router.want())
    gov = accounts.at(hedging_vault.governance(), True)

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


def test_deposit_harvest_and_revert_withdraw(
    synth_strategy, susd_vault, sbtc_vault, sbtc, susd_whale, sbtc_whale
):
    sbtc_router = synth_strategy
    hedging_vault = susd_vault

    susd = Contract(sbtc_router.want())
    gov = accounts.at(hedging_vault.governance(), True)

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
    sbtc_router.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(3600 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"Second harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] > 0

    prev_hedge_assets = hedging_vault.totalAssets()
    # money has just been exchange for synth so we need to wait 6 min to withdraw
    with reverts():
        hedging_vault.withdraw({"from": susd_whale})

    chain.sleep(3600 + 1)
    chain.mine(1)

    tx = sbtc_router.harvest({"from": gov})

    print(f"Third harvest {tx.events['Harvested']}")
    assert tx.events["Harvested"]["loss"] > 0

    chain.sleep(3600 + 1)
    chain.mine(1)

    sbtc_router.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(3600 + 1)
    chain.mine(1)

    hedging_vault.withdraw(
        hedging_vault.balanceOf(susd_whale), susd_whale, 100, {"from": susd_whale}
    )
    after_hedge_assets = hedging_vault.totalAssets()

    assert prev_hedge_assets > after_hedge_assets
