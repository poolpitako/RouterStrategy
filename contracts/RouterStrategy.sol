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
    bool internal isOriginal = true;

    constructor(
        address _vault,
        address _yVault,
        string memory _strategyName
    ) public BaseStrategy(_vault) {
        _initializeThis(_yVault, _strategyName);
    }

    event Cloned(address indexed clone);

    function cloneRouter(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _yVault,
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

        RouterStrategy(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _yVault,
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
        string memory _strategyName
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        require(address(yVault) == address(0));
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

    function estimatedTotalAssets()
        public
        view
        virtual
        override
        returns (uint256)
    {
        return balanceOfWant().add(valueOfInvestment());
    }

    function delegatedAssets() external view override returns (uint256) {
        return vault.strategies(address(this)).totalDebt;
    }

    function prepareReturn(uint256 _debtOutstanding)
        internal
        virtual
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {
        uint256 _totalDebt = vault.strategies(address(this)).totalDebt;
        uint256 _totalAsset = estimatedTotalAssets();

        // Estimate the profit we have so far
        if (_totalDebt <= _totalAsset) {
            _profit = _totalAsset.sub(_totalDebt);
        }

        // We take profit and debt
        uint256 _amountFreed;
        (_amountFreed, _loss) = liquidatePosition(
            _debtOutstanding.add(_profit)
        );
        _debtPayment = Math.min(_debtOutstanding, _amountFreed);

        if (_loss > _profit) {
            // Example:
            // debtOutstanding 100, profit 50, _amountFreed 100, _loss 50
            // loss should be 0, (50-50)
            // profit should endup in 0
            _loss = _loss.sub(_profit);
            _profit = 0;
        } else {
            // Example:
            // debtOutstanding 100, profit 50, _amountFreed 140, _loss 10
            // _profit should be 40, (50 profit - 10 loss)
            // loss should end up in be 0
            _profit = _profit.sub(_loss);
            _loss = 0;
        }
    }

    function adjustPosition(uint256 _debtOutstanding)
        internal
        virtual
        override
    {
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
        virtual
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 balance = balanceOfWant();
        if (balance >= _amountNeeded) {
            return (_amountNeeded, 0);
        }

        uint256 toWithdraw = _amountNeeded.sub(balance);
        _withdrawFromYVault(toWithdraw);

        uint256 looseWant = balanceOfWant();
        if (_amountNeeded > looseWant) {
            _liquidatedAmount = looseWant;
            _loss = _amountNeeded.sub(looseWant);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    function _withdrawFromYVault(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        uint256 _balanceOfYShares = yVault.balanceOf(address(this));
        uint256 sharesToWithdraw =
            Math.min(_investmentTokenToYShares(_amount), _balanceOfYShares);

        if (sharesToWithdraw == 0) {
            return;
        }

        yVault.withdraw(sharesToWithdraw, address(this), maxLoss);
    }

    function liquidateAllPositions()
        internal
        virtual
        override
        returns (uint256 _amountFreed)
    {
        return
            yVault.withdraw(
                yVault.balanceOf(address(this)),
                address(this),
                maxLoss
            );
    }

    function prepareMigration(address _newStrategy) internal virtual override {
        IERC20(yVault).safeTransfer(
            _newStrategy,
            IERC20(yVault).balanceOf(address(this))
        );
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory ret)
    {
        ret = new address[](1);
        ret[0] = address(yVault);
    }

    function ethToWant(uint256 _amtInWei)
        public
        view
        virtual
        override
        returns (uint256)
    {
        return _amtInWei;
    }

    function setMaxLoss(uint256 _maxLoss) public onlyVaultManagers {
        maxLoss = _maxLoss;
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

    function valueOfInvestment() public view virtual returns (uint256) {
        return
            yVault.balanceOf(address(this)).mul(yVault.pricePerShare()).div(
                10**yVault.decimals()
            );
    }
}
