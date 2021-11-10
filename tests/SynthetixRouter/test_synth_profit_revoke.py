import pytest
from brownie import chain, Wei, Contract


def test_synth_profit_revoke(
    susd_vault,
    sbtc_vault,
    synth_strategy,
    gov,
    sbtc,
    sbtc_whale,
    susd_whale,
    susd,
):

    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})
    susd_vault.deposit({"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.harvest({"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.depositInVault({"from": gov})
    assert synth_strategy.balanceOfWant() > 0
    assert synth_strategy.valueOfInvestment() > 0

    # Send profit to SBTC Vault
    prev_value = synth_strategy.valueOfInvestment()

    sbtc.transfer(sbtc_vault, sbtc.balanceOf(sbtc_whale), {"from": sbtc_whale})
    assert synth_strategy.valueOfInvestment() > prev_value

    susd_vault.revokeStrategy(synth_strategy, {"from": gov})

    synth_strategy.manualRemoveFullLiquidity({"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.harvest({"from": gov})
    chain.sleep(360 + 1)
    chain.mine(1)

    total_gain = susd_vault.strategies(synth_strategy).dict()["totalGain"]
    assert total_gain > 0
    assert susd_vault.strategies(synth_strategy).dict()["totalLoss"] == 0
    assert synth_strategy.balanceOfWant() == 0
    assert synth_strategy.valueOfInvestment() < Wei(
        "0.001 ether"
    )  # there might be dust
