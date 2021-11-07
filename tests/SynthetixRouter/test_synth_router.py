import pytest
from brownie import chain, Wei, reverts, Contract, ZERO_ADDRESS
from eth_abi import encode_single

DUST_THRESHOLD = 10_000


def test_synth_strategy_susd_sbtc(
    susd_vault,
    sbtc_vault,
    synth_strategy,
    strategist,
    rewards,
    keeper,
    gov,
    susd,
    sbtc,
    susd_whale,
    sbtc_whale,
):

    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})
    susd_vault.deposit({"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    assert sbtc.balanceOf(sbtc_whale) > 0

    prev_value = synth_strategy.valueOfInvestment()
    prev_value_dest_vault = sbtc_vault.totalAssets()

    # exchange susd to sbtc
    tx = synth_strategy.harvest({"from": gov})

    total_gain = susd_vault.strategies(synth_strategy).dict()["totalGain"]
    total_loss = susd_vault.strategies(synth_strategy).dict()["totalLoss"]

    assert synth_strategy.valueOfInvestment() == prev_value
    assert synth_strategy.estimatedTotalAssets() > 0
    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) > 0
    assert sbtc_vault.totalAssets() == prev_value_dest_vault

    # deposit sbtc into new strategy
    chain.sleep(3600 * 11)
    chain.mine(1)
    synth_strategy.depositInVault({"from": gov})

    assert synth_strategy.valueOfInvestment() > prev_value
    assert synth_strategy.estimatedTotalAssets() > 0
    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) == 0
    assert sbtc_vault.totalAssets() > prev_value_dest_vault
    assert sbtc_vault.balanceOf(synth_strategy) > 0

    prev_value_dest_vault = sbtc_vault.totalAssets()

    # produce gains
    sbtc.transfer(sbtc_vault, sbtc.balanceOf(sbtc_whale), {"from": sbtc_whale})

    susd_vault.revokeStrategy(synth_strategy, {"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.manualRemoveFullLiquidity({"from": gov})

    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) < DUST_THRESHOLD
    assert sbtc_vault.balanceOf(synth_strategy) < DUST_THRESHOLD

    chain.sleep(360 + 1)
    chain.mine(1)
    tx = synth_strategy.harvest({"from": gov})

    total_gain += tx.events["Harvested"]["profit"]
    total_loss += tx.events["Harvested"]["loss"]
    chain.sleep(360 + 1)
    chain.mine(1)

    assert susd_vault.strategies(synth_strategy).dict()["totalGain"] == total_gain
    assert susd_vault.strategies(synth_strategy).dict()["totalLoss"] == total_loss
    assert susd_vault.strategies(synth_strategy).dict()["totalDebt"] == 0


def test_user_deposit_and_reverts_withdraws(
    susd_vault,
    sbtc_vault,
    synth_strategy,
    strategist,
    rewards,
    keeper,
    gov,
    susd,
    sbtc,
    susd_whale,
):
    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})

    previousBalance = susd_vault.balanceOf(susd_whale)

    susd_vault.deposit({"from": susd_whale})

    assert susd_vault.balanceOf(susd_whale) > previousBalance

    chain.sleep(360 + 1)
    chain.mine(1)

    assert sbtc.balanceOf(synth_strategy) == 0

    synth_strategy.harvest({"from": gov})

    assert sbtc.balanceOf(synth_strategy) > 0

    chain.sleep(360 + 1)
    chain.mine(1)
    with reverts():
        susd_vault.withdraw({"from": susd_whale})


def test_user_deposit_manual_conversion_and_withdraw(
    susd_vault,
    sbtc_vault,
    synth_strategy,
    strategist,
    rewards,
    keeper,
    gov,
    susd,
    sbtc,
    susd_whale,
):
    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})

    previousBalance = susd_vault.balanceOf(susd_whale)

    prevValue = susd_vault.totalAssets()

    susd_vault.deposit({"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    assert susd_vault.totalAssets() > prevValue

    assert susd_vault.balanceOf(susd_whale) > previousBalance
    assert sbtc.balanceOf(synth_strategy) == 0

    # first time only exchanges susd to sbtc
    tx = synth_strategy.harvest({"from": gov})

    assert synth_strategy.valueOfInvestment() == 0
    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) > 0

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.depositInVault({"from": gov})

    assert synth_strategy.valueOfInvestment() > 0
    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) < DUST_THRESHOLD

    chain.sleep(360 + 1)
    chain.mine(1)

    # second time should be all loss because investment is locked in yvault and in synth
    total_debt = susd_vault.strategies(synth_strategy).dict()["totalDebt"]
    tx = synth_strategy.harvest({"from": gov})

    assert synth_strategy.balanceOfWant() > 0
    assert synth_strategy.valueOfInvestment() > 0

    loss = tx.events["Harvested"]["loss"]

    assert loss > 0

    # wait 6 min to withdraw
    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.manualRemoveFullLiquidity({"from": gov})

    assert sbtc.balanceOf(synth_strategy) < DUST_THRESHOLD
    assert synth_strategy.balanceOfWant() > 0
    assert synth_strategy.valueOfInvestment() == 0

    # wait 6 min to withdraw
    chain.sleep(360 + 1)
    chain.mine(1)

    susd_vault.withdraw(
        susd_vault.balanceOf(susd_whale), susd_whale, 10_000, {"from": susd_whale}
    )

    assert sbtc.balanceOf(synth_strategy) < DUST_THRESHOLD
    assert susd_vault.balanceOf(susd_whale) == 0
