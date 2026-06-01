
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
        单次调度总时长最短（需求 8a）：
        充电区出现多个空位时，一次叫多个号。
        穷举车辆与空桩的分配排列，使所有车 (wait_time + charge_time) 之和最小。
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

        for perm in permutations(candidates):
            current_total = 0.0
            assignment: List[Tuple[ChargingRequest, ChargingPile]] = []
            for i, req in enumerate(perm):
                if i < len(available_piles):
                    pile_time = self._calculate_pile_time(available_piles[i], req)
                    current_total += pile_time
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
        批量调度总时长最短（需求 8b）：
        忽略快慢充模式限制，贪心分配使总时长最短。
        策略：按需求电量降序，各车依次选当前累计时间最短的桩。
        """
        all_piles = charging_area.getAllPiles()
        available_piles = [p for p in all_piles if p.status != PileStatus.FAULT.value]
        if not available_piles or not allReqs:
            return

        allReqs.sort(key=lambda x: x.needPower, reverse=True)

        # 每桩当前累计时间
        pile_times = {p.pileId: p.getQueueWaitTime() for p in available_piles}

        for req in allReqs:
            best_pile = None
            best_time = float('inf')
            for pile in available_piles:
                if not pile.canAddToQueue():
                    continue
                charge_time = req.needPower / pile.power
                total = pile_times[pile.pileId] + charge_time
                if total < best_time:
                    best_time = total
                    best_pile = pile
            if best_pile:
                pile_times[best_pile.pileId] = best_time
                req.pileId = best_pile.pileId
                req.status = RequestStatus.WAITING.value
                best_pile.currentQueue.append(req)

    def dispatchFromWaitingArea(
        self, charging_area: ChargingArea, waiting_area: WaitingArea
    ) -> None:
        """
        需求：逐桩检查队列空位，发现空位立即叫匹配模式（F/T）等候区第一辆车加入该桩。
        """
        if self.isCallPaused:
            return

        for pile in charging_area.getAllPiles():
            if pile.status == PileStatus.FAULT.value:
                continue
            if not pile.canAddToQueue():
                continue

            mode = ChargeMode.FAST.value if pile.pileId.startswith('F') else ChargeMode.TRICKLE.value

            matching_reqs = [
                req for req in waiting_area.currentRequests
                if req.chargeMode == mode
            ]
            if not matching_reqs:
                continue

            # 按排队号排序，取第一个
            matching_reqs.sort(key=lambda x: x.queueNumber.generateTime)
            req = matching_reqs[0]

            waiting_area.removeRequest(req)
            self.dispatchToPile(req, pile)

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
