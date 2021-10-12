import pytest
from brownie import chain, Wei, reverts, Contract
from eth_abi import encode_single


def test_synth_prepare_migration(
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
        "ClonedSynthStrategy",
        encode_single("bytes32", b"ProxysBTC"),
        100,
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["FullCloned"]["clone"], synth_strategy.abi
    )
    susd.approve(susd_vault, 2 ** 256 - 1, {"from": susd_whale})
    susd_vault.deposit({"from": susd_whale})

    chain.sleep(360 + 1)
    chain.mine(1)

    synth_strategy.harvest({"from": gov})

    chain.sleep(360 + 1)
    chain.mine(1)

    assert sbtc.balanceOf(synth_strategy) > 0
    assert sbtc_vault.balanceOf(synth_strategy) == 0
    assert susd.balanceOf(synth_strategy) > 0

    synth_strategy.depositInVault({"from": gov})

    assert sbtc.balanceOf(synth_strategy) == 0
    assert sbtc_vault.balanceOf(synth_strategy) > 0
    assert susd.balanceOf(synth_strategy) > 0

    prev_sbtc = sbtc.balanceOf(synth_strategy)
    prev_sbtc_vault = sbtc_vault.balanceOf(synth_strategy)
    prev_susd = susd.balanceOf(synth_strategy)

    susd_vault.updateStrategyDebtRatio(synth_strategy, 0, {"from": gov})
    susd_vault.addStrategy(cloned_strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    synth_strategy.migrate(cloned_strategy, {"from": susd_vault})

    assert sbtc.balanceOf(synth_strategy) == 0
    assert sbtc_vault.balanceOf(synth_strategy) == 0
    assert susd.balanceOf(synth_strategy) == 0

    assert sbtc.balanceOf(cloned_strategy) == prev_sbtc
    assert sbtc_vault.balanceOf(cloned_strategy) == prev_sbtc_vault
    assert susd.balanceOf(cloned_strategy) == prev_susd
