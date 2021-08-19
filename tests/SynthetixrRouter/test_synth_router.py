import pytest
from brownie import chain, Wei, reverts, Contract, ZERO_ADDRESS
from eth_abi import encode_single

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
    wbtc,
    susd_whale,
    wbtc_whale,
):

    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})

    crvWTBC_SBTC = Contract("0x7fC77b5c7614E1533320Ea6DDc2Eb61fa00A9714")
    wbtc.approve(crvWTBC_SBTC, 2 ** 256 - 1, {"from": wbtc_whale})
    crvWTBC_SBTC.exchange(1, 2, 1 * 10 ** 11, 0, {"from": wbtc_whale})

    assert sbtc.balanceOf(wbtc_whale) > 0

    prev_value = synth_strategy.valueOfInvestment()
    prev_value_dest_vault = sbtc_vault.totalAssets()

    # exchange susd to sbtc
    synth_strategy.harvest({"from": gov})

    assert synth_strategy.valueOfInvestment() == prev_value
    assert synth_strategy.balanceOfWant() == 0
    assert sbtc.balanceOf(synth_strategy) > 0
    assert sbtc_vault.totalAssets() == prev_value_dest_vault

    # deposit sbtc into new strategy
    chain.sleep(3600 * 11)
    chain.mine(1)
    synth_strategy.depositInVault({"from": gov})

    assert synth_strategy.valueOfInvestment() > prev_value
    assert synth_strategy.balanceOfWant() == 0
    assert sbtc.balanceOf(synth_strategy) == 0
    assert sbtc_vault.totalAssets() > prev_value_dest_vault
    assert sbtc_vault.balanceOf(synth_strategy) > 0

    prev_value_dest_vault = sbtc_vault.totalAssets()

    # produce gains
    sbtc.transfer(sbtc_vault, sbtc.balanceOf(wbtc_whale), {"from": wbtc_whale})

    synth_strategy.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.harvest({"from": gov})

    total_gain = susd_vault.strategies(synth_strategy).dict()["totalGain"]
    total_loss = susd_vault.strategies(synth_strategy).dict()["totalLoss"]
    assert total_gain > 0
    assert total_loss == 0

    susd_vault.revokeStrategy(synth_strategy, {"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.manualRemoveFullLiquidity({"from": gov})

    assert synth_strategy.balanceOfWant() > 0
    assert sbtc.balanceOf(synth_strategy) == 0
    assert sbtc_vault.balanceOf(synth_strategy) == 0

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
