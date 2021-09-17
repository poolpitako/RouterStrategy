// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {BaseStrategy} from "@yearnvaults/contracts/BaseStrategy.sol";
import {
    SafeERC20,
    SafeMath,
    IERC20,
    Address
} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";

import "./RouterStrategy.sol";
import "./Synthetix.sol";

interface IUni {
    function getAmountsOut(uint256 amountIn, address[] calldata path)
        external
        view
        returns (uint256[] memory amounts);
}

contract SynthetixRouterStrategy is RouterStrategy, Synthetix {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    uint256 internal constant DENOMINATOR = 10_000;
    uint256 internal constant DUST_THRESHOLD = 10_000;
    address public constant weth = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address public constant uniswapRouter =
        0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;

    // This is the amount of sUSD that should not be exchanged for synth
    // Usually 100 for 1%.
    uint256 public susdBuffer;

    constructor(
        address _vault,
        address _yVault,
        string memory _strategyName,
        bytes32 _synth,
        uint256 _susdBuffer
    ) public RouterStrategy(_vault, _yVault, _strategyName) {
        _initializeSynthetixRouter(_synth, _susdBuffer);
    }

    event FullCloned(address indexed clone);

    function cloneSynthetixRouter(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _yVault,
        string memory _strategyName,
        bytes32 _synth,
        uint256 _susdBuffer
    ) external returns (address newStrategy) {
        require(isOriginal);
        // Copied from https://github.com/optionality/clone-factory/blob/master/contracts/CloneFactory.sol
        bytes20 addressBytes = bytes20(address(this));
        assembly {
            // EIP-1167 bytecode
            let clone_code := mload(0x40)
            mstore(
                clone_code,
                0x3d602d80600a3d3981f3363d3d373d3d3d363d73000000000000000000000000
            )
            mstore(add(clone_code, 0x14), addressBytes)
            mstore(
                add(clone_code, 0x28),
                0x5af43d82803e903d91602b57fd5bf30000000000000000000000000000000000
            )
            newStrategy := create(0, clone_code, 0x37)
        }

        SynthetixRouterStrategy(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _yVault,
            _strategyName,
            _synth,
            _susdBuffer
        );

        emit FullCloned(newStrategy);
    }

    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _yVault,
        string memory _strategyName,
        bytes32 _synth,
        uint256 _susdBuffer
    ) public {
        super.initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _yVault,
            _strategyName
        );
        _initializeSynthetixRouter(_synth, _susdBuffer);
    }

    function _initializeSynthetixRouter(bytes32 _synth, uint256 _susdBuffer)
        internal
    {
        _initializeSynthetix(_synth);
        susdBuffer = _susdBuffer;
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        uint256 looseSynth = _balanceOfSynth();
        uint256 _sUSDBalance = balanceOfWant();

        // this will tell us how much we need to keep in the buffer
        uint256 totalDebt = vault.strategies(address(this)).totalDebt; // in sUSD (want)
        uint256 buffer = totalDebt.mul(susdBuffer).div(DENOMINATOR);

        uint256 _sUSDToInvest =
            _sUSDBalance > buffer ? _sUSDBalance.sub(buffer) : 0;
        uint256 _sUSDNeeded = _sUSDToInvest == 0 ? buffer.sub(_sUSDBalance) : 0;
        uint256 _synthToSell =
            _sUSDNeeded > 0 ? _synthFromSUSD(_sUSDNeeded) : 0; // amount of Synth that we need to sell to refill buffer
        uint256 _synthToInvest =
            looseSynth > _synthToSell ? looseSynth.sub(_synthToSell) : 0;

        if (_synthToSell == 0) {
            // This will first deposit any loose synth in the vault if it not locked
            // Then will invest all available sUSD (exchanging to Synth)
            // After this, user has to manually call depositInVault to deposit synth after settlement period
            if (_sUSDToInvest == 0) {
                return;
            }
            if (checkWaitingPeriod() && looseSynth > DUST_THRESHOLD) {
                depositInVault();
            }
            exchangeSUSDToSynth(_sUSDToInvest);
            // now the waiting period starts
        } else if (_synthToSell >= DUST_THRESHOLD) {
            // this means that we need to refill the buffer
            // we may have already some uninvested Synth so we use it
            uint256 available = _synthToSUSD(looseSynth);
            uint256 sUSDToWithdraw =
                _sUSDNeeded > available ? _sUSDNeeded.sub(available) : 0;
            // this will withdraw and sell full balance of Synth (inside withdrawSomeWant)
            if (sUSDToWithdraw > 0) {
                withdrawSomeWant(sUSDToWithdraw, true);
            }
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 wantBal = balanceOfWant(); // want is always sUSD

        if (wantBal < _amountNeeded) {
            (_liquidatedAmount, _loss) = withdrawSomeWant(_amountNeeded, false);
        }

        _liquidatedAmount = Math.min(
            _amountNeeded,
            _liquidatedAmount == 0 ? wantBal : _liquidatedAmount
        );
    }

    function updateSUSDBuffer(uint256 _susdBuffer) public onlyVaultManagers {
        require(_susdBuffer <= 10_000, "!too high");
        susdBuffer = _susdBuffer;
    }

    function checkWaitingPeriod() private returns (bool freeToMove) {
        return
            _exchanger().maxSecsLeftInWaitingPeriod(
                address(this),
                synthCurrencyKey
            ) == 0;
    }

    function depositInVault() public onlyVaultManagers {
        uint256 balanceOfSynth = _balanceOfSynth();
        if (balanceOfSynth > DUST_THRESHOLD && checkWaitingPeriod()) {
            _checkAllowance(
                address(yVault),
                address(_synthCoin()),
                balanceOfSynth
            );
            yVault.deposit();
        }
    }

    //safe to enter more than we have
    function withdrawSomeWant(uint256 _amount, bool performExchanges)
        private
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        if (performExchanges) {
            // we exchange synths to susd
            uint256 synthBalanceBefore = _balanceOfSynth();
            uint256 sUSDBalanceBefore = balanceOfWant();
            uint256 _newAmount = _amount.sub(sUSDBalanceBefore);

            uint256 _synthAmount = _synthFromSUSD(_newAmount);
            if (checkWaitingPeriod()) {
                if (_synthAmount <= synthBalanceBefore) {
                    exchangeSynthToSUSD(_synthAmount);
                    return (_amount, 0);
                }

                _synthAmount = _synthAmount.sub(synthBalanceBefore);
            }
            _withdrawFromYVault(_synthAmount);
            uint256 newBalanceOfSynth = _balanceOfSynth();
            if (newBalanceOfSynth > DUST_THRESHOLD) {
                exchangeSynthToSUSD(newBalanceOfSynth);
            }
        }

        uint256 totalAssets = balanceOfWant();
        if (_amount > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amount.sub(totalAssets);
        } else {
            _liquidatedAmount = _amount;
        }
    }

    function liquidateAllPositions()
        internal
        override
        returns (uint256 _amountFreed)
    {
        // In order to work, manualRemoveFullLiquidity needs to be call 6 min in advance
        require(checkWaitingPeriod(), "Wait for settlement period");
        require(
            valueOfInvestment() < DUST_THRESHOLD,
            "Need to remove liquidity from vault first"
        );
        require(
            _balanceOfSynth() < DUST_THRESHOLD,
            "Need to exchange synth to want first"
        );
        _amountFreed = balanceOfWant();
    }

    function manualRemoveFullLiquidity()
        external
        onlyVaultManagers
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        // It will withdraw all the assets from the yvault and the exchange them to want
        (_liquidatedAmount, _loss) = withdrawSomeWant(
            estimatedTotalAssets(),
            true
        );
    }

    function manualRemoveLiquidity(uint256 _liquidityToRemove)
        external
        onlyVaultManagers
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        _liquidityToRemove = Math.min(
            _liquidityToRemove,
            estimatedTotalAssets()
        );
        // It will withdraw _liquidityToRemove assets from the yvault and the exchange them to want
        (_liquidatedAmount, _loss) = withdrawSomeWant(_liquidityToRemove, true);
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return
            balanceOfWant().add(_sUSDFromSynth(_balanceOfSynth())).add(
                valueOfInvestment()
            );
    }

    function _ethToWant(uint256 _amount) internal view returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = address(want);

        uint256[] memory amounts =
            IUni(uniswapRouter).getAmountsOut(_amount, path);

        return amounts[amounts.length - 1];
    }

    function valueOfInvestment() public view override returns (uint256) {
        return
            _sUSDFromSynth(
                yVault.balanceOf(address(this)).mul(yVault.pricePerShare()).div(
                    10**yVault.decimals()
                )
            );
    }

    function prepareMigration(address _newStrategy) internal override {
        super.prepareMigration(_newStrategy);
        _synthCoin().transferAndSettle(_newStrategy, _balanceOfSynth());
    }

    function prepareReturn(uint256 _debtOutstanding)
        internal
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {
        uint256 totalDebt = vault.strategies(address(this)).totalDebt;
        uint256 totalAssetsAfterProfit = estimatedTotalAssets();
        uint256 _balanceOfWant = balanceOfWant();

        _debtPayment = _debtOutstanding;

        if (totalDebt < totalAssetsAfterProfit) {
            _debtPayment = Math.min(_debtOutstanding, _balanceOfWant);
            _profit = _balanceOfWant.sub(_debtPayment);
        } else {
            _loss = totalDebt.sub(totalAssetsAfterProfit);
            _debtPayment = Math.min(_debtOutstanding, _balanceOfWant);
        }
    }
}
