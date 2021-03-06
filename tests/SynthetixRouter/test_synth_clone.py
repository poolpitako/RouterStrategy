import pytest
from brownie import chain, Wei, reverts, Contract
from eth_abi import encode_single


def route_susd_sbtc(
    synth_strategy,
    susd,
    sbtc,
    sbtc_whale,
    susd_whale,
    sbtc_vault,
    susd_vault,
    gov,
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
    assert sbtc.balanceOf(synth_strategy) < 10_000  # 10k is DUST_THRESHOLD
    assert sbtc_vault.balanceOf(synth_strategy) < 10_000  # 10k is DUST_THRESHOLD

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


def test_synth_cloned_strategy(
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

    clone_tx = synth_strategy.cloneSynthetixRouter(
        susd_vault,
        strategist,
        rewards,
        keeper,
        sbtc_vault,
        "ClonedSynthStrategy",
        encode_single("bytes32", b"ProxysBTC"),
        100,
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], synth_strategy.abi
    )

    susd_vault.updateStrategyDebtRatio(synth_strategy, 0, {"from": gov})

    synth_strategy.manualRemoveFullLiquidity({"from": gov})
    chain.sleep(360 + 1)
    chain.mine(1)
    # Return the funds to the vault
    synth_strategy.harvest({"from": gov})
    susd_vault.addStrategy(cloned_strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    route_susd_sbtc(
        cloned_strategy,
        susd,
        sbtc,
        sbtc_whale,
        susd_whale,
        sbtc_vault,
        susd_vault,
        gov,
    )


def test_clone_of_clone(
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

    clone_tx = synth_strategy.cloneSynthetixRouter(
        susd_vault,
        strategist,
        rewards,
        keeper,
        sbtc_vault,
        "ClonedSynthStrategy",
        encode_single("bytes32", b"ProxysBTC"),
        100,
        {"from": strategist},
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], synth_strategy.abi
    )

    # should not clone a clone
    with reverts():
        cloned_strategy.cloneSynthetixRouter(
            susd_vault,
            strategist,
            rewards,
            keeper,
            sbtc_vault,
            "New ClonedSynthStrategy",
            encode_single("bytes32", b"ProxysBTC"),
            100,
            {"from": strategist},
        )
