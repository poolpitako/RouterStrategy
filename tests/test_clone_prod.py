import pytest
from brownie import chain, Wei, Contract, ZERO_ADDRESS


def remove_old_strats(vault):
    for i in range(0, 20):
        strat_address = vault.withdrawalQueue(i)
        if ZERO_ADDRESS == strat_address:
            break

        vault.updateStrategyDebtRatio(strat_address, 0, {"from": vault.governance()})


def harvest_strats(vault):
    for i in range(0, 20):
        strat_address = vault.withdrawalQueue(i)
        if ZERO_ADDRESS == strat_address:
            break

        Contract(strat_address).harvest({"from": vault.governance()})


def do_happy_case(old_vault, strategy, whale):

    new_vault = Contract(strategy.yVault())
    token = Contract(strategy.want())
    gov = old_vault.governance()

    remove_old_strats(old_vault)

    # add router to old_vault
    old_vault.setPerformanceFee(0, {"from": gov})
    old_vault.setManagementFee(0, {"from": gov})
    old_vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})
    old_vault.setDepositLimit(0, {"from": gov})

    new_vault.setDepositLimit(2 ** 256 - 1, {"from": new_vault.governance()})

    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() == 0

    strategy.harvest({"from": gov})

    assert strategy.balanceOfWant() == 0
    assert strategy.valueOfInvestment() > 0

    prev_value = strategy.valueOfInvestment()

    # Produce earning in the new_vault
    token.transfer(new_vault, Wei("10 ether"), {"from": whale})
    assert strategy.valueOfInvestment() > prev_value

    # harvest all strats in new vault
    # harvest_strats(new_vault)

    chain.sleep(3600 * 11)
    chain.mine(1)

    # harvest router to get profits
    strategy.harvest({"from": gov})

    total_gain = old_vault.strategies(strategy).dict()["totalGain"]
    assert total_gain > 0
    assert old_vault.strategies(strategy).dict()["totalLoss"] == 0

    old_vault.revokeStrategy(strategy, {"from": gov})
    tx = strategy.harvest({"from": gov})
    total_gain += tx.events["Harvested"]["profit"]
    chain.sleep(3600 * 8)
    chain.mine(1)

    assert old_vault.strategies(strategy).dict()["totalGain"] == total_gain
    assert old_vault.strategies(strategy).dict()["totalLoss"] == 0
    assert old_vault.strategies(strategy).dict()["totalDebt"] == 0


def test_yfi_router_043():
    old_vault = Contract("0xE14d13d8B3b85aF791b2AADD661cDBd5E6097Db1")
    strategy = Contract("0x0A5157244e4F82F100A461CA65C7b05C8dACf835")
    whale = Contract("0x3ff33d9162ad47660083d7dc4bc02fb231c81677")
    do_happy_case(old_vault, strategy, whale)
