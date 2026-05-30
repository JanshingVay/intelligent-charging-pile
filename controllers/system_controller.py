from datetime import datetime
from typing import Dict, List, Optional
import uuid

from models.areas import WaitingArea, ChargingArea
from models.piles import ChargingPile, PileStatus
from models.entities import (
    User, ElectricVehicle, ChargingRequest, ChargingDetail, FaultRecord,
    RequestStatus, ChargeMode
)
from controllers.scheduling_controller import SchedulingController
from controllers.billing_controller import BillingController
import db


class SystemController:
    """系统主控制器：统一对外提供登录、充电、故障等业务接口。"""

    def __init__(self, waiting_capacity=10, max_queue_length=5):
        db.init_db()
        db.ensure_default_users()

        self.maxQueueLength: int = max_queue_length
        self.waitingArea = WaitingArea(waiting_capacity)
        self.chargingArea = ChargingArea(max_queue_length)
        self.schedulingController = SchedulingController()
        self.billingController = BillingController()

        self.users: Dict[str, User] = {}
        self.faultRecords: List[FaultRecord] = []
        self.chargingDetails: List[ChargingDetail] = []
        self.faultDispatchMode = "priority"  # "priority" or "time"
        self.isAdminMode = False

        self._load_sequence_numbers()
        self._load_pile_stats()
        self._load_fault_records()
        self._load_charging_details()

    def get_user_requests(self, user_id):
        """获取指定用户的所有请求（等候区+充电区+队列）。"""
        requests = []
        for req in self.waitingArea.currentRequests:
            if req.userId == user_id:
                requests.append(req)
        for pile in self.chargingArea.getAllPiles():
            for req in pile.currentQueue:
                if req.userId == user_id:
                    requests.append(req)
            if pile.currentChargingRequest and pile.currentChargingRequest.userId == user_id:
                requests.append(pile.currentChargingRequest)
        return requests

    def get_user_details(self, user_id):
        """获取指定用户的充电详单。"""
        rows = db.load_charging_details(user_id)
        return rows

    def set_fault_dispatch_mode(self, mode):
        """设置故障调度模式：priority（优先级）或 time（时间顺序）。"""
        self.faultDispatchMode = mode
        db.set_system_state("fault_dispatch_mode", mode)

    def _load_sequence_numbers(self):
        fast_seq = db.get_system_state("fast_seq")
        trickle_seq = db.get_system_state("trickle_seq")
        if fast_seq is not None:
            self.schedulingController._fast_seq = int(fast_seq)
        if trickle_seq is not None:
            self.schedulingController._trickle_seq = int(trickle_seq)
        mode = db.get_system_state("fault_dispatch_mode")
        if mode:
            self.faultDispatchMode = mode

    def _save_sequence_numbers(self) -> None:
        db.set_system_state("fast_seq", self.schedulingController._fast_seq)
        db.set_system_state("trickle_seq", self.schedulingController._trickle_seq)

    def _load_pile_stats(self) -> None:
        stats = db.load_pile_stats()
        for pile in self.chargingArea.getAllPiles():
            if pile.pileId in stats:
                s = stats[pile.pileId]
                pile.totalChargeCount = s["total_charge_count"]
                pile.totalChargeDuration = s["total_charge_duration"]
                pile.totalChargePower = s["total_charge_power"]

    def _load_fault_records(self) -> None:
        rows = db.load_fault_records()
        for row in rows:
            record = FaultRecord(
                record_id=row["record_id"],
                pile_id=row["pile_id"],
                fault_time=datetime.fromisoformat(row["fault_time"]),
                fault_reason=row["fault_reason"]
            )
            if row["is_resolved"]:
                record.markResolved()
            self.faultRecords.append(record)

    def _load_charging_details(self) -> None:
        rows = db.load_charging_details()
        for row in rows:
            detail = ChargingDetail(
                detail_id=row["detail_id"],
                pile_id=row["pile_id"],
                energy_amount=row["energy_amount"],
                start_time=datetime.fromisoformat(row["start_time"]),
                stop_time=datetime.fromisoformat(row["stop_time"]),
                charging_fee=row["charging_fee"],
                service_fee=row["service_fee"]
            )
            self.chargingDetails.append(detail)

    def userLogin(self, userId, pwd):
        return db.verify_user(userId, pwd)

    def registerUser(self, userId, pwd, role='user', battery_capacity=60.0):
        if db.register_user(userId, pwd, role):
            user = User(userId, pwd)
            user.vehicle = ElectricVehicle(battery_capacity)
            self.users[userId] = user
            return True
        return False

    def getUserRole(self, userId):
        return db.get_user_role(userId)

    def getAllUsers(self):
        return db.get_all_users()

    def userExists(self, userId: str) -> bool:
        return db.user_exists(userId)

    def _getTotalVehicleCount(self) -> int:
        """统计站点内车辆总数：等候区 + 各桩排队 + 正在充电。"""
        count = len(self.waitingArea.currentRequests)
        for pile in self.chargingArea.getAllPiles():
            count += len(pile.currentQueue)
            if pile.currentChargingRequest is not None:
                count += 1
        return count

    def _getBatchTriggerThreshold(self) -> int:
        """批量调度触发阈值：N + 5*M（等候区容量 + 全部桩队列容量）。"""
        num_piles = len(self.chargingArea.getAllPiles())
        return self.waitingArea.maxCapacity + num_piles * self.maxQueueLength

    def _tryBatchOptimalDispatch(self) -> None:
        """当站点车辆数达到 N+5*M 时，触发批量最优调度。"""
        if self.schedulingController.isCallPaused:
            return
        if not self.waitingArea.currentRequests:
            return
        if self._getTotalVehicleCount() < self._getBatchTriggerThreshold():
            return

        all_reqs = self.waitingArea.currentRequests.copy()
        for req in all_reqs:
            self.waitingArea.removeRequest(req)
        self.schedulingController.calcBatchOptimal(all_reqs, self.chargingArea)

    def _dispatchFromWaitingArea(self) -> None:
        """从等候区叫号至充电区（受 isCallPaused 控制）。"""
        self.schedulingController.dispatchFromWaitingArea(
            self.chargingArea, self.waitingArea
        )

    def _startAllAvailablePiles(self, current_time: datetime) -> None:
        """尝试让所有空闲桩启动队首车辆的充电。"""
        for pile in self.chargingArea.getAllPiles():
            self._tryStartCharging(pile, current_time)

    def submitChargeReq(
        self,
        userId: str,
        chargeMode: str,
        needPower: float,
        current_time: Optional[datetime] = None,
    ) -> Optional[str]:
        if not db.user_exists(userId):
            return None

        req_id = str(uuid.uuid4())[:8]
        if current_time is None:
            current_time = datetime.now()

        queue_num = self.schedulingController.generateQueueNumber(chargeMode)
        req = ChargingRequest(
            request_id=req_id,
            user_id=userId,
            charge_mode=chargeMode,
            need_power=needPower,
            queue_number=queue_num
        )

        # 基础调度：选择总时长最短的桩；无可用桩则进入等候区
        accepted = False
        best_pile = self.schedulingController.findBestPileForRequest(req, self.chargingArea)
        if best_pile:
            self.schedulingController.dispatchToPile(req, best_pile)
            self._tryStartCharging(best_pile, current_time)
            accepted = True
        elif self.waitingArea.checkCapacity():
            self.waitingArea.addRequest(req)
            self._tryBatchOptimalDispatch()
            accepted = True

        if not accepted:
            return None

        self._save_sequence_numbers()

        # 叫号服务：将等候区车辆调度至充电区
        if not self.schedulingController.isCallPaused:
            self._dispatchFromWaitingArea()
            self._startAllAvailablePiles(current_time)

        return req_id

    def _tryStartCharging(self, pile: ChargingPile, current_time: datetime) -> None:
        if pile.status == PileStatus.AVAILABLE.value and len(pile.currentQueue) > 0:
            req = pile.currentQueue.pop(0)
            req.status = RequestStatus.CHARGING.value
            req.startTime = current_time
            req.pileId = pile.pileId
            pile.currentChargingRequest = req
            pile.chargeStartTime = current_time
            pile.startCharging()

    def modifyChargeReq(
        self,
        reqId: str,
        optType: str,
        chargeMode: str,
        needPower: float,
        current_time: Optional[datetime] = None,
    ) -> None:
        if current_time is None:
            current_time = datetime.now()

        req = self.waitingArea.getRequestById(reqId)
        if req:
            if optType == "mode":
                # 等候区修改模式：重新生成排队号，排至新模式队尾
                self.waitingArea.removeRequest(req)
                new_queue_num = self.schedulingController.generateQueueNumber(chargeMode)
                self._save_sequence_numbers()
                req.updateModeAndQueue(chargeMode, new_queue_num)
                best_pile = self.schedulingController.findBestPileForRequest(req, self.chargingArea)
                if best_pile:
                    self.schedulingController.dispatchToPile(req, best_pile)
                else:
                    self.waitingArea.addRequest(req)
            elif optType == "power":
                # 等候区修改电量：保留原排队号
                req.updateNeedPower(needPower)

            self._dispatchFromWaitingArea()
            self._startAllAvailablePiles(current_time)
            return

        # 充电区排队中（尚未开始充电）仅允许修改电量
        req = self.chargingArea.getRequestFromQueue(reqId)
        if req and req.status == RequestStatus.WAITING.value:
            if optType == "power":
                req.updateNeedPower(needPower)

    def cancelChargeReq(self, reqId: str, current_time: Optional[datetime] = None) -> None:
        if current_time is None:
            current_time = datetime.now()

        req = self.waitingArea.getRequestById(reqId)
        if req:
            req.status = RequestStatus.CANCELLED.value
            self.waitingArea.removeRequest(req)
            return

        req = self.chargingArea.getRequestFromQueue(reqId)
        if req:
            req.status = RequestStatus.CANCELLED.value
            self.chargingArea.removeRequestFromQueue(req)
            return

        # 充电区取消：立刻结算已充费用并释放充电桩
        for pile in self.chargingArea.getAllPiles():
            if pile.currentChargingRequest and pile.currentChargingRequest.requestId == reqId:
                req = pile.currentChargingRequest
                req.status = RequestStatus.CANCELLED.value

                stop_result = pile.stopCharging(current_time)
                self._save_pile_stats(pile)
                if stop_result["powerUsed"] > 0:
                    charge_data = {
                        "pileId": pile.pileId,
                        "startTime": pile.chargeStartTime,
                        "stopTime": current_time,
                        "powerUsed": stop_result["powerUsed"]
                    }
                    detail = self.billingController.calculateFee(charge_data)
                    if detail:
                        detail.userId = req.userId
                        self.chargingDetails.append(detail)
                        db.save_charging_detail(detail, req.userId)

                self._tryStartCharging(pile, current_time)
                self._dispatchFromWaitingArea()
                self._startAllAvailablePiles(current_time)
                break

    def finishCharge(self, pileId: str, current_time: Optional[datetime] = None) -> None:
        if current_time is None:
            current_time = datetime.now()

        pile = self.chargingArea.getPileById(pileId)
        if not pile or pile.status != PileStatus.CHARGING.value:
            return

        req = pile.currentChargingRequest
        if req:
            req.status = RequestStatus.COMPLETED.value

            stop_result = pile.stopCharging(current_time)
            self._save_pile_stats(pile)
            charge_data = {
                "pileId": pile.pileId,
                "startTime": pile.chargeStartTime,
                "stopTime": current_time,
                "powerUsed": stop_result["powerUsed"]
            }
            detail = self.billingController.calculateFee(charge_data)
            if detail:
                detail.userId = req.userId
                self.chargingDetails.append(detail)
                db.save_charging_detail(detail, req.userId)

            self._tryStartCharging(pile, current_time)
            self._dispatchFromWaitingArea()
            self._startAllAvailablePiles(current_time)

    def _save_pile_stats(self, pile: ChargingPile) -> None:
        db.save_pile_stats(
            pile.pileId,
            pile.totalChargeCount,
            pile.totalChargeDuration,
            pile.totalChargePower
        )

    def catchFault(
        self,
        pileId: str,
        faultInfo: str,
        current_time: Optional[datetime] = None,
        dispatch_strategy: str = "priority",
    ) -> None:
        """
        故障上报：停止当前车辆计费、生成部分详单，并执行重调度。
        dispatch_strategy: 'priority' 优先级调度 | 'time_seq' 时间顺序调度
        """
        if current_time is None:
            current_time = datetime.now()

        pile = self.chargingArea.getPileById(pileId)
        if not pile:
            return

        pile.setStatus(PileStatus.FAULT.value)

        record_id = str(uuid.uuid4())[:8]
        fault_record = FaultRecord(
            record_id=record_id,
            pile_id=pileId,
            fault_time=current_time,
            fault_reason=faultInfo
        )
        self.faultRecords.append(fault_record)
        db.save_fault_record(fault_record)

        if pile.currentChargingRequest:
            stop_result = pile.stopCharging(current_time)
            self._save_pile_stats(pile)
            if stop_result["powerUsed"] > 0:
                charge_data = {
                    "pileId": pile.pileId,
                    "startTime": pile.chargeStartTime,
                    "stopTime": current_time,
                    "powerUsed": stop_result["powerUsed"]
                }
                detail = self.billingController.calculateFee(charge_data)
                if detail:
                    self.chargingDetails.append(detail)
                    db.save_charging_detail(detail)

        if dispatch_strategy == "time_seq":
            self.schedulingController.handleTimeSeqDispatch(
                pileId, self.chargingArea, self.waitingArea
            )
        else:
            self.schedulingController.handlePriorityDispatch(
                pileId, self.chargingArea, self.waitingArea
            )

        self._dispatchFromWaitingArea()
        self._startAllAvailablePiles(current_time)

    def resolveFault(self, pileId: str, current_time: Optional[datetime] = None) -> None:
        if current_time is None:
            current_time = datetime.now()

        pile = self.chargingArea.getPileById(pileId)
        if not pile or pile.status != PileStatus.FAULT.value:
            return

        for record in self.faultRecords:
            if record.pileId == pileId and not record.isResolved:
                record.markResolved()
                db.update_fault_resolved(record.recordId)
                break

        pile.setStatus(PileStatus.AVAILABLE.value)

        mode = ChargeMode.FAST.value if pileId.startswith('F') else ChargeMode.TRICKLE.value
        self.schedulingController.handleRecoveryDispatch(
            mode, self.chargingArea, self.waitingArea
        )
        self._dispatchFromWaitingArea()
        self._startAllAvailablePiles(current_time)

    def triggerMultiSpotOptimal(self, count: int, mode: str, current_time: Optional[datetime] = None) -> None:
        """触发单次多桩最优调度。"""
        if current_time is None:
            current_time = datetime.now()
        self.schedulingController.calcMultiSpotOptimal(
            count, mode, self.chargingArea, self.waitingArea
        )
        self._dispatchFromWaitingArea()
        self._startAllAvailablePiles(current_time)

    def triggerBatchOptimal(self) -> None:
        """触发批量最优调度。"""
        all_reqs = self.waitingArea.currentRequests.copy()
        for req in all_reqs:
            self.waitingArea.removeRequest(req)
        self.schedulingController.calcBatchOptimal(all_reqs, self.chargingArea)
