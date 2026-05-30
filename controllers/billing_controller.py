
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import uuid

from models.entities import ChargingDetail, BillingRule


class BillingController:
    """计费控制器：按峰平谷分时电价和服务费计算充电详单。"""

    def __init__(self) -> None:
        self.billingRule: BillingRule = BillingRule()

    def calculateFee(self, charge_data: Dict[str, Any]) -> Optional[ChargingDetail]:
        pile_id = charge_data["pileId"]
        start_time = charge_data["startTime"]
        stop_time = charge_data["stopTime"]
        power_used = charge_data["powerUsed"]

        if start_time is None:
            return None

        charging_fee = self._calculate_time_based_fee(start_time, stop_time, power_used)
        service_fee = self.billingRule.get_service_fee() * power_used

        detail_id = str(uuid.uuid4())[:8]
        return ChargingDetail(
            detail_id=detail_id,
            pile_id=pile_id,
            energy_amount=power_used,
            start_time=start_time,
            stop_time=stop_time,
            charging_fee=charging_fee,
            service_fee=service_fee
        )

    def _calculate_time_based_fee(
        self, start_time: datetime, stop_time: datetime, total_power: float
    ) -> float:
        """
        跨时段分段计费：
        将充电时长按小时切分，各段电量按时间比例分配，
        分别乘以对应时段电价后累加。
        """
        total_duration = (stop_time - start_time).total_seconds()
        if total_duration <= 0:
            return 0.0

        total_fee = 0.0
        current_time = start_time

        while current_time < stop_time:
            next_hour = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(next_hour, stop_time)

            segment_duration = (segment_end - current_time).total_seconds()
            segment_ratio = segment_duration / total_duration
            segment_power = total_power * segment_ratio

            price = self.billingRule.get_price_per_kwh(current_time)
            total_fee += price * segment_power

            current_time = segment_end

        return total_fee
