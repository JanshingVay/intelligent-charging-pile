
from typing import Any, Dict, List

from models.piles import ChargingPile
from models.entities import ChargingDetail, FaultRecord


class SystemReport:
    def __init__(self) -> None:
        pass

    @staticmethod
    def generatePileReport(piles: List[ChargingPile]) -> Dict[str, Any]:
        report: Dict[str, Any] = {"piles": []}
        for pile in piles:
            pile_info = {
                "pileId": pile.pileId,
                "pile_id": pile.pileId,
                "status": pile.status,
                "totalChargeCount": pile.totalChargeCount,
                "total_charge_count": pile.totalChargeCount,
                "totalChargeDuration": round(pile.totalChargeDuration, 2),
                "total_charge_duration": round(pile.totalChargeDuration, 2),
                "totalChargePower": round(pile.totalChargePower, 2),
                "total_charge_power": round(pile.totalChargePower, 2),
                "queueLength": len(pile.currentQueue),
                "queue_length": len(pile.currentQueue)
            }
            report["piles"].append(pile_info)
        return report

    @staticmethod
    def generateBillingReport(details: List[ChargingDetail]) -> Dict[str, Any]:
        total_energy = 0.0
        total_charging_fee = 0.0
        total_service_fee = 0.0
        total_fee = 0.0

        for detail in details:
            total_energy += detail.energyAmount
            total_charging_fee += detail.chargingFee
            total_service_fee += detail.serviceFee
            total_fee += detail.totalFee

        return {
            "totalTransactions": len(details),
            "total_transactions": len(details),
            "totalEnergy": round(total_energy, 2),
            "total_energy": round(total_energy, 2),
            "totalChargingFee": round(total_charging_fee, 2),
            "total_charging_fee": round(total_charging_fee, 2),
            "totalServiceFee": round(total_service_fee, 2),
            "total_service_fee": round(total_service_fee, 2),
            "totalFee": round(total_fee, 2),
            "total_fee": round(total_fee, 2)
        }

    @staticmethod
    def generateFaultReport(fault_records: List[FaultRecord]) -> Dict[str, Any]:
        unresolved = 0
        resolved = 0
        pile_faults: Dict[str, int] = {}

        for record in fault_records:
            if record.isResolved:
                resolved += 1
            else:
                unresolved += 1

            if record.pileId in pile_faults:
                pile_faults[record.pileId] += 1
            else:
                pile_faults[record.pileId] = 1

        return {
            "totalFaults": len(fault_records),
            "total_faults": len(fault_records),
            "unresolved": unresolved,
            "resolved": resolved,
            "pileFaultCounts": pile_faults,
            "pile_fault_counts": pile_faults
        }
