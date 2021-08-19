import pytest
from brownie import config, Contract, ZERO_ADDRESS
from eth_abi import encode_single

@pytest.fixture
def susd_vault():
    yield Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")


@pytest.fixture
def sbtc_vault():
    yield Contract("0x8472E9914C0813C4b465927f82E213EA34839173")


@pytest.fixture
def synth_strategy(
    strategist, keeper, susd_vault, sbtc_vault, SynthetixRouterStrategy, gov
):
    strategy = strategist.deploy(
        SynthetixRouterStrategy,
        susd_vault,
        sbtc_vault,
        encode_single("bytes32", b"ProxysBTC"),
        "RoutersUSDtosBTC",
    )
    strategy.setKeeper(keeper)

    for i in range(0, 20):
        strat_address = susd_vault.withdrawalQueue(i)
        if ZERO_ADDRESS == strat_address:
            break

        susd_vault.updateStrategyDebtRatio(strat_address, 0, {"from": gov})

    susd_vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    yield strategy


@pytest.fixture
def resolver():
    yield Contract("0x823bE81bbF96BEc0e25CA13170F5AaCb5B79ba83")


@pytest.fixture
def susd(resolver):
    yield Contract(resolver.getAddress(encode_single("bytes32", b"ProxyERC20sUSD")))


@pytest.fixture
def sbtc(resolver):
    yield Contract(resolver.getAddress(encode_single("bytes32", b"ProxysBTC")))


@pytest.fixture
def wbtc():
    yield Contract("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599")


@pytest.fixture
def susd_whale(accounts):
    yield accounts.at("0xa5407eae9ba41422680e2e00537571bcc53efbfd", force=True)


@pytest.fixture
def sbtc_whale(accounts):
    yield accounts.at("0xbf2f5b49571c9ff8610fad2d99a8b1c1829acff9", force=True)


@pytest.fixture
def wbtc_whale(accounts):
    yield accounts.at("0x64ad7226339c281f6ed951f3ce8aa807ab067054", force=True)