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
import "@openzeppelin/contracts/math/Math.sol";

import "./Interfaces/erc20/IERC20Extended.sol";

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

    uint256 internal constant DUST_THRESHOLD = 10_000;
    address public constant weth = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address public constant uniswapRouter =
        0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;

    uint256 public susdBuffer; // 10% amount of sUSD that should not be exchanged for synth
    uint256 public constant DENOMINATOR = 10_000;

    constructor(
        address _vault,
        address _yVault,
        bytes32 _synth,
        string memory _strategyName
    ) public RouterStrategy(_vault, _yVault, _strategyName) {
        _initializeSynthetix(_synth);
        susdBuffer = 100; // initial one is 1%
    }

    event FullCloned(address indexed clone);

    function cloneSynthetixRouter(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _yVault,
        bytes32 _synth,
        string memory _strategyName
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
            _synth,
            _strategyName
        );

        emit FullCloned(newStrategy);
    }

    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _yVault,
        bytes32 _synth,
        string memory _strategyName
    ) public {
        super.initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _yVault,
            _strategyName
        );
        _initializeSynthetix(_synth);
        susdBuffer = 1_000; // 10% over 10_000
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        uint256 looseSynth = _balanceOfSynth();
        uint256 _sUSDBalance = _balanceOfSUSD();

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
            // This will invest all available sUSD (exchanging to Synth first)
            // Exchange amount of sUSD to Synth
            if (_sUSDToInvest == 0) {
                return;
            }
            if (looseSynth > DUST_THRESHOLD) {
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
            (_liquidatedAmount, _loss) = withdrawSomeWant(
                _amountNeeded.sub(wantBal)
            );
        }

        _liquidatedAmount = Math.min(
            _amountNeeded,
            _liquidatedAmount.add(wantBal)
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
            uint256 _new_amount = _amount.sub(sUSDBalanceBefore);

            uint256 _synth_amount = _synthFromSUSD(_new_amount);
            uint256 _remaining_amount = _synth_amount;
            if (checkWaitingPeriod()) {
                if (_synth_amount <= synthBalanceBefore) {
                    exchangeSynthToSUSD(_synth_amount);
                    return (_amount, 0);
                }

                _remaining_amount = _synth_amount.sub(synthBalanceBefore);
            }
            _withdrawFromYVault(_remaining_amount);
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
        _amountFreed = balanceOfWant();
    }

    function manualRemoveFullLiquidity()
        external
        onlyVaultManagers
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        // It will remove max amount of assets and trade synth for sUSD
        // the Synthetix waiting period will start (and harvest can be called 6 mins later)
        if (yVault.balanceOf(address(this)) > 0) {
            super.liquidateAllPositions();
        }
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
        // It will withdraw all the assets from the yvault and the exchange them to want
        (_liquidatedAmount, _loss) = withdrawSomeWant(_liquidityToRemove, true);
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return
            _balanceOfSUSD().add(_synthToSUSD(_balanceOfSynth())).add(
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
            _synthToSUSD(
                yVault.balanceOf(address(this)).mul(yVault.pricePerShare()).div(
                    10**yVault.decimals()
                )
            );
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

        if (totalDebt < totalAssetsAfterProfit) {
            //profit
            _profit = totalAssetsAfterProfit.sub(totalDebt);
        } else {
            _loss = totalDebt.sub(totalAssetsAfterProfit);
        }
    }
}
