
from datetime import datetime
from enum import Enum
from typing import Optional

from config import (
    PEAK_PRICE, NORMAL_PRICE, VALLEY_PRICE,
    PEAK_HOURS, NORMAL_HOURS, VALLEY_HOURS,
    SERVICE_FEE
)


class ChargeMode(Enum):
    FAST = "Fast"
    TRICKLE = "Trickle"


class PileStatus(Enum):
    AVAILABLE = "Available"
    CHARGING = "Charging"
    FAULT = "Fault"


class RequestStatus(Enum):
    WAITING = "Waiting"
    CHARGING = "Charging"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    RESCHEDULING = "ReScheduling"


class User:
    def __init__(self, user_id: str, password: str) -> None:
        self.userId: str = user_id
        self.password: str = password
        self.vehicle: Optional["ElectricVehicle"] = None


class ElectricVehicle:
    def __init__(self, battery_capacity: float) -> None:
        self.batteryCapacity: float = battery_capacity


class QueueNumber:
    def __init__(self, prefix: str, sequence_num: int, generate_time: datetime) -> None:
        self.prefix: str = prefix
        self.sequenceNum: int = sequence_num
        self.generateTime: datetime = generate_time

    def getQueueString(self) -> str:
        return "%s%s" % (self.prefix, self.sequenceNum)


class ChargingRequest:
    def __init__(
        self,
        request_id: str,
        user_id: str,
        charge_mode: str,
        need_power: float,
        queue_number: QueueNumber,
    ) -> None:
        self.requestId: str = request_id
        self.userId: str = user_id
        self.chargeMode: str = charge_mode
        self.needPower: float = need_power
        self.status: str = RequestStatus.WAITING.value
        self.queueNumber: QueueNumber = queue_number
        self.startTime: Optional[datetime] = None
        self.pileId: Optional[str] = None

    def updateModeAndQueue(self, new_mode: str, new_queue_num: QueueNumber) -> None:
        self.chargeMode = new_mode
        self.queueNumber = new_queue_num

    def updateNeedPower(self, new_power: float) -> None:
        self.needPower = new_power


class ChargingDetail:
    def __init__(
        self,
        detail_id: str,
        pile_id: str,
        energy_amount: float,
        start_time: datetime,
        stop_time: datetime,
        charging_fee: float,
        service_fee: float,
        user_id: str = 'unknown',
    ) -> None:
        self.detailId: str = detail_id
        self.pileId: str = pile_id
        self.userId: str = user_id
        self.energyAmount: float = energy_amount
        self.startTime: datetime = start_time
        self.stopTime: datetime = stop_time
        self.chargingFee: float = charging_fee
        self.serviceFee: float = service_fee
        self.totalFee: float = charging_fee + service_fee


class FaultRecord:
    def __init__(
        self,
        record_id: str,
        pile_id: str,
        fault_time: datetime,
        fault_reason: str,
    ) -> None:
        self.recordId: str = record_id
        self.pileId: str = pile_id
        self.faultTime: datetime = fault_time
        self.faultReason: str = fault_reason
        self.isResolved: bool = False

    def markResolved(self) -> None:
        self.isResolved = True


class BillingRule:
    @staticmethod
    def get_price_per_kwh(current_time: datetime) -> float:
        hour = current_time.hour
        for start, end in PEAK_HOURS:
            if start <= hour < end:
                return PEAK_PRICE
        for start, end in NORMAL_HOURS:
            if start <= hour < end:
                return NORMAL_PRICE
        for start, end in VALLEY_HOURS:
            if start <= hour < end:
                return VALLEY_PRICE
        return NORMAL_PRICE

    @staticmethod
    def get_service_fee() -> float:
        return SERVICE_FEE
