// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title ProofPayEscrow
/// @notice Fund-first milestone escrow in the chain's native coin. The client locks the full amount when
///         creating the contract (for a named worker, or an open job any worker can accept). A VERIFIER
///         attests test results (evidence hash on-chain); each milestone has its own review window.
contract ProofPayEscrow is AccessControl, ReentrancyGuard, Pausable {
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");
    bytes32 public constant ARBITRATOR_ROLE = keccak256("ARBITRATOR_ROLE");
    uint8 public constant MAX_MILESTONES = 20;
    uint64 public constant MIN_WINDOW = 1 hours;
    uint64 public constant MAX_WINDOW = 30 days;

    uint64 public immutable refundGrace;

    enum S { Funded, Passed, Disputed, Released, Refunded }

    struct Milestone {
        uint128 amount;
        uint64 deadline;
        uint64 window;
        uint64 passedAt;
        S status;
        bytes32 evidence;
    }

    struct Escrow {
        address client;
        address freelancer; // address(0) while an open job has no worker
        bool accepted;
        bool cancelled;
        bool cancelRequested;
        bytes32 contractHash;
        bytes32 hiddenTestsHash;
    }

    mapping(bytes32 => Escrow) public escrows;
    mapping(bytes32 => Milestone[]) private _ms;

    event EscrowCreated(bytes32 indexed id, address indexed client, address indexed freelancer, bytes32 contractHash, bytes32 hiddenTestsHash, uint256 total);
    event Accepted(bytes32 indexed id, address indexed freelancer);
    event Cancelled(bytes32 indexed id, uint256 refunded);
    event CancelRequested(bytes32 indexed id);
    event CancelWithdrawn(bytes32 indexed id);
    event CancelAgreed(bytes32 indexed id, uint256 refunded);
    event Attested(bytes32 indexed id, uint256 indexed idx, bytes32 evidence, bool passed);
    event Released(bytes32 indexed id, uint256 indexed idx, address to, uint256 amount);
    event Disputed(bytes32 indexed id, uint256 indexed idx, bytes32 reasonHash);
    event Resolved(bytes32 indexed id, uint256 indexed idx, uint16 freelancerBps);
    event Refunded(bytes32 indexed id, uint256 indexed idx, uint256 amount);

    error Unauthorized();
    error BadState();
    error BadInput();
    error TransferFailed();

    constructor(address admin, address verifier, address arbitrator, uint64 refundGrace_) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(VERIFIER_ROLE, verifier);
        _grantRole(ARBITRATOR_ROLE, arbitrator);
        refundGrace = refundGrace_;
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) { _pause(); }
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) { _unpause(); }

    // ---------- setup ----------

    /// Locks msg.value (must equal the sum of milestone amounts). freelancer == address(0) makes an open job.
    function createEscrow(
        bytes32 id,
        address freelancer,
        bytes32 contractHash,
        bytes32 hiddenTestsHash,
        uint128[] calldata amounts,
        uint64[] calldata deadlines,
        uint64[] calldata windows
    ) external payable whenNotPaused {
        if (escrows[id].client != address(0)) revert BadState();
        uint256 n = amounts.length;
        if (n == 0 || n > MAX_MILESTONES || n != deadlines.length || n != windows.length) revert BadInput();
        if (freelancer == msg.sender) revert BadInput();
        uint256 sum;
        for (uint256 i; i < n; i++) {
            if (amounts[i] == 0 || deadlines[i] <= block.timestamp) revert BadInput();
            if (windows[i] < MIN_WINDOW || windows[i] > MAX_WINDOW) revert BadInput();
            sum += amounts[i];
            _ms[id].push(Milestone(amounts[i], deadlines[i], windows[i], 0, S.Funded, bytes32(0)));
        }
        if (msg.value != sum) revert BadInput();
        escrows[id] = Escrow(msg.sender, freelancer, false, false, false, contractHash, hiddenTestsHash);
        emit EscrowCreated(id, msg.sender, freelancer, contractHash, hiddenTestsHash, sum);
    }

    /// The named worker accepts; on an open job any account except the client may take it.
    function acceptContract(bytes32 id) external whenNotPaused {
        Escrow storage e = escrows[id];
        if (e.client == address(0) || e.accepted || e.cancelled) revert BadState();
        if (msg.sender == e.client) revert Unauthorized();
        if (e.freelancer == address(0)) e.freelancer = msg.sender;
        else if (msg.sender != e.freelancer) revert Unauthorized();
        e.accepted = true;
        emit Accepted(id, msg.sender);
    }

    /// Free cancel until someone accepts: the full amount returns to the client.
    function revoke(bytes32 id) external nonReentrant {
        Escrow storage e = escrows[id];
        if (msg.sender != e.client) revert Unauthorized();
        if (e.accepted || e.cancelled) revert BadState();
        e.cancelled = true;
        uint256 refunded = _refundOpen(id);
        emit Cancelled(id, refunded);
        _send(e.client, refunded);
    }

    /// After acceptance, cancelling needs the worker's agreement.
    function requestCancel(bytes32 id) external whenNotPaused {
        Escrow storage e = escrows[id];
        if (msg.sender != e.client) revert Unauthorized();
        if (!e.accepted || e.cancelled || e.cancelRequested) revert BadState();
        e.cancelRequested = true;
        emit CancelRequested(id);
    }

    function withdrawCancel(bytes32 id) external {
        Escrow storage e = escrows[id];
        if (msg.sender != e.client) revert Unauthorized();
        if (!e.cancelRequested || e.cancelled) revert BadState();
        e.cancelRequested = false;
        emit CancelWithdrawn(id);
    }

    function acceptCancel(bytes32 id) external nonReentrant {
        Escrow storage e = escrows[id];
        if (msg.sender != e.freelancer) revert Unauthorized();
        if (!e.cancelRequested || e.cancelled) revert BadState();
        e.cancelled = true;
        e.cancelRequested = false;
        uint256 refunded = _refundOpen(id);
        emit CancelAgreed(id, refunded);
        _send(e.client, refunded);
    }

    // ---------- verification and release ----------

    function attest(bytes32 id, uint256 idx, bytes32 evidence, bool passed) external onlyRole(VERIFIER_ROLE) whenNotPaused {
        Milestone storage m = _live(id, idx);
        if (m.status != S.Funded) revert BadState();
        m.evidence = evidence;
        if (passed) {
            m.status = S.Passed;
            m.passedAt = uint64(block.timestamp);
        }
        emit Attested(id, idx, evidence, passed);
    }

    /// Client accepts the work early ("I received it").
    function approve(bytes32 id, uint256 idx) external nonReentrant whenNotPaused {
        Escrow storage e = escrows[id];
        if (msg.sender != e.client) revert Unauthorized();
        Milestone storage m = _live(id, idx);
        if (m.status != S.Funded && m.status != S.Passed) revert BadState();
        _release(id, idx, m, e.freelancer);
    }

    /// Anyone can finalize once the milestone's review window has passed without a dispute.
    function finalize(bytes32 id, uint256 idx) external nonReentrant whenNotPaused {
        Milestone storage m = _live(id, idx);
        if (m.status != S.Passed || block.timestamp < m.passedAt + m.window) revert BadState();
        _release(id, idx, m, escrows[id].freelancer);
    }

    function dispute(bytes32 id, uint256 idx, bytes32 reasonHash) external whenNotPaused {
        if (msg.sender != escrows[id].client) revert Unauthorized();
        Milestone storage m = _live(id, idx);
        if (m.status != S.Passed || block.timestamp >= m.passedAt + m.window) revert BadState();
        m.status = S.Disputed;
        emit Disputed(id, idx, reasonHash);
    }

    function resolve(bytes32 id, uint256 idx, uint16 freelancerBps) external nonReentrant onlyRole(ARBITRATOR_ROLE) {
        if (freelancerBps > 10_000) revert BadInput();
        if (idx >= _ms[id].length) revert BadState();
        Milestone storage m = _ms[id][idx];
        if (m.status != S.Disputed) revert BadState();
        m.status = S.Released;
        uint256 toFreelancer = (uint256(m.amount) * freelancerBps) / 10_000;
        uint256 toClient = m.amount - toFreelancer;
        emit Resolved(id, idx, freelancerBps);
        if (toFreelancer > 0) _send(escrows[id].freelancer, toFreelancer);
        if (toClient > 0) _send(escrows[id].client, toClient);
    }

    /// Client reclaims a milestone that was never verified before deadline + grace.
    function refundExpired(bytes32 id, uint256 idx) external nonReentrant {
        Escrow storage e = escrows[id];
        if (msg.sender != e.client) revert Unauthorized();
        Milestone storage m = _live(id, idx);
        if (m.status != S.Funded || block.timestamp < m.deadline + refundGrace) revert BadState();
        m.status = S.Refunded;
        emit Refunded(id, idx, m.amount);
        _send(e.client, m.amount);
    }

    // ---------- views ----------

    function total(bytes32 id) public view returns (uint256 t) {
        Milestone[] storage ms = _ms[id];
        for (uint256 i; i < ms.length; i++) t += ms[i].amount;
    }

    function getMilestones(bytes32 id) external view returns (Milestone[] memory) {
        return _ms[id];
    }

    // ---------- internals ----------

    /// Milestone of an accepted, not-cancelled escrow.
    function _live(bytes32 id, uint256 idx) private view returns (Milestone storage) {
        Escrow storage e = escrows[id];
        if (!e.accepted || e.cancelled || idx >= _ms[id].length) revert BadState();
        return _ms[id][idx];
    }

    /// Marks every unsettled (Funded/Passed) milestone refunded and returns the sum.
    function _refundOpen(bytes32 id) private returns (uint256 sum) {
        Milestone[] storage ms = _ms[id];
        for (uint256 i; i < ms.length; i++) {
            if (ms[i].status == S.Funded || ms[i].status == S.Passed) {
                ms[i].status = S.Refunded;
                sum += ms[i].amount;
                emit Refunded(id, i, ms[i].amount);
            }
        }
    }

    function _release(bytes32 id, uint256 idx, Milestone storage m, address to) private {
        m.status = S.Released;
        emit Released(id, idx, to, m.amount);
        _send(to, m.amount);
    }

    function _send(address to, uint256 amount) private {
        (bool ok, ) = to.call{value: amount}("");
        if (!ok) revert TransferFailed();
    }
}
