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

    constructor(
        address _vault,
        address _yVault,
        bytes32 _synth,
        string memory _strategyName
    ) public RouterStrategy(_vault, _yVault, _strategyName) {
        _initializeSynthetix(_synth);
    }

    event Cloned(address indexed clone);

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

        emit Cloned(newStrategy);
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
        _initialize(_vault, _strategist, _rewards, _keeper);
        require(address(yVault) == address(0));
        _initializeSynthetix(_synth);
        _initializeThis(_yVault, _strategyName);
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }
        depositInVault();
        exchangeAllWant();
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

    function depositInVault() public onlyGovernance {
        if (
            _balanceOfSynth() > DUST_THRESHOLD &&
            _exchanger().maxSecsLeftInWaitingPeriod(
                address(this),
                synthCurrencyKey
            ) ==
            0
        ) {
            _checkAllowance(
                address(yVault),
                address(_synthCoin()),
                _balanceOfSynth()
            );
            yVault.deposit();
        }
    }

    function exchangeAllWant() internal returns (uint256 _exchangedAmount) {
        uint256 balanceBefore = _balanceOfSynth();
        if (_balanceOfSUSD() > DUST_THRESHOLD) {
            exchangeSUSDToSynth(_balanceOfSUSD());
        }
        _exchangedAmount = _balanceOfSynth().sub(balanceBefore);
    }

    function exchangeAllSynth() internal returns (uint256 _exchangedAmount) {
        uint256 balanceBefore = _balanceOfSUSD();
        if (_balanceOfSynth() > DUST_THRESHOLD) {
            exchangeSynthToSUSD(_balanceOfSynth());
        }
        _exchangedAmount = _balanceOfSUSD().sub(balanceBefore);
    }

    //safe to enter more than we have
    function withdrawSomeWant(uint256 _amount)
        public
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 sUSDBalanceBefore = balanceOfWant();
        uint256 synthBalanceBefore = _balanceOfSynth();

        if (_amount < sUSDBalanceBefore) {
            return (_amount, 0);
        }

        uint256 _new_amount = _amount.sub(sUSDBalanceBefore);

        uint256 _synth_amount = _synthFromSUSD(_new_amount);
        if (_synth_amount <= synthBalanceBefore) {
            exchangeSynthToSUSD(_synth_amount);
            return (_amount, 0);
        }

        uint256 _remaining_amount = _synth_amount.sub(synthBalanceBefore);

        _withdrawFromYVault(_remaining_amount);
        if (_balanceOfSynth() > DUST_THRESHOLD) {
            exchangeSynthToSUSD(_balanceOfSynth());
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
        onlyGovernance
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        // It will remove max amount of assets and trade synth for sUSD
        // the Synthetix waiting period will start (and harvest can be called 6 mins later)
        if (yVault.balanceOf(address(this)) > 0) {
            super.liquidateAllPositions();
        }
        exchangeAllSynth();
        (_liquidatedAmount, _loss) = withdrawSomeWant(estimatedTotalAssets());
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
        _debtPayment = _debtOutstanding;

        uint256 debt = vault.strategies(address(this)).totalDebt;
        uint256 currentValue = estimatedTotalAssets();
        uint256 wantBalance = balanceOfWant();

        // we check against estimatedTotalAssets
        if (debt < currentValue) {
            //profit
            _profit = currentValue.sub(debt);
            // NOTE: the strategy will only be able to serve profit payment up to buffer amount
            // we limit profit and try to delay its reporting until there is enough unlocked want to repay it to the vault
            _profit = Math.min(wantBalance, _profit);
        } else {
            _loss = debt.sub(currentValue);
        }

        uint256 toFree = _debtPayment.add(_profit);
        // if the strategy needs to exchange synth into sUSD, the waiting period will kick in and the vault.report will revert !!!
        // this only works if the strategy has been previously unwinded using manual function
        // otherwise, max amount "toFree" is wantBalance
        if (toFree > wantBalance) {
            toFree = toFree.sub(wantBalance);

            (, uint256 withdrawalLoss) = withdrawSomeWant(toFree);

            //when we withdraw we can lose money in the withdrawal
            if (withdrawalLoss < _profit) {
                _profit = _profit.sub(withdrawalLoss);
            } else {
                _loss = _loss.add(withdrawalLoss.sub(_profit));
                _profit = 0;
            }

            wantBalance = balanceOfWant();

            if (wantBalance < _profit) {
                _profit = wantBalance;
                _debtPayment = 0;
            } else if (wantBalance < _debtPayment.add(_profit)) {
                _debtPayment = wantBalance.sub(_profit);
            }
        }
    }
}
