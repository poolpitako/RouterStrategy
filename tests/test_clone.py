import pytest
from brownie import chain, Wei, reverts, Contract, ZERO_ADDRESS


def move_funds(
    vault, dest_vault, strategy, gov, weth, weth_whale, original_strategy=None
):
    print(strategy.name())
    # Move all funds to the new strat
    for i in range(0, 20):
        strat_address = vault.withdrawalQueue(i)
        if ZERO_ADDRESS == strat_address:
            break

        if strategy == strat_address or (
            original_strategy and original_strategy == strat_address
        ):
            continue

        strat = Contract(strat_address)
        if vault.strategies(strat).dict()["totalDebt"] == 0:
            continue

        print(f"harvesting {strat.name()}")
        tx = strat.harvest({"from": gov})
        print(f"harvested {tx.events['Harvested']}")

    if original_strategy:
        original_strategy.harvest({"from": gov})
    strategy.harvest({"from": gov})
    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    prev_value = strategy.valueOfInvestment()
    weth.transfer(dest_vault, Wei("10 ether"), {"from": weth_whale})
    assert strategy.valueOfInvestment() > prev_value

    strategy.harvest({"from": gov})
    chain.sleep(3600 * 11)
    chain.mine(1)

    total_gain = vault.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    vault.revokeStrategy(strategy, {"from": gov})
    tx = strategy.harvest({"from": gov})
    total_gain += tx.events["Harvested"]["profit"]
    chain.sleep(3600 * 8)
    chain.mine(1)

    assert vault.strategies(strategy).dict()["totalGain"] == total_gain
    assert vault.strategies(strategy).dict()["totalLoss"] == 0
    assert vault.strategies(strategy).dict()["totalDebt"] == 0


#
def test_original_strategy(
    origin_vault,
    destination_vault,
    strategy,
    strategist,
    rewards,
    keeper,
    gov,
    token,
    weth_whale,
):

    move_funds(origin_vault, destination_vault, strategy, gov, token, weth_whale)


def test_cloned_strategy(
    origin_vault,
    destination_vault,
    strategy,
    strategist,
    rewards,
    keeper,
    gov,
    token,
    weth_whale,
):

    clone_tx = strategy.cloneRouter(
        origin_vault, strategist, rewards, keeper, destination_vault, "ClonedStrategy"
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], strategy.abi
    )

    origin_vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})

    origin_vault.addStrategy(cloned_strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    move_funds(
        origin_vault,
        destination_vault,
        cloned_strategy,
        gov,
        token,
        weth_whale,
        original_strategy=strategy,
    )


def test_clone_of_clone(
    origin_vault, destination_vault, strategist, rewards, keeper, strategy
):

    clone_tx = strategy.cloneRouter(
        origin_vault, strategist, rewards, keeper, destination_vault, "ClonedStrategy"
    )

    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], strategy.abi
    )

    # should not clone a clone
    with reverts():
        cloned_strategy.cloneRouter(
            origin_vault,
            strategist,
            rewards,
            keeper,
            destination_vault,
            "New Strategy",
            {"from": strategist},
        )
