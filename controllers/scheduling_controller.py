
from datetime import datetime
from itertools import permutations
from typing import Dict, List, Optional, Tuple

from models.entities import QueueNumber, ChargingRequest, ChargeMode, RequestStatus
from models.piles import ChargingPile, PileStatus
from models.areas import WaitingArea, ChargingArea


class SchedulingController:
    """调度控制器：负责排队号生成、基础调度及故障重调度策略。"""

    def __init__(self) -> None:
        self.isCallPaused: bool = False
        self._fast_seq: int = 0
        self._trickle_seq: int = 0

    def generateQueueNumber(self, mode: str) -> QueueNumber:
        """生成 F/T 开头的排队号码牌。"""
        if mode == ChargeMode.FAST.value:
            self._fast_seq += 1
            prefix = 'F'
            seq = self._fast_seq
        else:
            self._trickle_seq += 1
            prefix = 'T'
            seq = self._trickle_seq
        return QueueNumber(prefix, seq, datetime.now())

    def findBestPileForRequest(
        self, req: ChargingRequest, charging_area: ChargingArea
    ) -> Optional[ChargingPile]:
        """
        基础调度：在同模式充电桩中，选择
        等待时间 + 自身充电时间 最短的桩。
        """
        piles = charging_area.getPilesByMode(req.chargeMode)
        best_pile: Optional[ChargingPile] = None
        min_total_time = float('inf')

        for pile in piles:
            if pile.status != PileStatus.FAULT.value and pile.canAddToQueue():
                wait_time = pile.getQueueWaitTime()
                charge_time = req.needPower / pile.power
                total_time = wait_time + charge_time

                if total_time < min_total_time:
                    min_total_time = total_time
                    best_pile = pile

        return best_pile

    def dispatchToPile(self, req: ChargingRequest, pile: ChargingPile) -> None:
        """将请求加入指定充电桩的排队队列。"""
        req.status = RequestStatus.WAITING.value
        req.pileId = pile.pileId
        pile.currentQueue.append(req)

    def handlePriorityDispatch(
        self, faultPileId: str, charging_area: ChargingArea, waiting_area: WaitingArea
    ) -> None:
        """
        优先级调度（需求 4.1）：
        故障时将故障桩队列中的车辆优先分配到同类型空闲桩，
        无空位则按最短总时长策略入队或退回等候区。
        """
        self.isCallPaused = True
        fault_pile = charging_area.getPileById(faultPileId)
        if not fault_pile:
            self.isCallPaused = False
            return

        mode = ChargeMode.FAST.value if fault_pile.pileId.startswith('F') else ChargeMode.TRICKLE.value
        fault_queue = fault_pile.currentQueue.copy()
        fault_pile.currentQueue.clear()

        for req in fault_queue:
            idle_pile = charging_area.findIdlePile(mode)
            if idle_pile and idle_pile.canAddToQueue():
                self.dispatchToPile(req, idle_pile)
            else:
                best_pile = self.findBestPileForRequest(req, charging_area)
                if best_pile:
                    self.dispatchToPile(req, best_pile)
                else:
                    waiting_area.addRequest(req)

        self.isCallPaused = False

    def handleTimeSeqDispatch(
        self, faultPileId: str, charging_area: ChargingArea, waiting_area: WaitingArea
    ) -> None:
        """
        时间顺序调度（需求 4.2）：
        合并故障桩与其他同类型桩的未充电队列，
        按 QueueNumber 生成时间重新排序后依次分配。
        """
        self.isCallPaused = True
        fault_pile = charging_area.getPileById(faultPileId)
        if not fault_pile:
            self.isCallPaused = False
            return

        mode = ChargeMode.FAST.value if fault_pile.pileId.startswith('F') else ChargeMode.TRICKLE.value
        fault_queue = fault_pile.currentQueue.copy()
        fault_pile.currentQueue.clear()

        all_waiting_reqs: List[ChargingRequest] = fault_queue.copy()
        for pile in charging_area.getPilesByMode(mode):
            if pile.pileId != faultPileId:
                all_waiting_reqs.extend(pile.currentQueue)
                pile.currentQueue.clear()

        all_waiting_reqs.sort(key=lambda x: x.queueNumber.generateTime)

        for req in all_waiting_reqs:
            best_pile = self.findBestPileForRequest(req, charging_area)
            if best_pile:
                self.dispatchToPile(req, best_pile)
            else:
                waiting_area.addRequest(req)

        self.isCallPaused = False

    def handleRecoveryDispatch(
        self, mode: str, charging_area: ChargingArea, waiting_area: WaitingArea
    ) -> None:
        """
        充电中故障恢复调度（需求 4.3）：
        故障桩修复后，收集同类型所有桩的未充电队列，
        按排队号时间顺序重新分配（含修复好的桩）。
        """
        self.isCallPaused = True

        all_waiting_reqs: List[ChargingRequest] = []
        for pile in charging_area.getPilesByMode(mode):
            all_waiting_reqs.extend(pile.currentQueue)
            pile.currentQueue.clear()

        all_waiting_reqs.sort(key=lambda x: x.queueNumber.generateTime)

        for req in all_waiting_reqs:
            best_pile = self.findBestPileForRequest(req, charging_area)
            if best_pile:
                self.dispatchToPile(req, best_pile)
            else:
                waiting_area.addRequest(req)

        self.isCallPaused = False

    def calcMultiSpotOptimal(
        self,
        emptyCount: int,
        mode: str,
        charging_area: ChargingArea,
        waiting_area: WaitingArea,
    ) -> None:
        """
        单次调度总时长最短（需求 5.1）：
        充电区出现多个空位时，一次叫多个号，
        穷举分配组合使完成充电总时长之和最小。
        """
        self.isCallPaused = True

        available_piles: List[ChargingPile] = []
        for pile in charging_area.getPilesByMode(mode):
            if pile.status == PileStatus.AVAILABLE.value and len(pile.currentQueue) == 0:
                available_piles.append(pile)

        mode_reqs = [req for req in waiting_area.currentRequests if req.chargeMode == mode]
        num_to_call = min(emptyCount, len(available_piles), len(mode_reqs))
        if num_to_call <= 0:
            self.isCallPaused = False
            return

        mode_reqs.sort(key=lambda x: x.queueNumber.generateTime)
        candidates = mode_reqs[:num_to_call]

        best_total_time = float('inf')
        best_assignment: List[Tuple[ChargingRequest, ChargingPile]] = []

        # 穷举车辆与空桩的分配排列，选取总充电时长最小的方案
        for perm in permutations(candidates):
            current_total = 0.0
            assignment: List[Tuple[ChargingRequest, ChargingPile]] = []
            for i, req in enumerate(perm):
                if i < len(available_piles):
                    charge_time = req.needPower / available_piles[i].power
                    current_total += charge_time
                    assignment.append((req, available_piles[i]))

            if current_total < best_total_time:
                best_total_time = current_total
                best_assignment = assignment

        for req, pile in best_assignment:
            waiting_area.removeRequest(req)
            self.dispatchToPile(req, pile)

        self.isCallPaused = False

    def calcBatchOptimal(
        self, allReqs: List[ChargingRequest], charging_area: ChargingArea
    ) -> None:
        """
        批量调度总时长最短（需求 5.2）：
        忽略快慢充模式限制，回溯搜索使
        Min(∑(各车等待时间 + 自身充电时间)) 最小的分配方案。
        """
        all_piles = charging_area.getAllPiles()
        available_piles = [p for p in all_piles if p.status != PileStatus.FAULT.value]

        best_total_time = float('inf')
        best_assignment: List[Tuple[ChargingRequest, ChargingPile]] = []

        def backtrack(
            assigned_reqs: List[Tuple[ChargingRequest, ChargingPile]],
            remaining_reqs: List[ChargingRequest],
            total_time: float,
        ) -> None:
            nonlocal best_total_time, best_assignment
            if not remaining_reqs:
                if total_time < best_total_time:
                    best_total_time = total_time
                    best_assignment = assigned_reqs.copy()
                return

            req = remaining_reqs[0]
            for pile in available_piles:
                if len(pile.currentQueue) < pile.maxQueueLength:
                    pile_time = self._calculate_pile_time(pile, req)
                    new_total = total_time + pile_time
                    if new_total >= best_total_time:
                        continue

                    assigned_reqs.append((req, pile))
                    pile.currentQueue.append(req)
                    backtrack(assigned_reqs, remaining_reqs[1:], new_total)
                    pile.currentQueue.pop()
                    assigned_reqs.pop()

        backtrack([], allReqs, 0.0)

        for req, pile in best_assignment:
            req.pileId = pile.pileId
            req.status = RequestStatus.WAITING.value
            if req not in pile.currentQueue:
                pile.currentQueue.append(req)

    def dispatchFromWaitingArea(
        self, charging_area: ChargingArea, waiting_area: WaitingArea
    ) -> None:
        """
        等候区叫号服务：每种模式每次只叫一辆车。
        """
        if self.isCallPaused:
            return

        for mode in (ChargeMode.FAST.value, ChargeMode.TRICKLE.value):
            mode_waiting = [
                req for req in waiting_area.currentRequests if req.chargeMode == mode
            ]
            if not mode_waiting:
                continue

            mode_waiting.sort(key=lambda x: x.queueNumber.generateTime)
            empty_count = self._countFullyAvailablePiles(mode, charging_area)

            if empty_count >= 2:
                self.calcMultiSpotOptimal(empty_count, mode, charging_area, waiting_area)
            else:
                req = mode_waiting[0]
                idle_pile = charging_area.findIdlePile(mode)
                if idle_pile and idle_pile.canAddToQueue():
                    waiting_area.removeRequest(req)
                    self.dispatchToPile(req, idle_pile)
                else:
                    best_pile = self.findBestPileForRequest(req, charging_area)
                    if best_pile:
                        waiting_area.removeRequest(req)
                        self.dispatchToPile(req, best_pile)

    def _countFullyAvailablePiles(self, mode: str, charging_area: ChargingArea) -> int:
        """统计某模式下完全空闲（Available 且无排队）的充电桩数量。"""
        count = 0
        for pile in charging_area.getPilesByMode(mode):
            if pile.status == PileStatus.AVAILABLE.value and len(pile.currentQueue) == 0:
                count += 1
        return count

    def _calculate_pile_time(self, pile: ChargingPile, new_req: ChargingRequest) -> float:
        """计算某请求分配到指定桩的 等待时间 + 充电时间。"""
        wait_time = pile.getQueueWaitTime()
        charge_time = new_req.needPower / pile.power
        return wait_time + charge_time
