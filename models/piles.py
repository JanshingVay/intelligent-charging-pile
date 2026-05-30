
from datetime import datetime
from typing import Dict, List, Optional

from models.entities import ChargingRequest, PileStatus


class ChargingPile:
    def __init__(self, pile_id: str, power: float, max_queue_length: int = 5) -> None:
        self.pileId: str = pile_id
        self.status: str = PileStatus.AVAILABLE.value
        self.totalChargeCount: int = 0
        self.totalChargeDuration: float = 0.0
        self.totalChargePower: float = 0.0
        self.currentQueue: List[ChargingRequest] = []
        self.power: float = power
        self.maxQueueLength: int = max_queue_length
        self.currentChargingRequest: Optional[ChargingRequest] = None
        self.chargeStartTime: Optional[datetime] = None

    def startCharging(self) -> None:
        self.status = PileStatus.CHARGING.value

    def stopCharging(self, current_time: datetime) -> Dict[str, float]:
        if self.status != PileStatus.CHARGING.value or not self.chargeStartTime:
            return {"duration": 0.0, "powerUsed": 0.0}

        duration_hours = (current_time - self.chargeStartTime).total_seconds() / 3600
        power_used = duration_hours * self.power

        self.totalChargeCount += 1
        self.totalChargeDuration += duration_hours
        self.totalChargePower += power_used

        self.status = PileStatus.AVAILABLE.value
        self.currentChargingRequest = None
        self.chargeStartTime = None

        return {"duration": duration_hours, "powerUsed": power_used}

    def setStatus(self, new_status: str) -> None:
        self.status = new_status

    def getQueueWaitTime(self) -> float:
        """队列中所有车辆完成充电所需时间之和。"""
        total_time = 0.0
        for req in self.currentQueue:
            total_time += req.needPower / self.power
        return total_time

    def canAddToQueue(self) -> bool:
        return len(self.currentQueue) < self.maxQueueLength


class FastChargingPile(ChargingPile):
    def __init__(self, pile_id: str, max_queue_length: int = 5) -> None:
        super(FastChargingPile, self).__init__(pile_id, power=30.0, max_queue_length=max_queue_length)


class TrickleChargingPile(ChargingPile):
    def __init__(self, pile_id: str, max_queue_length: int = 5) -> None:
        super(TrickleChargingPile, self).__init__(pile_id, power=10.0, max_queue_length=max_queue_length)
