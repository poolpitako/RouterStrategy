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

interface IVault is IERC20 {
    function token() external view returns (address);

    function decimals() external view returns (uint256);

    function deposit() external;

    function pricePerShare() external view returns (uint256);

    function withdraw(
        uint256 amount,
        address account,
        uint256 maxLoss
    ) external returns (uint256);
}

contract RouterStrategy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    string internal strategyName;
    IVault public yVault;
    uint256 public maxLoss;

    constructor(
        address _vault,
        address _yVault,
        string memory _strategyName
    ) public BaseStrategy(_vault) {
        _initializeThis(_yVault, _strategyName);
    }

    function _initializeThis(address _yVault, string memory _strategyName)
        internal
    {
        yVault = IVault(_yVault);
        strategyName = _strategyName;
    }

    function name() external view override returns (string memory) {
        return strategyName;
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return balanceOfWant().add(valueOfInvestment());
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
        uint256 balanceInit = balanceOfWant();
        _takeVaultProfit();
        uint256 balanceOfWant = balanceOfWant();

        if (balanceOfWant > balanceInit) {
            _profit = balanceOfWant.sub(balanceInit);
        }

        // if the vault is claiming repayment of debt
        if (_debtOutstanding > 0) {
            uint256 _amountFreed = 0;
            (_amountFreed, _loss) = liquidatePosition(_debtOutstanding);
            _debtPayment = Math.min(_debtOutstanding, _amountFreed);
            if (_loss > 0) {
                _profit = 0;
            }
        }
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }

        uint256 balance = balanceOfWant();
        if (balance > 0) {
            _checkAllowance(address(yVault), address(want), balance);
            yVault.deposit();
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 balance = balanceOfWant();
        if (balance >= _amountNeeded) {
            return (_amountNeeded, 0);
        }

        uint256 toWithdraw = _amountNeeded.sub(balance);
        _withdrawFromYVault(toWithdraw);

        uint256 totalAssets = want.balanceOf(address(this));
        if (_amountNeeded > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amountNeeded.sub(totalAssets);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    function _withdrawFromYVault(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        uint256 sharesToWithdraw =
            Math.min(
                _investmentTokenToYShares(_amount),
                yVault.balanceOf(address(this))
            );
        if (sharesToWithdraw == 0) {
            return;
        }

        yVault.withdraw(sharesToWithdraw, address(this), maxLoss);
    }

    function liquidateAllPositions()
        internal
        override
        returns (uint256 _amountFreed)
    {
        (_amountFreed, ) = liquidatePosition(
            vault.strategies(address(this)).totalDebt
        );
    }

    function prepareMigration(address _newStrategy) internal override {
        IERC20(yVault).safeTransfer(
            _newStrategy,
            IERC20(yVault).balanceOf(address(this))
        );
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}

    function ethToWant(uint256 _amtInWei)
        public
        view
        virtual
        override
        returns (uint256)
    {
        return _amtInWei;
    }

    function setMaxLoss(uint256 _maxLoss) public onlyEmergencyAuthorized {
        maxLoss = _maxLoss;
    }

    function _takeVaultProfit() internal {
        uint256 _debt = vault.strategies(address(this)).totalDebt;
        uint256 _valueInVault = valueOfInvestment();
        if (_debt >= _valueInVault) {
            return;
        }

        uint256 _profit = _valueInVault.sub(_debt);
        uint256 _ySharesToWithdraw = _investmentTokenToYShares(_profit);
        if (_ySharesToWithdraw > 0) {
            yVault.withdraw(_ySharesToWithdraw, address(this), maxLoss);
        }
    }

    function _checkAllowance(
        address _contract,
        address _token,
        uint256 _amount
    ) internal {
        if (IERC20(_token).allowance(address(this), _contract) < _amount) {
            IERC20(_token).safeApprove(_contract, 0);
            IERC20(_token).safeApprove(_contract, type(uint256).max);
        }
    }

    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function _investmentTokenToYShares(uint256 amount)
        internal
        view
        returns (uint256)
    {
        return amount.mul(10**yVault.decimals()).div(yVault.pricePerShare());
    }

    function valueOfInvestment() public view returns (uint256) {
        return
            yVault.balanceOf(address(this)).mul(yVault.pricePerShare()).div(
                10**yVault.decimals()
            );
    }
}
