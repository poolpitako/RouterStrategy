import pytest
from brownie import chain, Wei, reverts, Contract
from eth_abi import encode_single

DUST_THRESHOLD = 10_000


def route_susd_sbtc(
    synth_strategy,
    susd,
    sbtc,
    wbtc,
    wbtc_whale,
    susd_whale,
    sbtc_vault,
    susd_vault,
    gov,
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
    assert sbtc.balanceOf(synth_strategy) < DUST_THRESHOLD
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
    wbtc,
    susd_whale,
    wbtc_whale,
):

    clone_tx = synth_strategy.cloneSynthetixRouter(
        susd_vault,
        strategist,
        rewards,
        keeper,
        sbtc_vault,
        encode_single("bytes32", b"ProxysBTC"),
        "ClonedSynthStrategy",
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["FullCloned"]["clone"], synth_strategy.abi
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
        wbtc,
        wbtc_whale,
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
    wbtc,
    susd_whale,
    wbtc_whale,
):

    clone_tx = synth_strategy.cloneSynthetixRouter(
        susd_vault,
        strategist,
        rewards,
        keeper,
        sbtc_vault,
        encode_single("bytes32", b"ProxysBTC"),
        "ClonedSynthStrategy",
        {"from": strategist},
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["FullCloned"]["clone"], synth_strategy.abi
    )

    # should not clone a clone
    with reverts():
        cloned_strategy.cloneSynthetixRouter(
            susd_vault,
            strategist,
            rewards,
            keeper,
            sbtc_vault,
            encode_single("bytes32", b"ProxysBTC"),
            "New ClonedSynthStrategy",
            {"from": strategist},
        )
