
from typing import List, Optional

from models.entities import ChargeMode
from models.piles import FastChargingPile, TrickleChargingPile, ChargingPile, PileStatus
from models.entities import ChargingRequest


class WaitingArea:
    def __init__(self, max_capacity: int = 10) -> None:
        self.maxCapacity: int = max_capacity
        self.currentRequests: List[ChargingRequest] = []

    def checkCapacity(self) -> bool:
        return len(self.currentRequests) < self.maxCapacity

    def addRequest(self, req: ChargingRequest) -> None:
        if self.checkCapacity():
            self.currentRequests.append(req)

    def removeRequest(self, req: ChargingRequest) -> None:
        if req in self.currentRequests:
            self.currentRequests.remove(req)

    def getWaitCount(self, charge_mode: str) -> int:
        count = 0
        for req in self.currentRequests:
            if req.chargeMode == charge_mode:
                count += 1
        return count

    def getRequestById(self, req_id: str) -> Optional[ChargingRequest]:
        for req in self.currentRequests:
            if req.requestId == req_id:
                return req
        return None


class ChargingArea:
    def __init__(self, max_queue_length: int = 5) -> None:
        self.piles: List[ChargingPile] = []
        self._init_piles(max_queue_length)

    def _init_piles(self, max_queue_length: int) -> None:
        for i in range(3):
            self.piles.append(FastChargingPile("F%d" % (i + 1), max_queue_length))
        for i in range(2):
            self.piles.append(TrickleChargingPile("T%d" % (i + 1), max_queue_length))

    def findIdlePile(self, charge_mode: str) -> Optional[ChargingPile]:
        for pile in self.piles:
            if pile.status == PileStatus.AVAILABLE.value:
                if (charge_mode == ChargeMode.FAST.value and isinstance(pile, FastChargingPile)) or \
                   (charge_mode == ChargeMode.TRICKLE.value and isinstance(pile, TrickleChargingPile)):
                    return pile
        return None

    def getAllPiles(self) -> List[ChargingPile]:
        return self.piles

    def getPileById(self, pile_id: str) -> Optional[ChargingPile]:
        for pile in self.piles:
            if pile.pileId == pile_id:
                return pile
        return None

    def getPilesByMode(self, charge_mode: str) -> List[ChargingPile]:
        result: List[ChargingPile] = []
        for pile in self.piles:
            if (charge_mode == ChargeMode.FAST.value and isinstance(pile, FastChargingPile)) or \
               (charge_mode == ChargeMode.TRICKLE.value and isinstance(pile, TrickleChargingPile)):
                result.append(pile)
        return result

    def getRequestFromQueue(self, req_id: str) -> Optional[ChargingRequest]:
        for pile in self.piles:
            for req in pile.currentQueue:
                if req.requestId == req_id:
                    return req
        return None

    def removeRequestFromQueue(self, req: ChargingRequest) -> None:
        for pile in self.piles:
            if req in pile.currentQueue:
                pile.currentQueue.remove(req)
                break
