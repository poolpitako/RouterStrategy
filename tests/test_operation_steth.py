import pytest
from brownie import Contract, ZERO_ADDRESS, Wei, chain, accounts, reverts


def test_migrate(origin_vault, destination_vault, strategy, gov, loss_checker):
    whale = accounts.at('0x99ac10631F69C753DDb595D074422a0922D9056B',force=True)
    old_vault = origin_vault
    new_vault = destination_vault
    old_strategy = Contract(old_vault.withdrawalQueue(0),owner=gov)
    new_strategy = strategy

    # At this point, all fund are already removed from existing strats
    # We only have to harvest into our router strat, which is already at 100% DR
    strategy.setFeeLossTolerance(1e18,{"from": gov})
    strategy.harvest({"from": gov})

    chain.sleep(60 * 60 * 24 * 7)

    # No sells, means no profit yet
    # Let's set mgmt fee pretty high
    origin_vault.setManagementFee(500, {"from": gov})

    expectedLoss = loss_checker.check_loss(0, 0, strategy)
    print(f'EXPECTED LOSS AMOUNT = {expectedLoss}')
    expected_loss = emulate_fees(strategy, origin_vault)

    # Harvest should fail due to loss
    with reverts('LossyWithFees'):
        tx = strategy.harvest({"from": gov})

    chain.sleep(60 * 60 * 24 * 7)
    # Let's transfer some want to the checker that it can sweep
    est = loss_checker.check_loss(0, 0, strategy)
    whale = accounts.at('0x99ac10631F69C753DDb595D074422a0922D9056B', force=True)
    want = Contract(origin_vault.token(),owner=whale)

    pps = origin_vault.pricePerShare()
    strategy.setFeeLossTolerance(100e18,{"from": gov})
    
    tx = strategy.harvest({"from": gov})

    strategy.setFeeLossTolerance(100e18,{"from": gov})
    # Airdrop to offset profit
    want.transfer(origin_vault, est)
    assert origin_vault.pricePerShare() == pps


    totalShares = origin_vault.totalSupply()
    tx = strategy.harvest({"from": gov})
    totalSharesAfter = origin_vault.totalSupply()
    assert totalSharesAfter <= totalShares + (
        strategy.feeLossTolerance() * 
        origin_vault.pricePerShare() / 
        1e18
    )

    print(tx.events['Harvested'])
    # origin_vault.updateStrategyDebtRatio(strategy, 10_000, {'from':gov})
    


def emulate_fees(strategy, origin_vault):
    SECS_PER_YEAR = 31_557_600
    MAX_BPS = 10_000
    v = origin_vault
    mgmt_fee = v.managementFee()
    params = v.strategies(strategy).dict()
    last = v.lastReport()
    current = chain.time()
    time_since = current - last
    total_assets = v.totalAssets()
    gov_fee = total_assets * time_since * mgmt_fee / MAX_BPS / SECS_PER_YEAR
    return gov_fee