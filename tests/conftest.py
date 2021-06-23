import pytest
from brownie import config, Contract, ZERO_ADDRESS


@pytest.fixture
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


@pytest.fixture
def user(accounts):
    yield accounts[0]


@pytest.fixture
def rewards(accounts):
    yield accounts[1]


@pytest.fixture
def guardian(accounts):
    yield accounts[2]


@pytest.fixture
def management(accounts):
    yield accounts[3]


@pytest.fixture
def strategist(accounts):
    yield accounts[4]


@pytest.fixture
def keeper(accounts):
    yield accounts[5]


@pytest.fixture
def yvdai_030():
    yield Contract("0x19D3364A399d251E894aC732651be8B0E4e85001")


@pytest.fixture
def yvdai_042():
    yield Contract("0x63739d137EEfAB1001245A8Bd1F3895ef3e186E7")


@pytest.fixture
def yvweth_032():
    yield Contract("0xa9fE4601811213c340e850ea305481afF02f5b28")


@pytest.fixture
def yvweth_042():
    yield Contract("0xa258C4606Ca8206D8aA700cE2143D7db854D168c")


@pytest.fixture
def dai_whale(accounts):
    yield accounts.at("0x5d3a536e4d6dbd6114cc1ead35777bab948e3643", True)


@pytest.fixture
def weth_whale(accounts):
    yield accounts.at("0xc1aae9d18bbe386b102435a8632c8063d31e747c", True)


@pytest.fixture
def token():
    token_address = "0x6b175474e89094c44da98b954eedeac495271d0f"  # this should be the address of the ERC-20 used by the strategy/vault (DAI)
    yield Contract(token_address)


@pytest.fixture
def amount(accounts, token, user):
    amount = 10_000 * 10 ** token.decimals()
    # In order to get some funds for the token you are about to use,
    # it impersonate an exchange address to use it's funds.
    reserve = accounts.at("0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643", force=True)
    token.transfer(user, amount, {"from": reserve})
    yield amount


@pytest.fixture
def dai():
    yield Contract("0x6b175474e89094c44da98b954eedeac495271d0f")


@pytest.fixture
def weth():
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture
def weth_amout(user, weth):
    weth_amout = 10 ** weth.decimals()
    user.transfer(weth, weth_amout)
    yield weth_amout


@pytest.fixture
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian, management)
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagement(management, {"from": gov})
    yield vault


@pytest.fixture
def dai_strategy(strategist, keeper, yvdai_030, yvdai_042, RouterStrategy030, gov):
    strategy = strategist.deploy(
        RouterStrategy030, yvdai_030, yvdai_042, "Route yvDAI 042"
    )
    strategy.setKeeper(keeper)

    for i in range(0, 20):
        strat_address = yvdai_030.withdrawalQueue(i)
        if ZERO_ADDRESS == strat_address:
            break

        yvdai_030.updateStrategyDebtRatio(strat_address, 0, {"from": gov})

    yvdai_030.setPerformanceFee(0, {"from": gov})
    yvdai_030.setManagementFee(0, {"from": gov})
    yvdai_030.addStrategy(strategy, 9_924, 0, 0, {"from": gov})
    yvdai_030.setDepositLimit(0, {"from": gov})

    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
