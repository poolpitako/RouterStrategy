from brownie import Contract
from eth_abi import encode_single


def info():
    strategy = Contract("0xc9a62e09834cEdCFF8c136f33d0Ae3406aea66bD")
    snxOracle = Contract("0xDC3EA94CD0AC27d9A86C180091e7f78C683d3699")
    susdOracle = Contract("0xad35Bd71b9aFE6e4bDc266B345c198eaDEf9Ad94")
    snx = Contract(strategy.want())
    susd = Contract(
        Contract(strategy.resolver()).getAddress(encode_single("bytes32", b"Synthetix"))
    )
    snxPrice = snxOracle.latestRoundData()["answer"] / 1e8
    susdPrice = susdOracle.latestRoundData()["answer"] / 1e8
    balanceOfSnx = snx.balanceOf(strategy)
    totalStakedAssets = (
        (balanceOfSnx + strategy.balanceOfEscrowedWant()) / 1e18 * snxPrice
    )

    print(f"Strategy: {strategy.name()}")

    print(f"* SNX: ")
    print(f"    SNX price: ${snxPrice}")
    print(f"    Total Estimated Assets: {strategy.estimatedTotalAssets()/1e18:_} SNX")
    print(f"    Balance of Escrowed SNX: {strategy.balanceOfEscrowedWant()/1e18:_} SNX")
    print(f"    Balance of free SNX: {balanceOfSnx/1e18:_} SNX")
    print(
        f"    Total Balance of SNX: {(balanceOfSnx+strategy.balanceOfEscrowedWant())/1e18:_} SNX"
    )
    print(f"    Delegated assets: {strategy.delegatedAssets()/1e18:_} SNX")

    print(f"* sUSD: ")
    print(f"    sUSD price: ${susdPrice}")
    print(f"    Balance of sUSD: {strategy.balanceOfSusd()/1e18:_} sUSD")
    print(
        f"    Balance of sUSD in Vault: {strategy.balanceOfSusdInVault()/1e18:_} sUSD"
    )

    mintable = susd.maxIssuableSynths(strategy) - strategy.balanceOfDebt()
    print(f"* Debt: ")
    print(f"    Active Debt: $ {strategy.balanceOfDebt()*susdPrice/1e18:_}")
    print(f"    Total Staked Assets: $ {totalStakedAssets:_}")
    print(f"    Target c-ratio: {((1/strategy.getTargetRatio())*1e20):2f} %")
    print(f"    Current c-ratio: {((1/strategy.getCurrentRatio())*1e20):2f} %")
    print(f"    Issuance c-ratio: {((1/strategy.getIssuanceRatio())*1e20):2f} %")

    print(f"- Actions:")
    if strategy.getCurrentRatio() > strategy.getIssuanceRatio():
        print(f"    We will need to burn: {-mintable/1e18:_} sUSD")
    else:
        print(f"    We can mint {mintable/1e18:_} sUSD")
    print()


def main():
    info()
